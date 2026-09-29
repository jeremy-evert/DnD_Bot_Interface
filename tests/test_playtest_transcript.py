import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from playtest import harness
from playtest.play import main
from playtest.transcript import load_transcript, verify_chain


ROOT = Path(__file__).resolve().parents[1]


class PlaytestTranscriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "playtest.play", *map(str, args)], cwd=ROOT,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )

    def new(self, folder="a", seed=41, name="Ada", character="fighter"):
        session = self.base / folder
        result = self.cli("new", "--seed", seed, "--name", name, "--class", character,
                          "--persona", "test", "--session", session)
        self.assertEqual(result.returncode, 0, result.stderr)
        return session

    def step(self, session, calls):
        return self.cli("step", "--session", session, "--inputs-json", json.dumps(calls))

    def test_cli_new_and_steps_reconstruct_exact_full_replay(self):
        session = self.new()
        self.assertEqual(self.step(session, ["attack"] * 20 + ["move", "east"]).returncode, 0)
        self.assertEqual(self.step(session, ["look"]).returncode, 0)
        self.assertEqual(self.step(session, ["move", "east"]).returncode, 0)
        records = load_transcript(session / "transcript.jsonl")
        expected = harness.replay(41, ["Ada", "fighter"] + ["attack"] * 20 +
                                  ["move", "east", "look", "move", "east"])
        self.assertEqual("".join(item["new_output"] for item in records), expected.output)
        self.assertEqual(records[-1]["full_output_sha256"], hashlib.sha256(expected.output.encode()).hexdigest())
        self.assertEqual(records[-1]["snapshot"]["room_id"], "crossroads")

    def test_multi_call_action_preserves_both_input_calls(self):
        session = self.new()
        self.assertEqual(self.step(session, ["attack"] * 20).returncode, 0)
        result = self.step(session, ["move", "east"])
        self.assertEqual(result.returncode, 0, result.stderr)
        record = load_transcript(session / "transcript.jsonl")[-1]
        self.assertEqual(record["input_calls"], ["move", "east"])
        self.assertEqual(record["snapshot"]["room_id"], "stores")

    def test_chain_rejects_edit_delete_and_reorder(self):
        session = self.new()
        self.step(session, ["look"])
        self.step(session, ["status"])
        path = session / "transcript.jsonl"
        original = path.read_bytes()
        rows = original.splitlines(keepends=True)
        variants = [original.replace(b"look", b"LOOK", 1), rows[0] + rows[2],
                    rows[0] + rows[1], rows[1] + rows[0] + rows[2]]
        for altered in variants:
            path.write_bytes(altered)
            with self.subTest(altered=altered[:30]):
                with self.assertRaises(ValueError):
                    verify_chain(path)
        path.write_bytes(original)
        self.assertEqual(len(verify_chain(path)), 3)

    def test_load_rejects_hand_authored_golem_jsonl(self):
        path = self.base / "golem-transcript.jsonl"
        path.write_text('{"turn_id":1,"new_output":"I won"}\n', encoding="utf-8")
        with self.assertRaises(ValueError):
            load_transcript(path)

    def test_replay_divergence_exits_two_without_appending(self):
        session = self.new()
        transcript_before = (session / "transcript.jsonl").read_bytes()
        frames_before = (session / "frames.jsonl").read_bytes()
        real = harness.replay(41, ["Ada", "fighter"])
        divergent = harness.ReplayResult("not the old prefix", real.witness, True, None, real.consumed)
        captured_error = io.StringIO()
        with patch("playtest.play.harness.replay", return_value=divergent), redirect_stderr(captured_error):
            result = main(["step", "--session", str(session), "--inputs-json", '["look"]'])
        self.assertEqual(result, 2)
        self.assertIn("REPLAY_DIVERGENCE", captured_error.getvalue())
        self.assertEqual((session / "transcript.jsonl").read_bytes(), transcript_before)
        self.assertEqual((session / "frames.jsonl").read_bytes(), frames_before)

    def test_game_ended_session_refuses_steps(self):
        session = self.new(seed=1, character="wizard")
        calls = ["attack"] * 20 + ["move", "east", "move", "east", "move", "south"] + ["attack"] * 20
        result = self.step(session, calls)
        self.assertEqual(result.returncode, 0, result.stderr)
        records = load_transcript(session / "transcript.jsonl")
        self.assertEqual(records[-1]["termination"], "dead")
        before = (session / "transcript.jsonl").read_bytes()
        refused = self.step(session, ["look"])
        self.assertEqual(refused.returncode, 3)
        self.assertEqual((session / "transcript.jsonl").read_bytes(), before)

    def test_identical_sessions_have_identical_chains_different_seeds_differ(self):
        one = self.new("one", seed=41)
        two = self.new("two", seed=41)
        three = self.new("three", seed=42)
        for session in (one, two, three):
            self.assertEqual(self.step(session, ["look"]).returncode, 0)
            self.assertEqual(self.step(session, ["status"]).returncode, 0)
        hashes = [[row["chain_hash"] for row in load_transcript(path / "transcript.jsonl")]
                  for path in (one, two, three)]
        self.assertEqual(hashes[0], hashes[1])
        self.assertNotEqual(hashes[0], hashes[2])


if __name__ == "__main__":
    unittest.main()
