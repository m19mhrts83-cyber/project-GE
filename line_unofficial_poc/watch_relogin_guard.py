#!/usr/bin/env python3
"""オプチャ常駐監視の「再ログインが必要」ガード（標準ライブラリのみ）。

保存トークンが無効（LINE が更新を 403 で拒否）になると、監視は落ちて KeepAlive で
起動をくり返し、そのたびに LINE へ更新を試していた（2026-11-09〜10、254 回）。これを止める。

  - chrline_client_utils が「保存トークンが無効・QR 不可」で終わるときに印（marker）を書く
  - runner は起動直後に --check し、印がある間は LINE に触らず待つ（起動のくり返しをしない）
  - runner は監視が落ちた後に --notify し、#ops に「判定: 🔴 要対応」を 1 回だけ出す
  - QR 再ログインで有効なクライアントが作れたら、chrline_client_utils が印を消す → 自動で再開

  python3 watch_relogin_guard.py --check            # 印なし=0、印あり=3
  python3 watch_relogin_guard.py --notify --dry-run # 投稿文だけ表示
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
MARKER = Path(os.environ.get(
    "LINE_WATCH_RELOGIN_MARKER",
    str(Path.home() / "Library/Logs/line_open_chat/watch_relogin_required.json"),
))
GIT_REPOS = Path(__file__).resolve().parents[1]
POST_SCRIPT = GIT_REPOS / "scripts" / "jarvis_slack_webhook_post.py"
ENV_FILE = GIT_REPOS / ".env.jarvis_private"
RELOGIN_CMD = ("cd ~/git-repos/line_unofficial_poc && ./run_patch.sh chrline_yoritoori_inbox_fetch.py "
               "--allow-qr-login --discover-thread-mids-dry-run")


def _now() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def read_marker(path: Path | None = None) -> dict | None:
    p = path or MARKER
    if not p.is_file():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_marker(reason: str, path: Path | None = None) -> None:
    """印を書く。既にあれば作成時刻と通知済みの記録は残す。"""
    p = path or MARKER
    cur = read_marker(p) or {}
    cur.setdefault("created_at", _now())
    cur["reason"] = reason
    cur["last_seen_at"] = _now()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cur, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def clear_marker(path: Path | None = None) -> bool:
    p = path or MARKER
    try:
        p.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def notify_text(marker: dict) -> str:
    return "\n".join([
        "【ops】LINE オプチャ監視: 再ログインが必要",
        "判定: 🔴 要対応",
        f"1. 保存トークンが無効（{marker.get('reason') or 'LINE が更新を拒否'}）。{str(marker.get('created_at', ''))[:16]} から",
        "   監視は再試行をやめて待機中（LINE には触っていません）",
        "2. Mac のターミナルで QR 再ログイン（スマホの LINE で QR を読む）",
        f"   {RELOGIN_CMD}",
        "3. ログインできたら印が消え、監視は自動で再開します",
    ])


def _post_env() -> dict:
    env = dict(os.environ)
    if ENV_FILE.is_file():  # 値は表示しない。投稿スクリプトに渡すだけ
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.replace("export ", "").strip()
            env.setdefault(k, v.strip().strip('"').strip("'"))
    return env


def notify_once(*, dry_run: bool, path: Path | None = None) -> str:
    """印があり、まだ知らせていなければ #ops に 1 回だけ出す。"""
    p = path or MARKER
    m = read_marker(p)
    if m is None:
        return "no_marker"
    if m.get("notified_at"):
        return "already_notified"
    text = notify_text(m)
    if dry_run or os.environ.get("LINE_WATCH_NOTIFY_DRY_RUN") == "1":
        print(text)
        return "dry_run"
    r = subprocess.run([sys.executable, str(POST_SCRIPT), "--channel", "ops",
                        "--username", "LINE オプチャ監視", "--text", text],
                       env=_post_env(), capture_output=True, text=True)
    if r.returncode == 0:
        m["notified_at"] = _now()
        p.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return "posted"
    return f"post_failed:{r.returncode}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="印なし=0／印あり=3")
    ap.add_argument("--notify", action="store_true", help="#ops に 1 回だけ知らせる")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.check:
        return 3 if read_marker() is not None else 0
    if args.notify:
        print(f"# notify: {notify_once(dry_run=args.dry_run)}", file=sys.stderr)
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
