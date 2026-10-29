"""Task Decomposition and DAG Planner."""

from typing import List

from src.orchestrator.models import NormalizedRequirement, RiskTier, TaskNode, TaskStatus
from src.orchestrator.dag import TaskGraph


class SDLCPlanner:
    """Decomposes normalized requirements into a dependency graph of SDLC stages."""

    def build_plan(self, spec: NormalizedRequirement, is_brownfield: bool = False) -> TaskGraph:
        graph = TaskGraph()

        # Stage 1: Requirements Normalization Gate
        t_req = TaskNode(
            id="task_req_norm",
            title="Requirement Normalization & Boundary Definition",
            stage="requirements",
            risk_tier=RiskTier.LOW,
            postconditions=["NormalizedRequirementSpec validated"],
        )
        graph.add_node(t_req)

        # Stage 2: Architecture & Design
        t_arch = TaskNode(
            id="task_arch_design",
            title="Architecture & Interface Contract Specification",
            stage="architecture",
            dependencies=["task_req_norm"],
            risk_tier=RiskTier.LOW,
            postconditions=["Domain interfaces and DTOs defined"],
        )
        graph.add_node(t_arch)

        prior_dep = "task_arch_design"

        # Stage 3: (If Brownfield) Codebase AST Reasoning
        if is_brownfield:
            t_impact = TaskNode(
                id="task_impact_analysis",
                title="AST Blast-Radius & Codebase Impact Analysis",
                stage="architecture",
                dependencies=["task_arch_design"],
                risk_tier=RiskTier.MEDIUM,
                postconditions=["ImpactReport generated", "Regression test suite identified"],
            )
            graph.add_node(t_impact)
            prior_dep = "task_impact_analysis"

        # Stage 4: Governance & HITL Approval Gate (if High Risk)
        if spec.risk_tier == RiskTier.HIGH or is_brownfield:
            t_hitl = TaskNode(
                id="task_hitl_checkpoint",
                title="Human-In-The-Loop Governance Sign-Off",
                stage="governance",
                dependencies=[prior_dep],
                risk_tier=RiskTier.HIGH,
                postconditions=["Human approval recorded in audit ledger"],
            )
            graph.add_node(t_hitl)
            prior_dep = "task_hitl_checkpoint"

        # Stage 5: Implementation (Parallel Branches for Domain & Infrastructure Scaffolding)
        t_domain = TaskNode(
            id="task_impl_domain",
            title="Domain & Application Core Implementation",
            stage="implementation",
            dependencies=[prior_dep],
            risk_tier=RiskTier.LOW,
            postconditions=["Domain models and UseCases synthesized"],
        )
        graph.add_node(t_domain)

        t_infra = TaskNode(
            id="task_impl_infra",
            title="Infrastructure, Persistence & Security Adapters",
            stage="implementation",
            dependencies=[prior_dep],
            risk_tier=RiskTier.LOW,
            postconditions=["Repositories and cache adapters configured"],
        )
        graph.add_node(t_infra)

        # Stage 6: Presentation Layer Integration (Synchronization Barrier)
        t_present = TaskNode(
            id="task_impl_presentation",
            title="REST API Presentation & Routing Layer",
            stage="implementation",
            dependencies=["task_impl_domain", "task_impl_infra"],
            risk_tier=RiskTier.LOW,
            postconditions=["FastAPI endpoints connected"],
        )
        graph.add_node(t_present)

        # Stage 7: Automated Verification (Tests)
        t_verify = TaskNode(
            id="task_verify_tests",
            title="Automated Test Suite & Regression Verification",
            stage="testing",
            dependencies=["task_impl_presentation"],
            risk_tier=RiskTier.LOW,
            postconditions=["All unit and integration tests pass cleanly"],
        )
        graph.add_node(t_verify)

        # Stage 8: Policy Guardrail Audit
        t_policy = TaskNode(
            id="task_policy_audit",
            title="Architectural & Security Policy Verification Gate",
            stage="governance",
            dependencies=["task_verify_tests"],
            risk_tier=RiskTier.LOW,
            postconditions=["Zero AST security or architectural layer violations"],
        )
        graph.add_node(t_policy)

        # Stage 9: Documentation & Release Readiness
        t_release = TaskNode(
            id="task_release_readiness",
            title="Documentation, OpenAPI Schemas & Release Audit Ledger",
            stage="release",
            dependencies=["task_policy_audit"],
            risk_tier=RiskTier.LOW,
            postconditions=["Audit ledger sealed with SHA-256 chain"],
        )
        graph.add_node(t_release)

        return graph

