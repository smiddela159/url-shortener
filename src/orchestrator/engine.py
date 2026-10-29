"""Central Stateful Orchestration Engine coordinating the complete SDLC workflow."""

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import time
from typing import Any, Callable, Dict, List, Optional
import uuid

from src.orchestrator.models import (
    WorkflowState,
    RiskTier,
    TaskStatus,
    NormalizedRequirement,
    TaskNode,
    ImpactReport,
    GateResult,
    TelemetryMetrics,
)
from src.orchestrator.dag import TaskGraph
from src.orchestrator.normalizer import RequirementNormalizer
from src.orchestrator.planner import SDLCPlanner
from src.orchestrator.impact_analyzer import CodebaseImpactAnalyzer
from src.orchestrator.governance import GovernancePolicyEngine
from src.orchestrator.resilience import ResilienceController, CheckpointResult
from src.orchestrator.ledger import AuditLedger


class AgenticOrchestrationEngine:
    """Stateful, DAG-driven SDLC Orchestration Engine with governance and bounded autonomy."""

    def __init__(
        self,
        workspace_dir: str = ".",
        ledger_path: str = "artifacts/audit_ledger.jsonl",
        auto_approve_hitl: bool = True,
        test_command: Optional[List[str]] = None,
    ) -> None:
        self.workspace_dir = workspace_dir
        self.auto_approve_hitl = auto_approve_hitl
        self.test_command = test_command or ["pytest", "-v"]

        self.normalizer = RequirementNormalizer()
        self.planner = SDLCPlanner()
        self.impact_analyzer = CodebaseImpactAnalyzer(workspace_dir)
        self.governance = GovernancePolicyEngine(workspace_dir)
        self.resilience = ResilienceController(workspace_dir)
        self.ledger = AuditLedger(ledger_path)

        self.state = WorkflowState.INITIALIZED
        self.active_run_id: Optional[str] = None
        self.current_checkpoint: Optional[CheckpointResult] = None
        self.context: Dict[str, Any] = {}

    def run_sdlc(
        self,
        raw_prompt: str,
        is_brownfield: bool = False,
        modified_files_hint: Optional[List[str]] = None,
        hitl_callback: Optional[Callable[[str], str]] = None,
    ) -> Dict[str, Any]:
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        self.active_run_id = run_id
        start_time = time.time()
        self.context = {"run_id": run_id, "raw_prompt": raw_prompt, "is_brownfield": is_brownfield}

        self.ledger.log_event(
            run_id=run_id,
            stage="workflow",
            event_type="WORKFLOW_START",
            payload={"prompt": raw_prompt, "is_brownfield": is_brownfield},
        )

        try:
            # 1. State: NORMALIZING
            self.state = WorkflowState.NORMALIZING
            norm_spec = self.normalizer.analyze(raw_prompt)
            self.context["normalized_requirement"] = asdict(norm_spec)

            self.ledger.log_event(
                run_id=run_id,
                stage="requirements",
                event_type="REQUIREMENT_NORMALIZED",
                payload={
                    "intent": norm_spec.intent,
                    "ambiguity_score": norm_spec.ambiguity_score,
                    "clarifications": norm_spec.clarifications_needed,
                    "risk_tier": norm_spec.risk_tier.value,
                    "is_clarified": norm_spec.is_clarified,
                },
            )

            # 2. State: PLANNING
            self.state = WorkflowState.PLANNING
            dag = self.planner.build_plan(norm_spec, is_brownfield=is_brownfield)
            parallel_layers = dag.get_parallel_layers()

            self.ledger.log_event(
                run_id=run_id,
                stage="planning",
                event_type="DAG_PLAN_GENERATED",
                payload={
                    "layer_count": len(parallel_layers),
                    "total_nodes": len(dag.nodes),
                    "nodes": [n.id for n in dag.nodes.values()],
                },
            )

            # 3. Codebase Impact Analysis (if Brownfield)
            impact_report: Optional[ImpactReport] = None
            if is_brownfield:
                files_to_check = modified_files_hint or ["src/url_shortener/presentation/api.py"]
                impact_report = self.impact_analyzer.analyze_proposed_change(files_to_check)
                self.context["impact_report"] = asdict(impact_report)

                self.ledger.log_event(
                    run_id=run_id,
                    stage="architecture",
                    event_type="IMPACT_ANALYSIS_COMPLETE",
                    payload=asdict(impact_report),
                )

            # 4. Checkpoint creation prior to execution
            self.current_checkpoint = self.resilience.create_checkpoint(f"Pre-execution {run_id}")

            # 5. State: EXECUTING (Layer-by-Layer Synchronization)
            self.state = WorkflowState.EXECUTING

            for layer_idx, layer in enumerate(parallel_layers, start=1):
                self.ledger.log_event(
                    run_id=run_id,
                    stage="orchestration",
                    event_type="PARALLEL_LAYER_START",
                    payload={"layer_index": layer_idx, "tasks": [t.id for t in layer]},
                )

                for task in layer:
                    self._execute_task_node(
                        task=task,
                        run_id=run_id,
                        norm_spec=norm_spec,
                        impact_report=impact_report,
                        hitl_callback=hitl_callback,
                    )

                self.ledger.log_event(
                    run_id=run_id,
                    stage="orchestration",
                    event_type="PARALLEL_LAYER_SYNC",
                    payload={"layer_index": layer_idx, "status": "SYNCHRONIZED"},
                )

            # 6. Workflow Completed Successfully
            self.state = WorkflowState.COMPLETED
            self.resilience.commit_success(f"SDLC completed for run {run_id}")

            elapsed = round(time.time() - start_time, 2)
            metrics = self.ledger.compute_metrics()

            self.ledger.log_event(
                run_id=run_id,
                stage="workflow",
                event_type="WORKFLOW_COMPLETE",
                payload={"elapsed_seconds": elapsed, "final_state": self.state.value},
            )

            return {
                "run_id": run_id,
                "status": self.state.value,
                "normalized_requirement": norm_spec,
                "impact_report": impact_report,
                "elapsed_seconds": elapsed,
                "metrics": asdict(metrics),
            }

        except Exception as exc:
            self.state = WorkflowState.SAFE_STOP
            self.ledger.log_event(
                run_id=run_id,
                stage="workflow",
                event_type="SAFE_STOP",
                payload={"error": str(exc)},
            )
            if self.current_checkpoint:
                self.resilience.rollback_to_checkpoint(self.current_checkpoint)
                self.ledger.log_event(
                    run_id=run_id,
                    stage="resilience",
                    event_type="ROLLBACK",
                    payload={"target_sha": self.current_checkpoint.sha},
                )
            raise

    def _execute_task_node(
        self,
        task: TaskNode,
        run_id: str,
        norm_spec: NormalizedRequirement,
        impact_report: Optional[ImpactReport],
        hitl_callback: Optional[Callable[[str], str]],
    ) -> None:
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now(timezone.utc)

        self.ledger.log_event(
            run_id=run_id,
            stage=task.stage,
            event_type="TASK_START",
            payload={"task_id": task.id, "title": task.title},
        )

        # HITL Gate Check
        if task.id == "task_hitl_checkpoint" or self.governance.is_hitl_required(task, impact_report):
            self.state = WorkflowState.AWAITING_APPROVAL
            self.ledger.log_event(
                run_id=run_id,
                stage="governance",
                event_type="HITL_REQUEST",
                payload={"task_id": task.id, "risk_tier": task.risk_tier.value},
            )

            decision = self.governance.request_approval(
                task=task,
                impact=impact_report,
                auto_approve=self.auto_approve_hitl,
                prompt_callback=hitl_callback,
            )

            self.ledger.log_event(
                run_id=run_id,
                stage="governance",
                event_type="HITL_DECISION",
                payload={"task_id": task.id, "decision": decision},
            )

            if decision != "APPROVED":
                task.status = TaskStatus.FAILED
                task.error_message = f"HITL Gate rejected: {decision}"
                raise PermissionError(f"Human operator rejected task {task.id}: {decision}")

            self.state = WorkflowState.EXECUTING

        # Task Action Execution with Bounded Retry Loop
        success = False
        while not success and task.retry_count <= task.max_retries:
            try:
                self._dispatch_task_action(task)
                success = True
            except Exception as task_err:
                task.retry_count += 1
                self.ledger.log_event(
                    run_id=run_id,
                    stage=task.stage,
                    event_type="RETRY",
                    payload={
                        "task_id": task.id,
                        "retry_count": task.retry_count,
                        "error": str(task_err),
                    },
                )
                if task.retry_count > task.max_retries:
                    task.status = TaskStatus.FAILED
                    task.error_message = f"Exceeded max retries ({task.max_retries}): {task_err}"
                    raise

                time.sleep(0.05 * task.retry_count)

        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now(timezone.utc)

        self.ledger.log_event(
            run_id=run_id,
            stage=task.stage,
            event_type="TASK_COMPLETE",
            payload={"task_id": task.id, "retries": task.retry_count},
        )

    def _dispatch_task_action(self, task: TaskNode) -> None:
        if task.id == "task_verify_tests":
            res = subprocess.run(
                self.test_command,
                cwd=self.workspace_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if res.returncode != 0:
                raise RuntimeError(f"Automated test verification failed:\n{res.stdout}\n{res.stderr}")

        elif task.id == "task_policy_audit":
            files_to_audit = [
                str(p.relative_to(self.workspace_dir))
                for p in (Path(self.workspace_dir) / "src").rglob("*.py")
            ]
            gate_result = self.governance.evaluate_security_guardrails(files_to_audit)
            if not gate_result.passed:
                raise RuntimeError(f"Security/Architecture policy audit failed: {gate_result.violations}")

        elif task.id == "task_release_readiness":
            if not self.ledger.verify_integrity():
                raise RuntimeError("Audit ledger cryptographic hash chain is invalid!")

