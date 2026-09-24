"""Terminal interface for the deterministic three-room adventure."""

from __future__ import annotations

from .adventure import HEALING_POTION, Adventure, make_character
from .combat import Creature, Roller, roll_die
from .commands import (
    resolve_character_command,
    resolve_combat_command,
    resolve_exploration_command,
)
from .narrator import Narrator, make_narrator
from .session import announce_room
from .terminal import describe_attack, emit, show_status


def choose_character() -> Creature:
    name = input("What is your hero's name? ").strip() or "Hero"
    while True:
        choice = input(
            "Choose a character [F]ighter, [R]ogue, or [W]izard: "
        ).strip().lower()
        character = resolve_character_command(choice)
        if character:
            return make_character(character, name)
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
            choice = resolve_combat_command(input(
                "Your turn. [A]ttack, [U]se potion, [S]tatus: "
            ).strip())

            if choice in {"a", "attack"}:
                hp_before = enemy.hp
                items_before = set(game.room.items)
                result = game.player_attack(roller)
                describe_attack(
                    game.hero.name,
                    enemy.name,
                    result,
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

        choice = resolve_exploration_command(input(
            "[M]ove, [L]ook, [S]tatus, [T]ake item, [U]se potion: "
        ).strip())

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
