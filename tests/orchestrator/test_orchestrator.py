"""Unit and integration tests for the Agentic SDLC Orchestration Engine."""

import json
from pathlib import Path
import pytest

from src.orchestrator.models import (
    RiskTier,
    TaskNode,
    TaskStatus,
)
from src.orchestrator.dag import TaskGraph, CyclicDependencyError
from src.orchestrator.normalizer import RequirementNormalizer
from src.orchestrator.impact_analyzer import CodebaseImpactAnalyzer
from src.orchestrator.governance import GovernancePolicyEngine
from src.orchestrator.resilience import ResilienceController
from src.orchestrator.ledger import AuditLedger
from src.orchestrator.engine import AgenticOrchestrationEngine


class TestRequirementNormalizer:
    def setup_method(self) -> None:
        self.normalizer = RequirementNormalizer()

    def test_clear_requirement_has_low_ambiguity(self) -> None:
        prompt = (
            "Implement a Base62 URL shortener endpoint that accepts POST requests, "
            "validates RFC URLs, and stores records in SQLite with a 3600 second TTL."
        )
        norm = self.normalizer.analyze(prompt)
        assert norm.ambiguity_score <= 0.35
        assert norm.is_clarified is True

    def test_ambiguous_requirement_flags_clarifications(self) -> None:
        prompt = "Make the shortener super fast, cheap, and enterprise safe."
        norm = self.normalizer.analyze(prompt)
        assert norm.ambiguity_score > 0.40
        assert len(norm.clarifications_needed) >= 2
        assert len(norm.assumptions) >= 1

    def test_database_migration_classified_as_high_risk(self) -> None:
        prompt = "Alter database schema to add user authorization tables and drop legacy columns."
        norm = self.normalizer.analyze(prompt)
        assert norm.risk_tier == RiskTier.HIGH


class TestTaskGraph:
    def test_dag_topological_sort_and_parallel_layers(self) -> None:
        graph = TaskGraph()
        n1 = TaskNode(id="n1", title="Init", stage="requirements")
        n2_a = TaskNode(id="n2_a", title="Domain", stage="impl", dependencies=["n1"])
        n2_b = TaskNode(id="n2_b", title="Infra", stage="impl", dependencies=["n1"])
        n3 = TaskNode(id="n3", title="API", stage="impl", dependencies=["n2_a", "n2_b"])

        graph.add_node(n1)
        graph.add_node(n2_a)
        graph.add_node(n2_b)
        graph.add_node(n3)

        layers = graph.get_parallel_layers()
        assert len(layers) == 3
        # Layer 1 has n1
        assert [n.id for n in layers[0]] == ["n1"]
        # Layer 2 has n2_a and n2_b in parallel
        assert set(n.id for n in layers[1]) == {"n2_a", "n2_b"}
        # Layer 3 has n3 (synchronization barrier)
        assert [n.id for n in layers[2]] == ["n3"]

    def test_detects_dependency_cycle(self) -> None:
        graph = TaskGraph()
        n1 = TaskNode(id="n1", title="A", stage="impl", dependencies=["n2"])
        n2 = TaskNode(id="n2", title="B", stage="impl", dependencies=["n1"])
        graph.add_node(n1)
        graph.add_node(n2)

        with pytest.raises(CyclicDependencyError):
            graph.get_parallel_layers()


class TestCodebaseImpactAnalyzer:
    def test_indexes_symbols_and_computes_blast_radius(self) -> None:
        analyzer = CodebaseImpactAnalyzer(".")
        assert len(analyzer.symbol_definitions) > 0

        report = analyzer.analyze_proposed_change(["src/url_shortener/presentation/api.py"])
        assert "create_app" in report.affected_symbols or len(report.affected_symbols) > 0
        assert report.blast_radius_score > 0.0
        assert len(report.impacted_test_files) > 0


class TestGovernancePolicyEngine:
    def test_detects_forbidden_eval(self, tmp_path: Path) -> None:
        engine = GovernancePolicyEngine(str(tmp_path))
        bad_file = tmp_path / "unsafe.py"
        bad_file.write_text("result = eval('2 + 2')\n", encoding="utf-8")

        res = engine.evaluate_security_guardrails(["unsafe.py"])
        assert res.passed is False
        assert any("eval" in v for v in res.violations)

    def test_passes_clean_code(self, tmp_path: Path) -> None:
        engine = GovernancePolicyEngine(str(tmp_path))
        clean_file = tmp_path / "clean.py"
        clean_file.write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")

        res = engine.evaluate_security_guardrails(["clean.py"])
        assert res.passed is True


class TestAuditLedger:
    def test_hash_chaining_and_integrity_verification(self, tmp_path: Path) -> None:
        ledger_file = tmp_path / "test_ledger.jsonl"
        ledger = AuditLedger(str(ledger_file))

        ledger.log_event("run_1", "stage1", "EVENT_A", {"key": "val1"})
        ledger.log_event("run_1", "stage2", "EVENT_B", {"key": "val2"})
        ledger.log_event("run_1", "stage3", "EVENT_C", {"key": "val3"})

        assert ledger.verify_integrity() is True

        # Tamper with file
        lines = ledger_file.read_text(encoding="utf-8").splitlines()
        tampered = json.loads(lines[1])
        tampered["payload"]["key"] = "TAMPERED_VAL"
        lines[1] = json.dumps(tampered)
        ledger_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Must detect tampering
        assert ledger.verify_integrity() is False


class TestAgenticEngineEndToEnd:
    def test_greenfield_workflow_execution(self, tmp_path: Path) -> None:
        ledger_file = tmp_path / "run_ledger.jsonl"
        engine = AgenticOrchestrationEngine(
            workspace_dir=".",
            ledger_path=str(ledger_file),
            auto_approve_hitl=True,
            test_command=["python3", "-c", "import sys; sys.exit(0)"],
        )

        prompt = (
            "Implement an advanced Analytics Aggregator service for the URL shortener "
            "that collects daily click counts, tracks top referrers, and provides query API."
        )

        outcome = engine.run_sdlc(prompt, is_brownfield=False)
        assert outcome["status"] == "COMPLETED"
        assert outcome["normalized_requirement"].ambiguity_score <= 0.50
        assert ledger_file.exists()
        assert engine.ledger.verify_integrity() is True

    def test_brownfield_workflow_with_hitl_approval(self, tmp_path: Path) -> None:
        ledger_file = tmp_path / "brownfield_ledger.jsonl"
        engine = AgenticOrchestrationEngine(
            workspace_dir=".",
            ledger_path=str(ledger_file),
            auto_approve_hitl=True,
            test_command=["python3", "-c", "import sys; sys.exit(0)"],
        )

        prompt = (
            "Refactor redirect endpoint to add Redis-backed sliding window rate limiter "
            "without breaking existing client contracts."
        )

        outcome = engine.run_sdlc(
            prompt,
            is_brownfield=True,
            modified_files_hint=["src/url_shortener/presentation/api.py"],
        )
        assert outcome["status"] == "COMPLETED"
        assert outcome["impact_report"] is not None
        assert outcome["impact_report"].blast_radius_score > 0.0

    def test_hitl_rejection_halts_and_rolls_back(self, tmp_path: Path) -> None:
        ledger_file = tmp_path / "rejected_ledger.jsonl"
        engine = AgenticOrchestrationEngine(
            workspace_dir=".",
            ledger_path=str(ledger_file),
            auto_approve_hitl=False,
            test_command=["python3", "-c", "import sys; sys.exit(0)"],
        )

        prompt = "Drop user accounts table to clean up disk space."

        # Simulate human operator rejecting the change
        with pytest.raises(PermissionError, match="Human operator rejected"):
            engine.run_sdlc(
                prompt,
                is_brownfield=True,
                hitl_callback=lambda p: "REJECT",
            )

        assert engine.state.value == "SAFE_STOP"



class TestCommandLineInterface:
    def test_cli_metrics_display(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
        from src.orchestrator.cli import run_cli

        monkeypatch.setattr("sys.argv", ["cli.py", "--metrics"])
        with pytest.raises(SystemExit) as excinfo:
            run_cli()
        assert excinfo.value.code == 0
        captured = capsys.readouterr().out
        assert "Telemetry & Reliability Metrics" in captured
        assert "Audit Ledger Hash Valid" in captured

    def test_cli_greenfield_execution(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
        from src.orchestrator.cli import run_cli
        from src.orchestrator.models import NormalizedRequirement, RiskTier

        # Mock run_sdlc to prevent recursive pytest invocation
        dummy_req = NormalizedRequirement(
            raw_prompt="test",
            intent="test",
            ambiguity_score=0.1,
            risk_tier=RiskTier.LOW,
            is_clarified=True,
        )
        monkeypatch.setattr(
            "src.orchestrator.engine.AgenticOrchestrationEngine.run_sdlc",
            lambda self, raw_prompt, is_brownfield=False: {
                "run_id": "mock_run_123",
                "status": "COMPLETED",
                "elapsed_seconds": 1.23,
                "normalized_requirement": dummy_req,
            },
        )

        monkeypatch.setattr("sys.argv", ["cli.py", "--scenario", "greenfield"])
        run_cli()
        captured = capsys.readouterr().out
        assert "SDLC ORCHESTRATION COMPLETED SUCCESSFULLY" in captured
        assert "mock_run_123" in captured
