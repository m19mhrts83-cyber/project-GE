#!/usr/bin/env python3
"""Genspark AI Meeting Notes を gsk meeting でオンデマンド取得する。

SecondBrain Note / Speakly / AI Meeting Notes は同一ストア。
全文の常時ミラーはしない（Hot = この CLI、Warm = Notion Inbox、Cold = Obsidian 1行索引）。

例:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_genspark_meeting_fetch.py list --page-size 10
  ~/selenium_env/venv/bin/python scripts/jarvis_genspark_meeting_fetch.py search --keyword LEAF --date-from 2026-09-01
  ~/selenium_env/venv/bin/python scripts/jarvis_genspark_meeting_fetch.py get --task-id <ID> --detail-level summary
  ~/selenium_env/venv/bin/python scripts/jarvis_genspark_meeting_fetch.py get --task-id <ID> --detail-level segments --pretty
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
PRIVATE_ENV = REPO / ".env.jarvis_private"
DEFAULT_GSK_PATHS = (
    Path.home() / ".local" / "bin" / "gsk",
    Path.home() / ".genspark-tool-cli" / "bin" / "gsk",
)


def load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$", line)
        if m and not line.lstrip().startswith("#"):
            out[m.group(1)] = m.group(2).strip().strip("\"'")
    return out


def ensure_env() -> None:
    """Load GSK_API_KEY into os.environ if missing (from jarvis_private)."""
    if (os.environ.get("GSK_API_KEY") or "").strip():
        return
    env = load_dotenv(PRIVATE_ENV)
    key = (env.get("GSK_API_KEY") or "").strip()
    if key:
        os.environ["GSK_API_KEY"] = key


def find_gsk() -> str:
    which = shutil.which("gsk")
    if which:
        return which
    for p in DEFAULT_GSK_PATHS:
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    raise SystemExit(
        "gsk が見つかりません。npm i -g @genspark/cli 後に PATH へ "
        "~/.local/bin を入れてください。"
    )


def run_gsk(args: list[str]) -> dict[str, Any]:
    ensure_env()
    if not (os.environ.get("GSK_API_KEY") or "").strip():
        raise SystemExit(
            "GSK_API_KEY が未設定です。.env.jarvis_private に追記するか "
            "`gsk login` 後に config から転記してください。"
        )
    gsk = find_gsk()
    cmd = [gsk, "meeting", *args]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0:
        msg = stderr or stdout or f"exit {proc.returncode}"
        raise SystemExit(f"gsk meeting 失敗: {msg}")
    if not stdout:
        raise SystemExit("gsk meeting: 空の応答")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        raise SystemExit(f"gsk meeting: JSON 解析失敗: {e}\n--- stdout ---\n{stdout[:500]}") from e


def _note_brief(note: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": note.get("id") or note.get("task_id"),
        "title": note.get("title"),
        "status": note.get("status"),
        "created_at": note.get("created_at"),
        "duration_human": note.get("duration_human"),
        "duration_seconds": note.get("duration_seconds"),
    }


def shape_list_or_search(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    notes = data.get("notes") if isinstance(data.get("notes"), list) else []
    return {
        "status": payload.get("status"),
        "count": data.get("count", len(notes)),
        "has_more": data.get("has_more"),
        "continuation_token": data.get("continuation_token"),
        "notes": [_note_brief(n) for n in notes if isinstance(n, dict)],
    }


def shape_get(payload: dict[str, Any], detail_level: str) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        return {"status": payload.get("status"), "raw": data}

    out: dict[str, Any] = {
        "status": payload.get("status"),
        "detail_level": detail_level,
        "id": data.get("id") or data.get("task_id"),
        "title": data.get("title"),
        "status_note": data.get("status"),
        "created_at": data.get("created_at"),
        "duration_human": data.get("duration_human"),
        "duration_seconds": data.get("duration_seconds"),
        "summary": data.get("summary") or data.get("ai_summary"),
        "user_notes": data.get("user_notes") or data.get("notes"),
    }

    if detail_level == "full":
        transcript = (
            data.get("transcription")
            or data.get("transcript")
            or data.get("full_text")
            or data.get("content")
        )
        out["transcription"] = transcript
        if isinstance(transcript, str):
            out["transcription_chars"] = len(transcript)
    elif detail_level == "segments":
        segments = data.get("segments") or data.get("utterances") or []
        out["segments"] = segments
        if isinstance(segments, list):
            out["segments_count"] = len(segments)
    # summary: omit full body keys beyond summary/user_notes

    # Keep unknown useful fields (short only) for debugging without dumping secrets loudly
    for key in (
        "share_url",
        "url",
        "project_url",
        "source",
        "meeting_source",
        "project_id",
    ):
        if key in data and data[key] is not None:
            out[key] = data[key]

    return out


def print_human_list(shaped: dict[str, Any]) -> None:
    notes = shaped.get("notes") or []
    print(f"📎 Genspark meeting — {shaped.get('count', len(notes))}件")
    for i, n in enumerate(notes, 1):
        print(
            f"{i}. {n.get('created_at') or '—'} | {n.get('duration_human') or '—'} | "
            f"{n.get('title') or '(無題)'}\n"
            f"   id: {n.get('id')}"
        )
    if shaped.get("has_more"):
        print(f"(続きあり continuation_token={shaped.get('continuation_token')})")


def print_human_get(shaped: dict[str, Any]) -> None:
    print("📎 Genspark meeting get")
    print(f"- title: {shaped.get('title')}")
    print(f"- id: {shaped.get('id')}")
    print(f"- created_at: {shaped.get('created_at')}")
    print(f"- duration: {shaped.get('duration_human')}")
    print(f"- detail_level: {shaped.get('detail_level')}")
    summary = shaped.get("summary")
    if summary:
        print("- summary:")
        text = summary if isinstance(summary, str) else json.dumps(summary, ensure_ascii=False)
        for line in text.strip().splitlines()[:40]:
            print(f"  {line}")
    if shaped.get("transcription"):
        chars = shaped.get("transcription_chars")
        print(f"- transcription: {chars} chars（全文は --json で）")
    if shaped.get("segments_count") is not None:
        print(f"- segments: {shaped.get('segments_count')}（本文は --json で）")


def cmd_list(args: argparse.Namespace) -> int:
    gsk_args = ["list"]
    if args.page_size is not None:
        gsk_args += ["--page_size", str(args.page_size)]
    if args.continuation_token:
        gsk_args += ["--continuation_token", args.continuation_token]
    raw = run_gsk(gsk_args)
    shaped = shape_list_or_search(raw)
    if args.json:
        print(json.dumps(shaped if args.shaped else raw, ensure_ascii=False, indent=2))
    else:
        print_human_list(shaped)
        if args.pretty:
            print(json.dumps(shaped, ensure_ascii=False, indent=2))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    if not (args.keyword or "").strip():
        raise SystemExit("--keyword が必要です")
    gsk_args = ["search", "--keyword", args.keyword]
    if args.date_from:
        gsk_args += ["--date_from", args.date_from]
    if args.date_to:
        gsk_args += ["--date_to", args.date_to]
    if args.page_size is not None:
        gsk_args += ["--page_size", str(args.page_size)]
    if args.page is not None:
        gsk_args += ["--page", str(args.page)]
    if args.sort_by:
        gsk_args += ["--sort_by", args.sort_by]
    if args.meeting_source:
        gsk_args += ["--meeting_source", args.meeting_source]
    raw = run_gsk(gsk_args)
    shaped = shape_list_or_search(raw)
    if args.json:
        print(json.dumps(shaped if args.shaped else raw, ensure_ascii=False, indent=2))
    else:
        print_human_list(shaped)
        if args.pretty:
            print(json.dumps(shaped, ensure_ascii=False, indent=2))
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    if not args.task_id and not args.project_id:
        raise SystemExit("--task-id または --project-id が必要です")
    if args.task_id and args.project_id:
        raise SystemExit("--task-id と --project-id はどちらか一方だけ")
    detail = args.detail_level or "summary"
    gsk_args = ["get", "--detail_level", detail]
    if args.task_id:
        gsk_args += ["--task_id", args.task_id]
    if args.project_id:
        gsk_args += ["--project_id", args.project_id]
    raw = run_gsk(gsk_args)
    shaped = shape_get(raw, detail)
    if args.json:
        print(json.dumps(shaped if args.shaped else raw, ensure_ascii=False, indent=2))
    else:
        print_human_get(shaped)
        if args.pretty:
            print(json.dumps(shaped, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Genspark AI Meeting Notes を gsk meeting で取得（オンデマンド）"
    )
    sub = p.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="JSON のみ出力（stdout）")
    common.add_argument(
        "--shaped",
        action="store_true",
        help="--json 時に整形済みだけ出す（raw ではなく）",
    )
    common.add_argument(
        "--pretty",
        action="store_true",
        help="人間向け要約のあとに整形 JSON も出す",
    )

    pl = sub.add_parser("list", parents=[common], help="作成日順に一覧")
    pl.add_argument("--page-size", type=int, default=20)
    pl.add_argument("--continuation-token", default=None)
    pl.set_defaults(func=cmd_list)

    ps = sub.add_parser("search", parents=[common], help="キーワード検索")
    ps.add_argument("--keyword", required=True)
    ps.add_argument("--date-from", default=None, help="YYYY-MM-DD")
    ps.add_argument("--date-to", default=None, help="YYYY-MM-DD")
    ps.add_argument("--page-size", type=int, default=20)
    ps.add_argument("--page", type=int, default=None)
    ps.add_argument("--sort-by", choices=("created_at", "relevance"), default=None)
    ps.add_argument("--meeting-source", choices=("google", "outlook"), default=None)
    ps.set_defaults(func=cmd_search)

    pg = sub.add_parser("get", parents=[common], help="1件の詳細")
    pg.add_argument("--task-id", default=None)
    pg.add_argument("--project-id", default=None)
    pg.add_argument(
        "--detail-level",
        choices=("summary", "full", "segments"),
        default="summary",
    )
    pg.set_defaults(func=cmd_get)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
