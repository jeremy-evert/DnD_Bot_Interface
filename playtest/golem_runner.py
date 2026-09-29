"""File-IPC golem dispatch. Reads are not sandbox-enforced here; event logs are audited."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import stat
import shutil
import subprocess
import time

from . import harness
from .golem_prompt import build_prompt
from .play import main as play_main
from .schema import (SCHEMA_VERSION, canonical_json, git_revision, source_manifest,
                     strict_json_loads, validate_run_receipt)
from .transcript import load_transcript

SANDBOX_POLICY = "workspace-write; capsule-only cwd; read access is not restricted and is audited"
TERMINATIONS = {"won", "dead", "cap", "stalled", "timeout"}


def _sha(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def codex_golem_argv(model, effort, prompt_path):
    # prompt_path is recorded as a hash by the receipt; stdin is redirected by the runner.
    return ["codex", "exec", "-m", model, "-c", f"model_reasoning_effort={effort}",
            "-s", "workspace-write", "--json", "--skip-git-repo-check", "-"]


def validate_journal(entry):
    fields = {"turn_id", "wanted", "surprise", "continue", "reason", "unsupported_intent"}
    if not isinstance(entry, dict) or set(entry) != fields:
        raise ValueError("journal entry fields must be exactly " + ", ".join(sorted(fields)))
    if type(entry["turn_id"]) is not int or entry["turn_id"] < 1:
        raise ValueError("journal.turn_id must be a positive integer")
    for key in ("wanted", "surprise", "reason"):
        if not isinstance(entry[key], str):
            raise ValueError(f"journal.{key} must be a string")
    if type(entry["continue"]) is not int or entry["continue"] not in (0, 1):
        raise ValueError("journal.continue must be 0 or 1")
    if entry["unsupported_intent"] is not None and not isinstance(entry["unsupported_intent"], str):
        raise ValueError("journal.unsupported_intent must be a string or null")
    return entry


def audit_commands(events, capsule_path=None, session_path=None):
    """Return forbidden event hits. Capsule/playctl references are allowed."""
    forbidden = ("dnd_combat", "DnD_Bot_Interface", "playtest/", "transcript.jsonl",
                 "manifest.json", "frames.jsonl", ".git", "/mnt/nora")
    capsule = str(Path(capsule_path).resolve()) if capsule_path else ""
    session = str(Path(session_path).resolve()) if session_path else ""
    hits = []
    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for key, item in value.items():
                yield from strings(key)
                yield from strings(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                yield from strings(item)
    for event in events:
        raw = event if isinstance(event, str) else json.dumps(event, sort_keys=True)
        candidates = list(strings(event)) or [raw]
        for fragment in (*forbidden, *((session,) if session else ())):
            found = False
            for candidate in candidates:
                scrubbed = candidate.replace(capsule, "<capsule>") if capsule else candidate
                scrubbed = scrubbed.replace("playctl", "<playctl>")
                if session:
                    scrubbed = scrubbed.replace(session, "<session>")
                if fragment and fragment in scrubbed:
                    found = True
                    break
            if found:
                hits.append({"fragment": fragment, "event": raw})
    return hits


def _atomic_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _controller_reply(path, value):
    """Publish a reply only when its destination is an unused regular-file path."""
    try:
        path.lstat()
    except FileNotFoundError:
        pass
    else:
        raise FileExistsError(f"reply path already exists: {path.name}")
    temporary = path.with_name(path.name + ".controller-" + secrets.token_hex(8) + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(temporary, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    # Same-user hostile replacement races are outside the stated threat model.
    if path.is_symlink() or path.exists():
        temporary.unlink(missing_ok=True)
        raise FileExistsError(f"reply path appeared during write: {path.name}")
    os.replace(temporary, path)


def _stop_process_group(child):
    """Kill and reap the golem process group so ordinary spawned descendants cannot write later."""
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    if child.poll() is None:
        child.wait()
    else:
        child.wait()


def _game_manifest():
    """Hash sorted Python source paths and contents; this detects ordinary run-time edits.

    It is not an external trust anchor: an actor able to rewrite the checkout and receipt
    storage together can rewrite this evidence too.
    """
    root = Path(__file__).resolve().parent.parent
    return {"game": source_manifest(root, "game"),
            "harness": source_manifest(root, "harness")}


def _run_play(args):
    from contextlib import redirect_stdout, redirect_stderr
    import io
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = play_main(args)
    return code, out.getvalue(), err.getvalue()


def _playctl_source(repo_root=None, inbox=None, outbox=None, journal=None, nonce=""):
    return f'''#!/usr/bin/env python3
import json, os, sys, time, stat
from pathlib import Path
CAPSULE = Path(__file__).resolve().parent
INBOX, OUTBOX, JOURNAL = CAPSULE / "inbox", CAPSULE / "outbox", CAPSULE / "journal.jsonl"
NONCE = {nonce!r}
CLOSED = CAPSULE / "CLOSED"
def validate_journal(entry):
    fields = {{"turn_id", "wanted", "surprise", "continue", "reason", "unsupported_intent"}}
    if not isinstance(entry, dict) or set(entry) != fields:
        raise ValueError("journal entry fields must be exactly " + ", ".join(sorted(fields)))
    if type(entry["turn_id"]) is not int or entry["turn_id"] < 1:
        raise ValueError("journal.turn_id must be a positive integer")
    for key in ("wanted", "surprise", "reason"):
        if not isinstance(entry[key], str):
            raise ValueError(f"journal.{{key}} must be a string")
    if type(entry["continue"]) is not int or entry["continue"] not in (0, 1):
        raise ValueError("journal.continue must be 0 or 1")
    if entry["unsupported_intent"] is not None and not isinstance(entry["unsupported_intent"], str):
        raise ValueError("journal.unsupported_intent must be a string or null")
    return entry
def atomic(path, value):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, sort_keys=True, ensure_ascii=False) + "\\n", encoding="utf-8")
    os.replace(tmp, path)
def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("step", "journal"):
        return 2
    try:
        if CLOSED.exists(): return 2
        value = json.loads(sys.argv[2])
        if sys.argv[1] == "journal":
            validate_journal(value)
            with JOURNAL.open("a", encoding="utf-8") as f:
                f.write(json.dumps(value, sort_keys=True, ensure_ascii=False) + "\\n")
                f.flush(); os.fsync(f.fileno())
            return 0
        if not isinstance(value, list) or not value or any(not isinstance(x, str) for x in value):
            return 2
        number = 1
        while True:
            target = INBOX / (f"{{number:04d}}.json")
            try:
                fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                break
            except FileExistsError:
                number += 1
        request_id = target.stem
        payload = json.dumps({{"inputs": value, "request_id": request_id}}, sort_keys=True, ensure_ascii=False) + "\\n"
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        reply = OUTBOX / target.name
        deadline = time.monotonic() + 180
        while not reply.exists():
            if CLOSED.exists(): return 2
            if time.monotonic() >= deadline: return 2
            time.sleep(.05)
        info = reply.lstat()
        if not stat.S_ISREG(info.st_mode): return 2
        result = json.loads(reply.read_text(encoding="utf-8"))
        if result.get("request_id") != request_id or result.get("nonce") != NONCE: return 2
        sys.stdout.write(result["output"]); sys.stdout.flush()
        return 3 if result["terminated"] is not None else 0
    except (ValueError, OSError, KeyError, TypeError):
        return 2
if __name__ == "__main__": raise SystemExit(main())
'''


def run_golem(session_dir, run_dir, *, persona="explorer", model="gpt-6-luna",
              effort="medium", prompt_path=None, persona_text=None, persona_prompt_text=None,
              is_holdout=None, holdout_prompt_text=None, measurement_policy="detector_and_judge",
              golem_cmd=None, seed=41, name="Ada", character="fighter", turn_cap=35,
              timeout=1800, retry_count=0, retry_of=None, run_id=None, session_id=None,
              event_log=None, final_ack_grace=1.0):
    """Run a controller-owned dispatch and finalize its v2 receipt after child exit."""
    session_dir, run_dir = Path(session_dir).resolve(), Path(run_dir).resolve()
    if type(retry_count) is not int or retry_count not in (0, 1): raise ValueError("retry_count must be 0 or 1")
    if type(turn_cap) is not int or turn_cap <= 0: raise ValueError("turn_cap must be positive")
    if type(is_holdout) is not bool: raise ValueError("is_holdout must be explicit bool")
    if persona_prompt_text is None and persona_text is None: raise ValueError("persona_prompt_text must be supplied explicitly")
    if retry_count and not retry_of: raise ValueError("retry requires retry_of")
    repo_root = Path(__file__).resolve().parent.parent
    run_dir.mkdir(parents=True, exist_ok=True)
    capsule = run_dir / "capsule"
    if capsule.exists(): shutil.rmtree(capsule)
    if capsule == repo_root or repo_root in capsule.parents or capsule == session_dir or session_dir in capsule.parents:
        raise ValueError("capsule must not be inside repository root or canonical session directory")
    capsule.mkdir(parents=True, mode=0o700); capsule.chmod(0o700)
    for directory in ("inbox", "outbox"): (capsule / directory).mkdir(mode=0o700)
    journal_path = capsule / "journal.jsonl"; journal_path.touch(mode=0o600)
    nonce = secrets.token_hex(32)
    playctl_path = capsule / "playctl"
    playctl_path.write_text(_playctl_source(repo_root, capsule / "inbox", capsule / "outbox", journal_path, nonce), encoding="utf-8")
    playctl_path.chmod(0o700)
    run_id = run_id or secrets.token_hex(16); session_id = session_id or secrets.token_hex(16)
    persona_prompt_text = persona_prompt_text if persona_prompt_text is not None else persona_text
    persona_prompt_sha = _sha(persona_prompt_text)
    if is_holdout:
        if holdout_prompt_text is not None and _sha(holdout_prompt_text) != persona_prompt_sha: raise ValueError("holdout/persona prompt hashes differ")
        holdout_sha = _sha(holdout_prompt_text if holdout_prompt_text is not None else persona_prompt_text)
    else:
        if holdout_prompt_text is not None: raise ValueError("public runs cannot receive holdout text")
        holdout_sha = None
    prompt = build_prompt(persona_text if persona_text is not None else persona, turn_cap)
    if prompt_path:
        prompt = Path(prompt_path).read_text(encoding="utf-8") + "\n\n" + prompt
    prompt_hash = _sha(prompt)
    actual_prompt_file = run_dir / "prompt.txt"; actual_prompt_file.write_text(prompt, encoding="utf-8")
    argv = list(golem_cmd) if golem_cmd is not None else codex_golem_argv(model, effort, actual_prompt_file)
    start = _game_manifest(); revision = git_revision(repo_root)
    measurement = measurement_policy
    code, _, setup_error = _run_play(["new", "--seed", str(seed), "--name", name, "--class", character,
        "--persona", persona, "--session", str(session_dir), "--run-id", run_id, "--session-id", session_id,
        "--persona-prompt", persona_prompt_text, "--turn-cap", str(turn_cap), "--measurement-policy", measurement,
        "--is-holdout", str(is_holdout).lower(),
        *( ["--holdout-prompt-sha256", holdout_sha] if is_holdout else [])])
    if code: raise RuntimeError(setup_error or "could not initialize session")
    manifest = strict_json_loads((session_dir / "manifest.json").read_text(encoding="utf-8"))
    initial = load_transcript(session_dir / "transcript.jsonl")[-1]
    for entry in (capsule / "outbox").iterdir(): entry.unlink()
    _atomic_json(capsule / "outbox" / "0000.json", {"output": initial["new_output"], "turn": 0,
        "terminated": None, "request_id": "0000"})
    out_capture, err_capture = (run_dir / "stdout.log").open("wb"), (run_dir / "stderr.log").open("wb")
    started = time.monotonic(); prompt_stream = actual_prompt_file.open("rb")
    child = subprocess.Popen(argv, cwd=capsule, stdin=prompt_stream, stdout=out_capture,
                             stderr=err_capture, close_fds=True, start_new_session=True)
    prompt_stream.close()
    turns, no_progress = 0, 0
    game_termination, stop_reason = "playing", None
    timed_out, protocol_error, controller_stop = False, False, False
    processed, events = set(), []
    try:
        while True:
            if time.monotonic() - started > timeout:
                timed_out, stop_reason = True, "timeout"; break
            pending = sorted((capsule / "inbox").glob("[0-9][0-9][0-9][0-9].json"))
            for inbox in pending:
                if inbox.name in processed: continue
                processed.add(inbox.name)
                try:
                    request = strict_json_loads(inbox.read_text(encoding="utf-8"))
                    frame, request_id = request["inputs"], inbox.stem
                    if request.get("request_id") != request_id: raise ValueError("request identity mismatch")
                    if not isinstance(frame, list) or not frame or any(not isinstance(x, str) for x in frame): raise ValueError("invalid input frame")
                    if turns >= turn_cap: raise ValueError("turn cap exceeded")
                    before = load_transcript(session_dir / "transcript.jsonl")[-1]["snapshot"]
                    code, output, error = _run_play(["step", "--session", str(session_dir), "--inputs-json", json.dumps(frame, ensure_ascii=False)])
                    if code:
                        game_termination, stop_reason = "error", "game_error"
                        _controller_reply(capsule / "outbox" / inbox.name, {"output": error or "play step failed",
                            "turn": turns, "terminated": stop_reason, "request_id": request_id, "nonce": nonce})
                        break
                    rows = load_transcript(session_dir / "transcript.jsonl"); record = rows[-1]
                    after = record["snapshot"]; turns += 1
                    no_progress = no_progress + 1 if before.get("canonical_state_hash") == after.get("canonical_state_hash") and before.get("room_id") == after.get("room_id") else 0
                    if after.get("game_state") == "won": game_termination, stop_reason = "won", "won"
                    elif after.get("game_state") == "dead": game_termination, stop_reason = "dead", "dead"
                    elif no_progress >= 3: stop_reason = "no_progress"
                    elif turns >= turn_cap: stop_reason = "cap"
                    _controller_reply(capsule / "outbox" / inbox.name, {"output": output, "turn": turns,
                        "terminated": stop_reason, "request_id": request_id, "nonce": nonce})
                    if stop_reason: controller_stop = True; break
                except Exception as exc:
                    protocol_error = True; stop_reason = "ipc_error"
                    try: _controller_reply(capsule / "outbox" / inbox.name, {"output": str(exc), "turn": turns,
                        "terminated": "ipc_error", "request_id": inbox.stem, "nonce": nonce})
                    except FileExistsError: pass
                    break
            if stop_reason: break
            status = child.poll()
            if status is not None:
                if not any(p.name not in processed for p in (capsule / "inbox").glob("[0-9][0-9][0-9][0-9].json")):
                    stop_reason = "child_exit_error" if status else "premature_exit"
                    break
            time.sleep(.025)
        if controller_stop:
            try: child.wait(timeout=final_ack_grace)
            except subprocess.TimeoutExpired: _stop_process_group(child)
        else: _stop_process_group(child)
    finally:
        _stop_process_group(child); out_capture.close(); err_capture.close()
    (capsule / "CLOSED").write_text("closed\n", encoding="utf-8")
    for path in (capsule / "inbox", capsule / "outbox"):
        for item in path.iterdir():
            if item.is_file() and not item.is_symlink(): item.chmod(0o400)
        path.chmod(0o500)
    journal_path.chmod(0o400); (capsule / "CLOSED").chmod(0o400); playctl_path.chmod(0o500); capsule.chmod(0o500)
    event_path = Path(event_log) if event_log is not None else run_dir / "stdout.log"
    event_bytes = event_path.read_bytes() if event_path.exists() else b""
    (run_dir / "audit.log").write_bytes(event_bytes)
    for line in event_bytes.decode("utf-8", "replace").splitlines():
        try: events.append(strict_json_loads(line))
        except (ValueError, json.JSONDecodeError): events.append(line)
    recognized_types = {"item.completed", "item.started", "turn.completed", "response.completed",
                        "session.created", "thread.started", "command", "tool_call"}
    recognized = bool(events) and any(isinstance(event, dict) and event.get("type") in recognized_types for event in events)
    hits = audit_commands(events, capsule, session_dir)
    rows = load_transcript(session_dir / "transcript.jsonl")
    stdout_data, stderr_data = (run_dir / "stdout.log").read_bytes(), (run_dir / "stderr.log").read_bytes()
    journal_bytes = journal_path.read_bytes()
    try:
        journal_rows = [strict_json_loads(line) for line in journal_bytes.decode("utf-8").splitlines() if line]
        for item in journal_rows: validate_journal(item)
        journal_consistent = len(journal_rows) == turns and [item["turn_id"] for item in journal_rows] == list(range(1, turns + 1))
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        journal_rows, journal_consistent = [], False
    end = _game_manifest()
    audit_status = "VIOLATED" if hits else "CLEAN" if recognized else "UNVERIFIABLE"
    if start["game"] != end["game"] or start["harness"] != end["harness"]: outcome = "GAME_MODIFIED_DURING_RUN"
    elif hits: outcome = "BLINDNESS_VIOLATED"
    elif not recognized: outcome = "AUDIT_UNVERIFIABLE"
    elif timed_out or protocol_error or stop_reason in {"child_exit_error", "premature_exit", "ipc_error"}: outcome = "INCOMPLETE_DISPATCH"
    elif stop_reason not in {"won", "dead", "cap", "no_progress", "player_stop"}: outcome = "INCOMPLETE_DISPATCH"
    elif child.returncode != 0 and not (controller_stop and child.returncode == -signal.SIGKILL): outcome = "INCOMPLETE_DISPATCH"
    elif not journal_consistent: outcome = "INCOMPLETE_DISPATCH"
    else: outcome = "COMPLETE"
    receipt = {
        "schema_version": SCHEMA_VERSION, "run_id": run_id, "session_id": session_id,
        "manifest_sha256": manifest["manifest_sha256"], "game_revision": revision,
        "harness_revision": revision, "game_files_start": start["game"]["files"],
        "harness_files_start": start["harness"]["files"], "game_sha": start["game"]["sha256"],
        "harness_sha": start["harness"]["sha256"], "game_files_end": end["game"]["files"],
        "harness_files_end": end["harness"]["files"], "game_sha_end": end["game"]["sha256"],
        "harness_sha_end": end["harness"]["sha256"], "persona_id": persona,
        "persona_prompt_sha256": persona_prompt_sha, "seed": seed, "is_holdout": is_holdout,
        "holdout_prompt_sha256": holdout_sha, "narrator_policy": "plain",
        "turn_policy": "action_frames_v1", "turn_cap": turn_cap,
        "measurement_policy": measurement,
        "severity_taxonomy_version": manifest["severity_taxonomy_version"], "retry_of": retry_of,
        "receipt_finalized_after_child_exit": child.poll() is not None,
        "controller_stop": controller_stop, "exit_code": child.returncode, "timeout": timed_out,
        "stop_reason": stop_reason or "premature_exit", "termination": game_termination,
        "run_outcome": outcome, "turns": turns, "transcript_record_count": len(rows),
        "journal_record_count": len(journal_rows), "journal_consistent": journal_consistent,
        "transcript_head_chain_hash": rows[-1]["chain_hash"], "stdout_sha256": _sha(stdout_data),
        "stderr_sha256": _sha(stderr_data), "journal_sha256": _sha(journal_bytes),
        "audit_log_sha256": _sha(event_bytes), "audit_status": audit_status,
        "audit_events_seen": len(events), "model": model, "effort": effort,
        "prompt_sha256": prompt_hash,
    }
    validate_run_receipt(receipt)
    receipt_path = run_dir / "run_receipt.json"
    receipt_path.write_text(canonical_json(receipt) + "\n", encoding="utf-8")
    return receipt
