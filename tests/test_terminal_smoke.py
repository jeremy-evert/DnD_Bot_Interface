"""A deterministic, scripted playthrough of the terminal interface."""

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dnd_combat.__main__ import main
from dnd_combat.narrator import Narrator, PlainNarrator
from dnd_combat.session_log import RecordingNarrator as SessionNarrator, SessionRecorder


class FixedRoller:
    def __init__(self, *rolls):
        self.rolls = iter(rolls)

    def __call__(self, sides):
        return next(self.rolls)


class RecordingNarrator(PlainNarrator):
    def __init__(self):
        self.events = []

    def narrate(self, event, facts, plain_text):
        self.events.append(event)
        return super().narrate(event, facts, plain_text)


class SuggestingNarrator(RecordingNarrator):
    def __init__(self):
        super().__init__()
        self.suggestion_calls = 0

    def suggest_room_objects(self, facts):
        self.suggestion_calls += 1
        return [{"name": "cracked lantern", "description": "A soot-darkened lantern."}]


class TerminalSmokeTests(unittest.TestCase):
    def test_full_adventure_reaches_victory_and_emits_narration_events(self):
        roller = FixedRoller(20, 1, 20, 10, 20, 1, 20, 10, 1, 20, 10)
        commands = [
            "Arin", "fighter", "attack",
            "move", "e", "take", "healing potion", "move", "east",
            "move", "north", "move", "east", "move", "east",
            "attack", "attack",
        ]
        output = io.StringIO()
        narrator = RecordingNarrator()
        with tempfile.TemporaryDirectory() as directory:
            recorder = SessionRecorder(Path(directory) / "smoke.jsonl")

            with patch("builtins.input", side_effect=commands), patch("sys.stdout", output):
                main(roller, narrator, recorder)

            report = SessionRecorder.report(recorder.path)
            raw_log = recorder.path.read_text(encoding="utf-8")

        self.assertIn("Victory!", output.getvalue())
        self.assertIn("enter_room", narrator.events)
        self.assertNotIn("attack_hit", narrator.events)
        self.assertIn("enemy_defeated", narrator.events)
        self.assertIn("item_found", narrator.events)
        self.assertIn("victory", narrator.events)
        self.assertIn("Route:", report)
        self.assertIn("Hollow Vault", report)
        self.assertIn('"d20": 20', raw_log)
        self.assertIn('"event": "session_ended"', raw_log)

    def test_room_suggestions_are_requested_once_per_room_and_visible_after_return(self):
        from dnd_combat.adventure import Adventure, make_character
        from dnd_combat.__main__ import announce_room

        game = Adventure(make_character("fighter", "Arin"))
        game.rooms["entry"].enemy.hp = 0
        narrator = SuggestingNarrator()
        output = io.StringIO()

        with patch("sys.stdout", output):
            announce_room(game, narrator)
            game.move("east")
            announce_room(game, narrator)
            game.move("west")
            announce_room(game, narrator)

        self.assertEqual(narrator.suggestion_calls, 2)
        self.assertEqual(len([thing for thing in game.rooms["entry"].objects if thing.name == "cracked lantern"]), 1)
        self.assertIn("cracked lantern", output.getvalue())

    def test_unknown_terminal_attempt_is_recorded_in_report(self):
        from dnd_combat.adventure import Adventure, make_character

        game = Adventure(make_character("fighter", "Arin"))
        with tempfile.TemporaryDirectory() as directory:
            recorder = SessionRecorder(Path(directory) / "attempt.jsonl")
            recorder.input("cast portal", game, outcome="unrecognized command")

            report = SessionRecorder.report(recorder.path)

        self.assertIn("cast portal", report)
        self.assertIn("unrecognized", report)

    def test_recorder_captures_narrator_response_and_validates_object_proposals(self):
        from dnd_combat.adventure import Adventure, make_character
        from dnd_combat.__main__ import announce_room

        class FakeLocalNarrator(Narrator):
            adapter = object()
            model = "test-model"

            def narrate(self, event, facts, plain_text):
                return f"{plain_text}\nDM: The damp air smells of iron."

            def suggest_room_objects(self, facts):
                return [
                    {"name": "iron nail", "description": "A bent nail rests in the dust."},
                    {"name": "magic key", "description": "A key opens a secret door."},
                ]

        game = Adventure(make_character("fighter", "Arin"))
        with tempfile.TemporaryDirectory() as directory:
            recorder = SessionRecorder(Path(directory) / "llm.jsonl")
            narrator = SessionNarrator(FakeLocalNarrator(), recorder)
            with patch("sys.stdout", io.StringIO()):
                announce_room(game, narrator, recorder)
            report_events = [
                json.loads(line)
                for line in recorder.path.read_text(encoding="utf-8").splitlines()
            ]

        narration = next(event for event in report_events if event["event"] == "narration")
        suggestion = next(event for event in report_events if event["event"] == "room_suggestion")
        self.assertEqual(narration["category"], "enter_room")
        self.assertEqual(narration["model"], "test-model")
        self.assertIn("smells of iron", narration["response"])
        self.assertEqual(suggestion["accepted"], ["iron nail"])
        self.assertEqual(suggestion["rejected_count"], 1)

    def test_recorder_marks_unavailable_local_narration_as_fallback(self):
        from dnd_combat.session_log import RecordingNarrator as SessionNarrator

        class FailedLocalNarrator(Narrator):
            adapter = object()

            def narrate(self, event, facts, plain_text):
                return plain_text

        with tempfile.TemporaryDirectory() as directory:
            recorder = SessionRecorder(Path(directory) / "fallback.jsonl")
            narrator = SessionNarrator(FailedLocalNarrator(), recorder)
            narrator.narrate("enter_room", {}, "A quiet room.")
            event = json.loads(recorder.path.read_text(encoding="utf-8"))

        self.assertTrue(event["llm"])
        self.assertTrue(event["fallback"])
        self.assertGreaterEqual(event["latency_ms"], 0)


if __name__ == "__main__":
    unittest.main()
