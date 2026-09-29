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
    files = sorted(path for directory in (root / "dnd_combat", root / "playtest")
                   for path in directory.rglob("*.py") if path.is_file())
    manifest = []
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix()
        content = path.read_bytes()
        digest.update(relative.encode("utf-8") + b"\0" + content + b"\0")
        manifest.append({"path": relative, "sha256": _sha(content)})
    return {"sha256": digest.hexdigest(), "files": manifest}


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
              effort="medium", prompt_path=None, persona_text=None, golem_cmd=None,
              seed=41, name="Ada", character="fighter", turn_cap=35,
              timeout=1800, retry_count=0, event_log=None):
    """Create a canonical session and dispatch a player through an isolated file capsule."""
    session_dir, run_dir = Path(session_dir).resolve(), Path(run_dir).resolve()
    if type(retry_count) is not int or retry_count not in (0, 1):
        raise ValueError("retry_count must be 0 or 1; retries require an explicit receipted invocation")
    repo_root = Path(__file__).resolve().parent.parent
    run_dir.mkdir(parents=True, exist_ok=True)
    capsule = run_dir / "capsule"
    if capsule.exists():
        shutil.rmtree(capsule)
    if capsule == repo_root or repo_root in capsule.parents or capsule == session_dir or session_dir in capsule.parents:
        raise ValueError("capsule must not be inside repository root or canonical session directory")
    capsule.mkdir(parents=True, mode=0o700)
    capsule.chmod(0o700)
    for directory in ("inbox", "outbox"):
        (capsule / directory).mkdir(mode=0o700)
    journal_path = capsule / "journal.jsonl"
    journal_path.touch(mode=0o600)
    nonce = secrets.token_hex(32)
    playctl_path = capsule / "playctl"
    playctl_path.write_text(_playctl_source(repo_root, capsule / "inbox", capsule / "outbox", journal_path, nonce), encoding="utf-8")
    playctl_path.chmod(0o700)
    prompt = build_prompt(persona_text if persona_text is not None else persona, turn_cap)
    prompt_hash = _sha(prompt)
    actual_prompt_file = Path(prompt_path).resolve() if prompt_path else run_dir / "prompt.txt"
    if not prompt_path:
        actual_prompt_file.write_text(prompt, encoding="utf-8")
    else:
        # File may contain sealed text. It is consumed in memory and never copied into the receipt.
        prompt = actual_prompt_file.read_text(encoding="utf-8") + "\n\n" + build_prompt(persona_text or persona, turn_cap)
        prompt_hash = _sha(prompt)
        actual_prompt_file = run_dir / "dispatch_prompt.txt"
        actual_prompt_file.write_text(prompt, encoding="utf-8")
    argv = list(golem_cmd) if golem_cmd is not None else codex_golem_argv(model, effort, actual_prompt_file)
    game_manifest_start = _game_manifest()
    receipt = {"prompt_sha256": prompt_hash, "prompt_path_sha256": _sha(str(actual_prompt_file)),
               "golem_argv": argv, "model": model, "effort": effort, "sandbox_policy": SANDBOX_POLICY,
               "start_wall_time": time.time(), "end_wall_time": None, "exit_code": None,
               "timeout": False, "retry_count": retry_count, "stdout_sha256": None,
               "stderr_sha256": None, "journal_sha256": None, "transcript_head_chain_hash": None,
               "game_sha": game_manifest_start["sha256"], "game_manifest_start": game_manifest_start,
               "harness_sha": _sha((repo_root / "playtest/harness.py").read_bytes()),
               "final_game_harness_sha": _sha((repo_root / "dnd_combat/adventure.py").read_bytes() + (repo_root / "playtest/harness.py").read_bytes()),
               "outcome": "INCOMPLETE_DISPATCH", "turns_taken": 0, "termination": None}
    (run_dir / "run_receipt.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    # The CLI owns setup/replay and writes all artifacts outside the capsule.
    if retry_count == 1 and (session_dir / "transcript.jsonl").exists():
        # Explicit same-session retry: resume from the latest controller-authored output.
        initial = load_transcript(session_dir / "transcript.jsonl")[-1]
    else:
        code, _, setup_error = _run_play(["new", "--seed", str(seed), "--name", name, "--class", character,
                                          "--persona", persona, "--session", str(session_dir)])
        if code:
            receipt.update(outcome="ERROR", end_wall_time=time.time(), exit_code=code)
            (run_dir / "run_receipt.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
            raise RuntimeError(setup_error or "could not initialize session")
        initial = load_transcript(session_dir / "transcript.jsonl")[-1]
    for entry in (capsule / "outbox").iterdir():
        if entry.is_dir() and not entry.is_symlink(): shutil.rmtree(entry)
        else: entry.unlink()
    _atomic_json(capsule / "outbox" / "0000.json", {"output": initial["new_output"], "turn": 0, "terminated": None,
                                                       "request_id": "0000"})
    events = []
    out_capture, err_capture = (run_dir / "stdout.log").open("wb"), (run_dir / "stderr.log").open("wb")
    started = time.monotonic()
    prompt_stream = actual_prompt_file.open("rb")
    child = subprocess.Popen(argv, cwd=capsule, stdin=prompt_stream, stdout=out_capture,
                             stderr=err_capture, close_fds=True, start_new_session=True)
    prompt_stream.close()
    turn, no_progress, termination, timed_out = 0, 0, None, False
    processed = set()
    try:
        while True:
            if time.monotonic() - started > timeout:
                timed_out = True; termination = "timeout"; break
            pending = sorted((capsule / "inbox").glob("[0-9][0-9][0-9][0-9].json"))
            for inbox in pending:
                if inbox.name in processed:
                    continue
                processed.add(inbox.name)
                try:
                    request = json.loads(inbox.read_text(encoding="utf-8"))
                    frame = request["inputs"]
                    request_id = inbox.stem
                    if request.get("request_id") != request_id:
                        raise ValueError("request identity mismatch")
                    if not isinstance(frame, list) or any(not isinstance(x, str) for x in frame): raise ValueError("invalid input frame")
                    turn += 1
                    before = load_transcript(session_dir / "transcript.jsonl")[-1]["snapshot"]
                    code, output, error = _run_play(["step", "--session", str(session_dir), "--inputs-json", json.dumps(frame, ensure_ascii=False)])
                    rows = load_transcript(session_dir / "transcript.jsonl")
                    record = rows[-1]
                    after = record["snapshot"]
                    no_progress = no_progress + 1 if before.get("canonical_state_hash") == after.get("canonical_state_hash") and before.get("room_id") == after.get("room_id") else 0
                    if after.get("game_state") == "won": termination = "won"
                    elif after.get("game_state") == "dead": termination = "dead"
                    elif code: termination = "dead" if record["termination"] == "dead" else "stalled"
                    elif no_progress >= 3: termination = "stalled"
                    elif turn >= turn_cap: termination = "cap"
                    _controller_reply(capsule / "outbox" / inbox.name,
                                      {"output": output, "turn": turn, "terminated": termination,
                                       "request_id": request_id, "nonce": nonce})
                    if termination:
                        # A dispatched player may ignore the terminal response; the controller owns stop policy.
                        break
                except Exception as exc:
                    try:
                        _controller_reply(capsule / "outbox" / inbox.name,
                                          {"output": str(exc), "turn": turn, "terminated": "stalled",
                                           "request_id": inbox.stem, "nonce": nonce})
                    except FileExistsError:
                        pass
                    termination = "stalled"; break
            if termination:
                break
            status = child.poll()
            if status is not None:
                # Drain any final queued frame before exiting; otherwise dispatch is complete.
                if not any(p.name not in processed for p in (capsule / "inbox").glob("[0-9][0-9][0-9][0-9].json")):
                    break
            time.sleep(.025)
        _stop_process_group(child)
    finally:
        _stop_process_group(child)
        out_capture.close(); err_capture.close()
    # Freeze controller-owned capsule artifacts after all members of the golem process group
    # have been reaped. This bounds accidental descendants; same-user actors can still alter
    # arbitrary local files and are outside this capsule boundary.
    (capsule / "CLOSED").write_text("closed\n", encoding="utf-8")
    for path in (capsule / "inbox", capsule / "outbox"):
        for item in path.iterdir():
            if item.is_file() and not item.is_symlink(): item.chmod(0o400)
        path.chmod(0o500)
    journal_path.chmod(0o400)
    (capsule / "CLOSED").chmod(0o400)
    playctl_path.chmod(0o500)
    capsule.chmod(0o500)
    if event_log is not None:
        event_path = Path(event_log)
        if event_path.exists():
            for line in event_path.read_text(encoding="utf-8").splitlines():
                try: events.append(json.loads(line))
                except json.JSONDecodeError: events.append(line)
    else:
        for line in (run_dir / "stdout.log").read_text(encoding="utf-8", errors="replace").splitlines():
            try: events.append(json.loads(line))
            except json.JSONDecodeError: pass
    hits = audit_commands(events, capsule, session_dir)
    rows = load_transcript(session_dir / "transcript.jsonl")
    stdout_data, stderr_data = (run_dir / "stdout.log").read_bytes(), (run_dir / "stderr.log").read_bytes()
    game_manifest_end = _game_manifest()
    receipt.update(end_wall_time=time.time(), exit_code=child.returncode,
                   timeout=timed_out, stdout_sha256=_sha(stdout_data), stderr_sha256=_sha(stderr_data),
                   journal_sha256=_sha(journal_path.read_bytes()), transcript_head_chain_hash=rows[-1]["chain_hash"],
                   game_manifest_end=game_manifest_end,
                   final_game_harness_sha=game_manifest_end["sha256"],
                   turns_taken=turn, termination=termination,
                   audit_events_seen=len(events),
                   receipt_finalized_after_child_exit=True,
                   outcome=("GAME_MODIFIED_DURING_RUN" if game_manifest_start != game_manifest_end else
                            "INCOMPLETE_DISPATCH" if timed_out else
                            "BLINDNESS_VIOLATED" if hits else
                            "AUDIT_UNVERIFIABLE" if event_log is None and child.returncode is not None and not events else "COMPLETE"),
                   blindness_hits=hits)
    (run_dir / "run_receipt.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return receipt
