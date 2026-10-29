"""Resilience Controller: Bounded retries (<=3), Git checkpointing, rollback, and safe-stop."""

from dataclasses import dataclass
import subprocess
import time
from typing import Optional


@dataclass
class CheckpointResult:
    sha: str
    timestamp: float
    description: str


class ResilienceController:
    """Controls Git state checkpointing, automated rollbacks, and bounded self-healing loops."""

    MAX_RETRIES = 3

    def __init__(self, workspace_dir: str = ".") -> None:
        self.workspace_dir = workspace_dir

    def _run_git(self, args: list[str]) -> str:
        res = subprocess.run(
            ["git"] + args,
            cwd=self.workspace_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        return res.stdout.strip()

    def get_current_head(self) -> str:
        try:
            return self._run_git(["rev-parse", "HEAD"])
        except Exception:
            return "UNKNOWN_HEAD"

    def create_checkpoint(self, description: str) -> CheckpointResult:
        sha = self.get_current_head()
        return CheckpointResult(
            sha=sha,
            timestamp=time.time(),
            description=description,
        )

    def rollback_to_checkpoint(self, checkpoint: CheckpointResult) -> bool:
        try:
            from pathlib import Path
            # Preserve append-only audit ledger across code-level git rollbacks
            ledger_path = Path(self.workspace_dir) / "artifacts" / "audit_ledger.jsonl"
            ledger_backup = None
            if ledger_path.exists():
                ledger_backup = ledger_path.read_bytes()

            self._run_git(["checkout", "--", "."])
            if checkpoint.sha and checkpoint.sha != "UNKNOWN_HEAD":
                self._run_git(["reset", "--hard", checkpoint.sha])

            # Restore audit ledger to maintain cryptographic append-only integrity
            if ledger_backup is not None:
                ledger_path.parent.mkdir(parents=True, exist_ok=True)
                ledger_path.write_bytes(ledger_backup)

            return True
        except Exception as exc:
            print(f"[RESILIENCE ERROR] Rollback failed: {exc}")
            return False

    def commit_success(self, message: str) -> Optional[str]:
        try:
            from pathlib import Path
            targets = [d for d in ["src", "tests", "docs", "artifacts"] if (Path(self.workspace_dir) / d).exists()]
            if targets:
                self._run_git(["add"] + targets)
            status = self._run_git(["status", "--porcelain"])
            if not status:
                return self.get_current_head()
            self._run_git(["commit", "-m", f"agent(orchestrator): {message}"])
            return self.get_current_head()
        except Exception as exc:
            print(f"[RESILIENCE NOTICE] Commit skipped or failed: {exc}")
            return None
