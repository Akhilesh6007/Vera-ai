"""Conservative message intent and WhatsApp auto-reply detection."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


def normalize_message(message: str | None) -> str:
    """Normalize punctuation/spacing without discarding meaningful words."""
    value = unicodedata.normalize("NFKC", str(message or "")).lower()
    value = value.replace("’", "'").replace("‘", "'").replace("`", "'")
    value = re.sub(r"[^\w\s']", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


STOP_PATTERNS = (
    r"\bstop\b", r"\bunsubscribe\b", r"\bremove me\b",
    r"\bdon't contact(?: me)?\b", r"\bdo not contact(?: me)?\b",
    r"\bnot interested\b", r"\bno thanks\b", r"\bplease don't message\b",
    r"\bthis is useless spam\b", r"\bnahi chahiye\b", r"\babhi nahi\b",
    r"\bmessage mat(?: karo| kijiye)\b",
)

AUTO_PHRASES = (
    "thank you for contacting", "thanks for contacting", "thank you for your message",
    "thank you for reaching out", "we will get back", "we'll get back",
    "our team will respond", "team will contact", "we will contact you",
    "automated assistant", "automatic reply", "auto-reply", "office hours",
    "your call is important", "we have received your message",
    "hamari team tak", "jald hi sampark", "jaankari ke liye bahut-bahut shukriya",
)

_JOIN_PATTERNS = (
    r"\bwant to join\b", r"\bi want to (?:sign up|register|join)\b",
    r"\bmujhe (?:magicpin )?(?:join|jud|register|signup)",
    r"\bjoin magicpin\b", r"\bsign me up\b", r"\bregister me\b",
)
_GO_AHEAD_PATTERNS = (
    r"\blet'?s do it\b", r"\bgo ahead\b", r"\bproceed\b", r"\bmove forward\b",
    r"\bok(?:ay)? (?:please )?(?:do it|let'?s|proceed)\b", r"\bwhat'?s next\b",
    r"\bdo it\b", r"\bupdate my profile\b", r"\bplease update\b",
    r"\byes[, ]+(?:please[, ]+)?(?:do|send|share|start|go|update|proceed)\b",
    r"\bhaan[, ]+(?:shuru|kar|bhej|send)\b",
)
_AUTO_RE = tuple(re.compile(re.escape(p)) for p in AUTO_PHRASES)


def detect_intent(message: str | None) -> str:
    text = normalize_message(message)
    if not text:
        return "other"
    if any(re.search(pattern, text) for pattern in STOP_PATTERNS):
        return "stop"
    if any(pattern.search(text) for pattern in _AUTO_RE):
        return "auto_reply"
    if any(re.search(pattern, text) for pattern in _JOIN_PATTERNS):
        return "join"
    if any(re.search(pattern, text) for pattern in _GO_AHEAD_PATTERNS):
        return "go_ahead"
    if re.search(r"\b(update|change|edit) my (?:google )?profile\b", text):
        return "update_profile"
    if any(x in text for x in ("gst", "file my taxes", "weather", "unrelated", "can you also help")):
        return "off_topic"
    if any(x in text for x in ("confused", "samajh nahi", "what do you mean", "not clear")):
        return "confused"
    if any(x in text for x in ("bad service", "complaint", "terrible", "fraud", "bothering me", "useless")):
        return "complaint"
    if "?" in str(message or "") or re.search(r"\b(how much|what would|when can|which one|kaise|what is|how do)\b", text):
        return "question"
    if re.search(r"\b(yes|yeah|yep|haan|sure|ok|okay|accepted)\b", text):
        return "yes"
    return "other"


def is_automated(message: str | None, history=()) -> bool:
    """Detect known canned replies or a repeated non-trivial identical reply.

    A single recognizable template is enough to back off. Repetition matching
    catches templates that do not contain the common canned phrases; requiring
    three occurrences avoids treating a normal repeated short answer as a bot.
    """
    text = normalize_message(message)
    if not text:
        return False
    if any(pattern.search(text) for pattern in _AUTO_RE):
        return True
    if len(text) < 18:
        return False
    normalized_history = [normalize_message(item) for item in history]
    exact = sum(item == text for item in normalized_history)
    if exact >= 2:
        return True
    similar = sum(bool(item) and SequenceMatcher(None, text, item).ratio() >= 0.96 for item in normalized_history)
    return similar >= 2
