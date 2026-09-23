import unittest

from dnd_combat.adventure import DIRECTION_ALIASES, HEALING_POTION, Adventure, make_character


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

    def test_direction_aliases_move_between_rooms(self):
        game = Adventure(make_character("fighter", "Arin"))
        game.rooms["entry"].enemy.hp = 0

        self.assertTrue(game.move("e")[0])
        self.assertEqual(game.current_room_id, "stores")
        self.assertTrue(game.move("W")[0])
        self.assertEqual(game.current_room_id, "entry")
        self.assertEqual(
            DIRECTION_ALIASES,
            {"north": "north", "n": "north", "south": "south", "s": "south",
             "east": "east", "e": "east", "west": "west", "w": "west"},
        )

    def test_defeated_enemy_changes_look_and_drops_takeable_loot(self):
        game = Adventure(make_character("fighter", "Arin"))
        self.assertIn("A goblin is here.", game.look())

        game.start_encounter(FixedRoller(20, 1))
        game.player_attack(FixedRoller(20, 10))

        self.assertIn("The goblin lies defeated.", game.look())
        self.assertNotIn("A goblin is here.", game.look())
        self.assertIn("goblin's brass ring", game.room.items)
        self.assertTrue(game.take_item("goblin's brass ring")[0])
        self.assertIn("goblin's brass ring", game.hero.inventory)

    def test_room_items_and_enemy_state_persist_after_leaving_and_returning(self):
        game = Adventure(make_character("fighter", "Arin"))
        game.start_encounter(FixedRoller(20, 1))
        game.player_attack(FixedRoller(20, 10))
        game.take_item("goblin's brass ring")
        game.hero.hp = 17

        game.move("east")
        game.move("west")

        self.assertFalse(game.rooms["entry"].enemy.alive)
        self.assertNotIn("goblin's brass ring", game.rooms["entry"].items)
        self.assertIn("goblin's brass ring", game.hero.inventory)
        self.assertEqual(game.hero.hp, 17)

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

    def test_missing_combat_potion_does_not_consume_hero_turn(self):
        game = Adventure(make_character("fighter", "Arin"))
        game.start_encounter(FixedRoller(20, 1))
        starting_hp = game.hero.hp

        used, healed = game.player_use_potion()

        self.assertFalse(used)
        self.assertEqual(healed, 0)
        self.assertEqual(game.hero.hp, starting_hp)
        self.assertEqual(game.combat_turn, "hero")


if __name__ == "__main__":
    unittest.main()
