"""Deterministic strategy selection by trigger family and recipient scope."""
from __future__ import annotations

import re


# Specific trigger families come before broader words such as "seasonal" or
# "customer" so composite kinds always resolve to their intended strategy.
_ROUTES = (
    (("active_planning_intent", "planning_intent"), "action-draft"),
    (("cde_opportunity",), "education-opportunity"),
    (("seasonal_perf_dip",), "loss-aversion-action"),
    (("perf_dip", "performance_dip"), "loss-aversion-action"),
    (("perf_spike", "performance_spike"), "celebration-growth"),
    (("appointment",), "appointment-reminder"),
    (("recall",), "customer-convenience"),
    (("refill",), "customer-convenience"),
    (("lapsed_hard", "customer_lapsed_hard"), "careful-winback"),
    (("lapsed", "winback"), "customer-winback"),
    (("milestone",), "social-proof"),
    (("festival", "holiday"), "seasonal-opportunity"),
    (("weather", "local_event", "news"), "local-relevance"),
    (("competitor",), "factual-curiosity"),
    (("trend",), "trend-curiosity"),
    (("renewal",), "plan-status-action"),
    (("dormant",), "reactivation-curiosity"),
    (("curious",), "merchant-question"),
    (("review",), "service-insight"),
    (("regulation", "compliance"), "compliance-information"),
    (("profile", "gbp_unverified"), "profile-improvement"),
    (("research", "digest"), "knowledge-curiosity"),
    (("seasonal", "category_seasonal"), "seasonal-opportunity"),
)


def route_trigger(trigger: dict | None) -> str:
    if not isinstance(trigger, dict):
        return "contextual-specificity"
    raw = trigger.get("kind") or trigger.get("type") or trigger.get("trigger_type") or "unknown"
    kind = re.sub(r"[^a-z0-9]+", "_", str(raw).lower()).strip("_")
    for keys, strategy in _ROUTES:
        if any(key in kind for key in keys):
            return strategy
    if str(trigger.get("scope", "")).lower() == "customer":
        return "customer-convenience"
    return "contextual-specificity"
