#!/usr/bin/env python3
"""Slack 報告スレの FB 返信を拾い、分類して Ack する（Phase 1）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_slack_report_fb_poll.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_slack_report_fb_poll.py --apply
  ~/selenium_env/venv/bin/python scripts/jarvis_slack_report_fb_poll.py --apply --mark-only
  # 受けた → 対応した（毎日の FB 対応・Miss Lemon 定期タスク）
  ~/selenium_env/venv/bin/python scripts/jarvis_slack_report_fb_poll.py --pending
  ~/selenium_env/venv/bin/python scripts/jarvis_slack_report_fb_poll.py --done consult:1792616568.546519 \
      --summary "211 のクローズ済み案件を送らないようにした（PR #NNN）"

入口: #report / #consult の親投稿スレ
確認: Ack は自動。処置は毎日の FB 対応（Claude 定期タスク slack-fb-daily）が直して --done
履歴: .jarvis_state/slack_report_fb.json
停止: JARVIS_SLACK_FB_THREAD_DISABLE=1

正本: docs/AIエージェントチーム/40_Slack報告FB_スレ拾い_20261020.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jarvis_slack_report_fb_lib import (  # noqa: E402
    REACTION_DONE,
    REACTION_SEEN,
    build_ack_text,
    build_done_text,
    classify_fb_reply,
    has_handled_reaction,
    is_ack_or_bot_reply,
    kind_label_ja,
    poll_enabled,
)

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "config" / "slack_ai_team_hub.yaml"
STATE = REPO / ".jarvis_state" / "slack_report_fb.json"
EXAMPLE = REPO / ".jarvis_state" / "slack_report_fb.example.json"
JST = timezone(timedelta(hours=9))

# 対象（人向け報告・相談）
TARGET_CHANNELS = ("report", "consult")
DEFAULT_PARENT_LIMIT = 15
DEFAULT_LOOKBACK_HOURS = 72


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def load_config() -> dict[str, Any]:
    if not CONFIG.is_file():
        return {}
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}


def load_state() -> dict[str, Any]:
    if STATE.is_file():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    if EXAMPLE.is_file():
        try:
            return json.loads(EXAMPLE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {"disabled": False, "processed": {}, "last_run_at": None}


def save_state(st: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def slack_token() -> str:
    return (
        (os.environ.get("SLACK_BOT_TOKEN") or "").strip()
        or (os.environ.get("SLACK_USER_TOKEN") or "").strip()
        or (os.environ.get("SLACK_TOKEN") or "").strip()
    )


def _api(method: str, token: str, params: dict[str, str]) -> dict[str, Any]:
    url = f"https://slack.com/api/{method}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or f"{method}_failed")
    return data


def _api_post(method: str, token: str, body: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"https://slack.com/api/{method}",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        out = json.loads(resp.read().decode("utf-8"))
    if not out.get("ok"):
        raise RuntimeError(out.get("error") or f"{method}_failed")
    return out


def history(
    channel_id: str, *, token: str, limit: int, oldest: float | None
) -> list[dict[str, Any]]:
    params: dict[str, str] = {"channel": channel_id, "limit": str(limit)}
    if oldest is not None:
        params["oldest"] = str(oldest)
    data = _api("conversations.history", token, params)
    return list(data.get("messages") or [])


def replies(channel_id: str, thread_ts: str, *, token: str, limit: int = 50) -> list[dict[str, Any]]:
    data = _api(
        "conversations.replies",
        token,
        {"channel": channel_id, "ts": thread_ts, "limit": str(limit)},
    )
    msgs = list(data.get("messages") or [])
    # 先頭は親
    return msgs[1:] if len(msgs) > 1 else []


def post_thread_ack(
    channel_id: str,
    thread_ts: str,
    text: str,
    *,
    token: str,
    dry_run: bool,
) -> str | None:
    body = {
        "channel": channel_id,
        "thread_ts": thread_ts,
        "text": text,
        "username": "AIチーム 報告FB",
    }
    if dry_run:
        print("# dry-run chat.postMessage (thread ack)")
        print(json.dumps(body, ensure_ascii=False, indent=2)[:2000])
        return "dry-run"
    out = _api_post("chat.postMessage", token, body)
    return str(out.get("ts") or "") or None


def add_reaction(
    channel_id: str,
    timestamp: str,
    name: str,
    *,
    token: str,
    dry_run: bool,
) -> bool:
    """元コメントにリアクション（見た＝eyes／対応済＝white_check_mark）。"""
    body = {
        "channel": channel_id,
        "timestamp": timestamp,
        "name": name,
    }
    if dry_run:
        print(f"# dry-run reactions.add name={name} ts={timestamp}")
        return True
    try:
        _api_post("reactions.add", token, body)
        return True
    except RuntimeError as e:
        # already_reacted は成功扱い
        if "already_reacted" in str(e):
            return True
        print(f"# warn reactions.add {name}: {e}", file=sys.stderr)
        return False


def processed_key(channel_key: str, reply_ts: str) -> str:
    return f"{channel_key}:{reply_ts}"


def is_pending(entry: dict[str, Any]) -> bool:
    """受けた（Ack 済み／mark のみ）で、まだ「対応した」になっていない人のコメント。"""
    if not isinstance(entry, dict):
        return False
    if str(entry.get("kind") or "").startswith("skip_"):
        return False
    if entry.get("done_at"):
        return False
    return bool(entry.get("ack_ts") or entry.get("mark_only"))


def pending_entries(processed: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    rows = [(k, v) for k, v in processed.items() if is_pending(v)]
    return sorted(rows, key=lambda kv: str(kv[1].get("at") or ""))


def prune_processed(processed: dict[str, Any], keep: int = 500) -> dict[str, Any]:
    """肥大防止。未対応（pending）は件数に関係なく残す。"""
    if len(processed) <= keep:
        return processed
    pend = {k: v for k, v in processed.items() if is_pending(v)}
    rest = sorted(
        ((k, v) for k, v in processed.items() if k not in pend),
        key=lambda kv: str((kv[1] or {}).get("at") or ""),
    )
    room = max(keep - len(pend), 0)
    out = dict(rest[-room:]) if room else {}
    out.update(pend)
    return out


def _channel_id(cfg: dict[str, Any], name: str) -> str:
    return str(((cfg.get("channels") or {}).get(name) or {}).get("id") or "").strip()


def _clip(text: str, n: int) -> str:
    t = (text or "").strip()
    return t if len(t) <= n else t[: n - 1] + "…"


def cmd_pending(st: dict[str, Any], cfg: dict[str, Any], token: str) -> int:
    """未対応 FB を JSON で出す。token があればスレ本文（親＋人の返信）も添える。"""
    out: list[dict[str, Any]] = []
    for key, v in pending_entries(dict(st.get("processed") or {})):
        ch = str(v.get("channel") or key.split(":", 1)[0])
        cid = _channel_id(cfg, ch)
        thread_ts = str(v.get("thread_ts") or "")
        reply_ts = str(v.get("reply_ts") or key.split(":", 1)[-1])
        row: dict[str, Any] = {
            "key": key,
            "channel": ch,
            "channel_id": cid,
            "thread_ts": thread_ts,
            "reply_ts": reply_ts,
            "kind": v.get("kind"),
            "acked_at": v.get("at"),
        }
        if token and cid and thread_ts:
            try:
                data = _api(
                    "conversations.replies",
                    token,
                    {"channel": cid, "ts": thread_ts, "limit": "50"},
                )
                msgs = list(data.get("messages") or [])
                if msgs:
                    row["parent"] = _clip(str(msgs[0].get("text") or ""), 600)
                row["comment"] = next(
                    (str(m.get("text") or "") for m in msgs if str(m.get("ts")) == reply_ts),
                    "",
                )
                # 元コメント以降のやり取り（追加の質問、他 AI がすでに直した報告など）
                row["followups"] = [
                    {
                        "own": is_ack_or_bot_reply(m),
                        "text": _clip(str(m.get("text") or ""), 400),
                    }
                    for m in msgs[1:]
                    if float(m.get("ts") or 0) > float(reply_ts or 0)
                ]
            except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as e:
                row["error"] = str(e)
        out.append(row)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"# pending={len(out)}", file=sys.stderr)
    return 0


def cmd_done(
    st: dict[str, Any],
    cfg: dict[str, Any],
    token: str,
    *,
    key: str,
    summary: str,
    dry_run: bool,
) -> int:
    """スレに「対応したよ」＋元コメントに ✅、state に done を記録。"""
    processed = dict(st.get("processed") or {})
    v = processed.get(key)
    if not isinstance(v, dict):
        print(f"❌ state に {key} がありません（--pending の key を使う）", file=sys.stderr)
        return 2
    if v.get("done_at"):
        print(f"# already done: {key}")
        return 0
    if not summary.strip():
        print("❌ --summary が空です（何をしたか1〜5行）", file=sys.stderr)
        return 2
    ch = str(v.get("channel") or key.split(":", 1)[0])
    cid = _channel_id(cfg, ch)
    thread_ts = str(v.get("thread_ts") or "")
    reply_ts = str(v.get("reply_ts") or key.split(":", 1)[-1])
    if not cid or not thread_ts:
        print(f"❌ channel_id/thread_ts 不明: {key}", file=sys.stderr)
        return 2
    text = build_done_text(summary=summary)
    try:
        dts = post_thread_ack(cid, thread_ts, text, token=token, dry_run=dry_run)
    except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as e:
        print(f"❌ 対応した投稿 失敗 {key}: {e}", file=sys.stderr)
        return 1
    add_reaction(cid, reply_ts, REACTION_DONE, token=token, dry_run=dry_run)
    if dry_run:
        return 0
    v.update({"done_at": now_iso(), "done_ts": dts, "done_summary": _clip(summary, 300)})
    processed[key] = v
    st["processed"] = processed
    save_state(st)
    print(f"✅ done {key}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="Ack を投稿せず分類結果だけ出す")
    ap.add_argument("--apply", action="store_true", help="スレに Ack を投稿する")
    ap.add_argument(
        "--mark-only",
        action="store_true",
        help="Ack せず processed だけ進める（取り込み済みにする）",
    )
    ap.add_argument("--limit", type=int, default=DEFAULT_PARENT_LIMIT, help="親投稿の読取上限/ch")
    ap.add_argument(
        "--lookback-hours",
        type=float,
        default=DEFAULT_LOOKBACK_HOURS,
        help="何時間前までの親を見るか",
    )
    ap.add_argument(
        "--channels",
        default="report,consult",
        help="カンマ区切り（既定 report,consult）",
    )
    ap.add_argument(
        "--pending",
        action="store_true",
        help="受けたが未対応の FB を JSON で出す（スレ本文つき）",
    )
    ap.add_argument("--done", metavar="KEY", help="対応済みにする（--pending の key）")
    ap.add_argument("--summary", default="", help="--done で返す「何をしたか」")
    args = ap.parse_args()

    if args.pending or args.done:
        st = load_state()
        cfg = load_config()
        token = slack_token()
        if args.pending:
            return cmd_pending(st, cfg, token)
        if not token and not args.dry_run:
            print("❌ SLACK_BOT_TOKEN がありません", file=sys.stderr)
            return 3
        return cmd_done(
            st, cfg, token, key=args.done, summary=args.summary, dry_run=args.dry_run
        )

    if not poll_enabled():
        print("disabled via JARVIS_SLACK_FB_THREAD_DISABLE")
        return 0

    st = load_state()
    if st.get("disabled"):
        print("disabled via state.disabled")
        return 0

    if not args.dry_run and not args.apply and not args.mark_only:
        print("指定してください: --dry-run / --apply / --mark-only", file=sys.stderr)
        return 2

    token = slack_token()
    if not token:
        print(
            "❌ SLACK_BOT_TOKEN（または USER/TOKEN）がありません。"
            "スレ読取・Ack には Bot が必要です。",
            file=sys.stderr,
        )
        return 3

    cfg = load_config()
    chans = cfg.get("channels") or {}
    want = [c.strip() for c in args.channels.split(",") if c.strip()]
    oldest = (datetime.now(timezone.utc) - timedelta(hours=args.lookback_hours)).timestamp()

    processed = dict(st.get("processed") or {})
    found: list[dict[str, Any]] = []
    acked = 0
    marked = 0

    for name in want:
        if name not in TARGET_CHANNELS and name not in ("report", "consult"):
            # 明示指定は許可するが既定外は警告
            print(f"# warn: #{name} は FB 対象外の可能性（続行）", file=sys.stderr)
        meta = chans.get(name) or {}
        cid = str(meta.get("id") or "").strip()
        if not cid:
            print(f"# skip #{name}: channel id なし", file=sys.stderr)
            continue
        try:
            parents = history(cid, token=token, limit=args.limit, oldest=oldest)
        except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as e:
            print(f"# #{name} history 失敗: {e}", file=sys.stderr)
            continue

        for parent in parents:
            # スレ内の返信メッセージ自体を親扱いしない
            pts = str(parent.get("ts") or "")
            if not pts:
                continue
            if parent.get("thread_ts") and str(parent.get("thread_ts")) != pts:
                continue
            try:
                reps = replies(cid, pts, token=token)
            except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as e:
                print(f"# #{name} replies {pts} 失敗: {e}", file=sys.stderr)
                continue
            for rep in reps:
                rts = str(rep.get("ts") or "")
                if not rts:
                    continue
                key = processed_key(name, rts)
                if key in processed:
                    continue
                if is_ack_or_bot_reply(rep):
                    processed[key] = {
                        "at": now_iso(),
                        "kind": "skip_bot",
                        "channel": name,
                        "thread_ts": pts,
                    }
                    marked += 1
                    continue
                if has_handled_reaction(rep):
                    processed[key] = {
                        "at": now_iso(),
                        "kind": "skip_reacted",
                        "channel": name,
                        "thread_ts": pts,
                    }
                    marked += 1
                    continue
                text = str(rep.get("text") or "")
                kind = classify_fb_reply(text)
                item = {
                    "channel": name,
                    "channel_id": cid,
                    "thread_ts": pts,
                    "reply_ts": rts,
                    "kind": kind,
                    "text": text,
                }
                found.append(item)
                print(
                    f"📎 FB #{name} thread={pts} reply={rts} "
                    f"kind={kind_label_ja(kind)} — {text.replace(chr(10), ' ')[:100]}"
                )

                if args.mark_only:
                    processed[key] = {
                        "at": now_iso(),
                        "kind": kind,
                        "channel": name,
                        "thread_ts": pts,
                        "mark_only": True,
                    }
                    marked += 1
                    continue

                ack = build_ack_text(kind, reply_preview=text)
                try:
                    ats = post_thread_ack(
                        cid,
                        pts,
                        ack,
                        token=token,
                        dry_run=args.dry_run or not args.apply,
                    )
                except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as e:
                    print(f"❌ Ack 失敗 #{name} {pts}: {e}", file=sys.stderr)
                    continue
                if args.apply and not args.dry_run:
                    # 元コメントに👀＝「見た／受けた」（返信だけでは見落とす対策）
                    add_reaction(
                        cid,
                        rts,
                        REACTION_SEEN,
                        token=token,
                        dry_run=False,
                    )
                    processed[key] = {
                        "at": now_iso(),
                        "kind": kind,
                        "channel": name,
                        "thread_ts": pts,
                        "reply_ts": rts,
                        "ack_ts": ats,
                        "seen_reaction": REACTION_SEEN,
                    }
                    acked += 1
                elif args.dry_run:
                    print(f"# dry-run ack kind={kind_label_ja(kind)}")
                    add_reaction(
                        cid,
                        rts,
                        REACTION_SEEN,
                        token=token,
                        dry_run=True,
                    )

    # processed 肥大防止（直近500。未対応は残す）
    processed = prune_processed(processed)

    st["processed"] = processed
    st["last_run_at"] = now_iso()
    st["last_found"] = len(found)
    if args.apply or args.mark_only:
        save_state(st)
    elif args.dry_run and found:
        # dry-run でも state は書かない（再実行で同じ候補を見せる）
        pass

    print(
        f"# fb_poll found={len(found)} acked={acked} marked={marked} "
        f"mode={'apply' if args.apply and not args.dry_run else ('mark' if args.mark_only else 'dry-run')}"
    )
    if found:
        print("次: 毎日の FB 対応（slack-fb-daily）が直して --done で「対応したよ」を返す。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
