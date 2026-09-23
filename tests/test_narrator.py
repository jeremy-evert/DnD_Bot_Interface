import json
import os
import unittest
from unittest.mock import patch

from dnd_combat.narrator import (
    LocalLLMNarrator,
    PlainNarrator,
    make_narrator,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.closed = False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def close(self):
        self.closed = True


class NarratorTests(unittest.TestCase):
    def test_plain_narrator_preserves_deterministic_text(self):
        narrator = PlainNarrator()
        self.assertEqual(
            narrator.narrate("attack_hit", {"damage": 4}, "Hero hits for 4."),
            "Hero hits for 4.",
        )

    def test_local_narrator_sends_structured_facts_and_returns_model_text(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["timeout"] = timeout
            captured["url"] = request.full_url
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "The goblin learns a brief lesson about gravity."
                            }
                        }
                    ]
                }
            )

        narrator = LocalLLMNarrator(
            endpoint="http://example.test/v1/chat/completions",
            model="test-model",
            timeout=1.25,
            urlopen_fn=fake_urlopen,
        )
        text = narrator.narrate(
            "enemy_defeated",
            {"enemy": "Goblin", "room": "Mossy Entry"},
            "Goblin falls.",
        )

        self.assertEqual(
            text,
            "Goblin falls.\nDM: The goblin learns a brief lesson about gravity.",
        )
        self.assertEqual(captured["url"], "http://example.test/v1/chat/completions")
        self.assertEqual(captured["timeout"], 1.25)
        self.assertEqual(captured["payload"]["model"], "test-model")
        self.assertEqual(
            captured["payload"]["chat_template_kwargs"],
            {"enable_thinking": False},
        )
        self.assertEqual(captured["payload"]["top_p"], 0.8)
        self.assertEqual(captured["payload"]["top_k"], 20)
        event = json.loads(captured["payload"]["messages"][1]["content"])
        self.assertEqual(event["event"], "enemy_defeated")
        self.assertEqual(event["facts"]["enemy"], "Goblin")
        self.assertEqual(event["plain_text"], "Goblin falls.")

    def test_local_narrator_falls_back_on_transport_failure(self):
        def fail(*args, **kwargs):
            raise OSError("server is down")

        narrator = LocalLLMNarrator(urlopen_fn=fail)
        self.assertEqual(
            narrator.narrate("enter_room", {"room": "Mossy Entry"}, "Mossy Entry."),
            "Mossy Entry.",
        )

    def test_local_narrator_falls_back_on_malformed_response(self):
        narrator = LocalLLMNarrator(
            urlopen_fn=lambda request, timeout: FakeResponse({"choices": []})
        )
        self.assertEqual(
            narrator.narrate("attack_miss", {"roll": 2}, "Hero misses."),
            "Hero misses.",
        )

    def test_make_narrator_is_plain_by_default_and_local_when_requested(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsInstance(make_narrator(), PlainNarrator)

        with patch.dict(
            os.environ,
            {
                "DND_NARRATOR": "local",
                "DND_LLM_MODEL": "custom-qwen",
                "DND_LLM_ENDPOINT": "http://localhost:9999/v1/chat/completions",
            },
            clear=True,
        ):
            narrator = make_narrator()
            self.assertIsInstance(narrator, LocalLLMNarrator)
            self.assertEqual(narrator.model, "custom-qwen")
            self.assertEqual(
                narrator.endpoint,
                "http://localhost:9999/v1/chat/completions",
            )


if __name__ == "__main__":
    unittest.main()
