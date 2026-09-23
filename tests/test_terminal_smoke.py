"""A deterministic, scripted playthrough of the terminal interface."""

import io
import unittest
from unittest.mock import patch

from dnd_combat.__main__ import main


class FixedRoller:
    def __init__(self, *rolls):
        self.rolls = iter(rolls)

    def __call__(self, sides):
        return next(self.rolls)


class TerminalSmokeTests(unittest.TestCase):
    def test_full_adventure_reaches_victory(self):
        # Goblin initiative/attack, captain initiative, two hero attacks, and
        # the captain's intervening miss.
        roller = FixedRoller(20, 1, 20, 10, 20, 1, 20, 10, 1, 20, 10)
        commands = [
            "Arin", "fighter", "attack",  # defeat goblin
            "move", "e", "take", "healing potion", "move", "east",
            "attack", "attack",  # defeat captain
        ]
        output = io.StringIO()

        with patch("builtins.input", side_effect=commands), patch("sys.stdout", output):
            main(roller)

        self.assertIn("Victory!", output.getvalue())


if __name__ == "__main__":
    unittest.main()
