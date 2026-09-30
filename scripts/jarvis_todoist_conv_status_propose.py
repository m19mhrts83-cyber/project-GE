#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""会話駆動ステータス提案（Phase 5）— 提案→了承→適用。

相手の「完了しました」等 → オーナー確認へ移動提案。
「全部終わりでいいよ」 → 対象レーンの一括 complete 提案。
無言の自動 close／対外通知はしない。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_conv_status_propose.py \\
    --text 'LEAFさんから対応完了の連絡がありました'
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_conv_status_propose.py \\
    --text '全部終わりでいいよ' --lane apps --dry-run
  # 了承後
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_conv_status_propose.py \\
    --apply --select 1 --text '…'
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
SIGNALS = REPO / "config" / "todoist_extract_signals.yaml"
STATE = REPO / ".jarvis_state" / "todoist_conv_status.json"
PY = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")
API = REPO / "scripts" / "jarvis_todoist_api.py"
JST = timezone(timedelta(hours=9))


def _now() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def _load_yaml() -> dict[str, Any]:
    import yaml  # type: ignore

    return yaml.safe_load(SIGNALS.read_text(encoding="utf-8")) or {}


def _load_state() -> dict[str, Any]:
    if not STATE.is_file():
        return {"last_proposals": [], "applied": []}
    return json.loads(STATE.read_text(encoding="utf-8"))


def _save_state(data: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _match_kind(text: str, signals: dict[str, Any]) -> str | None:
    st = signals.get("status_signals") or {}
    for pat in st.get("bulk_close") or []:
        if pat and pat in text:
            return "bulk_close"
    for pat in st.get("partner_done") or []:
        if pat and pat in text:
            return "partner_done"
    # soft variants
    if re.search(r"全部.*(終わ|完了)", text):
        return "bulk_close"
    if re.search(r"(対応)?完了(しました|いたしました)?|終わりました", text):
        return "partner_done"
    return None


def _lane_open_tasks(lane: str) -> list[dict[str, str]]:
    """Parse `lane` CLI output for open tasks (non-HOLD optional filter later)."""
    r = subprocess.run(
        [str(PY), str(API), "lane", "--id", lane],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode != 0:
        print(r.stderr or r.stdout, file=sys.stderr)
        return []
    out: list[dict[str, str]] = []
    for line in (r.stdout or "").splitlines():
        m = re.match(r"\s*\[([^\]]+)\]\s+(\S+)\s+(.+)$", line)
        if not m:
            continue
        status, tid, title = m.group(1), m.group(2), m.group(3).strip()
        if status in ("完了",):
            continue
        out.append({"status": status, "task_id": tid, "title": title, "lane": lane})
    return out


def _propose(text: str, lane: str | None) -> list[dict[str, Any]]:
    signals = _load_yaml()
    kind = _match_kind(text, signals)
    if not kind:
        print("📎 会話駆動ステータス: 該当シグナルなし（完了／一括クローズの言い回しが必要）")
        return []

    lanes = [lane] if lane else ["properties", "apps", "ai_raimo", "kamiooya", "kanji", "kodate", "kazoku"]
    proposals: list[dict[str, Any]] = []

    if kind == "partner_done":
        for ln in lanes:
            for t in _lane_open_tasks(ln):
                if t["status"] in ("オーナー確認", "HOLD"):
                    continue
                # 進行中／相手待ち／未着手を完了候補へ
                proposals.append(
                    {
                        "kind": "owner_confirm",
                        "lane": t["lane"],
                        "task_id": t["task_id"],
                        "title": t["title"],
                        "from_status": t["status"],
                        "reason": "相手完了シグナル → オーナー確認へ",
                    }
                )
    else:  # bulk_close
        for ln in lanes:
            for t in _lane_open_tasks(ln):
                if t["status"] != "オーナー確認":
                    continue
                proposals.append(
                    {
                        "kind": "complete",
                        "lane": t["lane"],
                        "task_id": t["task_id"],
                        "title": t["title"],
                        "from_status": t["status"],
                        "reason": "一括クローズ了承候補（オーナー確認列のみ）",
                    }
                )

    print("📎 会話駆動ステータス（提案）")
    if not proposals:
        print("- 候補なし（対象タスク無し／既にオーナー確認のみ等）")
        return []
    for i, p in enumerate(proposals, 1):
        print(
            f"- [{i}] {p['kind']} | {p['lane']} | {p['task_id']} | "
            f"{p['from_status']} → {p['title'][:60]}"
        )
        print(f"    理由: {p['reason']}")
    print("了承なら `--apply --select N`（カンマ区切り可）。即 close しない（owner_confirm は二段）。")
    return proposals


def _apply(proposals: list[dict[str, Any]], select: list[int]) -> int:
    ok = 0
    for i in select:
        if i < 1 or i > len(proposals):
            print(f"skip invalid select={i}", file=sys.stderr)
            continue
        p = proposals[i - 1]
        if p["kind"] == "owner_confirm":
            cmd = [
                str(PY),
                str(API),
                "update-status",
                "--task-id",
                p["task_id"],
                "--lane",
                p["lane"],
                "--status",
                "オーナー確認",
            ]
            # comment via separate call
            subprocess.run(cmd, cwd=str(REPO), check=False)
            subprocess.run(
                [
                    str(PY),
                    str(API),
                    "comment",
                    "--task-id",
                    p["task_id"],
                    "--text",
                    (
                        "サマリ: 会話駆動でオーナー確認へ（相手完了シグナル）。了承後に完了して。\n"
                        f"アウトプット:\n- 出典テキスト反映（conv_status { _now() }）"
                    ),
                ],
                cwd=str(REPO),
                check=False,
            )
            print(f"moved → オーナー確認: {p['task_id']}")
            ok += 1
        elif p["kind"] == "complete":
            subprocess.run(
                [
                    str(PY),
                    str(API),
                    "complete-task",
                    "--lane",
                    p["lane"],
                    "--task-id",
                    p["task_id"],
                    "--comment",
                    (
                        "タスク完了したよ（Jarvis・一括クローズ了承）\n"
                        "サマリ: 会話駆動の一括完了。\n"
                        "アウトプット:\n- conv_status_propose"
                    ),
                ],
                cwd=str(REPO),
                check=False,
            )
            print(f"completed: {p['task_id']}")
            ok += 1
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="会話駆動ステータス提案")
    ap.add_argument("--text", default="", help="相手／自分の発言テキスト")
    ap.add_argument("--from-file", type=Path, help="テキストファイル")
    ap.add_argument("--lane", default="", help="絞り込みレーン（省略時は主要レーン横断）")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--select", default="", help="1,2,3")
    ap.add_argument("--dry-run", action="store_true", help="提案のみ（既定と同じ）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    text = (args.text or "").strip()
    if args.from_file:
        text = args.from_file.read_text(encoding="utf-8").strip()
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    if not text:
        print("ERROR: --text / --from-file / stdin が必要", file=sys.stderr)
        return 2

    lane = args.lane.strip() or None
    proposals = _propose(text, lane)
    st = _load_state()
    st["last_proposals"] = proposals
    st["last_text"] = text[:500]
    st["last_at"] = _now()
    _save_state(st)

    if args.json:
        print(json.dumps({"proposals": proposals}, ensure_ascii=False))

    if not args.apply or args.dry_run:
        return 0
    if not args.select.strip():
        print("ERROR: --apply には --select が必要", file=sys.stderr)
        return 2
    sels = [int(x) for x in args.select.split(",") if x.strip().isdigit()]
    n = _apply(proposals, sels)
    st["applied"].append({"at": _now(), "n": n, "select": sels})
    _save_state(st)
    print(f"applied={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
