"""R2 production seam: shipped runner -> judge -> CLI ledger -> paired report."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

from playtest.judge import run_judge
from playtest.ledger import verify_ledger
from playtest.report import compare, render_markdown
from playtest.run_ledger_cli import build_entry
from playtest.schema import (canonical_json, load_manifest, load_run_receipt, strict_json_loads)
from playtest.transcript import load_transcript
from playtest.golem_runner import run_golem

ROOT = Path(__file__).resolve().parents[1]
SEALED = "sealed persona text: patient and observant"


class PlaytestSeamTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def _golem(self, path):
        path.write_text(textwrap.dedent('''\
            import json, shlex, subprocess
            print(json.dumps({"type":"command", "command":"./playctl step"}), flush=True)
            frames = [["attack"], ["attack"], ["move", "east"], ["look"]]
            for number, frame in enumerate(frames, 1):
                subprocess.run("./playctl step " + shlex.quote(json.dumps(frame)), shell=True)
                note = {"turn_id":number,"wanted":"advance","surprise":"","continue":1,
                        "reason":"The next room may matter.","unsupported_intent":None}
                subprocess.run("./playctl journal " + shlex.quote(json.dumps(note)), shell=True)
        '''), encoding="utf-8")
        return [sys.executable, str(path)]

    def _judge_command(self, path, candidates):
        event = {"type":"item.completed", "item":{"type":"agent_message", "text":json.dumps(candidates)}}
        path.write_text("import json\nprint(json.dumps(" + repr(event) + "), flush=True)\n", encoding="utf-8")
        return [sys.executable, str(path)]

    def _verifier_command(self, path, quote):
        output = {"supports":True, "reason":"The cited room detail supports the candidate.", "quote":quote}
        event = {"type":"item.completed", "item":{"type":"agent_message", "text":json.dumps(output)}}
        path.write_text("import json\nprint(json.dumps(" + repr(event) + "), flush=True)\n", encoding="utf-8")
        return [sys.executable, str(path)]

    def _dispatch(self, label, *, holdout=False):
        session, run = self.root / f"{label}-session", self.root / f"{label}-run"
        receipt = run_golem(session, run, persona="explorer", persona_prompt_text=(SEALED if holdout else "public explorer persona"),
            is_holdout=holdout, holdout_prompt_text=SEALED if holdout else None,
            seed=41, name="Ada", character="fighter", turn_cap=4,
            measurement_policy="detector_and_judge" if not holdout else "detector_only",
            golem_cmd=self._golem(self.root / f"{label}-golem.py"))
        return session, run, receipt

    def _judge(self, session, run, label, candidates):
        records = load_transcript(session / "transcript.jsonl")
        receipt = strict_json_loads((run / "run_receipt.json").read_text())
        journal_sha = hashlib.sha256((run / "capsule/journal.jsonl").read_bytes()).hexdigest()
        verifier_cmd = (self._verifier_command(self.root / f"{label}-verifier.py", candidates[0]["quote"])
                        if candidates else None)
        journal = [json.loads(line) for line in (run/"capsule/journal.jsonl").read_text().splitlines()]
        return run_judge(records, journal, run / f"{label}-judge",
            judge_cmd=self._judge_command(self.root / f"{label}-judge.py", candidates),
            verifier_cmd=verifier_cmd,
            run_id=receipt["run_id"], manifest_sha256=receipt["manifest_sha256"],
            transcript_head_chain_hash=receipt["transcript_head_chain_hash"], journal_sha256=journal_sha)

    def _add(self, session, run, ledger, judge_path):
        result = subprocess.run([sys.executable, "-m", "playtest.run_ledger_cli", "add",
            "--run-dir", str(run), "--session-dir", str(session), "--ledger", str(ledger),
            "--judge-receipt", str(judge_path)], cwd=ROOT, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE":"1"})
        self.assertEqual(result.returncode, 0, result.stderr)
        return verify_ledger(ledger)[-1]

    def test_runner_judge_ledger_report_contract_v2(self):
        left_session, left_run, left_receipt = self._dispatch("left")
        right_session, right_run, right_receipt = self._dispatch("right")
        left_manifest, right_manifest = load_manifest(left_session / "manifest.json"), load_manifest(right_session / "manifest.json")
        left_records = load_transcript(left_session / "transcript.jsonl")
        right_records = load_transcript(right_session / "transcript.jsonl")

        # Assertions 1–2: setup/action shape, frozen scenario identity, and recomputed artifacts.
        for session, run, receipt, manifest, records in (
            (left_session,left_run,left_receipt,left_manifest,left_records),
            (right_session,right_run,right_receipt,right_manifest,right_records)):
            self.assertEqual([row["frame_kind"] for row in records], ["setup", "action", "action", "action", "action"])
            self.assertEqual(receipt["turns"], 4); self.assertEqual(receipt["transcript_record_count"], 5)
            self.assertEqual(receipt["turn_cap"], 4); self.assertEqual(receipt["stop_reason"], "cap")
            self.assertFalse(receipt["is_holdout"]); self.assertIsNone(receipt["holdout_prompt_sha256"])
            self.assertEqual(manifest["game_sha"], receipt["game_sha"])
            self.assertEqual(manifest["harness_sha"], receipt["harness_sha"])
            self.assertEqual(manifest["game_revision"], receipt["game_revision"])
            self.assertEqual(manifest["harness_revision"], receipt["harness_revision"])
            self.assertEqual(manifest["severity_taxonomy_version"], receipt["severity_taxonomy_version"])
            self.assertEqual(receipt["transcript_head_chain_hash"], records[-1]["chain_hash"])
            for name, field in (("stdout.log","stdout_sha256"),("stderr.log","stderr_sha256"),
                                ("audit.log","audit_log_sha256"),("capsule/journal.jsonl","journal_sha256")):
                self.assertEqual(hashlib.sha256((run/name).read_bytes()).hexdigest(), receipt[field])
            self.assertEqual(receipt["run_outcome"], "COMPLETE")
            catalog = manifest["content_catalog"]
            self.assertIn("entry", catalog["room_ids"])
            self.assertIn("entry", catalog["initial_reachability"])
            self.assertTrue(all(set(edge) == {"from", "direction", "to"} for edge in catalog["exits"]))
            initial_object = records[0]["snapshot"]["rooms"]["stores"]["objects"][0]
            self.assertTrue({"description", "aliases", "takeable"} <= set(initial_object))
        self.assertEqual(left_receipt["seed"], 41); self.assertEqual(left_manifest["persona_id"], "explorer")

        # Assertion 3: the real judge wrapper validates one candidate and discards the title quote.
        cited = next(row for row in left_records if row["turn_id"] == 3)
        quote = "You spot healing potion."
        self.assertIn(quote, cited["new_output"])
        good = {"mode":"FALSE_AFFORDANCE", "turn_ids":[3], "quote":quote,
                "rationale":"The world detail offers a relevant affordance."}
        bad = {"mode":"FALSE_AFFORDANCE", "turn_ids":[0], "quote":"=== D&D 0.6: The Mossy Delve ===",
               "rationale":"The title claims a false affordance."}
        left_judge = self._judge(left_session,left_run,"left",[good,bad])
        right_judge = self._judge(right_session,right_run,"right",[good,bad])
        for result in (left_judge,right_judge):
            self.assertEqual(result["judge_outcome"], "COMPLETE")
            self.assertEqual(result["severity_taxonomy_version"], left_manifest["severity_taxonomy_version"])
            self.assertEqual(result["audit_status"], "CLEAN")
            self.assertEqual(len(result["counted"]), 1)
            self.assertEqual(result["discarded_judge_claims"], 1)

        # Assertion 4: shipped CLI validates artifacts and appends the controller entry.
        left_ledger, right_ledger = self.root/"left-ledger.jsonl", self.root/"right-ledger.jsonl"
        left_entry = self._add(left_session,left_run,left_ledger,left_run/"left-judge/judge_receipt.json")
        right_entry = self._add(right_session,right_run,right_ledger,right_run/"right-judge/judge_receipt.json")
        self.assertEqual(left_entry["schema_version"], 2)
        self.assertEqual(left_entry["severity_taxonomy_version"], left_manifest["severity_taxonomy_version"])
        self.assertEqual(left_entry["judge_status"], "COMPLETE")
        self.assertEqual(left_entry["judge_counted_instances"], 1)
        self.assertEqual(left_entry["discarded_judge_claims"], 1)
        self.assertEqual(left_entry["per_mode_verified_instances"]["judge"]["FALSE_AFFORDANCE"], 1)
        self.assertEqual(left_entry["game_sha"], left_manifest["game_sha"])
        self.assertEqual(left_entry["harness_sha"], left_manifest["harness_sha"])
        static = [item for item in left_entry["verified_instances"] if item["evidence_kind"] == "static_probe"]
        self.assertTrue(static)
        probe_file = left_run/"static_probe_evidence.json"
        probe_data = json.loads(probe_file.read_text())
        probe_digests = {hashlib.sha256(json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
                         for item in probe_data["probes"]}
        self.assertTrue(all(item["evidence_sha256"] in probe_digests for item in static))

        # Assertion 5: production report pairs by the full identity/catalog, with action denominators.
        report = compare([left_entry],[right_entry])
        markdown = render_markdown(report)
        self.assertEqual(report["paired_count"], 1); self.assertEqual(report["ineligible"], [])
        mode = report["per_mode"]["judge:FALSE_AFFORDANCE"]
        self.assertEqual(mode["baseline_count"], 1); self.assertEqual(mode["candidate_count"], 1)
        self.assertEqual(mode["baseline_rate_per_100"], 25.0)
        self.assertEqual(left_entry["turns"], 4); self.assertEqual(right_entry["turns"], 4)
        self.assertIn("judge:FALSE_AFFORDANCE", markdown)
        self.assertNotIn("detector:CONVENTION_CLASH", report["per_mode"])
        self.assertIn("detector:CONVENTION_CLASH", report["static_probe_counts"])
        self.assertIn("Static probe instances (not action-turn rates)", markdown)

        # Assertion 6: sealed holdout wording stays private while its identity remains explicit.
        hold_session, hold_run, hold_receipt = self._dispatch("holdout", holdout=True)
        hold_entry = build_entry(hold_run, hold_session)
        self.assertTrue(hold_entry["is_holdout"])
        self.assertEqual(hold_entry["holdout_prompt_sha256"], hold_entry["persona_prompt_sha256"])
        self.assertNotIn(SEALED, json.dumps(load_manifest(hold_session/"manifest.json")))
        self.assertNotIn(SEALED, json.dumps(hold_receipt))
        self.assertNotIn(SEALED, json.dumps(hold_entry))

        # Assertion 7: each historical boundary defect is restored alone and rejected at its owner.
        # Revision used as digest.
        bad_receipt = json.loads((left_run/"run_receipt.json").read_text())
        bad_receipt["game_sha"] = bad_receipt["game_revision"]
        with self.assertRaisesRegex(ValueError, "game digest mismatch"):
            from playtest.schema import validate_run_receipt
            validate_run_receipt(bad_receipt)
        # Setup-inclusive turns.
        bad_receipt = json.loads((left_run/"run_receipt.json").read_text()); bad_receipt["turns"] = 5
        with self.assertRaisesRegex(ValueError, "setup record"):
            validate_run_receipt(bad_receipt)
        # Absent cap and seed.
        bad_receipt = json.loads((left_run/"run_receipt.json").read_text()); del bad_receipt["turn_cap"]
        with self.assertRaisesRegex(ValueError, "missing=.*turn_cap"):
            validate_run_receipt(bad_receipt)
        bad_manifest = json.loads((left_session/"manifest.json").read_text()); del bad_manifest["seed"]
        with self.assertRaisesRegex(ValueError, "missing=.*seed"):
            from playtest.schema import validate_manifest
            validate_manifest(bad_manifest)
        # Wrong judge binding is validly shaped but cannot transfer into the ledger.
        bad_judge_path = self.root/"wrong-binding.json"
        bad_judge = json.loads((left_run/"left-judge/judge_receipt.json").read_text()); bad_judge["run_id"] = "other-run"
        bad_judge_path.write_text(canonical_json(bad_judge) + "\n")
        invalid_entry = build_entry(left_run,left_session,judge_receipt_path=bad_judge_path)
        self.assertEqual(invalid_entry["judge_status"], "INVALID")
        self.assertFalse(invalid_entry["eligibility"]["comparison_eligible"])
        # Dropped normalization loses the expected counted instance.
        dropped_path = self.root/"dropped-normalization.json"
        dropped = json.loads((left_run/"left-judge/judge_receipt.json").read_text()); dropped["counted"] = []
        dropped_path.write_text(canonical_json(dropped) + "\n")
        dropped_entry = build_entry(left_run,left_session,judge_receipt_path=dropped_path)
        with self.assertRaisesRegex(AssertionError, "dropped judge normalization"):
            self.assertEqual(dropped_entry["judge_counted_instances"], 1, "dropped judge normalization")

        # Assertion 8: [] is a complete zero-candidate result; process failure is incomplete.
        zero = self._judge(left_session,left_run,"zero",[])
        self.assertEqual(zero["judge_outcome"], "COMPLETE"); self.assertEqual(zero["counted"], [])
        zero_entry = build_entry(left_run,left_session,judge_receipt_path=left_run/"zero-judge/judge_receipt.json")
        failed_cmd = self.root/"failed-judge.py"
        failed_cmd.write_text("raise SystemExit(9)\n", encoding="utf-8")
        base_receipt = strict_json_loads((left_run/"run_receipt.json").read_text())
        journal = [json.loads(line) for line in (left_run/"capsule/journal.jsonl").read_text().splitlines()]
        incomplete = run_judge(left_records, journal, left_run/"incomplete-judge", judge_cmd=[sys.executable,str(failed_cmd)],
            run_id=base_receipt["run_id"], manifest_sha256=base_receipt["manifest_sha256"],
            transcript_head_chain_hash=base_receipt["transcript_head_chain_hash"],
            journal_sha256=base_receipt["journal_sha256"])
        self.assertEqual(incomplete["judge_outcome"], "INCOMPLETE_JUDGE")
        incomplete_entry = build_entry(left_run,left_session,judge_receipt_path=left_run/"incomplete-judge/judge_receipt.json")
        self.assertEqual(zero_entry["judge_status"], "COMPLETE")
        self.assertEqual(zero_entry["judge_counted_instances"], 0)
        self.assertEqual(incomplete_entry["judge_status"], "INCOMPLETE")
        self.assertIsNone(incomplete_entry["judge_counted_instances"])


if __name__ == "__main__":
    unittest.main()
