"""A deterministic, scripted playthrough of the terminal interface."""

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dnd_combat.__main__ import main
from dnd_combat.narrator import LocalLLMNarrator, Narrator, PlainNarrator
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
    @staticmethod
    def mira_route_commands():
        return [
            "Arin", "fighter", "attack",
            "move", "east", "move", "east", "move", "north",
            "talk", "Mira", "move", "south", "move", "west", "move", "west",
            "take", "goblin's brass ring", "move", "east", "move", "east",
            "move", "north", "talk", "Mira", "move", "west", "attack", "move", "west",
        ]

    def run_mira_route(self, narrator, recorder, output):
        from dnd_combat.adventure import Adventure as RealAdventure

        games = []

        def make_game(hero):
            game = RealAdventure(hero)
            game.rooms["entry"].enemy.hp = 1
            game.rooms["sanctum"].enemy.hp = 1
            games.append(game)
            return game

        roller = lambda sides: 20
        with patch("dnd_combat.__main__.Adventure", side_effect=make_game), \
             patch("builtins.input", side_effect=self.mira_route_commands()), \
             patch("sys.stdout", output):
            main(roller, narrator, recorder)
        return games[0]

    def test_mira_memory_is_in_narration_packet_and_talk_record(self):
        class CapturingNarrator(PlainNarrator):
            def __init__(self):
                self.packets = []

            def narrate(self, event, facts, plain_text):
                if event == "npc_dialogue":
                    self.packets.append((dict(facts), plain_text))
                return plain_text

        with tempfile.TemporaryDirectory() as directory:
            recorder = SessionRecorder(Path(directory) / "mira.jsonl")
            narrator = CapturingNarrator()
            output = io.StringIO()
            game = self.run_mira_route(narrator, recorder, output)
            events = [json.loads(line) for line in recorder.path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual([facts["mira_remembered_prior_ask"] for facts, _ in narrator.packets], [False, True])
        for facts, _ in narrator.packets:
            self.assertTrue(all(
                isinstance(value, (str, bool)) or
                (isinstance(value, list) and all(isinstance(item, str) for item in value))
                for value in facts.values()
            ))
        talks = [event for event in events if event["event"] == "player_input" and event["action"] == "talk"]
        self.assertEqual([event["details"]["mira_remembered_prior_ask"] for event in talks], [False, True])
        self.assertTrue(game.vault_opened)

    def test_hostile_narrator_cannot_change_mira_route(self):
        class HostileNarrator(PlainNarrator):
            def narrate(self, event, facts, plain_text):
                if event == "npc_dialogue":
                    facts["inventory"].clear()
                    facts["mira_remembered_prior_ask"] = False
                    return "Mira refuses and the door stays sealed"
                return plain_text

        with tempfile.TemporaryDirectory() as directory:
            recorder = SessionRecorder(Path(directory) / "hostile.jsonl")
            output = io.StringIO()
            game = self.run_mira_route(HostileNarrator(), recorder, output)
            events = [json.loads(line) for line in recorder.path.read_text(encoding="utf-8").splitlines()]

        self.assertTrue(game.vault_opened)
        self.assertEqual(game.rooms["gallery"].exits["west"], "sanctum")
        self.assertIn("goblin's brass ring", game.hero.inventory)
        self.assertTrue(game.mira_memory.asked_about_ring)
        talks = [event for event in events if event["event"] == "player_input" and event["action"] == "talk"]
        narrations = [event for event in events if event["event"] == "narration" and event["category"] == "npc_dialogue"]
        self.assertEqual([event["details"]["mira_remembered_prior_ask"] for event in talks], [False, True])
        self.assertTrue(talks[1]["details"]["mira_remembered_prior_ask"])
        self.assertIn("goblin's brass ring", talks[1]["state"]["inventory"])
        self.assertEqual([event["request_facts"]["mira_remembered_prior_ask"] for event in narrations], [False, True])
        self.assertIn("goblin's brass ring", narrations[1]["request_facts"]["inventory"])
        visible = output.getvalue()
        earned_line = "You remembered what I asked"
        hostile_line = "Mira refuses and the door stays sealed"
        self.assertIn(earned_line, visible)
        self.assertLess(visible.index(earned_line), visible.rindex(hostile_line))

    def test_narrator_invalid_returns_and_exceptions_fall_back(self):
        cases = (
            ("none", lambda event, facts, plain: None),
            ("integer", lambda event, facts, plain: 42),
            ("exception", lambda event, facts, plain: (_ for _ in ()).throw(RuntimeError("boom"))),
        )
        for label, behavior in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                class BrokenNarrator(PlainNarrator):
                    def narrate(self, event, facts, plain_text):
                        if event == "npc_dialogue":
                            return behavior(event, facts, plain_text)
                        return plain_text

                recorder = SessionRecorder(Path(directory) / f"{label}.jsonl")
                output = io.StringIO()
                game = self.run_mira_route(BrokenNarrator(), recorder, output)
                events = [json.loads(line) for line in recorder.path.read_text(encoding="utf-8").splitlines()]
                talks = [event for event in events if event["event"] == "player_input" and event["action"] == "talk"]
                self.assertEqual(len(talks), 2)
                self.assertIn("You remembered what I asked", output.getvalue())
                self.assertTrue(game.vault_opened)
                self.assertEqual(game.current_room_id, "sanctum")
                self.assertEqual(game.room.name, "Hollow Vault")

    def test_string_subclass_cannot_hide_earned_dialogue(self):
        class DeceptiveString(str):
            def startswith(self, *args, **kwargs):
                return True

            def partition(self, *args, **kwargs):
                return ("", "", "")

            def __contains__(self, item):
                return True

        class DeceptiveNarrator(PlainNarrator):
            def narrate(self, event, facts, plain_text):
                if event == "npc_dialogue":
                    return DeceptiveString("Mira refuses")
                return plain_text

        with tempfile.TemporaryDirectory() as directory:
            recorder = SessionRecorder(Path(directory) / "deceptive.jsonl")
            output = io.StringIO()
            game = self.run_mira_route(DeceptiveNarrator(), recorder, output)
            events = [json.loads(line) for line in recorder.path.read_text(encoding="utf-8").splitlines()]

        self.assertTrue(game.vault_opened)
        self.assertIn("You remembered what I asked", output.getvalue())
        narrations = [event for event in events if event["event"] == "narration" and event["category"] == "npc_dialogue"]
        self.assertEqual(len(narrations), 2)
        self.assertTrue(all(event["fallback"] is False for event in narrations))

    def test_string_subclass_parse_methods_cannot_abort_route_or_record(self):
        class ExplodingString(str):
            def partition(self, *args, **kwargs):
                raise AssertionError("subclass partition must not be called")

            def __contains__(self, item):
                raise AssertionError("subclass __contains__ must not be called")

        class ExplodingNarrator(PlainNarrator):
            def narrate(self, event, facts, plain_text):
                if event == "npc_dialogue":
                    return ExplodingString("Mira's answer")
                return plain_text

        with tempfile.TemporaryDirectory() as directory:
            recorder = SessionRecorder(Path(directory) / "exploding.jsonl")
            output = io.StringIO()
            game = self.run_mira_route(ExplodingNarrator(), recorder, output)
            events = [json.loads(line) for line in recorder.path.read_text(encoding="utf-8").splitlines()]

        self.assertTrue(game.vault_opened)
        self.assertIn("You remembered what I asked", output.getvalue())
        talks = [event for event in events if event["event"] == "player_input" and event["action"] == "talk"]
        narrations = [event for event in events if event["event"] == "narration" and event["category"] == "npc_dialogue"]
        self.assertEqual(len(talks), 2)
        self.assertEqual(len(narrations), 2)

    def test_baseexception_from_narrator_propagates(self):
        class Stop(BaseException):
            pass

        class StoppingNarrator(PlainNarrator):
            def narrate(self, event, facts, plain_text):
                if event == "npc_dialogue":
                    raise Stop("stop requested")
                return plain_text

        with tempfile.TemporaryDirectory() as directory:
            recorder = SessionRecorder(Path(directory) / "stop.jsonl")
            with self.assertRaisesRegex(Stop, "stop requested"):
                self.run_mira_route(StoppingNarrator(), recorder, io.StringIO())

    def test_llm_style_fallback_still_records_request_facts(self):
        cases = (
            ("none", lambda event, facts, plain: None),
            ("exception", lambda event, facts, plain: (_ for _ in ()).throw(RuntimeError("offline"))),
        )
        for label, behavior in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                class BrokenLLMNarrator(PlainNarrator):
                    adapter = object()

                    def narrate(self, event, facts, plain_text):
                        if event == "npc_dialogue":
                            return behavior(event, facts, plain_text)
                        return plain_text

                recorder = SessionRecorder(Path(directory) / f"{label}.jsonl")
                output = io.StringIO()
                game = self.run_mira_route(BrokenLLMNarrator(), recorder, output)
                events = [json.loads(line) for line in recorder.path.read_text(encoding="utf-8").splitlines()]

            self.assertTrue(game.vault_opened)
            self.assertIn("You remembered what I asked", output.getvalue())
            narrations = [event for event in events if event["event"] == "narration" and event["category"] == "npc_dialogue"]
            self.assertEqual(len(narrations), 2)
            self.assertTrue(all(event["llm"] for event in narrations))
            self.assertTrue(all(event["fallback"] for event in narrations))
            self.assertEqual([event["request_facts"]["mira_remembered_prior_ask"] for event in narrations], [False, True])

    def test_mutate_then_raise_preserves_original_narration_facts(self):
        class MutateThenRaise(PlainNarrator):
            def narrate(self, event, facts, plain_text):
                if event == "npc_dialogue":
                    facts["mira_remembered_prior_ask"] = not facts["mira_remembered_prior_ask"]
                    facts["inventory"].clear()
                    raise RuntimeError("after mutation")
                return plain_text

        with tempfile.TemporaryDirectory() as directory:
            recorder = SessionRecorder(Path(directory) / "mutate-raise.jsonl")
            output = io.StringIO()
            self.run_mira_route(MutateThenRaise(), recorder, output)
            events = [json.loads(line) for line in recorder.path.read_text(encoding="utf-8").splitlines()]
        narrations = [event for event in events if event["event"] == "narration" and event["category"] == "npc_dialogue"]
        self.assertEqual([event["request_facts"]["mira_remembered_prior_ask"] for event in narrations], [False, True])
        self.assertIn("goblin's brass ring", narrations[1]["request_facts"]["inventory"])

    def test_valid_prefixed_narration_records_response_without_duplication(self):
        class PrefixNarrator(PlainNarrator):
            def narrate(self, event, facts, plain_text):
                if event == "npc_dialogue":
                    return f"{plain_text}\nDM: extra"
                return plain_text

        with tempfile.TemporaryDirectory() as directory:
            recorder = SessionRecorder(Path(directory) / "prefixed-record.jsonl")
            output = io.StringIO()
            self.run_mira_route(PrefixNarrator(), recorder, output)
            events = [json.loads(line) for line in recorder.path.read_text(encoding="utf-8").splitlines()]
        narrations = [event for event in events if event["event"] == "narration" and event["category"] == "npc_dialogue"]
        self.assertEqual([event["response"] for event in narrations], ["extra", "extra"])
        self.assertEqual(output.getvalue().count("DM: extra"), 2)

    def test_narrator_prefix_is_printed_without_duplicate_deterministic_response(self):
        class PrefixNarrator(PlainNarrator):
            def __init__(self):
                self.dialogue = []

            def narrate(self, event, facts, plain_text):
                if event == "npc_dialogue":
                    self.dialogue.append(plain_text)
                    return f"{plain_text}\nDM: extra"
                return plain_text

        narrator = PrefixNarrator()
        with tempfile.TemporaryDirectory() as directory:
            recorder = SessionRecorder(Path(directory) / "prefix.jsonl")
            output = io.StringIO()
            self.run_mira_route(narrator, recorder, output)

        expected = "\n".join(
            part for message in narrator.dialogue for part in (message, "DM: extra")
        )
        printed_lines = output.getvalue().splitlines()
        dialogue_lines = [
            line for line in printed_lines
            if line in narrator.dialogue or line == "DM: extra"
        ]
        self.assertEqual(dialogue_lines, expected.splitlines())
        for message in narrator.dialogue:
            self.assertEqual(dialogue_lines.count(message), 1)

    def test_failed_narrator_transport_falls_back_and_route_completes(self):
        def fail_request(*args, **kwargs):
            raise OSError("offline")

        narrator = LocalLLMNarrator(urlopen_fn=fail_request)
        with tempfile.TemporaryDirectory() as directory:
            recorder = SessionRecorder(Path(directory) / "failed.jsonl")
            output = io.StringIO()
            game = self.run_mira_route(narrator, recorder, output)

        self.assertTrue(game.vault_opened)
        self.assertIn("You remembered what I asked", output.getvalue())

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
