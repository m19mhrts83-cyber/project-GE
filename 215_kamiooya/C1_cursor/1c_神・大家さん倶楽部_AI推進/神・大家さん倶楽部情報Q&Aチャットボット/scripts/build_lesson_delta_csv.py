#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lesson 説明テキストの差分CSV生成。

state ファイル（JSON）にコメントID → コンテンツハッシュを保持し、
新規・更新・削除を判定する。

差分の種別:
  - add: state に無い新規 lesson
  - update: state のハッシュと異なる（テキスト変更）
  - delete: state にあるが今回の full に無い（ページ削除）

出力 CSV には全 LESSON_FIELDNAMES + "差分種別" 列を含む。
削除行は コメント内容="" / 差分種別="delete" で出力し、
取込側で論理削除として扱う。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LESSON_FIELDNAMES = [
    "コメントID",
    "投稿日時",
    "投稿者名",
    "投稿者メール",
    "コメント内容",
    "親コメントID",
    "IP アドレス",
    "ユーザーエージェント",
    "ソース",
    "ソース系統",
    "ソース種別",
    "分類",
    "板タイトル",
    "コースタブ",
    "目次セクション",
    "レッスンタイトル",
    "レッスンURL",
    "コンテンツハッシュ",
]

DELTA_FIELDNAMES = LESSON_FIELDNAMES + ["差分種別"]


def load_state(path: Path) -> dict:
    """state: {"version": 1, "updated_at": ..., "lessons": {"comment_id": "hash", ...}}"""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("lessons") or {}
    except Exception as e:
        print(f"[WARN] state 読込失敗、空で続行: {e}", file=sys.stderr)
        return {}


def save_state(path: Path, lessons: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "lessons": lessons,
    }
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_full_csv(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def build_delta(full_rows: list[dict], state: dict) -> tuple[list[dict], dict]:
    """
    差分を計算し、(delta_rows, new_state) を返す。
    """
    delta: list[dict] = []
    new_state: dict = {}

    current_ids = set()
    for row in full_rows:
        cid = row.get("コメントID", "").strip()
        chash = row.get("コンテンツハッシュ", "").strip()
        if not cid:
            continue
        current_ids.add(cid)
        new_state[cid] = chash

        old_hash = state.get(cid)
        if old_hash is None:
            row_copy = dict(row)
            row_copy["差分種別"] = "add"
            delta.append(row_copy)
        elif old_hash != chash:
            row_copy = dict(row)
            row_copy["差分種別"] = "update"
            delta.append(row_copy)

    for old_cid in state:
        if old_cid not in current_ids:
            delta.append({
                "コメントID": old_cid,
                "投稿日時": datetime.now(timezone.utc).isoformat(),
                "投稿者名": "",
                "投稿者メール": "",
                "コメント内容": "",
                "親コメントID": "",
                "IP アドレス": "",
                "ユーザーエージェント": "",
                "ソース": "WeStudy",
                "ソース系統": "lesson",
                "ソース種別": "lesson_desc",
                "分類": "",
                "板タイトル": "",
                "コースタブ": "",
                "目次セクション": "",
                "レッスンタイトル": "",
                "レッスンURL": "",
                "コンテンツハッシュ": "",
                "差分種別": "delete",
            })

    return delta, new_state


def write_delta_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=DELTA_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="lesson 説明テキストの差分CSV生成")
    parser.add_argument("--full", required=True, help="lesson_full_*.csv のパス")
    parser.add_argument("--state", required=True, help="state JSON のパス")
    parser.add_argument("--delta", required=True, help="出力する差分CSVのパス")
    parser.add_argument("--update-state", action="store_true",
                        help="差分生成後に state を更新")
    parser.add_argument("--init-state-only", action="store_true",
                        help="state 初期化のみ（差分CSVはヘッダのみ）")
    args = parser.parse_args()

    full_path = Path(args.full)
    state_path = Path(args.state)
    delta_path = Path(args.delta)

    if not full_path.exists():
        print(f"全件CSVが見つかりません: {full_path}", file=sys.stderr)
        sys.exit(2)

    full_rows = read_full_csv(full_path)
    print(f"全件CSV: {len(full_rows)} 行", flush=True)

    if args.init_state_only:
        new_state = {}
        for row in full_rows:
            cid = row.get("コメントID", "").strip()
            chash = row.get("コンテンツハッシュ", "").strip()
            if cid:
                new_state[cid] = chash
        save_state(state_path, new_state)
        write_delta_csv([], delta_path)
        print(f"state 初期化完了: {len(new_state)} 件。差分CSVはヘッダのみ。")
        return

    state = load_state(state_path)
    print(f"既知state: {len(state)} 件")

    delta, new_state = build_delta(full_rows, state)

    adds = sum(1 for r in delta if r.get("差分種別") == "add")
    updates = sum(1 for r in delta if r.get("差分種別") == "update")
    deletes = sum(1 for r in delta if r.get("差分種別") == "delete")
    print(f"差分: add={adds} update={updates} delete={deletes} (合計 {len(delta)})")

    write_delta_csv(delta, delta_path)
    print(f"差分CSV出力: {delta_path}")

    if args.update_state:
        save_state(state_path, new_state)
        print(f"state 更新: {len(new_state)} 件")


if __name__ == "__main__":
    main()
