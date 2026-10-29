"""Audit-grade JSONL event ledger with SHA-256 hash-chaining and telemetry tracking."""

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional

from src.orchestrator.models import AuditEvent, TelemetryMetrics


class AuditLedger:
    """Tamper-evident audit ledger recording decision lineage and reliability metrics."""

    GENESIS_HASH = "0" * 64

    def __init__(self, ledger_path: str = "artifacts/audit_ledger.jsonl") -> None:
        self.ledger_path = Path(ledger_path)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._last_hash = self._recover_last_hash()

    def _recover_last_hash(self) -> str:
        if not self.ledger_path.exists():
            return self.GENESIS_HASH

        last_hash = self.GENESIS_HASH
        with open(self.ledger_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        record = json.loads(line)
                        last_hash = record.get("hash", self.GENESIS_HASH)
                    except json.JSONDecodeError:
                        continue
        return last_hash

    def log_event(
        self,
        run_id: str,
        stage: str,
        event_type: str,
        payload: Dict[str, Any],
    ) -> AuditEvent:
        with self._lock:
            event = AuditEvent(
                run_id=run_id,
                stage=stage,
                event_type=event_type,
                payload=payload,
                previous_hash=self._last_hash,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

            payload_str = json.dumps(payload, sort_keys=True)
            raw_signature = f"{self._last_hash}|{run_id}|{stage}|{event_type}|{payload_str}|{event.timestamp}"
            event.hash = hashlib.sha256(raw_signature.encode("utf-8")).hexdigest()

            with open(self.ledger_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(event)) + "\n")

            self._last_hash = event.hash
            return event

    def verify_integrity(self) -> bool:
        if not self.ledger_path.exists():
            return True

        with self._lock:
            prev_hash = self.GENESIS_HASH
            with open(self.ledger_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    if record["previous_hash"] != prev_hash:
                        return False

                    payload_str = json.dumps(record["payload"], sort_keys=True)
                    raw_sig = f"{record['previous_hash']}|{record['run_id']}|{record['stage']}|{record['event_type']}|{payload_str}|{record['timestamp']}"
                    expected_hash = hashlib.sha256(raw_sig.encode("utf-8")).hexdigest()
                    if record["hash"] != expected_hash:
                        return False

                    prev_hash = record["hash"]
            return True

    def compute_metrics(self) -> TelemetryMetrics:
        if not self.ledger_path.exists():
            return TelemetryMetrics()

        runs: Dict[str, Dict[str, Any]] = {}
        retries = 0
        rollbacks = 0
        repair_durations: List[float] = []

        with self._lock:
            with open(self.ledger_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    rid = event["run_id"]
                    if rid not in runs:
                        runs[rid] = {
                            "started": event["timestamp"],
                            "ended": event["timestamp"],
                            "status": "UNKNOWN",
                            "has_healed": False,
                            "healing_start": None,
                        }

                    runs[rid]["ended"] = event["timestamp"]

                    etype = event["event_type"]
                    if etype == "RETRY":
                        retries += 1
                        if runs[rid]["healing_start"] is None:
                            runs[rid]["healing_start"] = event["timestamp"]
                    elif etype == "ROLLBACK":
                        rollbacks += 1
                    elif etype == "TASK_COMPLETE" and runs[rid]["healing_start"]:
                        try:
                            t_start = datetime.fromisoformat(runs[rid]["healing_start"])
                            t_end = datetime.fromisoformat(event["timestamp"])
                            repair_durations.append((t_end - t_start).total_seconds())
                            runs[rid]["healing_start"] = None
                        except Exception:
                            pass
                    elif etype == "WORKFLOW_COMPLETE":
                        runs[rid]["status"] = "COMPLETED"
                    elif etype in ("WORKFLOW_FAILED", "SAFE_STOP"):
                        runs[rid]["status"] = "FAILED"

        workflow_runs = [r for r in runs.values() if r["status"] in ("COMPLETED", "FAILED")]
        total_runs = len(workflow_runs)
        completed = sum(1 for r in workflow_runs if r["status"] == "COMPLETED")
        failed = sum(1 for r in workflow_runs if r["status"] == "FAILED")
        success_rate = (completed / total_runs * 100.0) if total_runs > 0 else 100.0
        mttr = (sum(repair_durations) / len(repair_durations)) if repair_durations else 0.0

        return TelemetryMetrics(
            total_runs=total_runs,
            completed_runs=completed,
            failed_runs=failed,
            total_retries=retries,
            total_rollbacks=rollbacks,
            mean_time_to_repair_seconds=round(mttr, 2),
            success_rate_percent=round(success_rate, 2),
        )

