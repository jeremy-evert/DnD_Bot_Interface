import unittest

from dnd_combat.adventure import Adventure, make_character
from dnd_combat.commands import resolve_combat_command, resolve_exploration_command
from dnd_combat.matching import DeterministicMatcher, MatchCandidate


class MatchingTests(unittest.TestCase):
    def test_unique_word_matching_accepts_playtest_object_shorthand(self):
        game = Adventure(make_character("fighter", "Arin"))
        game.rooms["entry"].enemy.hp = 0
        game.move("east")

        self.assertEqual(game.take_item("potion"), (True, "You take the healing potion."))

        second_game = Adventure(make_character("fighter", "Bea"))
        second_game.rooms["entry"].enemy.hp = 0
        second_game.move("east")
        self.assertEqual(second_game.take_item("healing"), (True, "You take the healing potion."))

    def test_visible_non_takeable_object_is_addressable(self):
        game = Adventure(make_character("fighter", "Arin"))
        game.rooms["entry"].enemy.hp = 0
        game.move("east")

        self.assertIn("broken crates", game.look())
        self.assertEqual(game.take_item("crates"), (False, "The broken crates cannot be taken."))

    def test_ambiguous_partial_match_is_rejected(self):
        matcher = DeterministicMatcher((
            MatchCandidate("red", "red potion"),
            MatchCandidate("blue", "blue potion"),
        ))

        self.assertIsNone(matcher.match("potion"))
        self.assertEqual(matcher.match("red"), "red")

    def test_command_boundary_uses_the_same_deterministic_matching(self):
        self.assertEqual(resolve_exploration_command("M"), "move")
        self.assertEqual(resolve_combat_command("use potion"), "use")
        self.assertIsNone(resolve_exploration_command("dance"))
