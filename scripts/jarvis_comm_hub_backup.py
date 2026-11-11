#!/usr/bin/env python3
"""コミュニケーション台帳（comm hub）の機械の予備（Mac launchd から1日2回）。

GHA が止まったときだけ代わりに動く。heartbeat（sync_meta の job_ok:<job>）を見て判断する。
  - 台帳書き込み（job_ok:comm_write）が WRITE_STALE_H 時間より古い
      → link-pending --apply（未返信のつなぎ直し＋閉じ残しの戻し）だけ代走し job_ok:comm_write_backup を書く
        （新しいメールの取り込みは GHA 側でしかできない。止まりが続けば #ops へ）
  - 今日の突き合わせ（job_ok:comm_reconcile）がまだで、JST RECONCILE_AFTER_H 時以降
      → reconcile を #ai-hub に3行（source=backup）
  - 台帳書き込みが ALERT_H 時間より古い → #ops に1日1回「台帳 止まっています」
  - 毎回: ボットの受付の表（comm_intake）の new を台帳へ本登録（ingest-intake。失敗しても続ける）
新しいメールは取り込まないので、予備はあくまで「止まっている間の穴埋め」と「気づかせる」役。
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_comm_hub as hub  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
WRITE_STALE_H = 18
ALERT_H = 24
RECONCILE_AFTER_H = 13  # 昼GHA（05:00予定・実際は昼ごろ）の後


def decide(
    now: datetime,
    write_hb: dict[str, Any] | None,
    reconcile_hb: dict[str, Any] | None,
    alert_hb: dict[str, Any] | None,
) -> list[str]:
    """やることの一覧（順番どおり）。純関数（テスト用）。"""
    acts: list[str] = []
    write_age = (now - write_hb["at"]) if write_hb else None
    if write_age is None or write_age > timedelta(hours=WRITE_STALE_H):
        acts.append("link_pending")
    today = now.astimezone(JST).date()
    done_today = reconcile_hb is not None and reconcile_hb["at"].astimezone(JST).date() == today
    if not done_today and now.astimezone(JST).hour >= RECONCILE_AFTER_H:
        acts.append("reconcile")
    alerted_today = alert_hb is not None and alert_hb["at"].astimezone(JST).date() == today
    if (write_age is None or write_age > timedelta(hours=ALERT_H)) and not alerted_today:
        acts.append("alert")
    return acts


def alert_text(write_hb: dict[str, Any] | None) -> str:
    last = (
        f"{write_hb['at'].astimezone(JST):%m/%d %H:%M}（{hub._source_label(write_hb['source'])}）"
        if write_hb
        else "記録なし"
    )
    return "\n".join(
        [
            f"1 台帳 止まっています（最後の書き込み {last}）",
            "2 予備がつなぎ直しだけ代走中。新しいメールは入っていない",
            "3 番頭さん→窓口で comm_write を再実行／2回失敗なら Jarvis・松野さんへ",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="判断だけ表示（書き込み・投稿なし）")
    args = ap.parse_args(argv)
    sb = hub.client()
    now = datetime.now(ZoneInfo("UTC"))
    write_hb = hub.read_heartbeat(sb, "comm_write")
    acts = decide(now, write_hb, hub.read_heartbeat(sb, "comm_reconcile"), hub.read_heartbeat(sb, "comm_alert"))
    print(f"# comm backup: write={write_hb and write_hb['at'].isoformat()} acts={acts}")
    if args.dry_run:
        return 0
    rc = 0
    # 受付の表（ボット）は毎回取り込む（GHA と両方で走っても external_id で1行にまとまる）
    try:
        st = hub.ingest_intake(sb, apply=True)
        st.pop("reasons", None)
        print(f"# comm backup ingest-intake: {st}")
    except Exception as e:  # noqa: BLE001
        print(f"# comm backup ingest-intake soft-fail: {type(e).__name__}: {e}")
    if "link_pending" in acts:
        st = hub.link_pending(sb, apply=True)
        st.pop("_closed_items", None)
        print(f"# comm backup link-pending: {st}")
        hub.write_heartbeat(sb, "comm_write_backup", "backup")
    if "reconcile" in acts:
        c = hub.reconcile_counts(sb)
        r = hub.post_slack(hub.reconcile_slack_text(c, source="backup", last_write=write_hb))
        if r == 0:
            hub.write_heartbeat(sb, "comm_reconcile", "backup")
        rc = rc or r
    if "alert" in acts:
        r = hub.post_slack(alert_text(write_hb), channel="ops")
        if r == 0:
            hub.write_heartbeat(sb, "comm_alert", "backup")
        rc = rc or r
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
