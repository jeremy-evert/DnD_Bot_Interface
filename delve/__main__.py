"""Single-line terminal entry point for Fast Delve."""
import argparse
from pathlib import Path
import time

from .commands import ParseProblem, parse_command
from .engine import Engine
from .pack import load_engine_ready_pack
from .render import RenderMemory, render_death, render_event, render_status, render_victory
from .state import DelveState


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
        print(f"Could not load delve pack: {exc}")
        return 2
    try:
        if args.hero_class is None:
            selected = input("Class [f]ighter/[r]ogue/[w]izard (enter = fighter): ").strip().casefold()
            hero_class = {"": "fighter", "f": "fighter", "fighter": "fighter",
                          "r": "rogue", "rogue": "rogue", "w": "wizard", "wizard": "wizard"}.get(selected, "fighter")
        else:
            hero_class = args.hero_class
    except (EOFError, KeyboardInterrupt):
        print("The delve waits for another time.")
        return 0

    while True:
        state = DelveState.new(pack, seed, hero_class, name="Delver")
        engine = Engine(pack, state)
        memory = RenderMemory()
        print(f"{pack.title} — seed {seed} — {hero_class}")
        retry = False
        while state.terminal == "playing":
            print(render_status(state, pack, memory))
            try:
                line = input("> ")
            except (EOFError, KeyboardInterrupt):
                print("The delve pauses here. Goodbye.")
                return 0
            parsed = parse_command(line, state, pack)
            if isinstance(parsed, ParseProblem):
                print(parsed.text)
                continue
            try:
                events = engine.apply(parsed)
                for event in events:
                    if event.key in ("terminal.death", "terminal.victory"):
                        continue
                    print(render_event(event, pack, seed, memory))
                if state.terminal == "dead":
                    terminal = next((e for e in events if e.key == "terminal.death"), None)
                    print(render_death(terminal, pack, seed, memory))
                    try:
                        choice = input("Choice: ").strip().casefold()
                    except (EOFError, KeyboardInterrupt):
                        print("The delve waits for another time.")
                        return 0
                    if choice in ("r", "retry"):
                        seed += 1
                        retry = True
                    else:
                        return 0
                    break
                if state.terminal == "victory":
                    terminal = next((e for e in events if e.key == "terminal.victory"), None)
                    print(render_victory(terminal, pack, seed, memory))
                    try:
                        choice = input("Choice: ").strip().casefold()
                    except (EOFError, KeyboardInterrupt):
                        print("The delve waits for another time.")
                        return 0
                    if choice in ("r", "retry"):
                        seed += 1
                        retry = True
                    else:
                        return 0
                    break
            except Exception:
                # A malformed or surprising input must not terminate ordinary play.
                print("That command could not be resolved. Type ? for help.")
        if not retry:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
