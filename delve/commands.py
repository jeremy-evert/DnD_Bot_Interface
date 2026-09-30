"""Read-only parser and discoverability metadata for the Fast Delve terminal."""
from dataclasses import dataclass
import re

from .engine import Action


def _bank_text(pack, key):
    entry = next((entry for entry in pack.bank if entry.key == key), None)
    return entry.fallback if entry else "The hazard is difficult to read."


@dataclass(frozen=True)
class ParseProblem:
    message_key: str
    fact_slots: dict
    text: str = ""


@dataclass(frozen=True)
class EnemyInspection:
    enemy_id: str


@dataclass(frozen=True)
class HeldInspection:
    item_id: str


# This table is the parser vocabulary and the source rendered by `?`.
# Each entry is (canonical action, accepted spellings, help label).
COMMANDS = (
    ("move", ("n", "north"), "n / north"),
    ("move", ("s", "south"), "s / south"),
    ("move", ("e", "east"), "e / east"),
    ("move", ("w", "west"), "w / west"),
    ("move", ("go",), "go <direction>"),
    ("look", ("x", "look", "examine", "inspect", "read", "check", "study", "talk", "speak", "ask", "greet"),
     "x/look/examine/inspect/read/check/study <thing>; talk/speak/ask/greet [to/with] <person>"),
    ("inventory", ("i", "inventory"), "i / inventory"),
    ("attack", ("a", "attack", "hit", "strike", "fight", "swing", "slash", "heavy"), "a/attack/hit/strike/fight/swing/slash/heavy [enemy]"),
    ("brace", ("b", "brace", "defend", "guard", "block", "parry"), "b/brace/defend/guard/block/parry"),
    ("shove", ("sh", "shove", "push", "shoulder", "shunt"), "sh/shove/push/shoulder/shunt [enemy]"),
    ("throw", ("t", "throw", "toss", "hurl", "fling"), "t/throw/toss/hurl/fling <item> [at enemy]"),
    ("use", ("u", "use", "give", "hand", "show", "offer", "present", "put", "drink"), "u/use/give/hand/show/offer/present/put/drink <item> [on target]"),
    ("get", ("g", "get", "take", "grab", "pick", "pick up"), "g/get/take/grab/pick/pick up <thing>"),
    ("retreat", ("ret", "retreat", "flee"), "ret / retreat / flee <direction>"),
    ("help", ("?", "help"), "? / help"),
    ("quit", ("q", "quit"), "q / quit"),
)

ALIAS_ACTIONS = {alias: action for action, aliases, _ in COMMANDS for alias in aliases}
HELP_FORMS = tuple(label for _, _, label in COMMANDS)


_DIRECTIONS = {"n": "north", "north": "north", "s": "south", "south": "south",
               "e": "east", "east": "east", "w": "west", "west": "west"}
_PREPOSITIONS = {"to", "for", "on", "in", "with"}
_ITEM_NAME_ALIASES = {"offering_bowl_item": ("rainwater", "water")}


def _get(obj, name, default=None):
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def _room(state, pack):
    return next(r for r in pack.rooms if r.id == state.room_id)


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


def _objects(state, pack):
    room = _room(state, pack)
    present = state.present_objects[state.room_id]
    return [(o.id, o.name) for o in room.objects if o.id in present]


def _enemies(state, pack):
    return [(e.id, e.name) for e in pack.enemies
            if e.room_id == state.room_id and state.enemies[e.id]["hp"] > 0]


def _held_items(state, pack):
    by_id = {item.id: item for item in pack.items}
    candidates = []
    for ident in state.inventory:
        if ident not in by_id:
            continue
        candidates.append((ident, by_id[ident].name))
        candidates.extend((ident, alias) for alias in _ITEM_NAME_ALIASES.get(ident, ()))
    return candidates


def _takeable_item_problem(query, state, pack):
    room = _room(state, pack)
    by_item = {item.id: item for item in pack.items}
    candidates = [(obj.item_id, by_item[obj.item_id].name)
                  for obj in room.objects
                  if obj.id in state.present_objects[state.room_id]
                  and obj.item_id and obj.item_id in by_item]
    ident, problem = _resolve(query, candidates, "takeable item")
    if problem is None:
        item = by_item[ident]
        return ParseProblem("target.not_held", {"target": item.name})
    return None


def _hazard_problem(query, state, pack):
    hazards = [h for h in pack.hazards if h.room_id == state.room_id]
    normalized = query.casefold().strip()
    for hazard in hazards:
        names = {hazard.id.casefold(), hazard.tag.casefold()}
        if hazard.tag == "collapse":
            names.update(("ceiling", "arch", "collapse", "hazard"))
        if normalized in names or any(word.startswith(normalized) for name in names for word in name.split()):
            if hazard.tag == "collapse":
                known = "captain_route_known" in state.flags
                text = _bank_text(pack, "hazard.hint.known" if known else "hazard.hint.unknown")
            elif hazard.tag == "fire":
                text = "This room has a fire hazard. It burns when you enter."
            else:
                text = f"This room has a {hazard.tag.replace('_', ' ')} hazard."
            return ParseProblem("hazard.inspect", {"hazard_name": hazard.tag}, text)
    return None


def _split_item_target(rest, state, pack, allow_reverse=False):
    """Return held item id and optional validated present target."""
    held = _held_items(state, pack)
    tokens = list(rest)
    for index, word in enumerate(tokens):
        if word in _PREPOSITIONS:
            if index == 0 or index == len(tokens) - 1:
                return None, ParseProblem("target.unknown", {"target": " ".join(tokens[index + 1:])})
            item_text, target_text = " ".join(tokens[:index]), " ".join(tokens[index + 1:])
            item_id, problem = _resolve(item_text, held, "held item")
            if problem:
                return None, problem
            target_id, problem = _resolve(target_text, _objects(state, pack) + _enemies(state, pack), "target")
            return (item_id, target_id), problem
    item_id, problem = _resolve(" ".join(tokens), held, "held item")
    if not problem:
        return (item_id, None), None
    if allow_reverse and len(tokens) > 1:
        present_targets = _objects(state, pack) + _enemies(state, pack)
        for split in range(1, len(tokens)):
            target_id, target_problem = _resolve(" ".join(tokens[:split]), present_targets, "target")
            if target_problem:
                continue
            item_id, item_problem = _resolve(" ".join(tokens[split:]), held, "held item")
            if not item_problem:
                return (item_id, target_id), None
    return None, problem


def parse_command(line, state, pack):
    """Return an immutable Action or a user-facing problem without changing state."""
    if not isinstance(line, str):
        return ParseProblem("parse.unknown_verb", {"verb": ""})
    words = line.strip().casefold().split()
    if not words:
        return ParseProblem("command.empty", {}, "Enter a command, or type ? for help.")

    first, rest = words[0], words[1:]
    phrase = " ".join(words)
    multiword_aliases = sorted((alias for alias in ALIAS_ACTIONS if " " in alias), key=len, reverse=True)
    for alias in multiword_aliases:
        if phrase == alias or phrase.startswith(alias + " "):
            first = alias
            rest = phrase[len(alias):].strip().split()
            break
    action = ALIAS_ACTIONS.get(first)

    if first in _DIRECTIONS and not rest:
        return Action("move", direction=_DIRECTIONS[first])
    if first == "go" and len(rest) == 1 and rest[0] in _DIRECTIONS:
        return Action("move", direction=_DIRECTIONS[rest[0]])

    if action == "look":
        if first in ("talk", "speak", "ask", "greet") and rest and rest[0] in ("to", "with"):
            rest = rest[1:]
        if not rest:
            return Action("look")
        query = " ".join(rest)
        ident, problem = _resolve(query, _objects(state, pack), "object")
        if problem and problem.message_key == "target.unknown":
            held_id, held_problem = _resolve(query, _held_items(state, pack), "held item")
            if held_problem is None and held_id in state.inventory:
                return HeldInspection(held_id)
        if problem and first in ("look", "x", "examine", "inspect", "read", "check", "study"):
            problem = _hazard_problem(query, state, pack) or problem
            if problem.message_key == "target.unknown":
                enemy_id, enemy_problem = _resolve(query, _enemies(state, pack), "enemy")
                if enemy_problem is None: return EnemyInspection(enemy_id)
                if enemy_problem.message_key == "target.ambiguous": return enemy_problem
            return problem
        return problem or Action("look", ident)

    if action == "inventory" and not rest:
        return Action("inventory")
    if action == "help" and not rest:
        return Action("help")
    if action == "quit" and not rest:
        return Action("quit")

    if action in ("attack", "shove"):
        if not rest:
            return Action(action)
        foes = _enemies(state, pack)
        if action == "shove":
            if not any(word in ("into", "toward", "at") for word in rest):
                for split in range(1, len(rest)):
                    foe_id, foe_problem = _resolve(" ".join(rest[:split]), foes, "enemy")
                    if foe_problem:
                        continue
                    hint = " ".join(rest[split:])
                    _, object_problem = _resolve(hint, _objects(state, pack), "object")
                    hazard_hint = _hazard_problem(hint, state, pack) if object_problem else None
                    if object_problem and (hazard_hint is None or hazard_hint.message_key != "hazard.inspect"):
                        return object_problem
                    return Action("shove", foe_id)
            for index, word in enumerate(rest):
                if word in ("into", "toward", "at"):
                    if index == 0:
                        return ParseProblem("target.unknown", {"target": " ".join(rest[index + 1:])})
                    hint = " ".join(rest[index + 1:])
                    if not hint:
                        return ParseProblem("target.unknown", {"target": hint})
                    target_id, target_problem = _resolve(hint, _objects(state, pack), "object")
                    if target_problem:
                        hazard_hint = _hazard_problem(hint, state, pack)
                        if hazard_hint is None or hazard_hint.message_key != "hazard.inspect":
                            return target_problem
                    rest = rest[:index]
                    break
        ident, problem = _resolve(" ".join(rest), foes, "enemy")
        return problem or Action(action, ident)

    if action == "brace" and not rest:
        return Action("brace")

    if action == "throw":
        item_text = rest
        enemy_target_id = None
        if "at" in rest:
            at = rest.index("at")
            if at == 0 or at == len(rest) - 1:
                return ParseProblem("target.unknown", {"target": " ".join(rest[at + 1:])})
            item_text = rest[:at]
            enemy_target_id, problem = _resolve(" ".join(rest[at + 1:]), _enemies(state, pack), "enemy")
            if problem:
                return problem
        ident, problem = _resolve(" ".join(item_text), _held_items(state, pack), "held item")
        if problem:
            return _takeable_item_problem(" ".join(item_text), state, pack) or problem
        return Action("throw", ident, enemy_target_id=enemy_target_id)

    if action == "use":
        if not rest:
            return ParseProblem("target.unknown", {"target": ""})
        result, problem = _split_item_target(rest, state, pack, allow_reverse=True)
        if problem:
            query = " ".join(rest)
            for index, word in enumerate(rest):
                if word in _PREPOSITIONS:
                    query = " ".join(rest[:index]); break
            not_held = _takeable_item_problem(query, state, pack)
            if not_held: return not_held
            # Known consumed or otherwise absent items reach the engine's use.nothing line.
            known, known_problem = _resolve(query, [(i.id, i.name) for i in pack.items], "item")
            if known_problem is None and known not in state.inventory: return Action("use", known)
            return problem
        return Action("use", result[0])

    if action == "get":
        if not rest:
            return ParseProblem("target.unknown", {"target": ""})
        ident, problem = _resolve(" ".join(rest), _objects(state, pack), "object")
        return problem or Action("get", ident)

    if first in ("ret", "retreat", "flee", "leave") and not rest:
        return ParseProblem("retreat.help", {})
    if first in ("ret", "retreat", "flee", "leave") and len(rest) == 1 and rest[0] in _DIRECTIONS:
        return Action("retreat", direction=_DIRECTIONS[rest[0]])
    return ParseProblem("parse.unknown_verb", {"verb": first})
