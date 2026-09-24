"""Deterministic adventure rules, independent of terminal input and output."""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from .combat import AttackResult, Creature, Roller, attack, roll_die, roll_initiative


HEALING_POTION = "healing potion"
_SAFE_OBJECT_NAME = re.compile(r"^[a-z][a-z' -]{1,48}$")
_FORBIDDEN_OBJECT_WORDS = {
    "armor", "bonus", "coin", "damage", "enemy", "exit", "gold", "heal",
    "healing", "key", "loot", "map", "monster", "potion", "reward", "spell",
    "weapon",
}

DIRECTION_ALIASES = {
    "north": "north", "n": "north",
    "south": "south", "s": "south",
    "east": "east", "e": "east",
    "west": "west", "w": "west",
}


@dataclass
class RoomObject:
    """A persistent, factual thing in a room.

    Only deterministic content may be takeable. LLM-created objects are always
    scenery, so accepting one can never alter rules, rewards, or progression.
    """

    name: str
    description: str
    takeable: bool = False
    aliases: tuple[str, ...] = ()


@dataclass
class Room:
    """One room in the small, connected dungeon."""

    name: str
    description: str
    exits: dict[str, str]
    objects: list[RoomObject] = field(default_factory=list)
    enemy: Creature | None = None
    encounter_started: bool = False
    loot_dropped: bool = False
    object_suggestions_requested: bool = False

    @property
    def items(self) -> list[str]:
        """Compatibility view of the room's takeable objects."""
        return [thing.name for thing in self.objects if thing.takeable]


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
        "entry": Room(
            "Mossy Entry", "A damp stone entryway opens onto a passage east.", {"east": "stores"},
            enemy=make_goblin(),
        ),
        "stores": Room(
            "Forgotten Stores", "Broken crates fill a quiet storeroom. A passage continues east.",
            {"west": "entry", "east": "sanctum"},
            [RoomObject(HEALING_POTION, "A stoppered vial of red liquid.", True)],
        ),
        "sanctum": Room(
            "Captain's Sanctum", "A scarred chamber has a passage west.", {"west": "stores"},
            enemy=make_hobgoblin(),
        ),
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
        if self.enemy is not None:
            if self.enemy.alive:
                details.append(f"A {self.enemy.name.lower()} is here.")
            else:
                details.append(f"The {self.enemy.name.lower()} lies defeated.")
        if self.room.objects:
            details.append(
                "You see: " + "; ".join(
                    f"{thing.name} ({thing.description})" for thing in self.room.objects
                ) + "."
            )
        details.append("Exits: " + ", ".join(sorted(self.room.exits)) + ".")
        return " ".join(details)

    def move(self, direction: str) -> tuple[bool, str]:
        if self.in_combat:
            return False, "Defeat the enemy before moving on."
        canonical_direction = DIRECTION_ALIASES.get(direction.strip().lower())
        destination = self.room.exits.get(canonical_direction) if canonical_direction else None
        if destination is None:
            return False, "There is no exit that way."
        self.current_room_id = destination
        self.combat_turn = None
        return True, f"You enter {self.room.name}."

    def take_item(self, item: str = "") -> tuple[bool, str]:
        """Take a deterministic, takeable room object by name or alias."""
        requested = item.strip().lower()
        takeable = [thing for thing in self.room.objects if thing.takeable]
        if not requested:
            if takeable:
                return False, "Takeable objects: " + ", ".join(thing.name for thing in takeable) + "."
            return False, "There is nothing takeable here."
        for thing in takeable:
            if requested == thing.name.lower() or requested in thing.aliases:
                self.room.objects.remove(thing)
                self.hero.inventory.append(thing.name)
                return True, f"You take the {thing.name}."
        return False, f"There is no takeable {item} here."

    def request_room_object_suggestions(self) -> bool:
        """Claim a room's one first-entry suggestion opportunity."""
        if self.room.object_suggestions_requested:
            return False
        self.room.object_suggestions_requested = True
        return True

    def add_room_object_suggestions(self, suggestions: object) -> list[RoomObject]:
        """Strictly accept only harmless, structured LLM scenery suggestions."""
        if not isinstance(suggestions, list):
            return []
        accepted: list[RoomObject] = []
        existing = {thing.name.lower() for thing in self.room.objects}
        for suggestion in suggestions[:3]:
            if not isinstance(suggestion, dict) or set(suggestion) != {"name", "description"}:
                continue
            name, description = suggestion["name"], suggestion["description"]
            if not isinstance(name, str) or not isinstance(description, str):
                continue
            name, description = name.strip().lower(), description.strip()
            words = set(re.findall(r"[a-z]+", f"{name} {description}".lower()))
            if (
                not _SAFE_OBJECT_NAME.fullmatch(name)
                or not 3 <= len(description) <= 160
                or "\n" in description
                or words & _FORBIDDEN_OBJECT_WORDS
                or name in existing
            ):
                continue
            object_ = RoomObject(name, description)
            self.room.objects.append(object_)
            accepted.append(object_)
            existing.add(name)
        return accepted

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
        """Use a potion on the hero's turn.

        A missing potion is an invalid combat action: it changes neither HP nor
        turn, so the hero may choose a valid action instead.
        """
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
            self._drop_enemy_loot()
            self.combat_turn = None
            if self.current_room_id == "sanctum":
                self.state = "won"
        else:
            self.combat_turn = "enemy" if self.combat_turn == "hero" else "hero"

    def _drop_enemy_loot(self) -> None:
        """Move an enemy's carried items to its room exactly once."""
        if self.room.loot_dropped or self.enemy is None:
            return
        self.room.objects.extend(
            RoomObject(item, f"Taken from the defeated {self.enemy.name.lower()}.", True,
                       ("ring",) if item == "goblin's brass ring" else ())
            for item in self.enemy.inventory
        )
        self.enemy.inventory.clear()
        self.room.loot_dropped = True
