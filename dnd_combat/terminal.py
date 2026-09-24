"""Terminal-only rendering of already-resolved game state and events."""

from __future__ import annotations

from .adventure import Adventure
from .combat import AttackResult
from .narrator import Narrator


def emit(narrator: Narrator, event: str, facts: dict, plain_text: str) -> None:
    print(narrator.narrate(event, facts, plain_text))


def show_status(game: Adventure) -> None:
    hero = game.hero
    inventory = ", ".join(hero.inventory) if hero.inventory else "empty"
    print(f"{hero.name} the {hero.character_class}: {hero.hp}/{hero.max_hp} HP, AC {hero.armor_class}. Inventory: {inventory}.")


def room_facts(game: Adventure) -> dict:
    enemy = game.enemy
    return {
        "room": game.room.name, "description": game.room.description,
        "exits": sorted(game.room.exits),
        "objects": [{"name": thing.name, "description": thing.description, "takeable": thing.takeable} for thing in game.room.objects],
        "enemy": enemy.name if enemy and enemy.alive else None,
        "defeated_enemy": enemy.name if enemy and not enemy.alive else None,
        "hero": game.hero.name, "hero_class": game.hero.character_class,
        "hero_hp": game.hero.hp, "hero_max_hp": game.hero.max_hp,
        "inventory": list(game.hero.inventory),
    }


def describe_attack(attacker_name: str, defender_name: str, result: AttackResult, narrator: Narrator) -> None:
    if result.hit:
        print(f"{attacker_name} rolls {result.roll} ({result.total}) and hits {defender_name} for {result.damage} damage!")
    else:
        print(f"{attacker_name} rolls {result.roll} ({result.total}) and misses {defender_name}.")
