"""Pure terminal rendering and deterministic bank selection for Fast Delve."""

from dataclasses import dataclass, field
import hashlib
import json
import re


@dataclass
class RenderMemory:
    """Renderer-owned no-repeat tracking; never stored on DelveState."""

    emitted: dict = field(default_factory=dict)
    problems: list = field(default_factory=list)


def _get(obj, name, default=None):
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def _entries(pack):
    bank = _get(pack, "bank", ())
    return _get(bank, "entries", bank)


def _bank(pack):
    return {_get(entry, "key"): entry for entry in _entries(pack)}


def _canonical_slots(slots):
    return json.dumps(slots, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def select_variant(bank_entry, seed, event_key, fact_slots, memory):
    """Choose a matching bank line, cycling without repeats for this event/slots."""
    supplied = dict(fact_slots or {})
    declared = tuple(_get(bank_entry, "fact_slots", ()))
    slots = {name: supplied[name] for name in declared if name in supplied}
    variants = tuple(_get(bank_entry, "variants", ()))
    fallback = _get(bank_entry, "fallback", "")
    missing = set(declared) - set(slots)
    if missing:
        memory.problems.append(
            f"{event_key}: missing declared slots {', '.join(sorted(missing))}"
        )
        return fallback
    eligible = list(variants)
    if not eligible:
        return fallback
    canonical = _canonical_slots(slots)
    mem_key = f"{event_key}|{canonical}"
    emitted = memory.emitted.setdefault(mem_key, [])
    available = [i for i in range(len(eligible)) if i not in emitted]
    if not available:
        emitted.clear()
        available = list(range(len(eligible)))
    digest = hashlib.sha256(f"{seed}|{event_key}|{canonical}".encode("utf-8")).hexdigest()
    index = available[int(digest, 16) % len(available)]
    emitted.append(index)
    return eligible[index]


_SLOT = re.compile(r"{{([^{}]+)}}")


def _fill(text, slots, memory, key):
    def replace(match):
        name = match.group(1)
        if name not in slots:
            memory.problems.append(f"{key}: unresolved slot {name!r}")
            return ""
        return str(slots[name])
    result = _SLOT.sub(replace, text)
    if "{{" in result or "}}" in result:
        memory.problems.append(f"{key}: malformed unresolved placeholder")
        result = result.replace("{{", "").replace("}}", "")
    return result


def render_event(event, pack, seed, memory):
    key = _get(event, "key", "")
    slots = _get(event, "fact_slots", {}) or {}
    entry = _bank(pack).get(key)
    if entry is None:
        # Unknown keys remain legible without trusting them as format strings.
        line = f"Something happens ({key.replace('.', ' ')})."
        return _fill(line, slots, memory, key)
    template = select_variant(entry, seed, key, slots, memory)
    if not template:
        template = _get(entry, "fallback", "")
    if any(name not in slots for name in _SLOT.findall(template)):
        template = _get(entry, "fallback", "")
    return _fill(template, slots, memory, key)


def _slot_value(entry, slots, key, memory):
    text = select_variant(entry, 0, key, slots, memory)
    return _fill(text or _get(entry, "fallback", ""), slots, memory, key)


def _fixed_slot_value(entry, seed, slots, key, memory):
    """Render a status line from a stable private namespace without no-repeat state."""
    declared = tuple(_get(entry, "fact_slots", ()))
    variants = tuple(_get(entry, "variants", ()))
    fallback = _get(entry, "fallback", "")
    if set(declared) != set(slots) or not variants:
        return _fill(fallback, slots, memory, key)
    canonical = _canonical_slots(slots)
    digest = hashlib.sha256(f"{seed}|status|{key}|{canonical}".encode("utf-8")).hexdigest()
    template = variants[int(digest, 16) % len(variants)]
    if any(name not in slots for name in _SLOT.findall(template)):
        template = fallback
    return _fill(template, slots, memory, key)


def _bar(value, maximum):
    value = max(0, min(int(value), int(maximum)))
    return "#" * value + "." * (int(maximum) - value)


def render_status(state, pack, memory=None):
    bank = _bank(pack)
    room = next((r for r in _get(pack, "rooms", ()) if _get(r, "id") == _get(state, "room_id")), None)
    if room is None:
        return ""
    title = str(_get(room, "title", "")).upper()
    player = _get(state, "player", {})
    zone = _get(player, "zone", "near")
    hp, max_hp = _get(player, "hp", 0), _get(player, "max_hp", 0)
    exits = ", ".join({"north":"N", "south":"S", "east":"E", "west":"W"}.get(_get(e, "direction"), "?") for e in _get(room, "exits", ()))
    line = f"{title} [{zone}]  HP {hp}/{max_hp}"
    clocks = _get(pack, "clocks", ())
    if clocks:
        clock = clocks[0]
        label = _get(clock, "label", "CLOCK")
        value = _get(state, "clocks", {}).get(_get(clock, "id"), _get(clock, "start", 0))
        line += f"  {label} [{_bar(value, _get(clock, 'max', 0))}]"
    line += f"  Exits: {exits}"
    lines = [line]
    objects = _get(room, "objects", ())
    present = _get(state, "present_objects", {}).get(_get(room, "id"), [])
    living_enemy = None
    for enemy in _get(pack, "enemies", ()):
        runtime = _get(state, "enemies", {}).get(_get(enemy, "id"), {})
        if _get(enemy, "room_id") == _get(room, "id") and runtime.get("hp", 0) > 0:
            living_enemy = (enemy, runtime)
            break
    memory = memory if memory is not None else RenderMemory()
    if living_enemy:
        enemy, runtime = living_enemy
        intent_id = runtime.get("current_intent_id")
        intent = next((i for i in _get(enemy, "intents", ()) if _get(i, "id") == intent_id), None)
        telegraph = ""
        if intent:
            telegraph_entry = bank.get(_get(intent, "telegraph_key"))
            if telegraph_entry:
                enemy_name = _get(enemy, "name")
                telegraph = _fixed_slot_value(telegraph_entry, _get(state, "seed", 0), {"enemy_name": enemy_name}, _get(intent, "telegraph_key"), memory)
                doubled = f"{enemy_name}: {enemy_name}"
                if telegraph.casefold().startswith(doubled.casefold()):
                    telegraph = f"{enemy_name}:" + telegraph[len(doubled):]
        enemy_name = _get(enemy, "name")
        hp_text = f"{runtime.get('hp', 0)}/{_get(enemy, 'stats').hp} HP [{runtime.get('zone', _get(enemy, 'start_zone', 'near'))}]"
        name_prefix = str(enemy_name)
        if telegraph.casefold().startswith((name_prefix + ":").casefold()):
            body = telegraph[len(name_prefix) + 1:].lstrip()
            if body.startswith("—"):
                body = body[1:].lstrip()
            lines.append(f"{name_prefix} {hp_text} — {body}")
        elif telegraph.casefold().startswith(name_prefix.casefold()):
            lines.append(f"{telegraph} — {hp_text}")
        else:
            lines.append(f"{name_prefix} {hp_text} — {telegraph}")
    else:
        desc_key = _get(room, "description_key")
        desc_entry = bank.get(desc_key)
        if desc_entry:
            lines.append(_slot_value(desc_entry, {"room_name": _get(room, "title")}, desc_key, memory))
        else:
            lines.append(f"Something happens ({str(desc_key).replace('.', ' ')}).")
    present_objects = [obj for obj in objects if _get(obj, "id") in present]
    if living_enemy:
        hazards = [h for h in _get(pack, "hazards", ()) if _get(h, "room_id") == _get(room, "id")]
        if hazards:
            hazard = hazards[0]
            lines.append(f"Hazard: {_get(hazard, 'tag').upper()} [{_get(hazard, 'zone')}].")
    lines.append("Objects: " + ("; ".join(f"{_get(o, 'name')} [{_get(o, 'zone')}]" for o in present_objects) or "none") + ".")
    return "\n".join(lines)


def render_help():
    return ("HELP — n/s/e/w move; x <thing> read; i inventory; a attack; sh <enemy> shove;\n"
            "b brace; t <item> throw; u <item> use; g <item> get; q quit.\n"
            "Enemy intent is shown before it resolves. Use zones, hazards, and exits.")


def render_death(event, pack=None, seed=0, memory=None):
    slots = _get(event, "fact_slots", {}) or {}
    cause = slots.get("cause", "unknown cause")
    memory = memory or RenderMemory()
    bank = _bank(pack) if pack is not None else {}
    def text(key, supplied_slots=None, default=""):
        entry = bank.get(key)
        if entry:
            return render_event({"key":key,"fact_slots":supplied_slots or {}}, pack, seed, memory)
        return default
    event_key = _get(event, "key", "terminal.death")
    event_line = text(event_key, slots, f"You fall to {cause}.")
    retry = text("terminal.retry", {}, "Retry: read the room, then counter the declared intent.")
    return f"YOU DIED — {event_line}\nRetry hint: {retry}\n[r]etry or [q]uit"


def render_victory(event, pack=None, seed=0, memory=None):
    memory = memory or RenderMemory()
    bank = _bank(pack) if pack is not None else {}
    event_key = _get(event, "key", "terminal.victory")
    entry = bank.get(event_key)
    if entry:
        line = render_event(event, pack, seed, memory)
        return f"VAULT CLEARED — {line}\n[r]etry or [q]uit"
    return "VAULT CLEARED —\n[r]etry or [q]uit"
