"""Isolated, quote-gated qualitative playtest judge."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


# Definitions are copied from Opus QUALITY_VISION_OPUS.md, section 3,
# except the four existing judge modes whose definitions are from Terra's
# terra-dnd-playtest-measurement-01 plan (evidence/dossiers/terra_playtest.md).
JUDGE_MODES = {
    "FALSE_AFFORDANCE": {"definition": "A visible object/narration cue reasonably invites an action but the interface offers only generic rejection; judge must quote cue and rejection.", "severity": 3, "requires_journal": False},
    "OBSCURE_ACTIONABLE_STATE": {"definition": "Judge identifies a player-relevant changed fact not rendered or discoverable through available commands; must cite state turn and output quote.", "severity": 3, "requires_journal": False},
    "PACING_DRAG": {"definition": "Low-information turns that could be removed without losing any decision.", "severity": 2, "requires_journal": False},
    "CONSEQUENCE_OPACITY": {"definition": "An outcome depends on an earlier choice, but no rendered text bridges them.", "severity": 4, "requires_journal": False},
    "CHOICE_ILLUSION": {"definition": "Options presented as meaningfully different converge on the same possibilities.", "severity": 3, "requires_journal": False},
    "REWARD_WITHOUT_CAUSE": {"definition": "The player gains an advantage, item, or praise that no player decision caused.", "severity": 3, "requires_journal": False},
    "HOLLOW_PAYOFF": {"definition": "A choice has a real, perceivable effect, but its value is negligible relative to what it cost or promised.", "severity": 4, "requires_journal": False},
    "NEVER_CLOSED_MYSTERY": {"definition": "Text marks something as anomalous (missing, broken, wrong, silent, sealed, locked, \"no obvious...\") and no rule ever pays it off.", "severity": 4, "requires_journal": False},
    "TUTORIAL_CLIFF": {"definition": "A cluster of failed inputs at the start of the session.", "severity": 4, "requires_journal": True},
    "MENU_WALL": {"definition": "The interface frames play as a fixed verb menu, and players stop attempting anything off-menu.", "severity": 3, "requires_journal": True},
    "NARRATOR_INVENTION": {"definition": "A `DM:` line introduces an entity, number, exit, item, or capability absent from its fact packet.", "severity": 4, "requires_journal": False},
}


class JudgeParseError(ValueError):
    """Judge output did not contain one unambiguous JSON candidate list."""


def _turn_text(record):
    inputs = record.get("input_calls", [])
    rendered_inputs = json.dumps(inputs, ensure_ascii=False) if isinstance(inputs, list) else str(inputs)
    return f"[T{record['turn_id']}] INPUT: {rendered_inputs} / OUTPUT: {record['new_output']}"


def build_judge_bundle(records, journal=None, seed_order=None):
    """Return the immutable, build-blind evidence text supplied to the judge."""
    rows = list(records)
    if seed_order is not None:
        order = {turn: index for index, turn in enumerate(seed_order)}
        rows.sort(key=lambda row: order.get(row["turn_id"], len(order)))
    sections = ["PLAYTEST TRANSCRIPT\n" + "\n\n".join(_turn_text(row) for row in rows)]
    if journal is not None:
        notes = list(journal.values()) if isinstance(journal, dict) else list(journal)
        safe_notes = []
        for note in notes:
            if isinstance(note, dict):
                safe_notes.append({key: note[key] for key in ("turn_id", "wanted", "surprise", "reason", "unsupported_intent") if key in note})
            else:
                safe_notes.append(note)
        sections.append("PLAYER NOTES (UNTRUSTED; context only, never evidence; do not quote as transcript output)\n" + json.dumps(safe_notes, ensure_ascii=False, sort_keys=True))
    return "\n\n".join(sections)


def build_judge_prompt(bundle):
    modes = ", ".join(JUDGE_MODES)
    return ("Assess the transcript for concrete failure instances. Player notes, if present, are untrusted context and never evidence. "
            "Assert instances ONLY as a JSON list of objects with exactly these fields: "
            '{"mode": string, "turn_ids": [int, ...], "quote": string, "rationale": string}. '
            "The quote must be an exact substring of a cited turn's OUTPUT. Use only these modes: " + modes + ". "
            "Never give any holistic score or rating. Return [] if none. Output ONLY the JSON list.\n\n" + bundle)


def verify_candidate(records, cand):
    if not isinstance(cand, dict):
        return {"candidate": cand, "reason_code": "MALFORMED"}
    if set(cand) != {"mode", "turn_ids", "quote", "rationale"}:
        return {"candidate": cand, "reason_code": "MALFORMED"}
    if not isinstance(cand["mode"], str) or cand["mode"] not in JUDGE_MODES:
        return {"candidate": cand, "reason_code": "UNKNOWN_MODE"}
    ids = cand["turn_ids"]
    if not isinstance(ids, list) or not ids or any(type(turn) is not int for turn in ids):
        return {"candidate": cand, "reason_code": "BAD_TURN"}
    by_id = {row.get("turn_id"): row for row in records}
    if any(turn not in by_id for turn in ids):
        return {"candidate": cand, "reason_code": "BAD_TURN"}
    if not isinstance(cand["quote"], str) or not cand["quote"]:
        return {"candidate": cand, "reason_code": "EMPTY_QUOTE"}
    if not isinstance(cand["rationale"], str) or not cand["rationale"].strip():
        return {"candidate": cand, "reason_code": "MALFORMED"}
    if not any(cand["quote"] in by_id[turn].get("new_output", "") for turn in ids):
        return {"candidate": cand, "reason_code": "QUOTE_NOT_IN_CITED_TURN"}
    return None


def gate(records, candidates):
    accepted, discards = [], []
    if not isinstance(candidates, list):
        return accepted, [{"candidate": candidates, "reason_code": "MALFORMED"}]
    for candidate in candidates:
        receipt = verify_candidate(records, candidate)
        if receipt is None:
            accepted.append(candidate)
        else:
            discards.append(receipt)
    return accepted, discards


def parse_judge_output(text):
    """Parse a JSON list from fenced output or the final top-level array."""
    if not isinstance(text, str):
        raise JudgeParseError("judge output must be text")
    import re
    fences = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.I)
    for block in reversed(fences):
        try:
            value = json.loads(block.strip())
            if isinstance(value, list):
                return value
        except (json.JSONDecodeError, TypeError):
            pass
    decoder = json.JSONDecoder()
    arrays = []
    depth, start, quoted, escaped = 0, None, False, False
    for index, char in enumerate(text):
        if quoted:
            if escaped: escaped = False
            elif char == "\\": escaped = True
            elif char == '"': quoted = False
            continue
        if char == '"': quoted = True
        elif char == "[":
            if depth == 0: start = index
            depth += 1
        elif char == "]" and depth:
            depth -= 1
            if depth == 0:
                try:
                    value, end = decoder.raw_decode(text[start:index + 1])
                    if isinstance(value, list) and end == index + 1 - start:
                        arrays.append(value)
                except json.JSONDecodeError:
                    pass
    if arrays:
        return arrays[-1]
    raise JudgeParseError("no valid top-level JSON array found")


def codex_judge_argv(model, effort):
    return ["codex", "exec", "-m", model, "-c", f"model_reasoning_effort={effort}",
            "-s", "read-only", "--json", "--skip-git-repo-check", "-"]


def _last_assistant_text(stream):
    messages = []
    for line in stream.splitlines():
        try: event = json.loads(line)
        except (json.JSONDecodeError, TypeError): continue
        item = event.get("item", {}) if isinstance(event, dict) else {}
        if event.get("type") == "item.completed" and item.get("type") == "agent_message" and isinstance(item.get("text"), str):
            messages.append(item["text"])
    return messages[-1] if messages else stream


def _write_receipt(run_dir, receipt):
    path = Path(run_dir) / "judge_receipt.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def run_judge(records, journal, run_dir, judge_cmd=None, model="gpt-6-sol", effort="high", timeout=900):
    """Run codex in a fresh empty cwd and receipt parsing and evidence gating."""
    run_dir = Path(run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    bundle = build_judge_bundle(records, journal)
    prompt = build_judge_prompt(bundle)
    bundle_hash = hashlib.sha256(bundle.encode("utf-8")).hexdigest()
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    prompt_path = run_dir / "judge_prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    receipt = {"bundle_sha256": bundle_hash, "prompt_sha256": prompt_hash, "model": model,
               "effort": effort, "exit_code": None, "timeout": False, "raw_accepted": [],
               "discards": [], "parse_status": "NOT_RUN", "outcome": "INCOMPLETE_JUDGE"}
    try:
        with tempfile.TemporaryDirectory(prefix="playtest-judge-") as empty_cwd:
            with prompt_path.open("rb") as prompt_file:
                process = subprocess.Popen(judge_cmd or codex_judge_argv(model, effort), cwd=empty_cwd,
                                           stdin=prompt_file, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                           close_fds=True)
                try:
                    stdout, stderr = process.communicate(timeout=timeout)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate()
                    receipt["timeout"] = True
                receipt["exit_code"] = process.returncode
        receipt["stdout"] = stdout.decode("utf-8", errors="replace")
        receipt["stderr"] = stderr.decode("utf-8", errors="replace")
        if receipt["timeout"]:
            receipt["parse_status"] = "TIMEOUT"
        elif process.returncode != 0:
            receipt["parse_status"] = "PROCESS_ERROR"
        else:
            try:
                candidates = parse_judge_output(_last_assistant_text(receipt["stdout"]))
                accepted, discards = gate(records, candidates)
                receipt.update(raw_accepted=accepted, discards=discards, parse_status="OK", outcome="COMPLETE")
            except JudgeParseError as exc:
                receipt.update(parse_status="MALFORMED", parse_error=str(exc))
    except (OSError, ValueError, TypeError) as exc:
        receipt.update(parse_status="RUN_ERROR", error=str(exc))
    return _write_receipt(run_dir, receipt)
