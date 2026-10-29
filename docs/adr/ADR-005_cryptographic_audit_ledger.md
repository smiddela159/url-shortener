# ADR-005: Cryptographic SHA-256 Hash-Chained Audit Ledger for Lineage

**Status:** Accepted  
**Date:** 2026-10-28  
**Author:** Staff AI Systems Engineer  
**Classification:** Financial Enterprise Grade (Schwab Internal Standard Compliance)  

---

## 1. Context & Problem Statement
Regulatory oversight in financial systems (e.g. FINRA, SEC, Schwab Internal Compliance) mandates an immutable, audit-grade history of automated changes. Standard console logging or transient text files can be altered, truncated, or forged, making forensic analysis and decision lineage verification impossible.

## 2. Decision
We implement an **Append-Only Cryptographic Audit Ledger** ([`src/orchestrator/ledger.py`](file:///Users/niharikapasham/Documents/workspace/url-shortener/src/orchestrator/ledger.py)) storing JSON Lines in [`artifacts/audit_ledger.jsonl`](file:///Users/niharikapasham/Documents/workspace/url-shortener/artifacts/audit_ledger.jsonl).

### 2.1 Cryptographic Hash-Chaining Formula
Every event record is cryptographically tied to the preceding event:
$$\text{hash}_n = \text{SHA-256}(\text{hash}_{n-1} \parallel \text{run\_id} \parallel \text{stage} \parallel \text{event\_type} \parallel \text{payload\_json} \parallel \text{timestamp})$$

The genesis record uses:
$$\text{hash}_0 = \text{"0"}^{64}$$

### 2.2 Event Envelope Schema
```json
{
  "run_id": "run_4d14d5bcb3d9",
  "stage": "requirements",
  "event_type": "REQUIREMENT_NORMALIZED",
  "payload": {
    "intent": "Implement an advanced Analytics Aggregator...",
    "ambiguity_score": 0.20,
    "risk_tier": "LOW"
  },
  "previous_hash": "136a0cc81224183e4c850b8fba16433abd49b7e05f87f3a791dd2dce33b9b6d6",
  "event_id": "0fe21487-c5aa-4464-8805-dd653104d11c",
  "timestamp": "2026-10-28T04:39:46.421928+00:00",
  "hash": "818f4a1e02a038d1d5b9ee2a0a4998bc1422bbc7cff6ce32425de969f5a9c4b7"
}
```

## 3. Real-Time Integrity Verification
The ledger provides an automated verification method:
`AuditLedger.verify_integrity() -> bool`
This recalculates every SHA-256 hash in sequence from the genesis block. If any character, timestamp, payload property, or link is modified or deleted, the hash chain breaks instantly, flagging the file as tampered.

## 4. Consequences
- **Tamper Evidence:** 100% mathematical guarantee that historical agent decisions cannot be altered post-execution.
- **Decision Lineage:** Every line of code committed is traceable back to the raw prompt, normalized acceptance criteria, AST impact report, and HITL approval.
- **Reliability Telemetry:** MTTR, success rate, retry count, and latency are computed directly from the immutable event history.

