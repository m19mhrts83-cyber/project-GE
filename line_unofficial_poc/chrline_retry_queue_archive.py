#!/usr/bin/env python3
"""
retry キューの exhausted を、削除せず別ファイルへ退避する（既定 --dry-run）。

退避対象（status=exhausted のうち、どちらかを満たすもの）:
  - 書込先MD（route_path）の親フォルダが存在しない
  - 発言日が --older-than-days（既定180）日より前

--apply のときだけ: 元ファイルを日時付きでバックアップ → アーカイブへ追記 → キューから除去。
active（exhausted 以外）は一切触らない。LINE へは接続しない（ファイル操作のみ）。
出力は件数のみ（会話名・フォルダ名・本文は出さない）。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

QUEUE_FILENAME = ".chrline_sync_retry_queue.json"
ARCHIVE_FILENAME = ".chrline_sync_retry_queue.archive.json"


def _load_items(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items", {})
    return {str(k): v for k, v in items.items() if isinstance(v, dict)} if isinstance(items, dict) else {}


def _item_epoch(item: dict) -> float | None:
    ts = item.get("ts")
    try:
        t = float(ts)
        if t > 0:
            return t / 1000.0 if t > 1e11 else t
    except (TypeError, ValueError):
        pass
    try:
        return datetime.strptime(str(item.get("date_part", ""))[:10], "%Y/%m/%d").timestamp()
    except ValueError:
        return None


def classify(item: dict, *, now: float, older_than_days: int) -> str | None:
    """退避理由（'missing_dir' / 'old'）。対象外は None。exhausted 以外は常に None。"""
    if item.get("status") != "exhausted":
        return None
    rp = str(item.get("route_path", ""))
    if not rp or not Path(rp).parent.exists():
        return "missing_dir"
    epoch = _item_epoch(item)
    if epoch is not None and epoch < now - older_than_days * 86400:
        return "old"
    return None


def plan(items: dict[str, dict], *, now: float, older_than_days: int) -> dict[str, str]:
    out: dict[str, str] = {}
    for dk, item in items.items():
        reason = classify(item, now=now, older_than_days=older_than_days)
        if reason:
            out[dk] = reason
    return out


def apply_archive(save_root: Path, targets: dict[str, str], *, now: float) -> tuple[Path, int]:
    """バックアップ→アーカイブ追記→キュー書き戻し。戻り値: (バックアップ先, 退避件数)。"""
    qpath = save_root / QUEUE_FILENAME
    apath = save_root / ARCHIVE_FILENAME
    stamp = datetime.fromtimestamp(now).strftime("%Y%m%d_%H%M%S")
    backup = save_root / f"{QUEUE_FILENAME}.bak_{stamp}"
    shutil.copy2(qpath, backup)
    items = _load_items(qpath)
    archive = _load_items(apath)
    moved = 0
    for dk, reason in targets.items():
        item = items.get(dk)
        if item is None or item.get("status") != "exhausted":
            continue
        rec = dict(item)
        rec["archived_at"] = datetime.fromtimestamp(now).isoformat(timespec="seconds")
        rec["archive_reason"] = reason
        archive[dk] = rec
        moved += 1
    # アーカイブを先に保存（途中で失敗してもキューは減らない）
    apath.write_text(json.dumps({"items": archive}, ensure_ascii=False, indent=2), encoding="utf-8")
    remaining = {k: v for k, v in items.items() if k not in targets or v.get("status") != "exhausted"}
    qpath.write_text(json.dumps({"items": remaining}, ensure_ascii=False, indent=2), encoding="utf-8")
    return backup, moved


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="retry キュー exhausted の退避（既定 dry-run）")
    p.add_argument("--apply", action="store_true", help="実際に退避する（既定は dry-run）")
    p.add_argument("--dry-run", action="store_true", help="件数のみ表示（既定）")
    p.add_argument("--older-than-days", type=int, default=180)
    p.add_argument("--save-root", type=Path, default=None, help="未指定時は LINE_UNOFFICIAL_AUTH_DIR")
    args = p.parse_args(argv)
    if args.apply and args.dry_run:
        p.error("--apply と --dry-run は同時に指定できません")

    if args.save_root:
        root = args.save_root.expanduser().resolve()
    else:
        from chrline_client_utils import save_root_from_env

        root = save_root_from_env()
    qpath = root / QUEUE_FILENAME
    items = _load_items(qpath)
    now = time.time()
    targets = plan(items, now=now, older_than_days=args.older_than_days)
    exhausted = sum(1 for i in items.values() if i.get("status") == "exhausted")
    by_reason = {r: sum(1 for v in targets.values() if v == r) for r in ("missing_dir", "old")}
    print(
        f"queue={len(items)} exhausted={exhausted} 退避対象={len(targets)}"
        f"（書込先フォルダなし {by_reason['missing_dir']} / {args.older_than_days}日超 {by_reason['old']}）"
        f" 残る exhausted={exhausted - len(targets)}"
    )
    if not args.apply:
        print("dry-run: ファイルは変更していません（--apply で実行）")
        return 0
    if not targets:
        print("退避対象なし")
        return 0
    backup, moved = apply_archive(root, targets, now=now)
    print(f"退避 {moved} 件 → {ARCHIVE_FILENAME}（バックアップ: {backup.name}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
