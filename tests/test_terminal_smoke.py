"""A deterministic, scripted playthrough of the terminal interface."""

import io
import unittest
from unittest.mock import patch

from dnd_combat.__main__ import main
from dnd_combat.narrator import PlainNarrator


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
            "attack", "attack",
        ]
        output = io.StringIO()
        narrator = RecordingNarrator()

        with patch("builtins.input", side_effect=commands), patch("sys.stdout", output):
            main(roller, narrator)

        self.assertIn("Victory!", output.getvalue())
        self.assertIn("enter_room", narrator.events)
        self.assertNotIn("attack_hit", narrator.events)
        self.assertIn("enemy_defeated", narrator.events)
        self.assertIn("item_found", narrator.events)
        self.assertIn("victory", narrator.events)

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


if __name__ == "__main__":
    unittest.main()
