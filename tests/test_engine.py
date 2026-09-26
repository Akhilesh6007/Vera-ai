"""Intent, policy, hidden-context and deterministic replay coverage."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
import app as service
from context_builder import select_context
from conversation_engine import transition
from conversation_store import ConversationStore
from context_store import ContextStore
from intent import detect_intent, is_automated
from router import route_trigger
from validator import validate, validate_grounding


class IntentAndStateMachineTests(unittest.TestCase):
    def test_intent_priority_and_commitment_variants(self):
        cases = {
            "Not interested. Stop messaging me.": "stop",
            "Mujhe magicpin join karna hai": "join",
            "Ok lets do it. Whats next?": "go_ahead",
            "Yes please send me the details": "go_ahead",
            "Btw can you help with GST filing?": "off_topic",
            "Could you explain the fee?": "question",
            "Thank you for contacting us; our team will respond shortly": "auto_reply",
        }
        for message, expected in cases.items():
            with self.subTest(message=message):
                self.assertEqual(detect_intent(message), expected)

    def test_auto_reply_detector_uses_canned_phrases_and_repetition(self):
        canned = "Thank you for contacting us. Our team will get back to you."
        self.assertTrue(is_automated(canned))
        repeated = "This branch is currently away and will respond during business hours."
        self.assertFalse(is_automated(repeated, [repeated]))
        self.assertTrue(is_automated(repeated, [repeated, repeated]))
        self.assertFalse(is_automated("Thanks", ["Thanks", "Thanks"]))

    def test_state_machine_auto_reply_replay_and_terminal_state(self):
        canned = "Thank you for contacting us! Our team will respond shortly."
        first = transition(message=canned, turn_number=2, auto_reply_count=0)
        self.assertEqual((first["action"], first["wait_seconds"]), ("wait", 14_400))
        second = transition(message=canned, turn_number=3, auto_reply_count=1)
        self.assertEqual(second["action"], "end")
        self.assertEqual(transition(message="Hi", turn_number=4, status="ended")["action"], "end")

    def test_state_machine_routes_commitment_without_qualifying(self):
        result = transition(message="Ok, let's do it. What's next?", turn_number=3)
        self.assertEqual(result["action"], "send")
        self.assertIn("onboarding", result["body"].lower())
        self.assertNotRegex(result["body"].lower(), r"\b(would you|can you tell me|what is your budget)\b")
        self.assertEqual(transition(message="This is useless. Stop messaging me", turn_number=2)["action"], "end")


class StrategyAndValidatorTests(unittest.TestCase):
    def test_strategy_router_families_and_unknown_fallback(self):
        cases = {
            "research_digest": "knowledge-curiosity",
            "seasonal_perf_dip": "loss-aversion-action",
            "perf_spike": "celebration-growth",
            "active_planning_intent": "action-draft",
            "appointment_tomorrow": "appointment-reminder",
            "recall_due": "customer-convenience",
            "competitor_opened": "factual-curiosity",
            "regulation_change": "compliance-information",
            "category_seasonal": "seasonal-opportunity",
            "unrecognized_signal": "contextual-specificity",
        }
        for kind, expected in cases.items():
            with self.subTest(kind=kind):
                self.assertEqual(route_trigger({"kind": kind}), expected)
        self.assertEqual(route_trigger({"scope": "customer"}), "customer-convenience")
        self.assertEqual(route_trigger(None), "contextual-specificity")

    def test_validator_rejects_missing_fields_hallucinations_and_taboo(self):
        base = {"body": "Our offer is ready.", "cta": "open_ended", "send_as": "vera",
                "suppression_key": "trigger:merchant", "rationale": "Uses provided context."}
        self.assertEqual(validate({"body": ""}), ["missing required output keys: cta, rationale, send_as, suppression_key"])
        unsupported = {**base, "body": "We found 9876 missed visits. Visit https://unknown.example"}
        errors = validate_grounding(unsupported, {"merchant": {"performance": {"visits": 21}}})
        self.assertTrue(any("9876" in error for error in errors))
        self.assertIn("unsupported URL", errors)
        taboo = {**base, "body": "We guarantee this will work."}
        errors = validate_grounding(taboo, {"category": {"voice": {"taboos": ["guarantee"]}}})
        self.assertIn("category taboo: guarantee", errors)
        wrong_route = {**base, "send_as": "vera"}
        self.assertIn("sender mismatch", validate(wrong_route, customer={}))


class HiddenContextTests(unittest.TestCase):
    def test_prompt_context_allowlists_identity_and_strips_private_fields(self):
        selected = select_context(
            {"slug": "dentists", "voice": {"tone": "calm"}, "internal_note": "HIDDEN-CAT"},
            {"identity": {"name": "Clinic", "owner_first_name": "Meera", "phone_redacted": "HIDDEN-PHONE",
                           "private_note": "HIDDEN-MERCHANT"}, "performance": {"ctr": 0.03}},
            {"kind": "research_digest", "payload": {"headline": "Public finding", "internal_secret": "HIDDEN-TRIGGER"}},
            {"identity": {"name": "Priya", "phone": "HIDDEN-CUSTOMER-PHONE", "age_band": "HIDDEN-AGE"},
             "preferences": {"channel": "whatsapp"}, "consent": {"scope": ["recall_reminders"]}},
        )
        serialized = repr(selected)
        for hidden in ("HIDDEN-CAT", "HIDDEN-PHONE", "HIDDEN-MERCHANT", "HIDDEN-TRIGGER",
                       "HIDDEN-CUSTOMER-PHONE", "HIDDEN-AGE"):
            self.assertNotIn(hidden, serialized)
        message_context = select_context({}, {}, {"scope": "merchant"}, history=["Call me at 555-010-2044 or email owner@example.test"])
        self.assertNotIn("555-010-2044", repr(message_context))
        self.assertNotIn("owner@example.test", repr(message_context))
        self.assertEqual(selected["merchant"]["identity"]["name"], "Clinic")
        self.assertEqual(selected["customer"]["identity"]["name"], "Priya")

    def test_injected_context_version_changes_composition_and_stale_facts_do_not_leak(self):
        isolated_contexts = ContextStore()
        client = TestClient(service.app)
        with patch.object(service, "contexts", isolated_contexts), patch.object(service, "conversations", ConversationStore()):
            merchant_id = "m_hidden_context_test"
            trigger_id = "t_hidden_context_test"
            category = {"slug": "dentists", "voice": {"tone": "calm", "taboos": []}}
            merchant = {"merchant_id": merchant_id, "category_slug": "dentists",
                        "identity": {"name": "Context Test Clinic", "owner_first_name": "Mira", "locality": "North Park"}}
            trigger = {"id": trigger_id, "scope": "merchant", "kind": "research_digest", "merchant_id": merchant_id,
                       "payload": {"headline": "Context Alpha"}}
            for scope, context_id, payload in (("category", "dentists", category),
                                                ("merchant", merchant_id, merchant),
                                                ("trigger", trigger_id, trigger)):
                self.assertEqual(client.post("/v1/context", json={"scope": scope, "context_id": context_id,
                                    "version": 1, "payload": payload}).status_code, 200)
            first = client.post("/v1/compose", json={"merchant_id": merchant_id, "trigger_id": trigger_id}).json()
            self.assertTrue(first["validation"]["valid"])
            self.assertIn("Context Alpha", first["message"]["body"])
            trigger["payload"]["headline"] = "Context Beta"
            self.assertEqual(client.post("/v1/context", json={"scope": "trigger", "context_id": trigger_id,
                                "version": 2, "payload": trigger}).status_code, 200)
            second = client.post("/v1/compose", json={"merchant_id": merchant_id, "trigger_id": trigger_id}).json()
            self.assertTrue(second["validation"]["valid"])
            self.assertIn("Context Beta", second["message"]["body"])
            self.assertNotIn("Context Alpha", second["message"]["body"])

    def test_customer_trigger_requires_matching_merchant_and_explicit_scope_consent(self):
        isolated_contexts = ContextStore()
        client = TestClient(service.app)
        with patch.object(service, "contexts", isolated_contexts), patch.object(service, "conversations", ConversationStore()):
            merchant_id = "m_consent_test"
            customer_id = "c_consent_test"
            trigger_id = "t_consent_test"
            category = {"slug": "dentists", "voice": {"tone": "calm", "taboos": []}}
            merchant = {"merchant_id": merchant_id, "category_slug": "dentists", "identity": {"name": "Consent Clinic"}}
            customer = {"customer_id": customer_id, "merchant_id": merchant_id, "identity": {"name": "Asha"}, "state": "active"}
            trigger = {"id": trigger_id, "scope": "customer", "kind": "recall_due", "merchant_id": merchant_id,
                       "customer_id": customer_id, "payload": {"service_due": "cleaning"}}
            records = (("category", "dentists", category), ("merchant", merchant_id, merchant),
                       ("customer", customer_id, customer), ("trigger", trigger_id, trigger))
            for scope, context_id, payload in records:
                self.assertEqual(client.post("/v1/context", json={"scope": scope, "context_id": context_id,
                                    "version": 1, "payload": payload}).status_code, 200)
            request = {"now": "2026-04-26T10:35:00Z", "available_triggers": [trigger_id]}
            self.assertEqual(client.post("/v1/tick", json=request).json()["actions"], [])
            customer["consent"] = {"scope": ["recall_reminders"]}
            self.assertEqual(client.post("/v1/context", json={"scope": "customer", "context_id": customer_id,
                                "version": 2, "payload": customer}).status_code, 200)
            actions = client.post("/v1/tick", json=request).json()["actions"]
            self.assertEqual(len(actions), 1)
            self.assertEqual(actions[0]["send_as"], "merchant_on_behalf")


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.store = ConversationStore()
        self.patcher = patch.object(service, "conversations", self.store)
        self.patcher.start()
        self.client = TestClient(service.app)

    def tearDown(self):
        self.patcher.stop()

    def test_replay_auto_reply_hell_waits_then_exits_idempotently(self):
        body = {"conversation_id": "replay-auto-hell", "merchant_id": "m_replay_auto",
                "message": "Thank you for contacting us. Our team will respond shortly."}
        first = self.client.post("/v1/reply", json={**body, "turn_number": 2}).json()
        self.assertEqual((first["action"], first["wait_seconds"]), ("wait", 14_400))
        second = self.client.post("/v1/reply", json={**body, "turn_number": 3}).json()
        self.assertEqual(second["action"], "end")
        after_end = self.client.post("/v1/reply", json={**body, "turn_number": 4}).json()
        self.assertEqual(after_end["action"], "end")
        self.assertEqual(len(self.store.get(body["conversation_id"])["messages"]), 2)

    def test_replay_intent_transition_and_duplicate_turn(self):
        body = {"conversation_id": "replay-intent", "merchant_id": "m_replay_intent",
                "message": "Ok lets do it. Whats next?", "turn_number": 3}
        response = self.client.post("/v1/reply", json=body).json()
        retry = self.client.post("/v1/reply", json=body).json()
        self.assertEqual(response["action"], "send")
        self.assertIn("onboarding", response["body"].lower())
        self.assertEqual(response, retry)
        changed_replay = self.client.post("/v1/reply", json={**body, "message": "Actually, never mind."})
        self.assertEqual(changed_replay.status_code, 409)
        self.assertEqual(len(self.store.get(body["conversation_id"])["messages"]), 2)

    def test_replay_stop_is_terminal_and_suppresses_later_trigger(self):
        body = {"conversation_id": "replay-stop", "merchant_id": "m_replay_stop",
                "message": "Why are you bothering me? This is useless. Stop sending these.", "turn_number": 2}
        response = self.client.post("/v1/reply", json=body).json()
        self.assertEqual(response["action"], "end")
        self.assertTrue(self.store.is_opted_out("m_replay_stop"))
        self.assertEqual(self.client.post("/v1/reply", json={**body, "turn_number": 3}).json()["action"], "end")

    def test_replay_wait_expires_then_allows_one_nonduplicate_followup(self):
        contexts = ContextStore()
        with patch.object(service, "contexts", contexts):
            merchant_id, trigger_id = "m_wait_resume", "t_wait_resume"
            merchant = {"merchant_id": merchant_id, "category_slug": "dentists",
                        "identity": {"name": "Wait Resume Clinic", "owner_first_name": "Nia", "locality": "Central"}}
            category = {"slug": "dentists", "voice": {"tone": "calm", "taboos": []}}
            trigger = {"id": trigger_id, "scope": "merchant", "kind": "research_digest", "merchant_id": merchant_id,
                       "payload": {"headline": "A verified research update"}}
            for scope, context_id, payload in (("category", "dentists", category),
                                                ("merchant", merchant_id, merchant),
                                                ("trigger", trigger_id, trigger)):
                contexts.put(scope, context_id, 1, payload)
            tick = {"available_triggers": [trigger_id]}
            first = self.client.post("/v1/tick", json={**tick, "now": "2026-04-26T10:00:00Z"}).json()["actions"]
            self.assertEqual(len(first), 1)
            reply = self.client.post("/v1/reply", json={"conversation_id": first[0]["conversation_id"],
                "merchant_id": merchant_id, "message": "Thank you for contacting us; our team will respond shortly.",
                "turn_number": 2, "received_at": "2026-04-26T10:00:00Z"}).json()
            self.assertEqual(reply["action"], "wait")
            early = self.client.post("/v1/tick", json={**tick, "now": "2026-04-26T13:59:59Z"}).json()["actions"]
            self.assertEqual(early, [])
            resumed = self.client.post("/v1/tick", json={**tick, "now": "2026-04-26T14:00:00Z"}).json()["actions"]
            self.assertEqual(len(resumed), 1)
            self.assertNotEqual(resumed[0]["body"], first[0]["body"])
            self.assertEqual(self.client.post("/v1/tick", json={**tick, "now": "2026-04-26T14:05:00Z"}).json()["actions"], [])

    def test_replay_off_topic_stays_on_mission_and_turn_cap_ends(self):
        off_topic = self.client.post("/v1/reply", json={"conversation_id": "replay-gst", "merchant_id": "m_replay_gst",
            "message": "Can you help file my GST return?", "turn_number": 2}).json()
        self.assertEqual(off_topic["action"], "send")
        self.assertIn("Vera update", off_topic["body"])
        capped = self.client.post("/v1/reply", json={"conversation_id": "replay-cap", "merchant_id": "m_replay_cap",
            "message": "A normal response", "turn_number": 5}).json()
        self.assertEqual(capped["action"], "end")


if __name__ == "__main__":
    unittest.main()
