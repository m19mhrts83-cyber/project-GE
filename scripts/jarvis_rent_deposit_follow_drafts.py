#!/usr/bin/env python3
"""家賃入金フォロー — 想定入金が確認できない号室のメール下書き。

月次チェック結果からパートナー別に下書きを作り、専用ファイルへ保存する。
現行の 4.送信下書き.txt は上書きしない（送る直前に --promote で移す）。

  python scripts/jarvis_rent_deposit_follow_drafts.py
  python scripts/jarvis_rent_deposit_follow_drafts.py --from-state
  python scripts/jarvis_rent_deposit_follow_drafts.py --promote ミニテック
  python scripts/jarvis_rent_deposit_follow_drafts.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_DIR = REPO / ".jarvis_state"
STATE_PATH = STATE_DIR / "rent_step_monthly.json"
ONEDRIVE_215 = Path(
    "~/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
).expanduser()
PARTNER = ONEDRIVE_215 / "C2_ルーティン作業" / "26_パートナー社への相談"

DRAFT_NAME = "4.送信下書き_家賃入金フォロー.txt"
SEND_NAME = "4.送信下書き.txt"

MANAGER_FOLDERS = {
    "ミニテック": "102_ミニテック",
    "LEAF": "104_LEAF",
    "ホームプランナー": "101_ホームプランナー",
    "Tcell": "103_Tcell",
}

MANAGER_GREETING = {
    "ミニテック": ("ミニテック大曽根支店", "林 様"),
    "LEAF": ("株式会社LEAF 管理部", "ご担当者様"),
    "ホームプランナー": ("ホームプランナー", "鈴木様"),
    "Tcell": ("Tcell", "ご担当者様"),
}

PROP_LABEL = {
    "grandole-i": "Grandole志賀本通Ⅰ",
    "grandole-ii": "Grandole志賀本通Ⅱ",
    "caramel": "キャラメル",
}

# メール送信できるパートナー（Tcell は LINE のみ → 下書きはメモ用）
EMAIL_PARTNERS = {"ミニテック", "LEAF", "ホームプランナー"}


def now_jst() -> datetime:
    return datetime.now(JST)


def load_state() -> dict[str, Any]:
    if STATE_PATH.is_file():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def fmt_yen(n: int | None) -> str:
    if n is None:
        return "—"
    return f"{n:,}円"


def remittance_ym(target_ym: str) -> str:
    """確認月の直前月を送金対象月の既定にする。"""
    y, m = map(int, target_ym.split("-"))
    if m == 1:
        return f"{y - 1}-12"
    return f"{y}-{m - 1:02d}"


def months_between(earlier_ym: str, later_ym: str) -> int:
    """later - earlier の月数（同じ月なら 0）。"""
    try:
        y1, m1 = map(int, earlier_ym.split("-"))
        y2, m2 = map(int, later_ym.split("-"))
        return (y2 - y1) * 12 + (m2 - m1)
    except ValueError:
        return 0


def item_in_watch(
    item: dict[str, Any],
    *,
    target_ym: str,
    grace_months: int,
) -> bool:
    """様子見中なら True（下書きを書かない）。"""
    if grace_months <= 0:
        return False
    # stale（2ヶ月以上古い明細）は様子見を飛ばして下書き可
    if item.get("kind") == "stale":
        return False
    ref = str(item.get("remittance_ym") or remittance_ym(target_ym))
    age = months_between(ref, target_ym)
    # 確認月が送金月の翌月（age=1）までは様子見。grace=1 → age<=1 は watch
    return age <= grace_months


def collect_follow_items(
    units: list[dict[str, Any]],
    aggregates: list[dict[str, Any]],
    *,
    target_ym: str,
    mismatch_thr: int = 500,
    grace_months: int = 1,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """想定入金が確認できない号室を列挙。(draft_items, watch_items)"""
    rem_ym = remittance_ym(target_ym)
    items: list[dict[str, Any]] = []

    for u in units:
        if u.get("status") != "occupied":
            continue
        mgr = u.get("manager") or ""
        if not mgr:
            continue

        if mgr == "ミニテック" and u.get("deposit_flag") == "deposit_missing":
            items.append(
                {
                    "kind": "missing",
                    "priority": 1,
                    "manager": mgr,
                    "id": u.get("id"),
                    "label": u.get("label"),
                    "property_id": u.get("property_id"),
                    "room": u.get("room"),
                    "book_rent": u.get("book_rent"),
                    "expected_rent": u.get("expected_rent") or u.get("book_rent"),
                    "observed_deposit": None,
                    "deposit_ym": None,
                    "gap_yen": None,
                    "remittance_ym": rem_ym,
                    "reason": "オーナーサイトの送金案内（PDF）が当方で確認できない",
                    "channel": "email",
                }
            )
            continue

        if u.get("flag") == "deposit_mismatch" or u.get("deposit_flag") == "deposit_mismatch":
            gap = u.get("deposit_gap_yen")
            if gap is None and u.get("observed_deposit") is not None:
                exp = u.get("expected_rent") or u.get("book_rent")
                if exp is not None:
                    gap = int(u["observed_deposit"]) - int(exp)
            gap = int(gap or 0)
            under = gap <= -mismatch_thr
            minitech_any = mgr == "ミニテック" and abs(gap) >= mismatch_thr
            if under or minitech_any:
                items.append(
                    {
                        "kind": "mismatch",
                        "priority": 1 if mgr == "ミニテック" and under else 2,
                        "manager": mgr,
                        "id": u.get("id"),
                        "label": u.get("label"),
                        "property_id": u.get("property_id"),
                        "room": u.get("room"),
                        "book_rent": u.get("book_rent"),
                        "expected_rent": u.get("expected_rent") or u.get("book_rent"),
                        "observed_deposit": u.get("observed_deposit"),
                        "deposit_ym": u.get("deposit_ym"),
                        "gap_yen": gap,
                        "remittance_ym": u.get("deposit_ym") or rem_ym,
                        "reason": u.get("reason") or f"入金差 {gap:+,}円",
                        "channel": "email" if mgr in EMAIL_PARTNERS else "line_note",
                    }
                )
                continue

        if mgr == "ミニテック" and u.get("deposit_ym"):
            try:
                dy, dm = map(int, str(u["deposit_ym"]).split("-"))
                ty, tm = map(int, rem_ym.split("-"))
                age = (ty - dy) * 12 + (tm - dm)
                if age >= 2 and u.get("observed_deposit") is not None:
                    items.append(
                        {
                            "kind": "stale",
                            "priority": 1,
                            "manager": mgr,
                            "id": u.get("id"),
                            "label": u.get("label"),
                            "property_id": u.get("property_id"),
                            "room": u.get("room"),
                            "book_rent": u.get("book_rent"),
                            "expected_rent": u.get("expected_rent") or u.get("book_rent"),
                            "observed_deposit": u.get("observed_deposit"),
                            "deposit_ym": u.get("deposit_ym"),
                            "gap_yen": None,
                            "remittance_ym": rem_ym,
                            "reason": f"最新明細が {u.get('deposit_ym')} で古い（{rem_ym}分を確認したい）",
                            "channel": "email",
                        }
                    )
            except ValueError:
                pass

    for a in aggregates:
        if a.get("flag") not in ("needs_memo", "missing_bank"):
            continue
        group = str(a.get("group") or "")
        mgr = {
            "hp": "ホームプランナー",
            "leaf": "LEAF",
            "tcell": "Tcell",
        }.get(group, "")
        if not mgr:
            continue
        items.append(
            {
                "kind": "aggregate",
                "priority": 2,
                "manager": mgr,
                "id": f"agg:{group}:{a.get('property_id')}",
                "label": a.get("title"),
                "property_id": a.get("property_id"),
                "room": None,
                "book_rent": a.get("book_rent_sum"),
                "expected_rent": a.get("book_rent_sum"),
                "observed_deposit": a.get("observed_yen"),
                "deposit_ym": a.get("observed_ym"),
                "gap_yen": a.get("gap_yen"),
                "remittance_ym": a.get("observed_ym") or rem_ym,
                "reason": f"口座合算の差 {a.get('gap_yen')}（メモキー {a.get('memo_key')}）",
                "channel": "email" if mgr in EMAIL_PARTNERS else "line_note",
                "rooms": a.get("rooms") or [],
            }
        )

    items.sort(key=lambda x: (x.get("priority", 9), x.get("manager") or "", x.get("label") or ""))
    draft_items: list[dict[str, Any]] = []
    watch_items: list[dict[str, Any]] = []
    for it in items:
        watching = item_in_watch(it, target_ym=target_ym, grace_months=grace_months)
        it = {**it, "watch": watching}
        if watching:
            watch_items.append(it)
        else:
            draft_items.append(it)
    return draft_items, watch_items


def property_title(items: list[dict[str, Any]]) -> str:
    pids = {i.get("property_id") for i in items if i.get("property_id")}
    labels = [PROP_LABEL.get(str(p), str(p)) for p in sorted(pids) if p]
    if not labels:
        return "Grandole"
    if len(labels) == 1:
        return labels[0]
    return "／".join(labels)


def build_email_body(
    manager: str,
    items: list[dict[str, Any]],
    *,
    target_ym: str,
) -> tuple[str, str]:
    """件名・本文（1行目=件名の yoritoori 形式）。"""
    org, honorific = MANAGER_GREETING.get(manager, (manager, "ご担当者様"))
    prop = property_title(items)
    rem_set = sorted({str(i.get("remittance_ym") or "") for i in items if i.get("remittance_ym")})
    rem_label = "・".join(rem_set) if rem_set else remittance_ym(target_ym)

    subject = f"【{prop}】家賃送金・明細の確認のお願い（{rem_label}分）"

    lines: list[str] = [
        f"件名：{subject}",
        "",
        org,
        honorific,
        "",
        "お世話になっております。",
        f"{prop}オーナーの松野です。",
        "",
        f"オーナー向けの送金明細等を突合したところ、下記号室について"
        f"{rem_label}分の想定入金（または送金案内）が当方で確認できておりません。",
        "お手数ですが、送金状況・明細のご確認をお願いできますでしょうか。",
        "",
        "■ 確認したい号室",
    ]

    for i in items:
        label = i.get("label") or "—"
        kind = i.get("kind")
        if kind == "missing":
            detail = (
                f"・{label}: 送金案内（PDF）未確認"
                f"（帳簿家賃 {fmt_yen(i.get('book_rent'))}）"
            )
        elif kind == "stale":
            detail = (
                f"・{label}: 最新明細 {i.get('deposit_ym')} が古く、"
                f"{i.get('remittance_ym')}分の確認を希望"
                f"（直近観測 {fmt_yen(i.get('observed_deposit'))}／帳簿 {fmt_yen(i.get('book_rent'))}）"
            )
        elif kind == "aggregate":
            rooms = "、".join(i.get("rooms") or []) or "該当号室"
            detail = (
                f"・合算（{rooms}）: 口座着金 {fmt_yen(i.get('observed_deposit'))}"
                f" / 帳簿合計 {fmt_yen(i.get('book_rent'))}"
                f"（差 {i.get('gap_yen')}）"
            )
        else:
            detail = (
                f"・{label}: 明細上の家賃 {fmt_yen(i.get('observed_deposit'))}"
                f" / 想定 {fmt_yen(i.get('expected_rent') or i.get('book_rent'))}"
                f"（差 {i.get('gap_yen'):+,}円）"
                if i.get("gap_yen") is not None
                else f"・{label}: {i.get('reason')}"
            )
        lines.append(detail)

    lines.extend(
        [
            "",
            "■ お願いしたいこと",
            "1. 上記号室の送金有無・送金日・金額",
            "2. 差額がある場合はその理由（フリーレント・キャンペーン・未納・差引項目等）",
            "3. 可能であれば、該当月の送金案内（PDF等）のご共有",
            "",
            "行き違い・既にご対応済みでしたらご容赦ください。",
            "お忙しいところ恐縮ですが、ご確認のほどよろしくお願いいたします。",
            "",
            "松野（090-9670-7595）",
            "",
        ]
    )
    return subject, "\n".join(lines)


def build_line_note(
    manager: str,
    items: list[dict[str, Any]],
    *,
    target_ym: str,
) -> str:
    """Tcell などメール無し向けの確認メモ。"""
    rem = remittance_ym(target_ym)
    lines = [
        f"【LINE確認メモ・送信しない】{manager} 家賃入金フォロー（{target_ym}確認／{rem}分）",
        "",
        "メール連絡先が無いため LINE で確認する想定の下書きです。",
        "",
    ]
    for i in items:
        lines.append(f"・{i.get('label')}: {i.get('reason')}")
    lines.extend(["", "松野"])
    return "\n".join(lines) + "\n"


def write_partner_draft(
    manager: str,
    text: str,
    *,
    dry_run: bool,
) -> Path | None:
    folder = MANAGER_FOLDERS.get(manager)
    if not folder:
        return None
    path = PARTNER / folder / DRAFT_NAME
    if dry_run:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def promote_draft(manager: str, *, dry_run: bool = False) -> dict[str, Any]:
    """専用下書き → 4.送信下書き.txt（現行はバックアップ）。"""
    folder = MANAGER_FOLDERS.get(manager)
    if not folder:
        return {"ok": False, "error": f"unknown manager: {manager}"}
    src = PARTNER / folder / DRAFT_NAME
    dst = PARTNER / folder / SEND_NAME
    if not src.is_file():
        return {"ok": False, "error": f"下書きなし: {src}"}
    backup = None
    if dst.is_file() and dst.read_text(encoding="utf-8").strip():
        stamp = now_jst().strftime("%Y%m%d-%H%M%S")
        backup = PARTNER / folder / f"4.送信下書き.bak.{stamp}.txt"
        if not dry_run:
            shutil.copy2(dst, backup)
    if not dry_run:
        shutil.copy2(src, dst)
    return {
        "ok": True,
        "manager": manager,
        "src": str(src),
        "dst": str(dst),
        "backup": str(backup) if backup else None,
        "dry_run": dry_run,
    }


def run_from_result(
    result: dict[str, Any],
    *,
    dry_run: bool = False,
    write_files: bool = True,
) -> dict[str, Any]:
    target_ym = str(result.get("target_month") or now_jst().strftime("%Y-%m"))
    grace_months = int(result.get("deposit_follow_grace_months") or 1)
    units = [u for u in (result.get("units") or []) if isinstance(u, dict)]
    aggregates = [a for a in (result.get("aggregates") or []) if isinstance(a, dict)]
    draft_items, watch_items = collect_follow_items(
        units,
        aggregates,
        target_ym=target_ym,
        grace_months=grace_months,
    )

    by_mgr: dict[str, list[dict[str, Any]]] = {}
    for it in draft_items:
        by_mgr.setdefault(str(it["manager"]), []).append(it)

    drafts: list[dict[str, Any]] = []
    for mgr, mgr_items in sorted(
        by_mgr.items(), key=lambda x: (0 if x[0] == "ミニテック" else 1, x[0])
    ):
        channel = "email" if mgr in EMAIL_PARTNERS else "line_note"
        if channel == "email":
            subject, body = build_email_body(mgr, mgr_items, target_ym=target_ym)
            text = body if body.endswith("\n") else body + "\n"
        else:
            subject = f"【LINEメモ】{mgr} 家賃入金フォロー"
            text = build_line_note(mgr, mgr_items, target_ym=target_ym)

        path = None
        if write_files:
            path = write_partner_draft(mgr, text, dry_run=dry_run)

        drafts.append(
            {
                "manager": mgr,
                "folder": MANAGER_FOLDERS.get(mgr),
                "channel": channel,
                "status": "draft_ready",
                "subject": subject,
                "item_count": len(mgr_items),
                "items": mgr_items,
                "draft_path": str(path) if path else None,
                "send_path": str(PARTNER / MANAGER_FOLDERS[mgr] / SEND_NAME)
                if mgr in MANAGER_FOLDERS
                else None,
                "promote_hint": f"python scripts/jarvis_rent_deposit_follow_drafts.py --promote {mgr}",
                "preview": "\n".join(text.splitlines()[:16]),
                "written": bool(write_files and not dry_run and path),
            }
        )

    watching = [
        {
            "label": i.get("label"),
            "manager": i.get("manager"),
            "kind": i.get("kind"),
            "reason": i.get("reason"),
            "remittance_ym": i.get("remittance_ym"),
            "watch": True,
        }
        for i in watch_items
    ]

    return {
        "at": now_jst().isoformat(timespec="seconds"),
        "target_month": target_ym,
        "grace_months": grace_months,
        "follow_count": len(draft_items) + len(watch_items),
        "draft_count": len(drafts),
        "watch_count": len(watch_items),
        "items": draft_items + watch_items,
        "drafts": drafts,
        "watching": watching,
    }


def print_block(out: dict[str, Any]) -> None:
    print("---")
    print(f"📎 家賃入金フォロー — {out.get('target_month')}")
    print(
        f"- 対象: {out.get('follow_count', 0)}"
        f" · 様子見中: {out.get('watch_count', 0)}"
        f" · 下書き可: {out.get('draft_count', 0)}"
        f"（猶予 {out.get('grace_months', 1)}ヶ月）"
    )
    for w in out.get("watching") or []:
        print(
            f"  …様子見 {w.get('manager')} {w.get('label')}: {w.get('reason')}"
            f" [{w.get('remittance_ym')}]"
        )
    if not out.get("drafts"):
        if not out.get("watching"):
            print("- 想定入金は確認できています（フォローなし）")
        else:
            print("- 様子見中のため下書きはまだ作りません")
        print("---")
        return
    for d in out.get("drafts") or []:
        ch = "メール" if d.get("channel") == "email" else "LINEメモ"
        print(f"  · {d.get('manager')}（{ch}）{d.get('item_count')}件")
        print(f"    件名: {d.get('subject')}")
        if d.get("draft_path"):
            print(f"    保存: {d.get('draft_path')}")
        print(f"    送信準備: {d.get('promote_hint')}")
        for it in d.get("items") or []:
            print(f"      - {it.get('label')}: {it.get('reason')}")
    print("- 送信は yoritoori_send（要確認）。専用下書きを --promote してから送る")
    print("---")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-state", action="store_true", help="rent_step_monthly.json から生成")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--promote", metavar="MANAGER", help="専用下書きを 4.送信下書き.txt へ移す")
    ap.add_argument("--no-write", action="store_true", help="ファイル保存せず state 更新のみ")
    args = ap.parse_args()

    if args.promote:
        res = promote_draft(args.promote, dry_run=args.dry_run)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res.get("ok") else 1

    state = load_state()
    result = state.get("last_result") or {}
    if not result.get("units"):
        print(
            "# no rent_step last_result — run jarvis_rent_step_monthly_check.py first",
            file=__import__("sys").stderr,
        )
        return 1

    out = run_from_result(
        result,
        dry_run=args.dry_run,
        write_files=not args.no_write,
    )
    state["follow_drafts"] = out
    if not args.dry_run:
        lr = dict(state.get("last_result") or {})
        lr["follow_drafts"] = {
            "follow_count": out["follow_count"],
            "draft_count": out["draft_count"],
            "watch_count": out["watch_count"],
            "watching": out.get("watching") or [],
            "drafts": [
                {
                    "manager": d["manager"],
                    "channel": d["channel"],
                    "status": d.get("status"),
                    "subject": d["subject"],
                    "item_count": d["item_count"],
                    "draft_path": d["draft_path"],
                    "send_path": d["send_path"],
                    "promote_hint": d["promote_hint"],
                    "preview": d["preview"],
                    "items": [
                        {
                            "label": i.get("label"),
                            "kind": i.get("kind"),
                            "reason": i.get("reason"),
                            "gap_yen": i.get("gap_yen"),
                            "watch": i.get("watch"),
                        }
                        for i in (d.get("items") or [])
                    ],
                }
                for d in out["drafts"]
            ],
        }
        state["last_result"] = lr
        save_state(state)

    print_block(out)
    return 0 if out.get("draft_count", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
