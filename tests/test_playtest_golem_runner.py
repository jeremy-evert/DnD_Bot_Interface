import hashlib
import json
import os
import hashlib
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

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
                         ["CLOSED", "inbox", "journal.jsonl", "outbox", "playctl"])
        with self.assertRaises(ValueError):
            run_golem(session, Path(__file__).resolve().parents[1] / "bad-capsule", golem_cmd=["false"])
        with self.assertRaises(ValueError):
            run_golem(session, session / "inside", golem_cmd=["false"])

    def test_capsule_and_launcher_are_owner_only(self):
        body = '''
            import os
            assert os.stat(".").st_mode & 0o777 == 0o700
            assert os.stat("playctl").st_mode & 0o777 == 0o700
            '''
        _, run, _ = self.run_fake(body)
        capsule = run / "capsule"
        self.assertEqual(capsule.stat().st_mode & 0o777, 0o500)
        self.assertEqual((capsule / "playctl").stat().st_mode & 0o777, 0o500)

    def test_concurrent_playctl_allocates_distinct_requests_and_replies(self):
        capsule = self.base / "ipc"
        inbox, outbox = capsule / "inbox", capsule / "outbox"
        inbox.mkdir(parents=True); outbox.mkdir()
        launcher = capsule / "playctl"
        launcher.write_text(_playctl_source(nonce="test-nonce")); launcher.chmod(0o700)
        finished = threading.Event()
        def controller():
            seen = set()
            deadline = time.monotonic() + 5
            while len(seen) < 12 and time.monotonic() < deadline:
                for request in inbox.glob("*.json"):
                    if request.name in seen: continue
                    seen.add(request.name)
                    data = json.loads(request.read_text())
                    (outbox / request.name).write_text(json.dumps({"output":"ok", "turn":1, "terminated":None,
                                                                    "request_id":data["request_id"], "nonce":"test-nonce"}))
                time.sleep(.002)
            finished.set()
        worker = threading.Thread(target=controller); worker.start()
        def invoke(n):
            return subprocess.run([str(launcher), "step", json.dumps(["look", str(n)])], capture_output=True, text=True)
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(invoke, range(12)))
        worker.join(6)
        requests = list(inbox.glob("[0-9][0-9][0-9][0-9].json"))
        replies = list(outbox.glob("[0-9][0-9][0-9][0-9].json"))
        self.assertTrue(finished.is_set())
        self.assertTrue(all(result.returncode == 0 for result in results), [(r.returncode, r.stdout) for r in results])
        self.assertEqual(len(requests), 12)
        self.assertEqual(len({p.name for p in requests}), 12)
        self.assertEqual(len(replies), 12)
        self.assertEqual({json.loads(p.read_text())['request_id'] for p in replies}, {p.stem for p in requests})

    def test_precreated_outbox_reply_is_not_trusted(self):
        body = '''
            from pathlib import Path
            import json, shlex, subprocess
            Path("outbox/0001.json").write_text(json.dumps({"output":"FORGED", "turn":1, "terminated":None}))
            result = subprocess.run("./playctl step " + shlex.quote(json.dumps(["look"])), shell=True, capture_output=True, text=True)
            assert result.stdout != "FORGED", result.stdout
            '''
        _, run, receipt = self.run_fake(body)
        self.assertNotIn("FORGED", (run / "stdout.log").read_text())

    def test_outbox_symlink_is_not_trusted(self):
        body = '''
            from pathlib import Path
            import json, shlex, subprocess
            Path("forged.json").write_text(json.dumps({"output":"FORGED", "turn":1, "terminated":None}))
            Path("outbox/0001.json").symlink_to("../forged.json")
            result = subprocess.run("./playctl step " + shlex.quote(json.dumps(["look"])), shell=True, capture_output=True, text=True)
            assert result.returncode != 0
            assert result.stdout != "FORGED"
            '''
        _, run, receipt = self.run_fake(body)
        self.assertNotIn("FORGED", (run / "stdout.log").read_text())

    def test_receipt_artifact_hashes_are_final_after_child_exit(self):
        session, run, receipt = self.run_fake('''
            import json, shlex, subprocess
            subprocess.run("./playctl step " + shlex.quote(json.dumps(["attack"])), shell=True)
            ''')
        self.assertTrue(receipt.get("receipt_finalized_after_child_exit"))
        self.assertEqual(receipt["stdout_sha256"], hashlib.sha256((run / "stdout.log").read_bytes()).hexdigest())
        self.assertEqual(receipt["stderr_sha256"], hashlib.sha256((run / "stderr.log").read_bytes()).hexdigest())
        self.assertEqual(receipt["journal_sha256"], hashlib.sha256((run / "capsule/journal.jsonl").read_bytes()).hexdigest())

    def test_descendant_cannot_append_journal_after_termination(self):
        _, run, receipt = self.run_fake('''
            import json, shlex, subprocess, sys
            code = 'import time; time.sleep(.25); open("journal.jsonl","a").write("LATE\\\\n")'
            subprocess.Popen([sys.executable, "-c", code])
            subprocess.run("./playctl step " + shlex.quote(json.dumps(["attack"])), shell=True)
            ''')
        before = (run / "capsule/journal.jsonl").read_bytes()
        time.sleep(.35)
        self.assertEqual((run / "capsule/journal.jsonl").read_bytes(), before)
        self.assertEqual(receipt["journal_sha256"], hashlib.sha256(before).hexdigest())

    def test_game_manifest_covers_all_python_and_changes_invalidate_run(self):
        from playtest import golem_runner
        source = Path(__file__).resolve().parents[1] / "dnd_combat/world.py"
        original = source.read_bytes()
        manifest = golem_runner._game_manifest
        calls = 0
        def mutate_between():
            nonlocal calls
            calls += 1
            result = manifest()
            if calls == 1:
                source.write_bytes(original + b"\n# temporary test mutation\n")
            return result
        try:
            with patch.object(golem_runner, "_game_manifest", side_effect=mutate_between):
                _, _, receipt = self.run_fake("pass\n")
        finally:
            source.write_bytes(original)
        self.assertNotEqual(receipt["game_manifest_start"], receipt["game_manifest_end"])
        self.assertEqual(receipt["outcome"], "GAME_MODIFIED_DURING_RUN")

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
        self.assertEqual(result.returncode, 2)

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
