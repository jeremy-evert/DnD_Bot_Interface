import unittest

from dnd_combat.adventure import (
    DIRECTION_ALIASES, HEALING_POTION, Adventure, RoomObject, make_character,
)


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

    def test_dungeon_has_ten_connected_rooms_and_persistent_inventory(self):
        game = Adventure(make_character("fighter", "Arin"))
        self.assertEqual(len(game.rooms), 10)
        for room in game.rooms.values():
            for destination in room.exits.values():
                self.assertIn(destination, game.rooms)
        game.rooms["entry"].enemy.hp = 0  # Clear the first encounter for movement-rule testing.
        self.assertTrue(game.move("east")[0])
        self.assertIn(HEALING_POTION, game.room.items)
        self.assertTrue(game.take_item(HEALING_POTION)[0])
        self.assertTrue(game.move("west")[0])
        self.assertIn(HEALING_POTION, game.hero.inventory)

    def test_mira_reacts_to_carried_ring_and_opens_persistent_shortcut(self):
        game = Adventure(make_character("fighter", "Arin"))
        game.rooms["entry"].enemy.hp = 0
        game.hero.inventory.append("goblin's brass ring")
        game.move("east")
        game.move("east")
        game.move("north")

        interacted, response = game.talk("Mira")

        self.assertTrue(interacted)
        self.assertIn("recognizes the brass ring", response)
        self.assertEqual(game.room.exits["west"], "sanctum")
        self.assertTrue(game.vault_opened)
        game.move("west")
        self.assertEqual(game.current_room_id, "sanctum")

    def test_mira_remembers_ring_question_after_player_leaves_gallery(self):
        game = Adventure(make_character("fighter", "Arin"))
        game.rooms["entry"].enemy.hp = 0
        game.move("east")
        game.move("east")
        game.move("north")

        self.assertTrue(game.talk()[0])
        self.assertTrue(game.mira_memory.asked_about_ring)
        self.assertTrue(game.move("south")[0])
        game.hero.inventory.append("goblin's brass ring")
        self.assertTrue(game.move("north")[0])

        interacted, response = game.talk("Mira")

        self.assertTrue(interacted)
        self.assertIn("You remembered what I asked", response)
        self.assertIn("opens the hidden door west to the vault", response)
        self.assertEqual(game.room.exits["west"], "sanctum")
        self.assertTrue(game.vault_opened)

    def test_mira_opens_shortcut_for_ring_without_claiming_prior_conversation(self):
        game = Adventure(make_character("fighter", "Arin"))
        game.rooms["entry"].enemy.hp = 0
        game.hero.inventory.append("goblin's brass ring")
        game.move("east")
        game.move("east")
        game.move("north")

        interacted, response = game.talk("Mira")

        self.assertTrue(interacted)
        self.assertNotIn("You remembered what I asked", response)
        self.assertEqual(game.room.exits["west"], "sanctum")
        self.assertTrue(game.vault_opened)

    def test_mira_memory_is_fresh_per_adventure_and_not_inferred(self):
        first = Adventure(make_character("fighter", "Arin"))
        second = Adventure(make_character("fighter", "Bea"))
        first.hero.inventory.append("goblin's brass ring")

        self.assertFalse(first.mira_memory.asked_about_ring)
        self.assertFalse(second.mira_memory.asked_about_ring)
        self.assertIsNot(first.mira_memory, second.mira_memory)
        first.rooms["entry"].enemy.hp = 0
        first.move("east")
        first.move("east")
        first.move("north")
        self.assertFalse(first.mira_memory.asked_about_ring)
        first.talk("Mira")
        self.assertFalse(second.mira_memory.asked_about_ring)

    def test_repeat_talk_after_mira_opens_shortcut_changes_nothing(self):
        game = Adventure(make_character("fighter", "Arin"))
        game.rooms["entry"].enemy.hp = 0
        game.hero.inventory.append("goblin's brass ring")
        game.move("east")
        game.move("east")
        game.move("north")
        game.talk("Mira")
        exits = dict(game.room.exits)
        memory = game.mira_memory.asked_about_ring

        interacted, response = game.talk("Mira")

        self.assertTrue(interacted)
        self.assertEqual(response, "Mira nods at the ring; the hidden door west remains open.")
        self.assertEqual(game.room.exits, exits)
        self.assertTrue(game.vault_opened)
        self.assertEqual(game.mira_memory.asked_about_ring, memory)

    def test_holding_ring_and_being_in_gallery_do_not_set_mira_memory(self):
        game = Adventure(make_character("fighter", "Arin"))
        game.rooms["entry"].enemy.hp = 0
        game.hero.inventory.append("goblin's brass ring")
        game.move("east")
        game.move("east")
        game.move("north")

        self.assertFalse(game.mira_memory.asked_about_ring)

    def test_gallery_npc_hints_at_ring_when_player_has_not_found_it(self):
        game = Adventure(make_character("fighter", "Arin"))
        game.rooms["entry"].enemy.hp = 0
        game.move("east")
        game.move("east")
        game.move("north")

        interacted, response = game.talk()

        self.assertTrue(interacted)
        self.assertIn("brass ring", response)
        self.assertNotIn("west", game.room.exits)

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
        game.move("north")
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

    def test_look_describes_persistent_room_objects_and_take_without_target_lists_loot(self):
        game = Adventure(make_character("fighter", "Arin"))
        game.rooms["entry"].objects.append(
            RoomObject("mossy bench", "A low stone bench slick with moss.")
        )
        game.rooms["entry"].enemy.hp = 0

        self.assertIn("mossy bench (A low stone bench slick with moss.)", game.look())
        self.assertEqual(game.take_item(), (False, "There is nothing takeable here."))
        game.move("east")
        self.assertEqual(
            game.take_item(), (False, "Takeable objects: healing potion.")
        )

    def test_take_accepts_deterministic_ring_alias(self):
        game = Adventure(make_character("fighter", "Arin"))
        game.start_encounter(FixedRoller(20, 1))
        game.player_attack(FixedRoller(20, 10))

        self.assertEqual(game.take_item("ring"), (True, "You take the goblin's brass ring."))
        self.assertIn("goblin's brass ring", game.hero.inventory)

    def test_room_object_suggestions_are_strictly_validated_and_persist(self):
        game = Adventure(make_character("fighter", "Arin"))
        accepted = game.add_room_object_suggestions([
            {"name": "cracked lantern", "description": "An old lantern with a smoke-blackened chimney."},
            {"name": "magic key", "description": "A key that opens the eastern exit."},
            {"name": "dusty map", "description": "A map that reveals treasure."},
            {"name": "rope", "description": "A rope.", "takeable": False},
        ])

        self.assertEqual([thing.name for thing in accepted], ["cracked lantern"])
        self.assertFalse(accepted[0].takeable)
        self.assertIn("cracked lantern", game.look())
        game.rooms["entry"].enemy.hp = 0
        game.move("east")
        game.move("west")
        self.assertIn("cracked lantern", game.look())


if __name__ == "__main__":
    unittest.main()
