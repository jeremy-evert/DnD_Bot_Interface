"""Immutable data model for validated Fast Delve packs."""
from dataclasses import dataclass
import re

ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
EVENT_KEY_RE = re.compile(r"^[a-z][a-z0-9_.]{1,63}$")
DIRECTIONS = ("north", "south", "east", "west")
ZONES = ("near", "far", "doorway", "hazard")
VERBS_READER_ON = ("look", "use", "throw")
HAZARD_TAGS = ("collapse", "fire", "drop", "noise", "cover", "unstable_ground")
INTENT_TYPES = ("strike", "rush", "smash", "grab", "guard")
EFFECT_TYPES = ("damage", "heal", "tick_clock", "move_zone", "set_flag", "reveal_clue", "spawn_object", "remove_object", "open_exit", "end_run", "interrupt_intent")
TERMINAL_KINDS = ("playing", "victory", "dead", "quit", "death")
PREDICATE_KINDS = ("enemy_dead", "fact_known", "flag_set", "clock_at_least", "room_is")

@dataclass(frozen=True)
class Effect:
    type: str
    target: str|None = None
    amount: int|None = None
    clock_id: str|None = None
    actor: str|None = None
    zone: str|None = None
    flag_id: str|None = None
    value: bool|None = None
    clue_id: str|None = None
    room_id: str|None = None
    object_id: str|None = None
    direction: str|None = None
    state: str|None = None

@dataclass(frozen=True)
class Counter:
    action: str
    result: str
@dataclass(frozen=True)
class Intent:
    id: str; type: str; telegraph_key: str; target_zone: str; effects: tuple[Effect,...]; counters: tuple[Counter,...]
@dataclass(frozen=True)
class Stats:
    hp: int; armor_class: int; attack_bonus: int; damage_die: int; damage_bonus: int
@dataclass(frozen=True)
class Reader:
    on: str; event_key: str; effects: tuple[Effect,...]; when_room_id: str|None=None; when_flag_id: str|None=None
@dataclass(frozen=True)
class GameObject:
    id: str; name: str; zone: str; reader: Reader|None=None; atmosphere_only: bool=False; atmosphere_id: str|None=None
@dataclass(frozen=True)
class Exit:
    direction: str; to_room_id: str; gate: object|None=None
@dataclass(frozen=True)
class Gate:
    kind: str; flag_id: str; denial_event_key: str
@dataclass(frozen=True)
class Room:
    id: str; title: str; description_key: str; zones: tuple[str,...]; exits: tuple[Exit,...]; objects: tuple[GameObject,...]; npc_id: str|None=None
@dataclass(frozen=True)
class Enemy:
    id: str; name: str; room_id: str; stats: Stats; intent_cycle: tuple[str,...]; intents: tuple[Intent,...]; start_zone: str="near"
@dataclass(frozen=True)
class Hazard:
    id: str; room_id: str; zone: str; tag: str; event_key: str; trigger: dict; effects: tuple[Effect,...]
@dataclass(frozen=True)
class ClockSource:
    source: str; amount: int
@dataclass(frozen=True)
class Threshold:
    at: int; effects: tuple[Effect,...]
@dataclass(frozen=True)
class Clock:
    id: str; label: str; max: int; start: int; tick_sources: tuple[ClockSource,...]; thresholds: tuple[Threshold,...]
@dataclass(frozen=True)
class Item:
    id: str; name: str; reader: Reader; throw_tags: tuple[str,...]=()
@dataclass(frozen=True)
class Fact:
    id: str; payoff: bool; clue_ids: tuple[str,...]; payoff_effects: tuple[Effect,...]; label: str|None=None
@dataclass(frozen=True)
class Clue:
    id: str; fact_id: str; source_id: str; room_id: str; event_key: str
@dataclass(frozen=True)
class Terminal:
    id: str; kind: str; all: tuple[dict,...]; event_key: str; retry_hint_key: str|None=None
@dataclass(frozen=True)
class BankEntry:
    key: str; fact_slots: tuple[str,...]; variants: tuple[str,...]; fallback: str
@dataclass(frozen=True)
class Pack:
    schema_version: int; id: str; title: str; start_room_id: str; atmosphere_registry: tuple[str,...]; rooms: tuple[Room,...]; enemies: tuple[Enemy,...]; hazards: tuple[Hazard,...]; clocks: tuple[Clock,...]; items: tuple[Item,...]; facts: tuple[Fact,...]; clues: tuple[Clue,...]; terminals: tuple[Terminal,...]; bank: tuple[BankEntry,...]; meta: dict|None=None
