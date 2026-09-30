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
import shlex
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

from playtest.golem_prompt import build_prompt
from playtest.golem_runner import audit_commands, run_golem, validate_journal, _playctl_source
from playtest.schema import load_manifest, load_run_receipt
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

    def run_fake(self, body, *, cap=35, timeout=5, event_log=None, emit_event=True,
                 allow_child_failure=False, final_ack_grace=.15):
        type(self).runs += 1
        session, run = self.base / f"session-{self.runs}", self.base / f"run-{self.runs}"
        receipt = run_golem(session, run, golem_cmd=self.fake(body, emit_event=emit_event), turn_cap=cap,
                            timeout=timeout, event_log=event_log, final_ack_grace=final_ack_grace,
                            persona_prompt_text="test public persona",
                            is_holdout=False)
        if not allow_child_failure:
            stderr = (run / "stderr.log").read_text(encoding="utf-8")
            self.assertIn(receipt["exit_code"], (0, -9), f"fake golem exit={receipt['exit_code']} stderr={stderr!r}")
            self.assertNotIn("AssertionError", stderr, f"fake golem exit={receipt['exit_code']} stderr={stderr!r}")
        return session, run, receipt

    def test_real_playctl_frames_chain_and_journal(self):
        session, run, receipt = self.run_fake('''
            import json, shlex, subprocess
            def call(cmd): return subprocess.run(cmd, shell=True)
            frames = [["attack"], ["attack"], ["take", "goblin's brass ring"], ["move", "east"], ["look"], ["move", "west"], ["move", "east"]]
            for n, frame in enumerate(frames):
                call("./playctl step " + shlex.quote(json.dumps(frame)))
                call("./playctl journal " + shlex.quote(json.dumps({"turn_id": n+1, "wanted":"advance", "surprise":"", "continue":1, "reason":"testing", "unsupported_intent":None})))
            ''' , cap=7)  # Contract lifecycle clause: cap is the valid controller-owned stop.
        rows = verify_chain(session / "transcript.jsonl")
        self.assertGreater(len(rows), 5)
        self.assertEqual(receipt["run_outcome"], "COMPLETE")
        self.assertEqual(receipt["sandbox_policy"], "codex workspace-write: writes only under capsule cwd; reads unrestricted (verified by probe evidence/sandbox_probe)")
        # Annabelle v2 receipt clauses: source digests and provenance revisions have distinct fields.
        manifest = load_manifest(session / "manifest.json")
        validated_receipt = load_run_receipt(run / "run_receipt.json")
        self.assertEqual(receipt["game_sha"], manifest["game_sha"])
        self.assertEqual(receipt["harness_sha"], manifest["harness_sha"])
        self.assertIn("game_revision", manifest)
        self.assertIn("harness_revision", manifest)
        self.assertEqual(receipt["transcript_record_count"], receipt["turns"] + 1)
        self.assertEqual(validated_receipt["run_id"], manifest["run_id"])
        self.assertEqual(len((run / "capsule/journal.jsonl").read_text().splitlines()), 7)
        self.assertTrue(all(json.loads(line)["continue"] == 1 for line in (run / "capsule/journal.jsonl").read_text().splitlines()))

    def test_audit_flags_forbidden_reference_and_clean_events_pass(self):
        hit = [{"command": "cat /mnt/nora/git/DnD_Bot_Interface/dnd_combat/adventure.py"}]
        self.assertTrue(audit_commands(hit))
        capsule = self.base / "capsule"
        capsule.mkdir()
        (capsule / "playctl").touch()
        self.assertFalse(audit_commands([{"command": "./playctl step [\\\"look\\\"]"}], capsule))
        shared = self.base / "shared"
        capsule = shared / "capsule"
        session = shared / "capsule-session"
        session.mkdir(parents=True)
        capsule.mkdir()
        (capsule / "playctl").touch()
        self.assertTrue(audit_commands([{"command": f"cat {session}/transcript.jsonl"}], capsule, session))
        replies = shared / "replies"
        replies.mkdir()
        self.assertTrue(audit_commands([{"command": f"cat {replies}/0001.json"}], capsule, session))
        self.assertTrue(audit_commands([{"command": "cat ../replies/0001.json"}], capsule, session))
        self.assertTrue(audit_commands([{"command": "cd .. && cat replies/0001.json"}], capsule, session))
        self.assertFalse(audit_commands([{"command": "cat ./inbox/0001.json"}], capsule, session))
        # A fully resolved path outside protected roots is allowed, even with
        # parent traversal; the auditor is protecting controller/repo evidence.
        self.assertFalse(audit_commands([{"command": "cat ../../etc/hostname"}], capsule, session))
        with patch.dict(os.environ, {"HOME": str(self.base / "home")}):
            self.assertFalse(audit_commands([{"command": "cat $HOME/hostname"}], capsule, session))
            self.assertFalse(audit_commands([{"command": "cat ~/hostname"}], capsule, session))
        unresolved = audit_commands([{"command": "cat ../$AREA/replies/*.json"}], capsule, session)
        self.assertTrue(unresolved)
        self.assertTrue(all(hit.get("reason") == "UNRESOLVED_PATH" for hit in unresolved))
        self.assertTrue(audit_commands([{"command": "cat ../replies/$(printf 0001).json"}], capsule, session))
        self.assertTrue(audit_commands([{"command": "pushd ../replies"}], capsule, session))
        self.assertTrue(audit_commands([{"command": f"./playctl step reads {replies}/0001.json"}], capsule, session))
        self.assertTrue(audit_commands([{"command": f"./playctl step '[\"look\"]'; cat {replies}/0001.json"}], capsule, session))
        self.assertTrue(audit_commands([{"command": f"./playctl step '[\"look\"]'\ncat {replies}/0001.json"}], capsule, session))
        self.assertFalse(audit_commands([{"command": "./playctl step '[\"look\"]'"}], capsule, session))
        self.assertFalse(audit_commands([{"command": "cd capsule && ./playctl step '[\"look\"]'"}], capsule, session))
        self.assertFalse(audit_commands([{"command": "./playctl step '[\"look\"]' | tee x"}], capsule, session))
        self.assertTrue(audit_commands([{"command": "./playctl step '[\"look\"]' | tee " + str(replies / "copy.json")}], capsule, session))
        self.assertTrue(audit_commands([{"command": "./playctl step '[\"look\"]' $(cat " + str(replies / "0001.json") + ")"}], capsule, session))
        events = self.base / "events.jsonl"
        events.write_text(json.dumps(hit[0]) + "\n")
        _, _, receipt = self.run_fake("pass\n", event_log=events)
        self.assertEqual(receipt["run_outcome"], "BLINDNESS_VIOLATED")
        events.write_text(json.dumps({"type": "command", "command": "cat ../$AREA/replies/*.json"}) + "\n")
        _, _, receipt = self.run_fake("pass\n", event_log=events)
        self.assertEqual(receipt["audit_status"], "UNVERIFIABLE")
        self.assertEqual(receipt["run_outcome"], "AUDIT_UNVERIFIABLE")

    def test_real_codex_event_fixtures_audit_clean_and_keep_event_counts(self):
        fixture_dir = Path(__file__).resolve().parents[1] / "playtest/fixtures/real_codex_events"
        fixtures = sorted(fixture_dir.glob("*.jsonl"))
        self.assertEqual(len(fixtures), 3)
        valid_play = '''
            import json, shlex, subprocess
            subprocess.run("./playctl step " + shlex.quote(json.dumps(["look"])), shell=True)
            note = {"turn_id":1,"wanted":"look","surprise":"","continue":1,"reason":"fixture audit","unsupported_intent":None}
            subprocess.run("./playctl journal " + shlex.quote(json.dumps(note)), shell=True)
            '''
        for fixture in fixtures:
            with self.subTest(fixture=fixture.name):
                events = []
                for line in fixture.read_text(encoding="utf-8").splitlines(keepends=True):
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass  # The real 60 KB capture can end mid-record.
                _, _, receipt = self.run_fake(valid_play, cap=1, event_log=fixture)
                self.assertEqual(receipt["audit_status"], "CLEAN")
                self.assertEqual(receipt["run_outcome"], "COMPLETE")
                self.assertEqual(receipt["audit_events_seen"], len(events))
                self.assertEqual(audit_commands(events), [])

    def test_real_codex_wrapped_forbidden_reads_remain_visible(self):
        fixture = Path(__file__).resolve().parents[1] / "playtest/fixtures/real_codex_events/v2_base60_tactician.jsonl"
        original = fixture.read_text(encoding="utf-8")
        for target in ("reply", "session"):
            with self.subTest(target=target):
                next_run = type(self).runs + 1
                path = (self.base / f"run-{next_run}/replies/0000.json" if target == "reply"
                        else self.base / f"session-{next_run}/transcript.jsonl")
                inner = f"cat {shlex.quote(str(path))}"
                # Match the real Codex argv spelling, including double-quoted script.
                wrapped = "/bin/bash -lc " + json.dumps(inner)
                injected = {"type": "item.completed", "item": {
                    "id": "injected-" + target, "type": "command_execution",
                    "command": wrapped, "aggregated_output": "", "exit_code": 0, "status": "completed"}}
                source = self.base / f"{target}-events.jsonl"
                source.write_text(original + json.dumps(injected) + "\n", encoding="utf-8")
                _, _, receipt = self.run_fake("pass\n", event_log=source)
                self.assertEqual(receipt["audit_status"], "VIOLATED")
                self.assertEqual(receipt["run_outcome"], "BLINDNESS_VIOLATED")

    def test_shell_wrappers_preserve_exact_launcher_exemption_and_data_payloads(self):
        capsule = self.base / "capsule"
        capsule.mkdir()
        (capsule / "playctl").touch()
        session = self.base / "session"
        session.mkdir()
        payload = json.dumps(["look", "apostrophe's ../ /mnt/nora/DnD_Bot_Interface/transcript.jsonl ☃"])
        note = json.dumps({"turn_id":1,"wanted":"../ replies/x","surprise":"Iñtërnâtiônàlizætion: /mnt/nora/x",
                           "continue":1,"reason":"apostrophe's path: /tmp/a/../b","unsupported_intent":None})
        script = "./playctl step " + shlex.quote(payload) + " && ./playctl journal " + shlex.quote(note)
        commands = [
            "/bin/bash -lc " + shlex.quote(script),
            "bash -c " + json.dumps(script, ensure_ascii=False),
            "/bin/sh -c " + shlex.quote(script),
            "sh -c " + json.dumps(script, ensure_ascii=False),
            "zsh -lc " + shlex.quote(script),
            "AREA='quoted value' /bin/bash -lc " + json.dumps(script, ensure_ascii=False),
            "MODE=test bash -c " + shlex.quote("sh -c " + shlex.quote(script)),
        ]
        for command in commands:
            with self.subTest(command=command[:45]):
                self.assertEqual(audit_commands([{"command": command}], capsule, session), [])

    def test_wrapped_forbidden_path_and_started_completed_pair_count_once(self):
        capsule = self.base / "capsule"
        capsule.mkdir()
        (capsule / "playctl").touch()
        session = self.base / "session"
        session.mkdir()
        command = "/bin/bash -lc " + shlex.quote("./playctl step '[\"look\"]' && cat " + shlex.quote(str(session / "transcript.jsonl")))
        pair = [{"type": event_type, "item": {"id": "same-command", "type": "command_execution", "command": command}}
                for event_type in ("item.started", "item.completed")]
        hits = audit_commands(pair, capsule, session)
        single = audit_commands(pair[:1], capsule, session)
        self.assertEqual(hits, single)
        self.assertIn("FORBIDDEN_PATH", [hit.get("reason") for hit in hits])

    def test_compound_playctl_then_reply_read_is_audited(self):
        reply = self.base / f"run-{type(self).runs + 1}" / "replies" / "0001.json"
        _, run, receipt = self.run_fake(f'''
            import json, shlex, subprocess
            from pathlib import Path
            reply = Path({str(reply)!r})
            command = "./playctl step " + shlex.quote(json.dumps(["look"])) + "; cat " + shlex.quote(str(reply))
            print(json.dumps({{"type":"command", "command":command}}), flush=True)
            subprocess.run(command, shell=True)
            note = {{"turn_id":1,"wanted":"advance","surprise":"","continue":1,"reason":"test","unsupported_intent":None}}
            subprocess.run("./playctl journal " + shlex.quote(json.dumps(note)), shell=True)
            ''', cap=1)
        self.assertIn('"request_id": "0001"', (run / "stdout.log").read_text())
        self.assertEqual(receipt["audit_status"], "VIOLATED")
        self.assertEqual(receipt["run_outcome"], "BLINDNESS_VIOLATED")

    def test_relative_reply_read_is_audited_from_capsule_cwd(self):
        reply = self.base / f"run-{type(self).runs + 1}" / "replies" / "0001.json"
        _, run, receipt = self.run_fake(f'''
            import json, shlex, subprocess
            from pathlib import Path
            reply = Path({str(reply)!r})
            command = "./playctl step " + shlex.quote(json.dumps(["look"])) + "; cat ../replies/0001.json"
            print(json.dumps({{"type":"command", "command":command}}), flush=True)
            subprocess.run(command, shell=True)
            note = {{"turn_id":1,"wanted":"advance","surprise":"","continue":1,"reason":"test","unsupported_intent":None}}
            subprocess.run("./playctl journal " + shlex.quote(json.dumps(note)), shell=True)
            ''', cap=1)
        self.assertTrue(reply.exists())
        self.assertEqual(receipt["audit_status"], "VIOLATED")
        self.assertEqual(receipt["run_outcome"], "BLINDNESS_VIOLATED")

    def test_capsule_is_minimal_and_cannot_be_under_repo_or_session(self):
        session, run, _ = self.run_fake("pass\n")
        self.assertEqual(sorted(p.name for p in (run / "capsule").iterdir()),
                         ["CLOSED", "inbox", "journal.jsonl", "playctl"])
        self.assertEqual(sorted(p.name for p in (run / "replies").iterdir()), ["0000.json"])
        with self.assertRaises(ValueError):
            run_golem(session, Path(__file__).resolve().parents[1] / "bad-capsule", golem_cmd=["false"],
                      persona_prompt_text="test", is_holdout=False)
        with self.assertRaises(ValueError):
            run_golem(session, session / "inside", golem_cmd=["false"], persona_prompt_text="test", is_holdout=False)

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
        inbox = capsule / "inbox"
        inbox.mkdir(parents=True)
        replies = self.base / "replies"
        replies.mkdir()
        launcher = capsule / "playctl"
        launcher.write_text(_playctl_source(replies_dir=replies, nonce="test-nonce")); launcher.chmod(0o700)
        finished = threading.Event()
        def controller():
            seen = set()
            deadline = time.monotonic() + 5
            while len(seen) < 12 and time.monotonic() < deadline:
                for request in inbox.glob("*.json"):
                    if request.name in seen: continue
                    seen.add(request.name)
                    data = json.loads(request.read_text())
                    (replies / request.name).write_text(json.dumps({"output":"ok", "turn":1, "terminated":None,
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
        reply_files = list(replies.glob("[0-9][0-9][0-9][0-9].json"))
        self.assertTrue(finished.is_set())
        self.assertTrue(all(result.returncode == 0 for result in results), [(r.returncode, r.stdout) for r in results])
        self.assertEqual(len(requests), 12)
        self.assertEqual(len({p.name for p in requests}), 12)
        self.assertEqual(len(reply_files), 12)
        self.assertEqual({json.loads(p.read_text())['request_id'] for p in reply_files}, {p.stem for p in requests})

    def test_precreated_outbox_reply_is_not_trusted(self):
        body = '''
            from pathlib import Path
            import json, shlex, subprocess
            Path("outbox").mkdir()
            Path("outbox/0001.json").write_text(json.dumps({"output":"FORGED", "turn":1, "terminated":None}))
            result = subprocess.run("./playctl step " + shlex.quote(json.dumps(["look"])), shell=True, capture_output=True, text=True)
            assert result.stdout != "FORGED", result.stdout
            '''
        _, run, receipt = self.run_fake(body)
        self.assertNotIn("FORGED", (run / "stdout.log").read_text())

    def test_capsule_forged_reply_is_ignored_and_replies_are_outside_capsule(self):
        body = '''
            from pathlib import Path
            import json, shlex, subprocess
            Path("forged-reply").write_text("FORGED CAPSULE REPLY")
            result = subprocess.run("./playctl step " + shlex.quote(json.dumps(["look"])), shell=True,
                                    capture_output=True, text=True, timeout=1)
            print("FORGED_REPLY_CHECK", result.returncode, result.stdout, flush=True)
            '''
        _, run, _ = self.run_fake(body)
        self.assertNotIn("FORGED CAPSULE REPLY", (run / "stdout.log").read_text())
        self.assertFalse((run / "capsule/outbox").exists())
        self.assertTrue((run / "replies").is_dir())
        self.assertEqual({p.name for p in (run / "replies").iterdir()}, {"0000.json", "0001.json"})

    def test_outbox_symlink_is_not_trusted(self):
        body = '''
            from pathlib import Path
            import json, shlex, subprocess
            Path("forged.json").write_text(json.dumps({"output":"FORGED", "turn":1, "terminated":None}))
            Path("outbox").mkdir()
            Path("outbox/0001.json").symlink_to("../forged.json")
            result = subprocess.run("./playctl step " + shlex.quote(json.dumps(["look"])), shell=True, capture_output=True, text=True)
            assert result.stdout != "FORGED"
            '''
        _, run, receipt = self.run_fake(body, cap=1)
        self.assertEqual(receipt["stop_reason"], "cap")
        self.assertNotIn("FORGED", (run / "stdout.log").read_text())
        self.assertNotIn("FORGED", (run / "replies/0001.json").read_text())

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
        self.assertNotEqual(receipt["game_files_start"], receipt["game_files_end"])
        self.assertEqual(receipt["run_outcome"], "GAME_MODIFIED_DURING_RUN")

    def test_cap_and_stall_are_controller_terminations(self):
        _, _, capped = self.run_fake('''
            import json, shlex, subprocess
            def journal(turn):
                note = {"turn_id":turn,"wanted":"advance","surprise":"","continue":1,"reason":"test","unsupported_intent":None}
                subprocess.run("./playctl journal " + shlex.quote(json.dumps(note)), shell=True)
            for n in range(5):
                subprocess.run("./playctl step " + shlex.quote(json.dumps(["attack"])), shell=True)
                journal(n+1)
            ''', cap=2)
        # Contract distinguishes the stop policy from actual game termination.
        self.assertEqual(capped["stop_reason"], "cap")
        _, _, stalled = self.run_fake('''
            import json, shlex, subprocess
            def journal(turn):
                note = {"turn_id":turn,"wanted":"advance","surprise":"","continue":1,"reason":"test","unsupported_intent":None}
                subprocess.run("./playctl journal " + shlex.quote(json.dumps(note)), shell=True)
            for n in range(4):
                subprocess.run("./playctl step " + shlex.quote(json.dumps(["look"])), shell=True)
                journal(n+1)
            ''')
        self.assertEqual(stalled["stop_reason"], "no_progress")
        self.assertEqual(capped["run_outcome"], "COMPLETE")
        self.assertEqual(stalled["run_outcome"], "COMPLETE")

    def test_final_action_journal_within_grace_completes_dispatch(self):
        import inspect
        from playtest.golem_runner import run_golem
        self.assertEqual(inspect.signature(run_golem).parameters["final_ack_grace"].default, 8.0)
        _, _, receipt = self.run_fake('''
            import json, shlex, subprocess, time
            subprocess.run("./playctl step " + shlex.quote(json.dumps(["attack"])), shell=True)
            time.sleep(.25)
            note = {"turn_id":1,"wanted":"advance","surprise":"","continue":1,"reason":"final ack","unsupported_intent":None}
            subprocess.run("./playctl journal " + shlex.quote(json.dumps(note)), shell=True)
            ''', cap=1, final_ack_grace=1.0)
        self.assertEqual(receipt["stop_reason"], "cap")
        self.assertEqual(receipt["run_outcome"], "COMPLETE")
        self.assertTrue(receipt["journal_consistent"])
        self.assertEqual(receipt["journal_record_count"], 1)

    def test_final_ack_written_during_reply_publication_window_completes_dispatch(self):
        from playtest import golem_runner
        publish = golem_runner._controller_reply
        def delayed_publish(path, value):
            publish(path, value)
            if value.get("terminated") == "cap":
                # Let playctl return to its caller and journal before the
                # controller resumes from reply publication.
                time.sleep(.2)
        with patch.object(golem_runner, "_controller_reply", side_effect=delayed_publish):
            _, _, receipt = self.run_fake('''
                import json, shlex, subprocess
                subprocess.run("./playctl step " + shlex.quote(json.dumps(["attack"])), shell=True)
                note = {"turn_id":1,"wanted":"advance","surprise":"after reply","continue":1,"reason":"final ack","unsupported_intent":None}
                subprocess.run("./playctl journal " + shlex.quote(json.dumps(note)), shell=True)
                ''', cap=1, final_ack_grace=1.0)
        self.assertEqual(receipt["stop_reason"], "cap")
        self.assertEqual(receipt["run_outcome"], "COMPLETE")
        self.assertTrue(receipt["journal_consistent"])
        self.assertEqual(receipt["journal_record_count"], 1)

    def test_prewritten_final_action_journal_is_not_acknowledgement(self):
        _, _, receipt = self.run_fake('''
            import json, shlex, subprocess
            note = {"turn_id":1,"wanted":"advance","surprise":"prewritten","continue":1,"reason":"before terminal reply","unsupported_intent":None}
            subprocess.run("./playctl journal " + shlex.quote(json.dumps(note)), shell=True)
            subprocess.run("./playctl step " + shlex.quote(json.dumps(["attack"])), shell=True)
            ''', cap=1, final_ack_grace=.2)
        self.assertEqual(receipt["journal_record_count"], 1)
        self.assertTrue(receipt["journal_consistent"])
        self.assertEqual(receipt["run_outcome"], "INCOMPLETE_DISPATCH")

    def test_missing_final_action_journal_expires_grace_as_incomplete(self):
        _, _, receipt = self.run_fake('''
            import json, shlex, subprocess, time
            subprocess.run("./playctl step " + shlex.quote(json.dumps(["attack"])), shell=True)
            time.sleep(5)
            ''', cap=1, final_ack_grace=.1)
        self.assertEqual(receipt["stop_reason"], "cap")
        self.assertEqual(receipt["run_outcome"], "INCOMPLETE_DISPATCH")
        self.assertFalse(receipt["journal_consistent"])
        self.assertEqual(receipt["journal_record_count"], 0)

    def test_unexpected_child_signal_after_controller_stop_is_incomplete(self):
        _, _, receipt = self.run_fake('''
            import json, os, shlex, signal, subprocess
            subprocess.run("./playctl step " + shlex.quote(json.dumps(["attack"])), shell=True)
            note = {"turn_id":1,"wanted":"advance","surprise":"","continue":1,"reason":"test","unsupported_intent":None}
            subprocess.run("./playctl journal " + shlex.quote(json.dumps(note)), shell=True)
            os.kill(os.getpid(), signal.SIGKILL)
            ''', cap=1)
        self.assertEqual(receipt["stop_reason"], "cap")
        self.assertEqual(receipt["exit_code"], -9)
        self.assertTrue(receipt["journal_consistent"])
        self.assertEqual(receipt["run_outcome"], "INCOMPLETE_DISPATCH")

    def test_timeout_kills_golem_and_leaves_verifiable_transcript(self):
        session, run, receipt = self.run_fake("import time\ntime.sleep(10)\n", timeout=.1)
        self.assertEqual(receipt["run_outcome"], "INCOMPLETE_DISPATCH")
        self.assertTrue(receipt["timeout"])
        self.assertTrue(verify_chain(session / "transcript.jsonl"))

    def test_unexpected_nonzero_exit_and_injected_missing_audit_are_ineligible(self):
        _, _, failed = self.run_fake("raise SystemExit(7)\n", allow_child_failure=True)
        self.assertEqual(failed["run_outcome"], "INCOMPLETE_DISPATCH")
        self.assertNotEqual(failed["stop_reason"], "cap")
        missing = self.base / "not-created-events.jsonl"
        _, _, unaudited = self.run_fake("pass\n", event_log=missing)
        # Contract clause: injected audit sources use the same presence/recognized-event checks.
        self.assertEqual(unaudited["run_outcome"], "AUDIT_UNVERIFIABLE")
        empty = self.base / "empty-events.jsonl"
        empty.write_bytes(b"")
        _, _, empty_audit = self.run_fake("pass\n", event_log=empty)
        self.assertEqual(empty_audit["run_outcome"], "AUDIT_UNVERIFIABLE")
        _, _, premature = self.run_fake("raise SystemExit(0)\n")
        self.assertEqual(premature["stop_reason"], "premature_exit")
        self.assertNotEqual(premature["run_outcome"], "COMPLETE")

    def test_malformed_published_request_is_protocol_error(self):
        _, run, receipt = self.run_fake('''
            from pathlib import Path
            Path("inbox/0001.json").write_text('{"inputs":')
            import time
            time.sleep(1)
            ''')
        self.assertEqual(receipt["stop_reason"], "ipc_error")
        self.assertEqual(receipt["run_outcome"], "ERROR")
        self.assertTrue(receipt["receipt_finalized_after_child_exit"])

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
        self.assertEqual(forbidden["run_outcome"], "BLINDNESS_VIOLATED")
        # Contract lifecycle clause: COMPLETE requires an in-order journal record per action.
        _, _, clean = self.run_fake('''
            import json, shlex, subprocess
            subprocess.run("./playctl step " + shlex.quote(json.dumps(["look"])), shell=True)
            note = {"turn_id":1,"wanted":"look","surprise":"","continue":1,"reason":"testing","unsupported_intent":None}
            subprocess.run("./playctl journal " + shlex.quote(json.dumps(note)), shell=True)
            ''', cap=1)
        self.assertEqual(clean["run_outcome"], "COMPLETE")
        # Contract clause: empty default and injected audit sources are unverifiable.
        _, _, empty = self.run_fake("pass\n", emit_event=False)
        self.assertEqual(empty["run_outcome"], "AUDIT_UNVERIFIABLE")
        self.assertEqual(empty["audit_events_seen"], 0)

    def test_empty_and_missing_event_sources_remain_unverifiable(self):
        missing = self.base / "missing.jsonl"
        empty = self.base / "empty.jsonl"
        empty.touch()
        for source in (missing, empty):
            _, _, receipt = self.run_fake("pass\n", event_log=source)
            self.assertEqual(receipt["audit_status"], "UNVERIFIABLE")
            self.assertEqual(receipt["run_outcome"], "AUDIT_UNVERIFIABLE")

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
        receipt = run_golem(session, run, persona_text="sealed operator wording", is_holdout=False,
                            golem_cmd=self.fake("pass\n"))
        self.assertNotIn("sealed operator wording", (run / "run_receipt.json").read_text())
        self.assertEqual(receipt["prompt_sha256"], hashlib.sha256((run / "prompt.txt").read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
