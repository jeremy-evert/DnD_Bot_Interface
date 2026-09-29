import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

from playtest.judge import (JUDGE_MODES, JudgeParseError, build_judge_bundle,
                           gate, parse_judge_output, run_judge)
from playtest.transcript import load_transcript


ROOT = Path(__file__).resolve().parents[1]


class JudgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.real = load_transcript(ROOT / "playtest/fixtures/real/pilot1_explorer/transcript.jsonl")
        cls.journal = [json.loads(line) for line in (ROOT / "playtest/fixtures/real/pilot1_explorer/journal.jsonl").read_text().splitlines()]

    def test_gate_accepts_exact_fixture_quote(self):
        row = next(r for r in self.real if r["new_output"])
        quote = row["new_output"].splitlines()[0]
        accepted, discards = gate(self.real, [{"mode": "FALSE_AFFORDANCE", "turn_ids": [row["turn_id"]], "quote": quote, "rationale": "The rendered output supports this observation."}])
        self.assertEqual(len(accepted), 1)
        self.assertEqual(discards, [])

    def test_gate_discards_bad_candidates_and_holistic_fields(self):
        first, second = self.real[0], self.real[1]
        quote_first = first["new_output"].splitlines()[0]
        quote_second = second["new_output"].splitlines()[0]
        candidates = [
            {"mode": "FALSE_AFFORDANCE", "turn_ids": [first["turn_id"]], "quote": "fabricated", "rationale": "bad"},
            {"mode": "FALSE_AFFORDANCE", "turn_ids": [first["turn_id"]], "quote": quote_second, "rationale": "cross turn"},
            {"mode": "FALSE_AFFORDANCE", "turn_ids": [first["turn_id"]], "quote": "", "rationale": "empty"},
            {"mode": "NOT_A_MODE", "turn_ids": [first["turn_id"]], "quote": quote_first, "rationale": "unknown"},
            {"mode": "FALSE_AFFORDANCE", "turn_ids": [999999], "quote": quote_first, "rationale": "bad turn"},
            {"mode": "FALSE_AFFORDANCE", "turn_ids": [True], "quote": quote_first, "rationale": "wrong type"},
            {"mode": "FALSE_AFFORDANCE", "turn_ids": [first["turn_id"]], "quote": quote_first, "rationale": "score", "score": 9},
            {"mode": "FALSE_AFFORDANCE", "turn_ids": [first["turn_id"]], "quote": quote_first, "rationale": "  "},
        ]
        accepted, discards = gate(self.real, candidates)
        self.assertEqual(accepted, [])
        self.assertEqual([item["reason_code"] for item in discards], ["QUOTE_NOT_IN_CITED_TURN", "QUOTE_NOT_IN_CITED_TURN", "EMPTY_QUOTE", "UNKNOWN_MODE", "BAD_TURN", "BAD_TURN", "MALFORMED", "MALFORMED"])

    def test_parse_fenced_and_prose_json_and_malformed(self):
        self.assertEqual(parse_judge_output('```json\n[]\n```'), [])
        self.assertEqual(parse_judge_output('Here is the result:\n[ {"ok": true} ]'), [{"ok": True}])
        with self.assertRaises(JudgeParseError):
            parse_judge_output("no list here [oops]")

    def test_bundle_is_blind_and_journal_is_untrusted(self):
        bundle = build_judge_bundle(self.real[:2], self.journal[:1])
        for forbidden in ("chain_hash", "prev_chain_hash", "game_sha", "/mnt/", "playtest", "dnd_combat"):
            self.assertNotIn(forbidden, bundle)
        self.assertIn("PLAYER NOTES (UNTRUSTED", bundle)
        self.assertIn("[T0]", bundle)

    def _fake(self, body):
        temp = Path(self.temp.name)
        script = temp / "fake_judge.py"
        script.write_text("#!/usr/bin/env python3\n" + textwrap.dedent(body), encoding="utf-8")
        return [sys.executable, str(script)]

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def test_run_judge_isolated_cwd_and_receipts_gate_results(self):
        row = self.real[0]
        candidate = {"mode": "FALSE_AFFORDANCE", "turn_ids": [row["turn_id"]], "quote": row["new_output"].splitlines()[0], "rationale": "quoted"}
        bad = {"mode": "FALSE_AFFORDANCE", "turn_ids": [row["turn_id"]], "quote": "not present", "rationale": "fabricated"}
        stream = [{"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps([candidate, bad])}}]
        body = "import json, os, sys\nassert os.listdir('.') == []\nassert sys.stdin.read()\nprint(json.dumps(" + repr(stream[0]) + "), flush=True)\n"
        receipt = run_judge(self.real, self.journal, Path(self.temp.name) / "run", self._fake(body))
        self.assertEqual(receipt["outcome"], "COMPLETE")
        self.assertEqual(receipt["parse_status"], "OK")
        self.assertEqual(len(receipt["raw_accepted"]), 1)
        self.assertEqual(receipt["discards"][0]["reason_code"], "QUOTE_NOT_IN_CITED_TURN")
        self.assertTrue((Path(self.temp.name) / "run/judge_receipt.json").exists())

    def test_journal_quote_is_never_evidence_and_timeout_is_incomplete(self):
        row = self.real[0]
        note_text = "PLAYER NOTE ONLY CANARY NEVER APPEARS IN TRANSCRIPT"
        journal = [{"turn_id": row["turn_id"], "wanted": note_text}]
        candidate = {"mode": "FALSE_AFFORDANCE", "turn_ids": [row["turn_id"]], "quote": note_text, "rationale": "journal"}
        event = {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps([candidate])}}
        body = "import json, os\nassert os.listdir('.') == []\nprint(json.dumps(" + repr(event) + "))\n"
        receipt = run_judge(self.real, journal, Path(self.temp.name) / "journal_run", self._fake(body))
        self.assertEqual(receipt["raw_accepted"], [])
        self.assertEqual(receipt["discards"][0]["reason_code"], "QUOTE_NOT_IN_CITED_TURN")
        slow = self._fake("import time\ntime.sleep(3)\n")
        timed = run_judge(self.real, None, Path(self.temp.name) / "timeout_run", slow, timeout=.05)
        self.assertEqual(timed["outcome"], "INCOMPLETE_JUDGE")
        self.assertTrue(timed["timeout"])


if __name__ == "__main__":
    unittest.main()
