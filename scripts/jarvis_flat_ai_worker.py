#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定額 AI の係（Mac 常駐）— ダッシュボードの依頼箱 ai_jobs を拾って定額 AI で作る。

2026-11-13 従量課金ゼロ化。ダッシュボード（Vercel）は Gemini などの従量 API を呼ばず、
ai_jobs に依頼を置いて待つ。この係が 3 秒ごとに見て、scripts/jarvis_flat_ai.py の順
（ボタン待ち: Codex → Cursor → Claude）で作り、結果を書き戻す。
- 心拍: sync_meta.flat_ai_worker_at を 1 分ごとに更新（Mac 見張りが読む）
- 古い依頼（3 日超）は消す（メール等の私的な文面を残さない）
- 15 分以上 running のままの依頼は queued に戻す（係が途中で落ちたとき）
- Supabase が失敗（402 制限・オフライン等）している間は 10 秒から 2 倍ずつ最大 300 秒まで
  間を空ける（3 秒ごとに打ち続けて egress と制限を悪化させない。2026-11-14 314・glucon 修正と同じ型）

launchd: launchd/install_flat_ai_worker_launchd.sh（KeepAlive）
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_flat_ai_worker.py --once --dry-run
停止: JARVIS_FLAT_AI_WORKER_DISABLE=1
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_flat_ai as flat  # noqa: E402

POLL_SEC = 3
HEARTBEAT_SEC = 60
KEEP_DAYS = 3
STUCK_MIN = 15
FAIL_WAIT_BASE_SEC = 10
FAIL_WAIT_MAX_SEC = 300
HEARTBEAT_KEY = "flat_ai_worker_at"
EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/webp": ".webp", "image/heic": ".heic"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def client() -> Any:
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    from supabase import create_client

    return create_client(url, key)


def heartbeat(sb: Any) -> None:
    st = flat.status()
    cooling = [p for p, v in st["providers"].items() if v.get("cooldown_until")]
    ts = now_iso()
    sb.table("sync_meta").upsert(
        {"key": HEARTBEAT_KEY, "value": ts if not cooling else f"{ts} cooling={','.join(cooling)}", "updated_at": ts},
        on_conflict="key",
    ).execute()


def housekeeping(sb: Any) -> None:
    old = (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).isoformat()
    sb.table("ai_jobs").delete().lt("created_at", old).execute()
    stuck = (datetime.now(timezone.utc) - timedelta(minutes=STUCK_MIN)).isoformat()
    sb.table("ai_jobs").update({"status": "queued", "started_at": None}).eq("status", "running").lt(
        "started_at", stuck
    ).execute()


def claim(sb: Any) -> dict[str, Any] | None:
    rows = (
        sb.table("ai_jobs").select("*").eq("status", "queued").order("created_at").limit(1).execute().data
        or []
    )
    if not rows:
        return None
    row = rows[0]
    got = (
        sb.table("ai_jobs")
        .update({"status": "running", "started_at": now_iso()})
        .eq("id", row["id"])
        .eq("status", "queued")
        .execute()
        .data
    )
    return row if got else None


def run_job(sb: Any, row: dict[str, Any]) -> str:
    images: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="flat_ai_job_") as td:
        for i, img in enumerate(row.get("images") or []):
            try:
                p = Path(td) / f"image{i + 1}{EXT.get(str(img.get('mimeType', '')).lower(), '.jpg')}"
                p.write_bytes(base64.b64decode(img.get("base64") or ""))
                images.append(p)
            except Exception:
                continue
        try:
            res = flat.generate(row["prompt"], interactive=bool(row.get("interactive", True)), images=images)
        except Exception as e:  # FlatAIError ほか
            sb.table("ai_jobs").update(
                {"status": "error", "error": str(e)[:900], "finished_at": now_iso()}
            ).eq("id", row["id"]).execute()
            return f"error: {str(e)[:120]}"
    sb.table("ai_jobs").update(
        {
            "status": "done",
            "result": res.text,
            "provider": res.provider,
            "notes": res.notes or None,
            "finished_at": now_iso(),
        }
    ).eq("id", row["id"]).execute()
    return f"done via {res.label}"


def fail_wait_sec(streak: int) -> float:
    """連続失敗 streak 回目（1 始まり）の待ち秒。10, 20, 40, … 最大 300。"""
    n = max(1, streak) - 1
    return float(min(FAIL_WAIT_MAX_SEC, FAIL_WAIT_BASE_SEC * (2 ** min(n, 10))))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="1 巡だけ")
    ap.add_argument("--dry-run", action="store_true", help="拾う候補を表示するだけ")
    args = ap.parse_args(argv)
    if (os.environ.get("JARVIS_FLAT_AI_WORKER_DISABLE") or "").strip() == "1":
        print("# flat_ai_worker disabled")
        return 0
    sb = client()
    if args.dry_run:
        rows = sb.table("ai_jobs").select("id,purpose,created_at").eq("status", "queued").order("created_at").limit(10).execute().data or []
        print(f"# queued {len(rows)}: {[r['purpose'] for r in rows]}")
        print(flat.status())
        return 0
    last_hb = 0.0
    last_hk = 0.0
    fail_streak = 0
    while True:
        now = time.time()
        try:
            if now - last_hb >= HEARTBEAT_SEC:
                heartbeat(sb)
                last_hb = now
            if now - last_hk >= 600:
                housekeeping(sb)
                last_hk = now
            row = claim(sb)
            fail_streak = 0
            if row:
                print(f"{now_iso()} job {row['id']} {row.get('purpose')}: {run_job(sb, row)}", flush=True)
                continue  # 溜まっていれば続けて処理
        except Exception as e:
            fail_streak += 1
            wait = fail_wait_sec(fail_streak)
            print(
                f"{now_iso()} worker error (streak={fail_streak}, wait={wait:.0f}s): "
                f"{type(e).__name__}: {str(e)[:200]}",
                flush=True,
            )
            if args.once:
                return 1
            time.sleep(wait)
            continue
        if args.once:
            return 0
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    raise SystemExit(main())
