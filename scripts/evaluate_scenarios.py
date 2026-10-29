"""Automated Evaluation Runner for the Three Mandated Assessment Scenarios.

Executes Greenfield, Brownfield, and Ambiguous scenarios end-to-end,
records their execution metrics, validates ledger integrity,
and generates structured scenario telemetry artifacts.
"""

from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.orchestrator.engine import AgenticOrchestrationEngine
from src.orchestrator.ledger import AuditLedger

SCENARIOS = {
    "greenfield": {
        "title": "Scenario 1: Greenfield (Advanced Analytics Aggregator)",
        "prompt": (
            "Implement an advanced Analytics Aggregator service for the URL shortener "
            "that collects daily click counts, tracks top referrers, identifies browser/device breakdown, "
            "and provides a time-series query API."
        ),
        "is_brownfield": False,
        "modified_hint": None,
    },
    "brownfield": {
        "title": "Scenario 2: Brownfield (Rate Limiting & Caching Refactor)",
        "prompt": (
            "Refactor the existing URL redirect endpoint to add distributed Redis-backed caching "
            "and sliding-window rate limiting (100 requests per minute per IP), "
            "ensuring zero breaking changes to existing client contracts."
        ),
        "is_brownfield": True,
        "modified_hint": ["src/url_shortener/presentation/api.py", "src/url_shortener/application/use_cases.py"],
    },
    "ambiguous": {
        "title": "Scenario 3: Ambiguous (Enterprise Abuse & Security Hardening)",
        "prompt": (
            "Make our URL shortener service enterprise-ready and safe against abuse."
        ),
        "is_brownfield": False,
        "modified_hint": None,
    },
}


def run_all_scenarios() -> Dict[str, Any]:
    output_dir = Path("artifacts/scenario_runs")
    output_dir.mkdir(parents=True, exist_ok=True)

    ledger_path = "artifacts/audit_ledger.jsonl"
    ledger = AuditLedger(ledger_path)
    engine = AgenticOrchestrationEngine(
        workspace_dir=".",
        ledger_path=ledger_path,
        auto_approve_hitl=True,
    )

    results: Dict[str, Any] = {}

    print("\n" + "=" * 75)
    print("  EXECUTING THE THREE MANDATED SDLC ASSESSMENT SCENARIOS")
    print("  Enterprise Financial Grade (Schwab Internal Standard Compliance)")
    print("=" * 75 + "\n")

    for key, spec in SCENARIOS.items():
        print(f"\n>>> Running {spec['title']}...")
        start = time.time()
        outcome = engine.run_sdlc(
            raw_prompt=spec["prompt"],
            is_brownfield=spec["is_brownfield"],
            modified_files_hint=spec["modified_hint"],
        )
        duration = round(time.time() - start, 2)

        scenario_result = {
            "scenario_key": key,
            "title": spec["title"],
            "raw_prompt": spec["prompt"],
            "run_id": outcome["run_id"],
            "final_state": outcome["status"],
            "elapsed_seconds": duration,
            "ambiguity_score": outcome["normalized_requirement"].ambiguity_score,
            "is_clarified": outcome["normalized_requirement"].is_clarified,
            "risk_tier": outcome["normalized_requirement"].risk_tier.value,
            "user_stories": outcome["normalized_requirement"].user_stories,
            "acceptance_criteria": outcome["normalized_requirement"].acceptance_criteria,
            "assumptions": outcome["normalized_requirement"].assumptions,
            "impact_report": asdict(outcome["impact_report"]) if outcome.get("impact_report") else None,
        }

        # Save individual run artifact
        run_file = output_dir / f"{key}_result.json"
        run_file.write_text(json.dumps(scenario_result, indent=2), encoding="utf-8")
        results[key] = scenario_result

        print(f"  [✓] Completed: {outcome['run_id']} in {duration}s")
        print(f"      Ambiguity Score: {scenario_result['ambiguity_score']} | Risk: {scenario_result['risk_tier']}")
        if scenario_result["impact_report"]:
            print(f"      Blast Radius:    {scenario_result['impact_report']['blast_radius_score'] * 100:.0f}%")

    # Global Telemetry
    metrics = ledger.compute_metrics()
    is_ledger_valid = ledger.verify_integrity()

    results["telemetry"] = {
        "metrics": asdict(metrics),
        "ledger_integrity_verified": is_ledger_valid,
    }

    summary_file = Path("artifacts/scenario_evaluation_summary.json")
    summary_file.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print("\n" + "=" * 75)
    print("  SCENARIO EVALUATION EXECUTION COMPLETE")
    print(f"  Total Runs:          {metrics.total_runs}")
    print(f"  Success Rate:        {metrics.success_rate_percent}%")
    print(f"  Audit Ledger Hash:   {'VALID (Intact SHA-256 Chain)' if is_ledger_valid else 'INVALID'}")
    print("=" * 75 + "\n")

    return results


if __name__ == "__main__":
    run_all_scenarios()
