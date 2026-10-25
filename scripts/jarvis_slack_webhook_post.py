#!/usr/bin/env python3
"""Post a simple message to Slack Incoming Webhook (AIエージェントチーム).

Secrets (`.env.jarvis_private`):
  SLACK_WEBHOOK_AI_TEAM_REPORT / CONSULT / OPS / HUB（#ai-hub）
  / DEAL_ACTIVE（#deal-active）
未設定チャンネルは REPORT にフォールバック（本文先頭に 【#consult】等を付ける）。

FB スレ案内フッタは既定オフ（2026-10-25）。付けるなら JARVIS_SLACK_FB_FOOTER_ENABLE=1。
--no-fb-footer / JARVIS_SLACK_FB_FOOTER_DISABLE=1 は常にオフ。
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jarvis_slack_report_fb_lib import append_fb_footer  # noqa: E402

# 論理名 → 正規キー
_CHANNEL_ALIASES = {
    "ai-hub": "hub",
    "ai_hub": "hub",
    "deal-active": "deal",
    "deal_active": "deal",
}

_DISPLAY = {
    "hub": "ai-hub",
    "deal": "deal-active",
}


def _normalize_channel(channel: str) -> str:
    ch = (channel or "report").strip().lstrip("#").lower()
    ch = _CHANNEL_ALIASES.get(ch, ch)
    if ch not in ("report", "consult", "ops", "hub", "deal"):
        ch = "report"
    return ch


def _display_name(ch: str) -> str:
    return _DISPLAY.get(ch, ch)


# 同一本文の連投防止（317／116／メール要対応などの二重投稿対策）
DEDUPE_TTL_DEFAULT = 1800
DEDUPE_PATH = (
    Path(__file__).resolve().parents[1] / ".jarvis_state" / "slack_webhook_dedupe.json"
)


def _dedupe_ttl() -> int:
    raw = (os.environ.get("JARVIS_SLACK_DEDUPE_TTL_SEC") or "").strip()
    if raw.isdigit():
        return int(raw)
    return DEDUPE_TTL_DEFAULT


def _dedupe_disabled() -> bool:
    return (os.environ.get("JARVIS_SLACK_DEDUPE_DISABLE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _dedupe_key(channel: str, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]
    return f"{channel}|{digest}"


def _load_dedupe() -> dict[str, float]:
    try:
        raw = json.loads(DEDUPE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(k): float(v) for k, v in raw.items()} if isinstance(raw, dict) else {}


def _save_dedupe(state: dict[str, float], *, ttl: int) -> None:
    cutoff = time.time() - max(ttl, 60) * 4
    pruned = {k: v for k, v in state.items() if v >= cutoff}
    DEDUPE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = DEDUPE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(pruned, ensure_ascii=False), encoding="utf-8")
    tmp.replace(DEDUPE_PATH)


def recent_duplicate_age(key: str, *, ttl: int) -> float | None:
    """同じ本文を ttl 秒以内に投稿していれば経過秒を返す。"""
    if _dedupe_disabled():
        return None
    lock = DEDUPE_PATH.with_suffix(".lock")
    DEDUPE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(lock, "a+") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            state = _load_dedupe()
            ts = state.get(key)
            if ts is None:
                return None
            age = time.time() - ts
            return age if age < ttl else None
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def remember_post(key: str, *, ttl: int) -> None:
    lock = DEDUPE_PATH.with_suffix(".lock")
    DEDUPE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(lock, "a+") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            state = _load_dedupe()
            state[key] = time.time()
            _save_dedupe(state, ttl=ttl)
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _webhook_for(channel: str) -> tuple[str, str, bool]:
    """Return (url, resolved_channel, used_fallback)."""
    ch = _normalize_channel(channel)
    env_map = {
        "report": "SLACK_WEBHOOK_AI_TEAM_REPORT",
        "consult": "SLACK_WEBHOOK_AI_TEAM_CONSULT",
        "ops": "SLACK_WEBHOOK_AI_TEAM_OPS",
        "hub": "SLACK_WEBHOOK_AI_TEAM_HUB",
        "deal": "SLACK_WEBHOOK_AI_TEAM_DEAL_ACTIVE",
    }
    url = (os.environ.get(env_map[ch]) or "").strip()
    if url:
        return url, ch, False
    # fallback: REPORT（専用 Webhook が無いとき）
    report = (os.environ.get("SLACK_WEBHOOK_AI_TEAM_REPORT") or "").strip()
    if report and ch != "report":
        return report, "report", True
    if report:
        return report, "report", False
    return "", ch, False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--channel",
        default="report",
        help=(
            "論理名: report | consult | ops | hub | deal "
            "（別名: ai-hub / deal-active）"
        ),
    )
    ap.add_argument("--text", required=True, help="投稿本文")
    ap.add_argument(
        "--username",
        default="Jarvis AI Team",
        help="表示名（Incoming Webhook が許可する場合）",
    )
    ap.add_argument(
        "--no-fb-footer",
        action="store_true",
        help="report/consult 末尾の FB スレ案内を付けない",
    )
    ap.add_argument(
        "--allow-duplicate",
        action="store_true",
        help="同一本文でも直近投稿を無視して再投稿する（既定は TTL 内スキップ）",
    )
    args = ap.parse_args()

    requested = _normalize_channel(args.channel)
    display = _display_name(requested)
    url, resolved, fallback = _webhook_for(args.channel)
    if not url:
        print(
            "❌ Webhook URL がありません。"
            " .env.jarvis_private に SLACK_WEBHOOK_AI_TEAM_REPORT"
            "（任意: CONSULT / OPS / HUB / DEAL_ACTIVE）を設定してください。",
            file=sys.stderr,
        )
        return 2

    text = args.text
    if fallback and requested != resolved:
        text = f"【#{display}】\n{text}"
    # FB 案内は論理チャンネル（requested）基準。fallback で #report に落ちても consult なら付ける
    if not args.no_fb_footer:
        text = append_fb_footer(text, channel=requested)
    resolved_display = _display_name(resolved)

    # 同一本文の連投防止（別スクリプト間の二重投稿もここで潰す）
    ttl = _dedupe_ttl()
    dedupe_key = _dedupe_key(resolved, text)
    if not args.allow_duplicate:
        age = recent_duplicate_age(dedupe_key, ttl=ttl)
        if age is not None:
            print(
                f"⏭ Slack webhook duplicate skip: #{resolved_display} "
                f"same text {int(age)}s ago (ttl={ttl}s)"
            )
            return 0

    payload = {"text": text, "username": args.username}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            remember_post(dedupe_key, ttl=ttl)
            fb = " fallback→#report" if fallback else ""
            print(
                f"✅ Slack webhook OK status={resp.status} "
                f"requested=#{display} resolved=#{resolved_display}{fb} body={body!r}"
            )
            return 0
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"❌ Slack webhook HTTP {e.code}: {err}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ Slack webhook failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
