"""Append-only, hash-chained transcript storage."""

import hashlib
import json
import os
from pathlib import Path

from .schema import (LEGACY_TRANSCRIPT_FIELDS, LegacyRecords, TRANSCRIPT_FIELDS,
                     canonical_json, strict_json_loads, validate_transcript_record)

ZERO_HASH = "0" * 64


class ReplayDivergence(ValueError):
    """A fresh replay did not preserve the previously rendered output."""


def _chain_hash(record):
    body = {key: value for key, value in record.items() if key != "chain_hash"}
    return hashlib.sha256((record["prev_chain_hash"] + canonical_json(body)).encode("utf-8")).hexdigest()


def verify_chain(path):
    path = Path(path)
    records = []
    previous = ZERO_HASH
    rendered = ""
    with open(path, "r", encoding="utf-8", newline="") as source:
        for line_number, line in enumerate(source, 1):
            if not line.endswith("\n"):
                raise ValueError(f"transcript line {line_number} is incomplete")
            try:
                record = strict_json_loads(line)
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                raise ValueError(f"invalid transcript line {line_number}") from exc
            if canonical_json(record) + "\n" != line:
                raise ValueError(f"noncanonical transcript line {line_number}")
            validate_transcript_record(record)
            if record["prev_chain_hash"] != previous:
                raise ValueError(f"transcript chain link mismatch at line {line_number}")
            if _chain_hash(record) != record["chain_hash"]:
                raise ValueError(f"transcript hash mismatch at line {line_number}")
            rendered += record["new_output"]
            if hashlib.sha256(rendered.encode("utf-8")).hexdigest() != record["full_output_sha256"]:
                raise ValueError(f"transcript output hash mismatch at line {line_number}")
            previous = record["chain_hash"]
            records.append(record)
    versions = {record.get("schema_version", 1) for record in records}
    if len(versions) > 1:
        raise ValueError("transcript cannot mix legacy and v2 records")
    if versions == {2}:
        identities = {(record["run_id"], record["manifest_sha256"], record["game_sha"], record["harness_sha"])
                      for record in records}
        if len(identities) != 1: raise ValueError("transcript records disagree on manifest/source identity")
        if not records or sum(record["frame_kind"] == "setup" for record in records) != 1:
            raise ValueError("v2 transcript requires exactly one setup record")
        if records[0]["frame_kind"] != "setup":
            raise ValueError("v2 setup record must be first")
        for index, record in enumerate(records[1:], 1):
            if record["frame_kind"] != "action" or record["turn_id"] != index or record["frame_id"] != index:
                raise ValueError("v2 action turn/frame ids must be contiguous")
    anchor_path = path.with_name(path.name + ".head")
    try:
        anchor = strict_json_loads(anchor_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("transcript head anchor is missing or invalid") from exc
    expected_anchor = {"record_count": len(records), "chain_hash": previous}
    if anchor != expected_anchor:
        raise ValueError("transcript head anchor mismatch (transcript may be truncated or altered)")
    return LegacyRecords(records) if versions == {1} else records


def load_transcript(path):
    """Load canonical controller transcript only after full chain verification."""
    return verify_chain(path)


class TranscriptWriter:
    def __init__(self, session_dir):
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.session_dir / "transcript.jsonl"

    def append_verified(self, record_without_hashes):
        # Callers supply all semantic fields; hashes and predecessor are writer-owned.
        fields = TRANSCRIPT_FIELDS if "schema_version" in record_without_hashes else LEGACY_TRANSCRIPT_FIELDS
        expected = set(fields) - {"prev_chain_hash", "chain_hash"}
        expected.add("full_output")
        if not isinstance(record_without_hashes, dict) or set(record_without_hashes) != expected:
            raise ValueError("record must contain exactly the transcript fields except writer-owned hashes")
        records = verify_chain(self.path) if self.path.exists() else []
        previous_hash = records[-1]["chain_hash"] if records else ZERO_HASH
        prior_output = "".join(record["new_output"] for record in records)
        if records and not record_without_hashes["full_output"].startswith(prior_output):
            raise ReplayDivergence("REPLAY_DIVERGENCE: new full output is not an exact prefix extension")
        record = dict(record_without_hashes)
        full_output = record.pop("full_output")
        if not isinstance(full_output, str):
            raise ValueError("full_output must be a string")
        if not full_output.startswith(prior_output):
            raise ReplayDivergence("REPLAY_DIVERGENCE: new full output is not an exact prefix extension")
        if full_output[len(prior_output):] != record["new_output"]:
            raise ValueError("new_output is not the exact full-output suffix")
        if hashlib.sha256(full_output.encode("utf-8")).hexdigest() != record["full_output_sha256"]:
            raise ValueError("full_output_sha256 does not match full output")
        record["prev_chain_hash"] = previous_hash
        record["chain_hash"] = "0" * 64
        validate_transcript_record(record)
        record["chain_hash"] = _chain_hash(record)
        validate_transcript_record(record)
        with self.path.open("a", encoding="utf-8", newline="") as target:
            target.write(canonical_json(record) + "\n")
            target.flush()
            os.fsync(target.fileno())
        anchor_path = self.path.with_name(self.path.name + ".head")
        temporary = anchor_path.with_name(anchor_path.name + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="") as target:
            target.write(canonical_json({"record_count": len(records) + 1,
                                         "chain_hash": record["chain_hash"]}) + "\n")
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, anchor_path)
        return record
