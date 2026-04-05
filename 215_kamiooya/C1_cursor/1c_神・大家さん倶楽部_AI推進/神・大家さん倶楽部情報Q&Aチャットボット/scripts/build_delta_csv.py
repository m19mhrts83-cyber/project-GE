#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
管理者形式の「全件CSV」と state（既知のコメントID集合）を比較し、
未登録分だけの差分CSVを出力する。

state ファイル: JSON
  { "version": 1, "updated_at": "...", "comment_ids": ["24148", ...] }

ポリシー:
  - 差分行 = 全件CSVにあって state に無い コメントID
  - --update-state 指定時: state := state | 今回の全件のID（単調増加。削除はしない）
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ADMIN_FIELDNAMES = [
    "コメントID",
    "投稿日時",
    "投稿者名",
    "投稿者メール",
    "コメント内容",
    "親コメントID",
    "IP アドレス",
    "ユーザーエージェント",
]


def load_state(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        ids = data.get("comment_ids") or []
        return {str(x).strip() for x in ids if str(x).strip()}
    except Exception as e:
        print(f"[WARN] state 読込失敗、空集合で続行: {e}", file=sys.stderr)
        return set()


def save_state(path: Path, ids: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "comment_ids": sorted(ids, key=lambda x: (len(x), x)),
    }
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def read_full_rows(full_csv: Path) -> list[dict]:
    rows = []
    with full_csv.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames:
            for h in ADMIN_FIELDNAMES:
                if h not in reader.fieldnames:
                    print(
                        f"エラー: 全件CSVに列「{h}」がありません。convert_to_admin_csv.py の出力を渡してください。",
                        file=sys.stderr,
                    )
                    sys.exit(2)
        for row in reader:
            cid = (row.get("コメントID") or "").strip()
            if cid:
                rows.append(row)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="管理者形式全件CSVから差分CSVを生成")
    ap.add_argument("--full", required=True, help="管理者形式の全件CSV")
    ap.add_argument(
        "--state",
        required=True,
        help="既知コメントIDの JSON（comment_ids）",
    )
    ap.add_argument("--delta", required=True, help="差分CSVの出力先")
    ap.add_argument(
        "--update-state",
        action="store_true",
        help="処理後に state を更新（全件のIDをマージ）",
    )
    ap.add_argument(
        "--init-state-only",
        action="store_true",
        help="全件のIDだけ state に記録し、差分CSVはヘッダのみ（初回DB登録済みのとき等）",
    )
    args = ap.parse_args()

    full_path = Path(args.full).expanduser().resolve()
    state_path = Path(args.state).expanduser().resolve()
    delta_path = Path(args.delta).expanduser().resolve()

    if not full_path.is_file():
        print(f"全件CSVがありません: {full_path}", file=sys.stderr)
        return 2

    rows = read_full_rows(full_path)
    all_ids = {r["コメントID"].strip() for r in rows}
    known = load_state(state_path)

    if args.init_state_only:
        save_state(state_path, all_ids | known)
        delta_path.parent.mkdir(parents=True, exist_ok=True)
        with delta_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(
                f,
                fieldnames=ADMIN_FIELDNAMES,
                lineterminator="\n",
            )
            w.writeheader()
        print(
            f"OK: state 初期化 {state_path} （{len(all_ids | known)} ID）差分は空: {delta_path}"
        )
        return 0

    new_ids = all_ids - known
    delta_rows = [r for r in rows if r["コメントID"].strip() in new_ids]

    delta_path.parent.mkdir(parents=True, exist_ok=True)
    with delta_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=ADMIN_FIELDNAMES,
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\n",
        )
        w.writeheader()
        for r in delta_rows:
            w.writerow({k: r.get(k, "") for k in ADMIN_FIELDNAMES})

    if args.update_state:
        save_state(state_path, known | all_ids)

    print(
        f"OK: 差分 {len(delta_rows)} 行 / 全件 {len(rows)} 行 / 新ID {len(new_ids)} "
        f"→ {delta_path}"
        + (f" | state 更新済み ({len(known | all_ids)} ID)" if args.update_state else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
