"""Pure conversation policy/state machine used by the HTTP adapter and replays."""
from __future__ import annotations

from intent import detect_intent, is_automated

MAX_TURNS = 5
AUTO_REPLY_WAIT_SECONDS = 14_400


def transition(*, message: str, turn_number: int, status: str = "open",
               prior_messages=(), auto_reply_count: int = 0,
               language: str = "en") -> dict:
    """Return a deterministic next action without mutating the supplied state."""
    if status in ("ended", "closed"):
        return {"action": "end", "intent": "closed", "status": status,
                "rationale": "Conversation is already closed; no further message was sent."}

    intent = detect_intent(message)
    history = list(prior_messages or ())
    automated = intent == "auto_reply" or is_automated(message, history)

    if intent == "stop":
        return {"action": "end", "intent": intent, "status": "ended",
                "rationale": "Recipient opted out; conversation ended and future outreach is suppressed."}
    if automated:
        if auto_reply_count >= 1 or turn_number >= MAX_TURNS:
            return {"action": "end", "intent": "auto_reply", "status": "ended",
                    "auto_reply_detected": True,
                    "rationale": "Repeated canned reply detected; closing without another pitch."}
        return {"action": "wait", "intent": "auto_reply", "status": "waiting",
                "wait_seconds": AUTO_REPLY_WAIT_SECONDS, "auto_reply_detected": True,
                "rationale": "Likely automated business reply; pausing four hours for a human response."}
    if turn_number >= MAX_TURNS:
        return {"action": "end", "intent": intent, "status": "ended",
                "rationale": "Conversation reached the five-turn limit; ending without another message."}
    if intent == "complaint":
        return {"action": "end", "intent": intent, "status": "ended",
                "rationale": "Complaint or frustration detected; promotional follow-up stopped."}

    if intent in ("join", "go_ahead", "yes"):
        body = "Great, I’ll move this to the magicpin onboarding step. The team can review the business details and confirm the next setup requirements."
        intent = "join" if intent == "join" else "go_ahead"
    elif intent == "off_topic":
        body = "I can’t help with that request, but I can keep helping with the Vera update we were discussing."
    elif intent == "update_profile":
        body = "I can help prepare the profile update. I’ll use the business details already on file and flag anything that needs your confirmation."
    elif intent == "question":
        body = "I can clarify using the business details available here. Which part would you like me to explain?"
    elif intent == "confused":
        body = "Sorry that wasn’t clear. I can explain the specific detail from my last note in simpler terms."
    else:
        body = "Thanks for letting me know. I’ll keep this focused on the update I sent and use only details available in your profile."
    if language == "hi-en":
        body = "Samajh gayi. " + body
    return {"action": "send", "body": body, "cta": "open_ended", "intent": intent,
            "status": "open", "rationale": f"Detected {intent} intent and routed it without repeating the prior message."}
