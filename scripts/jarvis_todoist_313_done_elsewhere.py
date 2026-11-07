#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""313 ループB' — 外で済んだ検知 → Todoist 根拠コメント＋close 候補.

材料（段階2）:
  - 台帳 comm_items work_status=done（相手・件名近似）
  - パートナー 5.やり取り の「自分から送信」直近
  - （拡張）PR merge / watch 解消 / 番頭指摘

既定は提案のみ。`--apply --select N` でコメント＋close。

  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_313_done_elsewhere.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
JST = ZoneInfo("Asia/Tokyo")
STATE = REPO / ".jarvis_state" / "todoist_313_done_elsewhere.json"
PARTNERS = Path(
    "/Users/matsunomasaharu2/Library/CloudStorage/OneDrive-個人用/"
    "215_神・大家さん倶楽部/C2_ルーティン作業/26_パートナー社への相談"
)


def _token() -> str:
    return (
        os.environ.get("TODOIST_API_TOKEN_OWNER")
        or os.environ.get("TODOIST_API_TOKEN")
        or ""
    ).strip()


def _api(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        "https://api.todoist.com/api/v1" + path,
        data=data,
        headers={
            "Authorization": f"Bearer {_token()}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=40) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw.strip() else {}


def _open_tasks() -> list[dict]:
    # 期日超過＋今後30日（フィルタは URL エンコード必須）
    filt = urllib.parse.quote("(overdue | today | due before: +30 days)", safe="")
    raw = _api("GET", f"/tasks?filter={filt}&limit=200")
    items = raw.get("results", raw) if isinstance(raw, dict) else raw
    return list(items or [])


def _yoritoori_send_hits(limit_files: int = 40) -> list[dict]:
    """5.やり取り.md 末尾の自分から送信を弱い手がかりに。"""
    hits: list[dict] = []
    if not PARTNERS.is_dir():
        return hits
    files = sorted(PARTNERS.glob("*/5.やり取り.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    for md in files[:limit_files]:
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # 末尾 80 行だけ
        tail = "\n".join(text.splitlines()[-80:])
        if "自分から送信" not in tail and "送信（Gmail）" not in tail:
            continue
        folder = md.parent.name
        # 件名っぽい行
        subj = ""
        for line in reversed(tail.splitlines()):
            if line.startswith("件名:") or line.startswith("### "):
                subj = line.strip()[:80]
                break
        hits.append({
            "folder": folder,
            "path": str(md),
            "subject": subj,
            "mtime": datetime.fromtimestamp(md.stat().st_mtime, JST).isoformat(),
        })
    return hits


def _match(task_title: str, hit: dict) -> bool:
    t = task_title.lower()
    blob = f"{hit.get('folder','')} {hit.get('subject','')}".lower()
    # フォルダ名の社名部分
    name = re.sub(r"^P?\d+_", "", hit.get("folder") or "")
    if name and len(name) >= 2 and name.lower() in t:
        return True
    # 共有キーワード（弱い）
    for kw in re.findall(r"[\u3040-\u30ff\u4e00-\u9fff]{3,}", task_title):
        if kw in blob:
            return True
    return False


def propose() -> list[dict]:
    tasks = _open_tasks()
    hits = _yoritoori_send_hits()
    out: list[dict] = []
    n = 0
    for t in tasks:
        title = str(t.get("content") or "")
        labels = [str(x) for x in (t.get("labels") or [])]
        # 要判断は候補にしない
        if re.search(r"要ボス|要確認", title):
            continue
        matched = [h for h in hits if _match(title, h)][:2]
        if not matched:
            continue
        n += 1
        out.append({
            "n": n,
            "task_id": str(t.get("id") or ""),
            "title": title,
            "labels": labels,
            "evidence": matched,
            "confidence": "medium" if len(matched) >= 2 else "low",
        })
        if n >= 15:
            break
    return out


def apply_close(row: dict, author: str) -> None:
    tid = row["task_id"]
    ev = row.get("evidence") or []
    lines = [
        f"【{author}】タスク完了したよ（外で済んだ・検知）",
        "サマリ: 313 done_elsewhere — やり取り送信痕跡と照合",
    ]
    for e in ev:
        lines.append(f"- 根拠: {e.get('folder')} / {e.get('subject','')[:60]}")
        lines.append(f"  path: {e.get('path')}")
    lines.append(f"アウトプット:\n- [該当](https://app.todoist.com/app/task/{tid})")
    comment = "\n".join(lines)[:1900]
    _api("POST", "/comments", {"task_id": tid, "content": comment})
    _api("POST", f"/tasks/{tid}/close", {})
    # owner_decisions は API 経路があれば別途。ここでは state に残す
    print(f"  closed {tid} {row['title'][:40]}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="互換（既定が提案のみ）")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--select", default="")
    ap.add_argument("--author", default=os.environ.get("TODOIST_313_AUTHOR") or "Jarvis")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if not _token():
        print("❌ TODOIST_API_TOKEN 未設定", file=sys.stderr)
        return 2

    rows = propose()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(
        json.dumps(
            {"at": datetime.now(JST).isoformat(timespec="seconds"), "candidates": rows},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    print(f"📎 313 外で済んだ候補: {len(rows)} 件")
    for r in rows:
        ev0 = (r.get("evidence") or [{}])[0]
        print(
            f"  #{r['n']} [{r['confidence']}] {r['title'][:50]} "
            f"← {ev0.get('folder','')}"
        )

    if not args.apply:
        print("了承後: --apply --select 1,2（low は慎重に）")
        return 0

    nums = {int(x) for x in re.findall(r"\d+", args.select)}
    for r in rows:
        if r["n"] not in nums:
            continue
        if r["confidence"] == "low":
            print(f"  skip low #{r['n']}（明示が必要なら confidence 無視で再実行）")
            continue
        apply_close(r, args.author)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
