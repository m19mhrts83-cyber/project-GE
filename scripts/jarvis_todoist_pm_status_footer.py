#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""管理会社別・所有物件タスク状況フッター（メール／LINE貼付用）.

Guest URL 未設定のあいだは要約のみ。転送メールアドレスは出さない。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_pm_status_footer.py --pm LEAF
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_pm_status_footer.py --pm ミニテック --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_todoist_api as api  # noqa: E402


def _load_cfg() -> dict[str, Any]:
    return api._load_yaml()


def _resolve_pm(cfg: dict[str, Any], raw: str) -> str:
    key = (raw or "").strip()
    pm_share = (cfg.get("pm_share") or {}).get("companies") or {}
    pm_labels = cfg.get("pm_labels") or {}
    # 別名
    aliases = {
        "leaf": "LEAF",
        "リーフ": "LEAF",
        "minitech": "ミニテック",
        "ミニテック": "ミニテック",
        "homeplanner": "ホームプランナー",
        "ホームプランナー": "ホームプランナー",
        "hp": "ホームプランナー",
        "tcell": "Tcell",
        "ティーセル": "Tcell",
        "t-cell": "Tcell",
    }
    low = key.lower()
    if low in aliases:
        key = aliases[low]
    if key in pm_share or key in pm_labels:
        return key
    # folder 部分一致
    for name, meta in {**pm_labels, **pm_share}.items():
        folder = str((meta or {}).get("folder") or "")
        if key and key in folder:
            return str(name)
    raise SystemExit(f"未知の管理会社: {raw}（LEAF / ミニテック / ホームプランナー / Tcell）")


def _open_tasks_for_pm(cfg: dict[str, Any], pm: str) -> list[dict[str, Any]]:
    lane = api._lane(cfg, "properties")
    proj = api._project_for_lane(cfg, lane)
    pid = str(proj["project_id"])
    tasks = api._paginate_results(f"/tasks?project_id={pid}", cfg=cfg)
    open_secs = set(lane.get("open_sections") or ["未着手", "進行中", "相手待ち", "オーナー確認"])
    sid_to_name = {
        str(v): k for k, v in (proj.get("section_ids") or {}).items() if v
    }
    out: list[dict[str, Any]] = []
    for t in tasks:
        labels = [str(x) for x in (t.get("labels") or [])]
        if pm not in labels:
            continue
        sec = sid_to_name.get(str(t.get("section_id") or ""), "")
        if open_secs and sec and sec not in open_secs:
            continue
        if t.get("checked") or t.get("is_completed"):
            continue
        out.append(
            {
                "id": t.get("id"),
                "content": t.get("content"),
                "section": sec or "-",
                "url": t.get("url") or "",
            }
        )
    return out


def build_footer(pm: str, tasks: list[dict[str, Any]], *, guest_url: str, max_n: int) -> str:
    lines = [
        "--------------------------------------------------",
        f"📌 【{pm}】進行中の対応（社内整理の抜粋）",
    ]
    if not tasks:
        lines.append("・現時点で未完了タスクはありません")
    else:
        for t in tasks[:max_n]:
            title = str(t.get("content") or "").strip()
            sec = t.get("section") or "-"
            lines.append(f"・[{sec}] {title}")
        if len(tasks) > max_n:
            lines.append(f"・…他 {len(tasks) - max_n} 件")
    if guest_url.strip():
        lines.append(f"共有ボード: {guest_url.strip()}")
        lines.append("※状況把握用です。書き込みは任意です。")
    else:
        lines.append("※詳細はこちらで更新しています。一覧の共有が必要でしたらお申し付けください。")
    lines.append("--------------------------------------------------")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="管理会社別 Todoist 状況フッター")
    p.add_argument("--pm", required=True, help="LEAF / ミニテック / ホームプランナー / Tcell")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    cfg = _load_cfg()
    pm = _resolve_pm(cfg, args.pm)
    share = ((cfg.get("pm_share") or {}).get("companies") or {}).get(pm) or {}
    max_n = int((cfg.get("pm_share") or {}).get("footer_max_tasks") or 5)
    guest_url = str(share.get("guest_project_url") or "")
    tasks = _open_tasks_for_pm(cfg, pm)
    footer = build_footer(pm, tasks, guest_url=guest_url, max_n=max_n)

    if args.json:
        print(
            json.dumps(
                {
                    "pm": pm,
                    "count": len(tasks),
                    "guest_project_url": guest_url or None,
                    "email_forward_to_partner": bool(
                        (cfg.get("pm_share") or {}).get("email_forward_to_partner")
                    ),
                    "tasks": tasks[:max_n],
                    "footer": footer,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(footer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
