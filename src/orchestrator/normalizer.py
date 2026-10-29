"""Requirement Normalizer and Ambiguity Scoring Engine."""

import re
from typing import List, Tuple

from src.orchestrator.models import NormalizedRequirement, RiskTier

AMBIGUITY_TRIGGERS = [
    (r"\b(fast|quick|high-speed)\b", "Missing concrete latency/throughput SLA targets (e.g. P99 < 20ms)."),
    (r"\b(secure|safe)\b", "Unspecified security controls (SSRF, auth, input sanitization, rate limiting)."),
    (r"\b(enterprise-ready|production-grade)\b", "Undefined operational criteria (monitoring, audit logs, HITL approval)."),
    (r"\b(scale|huge|many)\b", "Missing volumetric parameters (QPS, concurrent connections, dataset size)."),
    (r"\b(cheap|simple|easy)\b", "Subjective complexity/cost goals without architectural boundaries."),
    (r"\b(analytics|stats)\b", "Unspecified aggregation dimensions (daily, referrers, device types, retention)."),
]

HIGH_RISK_TRIGGERS = [
    r"\b(database|schema|migration|drop|alter)\b",
    r"\b(breaking|deprecate|remove|delete endpoint)\b",
    r"\b(auth|permission|secret|credential|token)\b",
    r"\b(security policy|bypass|disable)\b",
]


class RequirementNormalizer:
    """Normalizes natural language prompts into typed, testable engineering specifications."""

    def analyze(self, raw_prompt: str) -> NormalizedRequirement:
        """Analyzes requirement intent, quantifies ambiguity, and builds normalized spec."""
        cleaned = raw_prompt.strip()
        clarifications: List[str] = []
        assumptions: List[str] = []

        # 1. Ambiguity Scoring
        ambiguity_hits = 0
        for pattern, explanation in AMBIGUITY_TRIGGERS:
            if re.search(pattern, cleaned, re.IGNORECASE):
                ambiguity_hits += 1
                clarifications.append(explanation)

        word_count = len(cleaned.split())
        brevity_penalty = max(0.0, (15 - word_count) / 20.0) if word_count < 15 else 0.0
        ambiguity_score = min(1.0, round((ambiguity_hits * 0.20) + brevity_penalty, 2))

        # 2. Risk Tier Classification
        is_high_risk = any(re.search(trig, cleaned, re.IGNORECASE) for trig in HIGH_RISK_TRIGGERS)
        risk_tier = RiskTier.HIGH if is_high_risk else (RiskTier.MEDIUM if ambiguity_score > 0.4 else RiskTier.LOW)

        # 3. Intent Normalization
        intent = self._extract_intent(cleaned)

        # 4. Formulate Standard Engineering Assumptions
        if "analytics" in cleaned.lower():
            assumptions.append("Capture click timestamp, IP, referrer, and user-agent.")
            assumptions.append("Provide aggregation by date, device category, and top referrers.")
        if "rate limit" in cleaned.lower() or "abuse" in cleaned.lower() or "safe" in cleaned.lower():
            assumptions.append("Enforce sliding-window rate limit (100 req/min per IP).")
            assumptions.append("Enforce SSRF blocklist on internal IP ranges.")
        if not any("ttl" in a.lower() for a in assumptions) and ("ttl" in cleaned.lower() or "expire" in cleaned.lower()):
            assumptions.append("Support optional TTL expiration with automated 410 Gone response.")

        # 5. User Stories & Acceptance Criteria
        user_stories, criteria = self._synthesize_criteria(cleaned, intent, assumptions)

        return NormalizedRequirement(
            raw_prompt=raw_prompt,
            intent=intent,
            ambiguity_score=ambiguity_score,
            clarifications_needed=clarifications,
            user_stories=user_stories,
            acceptance_criteria=criteria,
            assumptions=assumptions,
            risk_tier=risk_tier,
            is_clarified=(ambiguity_score <= 0.35),
        )

    def _extract_intent(self, text: str) -> str:
        first_sentence = text.split(".")[0].strip()
        return first_sentence if len(first_sentence) < 120 else first_sentence[:117] + "..."

    def _synthesize_criteria(
        self, text: str, intent: str, assumptions: List[str]
    ) -> Tuple[List[str], List[str]]:
        stories = [
            f"As an API consumer, I want to {intent.lower()} so that the system reliably fulfills the request with low latency."
        ]
        criteria = [
            "Given valid inputs, When the API is invoked, Then the response status must be 200/201 and match schema.",
            "Given invalid or malicious inputs, When the API is invoked, Then the request must be safely rejected with appropriate error code.",
            "Given high concurrency, When requests are executed, Then latency P99 must remain < 50ms without data corruption.",
        ]
        for idx, assumption in enumerate(assumptions, start=1):
            criteria.append(f"Criterion {idx}: {assumption}")

        return stories, criteria

