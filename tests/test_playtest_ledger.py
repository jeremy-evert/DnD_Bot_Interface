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
    values = dict(run_id=run_id, game_sha="g", harness_sha="h", detector_version=DETECTOR_VERSION,
                  persona_id="p", seed=1, turn_cap=35, narrator_policy="plain", run_outcome="COMPLETE")
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
        b = base("b")
        for field, value in (("persona_id", "other"), ("seed", 9), ("turn_cap", 20),
                             ("narrator_policy", "live"), ("is_holdout", True)):
            report = compare([b], [base("c", **{field: value})])
            self.assertEqual(report["paired_count"], 0, field)

    def test_poisson_known_values(self):
        low, high = poisson_ci(10)
        self.assertAlmostEqual(low, 4.795, delta=.02)
        self.assertAlmostEqual(high, 18.390, delta=.03)
        self.assertEqual(poisson_ci(0)[0], 0)

    def test_holdout_does_not_store_prompt_text(self):
        entry = make_entry(run_id="x", game_sha="g", harness_sha="h", detector_version="1", persona_id="p", seed=1,
                           is_holdout=True, holdout_prompt_sha256="a" * 64, instances=[])
        self.assertNotIn("prompt", json.dumps(entry).lower().replace("holdout_prompt_sha256", ""))

    def test_four_real_fixtures_report_raw_counts_without_composite(self):
        entries = []
        for name in sorted(p.name for p in REAL.iterdir() if p.is_dir()):
            folder = REAL / name
            records = load_transcript(folder / "transcript.jsonl")
            journal = [json.loads(line) for line in (folder / "journal.jsonl").read_text().splitlines()]
            manifest = json.loads((folder / "manifest.json").read_text())
            instances = run_all(records, journal)
            entries.append(make_entry(run_id=name, game_sha=manifest["game_sha"], harness_sha=manifest["harness_sha"],
                detector_version=DETECTOR_VERSION, persona_id=manifest["persona_id"], seed=manifest["seed"],
                narrator_policy=manifest["narrator_policy"], run_outcome="COMPLETE", turns=len(records), instances=instances,
                curiosity=curiosity_events(records), coverage={**session_facts(records), "objects_touched": 2, "encounters_faced": 1}))
        report = compare(entries, entries)
        rendered = render_markdown(report)
        self.assertIn("Baseline raw", rendered)
        self.assertRegex(rendered, r"\| detector:[A-Z_]+ \| [0-9]+ \| [0-9]+ \|")
        self.assertNotIn("score", rendered.lower())
        self.assertEqual(report["paired_count"], 4)

    def test_cli_recomputes_fabricated_receipt_and_marks_mismatches(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); run, session = root / "run", root / "session"
            run.mkdir(); session.mkdir()
            source = REAL / "pilot1_explorer"
            session_manifest = json.loads((source / "manifest.json").read_text())
            (session / "manifest.json").write_text(json.dumps(session_manifest))
            # Reuse a real verified transcript to exercise the CLI's chain verification.
            for name in ("transcript.jsonl", "transcript.jsonl.head"):
                (session / name).write_bytes((source / name).read_bytes())
            (run / "run_receipt.json").write_text(json.dumps({"outcome":"COMPLETE", "receipt_finalized_after_child_exit":True,
              "turns_taken":1, "turn_cap":35, "game_sha":"WRONG_GAME_SHA", "harness_sha":"WRONG_HARNESS_SHA",
              "transcript_head_chain_hash":"f"*64}))
            entry = build_entry(run, session)
            self.assertEqual(entry["turns"], 22)
            self.assertNotEqual(entry["transcript_head_chain_hash"], "f"*64)
            self.assertFalse(entry["eligibility"]["comparison_eligible"])
            self.assertTrue(entry["eligibility"]["reason_code"].startswith("RECEIPT_MISMATCH:"))
            ledger = root / "ledger.jsonl"
            result = subprocess.run([sys.executable, "-m", "playtest.run_ledger_cli", "add", "--run-dir", str(run),
                "--session-dir", str(session), "--ledger", str(ledger)], cwd=ROOT, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env={**os.environ, "PYTHONDONTWRITEBYTECODE":"1"})
            self.assertEqual(result.returncode, 0, result.stderr)
            stored = verify_ledger(ledger)[0]
            self.assertFalse(stored["eligibility"]["comparison_eligible"])
            self.assertEqual(stored["eligibility"]["reason_code"], "RECEIPT_MISMATCH:game_sha")
            (run / "run_receipt.json").write_text(json.dumps({"outcome":"COMPLETE", "turn_cap":35,
              "game_sha":session_manifest["game_sha"], "harness_sha":session_manifest["harness_sha"]}))
            older = build_entry(run, session)
            self.assertEqual(older["eligibility"]["reason_code"], "RECEIPT_NOT_FINALIZED")

    def test_content_inventory_loss_and_expected_change(self):
        b = base("b", content_inventory={"total_rooms": 8, "total_objects": 4, "total_takeables": 2, "total_enemies": 3, "total_exits": 9}, coverage={"rooms_visited": 2})
        smaller = base("small", content_inventory={"total_rooms": 7, "total_objects": 4, "total_takeables": 2, "total_enemies": 3, "total_exits": 9}, coverage={"rooms_visited": 2})
        report = compare([b], [smaller])
        self.assertEqual(report["paired_count"], 0)
        self.assertEqual(report["ineligible"][0]["reason"], "COMPARISON_INELIGIBLE_CONTENT_LOSS")
        changed = base("changed", content_inventory=smaller["content_inventory"], expected_content_change="remove a room")
        report = compare([b], [changed])
        self.assertEqual(report["paired_count"], 0)
        self.assertEqual(report["ineligible"][0]["reason"], "NOT_A_LIKE_FOR_LIKE")

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
