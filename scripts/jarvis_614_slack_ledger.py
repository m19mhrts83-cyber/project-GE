#!/usr/bin/env python3
"""614 ポイント・還元ウォッチ — Slack 投稿の台帳と『送信済みか』の確認（P1・工程19/21）。

台帳 `slack_ledger.jsonl`（追記のみ）の1行＝1回の状態遷移。同じ通知（種別＋チャンネル＋本文の指紋）の
最新の状態を見て、再投稿してよいかを決める:

  sending   投稿を始めた（応答を受けるまでの印。落ちて残れば『結果不明』扱い）
  sent      送信できた（確認済み）
  unknown   届いたか分からない。**自動では再投稿しない**（確認できた時だけ sent / not_sent に進む）
  not_sent  届いていないと確定（HTTP エラー・接続できず・履歴を見て無かった）→ 1回だけ再試行してよい
  held      控えを保存できず投稿を保留した

Incoming Webhook は書き込み専用で、送れたかを聞けない。確認できるのは Slack の履歴を読める時だけ
（SLACK_BOT_TOKEN があり、チャンネルに入っている時）。確認できなければ unknown のままにし、再投稿しない。
本文・金額は台帳に書かない（指紋とチャンネルと run_id だけ）。
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_614_ops as ops  # noqa: E402
import jarvis_614_runlog as runlog  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
HUB_CONFIG = REPO / "config" / "slack_ai_team_hub.yaml"
LEDGER_WINDOW_HOURS = 24
CONFIRM_LOOKBACK_SEC = 30 * 60

BLOCKING = ("sent", "unknown", "sending")  # 再投稿しない状態


def ledger_path() -> Path:
    return runlog.log_dir() / "slack_ledger.jsonl"


def fingerprint(text: str) -> str:
    norm = "\n".join(ln.rstrip() for ln in (text or "").splitlines()).strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:20]


def key(kind: str, channel: str, text: str) -> str:
    return f"{kind}|{channel}|{fingerprint(text)}"


def record(k: str, status: str, *, run_id: str, note: str = "") -> bool:
    return ops._append_jsonl(
        ledger_path(),
        {"key": k, "status": status, "run_id": run_id, "at": runlog.now_iso(), "note": note[:120]},
    )


def latest(k: str, *, now: datetime | None = None, hours: int = LEDGER_WINDOW_HOURS) -> dict[str, Any] | None:
    cutoff = (now or datetime.now(runlog.JST)) - timedelta(hours=hours)
    found = None
    for r in ops._read_jsonl(ledger_path()):
        if r.get("key") != k:
            continue
        try:
            if datetime.fromisoformat(str(r.get("at"))) < cutoff:
                continue
        except ValueError:
            continue
        found = r
    return found


def should_skip(k: str) -> str | None:
    """再投稿してはいけない状態なら理由。sending が残っている＝前回が途中で落ちた＝結果不明として扱う。"""
    e = latest(k)
    if e and e.get("status") in BLOCKING:
        return str(e["status"])
    return None


# ---- 送信済みの確認 ---------------------------------------------------------

_LINK = re.compile(r"<([^>|]+)(?:\|[^>]*)?>")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", _LINK.sub(r"\1", html.unescape(s or ""))).strip()


def text_matches(message_text: str, sent_text: str) -> bool:
    """送った本文の各行が、履歴のメッセージに全部含まれるか（署名行・フッタが足されても一致）。"""
    lines = [_norm(ln) for ln in (sent_text or "").splitlines() if ln.strip()]
    msg = _norm(message_text)
    return bool(lines) and all(ln in msg for ln in lines)


def channel_id(channel: str) -> str:
    try:
        import yaml

        cfg = yaml.safe_load(HUB_CONFIG.read_text(encoding="utf-8")) or {}
        return str(((cfg.get("channels") or {}).get(channel) or {}).get("id") or "")
    except Exception:  # noqa: BLE001
        return ""


def slack_token() -> str:
    return (
        (os.environ.get("SLACK_BOT_TOKEN") or "").strip()
        or (os.environ.get("SLACK_USER_TOKEN") or "").strip()
        or (os.environ.get("SLACK_TOKEN") or "").strip()
    )


HISTORY_LIMIT = 30


def fetch_history(cid: str, *, oldest: float, token: str) -> list[dict[str, Any]]:
    params = {"channel": cid, "limit": str(HISTORY_LIMIT), "oldest": f"{oldest:.6f}"}
    req = urllib.request.Request(
        "https://slack.com/api/conversations.history?" + urllib.parse.urlencode(params),
        headers={"Authorization": f"Bearer {token}"}, method="GET",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(str(data.get("error") or "slack_api_error"))
    return list(data.get("messages") or [])


def confirm_sent(
    channel: str, text: str, *, history: Callable[..., list[dict[str, Any]]] | None = None
) -> bool | None:
    """True=届いている／False=履歴を読めて、無かった／None=確認できない（トークン無し・権限・API エラー）。"""
    token = slack_token()
    cid = channel_id(channel)
    if not token or not cid:
        return None
    try:
        msgs = (history or fetch_history)(cid, oldest=time.time() - CONFIRM_LOOKBACK_SEC, token=token)
    except Exception:  # noqa: BLE001 — not_in_channel / missing_scope / ネットワーク等
        return None
    if any(text_matches(str(m.get("text") or ""), text) for m in msgs):
        return True
    # 窓内のメッセージが上限に達していたら、全部は見えていない。『無かった』とは言えない
    return None if len(msgs) >= HISTORY_LIMIT else False
