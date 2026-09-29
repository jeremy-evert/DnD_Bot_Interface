"""Mutable per-run state for Fast Delve.

Only the future Engine is allowed to mutate a DelveState after construction.
"""
from dataclasses import dataclass, field
import hashlib
import json
import random


_HEROES = {
    "fighter": (24, 16, 5, 10, 3),
    "rogue": (18, 14, 5, 8, 3),
    "wizard": (14, 12, 5, 10, 2),
}


@dataclass
class DelveState:
    pack_id: str
    seed: int
    rng: random.Random = field(repr=False, compare=False)
    rng_draws: int
    player: dict
    room_id: str
    inventory: list
    present_objects: dict
    flags: set
    known_clues: list
    known_facts: list
    clocks: dict
    enemies: dict
    terminal: str = "playing"
    turn: int = 0
    bank_memory: dict = field(default_factory=dict)
    event_log: list = field(default_factory=list)

    @classmethod
    def new(cls, pack, seed, hero_class, name="Ada"):
        try:
            hp, armor_class, attack_bonus, damage_die, damage_bonus = _HEROES[hero_class]
        except (KeyError, TypeError):
            raise ValueError(f"unknown hero class: {hero_class!r}") from None
        present = {room.id: [obj.id for obj in room.objects] for room in pack.rooms}
        enemies = {
            enemy.id: {
                "hp": enemy.stats.hp, "max_hp": enemy.stats.hp,
                "alive": True, "zone": enemy.start_zone,
                "intent_index": 0,
                "current_intent_id": enemy.intent_cycle[0] if enemy.intent_cycle else None,
            }
            for enemy in pack.enemies
        }
        return cls(
            pack_id=pack.id, seed=seed, rng=random.Random(seed), rng_draws=0,
            player={"name": name, "class": hero_class, "hp": hp, "max_hp": hp,
                    "armor_class": armor_class, "attack_bonus": attack_bonus,
                    "damage_die": damage_die, "damage_bonus": damage_bonus,
                    "zone": "near"},
            room_id=pack.start_room_id, inventory=[], present_objects=present,
            flags=set(), known_clues=[], known_facts=[],
            clocks={clock.id: clock.start for clock in pack.clocks}, enemies=enemies,
        )

    def snapshot(self):
        """Return a deterministic JSON-safe snapshot and its canonical hash."""
        state = {
            "pack_id": self.pack_id,
            "seed": self.seed,
            "rng_draws": self.rng_draws,
            "player": self.player,
            "room_id": self.room_id,
            "inventory": self.inventory,
            "present_objects": self.present_objects,
            "flags": sorted(self.flags),
            "known_clues": self.known_clues,
            "known_facts": self.known_facts,
            "clocks": self.clocks,
            "enemies": self.enemies,
            "terminal": self.terminal,
            "turn": self.turn,
            "bank_memory": self.bank_memory,
            "event_log": self.event_log,
        }
        canonical = json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return {**state, "canonical_state_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}


def roll_die(state, sides):
    """Draw only from the run's private RNG and account for the draw."""
    if not isinstance(sides, int) or isinstance(sides, bool) or sides < 1:
        raise ValueError("sides must be a positive integer")
    state.rng_draws += 1
    return state.rng.randint(1, sides)
