"""Terminal interface for the deterministic three-room adventure."""

from __future__ import annotations

from .adventure import HEALING_POTION, Adventure, make_character
from .combat import AttackResult, Creature, Roller, roll_die
from .narrator import Narrator, make_narrator


def emit(narrator: Narrator, event: str, facts: dict, plain_text: str) -> None:
    """Render one completed game event without allowing narration to mutate state."""
    print(narrator.narrate(event, facts, plain_text))


def show_status(game: Adventure) -> None:
    hero = game.hero
    inventory = ", ".join(hero.inventory) if hero.inventory else "empty"
    print(
        f"{hero.name} the {hero.character_class}: "
        f"{hero.hp}/{hero.max_hp} HP, AC {hero.armor_class}. Inventory: {inventory}."
    )


def room_facts(game: Adventure) -> dict:
    enemy = game.enemy
    return {
        "room": game.room.name,
        "description": game.room.description,
        "exits": sorted(game.room.exits),
        "objects": [
            {"name": thing.name, "description": thing.description, "takeable": thing.takeable}
            for thing in game.room.objects
        ],
        "enemy": enemy.name if enemy and enemy.alive else None,
        "defeated_enemy": enemy.name if enemy and not enemy.alive else None,
        "hero": game.hero.name,
        "hero_class": game.hero.character_class,
        "hero_hp": game.hero.hp,
        "hero_max_hp": game.hero.max_hp,
        "inventory": list(game.hero.inventory),
    }


def announce_room(game: Adventure, narrator: Narrator) -> None:
    if game.request_room_object_suggestions():
        game.add_room_object_suggestions(narrator.suggest_room_objects(room_facts(game)))
    emit(
        narrator,
        "enter_room",
        room_facts(game),
        f"{game.room.name}: {game.look()}",
    )
    for item in game.room.items:
        emit(
            narrator,
            "item_found",
            {
                "room": game.room.name,
                "item": item,
                "hero": game.hero.name,
            },
            f"You spot {item}.",
        )


def describe_attack(
    attacker_name: str,
    defender_name: str,
    result: AttackResult,
    hp_before: int,
    hp_after: int,
    narrator: Narrator,
) -> None:
    if result.hit:
        plain = (
            f"{attacker_name} rolls {result.roll} ({result.total}) and hits "
            f"{defender_name} for {result.damage} damage!"
        )
        event = "attack_hit"
    else:
        plain = (
            f"{attacker_name} rolls {result.roll} ({result.total}) and misses "
            f"{defender_name}."
        )
        event = "attack_miss"

    # Attack rolls are deliberately routine: keep them factual and avoid an
    # LLM call per swing. The narrator remains for room entry and outcomes.
    print(plain)


def choose_character() -> Creature:
    name = input("What is your hero's name? ").strip() or "Hero"
    aliases = {
        "f": "fighter",
        "fighter": "fighter",
        "r": "rogue",
        "rogue": "rogue",
        "w": "wizard",
        "wizard": "wizard",
    }
    while True:
        choice = input(
            "Choose a character [F]ighter, [R]ogue, or [W]izard: "
        ).strip().lower()
        if choice in aliases:
            return make_character(aliases[choice], name)
        print("Choose fighter, rogue, or wizard.")


def run_combat(
    game: Adventure,
    roller: Roller = roll_die,
    narrator: Narrator | None = None,
) -> None:
    narrator = narrator or make_narrator()
    enemy = game.enemy
    hero_initiative, enemy_initiative = game.start_encounter(roller)
    print(
        f"\n{enemy.name} attacks! Initiative — {game.hero.name}: "
        f"{hero_initiative}; {enemy.name}: {enemy_initiative}"
    )

    while game.in_combat:
        enemy = game.enemy
        show_status(game)
        print(f"{enemy.name}: {enemy.hp}/{enemy.max_hp} HP, AC {enemy.armor_class}.")

        if game.combat_turn == "hero":
            choice = input(
                "Your turn. [A]ttack, [U]se potion, [S]tatus: "
            ).strip().lower()

            if choice in {"a", "attack"}:
                hp_before = enemy.hp
                items_before = set(game.room.items)
                result = game.player_attack(roller)
                describe_attack(
                    game.hero.name,
                    enemy.name,
                    result,
                    hp_before,
                    enemy.hp,
                    narrator,
                )

                if not enemy.alive:
                    emit(
                        narrator,
                        "enemy_defeated",
                        {
                            "hero": game.hero.name,
                            "enemy": enemy.name,
                            "room": game.room.name,
                        },
                        f"{enemy.name} falls.",
                    )
                    new_items = [
                        item for item in game.room.items if item not in items_before
                    ]
                    for item in new_items:
                        emit(
                            narrator,
                            "item_found",
                            {
                                "room": game.room.name,
                                "item": item,
                                "hero": game.hero.name,
                                "source": enemy.name,
                            },
                            f"You notice {item} among the fallen {enemy.name}.",
                        )

            elif choice in {"u", "use", "potion"}:
                used, healed = game.player_use_potion()
                print(
                    f"You recover {healed} HP."
                    if used
                    else "You have no healing potion."
                )
            elif choice in {"s", "status"}:
                show_status(game)
            else:
                print("Choose attack, use, or status.")

        else:
            print(f"{enemy.name}'s turn...")
            hp_before = game.hero.hp
            result = game.enemy_attack(roller)
            describe_attack(
                enemy.name,
                game.hero.name,
                result,
                hp_before,
                game.hero.hp,
                narrator,
            )

    if game.state == "won":
        emit(
            narrator,
            "victory",
            {
                "hero": game.hero.name,
                "hero_hp": game.hero.hp,
                "enemy": enemy.name,
                "room": game.room.name,
            },
            "Victory! The hobgoblin captain falls; you have cleared the dungeon.",
        )
    elif game.state == "dead":
        emit(
            narrator,
            "player_death",
            {
                "hero": game.hero.name,
                "hero_class": game.hero.character_class,
                "enemy": enemy.name,
                "room": game.room.name,
            },
            "You have fallen. The adventure ends here.",
        )


def main(
    roller: Roller = roll_die,
    narrator: Narrator | None = None,
) -> None:
    narrator = narrator or make_narrator()

    print("=== D&D 0.3: The Mossy Delve ===")
    game = Adventure(choose_character())
    print(
        f"Welcome, {game.hero.name}. Find your way through three rooms "
        "and survive the final encounter."
    )
    announce_room(game, narrator)

    while game.state == "playing":
        if game.in_combat:
            run_combat(game, roller, narrator)
            if game.state != "playing":
                break
            print(f"\n{game.room.name}: {game.look()}")
            continue

        choice = input(
            "[M]ove, [L]ook, [S]tatus, [T]ake item, [U]se potion: "
        ).strip().lower()

        if choice in {"m", "move"}:
            direction = input("Direction: ").strip().lower()
            moved, message = game.move(direction)
            if moved:
                announce_room(game, narrator)
            else:
                print(message)
        elif choice in {"l", "look"}:
            print(game.look())
        elif choice in {"s", "status"}:
            show_status(game)
        elif choice in {"t", "take"}:
            item = input("Take what? ").strip().lower()
            print(game.take_item(item)[1])
        elif choice in {"u", "use"}:
            used, healed = game.use_healing_potion()
            print(
                f"You recover {healed} HP."
                if used
                else f"You have no {HEALING_POTION}."
            )
        else:
            print("Choose move, look, status, take, or use.")


if __name__ == "__main__":
    main()
