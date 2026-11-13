#!/usr/bin/env python3
"""メール要対応を #ops に出す（毎朝 05:00 の夜間トリアージの最後・Mac launchd night-triage）。

2026-11-13 松野さん: 🔴 はパートナー関係など本当に要対応のメールが溜まったときだけ。
ゴミメールが溜まっているだけなら赤にしない。溜まった分は週次で判断デスクで 3〜5 件ずつ片付ける。

  毎朝: 🔴 のときだけ投稿（パートナー／人が書いたメールが平日3日以上止まっている、
        または queue の更新が2日以上止まっている）。🟡🟢 は投稿しない。
  日曜: 週次まとめ（今週見る 3〜5 件・判断デスクへのリンク）を必ず1本。
  毎回: 流し読み（skim）で7日たったものは自動で「見た」（skipped）にする。

色の決め方は scripts/jarvis_mail_ops_signal.py。116 の健全性（件数だけ）は #ops に出さなくした。

  python scripts/jarvis_night_triage_ops_report.py --dry-run
  python scripts/jarvis_night_triage_ops_report.py --dry-run --weekly
  python scripts/jarvis_night_triage_ops_report.py --post

停止: JARVIS_NIGHT_TRIAGE_OPS_REPORT_DISABLE=1
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_mail_ops_signal as ms  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
STATE = REPO / ".jarvis_state" / "night_triage_ops_report.json"
POST = REPO / "scripts" / "jarvis_slack_webhook_post.py"
WEEKLY_WEEKDAY = 6  # 日曜
CHANGED_ON = date(2026, 11, 13)  # 色の決め方を変えた日


def _days_since(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    return (datetime.now(JST).date() - dt.astimezone(JST).date()).days


def queue_stale_days() -> int | None:
    try:
        from jarvis_night_triage import load_queue

        return _days_since(load_queue().get("updated_at"))
    except Exception:  # noqa: BLE001
        return None


def stale_text(days: int) -> str:
    return "\n".join([
        "【ops】夜間トリアージが止まっています",
        f"判定: 🔴 要対応 — queue の更新が {days}日止まっています",
        "次: Mac の night-triage（~/Library/Logs/jarvis_night_triage）を確認",
    ])


def _post(text: str, level: str) -> int:
    r = subprocess.run(
        [sys.executable, str(POST), "--channel", "ops", "--text", text,
         "--username", "メール要対応", "--signal", level],
        cwd=str(REPO),
        check=False,
    )
    return int(r.returncode)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--post", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--weekly", action="store_true", help="曜日に関係なく週次まとめを作る")
    ap.add_argument("--force", action="store_true", help="同日判定を無視")
    args = ap.parse_args()
    if (os.environ.get("JARVIS_NIGHT_TRIAGE_OPS_REPORT_DISABLE") or "").strip() in ("1", "true", "yes"):
        print("⏭ disabled")
        return 0
    dry = args.dry_run or not args.post

    expired = ms.expire_old_skim(dry_run=dry)
    items, source = ms.fetch_pending()
    s = ms.classify(items)
    stale_days = queue_stale_days()
    print(
        f"📎 mail ops signal={s['level']} source={source} total={s['total']} "
        f"human={len(s['human'])} stale={len(s['stale'])} skim={s['skim']} other={s['other']} "
        f"skim_expired={expired}{'(dry)' if dry else ''} queue_stale_days={stale_days}"
    )

    now = datetime.now(JST)
    today = now.strftime("%Y-%m-%d")
    weekly = args.weekly or now.weekday() == WEEKLY_WEEKDAY
    posts: list[tuple[str, str, str]] = []  # (kind, level, text)
    if weekly:
        picks = ms.weekly_pick(s, items)
        level = "red" if s["stale"] else ("yellow" if s["total"] else "green")
        posts.append(("weekly", level, ms.weekly_text(s, picks, desk_url=ms.desk_url(), expired=expired)))
    elif s["level"] == "red":
        posts.append(("daily", "red", ms.daily_text(s, desk_url=ms.desk_url())))
    elif now.date() < CHANGED_ON + timedelta(days=7):
        # 立ち上げ・変更から約1週間は 🟢🟡 も報告（共通ルール18）
        posts.append(("daily", s["level"], ms.status_text(s)))
    if (stale_days or 0) >= 2:
        posts.append(("stale", "red", stale_text(int(stale_days or 0))))
    if not posts:
        print("⏭ 🔴 なし（🟡🟢 は毎朝は出さない・日曜の週次まとめへ）")
        return 0

    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        st = {}
    rc = 0
    for kind, level, text in posts:
        if dry:
            print(f"--- dry-run #ops ({kind}) ---\n{text}")
            continue
        key = f"last_post_date_{kind}"
        if not args.force and st.get(key) == today:
            print(f"⏭ 本日 #ops に出し済み ({kind})")
            continue
        r = _post(text, level)
        rc = rc or r
        if r == 0:
            st[key] = today
    if not dry:
        st.update({"last_level": s["level"], "last_total": s["total"], "last_stale": len(s["stale"])})
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
