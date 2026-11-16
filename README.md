# chat-demo-archive-preflight

A zero-dependency CLI that checks a [chat-demo](https://github.com/deepseek-ai/chat-demo) history ZIP *before* you import it,
because a successful import replaces **all** local conversations and attachments.

Upstream: https://github.com/deepseek-ai/chat-demo

## Why this exists

chat-demo exports `deepseek_data-*.zip` with `export_format_version: 3` and imports it by validating, staging, then replacing
all local sessions and images in one transaction. The validator lives inside the browser app (`schema.ts`, `zipReader.ts`), so
there is no way to answer "will this archive import cleanly, and which entry will break it?" from a terminal or CI. That matters
when the archive was edited, re-zipped, or produced on another machine: the documented rules are strict and some of them fail
only after the user has already confirmed the destructive replacement.

What the upstream docs actually say:

- `manifest.json` must be the **first** entry, with `export_format_version: 3` —
  <https://github.com/deepseek-ai/chat-demo/blob/main/src/services/chat/history/format.ts#L12-L15>
- ZIP64, encryption, multi-volume and non-UTF-8 non-ASCII names are **not supported**; entry names are compared after NFC —
  <https://github.com/deepseek-ai/chat-demo/blob/main/src/services/chat/history/README.md#L61>
- import validates the index/session one-to-one relation and the message tree, then replaces everything —
  <https://github.com/deepseek-ai/chat-demo/blob/main/src/services/chat/history/README.md#L18-L24>

Real open report on the same area (destructive import edge cases): <https://github.com/deepseek-ai/chat-demo/issues>

## What it does / does not do

Checks, offline, without extracting:

- container: valid ZIP32, `manifest.json` first, no ZIP64/encryption/multi-volume, UTF-8 flags, NFC duplicates, unsafe paths, CRC;
- manifest: JSON shape and `export_format_version == 3`;
- every `chat_sessions/{id}.json`: JSON shape, id/filename agreement, message ids, one USER root, `parent_id < id`, parent exists,
  role alternation, `current_message_id` resolvable;
- index: present, unique ids, session/index one-to-one, `message_count` matches the actual messages;
- attachments: every image `export_path` exists and lives under its session's `_files/` directory; orphan images are warnings.

It does **not** import, extract, rewrite or repair anything. It does not decode image bytes, does not validate every fragment
variant (only `FILE` references and the message tree), and it cannot know whether the browser's IndexedDB quota will accept the data.

## Install / usage

Requires Python 3.9+; no third-party packages.

```sh
python3 examples/make_archive.py /tmp
python3 bin/chat-demo-archive-preflight /tmp/chat-demo-example-valid.zip
python3 bin/chat-demo-archive-preflight /tmp/chat-demo-example-broken.zip --json
```

`--json` prints one object; `ensure_ascii=False`, stable sorting of findings, `sha256` of the input archive.

Exit codes: `0` no errors (warnings allowed), `1` findings (errors), `2` usage or input error (missing file, not a ZIP).

Example (real output of the committed example):

```json
{
  "tool": "chat-demo-archive-preflight",
  "version": "1.0.0",
  "ok": true,
  "entries": 6,
  "sessions": 2,
  "messages": 3,
  "findings": [],
  "summary": { "errors": 0, "warnings": 0 }
}
```

Findings: `E002` manifest not first · `E003` missing manifest · `E004` ZIP64 · `E005` encrypted · `E006` multi-volume ·
`E007` non-UTF-8 name · `E008` NFC duplicate · `E009` unsafe path · `E010` bad manifest/version · `E012` session or index
mismatch · `E013` CRC or message-tree violation · `E014` attachment reference mismatch · `W020` orphan image.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

18 tests (17 behaviour tests that build real ZIPs and assert exit codes/JSON, 1 example-fidelity test).

## 本轮创新

First CI-usable preflight for chat-demo v3 archives: it turns the documented-but-browser-only import contract into an offline,
deterministic verdict (including NFC duplicate and ZIP64 rejection), so a destructive import can be gated before it runs.
Existing chat-demo tooling only validates *inside* the app at import time; no third-party checker was found
(`gh search repos "chat-demo archive"` → 0 hits).

## 局限

- Mirrors the v3 contract, not older formats (upstream explicitly has no old-format migration).
- `message_count` and index checks reflect the documented v3 semantics; unknown fields are ignored rather than rejected.
- Warnings do not fail the run; pass `--json` and check `summary.warnings` if you want strictness.
- Not affiliated with DeepSeek. Upstream license: MIT.