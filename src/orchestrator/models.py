"""Typed schemas and data models for the Agentic Orchestration Engine."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class WorkflowState(str, Enum):
    """Finite state machine states for the SDLC orchestration workflow."""
    INITIALIZED = "INITIALIZED"
    NORMALIZING = "NORMALIZING"
    PLANNING = "PLANNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    HEALING = "HEALING"
    COMPLETED = "COMPLETED"
    ROLLED_BACK = "ROLLED_BACK"
    SAFE_STOP = "SAFE_STOP"


class RiskTier(str, Enum):
    """Categorizes the blast radius and risk of engineering tasks."""
    LOW = "LOW"        # Autonomous: scaffolding, unit test creation, linting, formatting
    MEDIUM = "MEDIUM"  # Autonomous with verification: internal non-breaking refactors
    HIGH = "HIGH"      # Human-In-The-Loop required: schema migrations, breaking API changes, security changes


class TaskStatus(str, Enum):
    """Status of an individual task node within the DAG."""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    SKIPPED = "SKIPPED"


@dataclass
class NormalizedRequirement:
    """Requirement normalized from natural language with ambiguity quantification."""
    raw_prompt: str
    intent: str
    ambiguity_score: float  # 0.0 (perfectly clear) to 1.0 (completely ambiguous)
    clarifications_needed: List[str] = field(default_factory=list)
    user_stories: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    risk_tier: RiskTier = RiskTier.LOW
    is_clarified: bool = False


@dataclass
class TaskNode:
    """Discrete executable node in the SDLC Directed Acyclic Graph."""
    id: str
    title: str
    stage: str  # requirements, architecture, implementation, testing, documentation, release
    dependencies: List[str] = field(default_factory=list)
    preconditions: List[str] = field(default_factory=list)
    postconditions: List[str] = field(default_factory=list)
    risk_tier: RiskTier = RiskTier.LOW
    status: TaskStatus = TaskStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    output_artifacts: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class ImpactReport:
    """Codebase blast-radius assessment produced by AST analysis."""
    target_files: List[str] = field(default_factory=list)
    affected_symbols: List[str] = field(default_factory=list)
    is_breaking_change: bool = False
    requires_schema_migration: bool = False
    impacted_test_files: List[str] = field(default_factory=list)
    blast_radius_score: float = 0.0  # 0.0 (localized) to 1.0 (system-wide)
    summary: str = ""


@dataclass
class GateResult:
    """Outcome of an entry or exit verification gate."""
    gate_name: str
    passed: bool
    reason: str
    violations: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AuditEvent:
    """Immutable audit-grade log event tracking decision lineage."""
    run_id: str
    stage: str
    event_type: str
    payload: Dict[str, Any]
    previous_hash: str
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    hash: str = ""


@dataclass
class TelemetryMetrics:
    """Real-time reliability and performance metrics."""
    total_runs: int = 0
    completed_runs: int = 0
    failed_runs: int = 0
    total_retries: int = 0
    total_rollbacks: int = 0
    mean_time_to_repair_seconds: float = 0.0
    average_workflow_latency_seconds: float = 0.0
    success_rate_percent: float = 100.0

