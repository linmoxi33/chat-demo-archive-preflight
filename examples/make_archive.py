#!/usr/bin/env python3
"""Build the example archives used by README. Writes to /tmp by default.

No binary archive is committed to the repository.
"""

import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IN = ROOT / "in"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp")


def valid_entries() -> list[tuple[str, bytes]]:
    return [
        ("manifest.json", (IN / "manifest.json").read_bytes()),
        ("chat_sessions/s1.json", (IN / "session-valid.json").read_bytes()),
        ("chat_sessions/s2.json", (IN / "session-s2.json").read_bytes()),
        ("chat_session_index.json", (IN / "index.json").read_bytes()),
        ("chat_sessions/s1_files/f1_a.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 16),
        ("chat_sessions/s2_files/f2_b.png", b"\x89PNG\r\n\x1a\n" + b"\x11" * 16),
    ]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    valid = OUT / "chat-demo-example-valid.zip"
    with zipfile.ZipFile(valid, "w", zipfile.ZIP_STORED) as zf:
        for name, data in valid_entries():
            zf.writestr(name, data)
    entries = valid_entries()
    index = json.loads((IN / "index.json").read_text(encoding="utf-8"))
    index[0]["message_count"] = 99
    broken = OUT / "chat-demo-example-broken.zip"
    with zipfile.ZipFile(broken, "w", zipfile.ZIP_STORED) as zf:
        for name, data in entries:
            if name == "chat_session_index.json":
                data = json.dumps(index).encode()
            zf.writestr(name, data)
    print(f"wrote {valid}")
    print(f"wrote {broken}")


if __name__ == "__main__":
    main()