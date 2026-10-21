#!/usr/bin/env python3
"""メール要対応 triage → Slack #consult（返信／見送り／Todoist）.

  Block Kit action_id → consult-action（業者返信・物件ゲートと同型）
  見送りが続く送信者は sync_meta mail_action_skip_mute で Slack 再掲除外。

  投稿形（2026-10-20〜）:
    - バッチ1回あたりスコア上位 N 件（既定5）
    - ダイジェスト1本（要旨一覧）＋ コンパクトカード（要旨＋ボタン、本文全文なし）
    - 要約は抽出（Plan A・LLMなし）。品質不足なら後続で Plan B（トップNのみLLM）
    - Slack に出した件は Gmail 既読（物件取込と同型。失敗時は morning catchup）
    - 各カードに digest_ts/channel を保存。見送り等で残 pending 更新／残0でダイジェスト削除

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_mail_action_slack_post.py --from-triage --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_mail_action_slack_post.py --from-triage
  ~/selenium_env/venv/bin/python scripts/jarvis_mail_action_slack_post.py --id gha-xxxx

正本: docs/Jarvis_メール要対応_Slack操作_20261019.md
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
MANUAL_DIR = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
MUTE_META_KEY = "mail_action_skip_mute"
DEFAULT_CONSULT_CHANNEL = "C0C7R0UF3MM"
DEFAULT_MUTE_THRESHOLD = 2
DEFAULT_LIMIT = 5

# アカウント → Gmail token（物件取込・triage catchup と同系）
TOKEN_BY_ACCOUNT = {
    "admin": "token_livingsupport.json",
    "mail_admin": "token_livingsupport.json",
    "estate": "token_estate.json",
    "mail_estate": "token_estate.json",
    "m19m": "token_m19m.json",
    "mail_m19m": "token_m19m.json",
}

# Slack 再掲前の軽いノイズ除外（見送り学習の前段・GenMail/night_triage と同趣旨）
NOISE_SUBJECT_RE = re.compile(
    r"(newsletter|キャンペーン|セール|配信停止|unsubscribe|"
    r"お知らせ\]|定期預金|ポイント付与|クーポン|広告|"
    r"プライバシーポリシー|利用規約.*(改訂|変更)|改訂のお知らせ)",
    re.I,
)

# 返信義務なしの定型（投稿対象から外す）
NO_REPLY_SUBJECT_RE = re.compile(
    r"(ご請求額のお知らせ|ご利用明細|ご利用金額|"
    r"認証コード|ワンタイム|OTP|確認コード|"
    r"お申し込み完了|申込受付|仮登録完了|本登録完了|"
    r"Meeting Notes:|AI Meeting Notes|"
    r"領収書のお知らせ|決済完了|お支払い完了|"
    r"カード追加完了|Apple Pay|パス・サイン|"
    r"メール送信$)",
    re.I,
)

# 販促・セミナー案内など（見送り学習前に再掲しない）
PROMO_SUBJECT_RE = re.compile(
    r"(Experiences|先行(先着)?販売|まだお席|開催\d+週間前|"
    r"エキスパ|vol\.\d|セミナー(ご案内|開催|招待)|"
    r"改定のお知らせ|交付書面|キャンペーン|"
    r"特別な体験|観戦チケット|HTMLメールの受信設定|"
    r"\d{4}年\d{1,2}月号|どう変わる|未来の自分に相談)",
    re.I,
)
PROMO_PARTNER_RE = re.compile(r"(エキスパ|newsletter|メルマガ)", re.I)

# 物件定例・紹介系（対応優先を下げる。完全除外はしない）
PROPERTY_DIGEST_RE = re.compile(
    r"(物件紹介|物件情報|新着物件|収益物件|投資用(不動産|物件)|"
    r"表面利回り|想定利回り|戸建て投資|一棟(アパート|マンション))",
    re.I,
)

# 返信／手配が要りそうなシグナル（OTP・ログイン促しだけでは加点しない）
ACTION_RE = re.compile(
    r"(ご確認|ご返信|お願い|至急|期限|締切|までに|"
    r"ご検討|ご指示|ご判断|署名|押印|見積|"
    r"要確認|折り返し|別途メール|ご連絡ください|"
    r"\?|？)",
)
TODO_ACTION_RE = re.compile(
    r"(電話|お電話|アップロード|提出|振込|送金|日程調整|予約)",
)
# 「手続き／ログイン」単体は定型メールに多いので弱シグナル扱い
WEAK_TODO_RE = re.compile(r"(ポータル|マイページ|手続|手続き|ログイン)")

OTP_LINE_RE = re.compile(
    r"(認証コード|ワンタイム|確認コード|OTP).{0,20}\d{4,8}",
    re.I,
)

PLACEHOLDER_SUMMARY_RE = re.compile(
    r"^(（本文\s*\d+\s*文字|本文\s*\d+\s*文字|（要約なし）)",
)

MA_ACTION_IDS = {
    "reply": "mail_action_reply",
    "skip": "mail_action_skip",
    "todoist": "mail_action_todoist",
}


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def _bot_token() -> str:
    return (os.environ.get("SLACK_BOT_TOKEN") or "").strip()


def _webhook_consult() -> str:
    return (
        (os.environ.get("SLACK_WEBHOOK_AI_TEAM_CONSULT") or "").strip()
        or (os.environ.get("SLACK_WEBHOOK_AI_TEAM_REPORT") or "").strip()
    )


def _consult_channel() -> str:
    return (
        (os.environ.get("SLACK_CONSULT_CHANNEL_ID") or "").strip()
        or DEFAULT_CONSULT_CHANNEL
    )


def _action_secret() -> str:
    return (
        (os.environ.get("MAIL_ACTION_TOKEN") or "").strip()
        or (os.environ.get("PROPERTY_GATE_ACTION_TOKEN") or "").strip()
    )


def _dashboard_base() -> str:
    return (
        (os.environ.get("JARVIS_DASHBOARD_URL") or "").strip().rstrip("/")
        or "https://jarvis-dashboard-amber.vercel.app"
    )


def ma_sig(triage_id: str, action: str) -> str:
    secret = _action_secret()
    if not secret:
        return "nosig"
    dig = hmac.new(
        secret.encode("utf-8"),
        f"ma:{triage_id}:{action}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return dig[:10]


def ma_url(triage_id: str, action: str) -> str:
    return f"{_dashboard_base()}/api/g/ma/{action}/{triage_id}?s={ma_sig(triage_id, action)}"


def mail_detail_url(triage_id: str) -> str:
    return f"{_dashboard_base()}/mail/{triage_id}"


def mute_key(from_email: str) -> str | None:
    e = (from_email or "").strip().lower()
    if not e or "@" not in e:
        return None
    return f"from:{e}"


def load_mute_registry(sb: Any) -> dict[str, Any]:
    th = int(
        os.environ.get("JARVIS_MAIL_ACTION_MUTE_THRESHOLD") or DEFAULT_MUTE_THRESHOLD
    )
    base = {"threshold": max(1, th), "entries": {}}
    try:
        r = (
            sb.table("sync_meta")
            .select("value")
            .eq("key", MUTE_META_KEY)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        if not rows:
            return base
        raw = rows[0].get("value")
        if isinstance(raw, str) and raw.strip():
            obj = json.loads(raw)
        elif isinstance(raw, dict):
            obj = raw
        else:
            return base
        entries = obj.get("entries") if isinstance(obj.get("entries"), dict) else {}
        t = int(obj.get("threshold") or th)
        return {"threshold": max(1, t), "entries": entries}
    except Exception as e:
        print(f"# mute registry load skip: {e}", file=sys.stderr)
        return base


def is_muted(reg: dict[str, Any], from_email: str) -> bool:
    key = mute_key(from_email)
    if not key:
        return False
    ent = (reg.get("entries") or {}).get(key) or {}
    return bool(ent.get("muted"))


def _button_elements(tid: str, *, url_mode: bool) -> list[dict[str, Any]]:
    if url_mode:
        return [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "返信する", "emoji": True},
                "style": "primary",
                "url": ma_url(tid, "reply"),
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "見送り", "emoji": True},
                "style": "danger",
                "url": ma_url(tid, "skip"),
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Todoist追加", "emoji": True},
                "url": ma_url(tid, "todoist"),
            },
        ]
    return [
        {
            "type": "button",
            "text": {"type": "plain_text", "text": "返信する", "emoji": True},
            "style": "primary",
            "action_id": MA_ACTION_IDS["reply"],
            "value": f"ma:reply:{tid}",
        },
        {
            "type": "button",
            "text": {"type": "plain_text", "text": "見送り", "emoji": True},
            "style": "danger",
            "action_id": MA_ACTION_IDS["skip"],
            "value": f"ma:skip:{tid}",
        },
        {
            "type": "button",
            "text": {"type": "plain_text", "text": "Todoist追加", "emoji": True},
            "action_id": MA_ACTION_IDS["todoist"],
            "value": f"ma:todoist:{tid}",
        },
    ]


def _clean_body_lines(body: str) -> list[str]:
    lines: list[str] = []
    for raw in (body or "").replace("\r", "\n").splitlines():
        s = raw.strip()
        if not s:
            continue
        if re.match(r"^(from|to|cc|sent|date|件名|差出人|宛先)\s*[:：]", s, re.I):
            continue
        if re.match(r"^[-_]{3,}$", s):
            continue
        if re.search(r"(配信停止|unsubscribe|このメールは)", s, re.I):
            continue
        if OTP_LINE_RE.search(s):
            # 秘密を Slack に載せない
            continue
        if len(s) < 4:
            continue
        # HTML 残骸の軽い除去
        s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
        s = re.sub(r"<[^>]+>", "", s)
        s = re.sub(r"\s+", " ", s).strip()
        if s:
            lines.append(s)
    return lines


def _sanitize_summary_text(text: str) -> str:
    s = (text or "").replace("\r", " ")
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_summary(row: dict[str, Any], *, max_len: int = 140) -> str:
    """Plan A: LLMなしの抽出要約。"""
    existing = _sanitize_summary_text(str(row.get("summary") or ""))
    if (
        existing
        and not PLACEHOLDER_SUMMARY_RE.search(existing)
        and not OTP_LINE_RE.search(existing)
        and existing not in ("本文", "summary")
    ):
        return existing[:max_len]

    subject = str(row.get("subject") or "").strip()
    body = str(row.get("original_body") or "").strip()
    lines = _clean_body_lines(body)

    picked: list[str] = []
    for ln in lines:
        if ACTION_RE.search(ln) or TODO_ACTION_RE.search(ln):
            picked.append(ln)
            if len(picked) >= 2:
                break
    if not picked:
        picked = lines[:2]

    blob = " / ".join(picked).strip()
    if not blob:
        blob = subject or "(要旨なし)"
    elif subject and subject not in blob and len(blob) < 80:
        blob = f"{subject} — {blob}"

    if len(blob) > max_len:
        blob = blob[: max_len - 1].rstrip() + "…"
    return blob


def _age_hours(received_at: str) -> float:
    s = (received_at or "").strip()
    if not s:
        return 999.0
    try:
        # support "2026-10-19T12:00:00+09:00" / "...Z" / naive
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)
        return max(0.0, (datetime.now(JST) - dt.astimezone(JST)).total_seconds() / 3600.0)
    except Exception:
        return 999.0


def score_row(row: dict[str, Any]) -> tuple[int, list[str]]:
    """対応優先度スコア（高いほど先に通知）。reasons は dry-run 用。"""
    score = 0
    reasons: list[str] = []
    pri = str(row.get("priority") or "").lower()
    kind = str(row.get("kind") or "").lower()
    lane = str(row.get("lane") or "").lower()
    subj = str(row.get("subject") or "")
    body = str(row.get("original_body") or "")
    blob = f"{subj}\n{body[:2000]}"
    draft = str(row.get("draft_text") or "").strip()

    if pri == "high":
        score += 50
        reasons.append("pri:high")
    elif pri in ("medium", "med"):
        score += 25
        reasons.append("pri:med")
    elif pri == "low":
        score += 5
        reasons.append("pri:low")

    if kind == "mail":
        score += 30
        reasons.append("kind:mail")
    elif kind == "skim":
        score -= 25
        reasons.append("kind:skim")

    if lane == "partner":
        score += 20
        reasons.append("lane:partner")
    elif lane == "general":
        score += 8
        reasons.append("lane:general")

    if draft:
        score += 20
        reasons.append("has_draft")

    if ACTION_RE.search(blob):
        score += 25
        reasons.append("action_signal")
    if TODO_ACTION_RE.search(blob):
        score += 15
        reasons.append("todo_signal")
    elif WEAK_TODO_RE.search(blob):
        score += 5
        reasons.append("weak_todo")

    if PROPERTY_DIGEST_RE.search(blob) and not draft:
        score -= 35
        reasons.append("property_digest")

    if NOISE_SUBJECT_RE.search(subj):
        score -= 40
        reasons.append("noise_subj")
    if NO_REPLY_SUBJECT_RE.search(subj):
        score -= 80
        reasons.append("no_reply_subj")

    age = _age_hours(str(row.get("received_at") or ""))
    if age <= 6:
        score += 12
        reasons.append("fresh<=6h")
    elif age <= 24:
        score += 6
        reasons.append("fresh<=24h")
    elif age >= 72:
        score -= 8
        reasons.append("stale>=72h")

    return score, reasons


def rank_candidates(rows: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in rows:
        sc, reasons = score_row(row)
        summary = extract_summary(row)
        item = dict(row)
        item["_score"] = sc
        item["_score_reasons"] = reasons
        item["_extract_summary"] = summary
        enriched.append(item)
    enriched.sort(
        key=lambda r: (
            -int(r.get("_score") or 0),
            str(r.get("received_at") or ""),
        ),
    )
    return enriched[: max(0, limit)]


def build_digest_payload(ranked: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(ranked)
    when = datetime.now(JST).strftime("%m/%d %H:%M")
    lines: list[str] = []
    for i, row in enumerate(ranked, 1):
        partner = str(row.get("partner") or "").strip() or "—"
        subject = str(row.get("subject") or "(件名なし)").strip()
        summary = str(row.get("_extract_summary") or "").strip()
        tid = str(row.get("id") or "")
        score = int(row.get("_score") or 0)
        detail = mail_detail_url(tid)
        lines.append(
            f"*{i}. [{partner}]* score={score}\n"
            f"件名: {subject[:100]}\n"
            f"要旨: {summary}\n"
            f"<{detail}|詳細を見る>"
        )
    body = "\n\n".join(lines) if lines else "(対象なし)"
    text = f"【メール要対応ダイジェスト】上位{n}件（{when}）"
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"メール要対応ダイジェスト — 上位{n}件",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{when}* · スコア順 · 要旨（抽出・AIなし）\n"
                    "気になったら下のカードで返信／見送り／Todoist、"
                    "または「詳細を見る」で本文確認。"
                ),
            },
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": body[:2900]},
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        "Plan A（抽出要約）· 件数既定5 · "
                        "残り pending は次バッチで再評価"
                    ),
                }
            ],
        },
    ]
    return {"text": text, "blocks": blocks, "username": "Jarvis メール要対応"}


def build_compact_payload(
    row: dict[str, Any],
    *,
    url_mode: bool,
    rank: int,
    total: int,
) -> dict[str, Any]:
    tid = str(row.get("id") or "")
    partner = str(row.get("partner") or "").strip() or "—"
    subject = str(row.get("subject") or "(件名なし)").strip()
    from_email = str(row.get("from_email") or "").strip()
    summary = str(row.get("_extract_summary") or extract_summary(row)).strip()
    draft = str(row.get("draft_text") or "").strip()
    lane = str(row.get("lane") or "")
    kind = str(row.get("kind") or "")
    account = str(row.get("account") or "admin")
    score = int(row.get("_score") or 0)
    draft_preview = draft[:400] if draft else "（下書きなし — 返信でモーダル編集）"
    mode_note = "アプリ内ボタン" if not url_mode else "URLボタン"
    detail = mail_detail_url(tid)
    text = (
        f"【メール要対応 {rank}/{total}】{partner}\n件名: {subject}\n"
        f"要旨: {summary}"
    )
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"メール要対応 {rank}/{total} — {partner[:36]}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*件名:* {subject[:120]}\n"
                    f"*From:* `{from_email}` · score=`{score}` · "
                    f"lane=`{lane}` kind=`{kind}` account=`{account}`"
                ),
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*要旨*\n{summary}\n<{detail}|本文の詳細（Dashboard）>",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*返信下書き*\n```{draft_preview}```",
            },
        },
        {
            "type": "actions",
            "block_id": f"ma_actions_{tid[:24]}",
            "elements": _button_elements(tid, url_mode=url_mode),
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"id=`{tid}` · {mode_note}\n"
                        f"予備URL: <{ma_url(tid, 'reply')}|返信> · "
                        f"<{ma_url(tid, 'skip')}|見送り> · "
                        f"<{ma_url(tid, 'todoist')}|Todoist>\n"
                        "Todoist＝メール返信以外の手配（電話・ポータル等）"
                    ),
                }
            ],
        },
    ]
    return {"text": text, "blocks": blocks, "username": "Jarvis メール要対応"}


def post_bot_message(
    payload: dict[str, Any], *, dry_run: bool
) -> tuple[int, str | None, str | None]:
    """Returns (rc, channel_id, message_ts). ts は見送り時の chat.delete 用。"""
    token = _bot_token()
    channel = _consult_channel()
    body = {
        "channel": channel,
        "text": payload.get("text") or "メール要対応",
        "blocks": payload.get("blocks") or [],
    }
    if dry_run:
        print("# dry-run chat.postMessage")
        print(json.dumps(body, ensure_ascii=False, indent=2)[:4000])
        return 0, channel, None
    if not token:
        return 3, None, None
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            j = json.loads(resp.read().decode("utf-8", errors="replace"))
            if not j.get("ok"):
                print(f"❌ chat.postMessage: {j.get('error')}", file=sys.stderr)
                return 1, None, None
            ts = str(j.get("ts") or "") or None
            ch = str(j.get("channel") or channel) or channel
            print(f"✅ Slack mail-action Bot OK channel={ch} ts={ts}")
            return 0, ch, ts
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"❌ Slack HTTP {e.code}: {err}", file=sys.stderr)
        return 1, None, None


def post_webhook(payload: dict[str, Any], *, dry_run: bool) -> tuple[int, str | None, str | None]:
    url = _webhook_consult()
    if dry_run:
        print("# dry-run Slack webhook payload")
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:4000])
        return 0, None, None
    if not url:
        print("❌ SLACK_WEBHOOK_AI_TEAM_CONSULT（or REPORT）未設定", file=sys.stderr)
        return 2, None, None
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            print(f"✅ Slack mail-action Webhook OK status={resp.status} body={body!r}")
            # Incoming Webhook は ts が取れない → 見送り削除はアプリ内ボタン本線
            return 0, None, None
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"❌ Slack HTTP {e.code}: {err}", file=sys.stderr)
        return 1, None, None


def post_slack(
    payload: dict[str, Any], *, dry_run: bool, force_webhook: bool
) -> tuple[int, str | None, str | None]:
    if not _action_secret():
        print("⚠️ PROPERTY_GATE_ACTION_TOKEN 未設定（予備 URL 署名なし）", file=sys.stderr)
    use_bot = bool(_bot_token()) and not force_webhook
    if use_bot:
        rc, ch, ts = post_bot_message(payload, dry_run=dry_run)
        if rc == 3:
            return post_webhook(payload, dry_run=dry_run)
        return rc, ch, ts
    return post_webhook(payload, dry_run=dry_run)


def _sb():
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    return create_client(url, key)


def fetch_one(tid: str) -> dict[str, Any] | None:
    sb = _sb()
    r = (
        sb.table("triage_items")
        .select(
            "id,status,subject,draft_text,original_body,from_email,partner,"
            "account,lane,kind,summary,payload,received_at,priority,"
            "gmail_message_id"
        )
        .eq("id", tid)
        .limit(1)
        .execute()
    )
    rows = r.data or []
    return rows[0] if rows else None


def _gmail_service(token_name: str) -> Any:
    """Mac / GHA（token 展開後）で Gmail modify 用 service を返す。"""
    sys.path.insert(0, str(MANUAL_DIR))
    from gmail_api_scopes import GMAIL_SCOPES_READ_MODIFY  # type: ignore
    from gmail_to_yoritoori import build_service_for_token  # type: ignore

    token_env = (os.environ.get("GMAIL_ADMIN_TOKEN_PATH") or "").strip()
    if token_env and token_name in (
        "token_livingsupport.json",
        "token_admin.json",
    ):
        token = Path(token_env)
    else:
        token = MANUAL_DIR / token_name
    if not token.is_file():
        raise FileNotFoundError(f"token missing: {token}")
    service, _ = build_service_for_token(
        token, scopes=list(GMAIL_SCOPES_READ_MODIFY), open_browser=False
    )
    if not service:
        raise RuntimeError(f"failed gmail service for {token_name}")
    return service


def mark_gmail_read_after_slack(
    sb: Any,
    rows: list[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> dict[str, int]:
    """Slack ダイジェスト／カードに出した件を Gmail 既読（物件取込と同型）。

    gmail_message_id がある行だけ。失敗しても Slack 投稿は成功のまま（soft-fail）。
    取りこぼしは morning の triage_gmail_read_catchup が埋める。
    """
    if os.environ.get("JARVIS_MAIL_ACTION_GMAIL_READ_DISABLE", "").strip() in {
        "1",
        "true",
        "yes",
    }:
        print("# gmail_read: disabled via JARVIS_MAIL_ACTION_GMAIL_READ_DISABLE")
        return {"ok": 0, "fail": 0, "skip": len(rows), "disabled": 1}

    ok = 0
    fail = 0
    skip = 0
    services: dict[str, Any] = {}

    for row in rows:
        tid = str(row.get("id") or "")
        gid = str(row.get("gmail_message_id") or "").strip()
        pl0 = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if pl0.get("gmail_read_at"):
            skip += 1
            continue
        if not gid:
            skip += 1
            continue
        account = (str(row.get("account") or "admin").strip().lower() or "admin")
        token_name = TOKEN_BY_ACCOUNT.get(account, "token_livingsupport.json")
        if dry_run:
            print(
                f"# dry-run gmail_read id={tid} gmail={gid} account={account}"
            )
            ok += 1
            continue
        try:
            if token_name not in services:
                services[token_name] = _gmail_service(token_name)
            services[token_name].users().messages().modify(
                userId="me",
                id=gid,
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()
            # payload を再読して slack_ma_* を潰さない
            r = (
                sb.table("triage_items")
                .select("payload")
                .eq("id", tid)
                .limit(1)
                .execute()
            )
            raw = (r.data or [{}])[0].get("payload")
            pl = dict(raw) if isinstance(raw, dict) else {}
            pl["gmail_read_at"] = datetime.now(timezone.utc).isoformat()
            pl["gmail_read_on"] = "slack_ma_digest"
            pl.pop("gmail_read_pending", None)
            pl.pop("gmail_read_error", None)
            sb.table("triage_items").update(
                {"payload": pl, "updated_at": now_iso()}
            ).eq("id", tid).execute()
            ok += 1
            print(f"📎 gmail_read: id={tid} gmail={gid} account={account}")
        except Exception as e:
            fail += 1
            print(
                f"# gmail_read soft-fail id={tid} gid={gid[:16]}: {e}",
                file=sys.stderr,
            )
            try:
                r = (
                    sb.table("triage_items")
                    .select("payload")
                    .eq("id", tid)
                    .limit(1)
                    .execute()
                )
                raw = (r.data or [{}])[0].get("payload")
                pl = dict(raw) if isinstance(raw, dict) else {}
                pl["gmail_read_pending"] = True
                pl["gmail_read_error"] = str(e)[:200]
                pl["gmail_read_on"] = "slack_ma_digest"
                sb.table("triage_items").update({"payload": pl}).eq(
                    "id", tid
                ).execute()
            except Exception:
                pass

    return {"ok": ok, "fail": fail, "skip": skip, "dry_run": int(dry_run)}


def load_pending_from_supabase(*, limit: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sb = _sb()
    mute = load_mute_registry(sb)
    pool = max(limit * 10, 60)
    r = (
        sb.table("triage_items")
        .select(
            "id,status,subject,draft_text,original_body,from_email,partner,"
            "account,lane,kind,summary,payload,received_at,priority,"
            "gmail_message_id"
        )
        .eq("status", "pending")
        .order("received_at", desc=True)
        .limit(pool)
        .execute()
    )
    from jarvis_kurashift_re_inquiry_channel import is_mail_action_excluded

    pool_rows: list[dict[str, Any]] = []
    muted_n = 0
    skipped_vendor = 0
    skipped_skim = 0
    skipped_posted = 0
    skipped_self = 0
    for row in r.data or []:
        tid = str(row.get("id") or "")
        if tid.startswith("re-vendor-"):
            skipped_vendor += 1
            continue
        pl = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if pl.get("re_vendor_reply"):
            skipped_vendor += 1
            continue
        # estate 送信・BCC 誤ラベルの自分発信は要対応に出さない
        if is_mail_action_excluded(
            from_email=str(row.get("from_email") or ""),
            body=str(row.get("original_body") or ""),
        ):
            skipped_self += 1
            continue
        kind = str(row.get("kind") or "").lower()
        lane = str(row.get("lane") or "").lower()
        pri = str(row.get("priority") or "").lower()
        subj = str(row.get("subject") or "")
        if NOISE_SUBJECT_RE.search(subj) and not (row.get("draft_text") or "").strip():
            skipped_skim += 1
            continue
        # OTP・請求通知・申込完了など返信不要定型は再掲しない
        if NO_REPLY_SUBJECT_RE.search(subj) and not (row.get("draft_text") or "").strip():
            skipped_skim += 1
            continue
        partner_name = str(row.get("partner") or "")
        if (
            (
                PROMO_SUBJECT_RE.search(subj)
                or PROMO_PARTNER_RE.search(partner_name)
            )
            and not (row.get("draft_text") or "").strip()
        ):
            skipped_skim += 1
            continue
        if kind == "skim" and pri != "high" and not (row.get("draft_text") or "").strip():
            skipped_skim += 1
            continue
        if lane == "openchat":
            continue
        if is_muted(mute, str(row.get("from_email") or "")):
            muted_n += 1
            continue
        if pl.get("slack_ma_posted_at") and not os.environ.get(
            "JARVIS_MAIL_ACTION_REPOST"
        ):
            skipped_posted += 1
            continue
        pool_rows.append(row)

    ranked = rank_candidates(pool_rows, limit=limit)
    stats = {
        "pool": len(pool_rows),
        "ranked": len(ranked),
        "muted": muted_n,
        "vendor_skip": skipped_vendor,
        "skim_skip": skipped_skim,
        "self_skip": skipped_self,
        "already_posted": skipped_posted,
        "mute_entries": len(mute.get("entries") or {}),
        "top_scores": [
            {
                "id": str(x.get("id")),
                "score": x.get("_score"),
                "reasons": x.get("_score_reasons"),
            }
            for x in ranked
        ],
    }
    return ranked, stats


def mark_posted(
    sb: Any,
    tid: str,
    *,
    score: int | None = None,
    summary: str = "",
    slack_channel: str | None = None,
    slack_ts: str | None = None,
    digest_channel: str | None = None,
    digest_ts: str | None = None,
) -> None:
    try:
        r = (
            sb.table("triage_items")
            .select("payload")
            .eq("id", tid)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        if not rows:
            return
        pl = rows[0].get("payload") if isinstance(rows[0].get("payload"), dict) else {}
        pl = dict(pl)
        pl["slack_ma_posted_at"] = now_iso()
        pl["slack_ma_digest"] = {
            "at": now_iso(),
            "score": score,
            "summary_plan": "A_extractive",
            "summary": (summary or "")[:200],
        }
        if slack_channel:
            pl["slack_ma_channel"] = slack_channel
        if slack_ts:
            pl["slack_ma_ts"] = slack_ts
        # 見送り等でダイジェストを更新／削除するためのバッチキー
        if digest_channel:
            pl["slack_ma_digest_channel"] = digest_channel
        if digest_ts:
            pl["slack_ma_digest_ts"] = digest_ts
        sb.table("triage_items").update(
            {"payload": pl, "updated_at": now_iso()}
        ).eq("id", tid).execute()
    except Exception as e:
        print(f"# mark posted skip {tid}: {e}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="メール要対応 → Slack #consult")
    ap.add_argument("--from-triage", action="store_true")
    ap.add_argument("--id", type=str, default="")
    ap.add_argument(
        "--limit",
        type=int,
        default=int(os.environ.get("JARVIS_MAIL_ACTION_LIMIT") or DEFAULT_LIMIT),
        help=f"バッチあたり最大件数（既定{DEFAULT_LIMIT}・スコア上位）",
    )
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--url-buttons", action="store_true")
    ap.add_argument("--webhook", action="store_true", help="Bot を使わず Webhook")
    ap.add_argument(
        "--no-digest",
        action="store_true",
        help="ダイジェストを出さずコンパクトカードのみ",
    )
    args = ap.parse_args()

    if os.environ.get("JARVIS_MAIL_ACTION_SLACK_DISABLE", "").strip() in {
        "1",
        "true",
        "yes",
    }:
        print("disabled via JARVIS_MAIL_ACTION_SLACK_DISABLE=1")
        return 0

    url_mode = bool(args.url_buttons)
    # 業者返信と同型: Bot / Signing が無いとアプリ内ボタンは無反応になる
    # （Webhook 投稿は ts が取れず見送り削除も不可 → URL ボタンへフォールバック）
    if not url_mode and (
        not _bot_token()
        or not (os.environ.get("SLACK_SIGNING_SECRET") or "").strip()
    ):
        print(
            "⚠️ SLACK_BOT_TOKEN / SLACK_SIGNING_SECRET なし "
            "→ URL ボタンにフォールバック（ブラウザで操作）",
            file=sys.stderr,
        )
        url_mode = True
    # URL ボタンは HMAC 必須。秘密が空だと s=nosig になり Vercel が「認証エラー」を返す
    if url_mode and not _action_secret():
        print(
            "ERROR: PROPERTY_GATE_ACTION_TOKEN（または MAIL_ACTION_TOKEN）が未設定です。"
            " URL ボタンを署名できないため投稿を中止します"
            "（GHA Secrets / .env.jarvis_private を確認）。",
            file=sys.stderr,
        )
        return 2
    rows: list[dict[str, Any]] = []
    stats: dict[str, Any] = {}
    if args.id:
        one = fetch_one(args.id.strip())
        if not one:
            print(f"not found: {args.id}", file=sys.stderr)
            return 2
        rows = rank_candidates([one], limit=1)
    elif args.from_triage:
        rows, stats = load_pending_from_supabase(limit=args.limit)
    else:
        ap.print_help()
        return 2

    print(
        f"📎 mail action slack — candidates={len(rows)} "
        f"limit={args.limit} score_rank=1 "
        f"mode={'url' if url_mode else 'interactive'} "
        f"via={'webhook' if args.webhook or not _bot_token() else 'bot'} "
        f"stats={json.dumps(stats, ensure_ascii=False)}"
    )
    if not rows:
        print("投稿対象なし（pending 要対応が無い／ミュート除外）")
        return 0

    for i, row in enumerate(rows, 1):
        print(
            f"# rank {i}: id={row.get('id')} score={row.get('_score')} "
            f"reasons={row.get('_score_reasons')} "
            f"summary={(row.get('_extract_summary') or '')[:80]}"
        )

    sb = None if args.dry_run else _sb()
    posted = 0
    digest_ch: str | None = None
    digest_ts: str | None = None

    if len(rows) >= 1 and not args.no_digest and (args.from_triage or len(rows) > 1):
        digest = build_digest_payload(rows)
        rc, digest_ch, digest_ts = post_slack(
            digest, dry_run=args.dry_run, force_webhook=args.webhook
        )
        if rc != 0:
            return rc

    total = len(rows)
    for i, row in enumerate(rows, 1):
        tid = str(row.get("id") or "")
        payload = build_compact_payload(
            row, url_mode=url_mode, rank=i, total=total
        )
        rc, ch, ts = post_slack(
            payload, dry_run=args.dry_run, force_webhook=args.webhook
        )
        if rc != 0:
            return rc
        posted += 1
        if sb and not args.dry_run:
            mark_posted(
                sb,
                tid,
                score=int(row.get("_score") or 0),
                summary=str(row.get("_extract_summary") or ""),
                slack_channel=ch,
                slack_ts=ts,
                digest_channel=digest_ch,
                digest_ts=digest_ts,
            )

    # Slack に出した＝目を通す動線に載せたので Gmail 既読（物件取込と同型）
    if args.dry_run:
        read_stats = mark_gmail_read_after_slack(None, rows, dry_run=True)
    elif sb is not None:
        read_stats = mark_gmail_read_after_slack(sb, rows, dry_run=False)
    else:
        read_stats = {"ok": 0, "fail": 0, "skip": 0}
    print(
        f"# posted_cards={posted} digest={'no' if args.no_digest else 'yes'} "
        f"gmail_read={json.dumps(read_stats, ensure_ascii=False)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
