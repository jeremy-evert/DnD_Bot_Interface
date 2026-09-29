"""Read-only parser for the Fast Delve terminal vocabulary."""
from dataclasses import dataclass
import re

from .engine import Action


@dataclass(frozen=True)
class ParseProblem:
    message_key: str
    fact_slots: dict
    text: str = ""


_DIRECTIONS = {"n": "north", "north": "north", "s": "south", "south": "south",
               "e": "east", "east": "east", "w": "west", "west": "west"}


def _get(obj, name, default=None):
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def _resolve(query, candidates, kind):
    """Resolve id/name or a unique word prefix among (id, display name) pairs."""
    raw = query.strip().casefold()
    if not raw:
        return None, ParseProblem("target.unknown", {"target": ""})
    normalized = re.sub(r"\s+", " ", raw)
    exact = [ident for ident, name in candidates
             if normalized == ident.casefold() or normalized == name.casefold()]
    matches = exact or [ident for ident, name in candidates
                        if any(word.startswith(normalized) for word in
                               re.findall(r"[\w']+", (ident + " " + name).casefold()))]
    matches = list(dict.fromkeys(matches))
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        names = [name for ident, name in candidates if ident in matches]
        return None, ParseProblem("target.ambiguous", {"target": query.strip(), "candidates": ", ".join(names)})
    return None, ParseProblem("target.unknown", {"target": query.strip()})


def parse_command(line, state, pack):
    """Return an immutable Action or a user-facing problem without changing state."""
    if not isinstance(line, str):
        return ParseProblem("parse.unknown_verb", {"verb": ""})
    words = line.strip().casefold().split()
    if not words:
        return ParseProblem("command.empty", {}, "Enter a command, or type ? for help.")
    first, rest = words[0], words[1:]
    if first in _DIRECTIONS and not rest:
        return Action("move", direction=_DIRECTIONS[first])
    if first == "go" and len(rest) == 1 and rest[0] in _DIRECTIONS:
        return Action("move", direction=_DIRECTIONS[rest[0]])
    if first in ("look", "x", "examine"):
        if not rest: return Action("look")
        candidates = [(o.id, o.name) for o in next(r for r in pack.rooms if r.id == state.room_id).objects
                      if o.id in state.present_objects[state.room_id]]
        ident, problem = _resolve(" ".join(rest), candidates, "object")
        return problem or Action("look", ident)
    if first in ("i", "inventory") and not rest: return Action("inventory")
    if first in ("a", "attack"):
        if not rest: return Action("attack")
        foes = [(e.id, e.name) for e in pack.enemies if e.room_id == state.room_id and state.enemies[e.id]["hp"] > 0]
        ident, problem = _resolve(" ".join(rest), foes, "enemy")
        return problem or Action("attack", ident)
    if first in ("sh", "shove"):
        if not rest: return Action("shove")
        foes = [(e.id, e.name) for e in pack.enemies if e.room_id == state.room_id and state.enemies[e.id]["hp"] > 0]
        ident, problem = _resolve(" ".join(rest), foes, "enemy")
        return problem or Action("shove", ident)
    if first in ("b", "brace") and not rest: return Action("brace")
    if first in ("t", "throw"):
        item_text = rest
        if "at" in rest:
            at = rest.index("at")
            if at == 0 or at == len(rest) - 1: return ParseProblem("parse.unknown_verb", {"verb": first})
            item_text = rest[:at]
            foes = [(e.id, e.name) for e in pack.enemies
                    if e.room_id == state.room_id and state.enemies[e.id]["hp"] > 0]
            enemy_id, problem = _resolve(" ".join(rest[at + 1:]), foes, "enemy")
            if problem: return problem
        if not item_text: return ParseProblem("target.unknown", {"target": ""})
        items = {i.id: i for i in pack.items}
        candidates = [(ident, items[ident].name) for ident in state.inventory if ident in items]
        ident, problem = _resolve(" ".join(item_text), candidates, "held item")
        return problem or Action("throw", ident)
    if first in ("u", "use"):
        if not rest: return ParseProblem("target.unknown", {"target": ""})
        items = {i.id: i for i in pack.items}
        candidates = [(ident, items[ident].name) for ident in state.inventory if ident in items]
        ident, problem = _resolve(" ".join(rest), candidates, "held item")
        return problem or Action("use", ident)
    if first in ("g", "get", "take"):
        if not rest: return ParseProblem("target.unknown", {"target": ""})
        room = next(r for r in pack.rooms if r.id == state.room_id)
        candidates = [(o.id, o.name) for o in room.objects if o.id in state.present_objects[state.room_id]]
        ident, problem = _resolve(" ".join(rest), candidates, "object")
        return problem or Action("get", ident)
    if first in ("ret", "retreat", "flee") and len(rest) == 1 and rest[0] in _DIRECTIONS:
        return Action("retreat", direction=_DIRECTIONS[rest[0]])
    if first in ("?", "help") and not rest: return Action("help")
    if first in ("q", "quit") and not rest: return Action("quit")
    return ParseProblem("parse.unknown_verb", {"verb": first})
