import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from playtest.detectors import DETECTOR_VERSION, curiosity_events, run_all, session_facts
from playtest.ledger import append_entry, head_hash, make_entry, verify_ledger
from playtest.run_ledger_cli import build_entry
from playtest.report import compare, poisson_ci, render_markdown
from playtest.transcript import load_transcript

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "playtest" / "fixtures" / "real"


def base(run_id="r", **kw):
    catalog = {"catalog_version": 1, "room_ids": ["entry"],
               "objects": [{"id": "entry:stone", "room_id": "entry", "name": "stone", "descriptor_sha256": "a" * 64}],
               "encounter_ids": [], "exits": [], "initial_reachability": ["entry"]}
    values = dict(run_id=run_id, session_id="session", game_sha="1" * 64, harness_sha="2" * 64,
                  manifest_sha256="3" * 64, run_receipt_sha256="4" * 64, journal_sha256="5" * 64,
                  transcript_head_chain_hash="6" * 64, persona_prompt_sha256="7" * 64,
                  content_catalog=catalog, detector_version=DETECTOR_VERSION,
                  golem_model="golem-test", golem_effort="medium",
                  persona_id="p", seed=1, turns=4, turn_cap=35, narrator_policy="plain",
                  turn_policy="action_frames_v1", measurement_policy="detector_only",
                  judge_status="NOT_REQUESTED", run_outcome="COMPLETE")
    values.update(kw)
    return make_entry(**values)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ledger.jsonl"

    def test_edit_delete_swap_and_refuse_append_after_tamper(self):
        append_entry(self.path, base("one")); append_entry(self.path, base("two"))
        original = self.path.read_bytes(); rows = original.splitlines(keepends=True)
        for changed in (original.replace(b'"run_id":"one"', b'"run_id":"ONE"'), rows[0], rows[1] + rows[0]):
            self.path.write_bytes(changed)
            with self.assertRaises(ValueError): verify_ledger(self.path)
            with self.assertRaises(ValueError): append_entry(self.path, base("three"))
        self.path.write_bytes(original)
        self.assertEqual(len(verify_ledger(self.path)), 2)

    def test_expected_head_is_an_external_anchor(self):
        append_entry(self.path, base("one"))
        expected = head_hash(self.path)
        self.assertEqual(verify_ledger(self.path, expected_head=expected)[0]["run_id"], "one")
        append_entry(self.path, base("two"))
        with self.assertRaisesRegex(ValueError, "expected head"):
            verify_ledger(self.path, expected_head=expected)

    def test_rewriting_chain_and_local_anchor_is_outside_threat_model(self):
        """Local hashes detect partial damage; a writer of data and anchor can forge both."""
        append_entry(self.path, base("one"))
        original_head = head_hash(self.path)
        entry = base("forged")
        # Rebuild a self-consistent replacement using the ordinary writer in a second file.
        replacement = self.path.with_name("replacement.jsonl")
        append_entry(replacement, entry)
        self.path.write_bytes(replacement.read_bytes())
        self.path.with_name(self.path.name + ".head").write_bytes(replacement.with_name(replacement.name + ".head").read_bytes())
        self.assertNotEqual(head_hash(self.path), original_head)
        self.assertEqual(verify_ledger(self.path)[0]["run_id"], "forged")
        with self.assertRaisesRegex(ValueError, "expected head"):
            verify_ledger(self.path, expected_head=original_head)

    def test_noncomplete_is_recorded_but_ineligible(self):
        entry = base(run_outcome="INCOMPLETE_DISPATCH")
        append_entry(self.path, entry)
        actual = verify_ledger(self.path)[0]
        self.assertFalse(actual["eligibility"]["comparison_eligible"])
        self.assertEqual(actual["eligibility"]["reason_code"], "RUN_OUTCOME_INCOMPLETE_DISPATCH")

    def test_paired_keys_mismatches_and_content_loss(self):
        b = base("b", coverage={"rooms_visited": 4, "objects_touched": 2, "encounters_faced": 1})
        good = base("c", coverage={"rooms_visited": 4, "objects_touched": 2, "encounters_faced": 1})
        wrong = base("wrong", seed=2)
        lost = base("lost", coverage={"rooms_visited": 2, "objects_touched": 2, "encounters_faced": 1})
        report = compare([b], [good, wrong])
        self.assertEqual(report["paired_count"], 1)
        self.assertTrue(any(x["reason"] == "UNPAIRED_CANDIDATE" for x in report["ineligible"]))
        report = compare([b], [lost])
        self.assertEqual(report["paired_count"], 0)
        self.assertEqual(report["ineligible"][0]["reason"], "COMPARISON_INELIGIBLE_CONTENT_LOSS")
        self.assertEqual(report["evidence_statement"], "not enough evidence to claim improvement")

    def test_pair_requires_persona_seed_cap_policy_and_holdout(self):
        # Annabelle pairing clause: every declared scenario field participates in identity.
        b = base("b")
        for field, value in (("persona_id", "other"), ("seed", 9), ("turn_cap", 20),
                             ("narrator_policy", "live"), ("is_holdout", True)):
            overrides = {field: value}
            if field == "is_holdout": overrides["holdout_prompt_sha256"] = "7" * 64
            report = compare([b], [base("c", **overrides)])
            self.assertEqual(report["paired_count"], 0, field)

    def test_pair_requires_all_identity_before_grouping(self):
        # Annabelle pairing clause: missing identity is ineligible before key grouping.
        b = base("b")
        for field, value in (("game_sha", "8" * 64), ("harness_sha", "9" * 64),
                             ("persona_prompt_sha256", None), ("seed", None)):
            other = base("c")
            other[field] = value
            report = compare([b], [other])
            self.assertEqual(report["paired_count"], 0, field)
        # Two absent values do not form a key match.
        missing_left = base("left"); missing_right = base("right")
        missing_left["persona_prompt_sha256"] = None; missing_right["persona_prompt_sha256"] = None
        report = compare([missing_left], [missing_right])
        self.assertEqual(report["paired_count"], 0)
        self.assertTrue(any(row["reason"] in {"PAIR_IDENTITY_MISSING", "MISSING_PAIR_IDENTITY"} for row in report["ineligible"]))

    def test_poisson_known_values(self):
        low, high = poisson_ci(10)
        self.assertAlmostEqual(low, 4.795, delta=.02)
        self.assertAlmostEqual(high, 18.390, delta=.03)
        self.assertEqual(poisson_ci(0)[0], 0)

    def test_holdout_does_not_store_prompt_text(self):
        entry = base("x", is_holdout=True, persona_prompt_sha256="a" * 64,
                     holdout_prompt_sha256="a" * 64)
        # Holdout provenance hashes are public; sealed prompt wording is never stored.
        self.assertNotIn("sealed operator wording", json.dumps(entry))

    def test_four_real_fixtures_report_raw_counts_without_composite(self):
        entries = []
        for name in sorted(p.name for p in REAL.iterdir() if p.is_dir()):
            folder = REAL / name
            records = load_transcript(folder / "transcript.jsonl")
            journal = [json.loads(line) for line in (folder / "journal.jsonl").read_text().splitlines()]
            manifest = json.loads((folder / "manifest.json").read_text())
            instances = run_all(records, journal)
            entries.append({"schema_version": 1, "run_id": name, "run_outcome": "COMPLETE"})
        report = compare(entries, entries)
        rendered = render_markdown(report)
        # Contract clause: preserved v1 evidence is readable but is never relabeled or paired as v2.
        self.assertEqual(report["paired_count"], 0)
        self.assertTrue(all(item["reason"] == "LEGACY_SCHEMA" for item in report["ineligible"]))
        self.assertIn("not enough evidence", rendered)

    def test_cli_refuses_to_relabel_legacy_evidence_as_v2(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); run, session = root / "run", root / "session"
            run.mkdir(); session.mkdir()
            source = REAL / "pilot1_explorer"
            session_manifest = json.loads((source / "manifest.json").read_text())
            (session / "manifest.json").write_text(json.dumps(session_manifest))
            # Reuse a real verified transcript to exercise the CLI's chain verification.
            for name in ("transcript.jsonl", "transcript.jsonl.head"):
                (session / name).write_bytes((source / name).read_bytes())
            (run / "run_receipt.json").write_text(json.dumps({"schema_version": 1, "outcome":"COMPLETE"}))
            # Annabelle legacy clause: readable historical artifacts are never relabeled v2.
            with self.assertRaisesRegex(ValueError, "cannot be relabeled"):
                build_entry(run, session)

    def test_content_catalog_rejects_equal_count_replacement_and_declared_change(self):
        b = base("b", coverage={"rooms_visited": 2})
        # Annabelle catalog clause: same-count object replacement changes content identity.
        replacement = json.loads(json.dumps(b["content_catalog"]))
        replacement["objects"][0]["descriptor_sha256"] = "b" * 64
        swapped = base("swapped", coverage={"rooms_visited": 2}, content_catalog=replacement)
        report = compare([b], [swapped])
        self.assertEqual(report["paired_count"], 0)
        self.assertEqual(report["ineligible"][0]["reason"], "CONTENT_CATALOG_MISMATCH")
        changed = base("changed", expected_content_change="remove a room")
        report = compare([b], [changed])
        self.assertEqual(report["paired_count"], 0)
        self.assertIn("NOT_A_LIKE_FOR_LIKE", {item["reason"] for item in report["ineligible"]})

    def test_duplicate_pair_keys_are_order_independent(self):
        b1, b2 = base("b1"), base("b2")
        c1, c2 = base("c1"), base("c2")
        c2["per_mode_verified_instances"] = {"detector": {"FAIL_WITH_NOTHING": 1}}
        first = compare([b1, b2], [c1, c2])
        second = compare([b2, b1], [c2, c1])
        def normalized(report):
            return sorted((row.get("run_id"), row["reason"]) for row in report["ineligible"])
        self.assertEqual(first["paired_count"], 0)
        self.assertEqual(normalized(first), normalized(second))
        self.assertTrue(all(reason == "DUPLICATE_PAIR_KEY" for _, reason in normalized(first)))


if __name__ == "__main__":
    unittest.main()
