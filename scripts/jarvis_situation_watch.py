#!/usr/bin/env python3
"""
Jarvis: 状況ウォッチ集約（Phase 0）

既存 .jarvis_state / watch status を読み、判定カードを JSON に書き出す。
新規ログインは行わない。

  python scripts/jarvis_situation_watch.py
  python scripts/jarvis_situation_watch.py --json   # stdout のみ
  python scripts/jarvis_situation_watch.py --write  # 既定で書き出しもする
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE = REPO / ".jarvis_state"
YAML_PATH = REPO / "config" / "situation_watch.yaml"
OUT_PATH = STATE / "situation_watch.json"
ARCHIVE_PATH = STATE / "situation_watch_archive.json"
WATCH_STATUS = (
    REPO / "line_unofficial_poc" / ".line_auth" / ".chrline_open_chat_watch_status.json"
)
OPENCHAT_MD_GLOB = (
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    / "C2_ルーティン作業/26_パートナー社への相談/815_神大家オプチャ"
)


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def today() -> date:
    return datetime.now(JST).date()


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def load_registry() -> dict[str, Any]:
    if not YAML_PATH.is_file():
        return {"version": 1, "popup_levels": ["attention", "warn"], "items": []}
    return yaml.safe_load(YAML_PATH.read_text(encoding="utf-8")) or {}


def load_archive() -> dict[str, Any]:
    data = load_json(ARCHIVE_PATH)
    if not data:
        return {"archived": {}}
    if "archived" not in data:
        data["archived"] = {}
    return data


def save_archive(data: dict[str, Any]) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = now_iso()
    ARCHIVE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    t = str(s).strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%Y-%m",
    ):
        try:
            if fmt == "%Y-%m":
                return datetime.strptime(t[:7], fmt).replace(tzinfo=JST)
            if fmt == "%Y-%m-%d":
                return datetime.strptime(t[:10], fmt).replace(tzinfo=JST)
            if "%z" in fmt and (t.endswith("Z") or "+" not in t[-6:] and t.count("-") >= 2):
                if t.endswith("Z"):
                    t2 = t[:-1] + "+0000"
                else:
                    t2 = t
                # normalize +09:00 → +0900
                t2 = re.sub(r"([+-]\d{2}):(\d{2})$", r"\1\2", t2)
                try:
                    return datetime.strptime(t2[:26] if "." in t2 else t2, fmt)
                except ValueError:
                    continue
            return datetime.strptime(t[:26] if "." in t else t, fmt).replace(
                tzinfo=JST if "%z" not in fmt else None
            )
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        return None


def days_since(s: str | None) -> int | None:
    dt = parse_dt(s)
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    return (datetime.now(JST) - dt.astimezone(JST)).days


def ym_now() -> str:
    return today().strftime("%Y-%m")


def card(
    *,
    item_id: str,
    title: str,
    category: str,
    level: str,
    summary: str,
    cursor_prompt: str,
    detail: str = "",
    source: str = "",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": item_id,
        "title": title,
        "category": category,
        "level": level,  # ok | info | warn | attention
        "summary": summary,
        "detail": detail,
        "source": source,
        "cursor_prompt": cursor_prompt.strip(),
        "checked_at": now_iso(),
    }
    if payload:
        out["payload"] = payload
    return out


def eval_energy_cf(meta: dict, data: dict | None) -> dict[str, Any]:
    title = meta["title"]
    prompt = meta.get("cursor_prompt") or ""
    src = meta.get("source") or ""
    if not data:
        return card(
            item_id=meta["id"],
            title=title,
            category=meta.get("category") or "",
            level="attention",
            summary="state なし — scripts/jarvis_energy_cf_collect.py を実行",
            cursor_prompt=prompt,
            source=src,
        )
    level = str(data.get("level") or "ok")
    summary = str(data.get("summary") or "データあり")
    detail = str(data.get("detail") or "")
    portal = data.get("portal") or {}
    if portal.get("portalone_credentials") == "missing" and level == "ok":
        # kWh 本収集は未配線でも円ベースなら ok のまま。detail に追記
        detail = (detail + " / " if detail else "") + "ポータルワン認証未設定（円は Zaim）"
    return card(
        item_id=meta["id"],
        title=title,
        category=meta.get("category") or "",
        level=level if level in ("ok", "info", "warn", "attention") else "ok",
        summary=summary,
        detail=detail,
        cursor_prompt=prompt,
        source=src,
    )


def eval_etc(meta: dict, data: dict | None) -> dict[str, Any]:
    title = meta["title"]
    prompt = meta.get("cursor_prompt") or ""
    src = meta.get("source") or ""
    if not data:
        return card(
            item_id=meta["id"],
            title=title,
            category=meta.get("category") or "",
            level="warn",
            summary="state なし",
            cursor_prompt=prompt,
            source=src,
        )
    if data.get("disabled"):
        return card(
            item_id=meta["id"],
            title=title,
            category=meta.get("category") or "",
            level="info",
            summary="無効化中",
            cursor_prompt=prompt,
            source=src,
        )
    day = today().day
    ym = ym_now()
    a = data.get("last_check_a")
    b = data.get("last_check_b")
    rb = data.get("last_result_b") or {}
    rebate = rb.get("rebate_yen")
    target = rb.get("target_month") or ""
    trips = rb.get("asayu_trip_count")
    rate = rb.get("asayu_rate_pct")
    savings = rb.get("savings_yen")
    ack = data.get("dashboard_ack_target_month")
    has_rebate = rebate is not None and bool(target)
    show_banner = has_rebate and ack != target

    approx_days = None
    if isinstance(trips, int) and trips > 0:
        approx_days = (trips + 1) // 2

    rebate_summary = {
        "target_month": target or None,
        "rebate_yen": rebate,
        "asayu_trip_count": trips,
        "asayu_rate_pct": rate,
        "savings_yen": savings if savings is not None else rebate,
        "approx_days": approx_days,
        "at": rb.get("at"),
        "note": rb.get("note") or "",
        "grant_rule": "利用月の翌月20日にETCマイレージへ還元額付与",
    }
    history = []
    for h in data.get("rebate_history") or []:
        if not isinstance(h, dict):
            continue
        history.append(
            {
                "target_month": h.get("target_month"),
                "rebate_yen": h.get("rebate_yen"),
                "asayu_trip_count": h.get("asayu_trip_count"),
                "asayu_rate_pct": h.get("asayu_rate_pct"),
                "savings_yen": h.get("savings_yen"),
                "at": h.get("at"),
                "note": h.get("note") or "",
            }
        )

    parts: list[str] = []
    if has_rebate and show_banner:
        part = f"{target}分 還元 {rebate:,}円" if isinstance(rebate, int) else f"{target}分 還元 {rebate}"
        if isinstance(trips, int):
            part += f" · 対象 {trips}回"
            if isinstance(rate, int):
                part += f"（約{rate}%）"
            if approx_days is not None:
                part += f" · 目安{approx_days}日分"
        else:
            part += " · 対象回数未取得"
        parts.append(part)
    elif has_rebate and not show_banner:
        parts.append(f"{target}分 確認済 · 次は翌月20日後")
    level = "ok"
    if show_banner and has_rebate:
        level = "info"
    if 1 <= day <= 8 and a != ym:
        level = "warn"
        parts.append(f"ウィンドウA未実施（{ym}）")
    if 19 <= day <= 26 and b != ym:
        level = "attention"
        parts.append(f"ウィンドウB未実施（{ym}）")
    if not parts:
        parts.append(f"B最終 {b or '—'} / A最終 {a or '—'}")

    detail_bits = [str(rb.get("note") or "").strip()]
    if show_banner:
        detail_bits.insert(0, "ダッシュボード /etc で還元サマリを確認できます。")
    detail = "\n".join(x for x in detail_bits if x)[:500]

    return card(
        item_id=meta["id"],
        title=title,
        category=meta.get("category") or "",
        level=level,
        summary=" · ".join(parts),
        detail=detail,
        cursor_prompt=prompt,
        source=src,
        payload={
            "rebate_summary": rebate_summary,
            "rebate_history": history[:12],
            "dashboard_ack_target_month": ack,
            "show_banner": show_banner,
            "href": "/etc",
        },
    )


def eval_vpoint(meta: dict) -> dict[str, Any]:
    title = meta["title"]
    prompt = meta.get("cursor_prompt") or ""
    src = meta.get("source") or ""
    cad = load_json(STATE / "vpoint_cadence.json") or {}
    mon = load_json(STATE / "vpoint_monthly.json") or {}
    if cad.get("disabled") and mon.get("disabled"):
        return card(
            item_id=meta["id"],
            title=title,
            category=meta.get("category") or "",
            level="info",
            summary="無効化中",
            cursor_prompt=prompt,
            source=src,
        )
    bal = cad.get("last_balance_pt")
    actions = [a for a in (cad.get("open_actions") or []) if a.get("status") == "open"]
    rc = mon.get("last_result_c") or {}
    grant = rc.get("grant_summary") if isinstance(rc.get("grant_summary"), dict) else {}
    if not grant and isinstance(mon.get("grant_history"), list) and mon["grant_history"]:
        first = mon["grant_history"][0]
        grant = first if isinstance(first, dict) else {}

    target = str(grant.get("target_month") or rc.get("target_month") or "")
    total_pt = grant.get("total_pt")
    ack = mon.get("dashboard_ack_target_month")
    has_grant = bool(target) and total_pt is not None
    show_banner = has_grant and ack != target
    bc = grant.get("by_cadence") if isinstance(grant.get("by_cadence"), dict) else {}

    parts: list[str] = []
    if has_grant and show_banner:
        part = f"{target}分 +{total_pt:,}pt" if isinstance(total_pt, int) else f"{target}分 +{total_pt}pt"
        if bc:
            part += f" · 月次条件 {bc.get('monthly', 0)}pt · 日次 {bc.get('daily', 0)}pt"
        parts.append(part)
        if grant.get("condition_grants_ok") is False or grant.get("shop_up_ok") is False:
            parts.append("要確認あり")
    elif has_grant and not show_banner:
        parts.append(f"{target}分 確認済 · 次はウィンドウC更新後")
    if bal is not None:
        parts.append(f"残高 {bal:,}pt" if isinstance(bal, int) else f"残高 {bal}")
    if actions:
        short = []
        for a in actions[:4]:
            t = str(a.get("title") or a.get("id") or "").strip()
            aid = str(a.get("id") or "")
            if aid == "eraberu_tokuten" or "選べる特典" in t:
                short.append("選べる特典")
            elif aid == "nisa_eval_band" or "NISA" in t or "評価額" in t:
                short.append("NISA評価額")
            elif aid == "visa_touch_not_id" or "Visa" in t or "iD" in t or "タッチ" in t:
                short.append("Visaタッチ")
            elif aid == "tsumitate_rate_band" or "積立" in t:
                short.append("積立還元帯")
            else:
                short.append((t[:12] + "…") if len(t) > 12 else t or aid or "?")
        parts.append(f"要対応{len(actions)}: " + " / ".join(short))
    note = str(rc.get("note") or "")
    if note and not has_grant:
        parts.append(note[:80])
    level = "ok"
    if show_banner:
        # 未確認の月次サマリはホーム掲載（info 以上）。考察の要確認もこの期間だけ attention
        level = "info"
        if (
            grant.get("condition_grants_ok") is False
            or grant.get("shop_up_ok") is False
            or rc.get("ok") is False
        ):
            level = "attention"
    if actions:
        # cadence の未対応は確認後も状況ウォッチ／ホームに残してよい
        if level in ("ok", "info"):
            level = "warn"
    if not parts:
        parts.append("データなし")
        level = "warn"

    detail_lines: list[str] = []
    if show_banner:
        detail_lines.append("ダッシュボード /vpoint で付与サマリ（％別・考察）を確認できます。")
        for ins in (grant.get("insights") or [])[:4]:
            detail_lines.append(f"· {ins}")
    action_items: list[dict[str, Any]] = []
    for a in actions:
        aid = str(a.get("id") or "")
        atitle = str(a.get("title") or aid)
        why = str(a.get("why") or "").strip()
        how = str(a.get("how") or "").strip()
        evidence = str(a.get("evidence") or "").strip()
        detail_lines.append(
            f"- [{aid}] {atitle}\n"
            f"  なぜ: {why}\n"
            f"  次: {how}"
            + (f"\n  根拠: {evidence}" if evidence else "")
        )
        action_items.append(
            {
                "date": aid,
                "shop": atitle,
                "proposal": how or why,
                "line": f"{atitle} — {how or why}",
                "kind": "vpoint_open_action",
                "why": why,
                "how": how,
                "evidence": evidence,
            }
        )

    hist = [h for h in (mon.get("grant_history") or []) if isinstance(h, dict)][:12]
    payload: dict[str, Any] = {
        "grant_summary": grant or None,
        "grant_history": hist,
        "dashboard_ack_target_month": ack,
        "show_banner": show_banner,
        "href": "/vpoint",
    }
    if action_items:
        payload["actions"] = action_items
    return card(
        item_id=meta["id"],
        title=title,
        category=meta.get("category") or "",
        level=level,
        summary=" · ".join(parts),
        detail="\n".join(detail_lines),
        cursor_prompt=prompt,
        source=src,
        payload=payload,
    )


def _parse_ymd(s: str) -> date | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def eval_card_annual_fee(meta: dict, data: dict | None) -> dict[str, Any]:
    """Olive / 単体PP の年会費ウォッチ（二重会員・有効期限退会・期限前を強調）。"""
    title = meta["title"]
    prompt = meta.get("cursor_prompt") or ""
    src = meta.get("source") or ""
    if not data or data.get("disabled"):
        return card(
            item_id=meta["id"],
            title=title,
            category=meta.get("category") or "",
            level="info",
            summary="未設定または無効化中",
            cursor_prompt=prompt,
            source=src,
        )

    cards = [c for c in (data.get("cards") or []) if isinstance(c, dict)]
    inv = data.get("investigation") if isinstance(data.get("investigation"), dict) else {}
    lessons = data.get("lessons") if isinstance(data.get("lessons"), dict) else {}
    today = datetime.now(JST).date()

    parts: list[str] = []
    detail_lines: list[str] = []
    actions: list[dict[str, Any]] = []
    level = "info"
    attention = False
    fee_bearing_active = 0
    risk_flags: list[str] = []

    cancelled_prefixes = ("cancelled", "cancel_done", "closed")

    for c in cards:
        label = str(c.get("label") or c.get("id") or "カード")
        status = str(c.get("status") or "")
        cancel_mode = str(c.get("cancel_mode") or "")
        fee = c.get("annual_fee_yen")
        last_d = str(c.get("last_fee_date") or "") or "—"
        next_d = str(c.get("next_fee_date") or "") or "—"
        deadline = str(c.get("cancel_deadline_to_skip_next") or "") or "—"
        last_yen = c.get("last_fee_yen")
        is_cancelled = status.lower().startswith(cancelled_prefixes)
        parts.append(f"{label}: {status}")
        fee_line = (
            f"- 年会費: {fee:,}円"
            if isinstance(fee, int)
            else f"- 年会費: {fee}"
        )
        last_line = f"- 直近請求: {last_d}"
        if isinstance(last_yen, int):
            last_line += f" / {last_yen:,}円"
        detail_lines.append(
            "\n".join(
                [
                    f"【{label}】",
                    f"- 状態: {status}",
                    fee_line,
                    last_line,
                    f"- 次回見込み: {next_d}",
                    f"- 次回回避の解約期限: {deadline}",
                ]
            )
        )
        if cancel_mode:
            detail_lines.append(f"- 退会モード: {cancel_mode}")
        if c.get("waiver_notes"):
            detail_lines.append(f"- 無料化メモ: {c.get('waiver_notes')}")
        for ev in (c.get("evidence") or [])[:4]:
            detail_lines.append(f"  · {ev}")
        for a in c.get("actions") or []:
            actions.append(
                {
                    "date": str(c.get("id") or ""),
                    "shop": label,
                    "proposal": str(a),
                    "line": f"{label} — {a}",
                    "kind": "card_annual_fee_action",
                }
            )

        # 課金対象として残っているか
        if not is_cancelled and isinstance(fee, int) and fee >= 10000:
            if "有効期限" in cancel_mode or status in (
                "active",
                "active_charged",
                "cancel_at_expiry_pending",
                "fee_notice_aug2_zaim_pending",
            ):
                fee_bearing_active += 1

        # 有効期限退会＝まだ会員（完了扱いしない）
        if (not is_cancelled) and (
            "有効期限" in cancel_mode or status == "cancel_at_expiry_pending"
        ):
            attention = True
            level = "warn"
            risk_flags.append(f"{label}: 有効期限退会中＝年会費リスク継続")
            actions.append(
                {
                    "date": str(c.get("id") or ""),
                    "shop": label,
                    "proposal": "即時退会へ切り替え（有効期限退会のままでは年会費がかかりうる）",
                    "line": f"{label} — 即時退会へ切り替え（有効期限退会のままでは年会費がかかりうる）",
                    "kind": "card_annual_fee_guard",
                }
            )

        # 解約期限・次回請求のカウントダウン（高額は早めに）
        fee_yen = fee if isinstance(fee, int) else 0
        warn_days = 180 if fee_yen >= 30000 else 120
        atten_days = 90 if fee_yen >= 30000 else 60
        try:
            if last_d and last_d != "—":
                ld = _parse_ymd(last_d)
                if ld and 0 <= (today - ld).days <= 90 and not is_cancelled:
                    attention = True
            if next_d and next_d != "—":
                nd = _parse_ymd(next_d)
                if nd:
                    days = (nd - today).days
                    if 0 <= days <= atten_days:
                        attention = True
                        level = "warn"
                        risk_flags.append(f"{label}: 次回年会費まであと{days}日")
                    elif 0 <= days <= warn_days:
                        attention = True
                        risk_flags.append(f"{label}: 次回年会費まであと{days}日")
            if deadline and deadline != "—":
                dd = _parse_ymd(deadline)
                if dd:
                    days = (dd - today).days
                    if 0 <= days <= atten_days:
                        attention = True
                        level = "warn"
                        risk_flags.append(f"{label}: 次回回避の解約期限まであと{days}日")
                    elif 0 <= days <= warn_days:
                        attention = True
                        risk_flags.append(f"{label}: 次回回避の解約期限まであと{days}日")
                    elif days < 0 and not is_cancelled:
                        attention = True
                        level = "warn"
                        risk_flags.append(f"{label}: 解約期限超過（次回年会費確定の可能性）")
        except Exception:
            pass

        if status in ("active_charged", "cancel_at_expiry_pending"):
            attention = True

    # 二重会員（高額年会費が2枚以上アクティブ）
    if fee_bearing_active >= 2:
        attention = True
        level = "warn"
        risk_flags.append(
            f"高額年会費カードが{fee_bearing_active}枚並行（二重課金リスク）"
        )
        actions.insert(
            0,
            {
                "date": "dual",
                "shop": "カード年会費ガード",
                "proposal": "捨てるカードは即時退会。有効期限退会は明示同意があるときだけ",
                "line": "カード年会費ガード — 捨てるカードは即時退会。有効期限退会は明示同意があるときだけ",
                "kind": "card_annual_fee_guard",
            },
        )

    if risk_flags:
        detail_lines.append("\n【リスク】\n" + "\n".join(f"- {x}" for x in risk_flags))

    if lessons.get("summary"):
        detail_lines.append(f"\n【教訓】\n{lessons.get('summary')}")

    if inv.get("verdict"):
        detail_lines.append(f"\n【調査結論】\n{inv.get('verdict')}")
    for w in (inv.get("why_charged") or [])[:5]:
        detail_lines.append(f"- 原因: {w}")
    for a in (inv.get("avoidance") or [])[:5]:
        detail_lines.append(f"- 回避策: {a}")

    if attention and level == "info":
        level = "attention"

    summary = " · ".join(parts) if parts else "カード情報なし"
    if risk_flags:
        summary = "⚠️ " + " / ".join(risk_flags[:2])
    elif inv.get("verdict"):
        summary = str(inv["verdict"])[:160]

    payload: dict[str, Any] = {
        "cards": cards,
        "investigation": inv or None,
        "lessons": lessons or None,
        "risk_flags": risk_flags,
        "href": "/situation#watch-card_annual_fee",
    }
    if actions:
        payload["actions"] = actions

    return card(
        item_id=meta["id"],
        title=title,
        category=meta.get("category") or "",
        level=level,
        summary=summary,
        detail="\n".join(detail_lines),
        cursor_prompt=prompt,
        source=src,
        payload=payload,
    )


def eval_rent_step(meta: dict) -> dict[str, Any]:
    """Grandole 入居1年 +4,000 の月次確認（ETC/Vポイント同型バナー）。"""
    title = meta["title"]
    prompt = meta.get("cursor_prompt") or ""
    src = meta.get("source") or ""
    # 当月未実行なら自動ビルド
    st0 = load_json(STATE / "rent_step_monthly.json") or {}
    if not st0.get("disabled"):
        ym_now = datetime.now(JST).strftime("%Y-%m")
        if st0.get("last_check") != ym_now:
            script = REPO / "scripts" / "jarvis_rent_step_monthly_check.py"
            py = Path.home() / "selenium_env" / "venv" / "bin" / "python"
            exe = str(py) if py.is_file() else sys.executable
            try:
                import subprocess

                subprocess.run(
                    [exe, str(script), "--build-only"],
                    cwd=str(REPO),
                    capture_output=True,
                    text=True,
                    timeout=90,
                    check=False,
                )
            except Exception as e:
                print(f"# rent_step auto-build skipped: {e}", file=sys.stderr)

    mon = load_json(STATE / "rent_step_monthly.json") or {}
    if mon.get("disabled"):
        return card(
            item_id=meta["id"],
            title=title,
            category=meta.get("category") or "",
            level="info",
            summary="無効化中",
            cursor_prompt=prompt,
            source=src,
        )
    lr = mon.get("last_result") or {}
    summary = lr.get("summary") if isinstance(lr.get("summary"), dict) else {}
    target = str(lr.get("target_month") or "")
    ack = mon.get("dashboard_ack_target_month")
    actionable = bool(summary.get("actionable"))
    has = bool(target) and (
        actionable
        or int(summary.get("overdue_count") or 0) > 0
        or int(summary.get("changed_count") or 0) > 0
        or int(summary.get("deposit_mismatch_count") or 0) > 0
        or int(summary.get("aggregate_need_count") or 0) > 0
        or int(summary.get("follow_count") or 0) > 0
        or int((lr.get("follow_drafts") or {}).get("follow_count") or 0) > 0
    )
    show_banner = has and ack != target

    parts: list[str] = []
    follow = lr.get("follow_drafts") if isinstance(lr.get("follow_drafts"), dict) else {}
    if show_banner:
        parts.append(
            f"{target} · 未反映{summary.get('overdue_count', 0)}"
            f" · 様子見{summary.get('grace_count', 0)}"
            f" · 入金差{summary.get('deposit_mismatch_count', 0)}"
            f" · 入金様子見{follow.get('watch_count', summary.get('follow_watch_count', 0))}"
            f" · フォロー下書き{follow.get('draft_count', summary.get('follow_draft_count', 0))}"
        )
        for d in (follow.get("drafts") or [])[:2]:
            parts.append(f"下書き {d.get('manager')} {d.get('item_count')}件")
        for row in (summary.get("grace") or [])[:2]:
            parts.append(f"様子見 {row.get('label')}")
        for row in (summary.get("deposit_mismatch") or [])[:2]:
            parts.append(f"入金差 {row.get('label')}")
        for row in (summary.get("overdue") or [])[:2]:
            parts.append(f"未反映 {row.get('label')}")
    elif has and not show_banner:
        parts.append(f"{target}分 確認済 · 次は翌月更新後")
    else:
        parts.append(
            f"OK {summary.get('ok_count', 0)} · 不明 {summary.get('unknown_count', 0)}"
            if summary
            else "データなし"
        )

    level = "ok"
    if show_banner:
        level = "info"
        if (
            int(summary.get("overdue_count") or 0) > 0
            or int(summary.get("changed_count") or 0) > 0
            or int(summary.get("deposit_mismatch_count") or 0) > 0
            or int(summary.get("aggregate_need_count") or 0) > 0
            or int(follow.get("follow_count") or 0) > 0
        ):
            level = "attention"
        elif int(summary.get("upcoming_count") or 0) > 0:
            level = "warn"
    if not parts:
        parts.append("データなし")
        level = "warn"

    detail_lines: list[str] = []
    if show_banner:
        detail_lines.append(
            "ダッシュボード /rent-step で号室入金・フォロー下書きを確認できます。"
        )
        for d in (follow.get("drafts") or [])[:5]:
            detail_lines.append(
                f"· 下書き {d.get('manager')}: {d.get('subject')}（{d.get('item_count')}件）"
            )
        for row in (summary.get("overdue") or [])[:4]:
            detail_lines.append(f"· 未反映 {row.get('label')}: {row.get('reason')}")
        for row in (summary.get("deposit_mismatch") or [])[:4]:
            detail_lines.append(f"· 入金差 {row.get('label')}: {row.get('reason')}")
        for row in (summary.get("aggregates_need") or [])[:4]:
            detail_lines.append(
                f"· 合算 {row.get('title')}: gap={row.get('gap_yen')} → {row.get('memo_key')}"
            )
        for row in (summary.get("upcoming") or [])[:3]:
            detail_lines.append(f"· まもなく {row.get('label')}: {row.get('reason')}")

    hist = [h for h in (mon.get("change_history") or []) if isinstance(h, dict)][:20]
    payload = {
        "rent_summary": summary,
        "units": lr.get("units") or [],
        "aggregates": lr.get("aggregates") or [],
        "follow_drafts": follow,
        "change_history": hist,
        "dashboard_ack_target_month": ack,
        "show_banner": show_banner,
        "href": "/rent-step",
        "target_month": target,
        "grant_rule": lr.get("grant_rule"),
        "note": lr.get("note"),
        "delta_yen": lr.get("delta_yen") or 4000,
    }
    return card(
        item_id=meta["id"],
        title=title,
        category=meta.get("category") or "",
        level=level,
        summary=" · ".join(parts),
        detail="\n".join(detail_lines),
        cursor_prompt=prompt,
        source=src,
        payload=payload,
    )


def eval_line_export(meta: dict, data: dict | None) -> dict[str, Any]:
    title = meta["title"]
    prompt = meta.get("cursor_prompt") or ""
    src = meta.get("source") or ""
    if not data or data.get("disabled"):
        return card(
            item_id=meta["id"],
            title=title,
            category=meta.get("category") or "",
            level="info" if data and data.get("disabled") else "warn",
            summary="無効化中" if data and data.get("disabled") else "state なし",
            cursor_prompt=prompt,
            source=src,
        )
    routes = data.get("routes") or {}
    ask: list[str] = []
    suggest: list[str] = []
    for rid, r in routes.items():
        days = days_since(r.get("last_import_at"))
        if days is None:
            ask.append(rid)
            continue
        if days >= 30:
            ask.append(f"{rid}({days}日)")
        elif days >= 14:
            suggest.append(f"{rid}({days}日)")
    level = "ok"
    parts = [f"ルート {len(routes)}"]
    if suggest:
        level = "warn"
        parts.append(f"suggest {len(suggest)}")
    if ask:
        level = "attention"
        parts.append(f"ask {len(ask)}")
    if not ask and not suggest:
        parts.append("経過良好")
    return card(
        item_id=meta["id"],
        title=title,
        category=meta.get("category") or "",
        level=level,
        summary=" · ".join(parts),
        detail="ask: " + ", ".join(ask[:6]) + (("; suggest: " + ", ".join(suggest[:6])) if suggest else ""),
        cursor_prompt=prompt,
        source=src,
    )


def eval_westudy(meta: dict, data: dict | None) -> dict[str, Any]:
    title = meta["title"]
    prompt = meta.get("cursor_prompt") or ""
    src = meta.get("source") or ""
    if not data:
        return card(
            item_id=meta["id"],
            title=title,
            category=meta.get("category") or "",
            level="warn",
            summary="state なし",
            cursor_prompt=prompt,
            source=src,
        )
    if data.get("disabled"):
        return card(
            item_id=meta["id"],
            title=title,
            category=meta.get("category") or "",
            level="info",
            summary="無効化中（安定済）",
            cursor_prompt=prompt,
            source=src,
        )
    conc = data.get("last_conclusion") or "—"
    succ = data.get("consecutive_successes") or 0
    need = data.get("success_needed") or 2
    level = "ok" if conc == "success" else "attention"
    if conc == "success" and succ < need:
        level = "info"
    return card(
        item_id=meta["id"],
        title=title,
        category=meta.get("category") or "",
        level=level,
        summary=f"{conc} · 連続成功 {succ}/{need}",
        detail=str(data.get("last_result_note") or "")[:200],
        cursor_prompt=prompt,
        source=src,
    )


def count_today_thread_headings() -> int:
    base = OPENCHAT_MD_GLOB
    if not base.is_dir():
        return -1
    today_s = today().strftime("%Y/%m/%d")
    pat = re.compile(rf"^### {re.escape(today_s)}.*【スレッド】", re.M)
    n = 0
    for md in base.glob("*/5.やり取り.md"):
        try:
            text = md.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        n += len(pat.findall(text))
    return n


def eval_openchat(meta: dict) -> dict[str, Any]:
    title = meta["title"]
    prompt = meta.get("cursor_prompt") or ""
    src = meta.get("source") or ""
    data = load_json(WATCH_STATUS)
    if not data:
        return card(
            item_id=meta["id"],
            title=title,
            category=meta.get("category") or "",
            level="warn",
            summary="常時監視 status なし",
            cursor_prompt=prompt,
            source=src,
        )
    state = data.get("state") or "—"
    hb_days = days_since(data.get("heartbeat_at"))
    err = str(data.get("last_write_error") or "").strip()
    threads_today = count_today_thread_headings()
    parts = [f"launchd {state}"]
    if hb_days is not None:
        parts.append(f"heartbeat {hb_days}日前" if hb_days else "heartbeat 直近")
    if threads_today >= 0:
        parts.append(f"今日【スレッド】{threads_today}件")
    level = "ok"
    if state != "running":
        level = "attention"
    elif hb_days is not None and hb_days >= 1:
        level = "warn"
    if err:
        level = "attention"
        parts.append("書込エラーあり")
    return card(
        item_id=meta["id"],
        title=title,
        category=meta.get("category") or "",
        level=level,
        summary=" · ".join(parts),
        detail=(err[:300] if err else ""),
        cursor_prompt=prompt,
        source=src,
    )


def eval_square(meta: dict, data: dict | None) -> dict[str, Any]:
    title = meta["title"]
    prompt = meta.get("cursor_prompt") or ""
    src = meta.get("source") or ""
    if not data:
        return card(
            item_id=meta["id"],
            title=title,
            category=meta.get("category") or "",
            level="info",
            summary="state なし",
            cursor_prompt=prompt,
            source=src,
        )
    if data.get("structural_limit"):
        return card(
            item_id=meta["id"],
            title=title,
            category=meta.get("category") or "",
            level="warn",
            summary="構造限界フラグ ON",
            detail=str(data.get("structural_limit_note") or "")[:300],
            cursor_prompt=prompt,
            source=src,
        )
    last_ok = (data.get("last_ok") or {}).get("at") or data.get("last_probe_at")
    d = days_since(last_ok)
    level = "ok"
    if d is None:
        level = "info"
        summary = "最終OK不明"
    elif d > 30:
        level = "info"
        summary = f"最終OK {d}日前（週次任意）"
    else:
        summary = f"最終OK {d}日前 · probe OK"
    return card(
        item_id=meta["id"],
        title=title,
        category=meta.get("category") or "",
        level=level,
        summary=summary,
        cursor_prompt=prompt,
        source=src,
    )


def eval_chrline(meta: dict, data: dict | None) -> dict[str, Any]:
    title = meta["title"]
    prompt = meta.get("cursor_prompt") or ""
    src = meta.get("source") or ""
    if not data:
        return card(
            item_id=meta["id"],
            title=title,
            category=meta.get("category") or "",
            level="info",
            summary="state なし",
            cursor_prompt=prompt,
            source=src,
        )
    ver = (data.get("installed") or {}).get("package_version") or "—"
    upd = bool(data.get("update_available"))
    level = "attention" if upd else "ok"
    return card(
        item_id=meta["id"],
        title=title,
        category=meta.get("category") or "",
        level=level,
        summary=f"v{ver}" + (" · 更新あり" if upd else " · 最新"),
        cursor_prompt=prompt,
        source=src,
    )


def eval_car_loan(meta: dict, data: dict | None) -> dict[str, Any]:
    title = meta["title"]
    prompt = meta.get("cursor_prompt") or ""
    src = meta.get("source") or ""
    if not data or data.get("disabled"):
        return card(
            item_id=meta["id"],
            title=title,
            category=meta.get("category") or "",
            level="info",
            summary="無効 or state なし",
            cursor_prompt=prompt,
            source=src,
        )
    apps = data.get("applications") or []
    done = [a for a in apps if a.get("status") == "contract_completed"]
    funding = data.get("funding_setup") or {}
    vehicle = data.get("target_vehicle") or "車両"
    if done:
        fund_st = funding.get("status") or "—"
        level = "warn" if fund_st == "pending" else "ok"
        summary = f"{vehicle} · 契約完了 · funding={fund_st}"
    else:
        level = "info"
        statuses = ", ".join(sorted({str(a.get("status")) for a in apps})) or "申請なし"
        summary = f"{vehicle} · {statuses}"
    return card(
        item_id=meta["id"],
        title=title,
        category=meta.get("category") or "",
        level=level,
        summary=summary,
        detail=str(funding.get("note") or "")[:200],
        cursor_prompt=prompt,
        source=src,
    )


def eval_sbi(meta: dict, data: dict | None) -> dict[str, Any]:
    title = meta["title"]
    prompt = meta.get("cursor_prompt") or ""
    src = meta.get("source") or ""
    if not data:
        return card(
            item_id=meta["id"],
            title=title,
            category=meta.get("category") or "",
            level="info",
            summary="state なし",
            cursor_prompt=prompt,
            source=src,
        )
    cl = data.get("checklist") or {}
    labels = {
        "nisa_eval_100man": "NISA評価額100万帯",
        "nisa_eval_200man": "NISA評価額200万帯（資産特典+0.5%）",
        "credit_tsumitate_rate_actual": "クレカ積立還元（実績1%／6%未達）",
        "cvs_rail_note": "コンビニ等の決済レール（iD優勢＝高還元対象外）",
    }
    follow: list[tuple[str, str, str]] = []
    for k, v in cl.items():
        st = str((v or {}).get("status") or "")
        if st in ("ok", "ok_user_confirmed", "ordered"):
            continue
        note = str((v or {}).get("note") or "")
        follow.append((k, st, note))
    level = "ok" if not follow else "warn"
    if any(
        "id_dominant" in st or "1pct" in st or st == "confirm"
        for _, st, _ in follow
    ):
        level = "warn"

    action_items: list[dict[str, Any]] = []
    detail_lines: list[str] = []
    short: list[str] = []
    for k, st, note in follow:
        label = labels.get(k, k)
        short.append(label.split("（")[0][:14])
        detail_lines.append(f"- [{k}] {label}\n  状態: {st}\n  メモ: {note}")
        action_items.append(
            {
                "date": k,
                "shop": label,
                "proposal": note or st,
                "line": f"{label} — {note or st}",
                "kind": "sbi_vpoint_follow",
            }
        )

    summary = (
        f"要フォロー {len(follow)}/{len(cl)}: " + " / ".join(short[:4])
        if follow
        else f"チェック {len(cl)} 項目OK寄り"
    )
    return card(
        item_id=meta["id"],
        title=title,
        category=meta.get("category") or "",
        level=level,
        summary=summary,
        detail="\n".join(detail_lines),
        cursor_prompt=prompt,
        source=src,
        payload={"actions": action_items} if action_items else None,
    )


def eval_night_triage(meta: dict, data: dict | None) -> dict[str, Any]:
    title = meta["title"]
    prompt = meta.get("cursor_prompt") or ""
    src = meta.get("source") or ""
    if not data:
        return card(
            item_id=meta["id"],
            title=title,
            category=meta.get("category") or "",
            level="warn",
            summary="queue なし",
            cursor_prompt=prompt,
            source=src,
        )
    items = data.get("items") or []
    pending = sum(
        1 for i in items if i.get("status") == "pending" and i.get("kind") != "activity"
    )
    upd = data.get("updated_at")
    d = days_since(upd)
    level = "ok"
    if pending >= 5:
        level = "warn"
    if pending >= 10:
        level = "attention"
    if d is not None and d >= 2:
        level = "attention" if level == "ok" else level
    parts = [f"pending {pending}", f"更新 {upd or '—'}"[:22]]
    if d is not None and d >= 1:
        parts.append(f"{d}日前")
    return card(
        item_id=meta["id"],
        title=title,
        category=meta.get("category") or "",
        level=level,
        summary=" · ".join(parts),
        cursor_prompt=prompt,
        source=src,
    )


def eval_zaim_quality(meta: dict, data: dict | None) -> dict[str, Any]:
    title = meta["title"]
    prompt = meta.get("cursor_prompt") or ""
    src = meta.get("source") or ""
    weekly = load_json(STATE / "zaim_csv_weekly.json")
    bank = load_json(STATE / "zaim_bank_sync.json")
    weekly_note = ""
    if weekly and weekly.get("last_ok") is False and weekly.get("last_error"):
        weekly_note = (
            f"／CSV週次失敗: {str(weekly.get('last_error'))[:80]} "
            "→ zaim_budget_apply.py --login のち zaim_csv_weekly_runner.sh"
        )
    elif weekly and weekly.get("last_success_at"):
        weekly_note = f"／CSV週次成功 {str(weekly.get('last_success_at'))[:16]}"

    bank_note = ""
    bank_detail = ""
    bank_level = "ok"
    if bank:
        bank_level = str(bank.get("level") or "ok")
        bank_note = f"／銀行連携: {str(bank.get('summary') or '')[:100]}"
        parts = []
        if bank.get("detail"):
            parts.append("【銀行・カード連携】\n" + str(bank.get("detail")))
        steps = bank.get("phase1_steps") or []
        if steps and bank_level in ("attention", "warn"):
            parts.append("【手動更新 Phase1】\n" + "\n".join(f"- {s}" for s in steps[:8]))
        bank_detail = "\n\n".join(parts)

    if not data:
        level = "warn"
        if bank_level in ("attention", "warn"):
            level = "warn" if bank_level == "warn" else "attention"
        return card(
            item_id=meta["id"],
            title=title,
            category=meta.get("category") or "",
            level=level,
            summary="state なし — jarvis_zaim_quality_check.py を実行" + weekly_note + bank_note,
            detail=bank_detail or None,
            cursor_prompt=prompt,
            source=src,
            payload={"bank_sync": bank} if bank else {},
        )
    level = str(data.get("level") or "ok")
    if level not in ("ok", "info", "warn", "attention"):
        level = "ok"
    if weekly and weekly.get("last_ok") is False and level == "ok":
        level = "warn"
    if bank_level == "warn" and level in ("ok", "info"):
        level = "warn"
    elif bank_level == "attention" and level in ("ok", "info"):
        level = "attention"
    action_items = data.get("action_items") or []
    if not action_items and data.get("samples"):
        for s in data.get("samples") or []:
            if not (s.get("both_include") or s.get("action") or s.get("viewpoint") in (
                "both_include",
                "both_exclude",
                "amazon",
                "must_include",
            )):
                continue
            act = s.get("action") if isinstance(s.get("action"), dict) else {}
            date = str(act.get("date") or s.get("date") or "")
            shop = str(act.get("shop") or s.get("shop") or "")
            try:
                amount = float(act.get("amount") or s.get("smart_yen") or s.get("card_yen") or 0)
            except (TypeError, ValueError):
                amount = 0.0
            proposal = str(s.get("proposal") or "").strip()
            line = f"{date} / {shop} / ¥{amount:,.0f}"
            if proposal:
                line = f"{line} / {proposal}"
            action_items.append(
                {
                    "date": date,
                    "shop": shop,
                    "amount": amount,
                    "proposal": proposal,
                    "kind": s.get("viewpoint") or "",
                    "line": line,
                    "action": act or None,
                }
            )
    action_lines = data.get("action_lines") or [a.get("line") for a in action_items if a.get("line")]
    detail = str(data.get("detail") or "")
    if action_lines and "要対応:" not in detail:
        detail = (
            "要対応:\n"
            + "\n".join(f"- {ln}" for ln in action_lines[:20])
            + (("\n" + detail) if detail else "")
        )
    if bank_detail:
        detail = (detail + "\n\n" + bank_detail).strip() if detail else bank_detail
    payload: dict[str, Any] = {
        "actions": action_items[:30],
        "action_lines": action_lines[:30],
        "never_archive": bool(meta.get("never_archive")),
        "bank_sync": {
            "level": bank.get("level") if bank else None,
            "summary": bank.get("summary") if bank else None,
            "stale": (bank.get("stale") or [])[:20] if bank else [],
            "missing": (bank.get("missing") or [])[:20] if bank else [],
        },
    }
    pending_n = 0
    try:
        cl_path = STATE / "zaim_watch_changelog.json"
        if cl_path.is_file():
            cl = json.loads(cl_path.read_text(encoding="utf-8"))
            entries = list(cl.get("entries") or [])
            pending = [e for e in entries if e.get("status") == "pending_confirm"]
            pending_n = len(pending)
            payload["recent_fixes"] = entries[-30:]
            payload["pending_confirm_count"] = pending_n
            if pending_n and level in ("ok", "info"):
                level = "attention"
    except Exception:
        pass
    summary = str(data.get("summary") or "データあり") + weekly_note + bank_note
    if pending_n:
        summary = f"直し確認待ち {pending_n}件 · " + summary
    return card(
        item_id=meta["id"],
        title=title,
        category=meta.get("category") or "",
        level=level,
        summary=summary,
        detail=detail,
        cursor_prompt=prompt,
        source=src,
        payload=payload,
    )


def refresh_zaim_quality() -> None:
    """評価前に CSV から再検知（ログイン不要）＋銀行連携鮮度。"""
    import subprocess

    py = Path.home() / "selenium_env" / "venv" / "bin" / "python"
    exe = str(py) if py.is_file() else sys.executable
    for script_name in ("jarvis_zaim_quality_check.py", "jarvis_zaim_bank_sync_check.py"):
        script = REPO / "scripts" / script_name
        if not script.is_file():
            continue
        try:
            subprocess.run(
                [exe, str(script)],
                cwd=str(REPO),
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except Exception as e:
            print(f"# {script_name} refresh failed: {e}", file=sys.stderr)


EVALUATORS = {
    "etc_mileage": lambda m: eval_etc(m, load_json(STATE / "etc_monthly.json")),
    "vpoint": lambda m: eval_vpoint(m),
    "rent_step": lambda m: eval_rent_step(m),
    "card_annual_fee": lambda m: eval_card_annual_fee(
        m, load_json(STATE / "card_annual_fee.json")
    ),
    "line_export": lambda m: eval_line_export(m, load_json(STATE / "line_export_reminder.json")),
    "energy_cf": lambda m: eval_energy_cf(m, load_json(STATE / "energy_cf.json")),
    "westudy_weekly": lambda m: eval_westudy(m, load_json(STATE / "westudy_weekly_watch.json")),
    "openchat_threads": lambda m: eval_openchat(m),
    "square_probe": lambda m: eval_square(m, load_json(STATE / "square_probe.json")),
    "chrline_version": lambda m: eval_chrline(m, load_json(STATE / "chrline_version.json")),
    "car_loan": lambda m: eval_car_loan(m, load_json(STATE / "car_loan.json")),
    "sbi_vpoint_up": lambda m: eval_sbi(m, load_json(STATE / "sbi_vpoint_up_checklist.json")),
    "night_triage": lambda m: eval_night_triage(m, load_json(STATE / "night_triage" / "queue.json")),
    "zaim_quality": lambda m: (
        refresh_zaim_quality(),
        eval_zaim_quality(m, load_json(STATE / "zaim_quality_watch.json")),
    )[1],
}


def collect() -> dict[str, Any]:
    reg = load_registry()
    archive = load_archive()
    archived_map = archive.get("archived") or {}
    popup_levels = set(reg.get("popup_levels") or ["attention", "warn"])
    items_out: list[dict[str, Any]] = []
    for meta in reg.get("items") or []:
        if not meta.get("enabled", True):
            continue
        iid = meta.get("id") or ""
        fn = EVALUATORS.get(iid)
        if not fn:
            items_out.append(
                card(
                    item_id=iid,
                    title=meta.get("title") or iid,
                    category=meta.get("category") or "",
                    level="info",
                    summary="評価器未実装",
                    cursor_prompt=meta.get("cursor_prompt") or "",
                    source=meta.get("source") or "",
                )
            )
            continue
        try:
            c = fn(meta)
        except Exception as e:
            c = card(
                item_id=iid,
                title=meta.get("title") or iid,
                category=meta.get("category") or "",
                level="warn",
                summary=f"評価エラー: {e}",
                cursor_prompt=meta.get("cursor_prompt") or "",
                source=meta.get("source") or "",
            )
        if meta.get("never_archive"):
            c["status"] = "active"
            c.pop("archived_at", None)
            pl = c.get("payload") if isinstance(c.get("payload"), dict) else {}
            pl = dict(pl)
            pl["never_archive"] = True
            c["payload"] = pl
            if iid in archived_map:
                del archived_map[iid]
                archive["archived"] = archived_map
                save_archive(archive)
        else:
            arch = archived_map.get(iid)
            if arch:
                c["status"] = "archived"
                c["archived_at"] = arch.get("archived_at")
            else:
                c["status"] = "active"
        items_out.append(c)

    active = [i for i in items_out if i.get("status") == "active"]
    popup = [i for i in active if i.get("level") in popup_levels]
    return {
        "updated_at": now_iso(),
        "registry": str(YAML_PATH.relative_to(REPO)),
        "counts": {
            "total": len(items_out),
            "active": len(active),
            "archived": len(items_out) - len(active),
            "popup": len(popup),
            "attention": sum(1 for i in active if i.get("level") == "attention"),
            "warn": sum(1 for i in active if i.get("level") == "warn"),
            "ok": sum(1 for i in active if i.get("level") == "ok"),
        },
        "popup_item_ids": [i["id"] for i in popup],
        "items": items_out,
    }


def registry_meta_by_id(item_id: str) -> dict[str, Any] | None:
    for meta in (load_registry().get("items") or []):
        if meta.get("id") == item_id:
            return meta
    return None


def archive_item(item_id: str) -> bool:
    meta = registry_meta_by_id(item_id)
    if meta and meta.get("never_archive"):
        print(f"# refuse archive (never_archive): {item_id}", file=sys.stderr)
        return False
    data = load_archive()
    data.setdefault("archived", {})[item_id] = {"archived_at": now_iso()}
    save_archive(data)
    return True


def unarchive_item(item_id: str) -> bool:
    data = load_archive()
    arch = data.get("archived") or {}
    if item_id not in arch:
        return False
    del arch[item_id]
    data["archived"] = arch
    save_archive(data)
    return True


def write_result(result: dict[str, Any]) -> Path:
    STATE.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return OUT_PATH


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Jarvis situation watch aggregator")
    ap.add_argument("--json", action="store_true", help="stdout に JSON")
    ap.add_argument("--write", action="store_true", default=True, help="JSON 書き出し（既定）")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--archive", metavar="ID", help="項目をアーカイブ")
    ap.add_argument("--unarchive", metavar="ID", help="アーカイブ解除")
    args = ap.parse_args(argv)

    if args.archive:
        archive_item(args.archive)
        print(f"# archived {args.archive}")
    if args.unarchive:
        unarchive_item(args.unarchive)
        print(f"# unarchived {args.unarchive}")

    result = collect()
    if not args.no_write:
        path = write_result(result)
        print(f"# wrote {path}", file=sys.stderr)
    c = result["counts"]
    print(
        f"# situation watch: active={c['active']} popup={c['popup']} "
        f"attention={c['attention']} warn={c['warn']} ok={c['ok']}",
        file=sys.stderr,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for it in result["items"]:
            if it.get("status") == "archived":
                continue
            print(f"  [{it['level']:9}] {it['title']}: {it['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
