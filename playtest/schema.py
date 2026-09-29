"""The single, versioned contract for playtest evidence.

Hashes in this module are content identities; Git revisions are recorded in
separate fields.  Local hashes detect accidental inconsistency, not a writer
that can rewrite every artifact and its local anchor.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Literal

SCHEMA_VERSION = 2
SCHEMA_MINOR = 1
LEGACY_VERSION = 1
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
GAME_IDS = {"dnd_combat", "delve"}
GAME_ENTRYPOINTS = {"dnd_combat": "dnd_combat.__main__", "delve": "delve.__main__"}
GAME_TREE_SPECS = {"dnd_combat": "dnd_combat/*.py", "delve": "delve/**/*.{py,json}"}


@dataclass(frozen=True)
class LegacyArtifact:
    """Readable historical data.  Legacy artifacts are never comparison eligible."""
    schema_version: int
    data: dict[str, Any]
    legacy: bool = True
    eligible: bool = False


class GameCompatibleDict(dict):
    """Expose v2.0's implicit D&D identity without changing its stored bytes."""
    _defaults = {"schema_minor": 0, "game_id": "dnd_combat",
                 "game_entrypoint": "dnd_combat.__main__",
                 "game_tree_spec": "dnd_combat/*.py", "detector_set_status": "IMPLEMENTED"}

    def __getitem__(self, key):
        if key not in self and key in self._defaults: return self._defaults[key]
        return super().__getitem__(key)

    def get(self, key, default=None):
        if key not in self and key in self._defaults: return self._defaults[key]
        return super().get(key, default)


@dataclass(frozen=True)
class Manifest:
    schema_version: int; schema_minor: int; game_id: str; game_entrypoint: str; game_tree_spec: str
    run_id: str; session_id: str; persona_id: str
    persona_prompt_sha256: str; seed: int; is_holdout: bool
    holdout_prompt_sha256: str | None; narrator_policy: str; turn_policy: str
    turn_cap: int; measurement_policy: str; severity_taxonomy_version: str; game_revision: str | None
    harness_revision: str | None; game_files: list[dict]; harness_files: list[dict]
    game_sha: str; harness_sha: str; manifest_sha256: str; name: str
    character_class: str; created_by: str; created_at: str; content_catalog: dict


@dataclass(frozen=True)
class TranscriptRecord:
    schema_version: int; run_id: str; manifest_sha256: str; frame_kind: str
    turn_id: int; frame_id: int; input_calls: list[str]; new_output: str
    full_output_sha256: str; prev_chain_hash: str; chain_hash: str
    snapshot: dict; termination: str; game_sha: str; harness_sha: str


@dataclass(frozen=True)
class RunReceipt:
    schema_version: int; schema_minor: int; game_id: str; game_entrypoint: str; game_tree_spec: str
    run_id: str; session_id: str; manifest_sha256: str
    game_revision: str | None; harness_revision: str | None
    game_files_start: list[dict]; harness_files_start: list[dict]
    game_sha: str; harness_sha: str; game_files_end: list[dict]
    harness_files_end: list[dict]; game_sha_end: str; harness_sha_end: str
    persona_id: str; persona_prompt_sha256: str; seed: int; is_holdout: bool
    holdout_prompt_sha256: str | None; narrator_policy: str; turn_policy: str
    turn_cap: int; measurement_policy: str; severity_taxonomy_version: str; retry_of: str | None
    receipt_finalized_after_child_exit: bool; controller_stop: bool
    exit_code: int | None; timeout: bool; stop_reason: str; termination: str
    run_outcome: str; turns: int; transcript_record_count: int
    journal_record_count: int; journal_consistent: bool
    transcript_head_chain_hash: str; stdout_sha256: str; stderr_sha256: str
    journal_sha256: str; audit_log_sha256: str; audit_status: str
    audit_events_seen: int; model: str; effort: str; prompt_sha256: str


@dataclass(frozen=True)
class JudgeReceipt:
    schema_version: int; run_id: str; manifest_sha256: str
    transcript_head_chain_hash: str; journal_sha256: str; bundle_sha256: str
    prompt_sha256: str; judge_version: str; verifier_version: str
    judge_model: str; judge_effort: str; verifier_model: str; verifier_effort: str
    severity_taxonomy_version: str; process_status: str; audit_status: str; audit_events_seen: int
    candidate_decisions: list[dict]; counted: list[dict]
    discarded_judge_claims: int; judge_outcome: str


@dataclass(frozen=True)
class VerifiedInstance:
    instance_id: str; source: str; mode: str; turn_ids: list[int]; quote: str
    rationale: str; severity: int; evidence_kind: str; evidence_sha256: str
    verifier_receipt_sha256: str | None


@dataclass(frozen=True)
class LedgerEntry:
    schema_version: int; schema_minor: int; game_id: str; game_entrypoint: str; game_tree_spec: str
    detector_set_status: str; run_id: str; session_id: str; manifest_sha256: str
    run_receipt_sha256: str; transcript_head_chain_hash: str; journal_sha256: str
    game_revision: str | None; harness_revision: str | None; game_sha: str; harness_sha: str
    persona_id: str; persona_prompt_sha256: str; seed: int; is_holdout: bool
    holdout_prompt_sha256: str | None; narrator_policy: str; turn_policy: str
    turn_cap: int; measurement_policy: str; severity_taxonomy_version: str; detector_version: str; turns: int
    transcript_record_count: int; termination: str | None; run_outcome: str; golem: dict
    judge_receipt_sha256: str | None
    judge_status: str; judge_version: str | None; verifier_version: str | None
    judge_model: str | None; judge_effort: str | None
    judge_counted_instances: int | None; discarded_judge_claims: int | None
    per_mode_verified_instances: dict; severity_weighted_counts: dict
    verified_instances: list[dict]; content_catalog: dict; catalog_sha256: str
    coverage: dict; curiosity: dict; expected_content_change: str | None; eligibility: dict


def canonical_json(value: Any) -> str:
    """Canonical JSON used by every v2 identity and chain."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def manifest_digest(manifest):
    body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def strict_json_loads(text: str) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"invalid JSON constant: {value}")))


def _digest(value, label):
    if not isinstance(value, str) or not DIGEST_RE.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def _revision(value, label):
    if value is None: return
    if not isinstance(value, str) or value in {"unknown", ""} or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value):
        raise ValueError(f"{label} must be a full Git object id or null")


def _fields(value, required, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    missing, extra = required - value.keys(), value.keys() - required
    if missing or extra:
        raise ValueError(f"{label} fields missing={sorted(missing)} extra={sorted(extra)}")


def _typed(value, spec, label):
    _fields(value, set(spec), label)
    for key, expected in spec.items():
        actual = value[key]
        if expected is int:
            valid = type(actual) is int
        elif expected is bool:
            valid = type(actual) is bool
        elif isinstance(expected, tuple) and type(None) in expected:
            allowed = tuple(x for x in expected if x is not type(None))
            valid = actual is None or any(type(actual) is item if item in (int, bool) else isinstance(actual, item)
                                          for item in allowed)
        else:
            valid = isinstance(actual, expected)
        if not valid:
            raise ValueError(f"{label}.{key} has wrong type")


FILE_SPEC = {"path": str, "sha256": str}
MANIFEST_FIELDS = {
    "schema_version": int, "schema_minor": int, "game_id": str, "game_entrypoint": str, "game_tree_spec": str,
    "run_id": str, "session_id": str, "persona_id": str,
    "persona_prompt_sha256": str, "seed": int, "is_holdout": bool,
    "holdout_prompt_sha256": (str, type(None)), "narrator_policy": str,
    "turn_policy": str, "turn_cap": int, "measurement_policy": str,
    "severity_taxonomy_version": str,
    "game_revision": (str, type(None)), "harness_revision": (str, type(None)),
    "game_files": list, "harness_files": list, "game_sha": str, "harness_sha": str,
    "manifest_sha256": str, "name": str, "character_class": str, "created_by": str,
    "created_at": str, "content_catalog": dict,
}
TRANSCRIPT_FIELDS = {
    "schema_version": int, "run_id": str, "manifest_sha256": str,
    "frame_kind": str, "turn_id": int, "frame_id": int, "input_calls": list,
    "new_output": str, "full_output_sha256": str, "prev_chain_hash": str,
    "chain_hash": str, "snapshot": dict, "termination": str,
    "game_sha": str, "harness_sha": str,
}
LEGACY_TRANSCRIPT_FIELDS = {
    "run_id": str, "turn_id": int, "frame_id": int, "input_calls": list,
    "new_output": str, "full_output_sha256": str, "prev_chain_hash": str,
    "chain_hash": str, "snapshot": dict, "termination": str,
    "game_sha": str, "harness_sha": str,
}
RUN_RECEIPT_FIELDS = {
    "schema_version": int, "schema_minor": int, "game_id": str, "game_entrypoint": str, "game_tree_spec": str,
    "run_id": str, "session_id": str, "manifest_sha256": str,
    "game_revision": (str, type(None)), "harness_revision": (str, type(None)),
    "game_files_start": list, "harness_files_start": list, "game_sha": str,
    "harness_sha": str, "game_files_end": list, "harness_files_end": list,
    "game_sha_end": str, "harness_sha_end": str, "persona_id": str,
    "persona_prompt_sha256": str, "seed": int, "is_holdout": bool,
    "holdout_prompt_sha256": (str, type(None)), "narrator_policy": str,
    "turn_policy": str, "turn_cap": int, "measurement_policy": str,
    "severity_taxonomy_version": str,
    "retry_of": (str, type(None)), "receipt_finalized_after_child_exit": bool,
    "controller_stop": bool, "exit_code": (int, type(None)), "timeout": bool,
    "stop_reason": str, "termination": str, "run_outcome": str, "turns": int,
    "transcript_record_count": int, "journal_record_count": int,
    "journal_consistent": bool, "transcript_head_chain_hash": str,
    "stdout_sha256": str, "stderr_sha256": str, "journal_sha256": str,
    "audit_log_sha256": str, "audit_status": str, "audit_events_seen": int,
    "model": str, "effort": str, "prompt_sha256": str,
}
VERIFIED_INSTANCE_FIELDS = {
    "instance_id": str, "source": str, "mode": str, "turn_ids": list,
    "quote": str, "rationale": str, "severity": int, "evidence_kind": str,
    "evidence_sha256": str, "verifier_receipt_sha256": (str, type(None)),
}
JUDGE_RECEIPT_FIELDS = {
    "schema_version": int, "run_id": str, "manifest_sha256": str,
    "transcript_head_chain_hash": str, "journal_sha256": str, "bundle_sha256": str,
    "prompt_sha256": str, "judge_version": str, "verifier_version": str,
    "judge_model": str, "judge_effort": str, "verifier_model": str,
    "verifier_effort": str, "severity_taxonomy_version": str,
    "process_status": str, "audit_status": str,
    "audit_events_seen": int, "candidate_decisions": list, "counted": list,
    "discarded_judge_claims": int, "judge_outcome": str,
}
LEDGER_ENTRY_FIELDS = {
    "schema_version": int, "schema_minor": int, "game_id": str, "game_entrypoint": str, "game_tree_spec": str,
    "detector_set_status": str, "run_id": str, "session_id": str, "manifest_sha256": str,
    "run_receipt_sha256": str, "transcript_head_chain_hash": str, "journal_sha256": str,
    "game_revision": (str, type(None)),
    "harness_revision": (str, type(None)), "game_sha": str, "harness_sha": str,
    "persona_id": str, "persona_prompt_sha256": str, "seed": int,
    "is_holdout": bool, "holdout_prompt_sha256": (str, type(None)),
    "narrator_policy": str, "turn_policy": str, "turn_cap": int,
    "measurement_policy": str, "severity_taxonomy_version": str,
    "detector_version": str, "turns": int,
    "transcript_record_count": int, "termination": (str, type(None)),
    "run_outcome": str, "golem": dict, "judge_receipt_sha256": (str, type(None)),
    "judge_status": str, "judge_version": (str, type(None)),
    "verifier_version": (str, type(None)), "judge_model": (str, type(None)),
    "judge_effort": (str, type(None)), "judge_counted_instances": (int, type(None)),
    "discarded_judge_claims": (int, type(None)), "per_mode_verified_instances": dict,
    "severity_weighted_counts": dict, "verified_instances": list,
    "content_catalog": dict, "catalog_sha256": str, "coverage": dict,
    "curiosity": dict, "expected_content_change": (str, type(None)), "eligibility": dict,
}

SEVERITY_TAXONOMY_VERSION = "1"
SEVERITY_TAXONOMY = {
    "UNRECOGNIZED_COMMAND": 2, "UNSUPPORTED_INTENT": 3,
    "HOLLOW_CONSEQUENCE": 4, "WORLD_STATE_CONTRADICTION": 5,
    "INERT_TAKEABLE": 2, "NO_CONSEQUENCE_STALL": 4,
    "REPEATED_RESPONSE": 3, "DOMINANT_ACTION": 3,
    "DOMINANT_ACTION_SOFT": 1, "FAIL_WITH_NOTHING": 3,
    "CONVENTION_CLASH": 2,
    "FALSE_AFFORDANCE": 3, "OBSCURE_ACTIONABLE_STATE": 3,
    "PACING_DRAG": 2, "CONSEQUENCE_OPACITY": 4, "CHOICE_ILLUSION": 3,
    "REWARD_WITHOUT_CAUSE": 3, "HOLLOW_PAYOFF": 4,
    "NEVER_CLOSED_MYSTERY": 4, "TUTORIAL_CLIFF": 4,
    "MENU_WALL": 3, "NARRATOR_INVENTION": 4,
}


def _validate_files(files, label):
    if not isinstance(files, list): raise ValueError(f"{label} must be a list")
    paths = []
    for item in files:
        _typed(item, FILE_SPEC, label + " item")
        _digest(item["sha256"], label + ".sha256")
        if not item["path"] or "\\" in item["path"] or item["path"].startswith("/") or ".." in Path(item["path"]).parts:
            raise ValueError(f"{label} contains a non-repository POSIX path")
        paths.append(item["path"])
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise ValueError(f"{label} paths must be sorted and unique")


def _validate_version(value, fields, label):
    version = value.get("schema_version") if isinstance(value, dict) else None
    if version is None:
        return LegacyArtifact(version or LEGACY_VERSION, value)
    if type(version) is int and version == LEGACY_VERSION:
        return LegacyArtifact(version, value)
    if type(version) is not int: raise ValueError(f"{label}.schema_version must be an integer")
    if version != SCHEMA_VERSION:
        raise ValueError(f"unsupported {label} schema_version")
    # Schema 2.0 artifacts remain readable with their original byte identity.
    # Their absent game identity is interpreted as the frozen D&D baseline.
    identity_fields = {"schema_minor", "game_id", "game_entrypoint", "game_tree_spec", "detector_set_status"}
    if "game_id" not in value and "game_id" in fields:
        _typed(value, {key: spec for key, spec in fields.items() if key not in identity_fields}, label)
    else:
        _typed(value, fields, label)
    return None


def _game_identity(value):
    game_id = value.get("game_id", "dnd_combat")
    if game_id not in GAME_IDS: raise ValueError("unsupported game_id")
    if value.get("schema_minor", 0) not in {0, SCHEMA_MINOR}: raise ValueError("unsupported schema_minor")
    if value.get("game_entrypoint", GAME_ENTRYPOINTS[game_id]) != GAME_ENTRYPOINTS[game_id]:
        raise ValueError("game_entrypoint does not match game_id")
    if value.get("game_tree_spec", GAME_TREE_SPECS[game_id]) != GAME_TREE_SPECS[game_id]:
        raise ValueError("game_tree_spec does not match game_id")
    return game_id


def _validate_game_paths(files, game_id, label):
    prefix = game_id + "/"
    for item in files:
        path = item["path"]
        if not path.startswith(prefix): raise ValueError(f"{label} path is outside declared game tree")
        suffix = Path(path).suffix
        allowed = suffix == ".py" if game_id == "dnd_combat" else suffix in {".py", ".json"}
        if not allowed: raise ValueError(f"{label} path does not match game_tree_spec")


def validate_manifest(value):
    legacy = _validate_version(value, MANIFEST_FIELDS, "manifest")
    if legacy: return legacy
    game_id = _game_identity(value)
    if not all(value[k] for k in ("run_id", "session_id", "persona_id", "name", "character_class")):
        raise ValueError("manifest identity strings must not be empty")
    if value["narrator_policy"] != "plain" or value["turn_policy"] != "action_frames_v1": raise ValueError("unsupported manifest policy")
    if value["measurement_policy"] not in {"detector_only", "detector_and_judge"}: raise ValueError("unsupported measurement policy")
    if value["severity_taxonomy_version"] != SEVERITY_TAXONOMY_VERSION: raise ValueError("unsupported severity taxonomy version")
    if value["turn_cap"] <= 0: raise ValueError("turn_cap must be positive")
    if value["is_holdout"] != (value["holdout_prompt_sha256"] is not None): raise ValueError("holdout identity must be explicit")
    if value["is_holdout"] and value["holdout_prompt_sha256"] != value["persona_prompt_sha256"]: raise ValueError("holdout prompt identity mismatch")
    for field in ("persona_prompt_sha256", "game_sha", "harness_sha", "manifest_sha256"): _digest(value[field], "manifest." + field)
    if value["holdout_prompt_sha256"] is not None: _digest(value["holdout_prompt_sha256"], "manifest.holdout_prompt_sha256")
    _revision(value["game_revision"], "manifest.game_revision"); _revision(value["harness_revision"], "manifest.harness_revision")
    _validate_files(value["game_files"], "manifest.game_files"); _validate_files(value["harness_files"], "manifest.harness_files")
    _validate_game_paths(value["game_files"], game_id, "manifest.game_files")
    validate_content_catalog(value["content_catalog"])
    if value["manifest_sha256"] != manifest_digest(value): raise ValueError("manifest digest mismatch")
    if value["game_sha"] != source_digest("game", value["game_files"], game_id): raise ValueError("manifest game_sha mismatch")
    if value["harness_sha"] != source_digest("harness", value["harness_files"]): raise ValueError("manifest harness_sha mismatch")


def validate_transcript_record(value):
    legacy = _validate_version(value, TRANSCRIPT_FIELDS, "transcript record")
    if legacy: return legacy
    if value["frame_kind"] not in {"setup", "action"}: raise ValueError("invalid frame_kind")
    if value["frame_kind"] == "setup" and (value["turn_id"] != 0 or value["frame_id"] != 0): raise ValueError("setup frame ids must be 0/0")
    if value["frame_kind"] == "action" and (value["turn_id"] < 1 or value["frame_id"] < 1): raise ValueError("action frame ids must be positive")
    if any(not isinstance(x, str) for x in value["input_calls"]): raise ValueError("input_calls must contain strings")
    if value["termination"] not in {"playing", "won", "dead", "quit", "error"}: raise ValueError("invalid transcript termination")
    for key in ("manifest_sha256", "full_output_sha256", "prev_chain_hash", "chain_hash", "game_sha", "harness_sha"):
        _digest(value[key], "transcript." + key)


def validate_run_receipt(value):
    legacy = _validate_version(value, RUN_RECEIPT_FIELDS, "run receipt")
    if legacy: return legacy
    game_id = _game_identity(value)
    _validate_files(value["game_files_start"], "run_receipt.game_files_start"); _validate_files(value["harness_files_start"], "run_receipt.harness_files_start")
    _validate_files(value["game_files_end"], "run_receipt.game_files_end"); _validate_files(value["harness_files_end"], "run_receipt.harness_files_end")
    _validate_game_paths(value["game_files_start"], game_id, "run_receipt.game_files_start")
    _validate_game_paths(value["game_files_end"], game_id, "run_receipt.game_files_end")
    if source_digest("game", value["game_files_start"], game_id) != value["game_sha"]: raise ValueError("run receipt start game digest mismatch")
    if source_digest("harness", value["harness_files_start"]) != value["harness_sha"]: raise ValueError("run receipt start harness digest mismatch")
    if source_digest("game", value["game_files_end"], game_id) != value["game_sha_end"]: raise ValueError("run receipt end game digest mismatch")
    if source_digest("harness", value["harness_files_end"]) != value["harness_sha_end"]: raise ValueError("run receipt end harness digest mismatch")
    for field in ("manifest_sha256", "game_sha", "harness_sha", "game_sha_end", "harness_sha_end", "persona_prompt_sha256", "transcript_head_chain_hash", "stdout_sha256", "stderr_sha256", "journal_sha256", "audit_log_sha256", "prompt_sha256"):
        _digest(value[field], "run_receipt." + field)
    if value["holdout_prompt_sha256"] is not None: _digest(value["holdout_prompt_sha256"], "run_receipt.holdout_prompt_sha256")
    _revision(value["game_revision"], "run_receipt.game_revision"); _revision(value["harness_revision"], "run_receipt.harness_revision")
    if value["stop_reason"] not in {"won", "dead", "cap", "no_progress", "player_stop", "timeout", "child_exit_error", "ipc_error", "game_error", "premature_exit"}: raise ValueError("invalid stop_reason")
    if value["termination"] not in {"playing", "won", "dead", "quit", "error"}: raise ValueError("invalid termination")
    if value["run_outcome"] not in {"COMPLETE", "INCOMPLETE_DISPATCH", "BLINDNESS_VIOLATED", "AUDIT_UNVERIFIABLE", "GAME_MODIFIED_DURING_RUN", "ERROR"}: raise ValueError("invalid run_outcome")
    if value["audit_status"] not in {"CLEAN", "VIOLATED", "UNVERIFIABLE"}: raise ValueError("invalid audit_status")
    if value["severity_taxonomy_version"] != SEVERITY_TAXONOMY_VERSION: raise ValueError("unsupported severity taxonomy version")
    if value["turns"] < 0 or value["transcript_record_count"] != value["turns"] + 1:
        raise ValueError("run receipt must count action frames separately from the setup record")
    if value["journal_record_count"] < 0: raise ValueError("journal_record_count must be nonnegative")
    same_start_end = (value["game_files_start"] == value["game_files_end"] and
                      value["harness_files_start"] == value["harness_files_end"] and
                      value["game_sha"] == value["game_sha_end"] and
                      value["harness_sha"] == value["harness_sha_end"])
    if value["run_outcome"] == "COMPLETE":
        if not value["receipt_finalized_after_child_exit"] or value["timeout"]:
            raise ValueError("COMPLETE receipt must be finalized after a non-timeout child exit")
        if not same_start_end: raise ValueError("COMPLETE receipt source identities differ")
        if value["audit_status"] != "CLEAN" or value["audit_events_seen"] < 1:
            raise ValueError("COMPLETE receipt requires recognized clean audit evidence")
        if value["termination"] == "error": raise ValueError("game error cannot be COMPLETE")
        if value["stop_reason"] not in {"won", "dead", "cap", "no_progress", "player_stop"}:
            raise ValueError("COMPLETE receipt requires a valid stop")
        if value["turns"] < 1 or value["transcript_record_count"] != value["turns"] + 1:
            raise ValueError("COMPLETE receipt turn counts are inconsistent")
        if value["journal_consistent"] is not True or value["journal_record_count"] != value["turns"]:
            raise ValueError("COMPLETE receipt requires one journal record per action")
        if value["exit_code"] not in (0, -9):
            raise ValueError("COMPLETE receipt has unexpected child exit")
        if value["exit_code"] == -9 and not value["controller_stop"]:
            raise ValueError("COMPLETE receipt kill was not controller initiated")


def validate_verified_instance(value):
    _typed(value, VERIFIED_INSTANCE_FIELDS, "verified instance")
    _digest(value["instance_id"], "instance_id"); _digest(value["evidence_sha256"], "evidence_sha256")
    if value["verifier_receipt_sha256"] is not None: _digest(value["verifier_receipt_sha256"], "verifier_receipt_sha256")
    if value["source"] not in {"detector", "judge"}: raise ValueError("invalid verified instance source")
    if value["evidence_kind"] not in {"transcript", "static_probe"}: raise ValueError("invalid evidence_kind")
    if value["source"] == "judge" and value["verifier_receipt_sha256"] is None: raise ValueError("judge instance requires verifier receipt")
    if type(value["severity"]) is not int or value["severity"] != SEVERITY_TAXONOMY.get(value["mode"]): raise ValueError("severity does not match taxonomy")
    if any(type(turn) is not int for turn in value["turn_ids"]): raise ValueError("turn_ids must be integers")
    expected_id = hashlib.sha256(canonical_json({key: item for key, item in value.items() if key != "instance_id"}).encode("utf-8")).hexdigest()
    if value["instance_id"] != expected_id: raise ValueError("verified instance id mismatch")


def validate_judge_receipt(value):
    legacy = _validate_version(value, JUDGE_RECEIPT_FIELDS, "judge receipt")
    if legacy: return legacy
    for field in ("manifest_sha256", "transcript_head_chain_hash", "journal_sha256", "bundle_sha256", "prompt_sha256"): _digest(value[field], "judge_receipt." + field)
    if value["judge_outcome"] not in {"COMPLETE", "INCOMPLETE_JUDGE", "BLINDNESS_VIOLATED", "AUDIT_UNVERIFIABLE"}: raise ValueError("invalid judge_outcome")
    if value["severity_taxonomy_version"] != SEVERITY_TAXONOMY_VERSION: raise ValueError("unsupported severity taxonomy version")
    if value["audit_status"] not in {"CLEAN", "VIOLATED", "UNVERIFIABLE"} or type(value["audit_events_seen"]) is not int or value["audit_events_seen"] < 0: raise ValueError("invalid judge audit receipt")
    if type(value["discarded_judge_claims"]) is not int or value["discarded_judge_claims"] < 0: raise ValueError("discarded_judge_claims must be nonnegative")
    for instance in value["counted"]: validate_verified_instance(instance)
    if any(instance["source"] != "judge" for instance in value["counted"]): raise ValueError("judge receipt can count only judge instances")
    if len(value["candidate_decisions"]) != len(value["counted"]) + value["discarded_judge_claims"]:
        raise ValueError("judge terminal decisions do not match counted/discarded totals")
    if value["judge_outcome"] == "COMPLETE" and (value["process_status"] != "OK" or value["audit_status"] != "CLEAN" or value["audit_events_seen"] < 1):
        raise ValueError("COMPLETE judge receipt requires a successful process and clean audited events")


def validate_ledger_entry(value):
    legacy = _validate_version(value, LEDGER_ENTRY_FIELDS, "ledger entry")
    if legacy: return legacy
    _game_identity(value)
    if value.get("detector_set_status", "IMPLEMENTED") not in {"IMPLEMENTED", "NOT_IMPLEMENTED"}: raise ValueError("invalid detector_set_status")
    for field in ("manifest_sha256", "run_receipt_sha256", "transcript_head_chain_hash", "journal_sha256", "game_sha", "harness_sha", "persona_prompt_sha256", "catalog_sha256"): _digest(value[field], "ledger." + field)
    _revision(value["game_revision"], "ledger.game_revision"); _revision(value["harness_revision"], "ledger.harness_revision")
    if value["turn_cap"] <= 0 or value["turns"] < 0 or value["transcript_record_count"] != value["turns"] + 1: raise ValueError("invalid ledger turn counts")
    if not value["run_id"] or not value["session_id"] or not value["persona_id"]: raise ValueError("ledger identities must not be empty")
    if value["run_outcome"] not in {"COMPLETE", "INCOMPLETE_DISPATCH", "BLINDNESS_VIOLATED", "AUDIT_UNVERIFIABLE", "GAME_MODIFIED_DURING_RUN", "ERROR"}: raise ValueError("invalid ledger run_outcome")
    if value["measurement_policy"] not in {"detector_only", "detector_and_judge"}: raise ValueError("invalid ledger measurement_policy")
    if value["severity_taxonomy_version"] != SEVERITY_TAXONOMY_VERSION: raise ValueError("unsupported severity taxonomy version")
    if value["judge_status"] not in {"NOT_REQUESTED", "COMPLETE", "INCOMPLETE", "INVALID"}: raise ValueError("invalid judge_status")
    validate_content_catalog(value["content_catalog"])
    if catalog_digest(value["content_catalog"]) != value["catalog_sha256"]: raise ValueError("ledger catalog identity mismatch")
    if value["is_holdout"] != (value["holdout_prompt_sha256"] is not None): raise ValueError("ledger holdout identity mismatch")
    if value["judge_status"] == "NOT_REQUESTED" and (value["judge_receipt_sha256"] is not None or value["judge_counted_instances"] is not None): raise ValueError("NOT_REQUESTED judge must have null receipt and count")
    if value["judge_status"] == "COMPLETE" and (value["judge_receipt_sha256"] is None or value["judge_counted_instances"] is None): raise ValueError("COMPLETE judge requires bound receipt and count")
    if value["measurement_policy"] == "detector_and_judge" and value["judge_status"] == "NOT_REQUESTED": raise ValueError("required judge cannot be NOT_REQUESTED")
    for instance in value["verified_instances"]: validate_verified_instance(instance)
    instance_ids = [instance["instance_id"] for instance in value["verified_instances"]]
    if len(instance_ids) != len(set(instance_ids)): raise ValueError("duplicate verified instance id")
    expected_counts = {"detector": {}, "judge": {} if value["judge_status"] != "NOT_REQUESTED" else None}
    expected_weighted = {"detector": {}, "judge": {} if value["judge_status"] != "NOT_REQUESTED" else None}
    for instance in value["verified_instances"]:
        source, mode = instance["source"], instance["mode"]
        if expected_counts[source] is None: raise ValueError("judge instance present when judging was not requested")
        expected_counts[source][mode] = expected_counts[source].get(mode, 0) + 1
        expected_weighted[source][mode] = expected_weighted[source].get(mode, 0) + instance["severity"]
    if expected_counts != value["per_mode_verified_instances"] or expected_weighted != value["severity_weighted_counts"]:
        raise ValueError("ledger counts do not match normalized instances")
    if value["judge_status"] == "COMPLETE" and value["judge_counted_instances"] != sum(expected_counts["judge"].values()):
        raise ValueError("judge_counted_instances mismatch")
    if value["turns"] == 0 and value["eligibility"].get("comparison_eligible") is True:
        raise ValueError("zero-action run cannot be comparison eligible")
    if value.get("detector_set_status", "IMPLEMENTED") == "NOT_IMPLEMENTED" and (
            value["eligibility"].get("comparison_eligible") is True or
            value["eligibility"].get("reason_code") != "DETECTORS_NOT_IMPLEMENTED_FOR_GAME"):
        raise ValueError("unimplemented detector set cannot be comparison eligible")


def source_manifest(root, kind, game_id="dnd_combat"):
    """Return sorted raw-byte source identity for one repository subtree."""
    if kind not in {"game", "harness"}: raise ValueError("kind must be game or harness")
    if game_id not in GAME_IDS: raise ValueError("unsupported game_id")
    root = Path(root).resolve()
    directory = root / (game_id if kind == "game" else "playtest")
    files = []
    if directory.is_symlink(): raise ValueError(f"source symlink rejected: {directory}")
    if directory.exists():
        for path in directory.rglob("*"):
            if path.is_symlink(): raise ValueError(f"source symlink rejected: {path}")
            allowed = path.suffix == ".py" if (kind == "harness" or game_id == "dnd_combat") else path.suffix in {".py", ".json"}
            if allowed and path.is_file():
                files.append({"path": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    files.sort(key=lambda item: item["path"])
    return {"kind": kind, "game_id": game_id if kind == "game" else None, "files": files,
            "sha256": source_digest(kind, files, game_id)}


def source_digest(kind, files, game_id="dnd_combat"):
    if kind not in {"game", "harness"}: raise ValueError("kind must be game or harness")
    if game_id not in GAME_IDS: raise ValueError("unsupported game_id")
    ordered = sorted((dict(item) for item in files), key=lambda item: item.get("path", ""))
    for item in ordered:
        _typed(item, FILE_SPEC, "source file"); _digest(item["sha256"], "source file sha256")
    if len({item["path"] for item in ordered}) != len(ordered): raise ValueError("source file paths must be unique")
    payload = {"kind": kind, "version": 1, "files": ordered}
    # Preserve the frozen 0.6 digest recipe; Delve identities bind the tree rule.
    if kind == "game" and game_id == "delve":
        payload = {"kind": kind, "version": 2, "game_id": game_id,
                   "game_tree_spec": GAME_TREE_SPECS[game_id], "files": ordered}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def git_revision(root):
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root,
                                       stderr=subprocess.DEVNULL, text=True).strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def count_turns(records):
    # v1 transcripts had no frame_kind; turn zero was the setup record.
    return sum(record.get("frame_kind") == "action" or
               ("frame_kind" not in record and type(record.get("turn_id")) is int and record["turn_id"] > 0)
               for record in records)


class LegacyRecords(list):
    """List-compatible marker for a verified v1 transcript chain."""
    legacy = True
    eligible = False


def load_manifest(path):
    raw = Path(path).read_text(encoding="utf-8")
    value = strict_json_loads(raw)
    marker = validate_manifest(value)
    if marker is None and raw != canonical_json(value) + "\n": raise ValueError("manifest serialization is not canonical")
    if marker: return marker
    return GameCompatibleDict(value) if "game_id" not in value else value


def load_run_receipt(path):
    raw = Path(path).read_text(encoding="utf-8")
    value = strict_json_loads(raw)
    marker = validate_run_receipt(value)
    if marker is None and raw != canonical_json(value) + "\n": raise ValueError("run receipt serialization is not canonical")
    if marker: return marker
    return GameCompatibleDict(value) if "game_id" not in value else value


def load_judge_receipt(path):
    raw = Path(path).read_text(encoding="utf-8")
    value = strict_json_loads(raw)
    marker = validate_judge_receipt(value)
    if marker is None and raw != canonical_json(value) + "\n": raise ValueError("judge receipt serialization is not canonical")
    return marker if marker else value


def load_ledger_entry(path):
    raw = Path(path).read_text(encoding="utf-8")
    value = strict_json_loads(raw)
    marker = validate_ledger_entry(value)
    if marker is None and raw != canonical_json(value) + "\n": raise ValueError("ledger entry serialization is not canonical")
    if marker: return marker
    return GameCompatibleDict(value) if "game_id" not in value else value


def load_artifact(path, validator):
    """Generic typed loader; a v1 artifact is returned as an ineligible marker."""
    value = strict_json_loads(Path(path).read_text(encoding="utf-8"))
    marker = validator(value)
    return marker if marker else value


def normalize_instance(*, source, mode, turn_ids, quote, rationale, evidence_kind,
                       evidence_sha256, verifier_receipt_sha256=None, severity=None):
    expected = SEVERITY_TAXONOMY.get(mode)
    if expected is None: raise ValueError(f"unknown severity mode: {mode}")
    if severity is not None and severity != expected: raise ValueError("severity is taxonomy-owned")
    core = {"source": source, "mode": mode, "turn_ids": list(turn_ids), "quote": quote,
            "rationale": rationale, "severity": expected, "evidence_kind": evidence_kind,
            "evidence_sha256": evidence_sha256, "verifier_receipt_sha256": verifier_receipt_sha256}
    core["instance_id"] = hashlib.sha256(canonical_json(core).encode("utf-8")).hexdigest()
    validate_verified_instance(core)
    return core


def content_catalog(snapshot, game_id="dnd_combat"):
    """Build a stable catalog from the controller's actual initial world snapshot."""
    if game_id == "delve":
        # M1's snapshot deliberately contains persistent run state, not its static pack.
        # Record only the starting room as observed coverage; do not invent map facts.
        room_id = snapshot.get("room_id") if isinstance(snapshot, dict) else None
        if not isinstance(room_id, str) or not room_id: raise ValueError("initial snapshot has no room identity")
        return {"catalog_version": 1, "room_ids": [room_id], "objects": [],
                "encounter_ids": [], "exits": [], "initial_reachability": [room_id]}
    if game_id != "dnd_combat": raise ValueError("unsupported game_id")
    rooms = snapshot.get("rooms") if isinstance(snapshot, dict) else None
    if not isinstance(rooms, dict): raise ValueError("initial snapshot has no room catalog")
    room_ids = sorted(rooms)
    exits = []
    objects = []
    encounters = []
    for room_id in room_ids:
        room = rooms[room_id]
        for direction, target in sorted(room.get("exits", {}).items()):
            exits.append({"from": room_id, "direction": direction, "to": target})
        seen_names = set()
        for item in room.get("objects", []):
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                raise ValueError("initial snapshot has malformed object")
            name = item["name"]
            if name in seen_names: raise ValueError(f"ambiguous object name in room {room_id}: {name}")
            seen_names.add(name)
            descriptor = {key: item.get(key) for key in ("description", "aliases", "takeable")}
            objects.append({"id": f"{room_id}:{name}", "room_id": room_id, "name": name,
                            "descriptor_sha256": hashlib.sha256(canonical_json(descriptor).encode()).hexdigest()})
        if room.get("enemy"):
            encounters.append({"id": room_id, "room_id": room_id})
    start = snapshot.get("room_id")
    reachable, queue = set(), [start] if start in rooms else []
    while queue:
        current = queue.pop(0)
        if current in reachable: continue
        reachable.add(current)
        queue.extend(dest for dest in rooms[current].get("exits", {}).values() if dest in rooms and dest not in reachable)
    objects.sort(key=lambda item: item["id"])
    return {"catalog_version": 1, "room_ids": room_ids, "objects": objects,
            "encounter_ids": sorted(item["id"] for item in encounters), "exits": exits,
            "initial_reachability": sorted(reachable)}


def catalog_digest(catalog):
    return hashlib.sha256(canonical_json(catalog).encode("utf-8")).hexdigest()


def validate_content_catalog(catalog):
    catalog_fields = {"catalog_version", "room_ids", "objects", "encounter_ids", "exits", "initial_reachability"}
    _fields(catalog, catalog_fields, "content catalog")
    if type(catalog["catalog_version"]) is not int or catalog["catalog_version"] != 1: raise ValueError("unsupported content catalog version")
    rooms = catalog["room_ids"]
    if not isinstance(rooms, list) or any(not isinstance(room, str) or not room for room in rooms) or rooms != sorted(set(rooms)):
        raise ValueError("catalog room_ids must be sorted unique strings")
    room_set = set(rooms)
    if not isinstance(catalog["objects"], list): raise ValueError("catalog objects must be a list")
    object_ids, names = set(), set()
    for item in catalog["objects"]:
        _fields(item, {"id", "room_id", "name", "descriptor_sha256"}, "catalog object")
        if not all(isinstance(item[key], str) and item[key] for key in ("id", "room_id", "name")): raise ValueError("catalog object identity must be nonempty")
        if item["room_id"] not in room_set or item["id"] != item["room_id"] + ":" + item["name"]: raise ValueError("catalog object id mismatch")
        _digest(item["descriptor_sha256"], "catalog descriptor_sha256")
        if item["id"] in object_ids or (item["room_id"], item["name"]) in names: raise ValueError("ambiguous catalog object identity")
        object_ids.add(item["id"]); names.add((item["room_id"], item["name"]))
    if [item["id"] for item in catalog["objects"]] != sorted(object_ids): raise ValueError("catalog objects must be sorted")
    for field in ("encounter_ids", "initial_reachability"):
        values = catalog[field]
        if not isinstance(values, list) or any(not isinstance(item, str) for item in values) or values != sorted(set(values)) or not set(values) <= room_set:
            raise ValueError(f"catalog {field} must be sorted known room ids")
    if not isinstance(catalog["exits"], list): raise ValueError("catalog exits must be a list")
    edge_keys = []
    for edge in catalog["exits"]:
        _fields(edge, {"from", "direction", "to"}, "catalog exit")
        if edge["from"] not in room_set or edge["to"] not in room_set or not isinstance(edge["direction"], str) or not edge["direction"]:
            raise ValueError("catalog exit references unknown room or direction")
        edge_keys.append((edge["from"], edge["direction"]))
    if edge_keys != sorted(set(edge_keys)): raise ValueError("catalog exits must be sorted and unique")
    return True
