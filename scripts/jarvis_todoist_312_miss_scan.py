#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""312 ループB — 拾い漏れ候補（多ソース・提案のみ）.

材料: パートナーやり取り末尾 / Obsidian Journal 直近見出し / Slack は別途.
結果は state と任意で task_loop_misses（Supabase）へ。

  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_312_miss_scan.py
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
JST = ZoneInfo("Asia/Tokyo")
STATE = REPO / ".jarvis_state" / "todoist_312_miss_scan.json"
PARTNERS = Path(
    "/Users/matsunomasaharu2/Library/CloudStorage/OneDrive-個人用/"
    "215_神・大家さん倶楽部/C2_ルーティン作業/26_パートナー社への相談"
)
JOURNAL = Path.home() / "Documents/500_Obsidian_r1/01_Journaling/★Journal"
SIGNAL_RE = re.compile(
    r"(要確認|ご確認ください|見積|退去|修繕|折り返し|返信ください|資料提出|未提出)",
    re.I,
)
NOISE_RE = re.compile(r"^(何卒|引き続き)?よろしくお願い", re.I)


def scan_yoritoori(limit: int = 20) -> list[dict]:
    out: list[dict] = []
    if not PARTNERS.is_dir():
        return out
    files = sorted(
        PARTNERS.glob("P*/5.やり取り.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for md in files[:limit]:
        try:
            lines = md.read_text(encoding="utf-8", errors="replace").splitlines()[-60:]
        except OSError:
            continue
        blob = "\n".join(lines)
        if not SIGNAL_RE.search(blob):
            continue
        # 815 除外
        if "815_" in md.parent.name or "神大家オプチャ" in md.parent.name:
            continue
        snippet = next(
            (
                ln
                for ln in reversed(lines)
                if SIGNAL_RE.search(ln) and not NOISE_RE.search(ln.strip())
            ),
            "",
        )[:120]
        if not snippet:
            continue
        out.append({
            "source": "yoritoori",
            "ref": str(md),
            "folder": md.parent.name,
            "snippet": snippet,
            "hypothesis": "やり取りに宿題サイン。Todoist未起票の可能性",
        })
    return out


def scan_journal(days: int = 3) -> list[dict]:
    out: list[dict] = []
    if not JOURNAL.is_dir():
        return out
    today = datetime.now(JST).date()
    for i in range(days):
        d = today - timedelta(days=i)
        # YYYY-MM/YYYY-MM-DD.md
        p = JOURNAL / f"{d:%Y-%m}" / f"{d:%Y-%m-%d}.md"
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not re.search(r"(タスク|Todoist|宿題|要対応|返事)", text):
            continue
        out.append({
            "source": "obsidian_journal",
            "ref": str(p),
            "folder": p.name,
            "snippet": text[:200].replace("\n", " "),
            "hypothesis": "Journal に宿題言及。拾い漏れ確認",
        })
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    cands = scan_yoritoori() + scan_journal()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "at": datetime.now(JST).isoformat(timespec="seconds"),
        "candidates": cands,
    }
    STATE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"📎 312 拾い漏れ候補: {len(cands)} 件（提案のみ・createしない）")
    for i, c in enumerate(cands[:15], start=1):
        print(f"  #{i} [{c['source']}] {c.get('folder','')} — {c.get('snippet','')[:60]}")
    print("判定は loopware /312 漏れ確認タブ、または Chat で「漏れ／漏れではない」")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
