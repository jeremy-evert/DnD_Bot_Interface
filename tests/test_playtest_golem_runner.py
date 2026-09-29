import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import textwrap
import unittest

from playtest.golem_prompt import build_prompt
from playtest.golem_runner import audit_commands, run_golem, validate_journal, _playctl_source
from playtest.transcript import verify_chain


class GolemRunnerTests(unittest.TestCase):
    runs = 0
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def fake(self, body, emit_event=True):
        path = self.base / "fake_golem.py"
        event = 'print(__import__("json").dumps({"type":"command","command":"./playctl step [\\\"look\\\"]"}), flush=True)\n' if emit_event else ""
        path.write_text("#!/usr/bin/env python3\n" + event + textwrap.dedent(body), encoding="utf-8")
        path.chmod(0o755)
        return [sys.executable, str(path)]

    def run_fake(self, body, *, cap=35, timeout=5, event_log=None, emit_event=True):
        type(self).runs += 1
        session, run = self.base / f"session-{self.runs}", self.base / f"run-{self.runs}"
        receipt = run_golem(session, run, golem_cmd=self.fake(body, emit_event=emit_event), turn_cap=cap,
                            timeout=timeout, event_log=event_log)
        return session, run, receipt

    def test_real_playctl_frames_chain_and_journal(self):
        session, run, receipt = self.run_fake('''
            import json, shlex, subprocess
            def call(cmd): return subprocess.run(cmd, shell=True)
            frames = [["attack"], ["attack"], ["take", "goblin's brass ring"], ["move", "east"], ["look"], ["move", "west"], ["move", "east"]]
            for n, frame in enumerate(frames):
                call("./playctl step " + shlex.quote(json.dumps(frame)))
                call("./playctl journal " + shlex.quote(json.dumps({"turn_id": n+1, "wanted":"advance", "surprise":"", "continue":1, "reason":"testing", "unsupported_intent":None})))
            ''' )
        rows = verify_chain(session / "transcript.jsonl")
        self.assertGreater(len(rows), 5)
        self.assertEqual(receipt["outcome"], "COMPLETE")
        self.assertEqual(len((run / "capsule/journal.jsonl").read_text().splitlines()), 7)
        self.assertTrue(all(json.loads(line)["continue"] == 1 for line in (run / "capsule/journal.jsonl").read_text().splitlines()))

    def test_audit_flags_forbidden_reference_and_clean_events_pass(self):
        hit = [{"command": "cat /mnt/nora/git/DnD_Bot_Interface/dnd_combat/adventure.py"}]
        self.assertTrue(audit_commands(hit))
        self.assertFalse(audit_commands([{"command": "./playctl step [\\\"look\\\"]"}], self.base / "capsule"))
        events = self.base / "events.jsonl"
        events.write_text(json.dumps(hit[0]) + "\n")
        _, _, receipt = self.run_fake("pass\n", event_log=events)
        self.assertEqual(receipt["outcome"], "BLINDNESS_VIOLATED")

    def test_capsule_is_minimal_and_cannot_be_under_repo_or_session(self):
        session, run, _ = self.run_fake("pass\n")
        self.assertEqual(sorted(p.name for p in (run / "capsule").iterdir()),
                         ["inbox", "journal.jsonl", "outbox", "playctl"])
        with self.assertRaises(ValueError):
            run_golem(session, Path(__file__).resolve().parents[1] / "bad-capsule", golem_cmd=["false"])
        with self.assertRaises(ValueError):
            run_golem(session, session / "inside", golem_cmd=["false"])

    def test_cap_and_stall_are_controller_terminations(self):
        _, _, capped = self.run_fake('''
            import json, shlex, subprocess
            for n in range(5):
                subprocess.run("./playctl step " + shlex.quote(json.dumps(["attack"])), shell=True)
            ''', cap=2)
        self.assertEqual(capped["termination"], "cap")
        _, _, stalled = self.run_fake('''
            import json, shlex, subprocess
            for n in range(4):
                subprocess.run("./playctl step " + shlex.quote(json.dumps(["look"])), shell=True)
            ''')
        self.assertEqual(stalled["termination"], "stalled")

    def test_timeout_kills_golem_and_leaves_verifiable_transcript(self):
        session, run, receipt = self.run_fake("import time\ntime.sleep(10)\n", timeout=.1)
        self.assertEqual(receipt["outcome"], "INCOMPLETE_DISPATCH")
        self.assertTrue(receipt["timeout"])
        self.assertTrue(verify_chain(session / "transcript.jsonl"))

    def test_forged_capsule_transcript_does_not_change_canonical_chain(self):
        body = '''
            from pathlib import Path
            Path("transcript.jsonl").write_text("forged")
            '''
        session, run, _ = self.run_fake(body)
        self.assertEqual((run / "capsule/transcript.jsonl").read_text(), "forged")
        rows = verify_chain(session / "transcript.jsonl")
        receipt = json.loads((run / "run_receipt.json").read_text())
        self.assertEqual(rows[-1]["chain_hash"], receipt["transcript_head_chain_hash"])

    def test_bad_journal_rejected_and_nothing_appended(self):
        body = '''
            import subprocess
            result = subprocess.run("./playctl journal '{bad json'", shell=True)
            assert result.returncode != 0
            '''
        _, run, _ = self.run_fake(body)
        self.assertEqual((run / "capsule/journal.jsonl").read_text(), "")

    def test_capsule_launcher_has_no_repository_or_session_knowledge(self):
        session, run, _ = self.run_fake("pass\n")
        source = (run / "capsule/playctl").read_text()
        self.assertNotIn(str(Path(__file__).resolve().parents[1]), source)
        self.assertNotIn(str(session), source)
        self.assertNotIn("sys.path.insert", source)
        self.assertNotIn("playtest.golem_runner", source)

    def test_launcher_journal_validator_matches_authority(self):
        generated = {}
        generated["__file__"] = str(self.base / "capsule" / "playctl")
        exec(_playctl_source(), generated)
        valid = [
            {"turn_id": 1, "wanted": "advance", "surprise": "", "continue": 1, "reason": "ok", "unsupported_intent": None},
            {"turn_id": 2, "wanted": "", "surprise": "a", "continue": 0, "reason": "", "unsupported_intent": "fly"},
        ]
        invalid = [
            {}, {"turn_id": True, "wanted": "", "surprise": "", "continue": 1, "reason": "", "unsupported_intent": None},
            {"turn_id": 1, "wanted": 3, "surprise": "", "continue": 1, "reason": "", "unsupported_intent": None},
            {"turn_id": 1, "wanted": "", "surprise": "", "continue": 2, "reason": "", "unsupported_intent": None},
            {"turn_id": 1, "wanted": "", "surprise": "", "continue": 1, "reason": "", "unsupported_intent": 4},
            {"turn_id": 1, "wanted": "", "surprise": "", "continue": 1, "reason": "", "unsupported_intent": None, "extra": 1},
        ]
        for entry in valid + invalid:
            def accepts(fn):
                try: fn(entry)
                except (ValueError, TypeError): return False
                return True
            self.assertEqual(accepts(validate_journal), accepts(generated["validate_journal"]), entry)

    def test_stdout_events_are_audited_and_empty_audit_is_unverifiable(self):
        _, _, forbidden = self.run_fake('''
            import json
            print(json.dumps({"type":"tool_call","payload":{"item":{"text":"cat /secret/DnD_Bot_Interface/dnd_combat/adventure.py"}}}))
            ''', emit_event=False)
        self.assertEqual(forbidden["outcome"], "BLINDNESS_VIOLATED")
        _, _, clean = self.run_fake("pass\n")
        self.assertEqual(clean["outcome"], "COMPLETE")
        _, _, empty = self.run_fake("pass\n", emit_event=False)
        self.assertEqual(empty["outcome"], "AUDIT_UNVERIFIABLE")
        self.assertEqual(empty["audit_events_seen"], 0)

    def test_playctl_works_from_a_different_cwd(self):
        session, run, _ = self.run_fake("pass\n")
        launcher = run / "capsule/playctl"
        result = subprocess.run([str(launcher), "journal", json.dumps({"turn_id": 1, "wanted": "", "surprise": "", "continue": 1, "reason": "ok", "unsupported_intent": None})], cwd=self.base, check=False)
        self.assertEqual(result.returncode, 0)

    def test_prompt_supports_sealed_persona_hash_and_no_scoring(self):
        prompt = build_prompt("a sealed persona: cautious and literal", 35)
        self.assertIn("never score or rate", prompt)
        persona_file = self.base / "sealed.txt"
        persona_file.write_text("sealed operator wording")
        session, run = self.base / "sealed_session", self.base / "sealed_run"
        receipt = run_golem(session, run, persona_text="sealed operator wording", golem_cmd=self.fake("pass\n"))
        self.assertNotIn("sealed operator wording", (run / "run_receipt.json").read_text())
        self.assertEqual(receipt["prompt_sha256"], hashlib.sha256((run / "prompt.txt").read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
