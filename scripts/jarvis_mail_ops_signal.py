#!/usr/bin/env python3
"""メール系 #ops の色を「中身」で決める共通部品（2026-11-13 松野さん）。

それまでは件数（pending 50 以上・5 以上）だけで投稿し、色は件名の【ops】から
自動で 🔴 になっていた。中身はほぼ流し読み（WeStudy・ダイヤモンド等）と通知メールで、
本当に要対応なのはパートナーと人が書いたメールの数件だけだった。

色の決め方:
  🔴 パートナー／人が書いたメールが、平日 STALE_WEEKDAYS 日以上たまっている
  🟡 パートナー／人が書いたメールはあるがまだ新しい、または流し読み・通知が多いだけ
  🟢 上のどれでもない
通知するのは 🔴 だけ。🟡 は日曜の週次まとめ（今週見る 3〜5 件）に載せる。

データは Supabase の triage_items（ダッシュ・判断デスクで閉じた状態が正）。
読めないときは Mac の queue.json で代わりに数える。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_mail_human import looks_human_mail  # noqa: E402

JST = timezone(timedelta(hours=9))
STALE_WEEKDAYS = int(os.environ.get("JARVIS_MAIL_OPS_STALE_WEEKDAYS") or "3")
SKIM_EXPIRE_DAYS = int(os.environ.get("JARVIS_TRIAGE_SKIM_EXPIRE_DAYS") or "7")
BACKLOG_YELLOW = 50
WEEKLY_PICK_MIN = 3
WEEKLY_PICK_MAX = 5
_FIELDS = "id,lane,kind,status,partner,folder,subject,received_at,from_email,created_at,original_body"


# ---- 取得 -------------------------------------------------------------------
def _sb() -> tuple[str, str] | None:
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    return (url, key) if url and key else None


def _headers(key: str) -> dict[str, str]:
    return {"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"}


def fetch_pending_remote() -> list[dict[str, Any]] | None:
    creds = _sb()
    if not creds:
        return None
    url, key = creds
    q = f"{url}/rest/v1/triage_items?status=eq.pending&select={_FIELDS}&limit=2000"
    try:
        with urllib.request.urlopen(urllib.request.Request(q, headers=_headers(key)), timeout=30) as r:
            rows = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"# mail_ops_signal: supabase 読み込み失敗 {e}", file=sys.stderr)
        return None
    return rows if isinstance(rows, list) else None


def fetch_pending_local() -> list[dict[str, Any]]:
    try:
        from jarvis_night_triage import load_queue

        q = load_queue()
    except Exception as e:  # noqa: BLE001
        print(f"# mail_ops_signal: queue.json 読み込み失敗 {e}", file=sys.stderr)
        return []
    return [i for i in (q.get("items") or []) if i.get("status") == "pending"]


def fetch_pending() -> tuple[list[dict[str, Any]], str]:
    rows = fetch_pending_remote()
    if rows is not None:
        return rows, "supabase"
    return fetch_pending_local(), "queue.json"


def expire_old_skim(*, days: int = SKIM_EXPIRE_DAYS, dry_run: bool = False) -> int:
    """流し読み（kind=skim）で days 日を過ぎた pending を skipped にする（Supabase）。"""
    creds = _sb()
    if not creds or days <= 0:
        return 0
    url, key = creds
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    flt = (
        "status=eq.pending&kind=eq.skim&created_at=lt."
        + urllib.parse.quote(cutoff, safe="")
    )
    hdr = _headers(key)
    if dry_run:
        req = urllib.request.Request(
            f"{url}/rest/v1/triage_items?{flt}&select=id",
            headers={**hdr, "Prefer": "count=exact", "Range": "0-0"},
            method="HEAD",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                tail = (r.headers.get("content-range") or "").split("/")[-1]
                return int(tail) if tail.isdigit() else 0
        except Exception:  # noqa: BLE001
            return 0
    body = json.dumps(
        {"status": "skipped", "updated_at": datetime.now(timezone.utc).isoformat()}
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/rest/v1/triage_items?{flt}",
        data=body,
        method="PATCH",
        headers={**hdr, "Content-Type": "application/json", "Prefer": "return=representation"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            rows = json.loads(r.read().decode("utf-8") or "[]")
        return len(rows) if isinstance(rows, list) else 0
    except Exception as e:  # noqa: BLE001
        print(f"# mail_ops_signal: skim 片付け失敗 {e}", file=sys.stderr)
        return 0


# ---- 判定 -------------------------------------------------------------------
def received_date(it: dict[str, Any]) -> date | None:
    raw = str(it.get("received_at") or "").strip()
    if len(raw) >= 10:
        try:
            return date.fromisoformat(raw[:10].replace("/", "-"))
        except ValueError:
            pass
    raw = str(it.get("created_at") or "").strip()
    if raw:
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=JST)
            return dt.astimezone(JST).date()
        except ValueError:
            pass
    return None


def weekdays_between(start: date, end: date) -> int:
    """start の翌日から end までの平日の数（土日は数えない）。"""
    if end <= start:
        return 0
    n = 0
    d = start + timedelta(days=1)
    while d <= end:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n


def is_human_item(it: dict[str, Any]) -> bool:
    """要対応として数えるもの: パートナー、または人が書いた一般メール。"""
    if it.get("kind") == "activity":
        return False
    lane = it.get("lane") or "partner"
    if lane == "openchat":
        return False
    if lane == "partner":
        return True
    if it.get("kind") != "mail":
        return False
    return looks_human_mail(
        it.get("from_email") or "",
        it.get("subject") or "",
        it.get("original_body") or it.get("summary") or "",
    )


def who(it: dict[str, Any]) -> str:
    return str(it.get("partner") or it.get("folder") or it.get("from_email") or "").strip() or "不明"


def classify(items: Iterable[dict[str, Any]], today: date | None = None) -> dict[str, Any]:
    today = today or datetime.now(JST).date()
    items = [i for i in items if i.get("status", "pending") == "pending" and i.get("kind") != "activity"]
    human: list[dict[str, Any]] = []
    for it in items:
        if not is_human_item(it):
            continue
        rd = received_date(it)
        age = weekdays_between(rd, today) if rd else 0
        human.append({**it, "_age": age, "_date": rd.isoformat() if rd else ""})
    human.sort(key=lambda x: (x["_date"] or "9999", x.get("id") or ""))
    stale = [h for h in human if h["_age"] >= STALE_WEEKDAYS]
    skim = sum(1 for i in items if i.get("kind") == "skim")
    other = len(items) - len(human) - skim
    if stale:
        level = "red"
    elif human or len(items) >= BACKLOG_YELLOW:
        level = "yellow"
    else:
        level = "green"
    return {
        "level": level,
        "total": len(items),
        "human": human,
        "stale": stale,
        "skim": skim,
        "other": other,
        "partner": sum(1 for h in human if (h.get("lane") or "partner") == "partner"),
    }


def _item_line(h: dict[str, Any]) -> str:
    subj = str(h.get("subject") or "").strip()
    if not subj or subj == "(件名なし)":
        subj = "チャット"
    return f"・{who(h)}｜{subj[:40]}（{h['_date'][5:].replace('-', '/') or '?'}・{h['_age']}営業日）"


def daily_text(s: dict[str, Any], *, desk_url: str) -> str:
    """🔴 のときだけ出す毎朝の1本。"""
    stale = s["stale"]
    lines = [
        "【ops】メール要対応（パートナー・人のメール）",
        f"判定: 🔴 要対応 — {len(stale)}件が平日{STALE_WEEKDAYS}日以上止まっています",
    ]
    lines += [_item_line(h) for h in stale[:3]]
    if len(stale) > 3:
        lines.append(f"・ほか {len(stale) - 3}件")
    lines += [
        "",
        f"参考: 未処理 全{s['total']}件のうち 流し読み{s['skim']}・通知{s['other']}は色に入れていません（週次で片付け）",
        f"次: 判断デスクで 返信／返信不要／Todoistへ を決める <{desk_url}|判断デスクを開く>",
    ]
    return "\n".join(lines)


def status_text(s: dict[str, Any]) -> str:
    """立ち上げ後1週間だけ出す 🟡🟢 の短い1本（共通ルール18）。"""
    icon = {"yellow": "🟡 様子見", "green": "🟢 回っています"}.get(s["level"], "🟢 回っています")
    return "\n".join([
        "【ops】メール要対応（パートナー・人のメール）",
        f"判定: {icon}",
        f"止まっている要対応 0件／新しい要対応 {len(s['human'])}件"
        f"（未処理 全{s['total']}件: 流し読み{s['skim']}・通知{s['other']}は色に入れない）",
        "※色の決め方を 11/13 に変更。1週間は 🟢🟡 も出し、その後は 🔴 と日曜の週次まとめだけにします",
    ])


def weekly_pick(s: dict[str, Any], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """今週見る 3〜5 件。止まっている順 → 新しい要対応 → 足りなければ通知メールの古い順。"""
    picks = list(s["human"][:WEEKLY_PICK_MAX])
    if len(picks) < WEEKLY_PICK_MIN:
        today = datetime.now(JST).date()
        ids = {p.get("id") for p in picks}
        rest = [
            i for i in items
            if i.get("kind") == "mail" and i.get("id") not in ids and i.get("kind") != "activity"
        ]
        rest.sort(key=lambda i: (received_date(i) or today).isoformat())
        for it in rest[: WEEKLY_PICK_MIN - len(picks)]:
            rd = received_date(it)
            picks.append({**it, "_age": weekdays_between(rd, today) if rd else 0,
                          "_date": rd.isoformat() if rd else ""})
    return picks


def weekly_text(s: dict[str, Any], picks: list[dict[str, Any]], *, desk_url: str, expired: int) -> str:
    level = "red" if s["stale"] else ("yellow" if s["total"] else "green")
    icon = {"red": "🔴", "yellow": "🟡", "green": "🟢"}[level]
    label = {"red": "要対応あり", "yellow": "今週の片付け", "green": "たまっていません"}[level]
    lines = [
        "【ops】メール 今週の片付け（週次）",
        f"判定: {icon} {label}",
        f"未処理 {s['total']}件: パートナー・人のメール {len(s['human'])}"
        f"（うち止まり {len(s['stale'])}）／通知 {s['other']}／流し読み {s['skim']}",
    ]
    if expired:
        lines.append(f"流し読み {expired}件は{SKIM_EXPIRE_DAYS}日たったので自動で「見た」にしました")
    if picks:
        lines += ["", f"*今週見る {len(picks)}件*（古い順）"]
        lines += [_item_line(p) for p in picks]
    lines += [
        "",
        "見きれなかった分は来週の先頭に回ります。通知・流し読みは「その他メール」で「確認したよ」でまとめて片付け。",
        f"<{desk_url}|判断デスクを開く>",
    ]
    return "\n".join(lines)


def desk_url() -> str:
    try:
        from jarvis_nody_link import nody_link

        return nody_link("/desk")
    except Exception:  # noqa: BLE001
        return "https://jarvis-dashboard-amber.vercel.app/go/loopware?to=/desk"
