import unittest

from dnd_combat.adventure import HEALING_POTION, Adventure, make_character


class FixedRoller:
    def __init__(self, *rolls):
        self.rolls = iter(rolls)

    def __call__(self, sides):
        return next(self.rolls)


class AdventureTests(unittest.TestCase):
    def test_character_choices_have_distinct_stats(self):
        fighter = make_character("fighter", "Arin")
        rogue = make_character("rogue", "Bea")
        wizard = make_character("wizard", "Cy")

        self.assertEqual(fighter.name, "Arin")
        self.assertEqual(fighter.character_class, "Fighter")
        self.assertEqual((fighter.hp, fighter.armor_class, fighter.attack_bonus, fighter.damage_die, fighter.damage_bonus, fighter.initiative_bonus), (24, 16, 5, 10, 3, 1))
        self.assertNotEqual((fighter.hp, fighter.armor_class, fighter.attack_bonus, fighter.damage_die, fighter.damage_bonus, fighter.initiative_bonus), (rogue.hp, rogue.armor_class, rogue.attack_bonus, rogue.damage_die, rogue.damage_bonus, rogue.initiative_bonus))
        self.assertNotEqual((rogue.hp, rogue.armor_class, rogue.attack_bonus, rogue.damage_die, rogue.damage_bonus, rogue.initiative_bonus), (wizard.hp, wizard.armor_class, wizard.attack_bonus, wizard.damage_die, wizard.damage_bonus, wizard.initiative_bonus))

    def test_dungeon_has_three_connected_rooms_and_persistent_inventory(self):
        game = Adventure(make_character("fighter", "Arin"))
        self.assertEqual(set(game.rooms), {"entry", "stores", "sanctum"})
        game.rooms["entry"].enemy.hp = 0  # Clear the first encounter for movement-rule testing.
        self.assertTrue(game.move("east")[0])
        self.assertIn(HEALING_POTION, game.room.items)
        self.assertTrue(game.take_item(HEALING_POTION)[0])
        self.assertTrue(game.move("west")[0])
        self.assertIn(HEALING_POTION, game.hero.inventory)

    def test_potion_heals_without_exceeding_maximum_hp(self):
        game = Adventure(make_character("rogue", "Bea"))
        game.hero.hp = 12
        game.hero.inventory.append(HEALING_POTION)

        used, healed = game.use_healing_potion()

        self.assertTrue(used)
        self.assertEqual(healed, 6)
        self.assertEqual(game.hero.hp, game.hero.max_hp)
        self.assertNotIn(HEALING_POTION, game.hero.inventory)

    def test_final_enemy_is_harder_and_defeating_it_wins(self):
        game = Adventure(make_character("fighter", "Arin"))
        first_enemy = game.enemy
        final_enemy = game.rooms["sanctum"].enemy
        self.assertGreater(final_enemy.hp, first_enemy.hp)
        self.assertGreater(final_enemy.armor_class, first_enemy.armor_class)

        game.rooms["entry"].enemy.hp = 0
        game.move("east")
        game.move("east")
        game.start_encounter(FixedRoller(20, 1))
        game.player_attack(FixedRoller(20, 20))

        self.assertEqual(game.state, "won")
        self.assertFalse(game.in_combat)

    def test_enemy_attack_can_end_adventure(self):
        game = Adventure(make_character("wizard", "Cy"))
        game.start_encounter(FixedRoller(1, 20))
        game.hero.hp = 1
        game.enemy_attack(FixedRoller(20, 20))

        self.assertEqual(game.state, "dead")


if __name__ == "__main__":
    unittest.main()
