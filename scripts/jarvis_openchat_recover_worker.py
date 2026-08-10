#!/usr/bin/env python3
"""
オプチャ静かな失敗の既知レシピ復旧（Mac Worker）。

watch_status.openchat_threads.payload.mac_recipe.status=queued を拾い、
pause → --init discover+append → --init --no-main backfill → resume → health push。

QR が必要／失敗時は status=error（勝手に待たない）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_openchat_recover_worker.py
  python scripts/jarvis_openchat_recover_worker.py --dry-run
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
POC = REPO / "line_unofficial_poc"
RUN_PATCH = POC / "run_patch.sh"
PAUSE = POC / "launchd" / "open_chat_watch_pause.sh"
RESUME = POC / "launchd" / "open_chat_watch_resume.sh"
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"
RECIPE_ID = "openchat_init_bootstrap"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sb_client():
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要")
    from supabase import create_client

    return create_client(url, key)


def load_recipe(sb: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    res = (
        sb.table("watch_status")
        .select("id,payload")
        .eq("id", "openchat_threads")
        .limit(1)
        .execute()
    )
    rows = res.data or []
    row = rows[0] if rows else {}
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    rem = payload.get("remediation") if isinstance(payload.get("remediation"), dict) else {}
    recipe = rem.get("mac_recipe") if isinstance(rem.get("mac_recipe"), dict) else {}
    if not recipe and isinstance(payload.get("mac_recipe"), dict):
        recipe = payload.get("mac_recipe") or {}
    return payload, rem, recipe


def save_recipe(
    sb: Any,
    payload: dict[str, Any],
    rem: dict[str, Any],
    recipe: dict[str, Any],
) -> None:
    rem = dict(rem)
    rem["mac_recipe"] = recipe
    payload = dict(payload)
    payload["remediation"] = rem
    payload["mac_recipe"] = recipe
    sb.table("watch_status").update(
        {"payload": payload, "updated_at": now_iso()}
    ).eq("id", "openchat_threads").execute()


def looks_like_qr_needed(text: str) -> bool:
    t = (text or "").lower()
    return any(
        x in t
        for x in (
            "qr",
            "scan",
            "login required",
            "allow-qr-login",
            "logged_out",
            "v3_token_client_logged_out",
        )
    )


def run_recipe(route_ids: list[str], *, dry_run: bool) -> tuple[bool, str]:
    if not route_ids:
        return False, "route_ids 空"
    if not RUN_PATCH.is_file():
        return False, f"run_patch.sh なし: {RUN_PATCH}"

    pause = [str(PAUSE)]
    discover = [
        str(RUN_PATCH),
        "chrline_open_chat_to_md.py",
        "--allow-qr-login",
        "--discover-only",
        "--discover-thread-mids",
        "--init",
        "--auto-append-thread-mids",
        "--route-ids",
        *route_ids,
        "--min-hit-count",
        "1",
        "--max-pages-per-stream",
        "80",
    ]
    backfill = [
        str(RUN_PATCH),
        "chrline_open_chat_to_md.py",
        "--allow-qr-login",
        "--init",
        "--no-main",
        "--join-threads-yes",
        "--route-ids",
        *route_ids,
        "--max-pages-per-stream",
        "80",
    ]
    resume = [str(RESUME)]
    health = [
        str(PY if PY.is_file() else sys.executable),
        str(REPO / "scripts" / "jarvis_openchat_thread_health.py"),
        "--push",
    ]

    steps = [
        ("pause", pause, 60),
        ("discover", discover, 600),
        ("backfill", backfill, 900),
        ("resume", resume, 60),
        ("health", health, 180),
    ]
    if dry_run:
        for name, argv, _ in steps:
            print(f"# dry-run {name}: {' '.join(argv)}")
        return True, "dry_run"

    logs: list[str] = []
    try:
        for name, argv, timeout in steps:
            print(f"# run {name}")
            cwd = str(POC) if name in {"pause", "discover", "backfill", "resume"} else str(REPO)
            r = subprocess.run(
                argv,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=os.environ.copy(),
            )
            out = (r.stdout or "") + "\n" + (r.stderr or "")
            logs.append(f"[{name} rc={r.returncode}]\n{out[-4000:]}")
            if r.returncode != 0:
                if looks_like_qr_needed(out):
                    # 必ず resume を試みる
                    subprocess.run(resume, cwd=str(POC), capture_output=True, text=True, timeout=60)
                    return False, "QR要・Cursorへ（トークン失効の可能性）"
                subprocess.run(resume, cwd=str(POC), capture_output=True, text=True, timeout=60)
                return False, f"{name} failed rc={r.returncode}: {out[-240:]}"
        # 簡易サマリ
        sync_line = ""
        for block in logs:
            for line in block.splitlines():
                if "thread sync:" in line or "thread_mids 追記" in line:
                    sync_line = line.strip()
        return True, sync_line or "ok"
    except subprocess.TimeoutExpired as e:
        subprocess.run(resume, cwd=str(POC), capture_output=True, text=True, timeout=60)
        return False, f"timeout: {e}"
    except Exception as e:
        subprocess.run(resume, cwd=str(POC), capture_output=True, text=True, timeout=60)
        return False, str(e)[:400]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    sb = sb_client()
    payload, rem, recipe = load_recipe(sb)
    if str(recipe.get("id") or "") != RECIPE_ID:
        print("# no openchat_init_bootstrap recipe")
        return 0
    if str(recipe.get("status") or "") != "queued":
        print(f"# skip status={recipe.get('status')}")
        return 0

    route_ids = [str(x).strip() for x in (recipe.get("route_ids") or []) if str(x).strip()]
    print(f"# queued routes={route_ids}")

    running = dict(recipe)
    running["status"] = "running"
    running["started_at"] = now_iso()
    if not args.dry_run:
        save_recipe(sb, payload, rem, running)

    ok, result = run_recipe(route_ids, dry_run=bool(args.dry_run))
    finished = dict(running)
    finished["finished_at"] = now_iso()
    if ok:
        finished["status"] = "done"
        finished["result"] = result[:400]
        finished["error"] = None
    else:
        finished["status"] = "error"
        finished["error"] = result[:400]
        finished["result"] = None

    if args.dry_run:
        print(json.dumps({"ok": ok, "result": result}, ensure_ascii=False))
        return 0

    # 最新 payload を再読して上書き衝突を減らす
    payload2, rem2, _ = load_recipe(sb)
    save_recipe(sb, payload2, rem2, finished)
    print(json.dumps({"ok": ok, "status": finished["status"], "result": result}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
