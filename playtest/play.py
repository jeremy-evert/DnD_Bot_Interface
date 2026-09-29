"""Controller CLI for deterministic, real-game playtest sessions."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys

from . import harness
from .schema import (SCHEMA_VERSION, SEVERITY_TAXONOMY_VERSION, canonical_json, content_catalog, git_revision,
                     manifest_digest, source_manifest, strict_json_loads,
                     validate_manifest)
from .transcript import ReplayDivergence, TranscriptWriter, load_transcript


def _digest(data):
    if isinstance(data, str): data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _read_manifest(session_dir):
    manifest = strict_json_loads((session_dir / "manifest.json").read_text(encoding="utf-8"))
    marker = validate_manifest(manifest)
    if marker: raise ValueError("legacy session cannot be extended by the v2 play CLI")
    return manifest


def _append_frame(session_dir, calls):
    with (session_dir / "frames.jsonl").open("a", encoding="utf-8", newline="") as target:
        target.write(canonical_json({"input_calls": calls}) + "\n")
        target.flush(); os.fsync(target.fileno())


def _read_frames(session_dir):
    frames = []
    with (session_dir / "frames.jsonl").open(encoding="utf-8") as source:
        for number, line in enumerate(source, 1):
            try: frame = strict_json_loads(line)
            except (ValueError, json.JSONDecodeError) as exc: raise ValueError(f"invalid frame history line {number}") from exc
            if (not isinstance(frame, dict) or set(frame) != {"input_calls"} or
                    not isinstance(frame["input_calls"], list) or
                    any(not isinstance(call, str) for call in frame["input_calls"])):
                raise ValueError(f"invalid frame history line {number}")
            frames.append(frame["input_calls"])
    return frames


def _record(writer, manifest, calls, frame_kind, turn_id, full_output, result):
    witness = result.witness
    state = harness.snapshot(witness) if witness is not None else {}
    termination = ("error" if result.error else
                   state.get("game_state") if state.get("game_state") in {"won", "dead"} else "playing")
    previous = load_transcript(writer.path) if writer.path.exists() else []
    prior_output = "".join(entry["new_output"] for entry in previous)
    if not full_output.startswith(prior_output): raise ReplayDivergence("REPLAY_DIVERGENCE: replay output changed its previous prefix")
    return writer.append_verified({
        "schema_version": SCHEMA_VERSION, "run_id": manifest["run_id"],
        "manifest_sha256": manifest["manifest_sha256"], "frame_kind": frame_kind,
        "turn_id": turn_id, "frame_id": turn_id, "input_calls": calls,
        "new_output": full_output[len(prior_output):], "full_output": full_output,
        "full_output_sha256": _digest(full_output), "snapshot": state,
        "termination": termination, "game_sha": manifest["game_sha"],
        "harness_sha": manifest["harness_sha"],
    }), termination


def _new(args):
    session_dir = Path(args.session)
    session_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = session_dir / "manifest.json"
    # Session paths need not be inside the checkout; source identity is rooted at this module.
    from pathlib import Path as _Path
    repo_root = _Path(__file__).resolve().parent.parent
    game, harness_source = source_manifest(repo_root, "game"), source_manifest(repo_root, "harness")
    setup_calls = [args.name, args.character]
    result = harness.replay(args.seed, setup_calls)
    if result.error:
        print(f"game error: {result.error}", file=sys.stderr); return 2
    run_id = args.run_id or secrets.token_hex(16)
    prompt_text = args.persona_prompt
    prompt_hash = _digest(prompt_text)
    is_holdout = args.is_holdout == "true"
    holdout_hash = args.holdout_prompt_sha256
    if is_holdout:
        holdout_hash = holdout_hash or prompt_hash
    elif holdout_hash is not None:
        raise ValueError("public session cannot carry holdout prompt identity")
    snapshot = harness.snapshot(result.witness)
    manifest = {
        "schema_version": SCHEMA_VERSION, "run_id": run_id,
        "session_id": args.session_id, "persona_id": args.persona,
        "persona_prompt_sha256": prompt_hash, "seed": args.seed,
        "is_holdout": is_holdout, "holdout_prompt_sha256": holdout_hash,
        "narrator_policy": "plain", "turn_policy": "action_frames_v1",
        "turn_cap": args.turn_cap, "measurement_policy": args.measurement_policy,
        "severity_taxonomy_version": SEVERITY_TAXONOMY_VERSION,
        "game_revision": git_revision(repo_root), "harness_revision": git_revision(repo_root),
        "game_files": game["files"], "harness_files": harness_source["files"],
        "game_sha": game["sha256"], "harness_sha": harness_source["sha256"],
        "manifest_sha256": "", "name": args.name, "character_class": args.character,
        "created_by": "controller", "created_at": datetime.now(timezone.utc).isoformat(),
        "content_catalog": content_catalog(snapshot),
    }
    manifest["manifest_sha256"] = manifest_digest(manifest)
    try:
        with manifest_path.open("x", encoding="utf-8", newline="") as target:
            target.write(canonical_json(manifest) + "\n")
    except FileExistsError:
        print("session manifest already exists", file=sys.stderr); return 2
    try:
        validate_manifest(manifest)
        writer = TranscriptWriter(session_dir)
        _record(writer, manifest, setup_calls, "setup", 0, result.output, result)
        _append_frame(session_dir, setup_calls)
        return 0
    except (ValueError, ReplayDivergence) as exc:
        print(str(exc), file=sys.stderr); return 2


def _step(args):
    session_dir = Path(args.session)
    try:
        manifest = _read_manifest(session_dir)
        writer = TranscriptWriter(session_dir)
        previous = load_transcript(writer.path)
        if not previous: raise ValueError("session has no initial transcript frame")
        if previous[-1]["termination"] in {"won", "dead", "error"}:
            print("session has ended", file=sys.stderr); return 3
        calls = strict_json_loads(args.inputs_json)
        if not isinstance(calls, list) or any(not isinstance(call, str) for call in calls): raise ValueError("--inputs-json must be a JSON array of strings")
        action_count = sum(record["frame_kind"] == "action" for record in previous)
        if action_count >= manifest["turn_cap"]: raise ValueError("turn cap already reached")
        frames = _read_frames(session_dir) + [calls]
        result = harness.replay(manifest["seed"], [manifest["name"], manifest["character_class"],
                                                   *[call for frame in frames[1:] for call in frame]])
        if result.error: raise ValueError(f"game error: {result.error}")
        prior_output = "".join(record["new_output"] for record in previous)
        if not result.output.startswith(prior_output): raise ReplayDivergence("REPLAY_DIVERGENCE: replay output changed its previous prefix")
        record, _ = _record(writer, manifest, calls, "action", action_count + 1, result.output, result)
        _append_frame(session_dir, calls)
        sys.stdout.write(record["new_output"]); sys.stdout.flush()
        return 0
    except ReplayDivergence as exc:
        print(str(exc), file=sys.stderr); return 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"playtest error: {exc}", file=sys.stderr); return 2


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m playtest.play")
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("new")
    new.add_argument("--seed", required=True, type=int); new.add_argument("--name", required=True)
    new.add_argument("--class", dest="character", required=True, choices=("fighter", "rogue", "wizard"))
    new.add_argument("--persona", required=True); new.add_argument("--session", required=True)
    new.add_argument("--run-id"); new.add_argument("--session-id", required=True); new.add_argument("--persona-prompt", required=True)
    new.add_argument("--turn-cap", type=int, default=35)
    new.add_argument("--measurement-policy", choices=("detector_only", "detector_and_judge"), default="detector_only")
    new.add_argument("--is-holdout", choices=("true", "false"), required=True); new.add_argument("--holdout-prompt-sha256")
    new.set_defaults(handler=_new)
    step = commands.add_parser("step"); step.add_argument("--session", required=True); step.add_argument("--inputs-json", required=True)
    step.set_defaults(handler=_step)
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__": raise SystemExit(main())
