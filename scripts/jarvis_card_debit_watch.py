#!/usr/bin/env python3
"""カード引落ウォッチ（Olive Infinite 本線）。

財務お知らせ（Gmail: statement@vpass.ne.jp の「お支払い金額のお知らせ」）を取り込み、
金額・引落日・SMBC不足を state / sync_meta に載せる。自動振込なし。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_card_debit_watch.py
  ~/selenium_env/venv/bin/python scripts/jarvis_card_debit_watch.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_card_debit_watch.py \\
    --set olive_infinite --amount 1200000 --due 2026-08-26

閾値（env・任意）:
  CARD_DEBIT_OLIVE_WARN_YEN=500000
  CARD_DEBIT_OTHER_WARN_YEN=300000
  CARD_DEBIT_DEFAULT_DUE_DAY=26
  CARD_DEBIT_LEAD_DAYS=14
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
    out: list[int] = []
    for m in re.finditer(
        r"(?:お支払い(?:合計|金額)|ご請求金額|請求金額|合計)\s*[:：]?\s*"
        r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)\s*円",
        text,
    ):
        out.append(int(m.group(1).replace(",", "")))
    return out


def parse_due_from_text(text: str, notice_date: date) -> date | None:
    # 明示: 引落日 2026年8月26日 / 8月26日
    m = re.search(
        r"(?:引落|振替|お支払(?:い)?日)[^\d]{0,12}"
        r"(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日",
        text,
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


def push_sync_meta(summary: dict[str, Any]) -> None:
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        return
    try:
        from supabase import create_client

        sb = create_client(url, key)
        sb.table("sync_meta").upsert(
            {
                "key": "card_debit_watch_summary",
                "value": json.dumps(summary, ensure_ascii=False),
                "updated_at": now_iso(),
            },
            on_conflict="key",
        ).execute()
    except Exception as e:
        print(f"# sync_meta skip: {e}", file=sys.stderr)


def shortfall(need: int | None, smbc: int | None, reserve: int = 0) -> int | None:
    if need is None or smbc is None:
        return None
    usable = max(0, smbc - reserve)
    return need - usable


def build_alerts(cards: dict[str, Any], smbc: int | None) -> list[dict[str, Any]]:
    olive_warn = env_int("CARD_DEBIT_OLIVE_WARN_YEN", 500_000)
    other_warn = env_int("CARD_DEBIT_OTHER_WARN_YEN", 300_000)
    lead = env_int("CARD_DEBIT_LEAD_DAYS", 14)
    today = today_jst()
    alerts: list[dict[str, Any]] = []

    for cid, c in cards.items():
        if not isinstance(c, dict):
            continue
        if c.get("dismissed"):
            continue
        amount = c.get("amount_jpy")
        due_s = c.get("due_date")
        due = None
        if due_s:
            try:
                due = date.fromisoformat(str(due_s)[:10])
            except ValueError:
                due = None
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
            # Infinite: 常に state 更新済み。アラート条件
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
                # 金額未確定でも通知あり → 要確認（T-14内なら warn）
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
            # 未満はアラートなし（記録のみ）

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
    # warn 優先
    rank = {"warn": 0, "attention": 1, "info": 2}
    alerts.sort(key=lambda a: (rank.get(a["level"], 9), a.get("card_id") or ""))
    return alerts


def scan_gmail(svc, newer_days: int = 60) -> list[dict[str, Any]]:
    q = (
        f'from:statement@vpass.ne.jp subject:お支払い金額のお知らせ '
        f"newer_than:{newer_days}d"
    )
    # AMEX 請求系も拾う（件数少なめ）
    q_amex = (
        f'(from:americanexpress.com OR from:welcome.americanexpress.com) '
        f'(お支払い OR ご請求 OR statement OR Statement) newer_than:{newer_days}d'
    )
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for query in (q, q_amex):
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
            if not card and "お支払い金額のお知らせ" in subj:
                # 製品名が取れない通知はスキップ
                continue
            if not card:
                continue
            cid, label, primary = card
            # 日付
            notice_date = today_jst()
            try:
                if hdrs.get("Date"):
                    notice_date = parsedate_to_datetime(hdrs["Date"]).astimezone(JST).date()
            except Exception:
                pass
            amounts = parse_yen_amounts(text)
            amount = max(amounts) if amounts else None
            # 副線は金額が取れる請求だけ（マーケティング・金額なし通知は捨てる）
            if not primary and amount is None and "お支払い金額のお知らせ" not in subj:
                continue
            if not primary and amount is None:
                # Vpass 金額なし通知は Amazon 等も来るが、閾値アラート不能なので記録のみ省略可
                # Infinite 以外は金額確定メールだけ残す
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
                }
            )
    return found


def _ymd(s: Any) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


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
    for cid in ("olive_infinite", "amazon_master", "amex", "smcc_pp"):
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
    ap.add_argument("--newer-days", type=int, default=60)
    args = ap.parse_args()

    state = load_state()
    if state.get("disabled"):
        print("📎 カード引落ウォッチ: disabled")
        return 0

    token_name = "—"
    if not args.no_gmail and not args.set_card:
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

    smbc = fetch_smbc_balance()
    state["smbc_balance_jpy"] = smbc
    state["smbc_account_id"] = SMBC_ACCOUNT_ID
    state["alerts"] = build_alerts(state.get("cards") or {}, smbc)
    # shortfall を cards に反映済み
    state["thresholds"] = {
        "olive_warn_yen": env_int("CARD_DEBIT_OLIVE_WARN_YEN", 500_000),
        "other_warn_yen": env_int("CARD_DEBIT_OTHER_WARN_YEN", 300_000),
        "lead_days": env_int("CARD_DEBIT_LEAD_DAYS", 14),
        "default_due_day": env_int("CARD_DEBIT_DEFAULT_DUE_DAY", 26),
    }

    summary = summary_for_meta(state, smbc)
    print_block(state, smbc)

    if args.dry_run:
        print("# dry-run: state / sync_meta は書きません", file=sys.stderr)
        return 0

    save_state(state)
    push_sync_meta(summary)
    print(f"# wrote {STATE_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
