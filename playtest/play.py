"""Controller CLI for deterministic, real-game playtest sessions."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from . import harness
from .schema import SCHEMA_VERSION, validate_manifest
from .transcript import ReplayDivergence, TranscriptWriter, canonical_json, load_transcript


def _revision():
    root = Path(__file__).resolve().parent.parent
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_manifest(session_dir):
    with (session_dir / "manifest.json").open(encoding="utf-8") as source:
        manifest = json.load(source)
    validate_manifest(manifest)
    return manifest


def _append_frame(session_dir, calls):
    with (session_dir / "frames.jsonl").open("a", encoding="utf-8", newline="") as target:
        target.write(canonical_json({"input_calls": calls}) + "\n")
        target.flush()
        os.fsync(target.fileno())


def _read_frames(session_dir):
    path = session_dir / "frames.jsonl"
    frames = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            try:
                frame = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid frame history line {line_number}") from exc
            if (not isinstance(frame, dict) or set(frame) != {"input_calls"}
                    or not isinstance(frame["input_calls"], list)
                    or any(not isinstance(call, str) for call in frame["input_calls"])):
                raise ValueError(f"invalid frame history line {line_number}")
            frames.append(frame["input_calls"])
    return frames


def _record(writer, manifest, calls, run_id, turn_id, full_output, result):
    witness = result.witness
    state = harness.snapshot(witness) if witness is not None else {}
    termination = ("error" if result.error else
                   state.get("game_state") if state.get("game_state") in {"won", "dead"} else
                   "exhausted" if result.exhausted else "playing")
    previous = load_transcript(writer.path) if writer.path.exists() else []
    prior_output = "".join(entry["new_output"] for entry in previous)
    if not full_output.startswith(prior_output):
        raise ReplayDivergence("REPLAY_DIVERGENCE: replay output changed its previous prefix")
    return writer.append_verified({
        "run_id": run_id,
        "turn_id": turn_id,
        "frame_id": turn_id,
        "input_calls": calls,
        "new_output": full_output[len(prior_output):],
        "full_output": full_output,
        "full_output_sha256": _digest(full_output),
        "snapshot": state,
        "termination": termination,
        "game_sha": manifest["game_sha"],
        "harness_sha": manifest["harness_sha"],
    }), termination


def _new(args):
    session_dir = Path(args.session)
    session_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = session_dir / "manifest.json"
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_dir.name,
        "seed": args.seed,
        "persona_id": args.persona,
        "name": args.name,
        "character_class": args.character,
        "game_sha": _revision(),
        "harness_sha": _revision(),
        "narrator_policy": "plain",
        "created_by": "controller",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    # Timestamp belongs in manifest but is not part of chained transcript records.
    try:
        with manifest_path.open("x", encoding="utf-8") as target:
            target.write(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    except FileExistsError:
        print("session manifest already exists", file=sys.stderr)
        return 2
    try:
        validate_manifest(manifest)
        calls = [args.name, args.character]
        result = harness.replay(args.seed, calls)
        run_id = _digest(f"{args.seed}\0{args.name}\0{args.character}")
        writer = TranscriptWriter(session_dir)
        if result.error:
            print(f"game error: {result.error}", file=sys.stderr)
            return 2
        _record(writer, manifest, calls, run_id, 0, result.output, result)
        _append_frame(session_dir, calls)
        return 0
    except (ValueError, ReplayDivergence) as exc:
        print(str(exc), file=sys.stderr)
        return 2


def _step(args):
    session_dir = Path(args.session)
    try:
        manifest = _read_manifest(session_dir)
        writer = TranscriptWriter(session_dir)
        previous = load_transcript(writer.path)
        if not previous:
            raise ValueError("session has no initial transcript frame")
        if previous[-1]["termination"] in {"won", "dead"}:
            print("session has ended", file=sys.stderr)
            return 3
        calls = json.loads(args.inputs_json)
        if not isinstance(calls, list) or any(not isinstance(call, str) for call in calls):
            raise ValueError("--inputs-json must be a JSON array of strings")
        frames = _read_frames(session_dir) + [calls]
        all_calls = [call for frame in frames for call in frame]
        result = harness.replay(manifest["seed"], all_calls)
        if result.error:
            print(f"game error: {result.error}", file=sys.stderr)
            return 2
        prior_output = "".join(record["new_output"] for record in previous)
        if not result.output.startswith(prior_output):
            raise ReplayDivergence("REPLAY_DIVERGENCE: replay output changed its previous prefix")
        run_id = previous[0]["run_id"]
        record, termination = _record(
            writer, manifest, calls, run_id, len(previous), result.output, result
        )
        _append_frame(session_dir, calls)
        sys.stdout.write(record["new_output"])
        sys.stdout.flush()
        return 0
    except ReplayDivergence as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"playtest error: {exc}", file=sys.stderr)
        return 2


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m playtest.play")
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("new")
    new.add_argument("--seed", required=True, type=int)
    new.add_argument("--name", required=True)
    new.add_argument("--class", dest="character", required=True, choices=("fighter", "rogue", "wizard"))
    new.add_argument("--persona", required=True)
    new.add_argument("--session", required=True)
    new.set_defaults(handler=_new)
    step = commands.add_parser("step")
    step.add_argument("--session", required=True)
    step.add_argument("--inputs-json", required=True)
    step.set_defaults(handler=_step)
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
