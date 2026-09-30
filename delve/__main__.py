"""Single-line terminal entry point for Fast Delve."""
import argparse
from pathlib import Path
import time

from .commands import EnemyInspection, HELP_FORMS, ParseProblem, parse_command
from .engine import Engine
from .pack import load_engine_ready_pack
from .render import RenderMemory, render_death, render_event, render_help, render_status, render_victory
from .state import DelveState


def _print(text=""):
    """Keep terminal output alive if the active console cannot encode text."""
    try:
        print(text)
    except UnicodeError:
        print("[text unavailable]")


def _input(prompt):
    """Read a line, mapping undecodable bytes/scalars to a private sentinel."""
    try:
        line = input(prompt)
        line.encode("utf-8")
        return line
    except UnicodeError:
        return None


def _parser():
    parser = argparse.ArgumentParser(description="Play the Fast Delve terminal adventure.")
    parser.add_argument("--seed", type=int, default=None, help="reproducible run seed (default: fresh seed)")
    parser.add_argument("--class", dest="hero_class", choices=("fighter", "rogue", "wizard"), default=None)
    parser.add_argument("--pack", type=Path, default=Path(__file__).parent / "content" / "mossy_fast_slice.json")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    seed = args.seed if args.seed is not None else time.time_ns()
    try:
        pack = load_engine_ready_pack(args.pack)
    except (OSError, ValueError) as exc:
        _print(f"Could not load delve pack: {exc}")
        return 2
    try:
        if args.hero_class is None:
            selected = _input("Class [f]ighter/[r]ogue/[w]izard (enter = fighter): ")
            selected = (selected or "").strip().casefold()
            hero_class = {"": "fighter", "f": "fighter", "fighter": "fighter",
                          "r": "rogue", "rogue": "rogue", "w": "wizard", "wizard": "wizard"}.get(selected, "fighter")
        else:
            hero_class = args.hero_class
    except (EOFError, KeyboardInterrupt):
        _print("The delve waits for another time.")
        return 0

    while True:
        state = DelveState.new(pack, seed, hero_class, name="Delver")
        engine = Engine(pack, state)
        memory = RenderMemory()
        _print(f"{pack.title} — seed {seed} — {hero_class}")
        retry = False
        while state.terminal == "playing":
            _print(render_status(state, pack, memory))
            try:
                line = _input("> ")
            except (EOFError, KeyboardInterrupt):
                _print("The delve pauses here. Goodbye.")
                return 0
            parsed = (parse_command(line, state, pack) if line is not None else
                      ParseProblem("parse.unknown_verb", {"verb": "[undecodable input]"}))
            if isinstance(parsed, EnemyInspection):
                enemy = next(e for e in pack.enemies if e.id == parsed.enemy_id)
                runtime = state.enemies[enemy.id]
                intent = next((i for i in enemy.intents if i.id == runtime.get('current_intent_id')), None)
                intent_text = ''
                if intent:
                    intent_text = render_event({'key': intent.telegraph_key,
                                                'fact_slots': {'enemy_name': enemy.name}},
                                               pack, seed, memory)
                    prefix = enemy.name + ':'
                    if intent_text.casefold().startswith(prefix.casefold()):
                        intent_text = intent_text[len(prefix):].strip()
                _print(f"{enemy.name} {runtime['hp']}/{enemy.stats.hp} HP "
                      f"[{runtime.get('zone', enemy.start_zone)}] — {intent_text or 'no declared intent'}")
                continue
            if isinstance(parsed, ParseProblem):
                if parsed.text:
                    _print(parsed.text)
                else:
                    _print(render_event({"key": parsed.message_key, "fact_slots": parsed.fact_slots}, pack, seed, memory))
                continue
            try:
                events = engine.apply(parsed)
                for event in events:
                    if event.key in ("terminal.death", "terminal.victory") or event.type == "enemy_intent":
                        continue
                    if event.key == "help":
                        tip = render_event(event, pack, seed, memory)
                        tip += "\nObjects marked (get) can be picked up with get <name>."
                        _print(render_help(HELP_FORMS, tip))
                        continue
                    _print(render_event(event, pack, seed, memory))
                if state.terminal == "dead":
                    terminal = next((e for e in events if e.key == "terminal.death"), None)
                    _print(render_death(terminal, pack, seed, memory))
                    try:
                        choice = (_input("Choice: ") or "").strip().casefold()
                    except (EOFError, KeyboardInterrupt):
                        _print("The delve waits for another time.")
                        return 0
                    if choice in ("r", "retry"):
                        seed += 1
                        retry = True
                    else:
                        return 0
                    break
                if state.terminal == "victory":
                    terminal = next((e for e in events if e.key == "terminal.victory"), None)
                    _print(render_victory(terminal, pack, seed, memory))
                    try:
                        choice = (_input("Choice: ") or "").strip().casefold()
                    except (EOFError, KeyboardInterrupt):
                        _print("The delve waits for another time.")
                        return 0
                    if choice in ("r", "retry"):
                        seed += 1
                        retry = True
                    else:
                        return 0
                    break
            except Exception:
                # A malformed or surprising input must not terminate ordinary play.
                _print("That command could not be resolved. Type ? for help.")
        if not retry:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
