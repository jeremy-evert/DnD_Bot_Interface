import io
import unittest
from contextlib import redirect_stdout

from dnd_combat.adventure import Adventure, make_character
from dnd_combat.commands import resolve_combat_command
from dnd_combat.narrator import Narrator
from dnd_combat.terminal import emit


class FixedRoller:
    def __init__(self, *rolls):
        self.rolls = iter(rolls)

    def __call__(self, sides):
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
        game = self.wizard_in_combat()
        hp = game.enemy.hp

        result = game.player_cast_magic_missile(FixedRoller(3, 4))

        self.assertTrue(result.hit)
        self.assertEqual(result.damage, 7)
        self.assertEqual(game.enemy.hp, hp - 7)
        self.assertEqual(game.hero.spell_charges, 2)
        self.assertEqual(game.combat_turn, "enemy")

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


if __name__ == "__main__":
    unittest.main()
