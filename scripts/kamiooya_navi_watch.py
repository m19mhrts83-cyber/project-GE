#!/usr/bin/env python3
"""神大家AIナビ（ライモ）の停止を見回る（2026-11-25、第4回協議ToDo）。

GitHub Actions から10分ごとに呼ぶ。AIナビのURLを開き、開けなければ60秒あけてもう1回試す。
2回続けて開けなければ「停止中」と判断する（1回だけの失敗では騒がない）。

状態は docs/kamiooya-navi-status.json に置く。入口ページ docs/kamiooya-navi.html がこれを読み、
停止中なら「ただいま一時停止中です」を出し、動いていればAIナビへそのまま移る。
状態が変わった時だけファイルを書き、Slack #ops へ知らせる（同じ状態の繰り返し通知はしない）。

使い方:
    python scripts/kamiooya_navi_watch.py            # 見回り（状態が変われば書く・知らせる）
    python scripts/kamiooya_navi_watch.py --dry-run  # 書かず・知らせず、判定だけ表示
終了コード: 0 = 判定できた（停止中でも0）。状態ファイルが壊れている等は 1。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

APP_URL = "https://ma-54t2keqdelz3.raimo-app.buzz/"
STATUS_PATH = Path(__file__).resolve().parents[1] / "docs" / "kamiooya-navi-status.json"
JST = timezone(timedelta(hours=9))
RETRY_WAIT_SECONDS = 60
TIMEOUT_SECONDS = 20


def probe(url: str = APP_URL, timeout: int = TIMEOUT_SECONDS) -> tuple[bool, str]:
    """開ければ (True, 理由)。5xx・通信失敗・時間切れは (False, 理由)。4xx はライモ自体は動いているので up。"""
    req = urllib.request.Request(url, headers={"User-Agent": "kamiooya-navi-watch/1.0", "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        return (e.code < 500), f"HTTP {e.code}"
    except Exception as e:  # 名前解決・接続・時間切れ
        return False, type(e).__name__


def judge(first: tuple[bool, str], second: tuple[bool, str] | None) -> tuple[str, str]:
    """1回目が開ければ up。1回目も2回目も開けなければ down。2回目で開ければ up（一時的な揺れ）。"""
    if first[0]:
        return "up", first[1]
    if second is None:
        return "up", first[1] + "（再確認なし）"
    if second[0]:
        return "up", f"{first[1]} のあと {second[1]}"
    return "down", f"{first[1]} / {second[1]}"


def load_status(path: Path = STATUS_PATH) -> dict:
    if not path.exists():
        return {"state": "up", "since": None}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("state") not in ("up", "down"):
        raise ValueError("state が up/down ではありません")
    return data


def next_status(prev: dict, state: str, detail: str, now: datetime) -> dict | None:
    """状態が変わった時だけ新しい内容を返す。変わらなければ None（書かない・知らせない）。"""
    if prev.get("state") == state:
        return None
    return {
        "state": state,
        "since": now.astimezone(JST).isoformat(timespec="minutes"),
        "detail": detail,
        "app_url": APP_URL,
        "note": "kamiooya_navi_watch.py が状態の変わった時だけ書きます。手で直す時も state は up / down のどちらか。",
    }


def slack_text(new: dict, prev: dict) -> str:
    when = new["since"].replace("T", " ")
    if new["state"] == "down":
        return (f":red_circle: 神大家AIナビが開けません（{when} 確認、{new['detail']}）。"
                f"入口ページは「一時停止中」を表示しています。{APP_URL}")
    started = (prev.get("since") or "").replace("T", " ")
    return (f":large_green_circle: 神大家AIナビが戻りました（{when} 確認"
            + (f"、停止の確認は {started}" if started else "") + "）。入口ページは通常に戻りました。")


def post_slack(text: str) -> None:
    hook = os.getenv("SLACK_WEBHOOK_AI_TEAM_OPS", "")
    if not hook:
        print("::warning::SLACK_WEBHOOK_AI_TEAM_OPS が無いので Slack には知らせません")
        return
    body = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(hook, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    try:
        prev = load_status()
    except Exception as e:
        print(f"::error::状態ファイルが読めません: {e}")
        return 1
    first = probe()
    second = None
    if not first[0]:
        time.sleep(0 if args.dry_run else RETRY_WAIT_SECONDS)
        second = probe()
    state, detail = judge(first, second)
    print(f"判定: {state}（{detail}）／前回: {prev.get('state')}")
    new = next_status(prev, state, detail, datetime.now(timezone.utc))
    if new is None:
        print("状態は変わっていません（書かない・知らせない）")
        return 0
    if args.dry_run:
        print("dry-run: 書くはずの内容", json.dumps(new, ensure_ascii=False))
        return 0
    STATUS_PATH.write_text(json.dumps(new, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"状態ファイルを書きました: {new['state']}")
    try:
        post_slack(slack_text(new, prev))
    except Exception as e:  # 知らせの失敗で状態の反映は止めない
        print(f"::warning::Slack への知らせに失敗: {type(e).__name__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
