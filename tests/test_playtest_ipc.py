import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from playtest.golem_runner import _playctl_source


class PlayctlIPCTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.capsule = self.root / "capsule"
        self.inbox = self.capsule / "inbox"
        self.inbox.mkdir(parents=True)
        self.replies = self.root / "replies"
        self.replies.mkdir()
        self.launcher = self.capsule / "playctl"

    def install_launcher(self, source=None):
        self.launcher.write_text(source or _playctl_source(replies_dir=self.replies, nonce="correlation-only"))
        self.launcher.chmod(0o700)

    def test_partial_request_is_never_published_or_consumed(self):
        self.install_launcher()
        source = self.launcher.read_text()
        # Simulate a slow writer after its first flushed half. The temporary file
        # must remain invisible to the controller until the atomic rename.
        source = source.replace(
            "stream.write(encoded); stream.flush(); os.fsync(stream.fileno())",
            "stream.write(encoded[:len(encoded)//2]); stream.flush(); time.sleep(.3); "
            "stream.write(encoded[len(encoded)//2:]); stream.flush(); os.fsync(stream.fileno())",
        )
        self.assertNotEqual(source, self.launcher.read_text(), "slow-writer hook did not match launcher")
        self.launcher.write_text(source)
        process = subprocess.Popen([str(self.launcher), "step", '["look"]'], text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(.1)
        published_early = list(self.inbox.glob("[0-9][0-9][0-9][0-9].json"))
        self.assertEqual(published_early, [])
        published = []
        deadline = time.monotonic() + 2
        while not published and time.monotonic() < deadline:
            published = list(self.inbox.glob("[0-9][0-9][0-9][0-9].json"))
            time.sleep(.01)
        self.assertEqual(len(published), 1)
        request = json.loads(published[0].read_text(encoding="utf-8"))
        self.assertEqual(request, {"inputs": ["look"], "request_id": published[0].stem})
        (self.replies / published[0].name).write_text(json.dumps({
            "output": "ok", "turn": 1, "terminated": None,
            "request_id": published[0].stem, "nonce": "correlation-only",
        }))
        stdout, stderr = process.communicate(timeout=2)
        self.assertEqual(process.returncode, 0, stderr)
        self.assertEqual(stdout, "ok")

    def test_controller_reply_is_read_from_external_absolute_directory(self):
        self.install_launcher()
        self.assertIn(str(self.replies), self.launcher.read_text())
        self.assertNotIn("OUTBOX", self.launcher.read_text())
        result_holder = []

        def invoke():
            result_holder.append(subprocess.run([str(self.launcher), "step", '["look"]'],
                                                capture_output=True, text=True, timeout=3))

        worker = threading.Thread(target=invoke)
        worker.start()
        deadline = time.monotonic() + 2
        request = None
        while request is None and time.monotonic() < deadline:
            candidates = list(self.inbox.glob("[0-9][0-9][0-9][0-9].json"))
            if candidates:
                request = candidates[0]
            time.sleep(.01)
        self.assertIsNotNone(request)
        payload = json.loads(request.read_text())
        reply = self.replies / request.name
        reply.write_text(json.dumps({"output": "controller", "turn": 1, "terminated": None,
                                     "request_id": payload["request_id"], "nonce": "correlation-only"}))
        worker.join(3)
        self.assertFalse(worker.is_alive())
        result = result_holder[0]
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "controller")
        self.assertFalse((self.capsule / "outbox").exists())

    def test_forged_capsule_reply_cannot_answer_launcher_request(self):
        source = _playctl_source(replies_dir=self.replies, nonce="correlation-only")
        source = source.replace("time.monotonic() + 180", "time.monotonic() + .25")
        self.install_launcher(source)
        outbox = self.capsule / "outbox"
        outbox.mkdir()
        (outbox / "0001.json").write_text(json.dumps({
            "output": "FORGED", "turn": 1, "terminated": None,
            "request_id": "0001", "nonce": "correlation-only",
        }))
        result = subprocess.run([str(self.launcher), "step", '["look"]'],
                                capture_output=True, text=True, timeout=2)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("FORGED", result.stdout)
        self.assertEqual(list(self.replies.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
