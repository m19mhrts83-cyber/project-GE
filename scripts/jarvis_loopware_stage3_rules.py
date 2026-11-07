#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""段階3 — 高信頼型だけ自動寄りにするルール草案を出す（適用は人手）.

owner_decisions / task_loop_* を読んで、推しそのまま率が高い型を列挙。
自動 close はここでは有効化しない（提案 MD のみ）。

  ~/selenium_env/venv/bin/python scripts/jarvis_loopware_stage3_rules.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
OUT = (
    REPO
    / "docs/AIエージェントチーム/300_品質・タスク運用管理室"
    / "314_業務品質監査係/output"
)
JST = ZoneInfo("Asia/Tokyo")


def _sb():
    try:
        from supabase import create_client
    except ImportError:
        return None
    url = os.environ.get("JARVIS_SUPABASE_URL") or ""
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        return None
    return create_client(url, key)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=21)
    args = ap.parse_args()

    sb = _sb()
    lines = [
        f"# ループウェア段階3 ルール草案 — {datetime.now(JST):%Y-%m-%d}",
        "",
        "自動学習はしない。同じ直しが2件以上なら prompts／プログラムへ人手反映。",
        "",
    ]
    seed = [
        "## 候補（初期・段階3）",
        "- 313: `kind=confirm_only` かつ推し close を人がそのまま選んだ型 → コメント付き auto-close 候補",
        "- 313: done_elsewhere confidence=high かつ誤close 0 → 自動コメント＋オーナー確認列へ",
        "- 312: 案3（登録しない）推しそのまま率 ≥90% の催促パターン → Slack 完結可",
        "- 改善は常に `apps/loopware/prompts/*.md` と検知スクリプトへ戻す（ツール内学習なし）",
        "",
    ]
    if not sb:
        lines += [
            "## 状態",
            "- Supabase 未接続のため、テンプレのみ。",
            "- migration `20261107_task_loop.sql` / `owner_decisions` 適用後に再実行。",
            "",
        ] + seed
    else:
        since = (datetime.now(JST) - timedelta(days=args.days)).isoformat()
        try:
            rows = (
                sb.table("owner_decisions")
                .select("action,payload,note")
                .eq("surface", "todoist_313")
                .gte("decided_at", since)
                .execute()
                .data
                or []
            )
            actions = Counter(r.get("action") for r in rows)
            lines += ["## 313 owner_decisions 集計", f"- 件数: {len(rows)}", ""]
            for a, c in actions.most_common():
                lines.append(f"- {a}: {c}")
            lines += ["", "## 自動寄り候補", "- （集計を見て 314 が PR）", ""] + seed
        except Exception as e:
            lines += [
                "## 状態",
                f"- owner_decisions 読取失敗: {e}",
                "- migration 未適用の可能性。テンプレのみ出力。",
                "",
            ] + seed

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{datetime.now(JST):%Y%m%d}_ループウェア段階3草案.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"📎 wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
