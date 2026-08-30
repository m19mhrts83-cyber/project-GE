#!/usr/bin/env python3
"""年会費・大型引落の要約 → リソース経営部長 outbox（秘密なし）。

ホーク週次（日曜 20:00）前に Jarvis が書き、リソース部長 Bot が参照する。
正本 state: .jarvis_state/card_annual_fee.json / card_debit_watch.json

  cd ~/git-repos
  ~/selenium_env/venv/bin/python scripts/jarvis_card_fee_resource_outbox.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_card_fee_resource_outbox.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jarvis_bucho_bridge_lib import team_folder, sanitize_title  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
STATE = REPO / ".jarvis_state"
FEE_PATH = STATE / "card_annual_fee.json"
DEBIT_PATH = STATE / "card_debit_watch.json"
OUTBOX_STATE = STATE / "card_fee_resource_outbox.json"
JST = ZoneInfo("Asia/Tokyo")


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def build_body(fee: dict[str, Any], debit: dict[str, Any]) -> str:
    lines: list[str] = [
        "## カード年会費（jarvis-card-fee-guard 正本）",
        "",
    ]
    cards = fee.get("cards") or []
    if not cards:
        lines.append("- （card_annual_fee.json 未設定または cards 空）")
    else:
        for c in cards:
            if not isinstance(c, dict):
                continue
            label = c.get("label") or c.get("id") or "?"
            status = c.get("status") or "—"
            next_fee = c.get("next_fee_date") or "—"
            deadline = c.get("cancel_deadline_to_skip_next") or "—"
            cancel = c.get("cancel_mode") or "—"
            fee_yen = c.get("annual_fee_yen")
            fee_part = f" · 年会費{fee_yen:,}円" if isinstance(fee_yen, int) else ""
            lines.append(
                f"- **{label}**: {status}{fee_part} · 次回{next_fee} · "
                f"回避期限{deadline} · 退会モード{cancel}"
            )

    lines.extend(["", "## 大型引落（card_debit_watch）", ""])
    dcards = (debit.get("cards") or {}) if isinstance(debit.get("cards"), dict) else {}
    if not dcards:
        lines.append("- （card_debit_watch.json 未設定または cards 空）")
    else:
        for _cid, c in dcards.items():
            if not isinstance(c, dict):
                continue
            label = c.get("label") or c.get("id") or "?"
            amount = c.get("amount_jpy")
            due = c.get("due_date") or "—"
            pending = c.get("amount_pending")
            amt = f"{amount:,}円" if isinstance(amount, int) else "（未確定）"
            pend = " · 金額未確定" if pending else ""
            shortfall = c.get("smbc_shortfall")
            sf = f" · 不足見込{shortfall:,}円" if isinstance(shortfall, int) and shortfall > 0 else ""
            lines.append(f"- **{label}**: 引落{amt} · 予定日{due}{pend}{sf}")

    alerts = debit.get("alerts") or []
    if alerts:
        lines.extend(["", "## アラート", ""])
        for a in alerts[:5]:
            if isinstance(a, dict):
                lines.append(f"- {a.get('summary') or a.get('kind') or str(a)[:120]}")
            else:
                lines.append(f"- {a}")

    lines.extend(
        [
            "",
            "## ホーク週次での確認（Q3）",
            "- 年会費・二重課金・引落不足を常設アテンション候補として扱う",
            "- 該当あれば参謀室週次の `## attention` に1行以上載せる",
            "",
            "（秘密・カード番号・口座番号は含まない · Jarvis 自動生成）",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="年会費・引落要約 → resource outbox")
    ap.add_argument("--apply", action="store_true", help="outbox に書く")
    ap.add_argument("--dry-run", action="store_true", help="stdout のみ")
    args = ap.parse_args()

    fee = load_json(FEE_PATH)
    debit = load_json(DEBIT_PATH)
    body = build_body(fee, debit)
    today = datetime.now(JST).strftime("%Y-%m-%d")
    stamp = datetime.now(JST).strftime("%H%M")
    title = sanitize_title(f"カード年会費引落_{today}")
    fname = f"{today}_{stamp}_{title}.md"

    md = (
        f"# Jarvis → Grok\n"
        f"target: resource\n"
        f"priority: normal\n"
        f"action: card_fee_debit_brief\n"
        f"source: jarvis\n"
        f"generated_at: {datetime.now(JST).isoformat()}\n"
        f"\n"
        f"{body}\n"
    )

    if args.dry_run or not args.apply:
        print("📎 カード年会費・引落 resource outbox（dry-run）")
        print(f"- file: {fname}")
        print(body[:800])
        if not args.apply:
            print("# use --apply to write", file=sys.stderr)
            return 0

    dest_dir = team_folder("resource")
    dest = dest_dir / fname
    dest.write_text(md, encoding="utf-8")
    OUTBOX_STATE.parent.mkdir(parents=True, exist_ok=True)
    OUTBOX_STATE.write_text(
        json.dumps(
            {
                "last_written_at": datetime.now(JST).isoformat(),
                "path": str(dest),
                "file": fname,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("📎 カード年会費・引落 resource outbox")
    print(f"- written: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
