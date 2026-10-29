"""Governance Policy Guardrails and Human-In-The-Loop (HITL) Checkpoint Gate."""

import ast
from pathlib import Path
from typing import Callable, List, Optional

from src.orchestrator.models import GateResult, ImpactReport, RiskTier, TaskNode

FORBIDDEN_CALLS = frozenset({"eval", "exec"})
FORBIDDEN_MODULES = frozenset({"pickle", "telnetlib"})


class GovernancePolicyEngine:
    """Enforces architectural constraints, security guardrails, and HITL authorization."""

    def __init__(self, root_dir: str = ".") -> None:
        self.root_dir = Path(root_dir)

    def evaluate_security_guardrails(self, file_paths: List[str]) -> GateResult:
        violations: List[str] = []

        for rel_path in file_paths:
            full_path = self.root_dir / rel_path
            if not full_path.exists() or not rel_path.endswith(".py"):
                continue

            try:
                content = full_path.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=rel_path)
            except Exception as exc:
                violations.append(f"Failed to parse AST for {rel_path}: {exc}")
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
                        violations.append(f"Security Policy Violation in {rel_path}: Forbidden call to '{node.func.id}'")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in FORBIDDEN_MODULES:
                            violations.append(f"Security Policy Violation in {rel_path}: Prohibited module import '{alias.name}'")
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module.split(".")[0] in FORBIDDEN_MODULES:
                        violations.append(f"Security Policy Violation in {rel_path}: Prohibited module import '{node.module}'")

            if "src/url_shortener/domain/" in rel_path:
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom) and node.module:
                        if "presentation" in node.module or "infrastructure" in node.module:
                            violations.append(
                                f"Architectural Invariant Violation in {rel_path}: "
                                f"Domain layer cannot import from outer layer '{node.module}'"
                            )

        passed = len(violations) == 0
        reason = "All security and architectural guardrails passed." if passed else "Guardrail violations detected."
        return GateResult(
            gate_name="SECURITY_AND_ARCHITECTURE_POLICY_GATE",
            passed=passed,
            reason=reason,
            violations=violations,
        )

    def is_hitl_required(self, task: TaskNode, impact: Optional[ImpactReport] = None) -> bool:
        if task.risk_tier == RiskTier.HIGH:
            return True
        if impact:
            if impact.is_breaking_change:
                return True
            if impact.requires_schema_migration:
                return True
            if impact.blast_radius_score >= 0.40:
                return True
        return False

    def request_approval(
        self,
        task: TaskNode,
        impact: Optional[ImpactReport] = None,
        auto_approve: bool = False,
        prompt_callback: Optional[Callable[[str], str]] = None,
    ) -> str:
        prompt_lines = [
            "\n" + "=" * 65,
            " [HITL GOVERNANCE CHECKPOINT REQUIRED]",
            f" Task ID:     {task.id} ({task.title})",
            f" Risk Tier:   {task.risk_tier.value}",
        ]
        if impact:
            prompt_lines.append(f" Blast Radius: {impact.blast_radius_score * 100:.0f}%")
            prompt_lines.append(f" Breaking:     {impact.is_breaking_change}")
            prompt_lines.append(f" Schema Alter: {impact.requires_schema_migration}")
            prompt_lines.append(f" Target Files: {', '.join(impact.target_files)}")
        prompt_lines.append(" Action Required: [A]pprove / [R]eject / Re-[P]lan")
        prompt_lines.append("=" * 65)

        full_prompt = "\n".join(prompt_lines)

        if auto_approve:
            return "APPROVED"

        if prompt_callback:
            decision = prompt_callback(full_prompt).strip().upper()
        else:
            print(full_prompt)
            decision = input("Enter decision [A/R/P]: ").strip().upper()

        if decision in ("A", "APPROVE", "APPROVED"):
            return "APPROVED"
        elif decision in ("P", "PLAN", "REPLAN", "RE_PLAN"):
            return "RE_PLAN"
        else:
            return "REJECTED"

