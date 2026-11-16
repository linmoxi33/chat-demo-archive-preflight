#!/usr/bin/env python3
"""Behaviour tests: build real ZIPs, run the CLI as a subprocess, assert exit codes/JSON."""

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "bin" / "chat-demo-archive-preflight"
TS = "2026-11-11T02:33:23.270Z"


def msg(mid, parent, role, status="FINISHED", fragments=None):
    return {
        "id": mid, "parent_id": parent, "role": role, "status": status,
        "thinking_enabled": False, "search_enabled": False,
        "accumulated_token_usage": 0, "inserted_at": TS,
        "fragments": fragments or [{"type": "RESPONSE", "content": "x"}],
    }


def session(sid="s1", messages=None, current=1, image=True):
    messages = messages if messages is not None else [
        msg(1, None, "USER", fragments=[{"type": "REQUEST", "content": "hi"}]),
        msg(2, 1, "ASSISTANT"),
    ]
    if image:
        messages[0]["fragments"].append({"type": "FILE", "files": [{
            "id": "f1", "file_name": "a.png", "file_size": 8, "token_usage": None,
            "inserted_at": TS, "export_path": f"chat_sessions/{sid}_files/f1_a.png",
            "is_image": True, "width": 1, "height": 1}]})
    return {"id": sid, "title": None, "pinned": False,
            "current_message_id": current, "inserted_at": TS, "updated_at": TS,
            "messages": messages}


def index_for(sessions, count_override=None):
    out = []
    for s in sessions:
        out.append({"id": s["id"], "title": s["title"], "pinned": s["pinned"],
                    "message_count": count_override if count_override is not None else len(s["messages"]),
                    "inserted_at": TS, "updated_at": TS})
    return out


def build(path, entries):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as zf:
        for name, data in entries:
            if isinstance(data, (dict, list)):
                data = json.dumps(data).encode()
            zf.writestr(name, data)
    return path


def valid_entries(sessions=None, index=None, image=True):
    sessions = sessions or [session(image=image)]
    entries = [("manifest.json", {"export_format_version": 3})]
    entries += [(f"chat_sessions/{s['id']}.json", s) for s in sessions]
    entries.append(("chat_session_index.json", index if index is not None else index_for(sessions)))
    if image:
        for s in sessions:
            entries.append((f"chat_sessions/{s['id']}_files/f1_a.png", b"\x89PNG" + b"\x00" * 8))
    return entries


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_zip(self, entries, json_mode=False, name="a.zip"):
        path = build(self.dir / name, entries)
        cmd = [sys.executable, str(BIN), str(path)]
        if json_mode:
            cmd.append("--json")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        payload = None
        if json_mode and proc.stdout.strip():
            payload = json.loads(proc.stdout)
        return proc, payload

    def codes(self, payload):
        return [f["code"] for f in payload["findings"]]


class TestBehaviour(Base):
    def test_valid_archive_exits_zero(self):
        proc, _ = self.run_zip(valid_entries())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("0 error(s)", proc.stdout)

    def test_json_is_parseable_and_complete(self):
        proc, payload = self.run_zip(valid_entries(), json_mode=True)
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["sha256"]), 64)
        self.assertEqual(payload["sessions"], 1)
        self.assertEqual(payload["messages"], 2)

    def test_manifest_not_first_is_e002(self):
        entries = valid_entries()
        entries = entries[1:] + [entries[0]]
        proc, payload = self.run_zip(entries, json_mode=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("E002", self.codes(payload))

    def test_wrong_version_is_e010(self):
        entries = valid_entries()
        entries[0] = ("manifest.json", {"export_format_version": 2})
        proc, payload = self.run_zip(entries, json_mode=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("E010", self.codes(payload))

    def test_missing_manifest_is_e003(self):
        entries = [e for e in valid_entries() if e[0] != "manifest.json"]
        proc, payload = self.run_zip(entries, json_mode=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("E003", self.codes(payload))

    def test_parent_not_smaller_is_e013(self):
        bad = session(messages=[msg(1, None, "USER"), msg(2, 3, "ASSISTANT"), msg(3, 2, "USER")], image=False)
        proc, payload = self.run_zip(valid_entries([bad]), json_mode=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("E013", self.codes(payload))

    def test_role_not_alternating_is_e013(self):
        bad = session(messages=[msg(1, None, "USER"), msg(2, 1, "USER")], image=False)
        proc, payload = self.run_zip(valid_entries([bad]), json_mode=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("E013", self.codes(payload))

    def test_two_roots_is_e013(self):
        bad = session(messages=[msg(1, None, "USER"), msg(2, None, "USER")], image=False)
        proc, payload = self.run_zip(valid_entries([bad]), json_mode=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("E013", self.codes(payload))

    def test_dangling_current_message_is_e013(self):
        bad = session(current=99, image=False)
        proc, payload = self.run_zip(valid_entries([bad]), json_mode=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("E013", self.codes(payload))

    def test_index_count_mismatch_is_e012(self):
        s = session(image=False)
        index = index_for([s], count_override=99)
        proc, payload = self.run_zip(valid_entries([s], index), json_mode=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("E012", self.codes(payload))

    def test_missing_referenced_image_is_e014(self):
        entries = [e for e in valid_entries() if not e[0].endswith(".png")]
        proc, payload = self.run_zip(entries, json_mode=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("E014", self.codes(payload))

    def test_orphan_image_is_only_a_warning(self):
        entries = valid_entries() + [("chat_sessions/s1_files/ff_extra.png", b"\x89PNG" + b"\x02" * 8)]
        proc, payload = self.run_zip(entries, json_mode=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("W020", self.codes(payload))
        self.assertEqual(payload["summary"]["errors"], 0)

    def test_duplicate_nfc_name_is_e008(self):
        entries = valid_entries() + [("chat_sessions/s\u00e9.json", b"{}"), ("chat_sessions/se\u0301.json", b"{}")]
        proc, payload = self.run_zip(entries, json_mode=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("E008", self.codes(payload))

    def test_unsafe_path_is_e009(self):
        entries = valid_entries() + [("../evil.json", b"{}")]
        proc, payload = self.run_zip(entries, json_mode=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("E009", self.codes(payload))

    def test_not_a_zip_is_exit_2(self):
        path = self.dir / "plain.zip"
        path.write_text("not a zip")
        proc = subprocess.run([sys.executable, str(BIN), str(path)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout.strip(), "")

    def test_missing_file_json_error_is_exit_2(self):
        proc = subprocess.run([sys.executable, str(BIN), str(self.dir / "nope.zip"), "--json"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "E000"),


class TestExamples(unittest.TestCase):
    def test_committed_examples_build_and_match(self):
        out = Path(tempfile.mkdtemp())
        subprocess.run([sys.executable, str(ROOT / "examples" / "make_archive.py"), str(out)],
                       check=True, capture_output=True)
        valid = subprocess.run([sys.executable, str(BIN), str(out / "chat-demo-example-valid.zip"), "--json"],
                               capture_output=True, text=True)
        self.assertEqual(valid.returncode, 0)
        expected = json.loads((ROOT / "examples" / "out" / "valid.json").read_text())
        got = json.loads(valid.stdout)
        got.pop("archive")
        self.assertEqual(got["ok"], expected["ok"])
        self.assertEqual(got["summary"], expected["summary"])
        broken = subprocess.run([sys.executable, str(BIN), str(out / "chat-demo-example-broken.zip"), "--json"],
                                capture_output=True, text=True)
        self.assertEqual(broken.returncode, 1)
        self.assertIn("E012", [f["code"] for f in json.loads(broken.stdout)["findings"]])


if __name__ == "__main__":
    unittest.main(verbosity=2)