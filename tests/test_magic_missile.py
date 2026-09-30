import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from dnd_combat.__main__ import run_combat
from dnd_combat.adventure import Adventure, make_character
from dnd_combat.commands import resolve_combat_command
from dnd_combat.narrator import Narrator
from dnd_combat.session_log import RecordingNarrator, SessionRecorder
from dnd_combat.terminal import emit


class FixedRoller:
    def __init__(self, *rolls):
        self.rolls = iter(rolls)
        self.requested_sides = []

    def __call__(self, sides):
        self.requested_sides.append(sides)
        return next(self.rolls)


class MagicMissileTests(unittest.TestCase):
    def wizard_in_combat(self):
        game = Adventure(make_character("wizard", "Cy"))
        game.start_encounter(FixedRoller(20, 1))  # hero acts first
        return game

    def test_only_wizard_has_charges(self):
        self.assertEqual(make_character("wizard", "Cy").spell_charges, 3)
        self.assertEqual(make_character("fighter", "Arin").max_spell_charges, 0)

    def test_magic_missile_always_hits_for_two_d4(self):
        for rolls, expected_damage in (((1, 1), 2), ((4, 4), 8)):
            with self.subTest(rolls=rolls):
                game = self.wizard_in_combat()
                hp = game.enemy.hp
                roller = FixedRoller(*rolls)

                result = game.player_cast_magic_missile(roller)

                self.assertTrue(result.hit)
                self.assertEqual(result.damage, expected_damage)
                self.assertEqual(game.enemy.hp, hp - expected_damage)
                self.assertEqual(game.hero.spell_charges, 2)
                self.assertEqual(game.combat_turn, "enemy")
                self.assertEqual(roller.requested_sides, [4, 4])

    def test_non_wizard_cannot_cast_with_forged_charge(self):
        game = Adventure(make_character("fighter", "Arin"))
        game.start_encounter(FixedRoller(20, 1))
        game.hero.spell_charges = 1
        hp = game.enemy.hp
        roller = FixedRoller(4, 4)

        with self.assertRaises(ValueError):
            game.player_cast_magic_missile(roller)

        self.assertEqual(game.enemy.hp, hp)
        self.assertEqual(game.hero.spell_charges, 1)
        self.assertEqual(game.combat_turn, "hero")
        self.assertEqual(roller.requested_sides, [])

    def test_out_of_charges_does_not_consume_turn(self):
        game = self.wizard_in_combat()
        game.hero.spell_charges = 0
        hp = game.enemy.hp

        self.assertIsNone(game.player_cast_magic_missile(FixedRoller(4, 4)))
        self.assertEqual(game.enemy.hp, hp)
        self.assertEqual(game.combat_turn, "hero")

    def test_charges_refresh_at_next_encounter(self):
        game = Adventure(make_character("wizard", "Cy"))
        game.hero.spell_charges = 0
        game.start_encounter(FixedRoller(20, 1))
        self.assertEqual(game.hero.spell_charges, 3)

    def test_cast_command_aliases(self):
        for raw in ("c", "cast", "magic missile", "missile"):
            self.assertEqual(resolve_combat_command(raw), "cast")

    def test_cannot_cast_on_enemy_turn(self):
        game = Adventure(make_character("wizard", "Cy"))
        game.start_encounter(FixedRoller(1, 20))
        with self.assertRaises(ValueError):
            game.player_cast_magic_missile(FixedRoller(1, 1))

    def test_spell_kill_emits_and_records_dropped_item(self):
        game = Adventure(make_character("wizard", "Cy"))
        game.enemy.hp = 1
        roller = FixedRoller(20, 1, 4, 4)
        output = io.StringIO()

        with tempfile.TemporaryDirectory() as directory:
            recorder = SessionRecorder(Path(directory) / "spell-kill.jsonl")
            narrator = RecordingNarrator(NarratorForText(), recorder)
            with patch("builtins.input", return_value="cast"), redirect_stdout(output):
                run_combat(game, roller, narrator, recorder)
            events = [
                json.loads(line)
                for line in recorder.path.read_text(encoding="utf-8").splitlines()
            ]

        narration_categories = [
            event["category"] for event in events if event["event"] == "narration"
        ]
        self.assertEqual(narration_categories[-2:], ["enemy_defeated", "item_found"])
        self.assertIn("goblin's brass ring", output.getvalue())


class NarratorForText(Narrator):
    def narrate(self, event, facts, plain_text):
        return plain_text


class SlowNarrator(Narrator):
    def narrate(self, event, facts, plain_text):
        print("[model call]")
        return f"{plain_text}\nDM: flavor"


class InstantTextTests(unittest.TestCase):
    def test_plain_text_prints_before_the_narrator_is_called(self):
        out = io.StringIO()
        with redirect_stdout(out):
            emit(SlowNarrator(), "enter_room", {}, "Room: plain")
        self.assertEqual(out.getvalue(), "Room: plain\n[model call]\nDM: flavor\n")

    def test_plain_narrator_output_is_not_duplicated(self):
        class Plain(Narrator):
            def narrate(self, event, facts, plain_text):
                return plain_text

        out = io.StringIO()
        with redirect_stdout(out):
            emit(Plain(), "e", {}, "once")
        self.assertEqual(out.getvalue(), "once\n")

    def test_recording_and_emit_share_narration_contract(self):
        cases = (
            ("unchanged", "PLAIN", "PLAIN\n", None, True),
            ("combined", "PLAIN\nDM: extra", "PLAIN\nDM: extra\n", "extra", False),
            ("addition-only", "DM: extra", "PLAIN\nDM: extra\n", "extra", False),
        )
        for label, rendered, expected_output, expected_response, expected_fallback in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                class FixedNarrator(Narrator):
                    adapter = object()
                    model = "test-model"

                    def narrate(self, event, facts, plain_text):
                        return rendered

                recorder = SessionRecorder(Path(directory) / f"{label}.jsonl")
                output = io.StringIO()
                with redirect_stdout(output):
                    emit(RecordingNarrator(FixedNarrator(), recorder), "event", {}, "PLAIN")
                event = json.loads(recorder.path.read_text(encoding="utf-8"))

            self.assertEqual(output.getvalue(), expected_output)
            self.assertEqual(event["response"], expected_response)
            self.assertEqual(event["fallback"], expected_fallback)


if __name__ == "__main__":
    unittest.main()
