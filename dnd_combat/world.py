"""Persistent world state and fixed world construction for The Mossy Delve."""

from __future__ import annotations

from dataclasses import dataclass, field

from .combat import Creature


HEALING_POTION = "healing potion"


@dataclass
class RoomObject:
    """A factual, persistent thing in a room."""

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
    """Create one of the three fixed player characters."""
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
    return Creature("Hobgoblin Captain", 18, 14, 5, 8, 2, 3)


def make_dungeon() -> dict[str, Room]:
    """Create the fixed three-room adventure; no map expansion belongs here."""
    from .combat import make_goblin

    return {
        "entry": Room(
            "Mossy Entry", "A damp stone entryway opens onto a passage east.", {"east": "stores"},
            enemy=make_goblin(),
        ),
        "stores": Room(
            "Forgotten Stores", "Broken crates fill a quiet storeroom. A passage continues east.",
            {"west": "entry", "east": "sanctum"},
            [
                RoomObject("broken crates", "Splintered shipping crates, damp and empty."),
                RoomObject(HEALING_POTION, "A stoppered vial of red liquid.", True),
            ],
        ),
        "sanctum": Room(
            "Captain's Sanctum", "A scarred chamber has a passage west.", {"west": "stores"},
            enemy=make_hobgoblin(),
        ),
    }
