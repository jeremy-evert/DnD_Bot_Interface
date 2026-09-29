"""Deterministic terminal replay adapter around the real game entry point."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib
import io
import json
import random
import sys
from unittest.mock import patch

from dnd_combat.adventure import Adventure as RealAdventure
from dnd_combat.narrator import PlainNarrator
import dnd_combat.__main__ as game_main


class InputsExhausted(BaseException):
    """Private control signal used only when the supplied input frame ends."""


@dataclass
class ReplayResult:
    output: str
    witness: RealAdventure | None
    exhausted: bool
    error: str | None
    consumed: int


class MemoryRecorder:
    """The recorder interface used by main, without files or nondeterminism."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def record(self, event: str, **fields: object) -> None:
        self.events.append((event, fields))

    def input(self, player_input: str, game, *, action=None, outcome=None, details=None) -> None:
        self.record(
            "player_input", input=player_input, room_id=game.current_room_id,
            room=game.room.name, action=action, outcome=outcome,
            details=details or {},
        )


def replay(seed: int, input_calls: list[str], narrator=None, game_id="dnd_combat") -> ReplayResult:
    """Run real ``main`` with isolated dice, terminal I/O, and memory state."""
    if game_id not in {"dnd_combat", "delve"}: raise ValueError("unsupported game_id")
    rng = random.Random(seed) if game_id == "dnd_combat" else None
    answers = iter(input_calls)
    consumed = 0
    captured = io.StringIO()
    witnesses = []

    def terminal_input(prompt: str = "") -> str:
        nonlocal consumed
        captured.write(prompt)
        try:
            answer = next(answers)
        except StopIteration:
            raise InputsExhausted()
        consumed += 1
        captured.write(f"{answer}\n")
        return answer

    error = None
    exhausted = False
    with patch("builtins.input", side_effect=terminal_input), patch("sys.stdout", captured):
        try:
            if game_id == "dnd_combat":
                def make_adventure(hero):
                    game = RealAdventure(hero); witnesses.append(game); return game
                with patch.object(game_main, "Adventure", side_effect=make_adventure):
                    game_main.main(roller=lambda sides: rng.randint(1, sides),
                        narrator=narrator if narrator is not None else PlainNarrator(), recorder=MemoryRecorder())
            else:
                delve_main = importlib.import_module("delve.__main__")
                delve_state = importlib.import_module("delve.state")
                real_new = delve_state.DelveState.new
                def make_state(*args, **kwargs):
                    state = real_new(*args, **kwargs); witnesses.append(state); return state
                with patch.object(delve_state.DelveState, "new", side_effect=make_state):
                    delve_main.main(["--seed", str(seed)])
        except InputsExhausted:
            exhausted = True
        except Exception as exc:
            error = repr(exc)

    return ReplayResult(captured.getvalue(), witnesses[0] if witnesses else None,
                        exhausted, error, consumed)


def snapshot(witness, game_id="dnd_combat") -> dict:
    """Return canonical, JSON-safe state for a real Adventure witness."""
    if game_id == "delve": return witness.snapshot()
    if game_id != "dnd_combat": raise ValueError("unsupported game_id")
    hero = witness.hero
    rooms = {}
    for room_id, room in sorted(witness.rooms.items()):
        enemy = room.enemy
        rooms[room_id] = {
            "name": room.name,
            "exits": dict(sorted(room.exits.items())),
            "objects": [
                {"name": item.name, "description": item.description,
                 "aliases": list(item.aliases), "takeable": bool(item.takeable)}
                for item in room.objects
            ],
            "enemy": ({"name": enemy.name, "hp": enemy.hp, "alive": enemy.alive}
                      if enemy is not None else None),
            "encounter_started": room.encounter_started,
            "loot_dropped": room.loot_dropped,
        }
    state = {
        "room_id": witness.current_room_id,
        "room": witness.room.name,
        "hp": hero.hp,
        "max_hp": hero.max_hp,
        "inventory": list(hero.inventory),
        "game_state": witness.state,
        "vault_opened": witness.vault_opened,
        "mira_memory": {"asked_about_ring": witness.mira_memory.asked_about_ring},
        "exits": dict(sorted(witness.room.exits.items())),
        "rooms": rooms,
        "combat_turn": witness.combat_turn,
    }
    canonical = json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    state["canonical_state_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return state
