#!/usr/bin/env python3
"""カード引落ウォッチ（Olive Infinite 本線）。

財務お知らせ（Gmail: statement@vpass.ne.jp の「お支払い金額のお知らせ」）を取り込み、
金額・引落日・SMBC不足を state / sync_meta に載せる。自動振込なし。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_card_debit_watch.py
  ~/selenium_env/venv/bin/python scripts/jarvis_card_debit_watch.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_card_debit_watch.py \\
    --set olive_infinite --amount 1200000 --due 2026-08-26
  ~/selenium_env/venv/bin/python scripts/jarvis_card_debit_watch.py \\
    --dismiss-due 2026-08-26
  ~/selenium_env/venv/bin/python scripts/jarvis_card_debit_watch.py --fetch-vpass
  ~/selenium_env/venv/bin/python scripts/jarvis_card_debit_watch.py --fetch-vpass-if-pending

金額把握ライン（優先・確定）:
  1) Gmail「お支払い金額のお知らせ」に金額あり（Vpassでメール金額表示ON時）
  2) Vpass Web 取得（--fetch-vpass / 日次 --fetch-vpass-if-pending）← 本線
  3) 手動 --set
  ※既定メールは金額非表示。「お支払い日のご案内」は due 補強のみ。

閾値（env・任意）:
  CARD_DEBIT_OLIVE_WARN_YEN=500000
  CARD_DEBIT_OTHER_WARN_YEN=300000
  CARD_DEBIT_DEFAULT_DUE_DAY=26
  CARD_DEBIT_LEAD_DAYS=14

ライフサイクル（state / sync_meta）:
  settled_due … money_ops done または --dismiss-due（当該 due のアラート消）
  plan_ready_due … consulting/approved/executing（warn→attention）
  dashboard_ack_due … ダッシュボード「確認」（ホームピンのみ消）
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_PATH = REPO / ".jarvis_state" / "card_debit_watch.json"
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
SMBC_ACCOUNT_ID = "smbc_kariya"

sys.path.insert(0, str(MANUAL))
sys.path.insert(0, str(REPO / "scripts"))

# カード製品 → id（本文マッチ）
CARD_PATTERNS: list[tuple[str, str, str, bool]] = [
    # id, label, regex, is_primary (Infinite)
    (
        "olive_infinite",
        "Olive Infinite（クレジット）",
        r"Ｏｌｉｖｅ\s*ＩＮＦ|Olive\s*INF|オリーブ.?INF",
        True,
    ),
    (
        "amazon_master",
        "Amazonマスター",
        r"Ａｍａｚｏｎマスター|Amazon.?マスター|Amazon.?Master",
        False,
    ),
    (
        "smcc_pp",
        "プラチナプリファード",
        r"プラチナプリファード",
        False,
    ),
    (
        "amex",
        "American Express",
        r"アメリカン.?エキスプレス|American\s*Express|ＡＭＥＸ|AMEX",
        False,
    ),
    (
        "paypay_card",
        "PayPayカード",
        r"PayPayカード|ＰａｙＰａｙカード",
        False,
    ),
]


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def today_jst() -> date:
    return datetime.now(JST).date()


def env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw.replace(",", ""))
    except ValueError:
        return default


def load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {
            "updated_at": None,
            "disabled": False,
            "gmail_account": "m19m",
            "cards": {},
            "alerts": [],
        }
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"disabled": False, "cards": {}, "alerts": []}


def save_state(data: dict[str, Any]) -> None:
    data["updated_at"] = now_iso()
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def gmail_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from gmail_api_scopes import GMAIL_SCOPES_215 as SCOPES

    for name in ("token_m19m.json", "token_livingsupport.json", "token.json"):
        path = MANUAL / name
        if path.is_file():
            break
    else:
        raise FileNotFoundError("Gmail token が見つかりません（token_m19m.json）")

    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False), path.name


def message_body_text(msg: dict[str, Any]) -> str:
    payload = msg.get("payload") or {}
    parts = [payload]
    chunks: list[str] = []
    while parts:
        p = parts.pop()
        if p.get("parts"):
            parts.extend(p["parts"])
            continue
        data = (p.get("body") or {}).get("data")
        if not data:
            continue
        raw = base64.urlsafe_b64decode(data.encode()).decode("utf-8", errors="replace")
        mime = p.get("mimeType") or ""
        if mime.startswith("text/html"):
            raw = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw)
            raw = re.sub(r"(?is)<style.*?>.*?</style>", " ", raw)
            raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
            raw = re.sub(r"</p>", "\n", raw, flags=re.I)
            raw = re.sub(r"<[^>]+>", " ", raw)
            raw = (
                raw.replace("&nbsp;", " ")
                .replace("&amp;", "&")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
            )
        chunks.append(raw)
    return "\n".join(chunks)


def headers_map(msg: dict[str, Any]) -> dict[str, str]:
    return {
        h["name"]: h["value"]
        for h in (msg.get("payload") or {}).get("headers") or []
        if "name" in h and "value" in h
    }


def match_card(text: str) -> tuple[str, str, bool] | None:
    for cid, label, pat, primary in CARD_PATTERNS:
        if re.search(pat, text, re.I):
            return cid, label, primary
    return None


def parse_yen_amounts(text: str) -> list[int]:
    # HTML 残骸を軽く正規化
    t = (
        text.replace("\xa0", " ")
        .replace("&nbsp;", " ")
        .replace("，", ",")
    )
    out: list[int] = []
    for m in re.finditer(
        r"(?:お支払い(?:合計|金額)|お支払金額|ご請求金額|請求金額|合計)\s*[:：]?\s*"
        r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)\s*円",
        t,
    ):
        out.append(int(m.group(1).replace(",", "")))
    # メール表示設定ON時の別表記
    for m in re.finditer(
        r"([0-9]{1,3}(?:,[0-9]{3})+)\s*円\s*(?:（税込）)?\s*(?:が|を)?\s*お支払い",
        t,
    ):
        out.append(int(m.group(1).replace(",", "")))
    return out


def parse_due_from_text(text: str, notice_date: date) -> date | None:
    t = text.replace("\xa0", " ").replace("&nbsp;", " ")
    # 明示: 引落日 2026年8月26日 / お支払い日 8月26日（金）
    m = re.search(
        r"(?:引落|振替|お支払(?:い)?日)[^\d]{0,20}"
        r"(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日",
        t,
    )
    if m:
        y = int(m.group(1)) if m.group(1) else notice_date.year
        mo, d = int(m.group(2)), int(m.group(3))
        try:
            due = date(y, mo, d)
            if not m.group(1) and due < notice_date - timedelta(days=7):
                due = date(y + 1, mo, d)
            return due
        except ValueError:
            pass
    return None


def default_due(notice_date: date) -> date:
    day = env_int("CARD_DEBIT_DEFAULT_DUE_DAY", 26)
    day = max(1, min(28, day))
    if notice_date.day <= day:
        return date(notice_date.year, notice_date.month, day)
    # 翌月
    if notice_date.month == 12:
        return date(notice_date.year + 1, 1, day)
    return date(notice_date.year, notice_date.month + 1, day)


def fetch_smbc_balance() -> int | None:
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        return None
    try:
        from supabase import create_client

        sb = create_client(url, key)
        rows = (
            sb.table("liquidity_snapshots")
            .select("account_id, balance_jpy, as_of")
            .eq("account_id", SMBC_ACCOUNT_ID)
            .order("as_of", desc=True)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not rows:
            return None
        return int(float(rows[0]["balance_jpy"]))
    except Exception as e:
        print(f"# smbc balance skip: {e}", file=sys.stderr)
        return None


def _ymd(s: Any) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _sb():
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        return None
    from supabase import create_client

    return create_client(url, key)


def push_sync_meta(summary: dict[str, Any], lifecycle: dict[str, Any] | None = None) -> None:
    sb = _sb()
    if not sb:
        return
    try:
        sb.table("sync_meta").upsert(
            {
                "key": "card_debit_watch_summary",
                "value": json.dumps(summary, ensure_ascii=False),
                "updated_at": now_iso(),
            },
            on_conflict="key",
        ).execute()
        if lifecycle is not None:
            sb.table("sync_meta").upsert(
                {
                    "key": "card_debit_lifecycle",
                    "value": json.dumps(lifecycle, ensure_ascii=False),
                    "updated_at": now_iso(),
                },
                on_conflict="key",
            ).execute()
    except Exception as e:
        print(f"# sync_meta skip: {e}", file=sys.stderr)


def _due_str(v: Any) -> str | None:
    d = _ymd(v)
    return d.isoformat() if d else None


def merge_lifecycle_from_remote(state: dict[str, Any]) -> dict[str, Any]:
    """money_ops / sync_meta から settled・plan_ready を合流。"""
    settled = _due_str(state.get("settled_due"))
    plan_ready = _due_str(state.get("plan_ready_due"))
    ack = _due_str(state.get("dashboard_ack_due"))

    sb = _sb()
    if sb:
        try:
            rows = (
                sb.table("sync_meta")
                .select("value")
                .eq("key", "card_debit_lifecycle")
                .limit(1)
                .execute()
                .data
                or []
            )
            if rows:
                raw = rows[0].get("value")
                lc = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(lc, dict):
                    settled = _due_str(lc.get("settled_due")) or settled
                    plan_ready = _due_str(lc.get("plan_ready_due")) or plan_ready
                    ack = _due_str(lc.get("dashboard_ack_due")) or ack
        except Exception as e:
            print(f"# lifecycle sync_meta skip: {e}", file=sys.stderr)

        try:
            rows = (
                sb.table("kurashift_money_ops")
                .select("id, status, assist_payload, updated_at")
                .eq("kind", "card_settlement_buffer")
                .in_("status", ["consulting", "approved", "executing", "done"])
                .order("updated_at", desc=True)
                .limit(20)
                .execute()
                .data
                or []
            )
            for op in rows:
                ap = (
                    op.get("assist_payload")
                    if isinstance(op.get("assist_payload"), dict)
                    else {}
                )
                due = _due_str(ap.get("due_date"))
                if not due:
                    continue
                st = str(op.get("status") or "")
                if st == "done" and not settled:
                    settled = due
                elif (
                    st in ("consulting", "approved", "executing")
                    and not plan_ready
                ):
                    plan_ready = due
                if settled and plan_ready:
                    break
        except Exception as e:
            print(f"# lifecycle money_ops skip: {e}", file=sys.stderr)

    if settled:
        state["settled_due"] = settled
    if plan_ready:
        state["plan_ready_due"] = plan_ready
    if ack:
        state["dashboard_ack_due"] = ack
    return state


def lifecycle_payload(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "settled_due": state.get("settled_due"),
        "plan_ready_due": state.get("plan_ready_due"),
        "dashboard_ack_due": state.get("dashboard_ack_due"),
        "updated_at": state.get("updated_at") or now_iso(),
    }


def shortfall(need: int | None, smbc: int | None, reserve: int = 0) -> int | None:
    if need is None or smbc is None:
        return None
    usable = max(0, smbc - reserve)
    return need - usable


def build_alerts(
    cards: dict[str, Any],
    smbc: int | None,
    *,
    settled_due: str | None = None,
    plan_ready_due: str | None = None,
) -> list[dict[str, Any]]:
    olive_warn = env_int("CARD_DEBIT_OLIVE_WARN_YEN", 500_000)
    other_warn = env_int("CARD_DEBIT_OTHER_WARN_YEN", 300_000)
    lead = env_int("CARD_DEBIT_LEAD_DAYS", 14)
    today = today_jst()
    settled = _due_str(settled_due)
    plan_ready = _due_str(plan_ready_due)
    alerts: list[dict[str, Any]] = []

    for cid, c in cards.items():
        if not isinstance(c, dict):
            continue
        if c.get("dismissed"):
            continue
        amount = c.get("amount_jpy")
        due_s = _due_str(c.get("due_date"))
        due = _ymd(due_s)
        # 引落日経過、または settled 済み → アラートなし
        if due is not None and due < today:
            c["smbc_shortfall"] = shortfall(
                int(amount) if isinstance(amount, int) else None,
                smbc,
                int(c.get("reserve_jpy") or 0),
            )
            continue
        if due_s and settled and due_s == settled:
            c["smbc_shortfall"] = shortfall(
                int(amount) if isinstance(amount, int) else None,
                smbc,
                int(c.get("reserve_jpy") or 0),
            )
            continue
        days = (due - today).days if due else None
        sf = shortfall(
            int(amount) if isinstance(amount, int) else None,
            smbc,
            int(c.get("reserve_jpy") or 0),
        )
        c["smbc_shortfall"] = sf
        primary = bool(c.get("primary"))
        level = None
        reason = None

        if primary:
            if isinstance(amount, int) and amount >= olive_warn:
                level = "warn"
                reason = f"請求額 {amount:,}円（≥{olive_warn:,}）"
            elif (
                days is not None
                and 0 <= days <= lead
                and sf is not None
                and sf > 0
            ):
                level = "warn"
                reason = f"引落まで{days}日・SMBC不足 {sf:,}円"
            elif amount is None and c.get("notice_at"):
                if days is not None and 0 <= days <= lead:
                    level = "warn"
                    reason = "お支払い金額のお知らせあり（金額未確定・Vpassで確認）"
                else:
                    level = "attention"
                    reason = "お支払い金額のお知らせあり（金額未確定）"
            elif days is not None and 0 <= days <= lead:
                level = "attention"
                reason = f"引落まで{days}日"
        else:
            if isinstance(amount, int) and amount >= other_warn:
                level = "warn" if amount >= olive_warn else "attention"
                reason = f"請求額 {amount:,}円（≥{other_warn:,}）"

        if level and due_s and plan_ready and due_s == plan_ready and level == "warn":
            level = "attention"
            reason = f"寄せ計画作成済み・実行待ち — {reason}"

        if level:
            alerts.append(
                {
                    "card_id": cid,
                    "label": c.get("label") or cid,
                    "level": level,
                    "reason": reason,
                    "amount_jpy": amount,
                    "due_date": due_s,
                    "smbc_shortfall": sf,
                    "href": (
                        f"/money-ops?due={due_s or ''}"
                        f"&need={amount or ''}"
                        f"&card={cid}"
                    ),
                }
            )
    rank = {"warn": 0, "attention": 1, "info": 2}
    alerts.sort(key=lambda a: (rank.get(a["level"], 9), a.get("card_id") or ""))
    return alerts


def scan_gmail(svc, newer_days: int = 60) -> list[dict[str, Any]]:
    queries = [
        # 金額が入るのはメール表示設定ON時のみ。OFFでもカード特定・通知日は取れる
        f'from:statement@vpass.ne.jp subject:お支払い金額のお知らせ newer_than:{newer_days}d',
        # 引落日の再通知（金額は通常なし。due 補強用）
        f'subject:お支払い日のご案内 newer_than:{newer_days}d',
        # AMEX 請求系
        (
            f'(from:americanexpress.com OR from:welcome.americanexpress.com) '
            f'(お支払い OR ご請求 OR statement OR Statement) newer_than:{newer_days}d'
        ),
    ]
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for query in queries:
        r = (
            svc.users()
            .messages()
            .list(userId="me", q=query, maxResults=25)
            .execute()
        )
        for m in r.get("messages") or []:
            mid = m["id"]
            if mid in seen:
                continue
            seen.add(mid)
            full = (
                svc.users()
                .messages()
                .get(userId="me", id=mid, format="full")
                .execute()
            )
            hdrs = headers_map(full)
            subj = hdrs.get("Subject") or ""
            if "ご利用のお知らせ" in subj or "すぐチャン" in subj:
                continue
            text = message_body_text(full)
            card = match_card(text + "\n" + subj)
            is_due_notice = "お支払い日のご案内" in subj
            is_pay_notice = "お支払い金額のお知らせ" in subj
            if not card and is_pay_notice:
                continue
            if not card and is_due_notice:
                # カード名が無い案内は Infinite 本線の due 補強として採用
                cid, label, primary = (
                    "olive_infinite",
                    "Olive Infinite（クレジット）",
                    True,
                )
            elif not card:
                continue
            else:
                cid, label, primary = card
            notice_date = today_jst()
            try:
                if hdrs.get("Date"):
                    notice_date = parsedate_to_datetime(hdrs["Date"]).astimezone(JST).date()
            except Exception:
                pass
            amounts = parse_yen_amounts(text)
            amount = max(amounts) if amounts else None
            if not primary and amount is None and not is_pay_notice:
                continue
            if not primary and amount is None:
                continue
            due = parse_due_from_text(text, notice_date) or default_due(notice_date)
            found.append(
                {
                    "card_id": cid,
                    "label": label,
                    "primary": primary,
                    "amount_jpy": amount,
                    "due_date": due.isoformat(),
                    "notice_date": notice_date.isoformat(),
                    "source_message_id": mid,
                    "subject": subj,
                    "amount_pending": amount is None,
                    "mail_kind": (
                        "due_guide"
                        if is_due_notice
                        else "payment_notice"
                        if is_pay_notice
                        else "other"
                    ),
                }
            )
    return found


def merge_vpass_fetch(state: dict[str, Any], fetched: dict[str, Any]) -> dict[str, Any]:
    """Vpass Web 取得結果を olive_infinite に反映（手動上書きは尊重）。"""
    if not fetched.get("ok"):
        state["last_vpass_fetch_error"] = fetched.get("error")
        state["last_vpass_fetch_at"] = fetched.get("fetched_at") or now_iso()
        return state
    cards = dict(state.get("cards") or {})
    row = dict(cards.get("olive_infinite") or {})
    row["id"] = "olive_infinite"
    row["label"] = row.get("label") or "Olive Infinite（クレジット）"
    row["primary"] = True
    if not row.get("amount_jpy_manual") and isinstance(fetched.get("amount_jpy"), int):
        row["amount_jpy"] = fetched["amount_jpy"]
        row["amount_pending"] = False
        row["amount_source"] = "vpass_web"
    if not row.get("due_date_manual") and fetched.get("due_date"):
        row["due_date"] = fetched["due_date"]
        row["due_source"] = "vpass_web"
    row["vpass_fetched_at"] = fetched.get("fetched_at") or now_iso()
    row["updated_at"] = now_iso()
    row["source"] = "vpass_web"
    cards["olive_infinite"] = row
    state["cards"] = cards
    state["last_vpass_fetch_at"] = row["vpass_fetched_at"]
    state.pop("last_vpass_fetch_error", None)
    return state


def fetch_vpass_payment() -> dict[str, Any]:
    try:
        from jarvis_vpass_payment_fetch import fetch_olive_payment

        return fetch_olive_payment()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def merge_scan(state: dict[str, Any], scanned: list[dict[str, Any]]) -> dict[str, Any]:
    cards = dict(state.get("cards") or {})
    # 新しい通知だけを採用（古いメールで上書きしない）
    best: dict[str, dict[str, Any]] = {}
    for hit in scanned:
        cid = hit["card_id"]
        nd = _ymd(hit.get("notice_date"))
        prev_hit = best.get(cid)
        if prev_hit is None:
            best[cid] = hit
            continue
        pd = _ymd(prev_hit.get("notice_date"))
        if nd and (pd is None or nd > pd):
            best[cid] = hit

    for cid, hit in best.items():
        prev = cards.get(cid) if isinstance(cards.get(cid), dict) else {}
        prev_notice = _ymd(prev.get("notice_date"))
        hit_notice = _ymd(hit.get("notice_date"))
        if prev_notice and hit_notice and hit_notice < prev_notice:
            continue  # state の方が新しい

        # 手動上書きを優先
        amount = prev.get("amount_jpy_manual")
        if amount is None:
            amount = hit.get("amount_jpy")
            if amount is None:
                amount = prev.get("amount_jpy")
        due = prev.get("due_date_manual") or hit.get("due_date") or prev.get("due_date")
        row = {
            **prev,
            "id": cid,
            "label": hit.get("label") or prev.get("label") or cid,
            "primary": bool(hit.get("primary") or prev.get("primary")),
            "amount_jpy": amount,
            "due_date": due,
            "notice_date": hit.get("notice_date") or prev.get("notice_date"),
            "notice_at": now_iso(),
            "source_message_id": hit.get("source_message_id"),
            "subject": hit.get("subject"),
            "amount_pending": amount is None,
            "source": "gmail_payment_notice",
        }
        # 手動 due が無いときだけ、新しい通知の推定 due で更新
        if not prev.get("due_date_manual"):
            row["due_date"] = hit.get("due_date") or due
        cards[cid] = row
    state["cards"] = cards
    return state


def apply_manual(
    state: dict[str, Any],
    card_id: str,
    amount: int | None,
    due: str | None,
) -> dict[str, Any]:
    cards = dict(state.get("cards") or {})
    row = dict(cards.get(card_id) or {})
    row["id"] = card_id
    if not row.get("label"):
        for cid, label, _pat, primary in CARD_PATTERNS:
            if cid == card_id:
                row["label"] = label
                row["primary"] = primary
                break
        else:
            row["label"] = card_id
            row["primary"] = card_id == "olive_infinite"
    if amount is not None:
        row["amount_jpy"] = amount
        row["amount_jpy_manual"] = amount
        row["amount_pending"] = False
    if due:
        row["due_date"] = due
        row["due_date_manual"] = due
    row["updated_at"] = now_iso()
    row["source"] = row.get("source") or "manual"
    cards[card_id] = row
    state["cards"] = cards
    return state


def summary_for_meta(state: dict[str, Any], smbc: int | None) -> dict[str, Any]:
    alerts = state.get("alerts") or []
    olive = (state.get("cards") or {}).get("olive_infinite") or {}
    top = alerts[0] if alerts else None
    return {
        "updated_at": state.get("updated_at"),
        "smbc_balance_jpy": smbc,
        "settled_due": state.get("settled_due"),
        "plan_ready_due": state.get("plan_ready_due"),
        "dashboard_ack_due": state.get("dashboard_ack_due"),
        "olive_infinite": {
            "amount_jpy": olive.get("amount_jpy"),
            "due_date": olive.get("due_date"),
            "amount_pending": olive.get("amount_pending"),
            "smbc_shortfall": olive.get("smbc_shortfall"),
            "notice_date": olive.get("notice_date"),
        },
        "alerts": alerts,
        "top_alert": top,
        "money_ops_href": (top or {}).get("href")
        or "/money-ops?card=olive_infinite",
    }


def print_block(state: dict[str, Any], smbc: int | None) -> None:
    print("📎 カード引落ウォッチ")
    print(f"- SMBC刈谷: {smbc:,}円" if smbc is not None else "- SMBC刈谷: —")
    cards = state.get("cards") or {}
    for cid in ("olive_infinite", "amazon_master", "smcc_pp", "paypay_card", "amex"):
        c = cards.get(cid)
        if not isinstance(c, dict):
            continue
        amt = c.get("amount_jpy")
        amt_s = f"{amt:,}円" if isinstance(amt, int) else "未確定"
        print(
            f"- {c.get('label') or cid}: {amt_s} / 引落 {c.get('due_date') or '—'} "
            f"/ 不足 {c.get('smbc_shortfall') if c.get('smbc_shortfall') is not None else '—'}"
        )
    alerts = state.get("alerts") or []
    if not alerts:
        print("- アラート: なし")
    else:
        for a in alerts:
            print(f"- [{a.get('level')}] {a.get('label')}: {a.get('reason')}")
            print(f"  → {a.get('href')}")


def main() -> int:
    ap = argparse.ArgumentParser(description="カード引落ウォッチ")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-gmail", action="store_true", help="Gmail を読まず state だけ再計算")
    ap.add_argument("--set", dest="set_card", help="手動更新するカード id")
    ap.add_argument("--amount", type=int, help="手動の請求額（円）")
    ap.add_argument("--due", help="手動の引落日 YYYY-MM-DD")
    ap.add_argument(
        "--dismiss-due",
        help="当該引落日を settled としてアラート解除（YYYY-MM-DD）",
    )
    ap.add_argument(
        "--fetch-vpass",
        action="store_true",
        help="Vpass Web から Olive INF の支払額・引落日を取得（金額把握本線）",
    )
    ap.add_argument(
        "--fetch-vpass-if-pending",
        action="store_true",
        help="olive_infinite が amount_pending のときだけ Vpass 取得",
    )
    ap.add_argument("--newer-days", type=int, default=60)
    args = ap.parse_args()

    state = load_state()
    if state.get("disabled"):
        print("📎 カード引落ウォッチ: disabled")
        return 0

    if args.dismiss_due:
        due = _due_str(args.dismiss_due)
        if not due:
            print("# --dismiss-due は YYYY-MM-DD", file=sys.stderr)
            return 2
        state["settled_due"] = due
        print(f"# settled_due={due}", file=sys.stderr)

    token_name = "—"
    skip_gmail = bool(args.no_gmail or args.set_card or args.dismiss_due)
    if not skip_gmail:
        try:
            svc, token_name = gmail_service()
            scanned = scan_gmail(svc, newer_days=args.newer_days)
            state = merge_scan(state, scanned)
            state["gmail_account"] = "m19m"
            state["gmail_token"] = token_name
            print(f"# gmail scanned={len(scanned)} token={token_name}", file=sys.stderr)
        except Exception as e:
            print(f"# gmail error: {e}", file=sys.stderr)
            state["last_gmail_error"] = str(e)

    if args.set_card:
        state = apply_manual(state, args.set_card, args.amount, args.due)

    olive = (state.get("cards") or {}).get("olive_infinite") or {}
    need_vpass = bool(args.fetch_vpass) or (
        args.fetch_vpass_if_pending
        and (
            olive.get("amount_pending")
            or olive.get("amount_jpy") is None
            or not olive.get("due_date")
        )
    )
    if need_vpass:
        print("# vpass fetch…", file=sys.stderr)
        fetched = fetch_vpass_payment()
        state = merge_vpass_fetch(state, fetched)
        if fetched.get("ok"):
            print(
                f"# vpass ok amount={fetched.get('amount_jpy')} due={fetched.get('due_date')}",
                file=sys.stderr,
            )
        else:
            print(f"# vpass fail: {fetched.get('error')}", file=sys.stderr)

    state = merge_lifecycle_from_remote(state)

    smbc = fetch_smbc_balance()
    state["smbc_balance_jpy"] = smbc
    state["smbc_account_id"] = SMBC_ACCOUNT_ID
    state["alerts"] = build_alerts(
        state.get("cards") or {},
        smbc,
        settled_due=state.get("settled_due"),
        plan_ready_due=state.get("plan_ready_due"),
    )
    state["thresholds"] = {
        "olive_warn_yen": env_int("CARD_DEBIT_OLIVE_WARN_YEN", 500_000),
        "other_warn_yen": env_int("CARD_DEBIT_OTHER_WARN_YEN", 300_000),
        "lead_days": env_int("CARD_DEBIT_LEAD_DAYS", 14),
        "default_due_day": env_int("CARD_DEBIT_DEFAULT_DUE_DAY", 26),
    }

    summary = summary_for_meta(state, smbc)
    print_block(state, smbc)
    if state.get("settled_due") or state.get("plan_ready_due"):
        print(
            f"- lifecycle: settled={state.get('settled_due') or '—'} "
            f"plan_ready={state.get('plan_ready_due') or '—'} "
            f"ack={state.get('dashboard_ack_due') or '—'}"
        )
    olive2 = (state.get("cards") or {}).get("olive_infinite") or {}
    if olive2.get("amount_pending") or olive2.get("amount_jpy") is None:
        print(
            "- 金額把握: 未確定 → Vpass Web（--fetch-vpass）か "
            "メール金額表示設定ON、または --set が必要"
        )

    if args.dry_run:
        print("# dry-run: state / sync_meta は書きません", file=sys.stderr)
        return 0

    save_state(state)
    push_sync_meta(summary, lifecycle_payload(state))
    print(f"# wrote {STATE_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
