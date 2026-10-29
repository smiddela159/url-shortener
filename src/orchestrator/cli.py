"""Staff AI Engineer Command Line Interface for Agentic SDLC Orchestration."""

import argparse
import json
import sys
from typing import Optional

from src.orchestrator.engine import AgenticOrchestrationEngine
from src.orchestrator.ledger import AuditLedger

SCENARIO_PROMPTS = {
    "greenfield": (
        "Implement an advanced Analytics Aggregator service for the URL shortener "
        "that collects daily click counts, tracks top referrers, identifies browser/device breakdown, "
        "and provides a time-series query API."
    ),
    "brownfield": (
        "Refactor the existing URL redirect endpoint to add distributed Redis-backed caching "
        "and sliding-window rate limiting (100 requests per minute per IP), "
        "ensuring zero breaking changes to existing client contracts."
    ),
    "ambiguous": (
        "Make our URL shortener service enterprise-ready and safe against abuse."
    ),
}


def print_banner() -> None:
    print("\n" + "=" * 70)
    print("  AGENTIC SOFTWARE ENGINEERING SYSTEM - SDLC ORCHESTRATOR")
    print("  Classification: Financial Enterprise Grade (Schwab Internal)")
    print("=" * 70 + "\n")


def run_cli() -> None:
    parser = argparse.ArgumentParser(
        description="Agentic Software Engineering SDLC Orchestration Runner"
    )
    parser.add_argument(
        "--scenario",
        choices=["greenfield", "brownfield", "ambiguous"],
        help="Execute one of the three mandated evaluation scenarios.",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        help="Custom requirement prompt to process through the SDLC orchestrator.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt human operator interactively for HITL governance checkpoints.",
    )
    parser.add_argument(
        "--metrics",
        action="store_true",
        help="Display aggregated reliability telemetry metrics and exit.",
    )

    args = parser.parse_args()
    print_banner()

    ledger = AuditLedger("artifacts/audit_ledger.jsonl")

    if args.metrics:
        metrics = ledger.compute_metrics()
        print("\n--- Telemetry & Reliability Metrics ---")
        print(f"Total Workflow Runs:        {metrics.total_runs}")
        print(f"Completed Runs:             {metrics.completed_runs}")
        print(f"Failed / Halted Runs:       {metrics.failed_runs}")
        print(f"Success Rate:               {metrics.success_rate_percent}%")
        print(f"Total Retries:              {metrics.total_retries}")
        print(f"Total Rollbacks:            {metrics.total_rollbacks}")
        print(f"Mean Time To Repair (MTTR): {metrics.mean_time_to_repair_seconds}s")
        print(f"Audit Ledger Hash Valid:    {ledger.verify_integrity()}\n")
        sys.exit(0)

    if not args.scenario and not args.prompt:
        parser.print_help()
        sys.exit(1)

    raw_prompt = SCENARIO_PROMPTS.get(args.scenario, args.prompt)
    is_brownfield = (args.scenario == "brownfield") or ("refactor" in raw_prompt.lower())

    print(f"[*] Scenario Selected:  {args.scenario or 'Custom Prompt'}")
    print(f"[*] Mode:               {'Interactive HITL' if args.interactive else 'Autonomous with Guardrails'}")
    print(f"[*] Raw Prompt:\n    \"{raw_prompt}\"\n")

    engine = AgenticOrchestrationEngine(
        workspace_dir=".",
        ledger_path="artifacts/audit_ledger.jsonl",
        auto_approve_hitl=not args.interactive,
    )

    try:
        outcome = engine.run_sdlc(
            raw_prompt=raw_prompt,
            is_brownfield=is_brownfield,
        )
        print("\n" + "=" * 70)
        print(" [✓] SDLC ORCHESTRATION COMPLETED SUCCESSFULLY")
        print(f" Run ID:          {outcome['run_id']}")
        print(f" Final State:     {outcome['status']}")
        print(f" Elapsed Time:    {outcome['elapsed_seconds']}s")
        print(f" Ambiguity Score: {outcome['normalized_requirement'].ambiguity_score}")
        print(f" Risk Tier:       {outcome['normalized_requirement'].risk_tier.value}")
        if outcome.get("impact_report"):
            print(f" Blast Radius:    {outcome['impact_report'].blast_radius_score * 100:.0f}%")
        print("=" * 70 + "\n")

    except Exception as exc:
        print("\n" + "=" * 70)
        print(f" [!] ORCHESTRATION TERMINATED: {exc}")
        print("=" * 70 + "\n")
        sys.exit(1)


if __name__ == "__main__":
    run_cli()

