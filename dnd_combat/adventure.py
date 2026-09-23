"""Deterministic adventure rules, independent of terminal input and output."""

from __future__ import annotations

from dataclasses import dataclass, field

from .combat import AttackResult, Creature, Roller, attack, roll_die, roll_initiative


HEALING_POTION = "healing potion"


@dataclass
class Room:
    """One room in the small, connected dungeon."""

    name: str
    description: str
    exits: dict[str, str]
    items: list[str] = field(default_factory=list)
    enemy: Creature | None = None
    encounter_started: bool = False


def make_character(choice: str, name: str) -> Creature:
    """Create one of the three fixed 0.2 player characters."""
    choices = {
        "fighter": (24, 16, 5, 10, 3, 1),
        "rogue": (18, 14, 5, 8, 3, 4),
        "wizard": (14, 12, 5, 10, 2, 3),
    }
    try:
        hp, armor_class, attack_bonus, damage_die, damage_bonus, initiative_bonus = choices[choice.lower()]
    except KeyError as error:
        raise ValueError(f"Unknown character choice: {choice}") from error
    return Creature(name, hp, armor_class, attack_bonus, damage_die, damage_bonus, initiative_bonus, character_class=choice.title())


def make_hobgoblin() -> Creature:
    """Create the final, tougher encounter."""
    return Creature("Hobgoblin Captain", 18, 14, 5, 8, 2, 3)


def make_dungeon() -> dict[str, Room]:
    """Create the fixed three-room adventure."""
    from .combat import make_goblin

    return {
        "entry": Room("Mossy Entry", "A damp stone entryway. A goblin guards the passage east.", {"east": "stores"}, enemy=make_goblin()),
        "stores": Room("Forgotten Stores", "Broken crates fill a quiet storeroom. A passage continues east.", {"west": "entry", "east": "sanctum"}, [HEALING_POTION]),
        "sanctum": Room("Captain's Sanctum", "A scarred hobgoblin captain bars the only way out.", {"west": "stores"}, enemy=make_hobgoblin()),
    }


@dataclass
class Adventure:
    """Mutable game state and rules for the 0.2 adventure."""

    hero: Creature
    rooms: dict[str, Room] = field(default_factory=make_dungeon)
    current_room_id: str = "entry"
    state: str = "playing"  # playing, won, dead
    combat_turn: str | None = None  # hero or enemy

    @property
    def room(self) -> Room:
        return self.rooms[self.current_room_id]

    @property
    def enemy(self) -> Creature | None:
        return self.room.enemy

    @property
    def in_combat(self) -> bool:
        return self.state == "playing" and self.enemy is not None and self.enemy.alive

    def look(self) -> str:
        details = [self.room.description]
        if self.room.items:
            details.append("You see: " + ", ".join(self.room.items) + ".")
        details.append("Exits: " + ", ".join(sorted(self.room.exits)) + ".")
        return " ".join(details)

    def move(self, direction: str) -> tuple[bool, str]:
        if self.in_combat:
            return False, "Defeat the enemy before moving on."
        destination = self.room.exits.get(direction.lower())
        if destination is None:
            return False, "There is no exit that way."
        self.current_room_id = destination
        self.combat_turn = None
        return True, f"You enter {self.room.name}."

    def take_item(self, item: str) -> tuple[bool, str]:
        if item not in self.room.items:
            return False, f"There is no {item} here."
        self.room.items.remove(item)
        self.hero.inventory.append(item)
        return True, f"You take the {item}."

    def use_healing_potion(self) -> tuple[bool, int]:
        if HEALING_POTION not in self.hero.inventory:
            return False, 0
        self.hero.inventory.remove(HEALING_POTION)
        return True, self.hero.heal(8)

    def start_encounter(self, roller: Roller = roll_die) -> tuple[int, int]:
        if not self.in_combat:
            raise ValueError("There is no active encounter in this room.")
        if self.room.encounter_started:
            raise ValueError("This encounter has already started.")
        hero_initiative = roll_initiative(self.hero, roller)
        enemy_initiative = roll_initiative(self.enemy, roller)
        self.room.encounter_started = True
        self.combat_turn = "hero" if hero_initiative >= enemy_initiative else "enemy"
        return hero_initiative, enemy_initiative

    def player_attack(self, roller: Roller = roll_die) -> AttackResult:
        if not self.in_combat or self.combat_turn != "hero":
            raise ValueError("It is not the hero's attack turn.")
        result = attack(self.hero, self.enemy, roller)
        self._finish_or_pass_turn()
        return result

    def enemy_attack(self, roller: Roller = roll_die) -> AttackResult:
        if not self.in_combat or self.combat_turn != "enemy":
            raise ValueError("It is not the enemy's attack turn.")
        result = attack(self.enemy, self.hero, roller)
        self._finish_or_pass_turn()
        return result

    def player_use_potion(self) -> tuple[bool, int]:
        if not self.in_combat or self.combat_turn != "hero":
            raise ValueError("It is not the hero's turn.")
        used, healed = self.use_healing_potion()
        if used:
            self.combat_turn = "enemy"
        return used, healed

    def _finish_or_pass_turn(self) -> None:
        if not self.hero.alive:
            self.state = "dead"
            self.combat_turn = None
        elif not self.enemy.alive:
            self.combat_turn = None
            if self.current_room_id == "sanctum":
                self.state = "won"
        else:
            self.combat_turn = "enemy" if self.combat_turn == "hero" else "hero"
