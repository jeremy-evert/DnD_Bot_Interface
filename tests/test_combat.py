import unittest

from dnd_combat.combat import Creature, attack, roll_initiative


class FixedRoller:
    def __init__(self, *rolls):
        self.rolls = iter(rolls)

    def __call__(self, sides):
        return next(self.rolls)


class CombatTests(unittest.TestCase):
    def setUp(self):
        self.hero = Creature("Hero", 20, 14, 4, 8, 2, 2)
        self.goblin = Creature("Goblin", 12, 13, 4, 6, 2, 2)

    def test_hit_applies_damage(self):
        result = attack(self.hero, self.goblin, FixedRoller(10, 5))
        self.assertTrue(result.hit)
        self.assertEqual(result.total, 14)
        self.assertEqual(result.damage, 7)
        self.assertEqual(self.goblin.hp, 5)

    def test_miss_does_not_change_hp(self):
        result = attack(self.hero, self.goblin, FixedRoller(2))
        self.assertFalse(result.hit)
        self.assertEqual(self.goblin.hp, 12)

    def test_natural_one_misses_even_when_bonus_would_hit(self):
        strong_hero = Creature("Hero", 20, 14, 20, 8, 2)
        result = attack(strong_hero, self.goblin, FixedRoller(1))
        self.assertFalse(result.hit)
        self.assertEqual(self.goblin.hp, 12)

    def test_natural_twenty_hits_and_hp_never_goes_below_zero(self):
        result = attack(self.hero, self.goblin, FixedRoller(20, 20))
        self.assertTrue(result.hit)
        self.assertEqual(self.goblin.hp, 0)

    def test_initiative_includes_bonus(self):
        self.assertEqual(roll_initiative(self.hero, FixedRoller(11)), 13)


if __name__ == "__main__":
    unittest.main()
