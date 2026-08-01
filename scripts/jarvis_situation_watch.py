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
) -> dict[str, Any]:
    return {
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
    parts = []
    if rebate is not None:
        parts.append(f"{target or '前月'}分還元 {rebate:,}円" if isinstance(rebate, int) else f"還元 {rebate}")
    level = "ok"
    if 1 <= day <= 8 and a != ym:
        level = "warn"
        parts.append(f"ウィンドウA未実施（{ym}）")
    if 19 <= day <= 26 and b != ym:
        level = "attention"
        parts.append(f"ウィンドウB未実施（{ym}）")
    if not parts:
        parts.append(f"B最終 {b or '—'} / A最終 {a or '—'}")
    return card(
        item_id=meta["id"],
        title=title,
        category=meta.get("category") or "",
        level=level,
        summary=" · ".join(parts),
        detail=str(rb.get("note") or "")[:400],
        cursor_prompt=prompt,
        source=src,
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
    rc = (mon.get("last_result_c") or {})
    parts = []
    if bal is not None:
        parts.append(f"残高 {bal:,}pt" if isinstance(bal, int) else f"残高 {bal}")
    if actions:
        parts.append(f"open_actions {len(actions)}件")
    note = str(rc.get("note") or "")
    if note:
        parts.append(note[:80])
    level = "ok"
    if actions:
        level = "warn"
    if rc.get("ok") is False:
        level = "attention"
    if not parts:
        parts.append("データなし")
        level = "warn"
    return card(
        item_id=meta["id"],
        title=title,
        category=meta.get("category") or "",
        level=level,
        summary=" · ".join(parts),
        detail="; ".join(a.get("title") or "" for a in actions[:4]),
        cursor_prompt=prompt,
        source=src,
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
    follow = []
    for k, v in cl.items():
        st = str((v or {}).get("status") or "")
        if st in ("ok", "ok_user_confirmed", "ordered"):
            continue
        follow.append(f"{k}={st}")
    level = "ok" if not follow else "warn"
    if any("id_dominant" in f or "1pct" in f or "confirm" in f for f in follow):
        level = "warn"
    return card(
        item_id=meta["id"],
        title=title,
        category=meta.get("category") or "",
        level=level,
        summary=f"要フォロー {len(follow)}/{len(cl)}" if follow else f"チェック {len(cl)} 項目OK寄り",
        detail="; ".join(follow[:8]),
        cursor_prompt=prompt,
        source=src,
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


EVALUATORS = {
    "etc_mileage": lambda m: eval_etc(m, load_json(STATE / "etc_monthly.json")),
    "vpoint": lambda m: eval_vpoint(m),
    "line_export": lambda m: eval_line_export(m, load_json(STATE / "line_export_reminder.json")),
    "energy_cf": lambda m: eval_energy_cf(m, load_json(STATE / "energy_cf.json")),
    "westudy_weekly": lambda m: eval_westudy(m, load_json(STATE / "westudy_weekly_watch.json")),
    "openchat_threads": lambda m: eval_openchat(m),
    "square_probe": lambda m: eval_square(m, load_json(STATE / "square_probe.json")),
    "chrline_version": lambda m: eval_chrline(m, load_json(STATE / "chrline_version.json")),
    "car_loan": lambda m: eval_car_loan(m, load_json(STATE / "car_loan.json")),
    "sbi_vpoint_up": lambda m: eval_sbi(m, load_json(STATE / "sbi_vpoint_up_checklist.json")),
    "night_triage": lambda m: eval_night_triage(m, load_json(STATE / "night_triage" / "queue.json")),
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


def archive_item(item_id: str) -> bool:
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
