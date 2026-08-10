#!/usr/bin/env python3
"""
Ops Fail のローカル（Mac）フォールバック Worker。

watch_status.payload.cursor_ops_fix.status=queued を拾い、
ローカル cursor agent で修正を試みる。Cloud 上限時の受け皿。

  python scripts/jarvis_ops_fail_local_worker.py
  python scripts/jarvis_ops_fail_local_worker.py --dry-run

既存 launchd: launchd/cursor_revise_worker_runner.sh から呼ぶ。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_night_triage import find_cursor_agent  # noqa: E402

WATCH_IDS = ("vercel_deploy", "gha_workflow_fail")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def build_fix_prompt(row: dict[str, Any]) -> str:
    pl = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    ops = pl.get("cursor_ops_fix") if isinstance(pl.get("cursor_ops_fix"), dict) else {}
    custom = str(ops.get("prompt") or "").strip()
    if custom:
        base = custom
    else:
        base = str(row.get("cursor_prompt") or row.get("summary") or "").strip()
    return "\n".join(
        [
            "あなたは Jarvis（運用修復 Agent）です。リポジトリ project-GE の main 系を直してください。",
            "対象は Vercel / GitHub Actions の失敗修復。秘密はチャットに出さない。",
            "手順:",
            "1. 失敗内容を確認（summary / detail URL / gh / 可能なら npm run build）",
            "2. 最小限の修正をコミット（関係ないファイルは触らない）",
            "3. push し、必要なら draft PR",
            "4. 直したら次を実行:",
            "   python scripts/jarvis_ops_fail_watch.py --push --note '（直した内容を1〜2文）'",
            "対外メール送信・承認ゲート緩和はしない。",
            "",
            f"watch_id: {row.get('id')}",
            f"title: {row.get('title')}",
            f"level: {row.get('level')}",
            f"summary: {row.get('summary')}",
            f"detail: {row.get('detail')}",
            "",
            "追加指示:",
            base or "（なし）",
        ]
    )


def run_local_agent(prompt: str, *, timeout: int = 900) -> str:
    exe = find_cursor_agent()
    if not exe:
        raise RuntimeError("cursor-agent / agent が見つかりません（未インストール）")
    # 書込あり（ask ではない）。非対話。
    cmd = [exe, "-p", "--force", "--output-format", "text", prompt]
    r = subprocess.run(
        cmd,
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if r.returncode != 0:
        raise RuntimeError(
            f"local agent failed ({r.returncode}): {(r.stderr or r.stdout or '')[:500]}"
        )
    return (r.stdout or "").strip()


def process_row(sb: Any, row: dict[str, Any], *, dry_run: bool) -> str:
    item_id = str(row["id"])
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    ops = payload.get("cursor_ops_fix") if isinstance(payload.get("cursor_ops_fix"), dict) else {}
    if str(ops.get("status") or "") != "queued":
        return "skip"

    print(f"# ops_fix local id={item_id}")
    if dry_run:
        return "dry_run"

    running = dict(payload)
    running_ops = dict(ops)
    running_ops["status"] = "running"
    running_ops["via"] = "local_worker"
    running_ops["started_at"] = now_iso()
    running["cursor_ops_fix"] = running_ops
    sb.table("watch_status").update(
        {"payload": running, "updated_at": now_iso()}
    ).eq("id", item_id).execute()

    prompt = build_fix_prompt(row)
    try:
        out = run_local_agent(prompt)
    except Exception as e:
        err_payload = dict(payload)
        err_ops = dict(ops)
        err_ops["status"] = "error"
        err_ops["error"] = str(e)[:400]
        err_ops["finished_at"] = now_iso()
        err_ops["via"] = "local_worker"
        err_payload["cursor_ops_fix"] = err_ops
        sb.table("watch_status").update(
            {"payload": err_payload, "updated_at": now_iso()}
        ).eq("id", item_id).execute()
        print(f"# error id={item_id}: {e}", file=sys.stderr)
        return "error"

    ok_payload = dict(payload)
    ok_ops = dict(ops)
    ok_ops["status"] = "done"
    ok_ops["finished_at"] = now_iso()
    ok_ops["via"] = "local_worker"
    ok_ops["result_preview"] = (out or "")[:500]
    ok_ops.pop("error", None)
    ok_payload["cursor_ops_fix"] = ok_ops
    # ローカル完了後もバナーは残しつつ、要約に追記しやすいよう level は維持
    sb.table("watch_status").update(
        {"payload": ok_payload, "updated_at": now_iso()}
    ).eq("id", item_id).execute()

    # お知らせ（失敗していても note は出す）
    try:
        note = f"ローカル Cursor で {item_id} の修復を実行した。結果を確認して。"
        subprocess.run(
            [
                sys.executable,
                str(REPO / "scripts" / "jarvis_ops_fail_watch.py"),
                "--push",
                "--note",
                note,
            ],
            cwd=str(REPO),
            check=False,
            timeout=120,
        )
    except Exception as e:
        print(f"# note push skip: {e}", file=sys.stderr)

    print(f"# done id={item_id}")
    return "done"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        print("JARVIS_SUPABASE_* が必要", file=sys.stderr)
        return 1

    from supabase import create_client

    sb = create_client(url, key)
    r = (
        sb.table("watch_status")
        .select("id,title,level,summary,detail,cursor_prompt,payload,status")
        .eq("status", "active")
        .in_("id", list(WATCH_IDS))
        .execute()
    )
    rows = r.data or []
    queued = []
    for row in rows:
        pl = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        ops = pl.get("cursor_ops_fix") if isinstance(pl.get("cursor_ops_fix"), dict) else {}
        if str(ops.get("status") or "") == "queued":
            queued.append(row)

    if not queued:
        print("# ops_fix local: queued=0")
        return 0

    counts: dict[str, int] = {}
    for row in queued:
        st = process_row(sb, row, dry_run=args.dry_run)
        counts[st] = counts.get(st, 0) + 1
    print(json.dumps({"counts": counts}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
