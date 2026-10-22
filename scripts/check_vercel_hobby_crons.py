#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hobby 向け: apps/*/vercel.json の Cron が日次超えていないか検査する。

Vercel Hobby は Cron が **1日1回まで**。`*/5 * * * *` などを入れると
Production / Preview デプロイ自体が失敗する（2026-10-22 · PR #127→#128）。

  python scripts/check_vercel_hobby_crons.py
  python scripts/check_vercel_hobby_crons.py --root apps

終了コード: 0=OK / 1=違反あり
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# 分・時が「単一の固定値」だけなら 1日1回（または週次等でそれ以下）になりやすい
_SINGLE_NUM = re.compile(r"^\d{1,2}$")


def _field_ok_for_hobby(field: str, *, allow_star_dow_dom_mon: bool) -> bool:
    f = (field or "").strip()
    if not f:
        return False
    if allow_star_dow_dom_mon and f in ("*", "?"):
        return True
    # リスト・範囲・ステップは Hobby で日次超過しやすいので拒否
    if any(ch in f for ch in (",", "-", "/")):
        return False
    return bool(_SINGLE_NUM.match(f))


def schedule_ok_for_hobby(schedule: str) -> tuple[bool, str]:
    """Hobby で許容しうるか。厳しめ: 分・時は単一数字のみ。"""
    parts = (schedule or "").strip().split()
    if len(parts) != 5:
        return False, f"cron は5フィールド必須（得た: {len(parts)}）: {schedule!r}"
    minute, hour, dom, month, dow = parts
    if not _field_ok_for_hobby(minute, allow_star_dow_dom_mon=False):
        return False, f"分フィールドが Hobby 非対応（単一数字のみ可）: {schedule!r}"
    if not _field_ok_for_hobby(hour, allow_star_dow_dom_mon=False):
        return False, f"時フィールドが Hobby 非対応（単一数字のみ可）: {schedule!r}"
    for label, field in (("日", dom), ("月", month), ("曜", dow)):
        if not _field_ok_for_hobby(field, allow_star_dow_dom_mon=True):
            return False, f"{label}フィールドが Hobby 非対応: {schedule!r}"
    return True, "ok"


def iter_vercel_json(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(root.rglob("vercel.json"))


def check_file(path: Path) -> list[str]:
    errs: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path}: JSON 読取失敗: {exc}"]
    crons = data.get("crons")
    if not crons:
        return []
    if not isinstance(crons, list):
        return [f"{path}: crons は配列である必要がある"]
    for i, entry in enumerate(crons):
        if not isinstance(entry, dict):
            errs.append(f"{path}: crons[{i}] がオブジェクトでない")
            continue
        sched = str(entry.get("schedule") or "")
        ok, reason = schedule_ok_for_hobby(sched)
        if not ok:
            path_api = entry.get("path") or "?"
            errs.append(
                f"{path}: Hobby 不可の Cron schedule={sched!r} path={path_api} — {reason}. "
                "5分間隔などは GHA schedule か launchd へ（Vercel Cron に載せない）"
            )
    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--root",
        default=str(REPO / "apps"),
        help="vercel.json を探すルート（既定: apps）",
    )
    args = ap.parse_args()
    root = Path(args.root)
    if not root.is_absolute():
        root = REPO / root

    files = iter_vercel_json(root)
    if not files:
        print(f"# no vercel.json under {root}")
        return 0

    all_errs: list[str] = []
    for p in files:
        all_errs.extend(check_file(p))

    if all_errs:
        print("Hobby Vercel Cron 検査 NG:")
        for e in all_errs:
            print(f"  - {e}")
        return 1

    print(f"Hobby Vercel Cron 検査 OK（{len(files)} files, no disallowed crons）")
    for p in files:
        rel = p.relative_to(REPO) if p.is_relative_to(REPO) else p
        print(f"  - {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
