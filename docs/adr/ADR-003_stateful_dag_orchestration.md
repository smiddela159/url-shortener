# ADR-003: Stateful DAG-Based Orchestration vs Linear Prompt Chaining

**Status:** Accepted  
**Date:** 2026-10-28  
**Author:** Staff AI Systems Engineer  
**Classification:** Financial Enterprise Grade (Schwab Internal Standard Compliance)  

---

## 1. Context & Problem Statement
Naive AI coding assistants and script generators rely on **linear prompt chaining** (e.g. Prompt 1 $\rightarrow$ Output 1 $\rightarrow$ Prompt 2 $\rightarrow$ Output 2). 

Linear chaining exhibits critical architectural flaws:
1. **No Parallel Execution:** Independent tasks (e.g. implementing domain entities and infrastructure adapters) cannot execute concurrently.
2. **Error Cascades:** A failure in step 3 propagates unhandled errors downstream without rollback or self-healing.
3. **No State Persistence:** Interrupted runs lose state and cannot be resumed or re-planned dynamically.
4. **Lack of Entry/Exit Governance:** Linear chains lack deterministic verification gates, human-in-the-loop checkpoints, and explicit pre/postconditions.

## 2. Decision
We design and implement a **Stateful, Directed Acyclic Graph (DAG) Workflow Engine** ([`src/orchestrator/dag.py`](file:///Users/niharikapasham/Documents/workspace/url-shortener/src/orchestrator/dag.py)) governed by an explicit Finite State Machine ([`src/orchestrator/models.py`](file:///Users/niharikapasham/Documents/workspace/url-shortener/src/orchestrator/models.py)):

1. **Topological Parallel Layering:** The graph dynamically computes topological layers where independent nodes execute in parallel, synchronizing at defined join barriers before advancing.
2. **Explicit Entry/Exit Gates:** Each task node defines typed preconditions, postconditions, and risk tiers.
3. **Dynamic Re-planning:** If an upstream task fails or its output alters downstream requirements, the orchestrator invalidates the downstream subgraph and dynamically restructures the DAG.
4. **Finite State Transitions:** State transitions (`NORMALIZING`, `PLANNING`, `AWAITING_APPROVAL`, `EXECUTING`, `VERIFYING`, `HEALING`, `COMPLETED`, `ROLLED_BACK`, `SAFE_STOP`) are strictly logged and enforced.

## 3. Consequences & Trade-offs
### Positive:
- **Governance:** High-impact tasks are trapped before execution; low-impact tasks execute autonomously.
- **Resilience:** Integrates cleanly with bounded retries ($\le 3$) and automated Git rollback.
- **Traceability:** Every DAG transition is recorded in the cryptographic audit ledger.

### Negative / Mitigations:
- **Complexity:** Requires graph construction and topological sorting. Mitigated by `SDLCPlanner`, which generates standardized SDLC templates tailored to requirement risk.

