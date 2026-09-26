"""Allowlisted, trigger-aware context selection for model prompts and replay."""
from __future__ import annotations

import re

_SENSITIVE_KEY_PARTS = ("phone", "email", "secret", "token", "password", "ssn", "private", "internal", "redacted")


def _public_value(value):
    """Remove obvious private/internal fields from nested prompt context."""
    if isinstance(value, dict):
        return {k: _public_value(v) for k, v in value.items()
                if not any(part in str(k).lower() for part in _SENSITIVE_KEY_PARTS)}
    if isinstance(value, list):
        return [_public_value(v) for v in value]
    return value


def _public_text(value):
    text = str(value)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[redacted email]", text)
    text = re.sub(r"(?<!\w)(?:\+?\d[\d ()-]{7,}\d)(?!\w)", "[redacted phone]", text)
    return text


def _identity(identity, allowed):
    if not isinstance(identity, dict):
        return {}
    return {key: _public_value(identity[key]) for key in allowed if key in identity}


def select_context(category, merchant, trigger, customer=None, history=()):
    category = category if isinstance(category, dict) else {}
    merchant = merchant if isinstance(merchant, dict) else {}
    trigger = trigger if isinstance(trigger, dict) else {}
    customer = customer if isinstance(customer, dict) else None
    kind = str(trigger.get("kind", "")).lower()
    shared = {"slug": category.get("slug"), "voice": _public_value(category.get("voice", {}))}
    identity_keys = ("name", "owner_first_name", "business_name", "city", "locality", "languages", "language_pref", "category_slug")
    merchant_data = {"identity": _identity(merchant.get("identity"), identity_keys)}
    for key in ("offers", "performance", "signals", "customer_aggregate", "subscription", "review_themes"):
        if key in merchant:
            merchant_data[key] = _public_value(merchant[key])
    result = {"category": shared, "merchant": merchant_data,
              "trigger": _public_value(trigger), "recent_messages": [_public_text(x) for x in list(history)[-4:]]}
    if customer is not None or trigger.get("scope") == "customer":
        identity = _identity((customer or {}).get("identity"), ("name", "language_pref"))
        customer_data = {"identity": identity}
        for key in ("relationship", "state", "preferences", "consent"):
            if key in (customer or {}):
                customer_data[key] = _public_value(customer[key])
        result["customer"] = customer_data
        return result
    if any(x in kind for x in ("research", "digest", "trend", "cde", "regulation")):
        # Category facts are only passed when relevant to the selected trigger.
        for key in ("digest", "peer_stats", "trend_signals"):
            if key in category:
                shared[key] = _public_value(category[key])
    return result
