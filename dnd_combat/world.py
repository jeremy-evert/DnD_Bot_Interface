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
    npc: str | None = None

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


def make_skeleton() -> Creature:
    return Creature("Bone Sentinel", 11, 12, 3, 6, 1, 1)


def make_dungeon() -> dict[str, Room]:
    """Create a compact, connected exploration map with persistent rooms."""
    from .combat import make_goblin

    return {
        "entry": Room(
            "Mossy Entry", "Rain ticks through a cracked ceiling above a passage east.", {"east": "stores"},
            enemy=make_goblin(),
        ),
        "stores": Room(
            "Forgotten Stores", "Broken crates crowd a quiet storeroom. Passages lead west and east.",
            {"west": "entry", "east": "crossroads"},
            [
                RoomObject("broken crates", "Splintered shipping crates, damp and empty."),
                RoomObject(HEALING_POTION, "A stoppered vial of red liquid.", True),
            ],
        ),
        "crossroads": Room(
            "Three-Way Hall", "A worn compass rose marks three passages through the stone.",
            {"west": "stores", "north": "gallery", "south": "cistern"},
            [RoomObject("stone compass", "Its carved arrow points toward no obvious north.")],
        ),
        "gallery": Room(
            "Silent Gallery", "Dusty portraits watch over a junction of old corridors.",
            {"south": "crossroads", "east": "shrine", "north": "observatory"},
            [RoomObject("brass nameplate", "A tarnished plate reads only 'Mira'.", True)],
            npc="Mira",
        ),
        "cistern": Room(
            "Dry Cistern", "A dry cistern opens into a low passage east and the hall north.",
            {"north": "crossroads", "east": "rootway"},
            [RoomObject("clay cup", "A chipped cup rests at the bottom of the cistern.", True)],
            enemy=make_skeleton(),
        ),
        "rootway": Room(
            "Rootway", "Pale roots thread through the ceiling toward a passage north.",
            {"west": "cistern", "north": "shrine"},
            [RoomObject("silver leaf", "A dry leaf glints faintly against the dark stone.", True)],
        ),
        "observatory": Room(
            "Collapsed Observatory", "A cracked dome opens onto a narrow side chamber east.",
            {"south": "gallery", "east": "bell-niche"},
            [RoomObject("star chart", "A worn chart marks a sky no longer visible here.", True)],
        ),
        "bell-niche": Room(
            "Bell Niche", "A tiny dead-end room holds a bell with no clapper.",
            {"west": "observatory"},
            [RoomObject("clapperless bell", "The bronze bell is silent and fixed to the wall.")],
        ),
        "shrine": Room(
            "Rootbound Shrine", "A quiet shrine joins the gallery, rootway, and sealed vault.",
            {"west": "gallery", "south": "rootway", "east": "sanctum"},
            [RoomObject("offering bowl", "A shallow bowl is empty but carefully polished.", True)],
        ),
        "sanctum": Room(
            "Hollow Vault", "A scarred vault lies beyond the shrine. A hidden door may lead west.",
            {"west": "shrine"},
            enemy=make_hobgoblin(),
        ),
    }
