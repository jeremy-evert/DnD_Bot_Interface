"""R1 S1 checks for the sole v2 contract owner (Annabelle exact contract)."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from playtest.schema import (LegacyArtifact, RUN_RECEIPT_FIELDS, canonical_json, load_run_receipt,
                             source_digest, source_manifest, strict_json_loads, validate_manifest)


class SchemaContractTests(unittest.TestCase):
    def test_duplicate_json_keys_and_nonfinite_values_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            strict_json_loads('{"x":1,"x":2}')
        with self.assertRaises(ValueError):
            canonical_json({"x": float("nan")})

    def test_bool_is_not_an_integer(self):
        with self.assertRaisesRegex(ValueError, "seed has wrong type"):
            # Strict field validation rejects bool even though bool subclasses int.
            from playtest.schema import _typed
            _typed({"seed": True}, {"seed": int}, "manifest")

    def test_source_digest_is_canonical_and_revisions_are_not_digests(self):
        files = [{"path": "playtest/a.py", "sha256": hashlib.sha256(b"a").hexdigest()}]
        expected = hashlib.sha256(canonical_json({"kind": "harness", "version": 1,
                                                  "files": files}).encode()).hexdigest()
        self.assertEqual(source_digest("harness", files), expected)

    def test_source_manifest_rejects_symlinks_and_hashes_raw_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / "playtest").mkdir()
            source = root / "playtest" / "x.py"; source.write_bytes(b"\xff\x00")
            manifest = source_manifest(root, "harness")
            self.assertEqual(manifest["files"][0]["sha256"], hashlib.sha256(b"\xff\x00").hexdigest())
            (root / "playtest" / "linked.py").symlink_to(source)
            with self.assertRaisesRegex(ValueError, "symlink"):
                source_manifest(root, "harness")

    def test_legacy_manifest_is_marked_and_never_eligible(self):
        marker = validate_manifest({"schema_version": 1, "game_sha": "old"})
        self.assertIsInstance(marker, LegacyArtifact)
        self.assertTrue(marker.legacy)
        self.assertFalse(marker.eligible)

    def test_sandbox_policy_is_required_for_current_receipts_and_legacy_loads_as_none(self):
        self.assertIn("sandbox_policy", RUN_RECEIPT_FIELDS)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "old-receipt.json"
            path.write_text(canonical_json({"schema_version": 1, "old": True}) + "\n", encoding="utf-8")
            receipt = load_run_receipt(path)
        self.assertTrue(receipt.legacy)
        self.assertIsNone(receipt.data["sandbox_policy"])

    def test_revision_uses_full_object_id_or_null_not_unknown_sentinel(self):
        from playtest.schema import _revision
        _revision(None, "revision")
        _revision("a" * 40, "revision")
        _revision("b" * 64, "revision")
        with self.assertRaisesRegex(ValueError, "full Git object id"):
            _revision("unknown", "revision")


if __name__ == "__main__":
    unittest.main()
