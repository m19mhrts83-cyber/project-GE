#!/usr/bin/env python3
"""
ダッシュボードからの Cursor Agent 見直しキューを処理する。

Web（Vercel）は agent CLI を直接呼べないため、payload.cursor_revise に
queued を書き、本ワーカー（Mac launchd）が夜間トリアージと同じ
`cursor_generate` で本文を書き直す。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_triage_cursor_revise_worker.py
  python scripts/jarvis_triage_cursor_revise_worker.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_night_triage import cursor_generate  # noqa: E402


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def build_prompt(instruction: str, draft: str) -> str:
    return "\n".join(
        [
            "あなたはビジネス日本語のメール下書き校正アシスタントです。",
            "意味は変えず、指示に従って返信下書きを書き直してください。",
            "出力は本文のみ（挨拶から結びまで）。前置きやコードフェンスは付けない。",
            "",
            "【見直し指示】",
            instruction.strip() or "（丁寧に整えて）",
            "",
            "【現在の下書き】",
            draft,
        ]
    )


def strip_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Process Cursor revise queue from dashboard")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args(argv)

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        print("# JARVIS_SUPABASE_* 未設定", file=sys.stderr)
        return 1

    from supabase import create_client

    sb = create_client(url, key)
    # PostgREST: nested JSON path
    r = (
        sb.table("triage_items")
        .select("id,partner,folder,draft_text,payload")
        .filter("payload->cursor_revise->>status", "eq", "queued")
        .order("updated_at", desc=False)
        .limit(args.limit)
        .execute()
    )
    rows = r.data or []
    if not rows:
        print("# cursor revise: queued=0")
        return 0

    done = 0
    failed = 0
    for it in rows:
        item_id = it["id"]
        payload = it.get("payload") if isinstance(it.get("payload"), dict) else {}
        cr = payload.get("cursor_revise") if isinstance(payload.get("cursor_revise"), dict) else {}
        instruction = str(cr.get("instruction") or "").strip() or "（丁寧に整えて）"
        draft = str(cr.get("draft") or it.get("draft_text") or "").strip()
        if not draft:
            print(f"# skip empty id={item_id}", file=sys.stderr)
            failed += 1
            continue

        print(f"# revise id={item_id} partner={it.get('partner')}")
        if args.dry_run:
            done += 1
            continue

        running = dict(payload)
        running_cr = dict(cr)
        running_cr["status"] = "running"
        running_cr["started_at"] = now_iso()
        running["cursor_revise"] = running_cr
        sb.table("triage_items").update(
            {"payload": running, "updated_at": now_iso()}
        ).eq("id", item_id).execute()

        try:
            raw = cursor_generate(build_prompt(instruction, draft))
            new_draft = strip_fences(raw)
            if not new_draft:
                raise RuntimeError("Cursor Agent 応答が空")
        except Exception as e:
            err_payload = dict(payload)
            err_cr = dict(cr)
            err_cr["status"] = "error"
            err_cr["error"] = str(e)[:400]
            err_cr["finished_at"] = now_iso()
            err_payload["cursor_revise"] = err_cr
            sb.table("triage_items").update(
                {"payload": err_payload, "updated_at": now_iso()}
            ).eq("id", item_id).execute()
            print(f"# error id={item_id}: {e}", file=sys.stderr)
            failed += 1
            continue

        ok_payload: dict[str, Any] = dict(payload)
        ok_cr = dict(cr)
        ok_cr["status"] = "done"
        ok_cr["finished_at"] = now_iso()
        ok_cr.pop("error", None)
        ok_payload["cursor_revise"] = ok_cr
        ok_payload["draft_cursor"] = new_draft
        ok_payload["web_draft_saved_at"] = now_iso()
        if not isinstance(ok_cr.get("via"), str) or not ok_cr.get("via"):
            ok_cr["via"] = "mac_fallback"
        sb.table("triage_items").update(
            {
                "draft_text": new_draft,
                "payload": ok_payload,
                "updated_at": now_iso(),
            }
        ).eq("id", item_id).execute()
        done += 1
        print(f"# done id={item_id} chars={len(new_draft)}")

    print(f"# cursor revise done={done} failed={failed} scanned={len(rows)}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
