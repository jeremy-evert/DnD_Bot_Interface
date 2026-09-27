"""Terminal interface for the deterministic Mossy Delve adventure."""

from __future__ import annotations

import sys

from .adventure import HEALING_POTION, Adventure, make_character
from .combat import Creature, Roller, roll_die
from .commands import (
    resolve_character_command,
    resolve_combat_command,
    resolve_exploration_command,
)
from .narrator import Narrator, make_narrator
from .session import announce_room
from .session_log import RecordingNarrator, SessionRecorder
from .terminal import describe_attack, emit, show_status


def choose_character(recorder: SessionRecorder | None = None) -> Creature:
    name = input("What is your hero's name? ").strip() or "Hero"
    while True:
        choice = input(
            "Choose a character [F]ighter, [R]ogue, or [W]izard: "
        ).strip().lower()
        character = resolve_character_command(choice)
        if character:
            hero = make_character(character, name)
            if recorder:
                recorder.record("character_created", hero=name, character_class=character)
            return hero
        print("Choose fighter, rogue, or wizard.")


def run_combat(
    game: Adventure,
    roller: Roller = roll_die,
    narrator: Narrator | None = None,
    recorder: SessionRecorder | None = None,
) -> None:
    narrator = narrator or make_narrator()
    enemy = game.enemy
    hero_initiative, enemy_initiative = game.start_encounter(roller)
    print(
        f"\n{enemy.name} attacks! Initiative — {game.hero.name}: "
        f"{hero_initiative}; {enemy.name}: {enemy_initiative}"
    )
    if recorder:
        recorder.record(
            "encounter_started",
            room_id=game.current_room_id,
            room=game.room.name,
            enemy=enemy.name,
            rolls={"hero_initiative": hero_initiative, "enemy_initiative": enemy_initiative},
        )

    while game.in_combat:
        enemy = game.enemy
        show_status(game)
        print(f"{enemy.name}: {enemy.hp}/{enemy.max_hp} HP, AC {enemy.armor_class}.")

        if game.combat_turn == "hero":
            raw_choice = input(
                "Your turn. [A]ttack, [U]se potion, [S]tatus: "
            ).strip()
            choice = resolve_combat_command(raw_choice)

            if choice in {"a", "attack"}:
                hp_before = enemy.hp
                items_before = set(game.room.items)
                result = game.player_attack(roller)
                if recorder:
                    recorder.input(
                        raw_choice, game, action="attack",
                        outcome="hit" if result.hit else "miss",
                        details={
                            "attacker": game.hero.name,
                            "target": enemy.name,
                            "rolls": {"d20": result.roll, "total": result.total, "damage": result.damage},
                            "enemy_hp": enemy.hp,
                        },
                    )
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
                hp_before = game.hero.hp
                used, healed = game.player_use_potion()
                if recorder:
                    recorder.input(
                        raw_choice, game, action="use_potion",
                        outcome="used" if used else "unavailable",
                        details={"healed": healed, "hp_before": hp_before, "hp_after": game.hero.hp},
                    )
                print(
                    f"You recover {healed} HP."
                    if used
                    else "You have no healing potion."
                )
            elif choice in {"s", "status"}:
                if recorder:
                    recorder.input(raw_choice, game, action="status", outcome="shown")
                show_status(game)
            else:
                if recorder:
                    recorder.input(raw_choice, game, outcome="unrecognized or unsupported combat command")
                print("Choose attack, use, or status.")

        else:
            print(f"{enemy.name}'s turn...")
            hp_before = game.hero.hp
            result = game.enemy_attack(roller)
            if recorder:
                recorder.record(
                    "enemy_action",
                    room_id=game.current_room_id,
                    room=game.room.name,
                    enemy=enemy.name,
                    action="attack",
                    outcome="hit" if result.hit else "miss",
                    rolls={"d20": result.roll, "total": result.total, "damage": result.damage},
                    hero_hp=game.hero.hp,
                )
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
    recorder: SessionRecorder | None = None,
) -> None:
    recorder = recorder or SessionRecorder()
    narrator = RecordingNarrator(narrator or make_narrator(), recorder)

    print("=== D&D 0.6: The Mossy Delve ===")
    game = Adventure(choose_character(recorder))
    recorder.record(
        "session_started",
        hero=game.hero.name,
        character_class=game.hero.character_class,
        room_id=game.current_room_id,
        room=game.room.name,
    )
    print(
        f"Welcome, {game.hero.name}. Explore the delve, see what the world remembers, "
        "and survive the final encounter."
    )
    announce_room(game, narrator, recorder)

    while game.state == "playing":
        if game.in_combat:
            run_combat(game, roller, narrator, recorder)
            if game.state != "playing":
                break
            print(f"\n{game.room.name}: {game.look()}")
            continue

        raw_choice = input(
            "[M]ove, [L]ook, [S]tatus, [T]ake item, [U]se potion, [K] talk: "
        ).strip()
        choice = resolve_exploration_command(raw_choice)

        if choice in {"m", "move"}:
            direction = input("Direction: ").strip().lower()
            origin_id = game.current_room_id
            origin_name = game.room.name
            moved, message = game.move(direction)
            recorder.input(
                f"{raw_choice} {direction}", game, action="move",
                outcome="moved" if moved else message,
                details={"direction": direction, "origin_room_id": origin_id, "origin_room": origin_name},
            )
            if moved:
                announce_room(game, narrator, recorder)
            else:
                print(message)
        elif choice in {"l", "look"}:
            observation = game.look()
            recorder.input(raw_choice, game, action="look", outcome="shown", details={"text": observation})
            print(observation)
        elif choice in {"s", "status"}:
            recorder.input(raw_choice, game, action="status", outcome="shown")
            show_status(game)
        elif choice in {"t", "take"}:
            item = input("Take what? ").strip().lower()
            taken, message = game.take_item(item)
            recorder.input(
                f"{raw_choice} {item}".strip(), game, action="take",
                outcome="taken" if taken else message,
                details={"item": item, "inventory": list(game.hero.inventory)},
            )
            print(message)
        elif choice in {"u", "use"}:
            hp_before = game.hero.hp
            used, healed = game.use_healing_potion()
            recorder.input(
                raw_choice, game, action="use_potion", outcome="used" if used else "unavailable",
                details={"healed": healed, "hp_before": hp_before, "hp_after": game.hero.hp},
            )
            print(
                f"You recover {healed} HP."
                if used
                else f"You have no {HEALING_POTION}."
            )
        elif choice == "talk":
            target = input("Talk to whom? ").strip()
            interacted, message = game.talk(target)
            narrated = message
            if interacted:
                narrated = narrator.narrate(
                    "npc_dialogue",
                    {
                        "npc": game.room.npc,
                        "room": game.room.name,
                        "hero": game.hero.name,
                        "inventory": list(game.hero.inventory),
                        "deterministic_response": message,
                    },
                    message,
                )
            recorder.input(
                f"{raw_choice} {target}".strip(), game, action="talk",
                outcome=message,
                details={"target": target, "response": message, "vault_opened": game.vault_opened},
            )
            print(narrated)
        else:
            recorder.input(raw_choice, game, outcome="unrecognized command")
            print("Choose move, look, status, take, use, or talk.")

    recorder.record(
        "session_ended",
        result=game.state,
        room_id=game.current_room_id,
        room=game.room.name,
        hp=game.hero.hp,
        inventory=list(game.hero.inventory),
        vault_opened=game.vault_opened,
    )


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        print(SessionRecorder.report(sys.argv[2] if len(sys.argv) > 2 else None))
    else:
        main()
