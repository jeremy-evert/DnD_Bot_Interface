"""Strict schemas for controller-authored playtest artifacts."""

SCHEMA_VERSION = 1

MANIFEST_FIELDS = {
    "schema_version": int,
    "session_id": str,
    "seed": int,
    "persona_id": str,
    "name": str,
    "character_class": str,
    "game_sha": str,
    "harness_sha": str,
    "narrator_policy": str,
    "created_by": str,
    "created_at": str,
}

TRANSCRIPT_FIELDS = {
    "run_id": str,
    "turn_id": int,
    "frame_id": int,
    "input_calls": list,
    "new_output": str,
    "full_output_sha256": str,
    "prev_chain_hash": str,
    "chain_hash": str,
    "snapshot": dict,
    "termination": str,
    "game_sha": str,
    "harness_sha": str,
}


def _validate(value, fields, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    missing, extra = fields.keys() - value.keys(), value.keys() - fields.keys()
    if missing or extra:
        raise ValueError(f"{label} fields missing={sorted(missing)} extra={sorted(extra)}")
    for field, expected in fields.items():
        actual = value[field]
        valid = type(actual) is expected if expected is int else isinstance(actual, expected)
        if not valid:
            raise ValueError(f"{label}.{field} must be {expected.__name__}")


def validate_manifest(manifest):
    _validate(manifest, MANIFEST_FIELDS, "manifest")
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported manifest schema_version")
    for field in ("session_id", "persona_id", "name", "character_class", "game_sha", "harness_sha"):
        if not manifest[field]:
            raise ValueError(f"manifest.{field} must not be empty")
    if manifest["narrator_policy"] != "plain" or manifest["created_by"] != "controller":
        raise ValueError("unsupported manifest narrator_policy or created_by")
    if not manifest["created_at"]:
        raise ValueError("manifest.created_at must not be empty")


def validate_transcript_record(record):
    _validate(record, TRANSCRIPT_FIELDS, "transcript record")
    if any(not isinstance(item, str) for item in record["input_calls"]):
        raise ValueError("transcript record.input_calls must contain only strings")
    if record["termination"] not in {"playing", "exhausted", "won", "dead", "error"}:
        raise ValueError("invalid transcript termination")
    for key in ("full_output_sha256", "prev_chain_hash", "chain_hash"):
        value = record[key]
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise ValueError(f"transcript record.{key} must be a lowercase SHA-256 hex digest")
