#!/usr/bin/env python3
"""戦力の推移（月ごと）を Zaim CSV から集計し、sync_meta `force_monthly` へ写す（ルールのみ・LLM なし）。

画面は Jarvis Dashboard の /policy（方針タブ）。公開リポなので金額はここに書かない（CSV→Supabase のみ）。
  python3 scripts/jarvis_force_monthly.py            # 表示だけ（金額は出力するのでログに残さない）
  python3 scripts/jarvis_force_monthly.py --push     # Supabase sync_meta へ upsert

集計ルール（payment 行・「集計に含めない」は除く）:
  AI : Claude=ANTHROPIC / Cursor=CURSOR / ChatGPT=Apple iTunes の 3,000 円ちょうど
  基盤: Google Cloud=GOOGLE*CLOUD（前払いの補充額・使用量ではない）/ Supabase / Todoist / Slack / Notion(NOTION LABS)
  年額払い（Todoist 5,000 円以上）は払った月から12か月で月割り。Slack の年額かは未確認なので月払い扱い。
AI 顧問料は Zaim からは拾えない（固定＋月ごとの追加費用）。sync_meta `advisory_fee` に別に置く（scripts/jarvis_advisory_fee.py）。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
SYNC_KEY = "force_monthly"
DEFAULT_CSV = Path.home() / (
    "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/"
    "50_税金,確定申告/2026年度/Zaim.2026年度.csv"
)

# id, 表示名, グループ
SERVICES = [
    ("claude", "Claude", "ai"),
    ("cursor", "Cursor", "ai"),
    ("chatgpt", "ChatGPT", "ai"),
    ("gcloud", "Google Cloud（補充額）", "base"),
    ("supabase", "Supabase", "base"),
    ("todoist", "Todoist", "base"),
    ("slack", "Slack", "base"),
    ("notion", "Notion", "base"),
]
ANNUAL_MIN = {"todoist": 5000}  # この額以上は年額払いとして12か月で割る
CHATGPT_YEN = 3000


def classify(shop: str, memo: str, yen: int) -> str | None:
    s = f"{shop} {memo}".upper()
    if "ANTHROPIC" in s:
        return "claude"
    if "CURSOR" in s:
        return "cursor"
    if "ITUNES" in s and yen == CHATGPT_YEN:
        return "chatgpt"
    if "GOOGLE*CLOUD" in s:
        return "gcloud"
    if "SUPABASE" in s:
        return "supabase"
    if "TODOIST" in s:
        return "todoist"
    if "SLACK" in s:
        return "slack"
    if "NOTION LABS" in s:
        return "notion"
    return None


def add_months(ym: str, n: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    t = y * 12 + (m - 1) + n
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def aggregate(rows: list[dict[str, str]], today: datetime) -> dict:
    last = today.strftime("%Y-%m")
    first = f"{today.year:04d}-01"
    months: list[str] = []
    m = first
    while m <= last:
        months.append(m)
        m = add_months(m, 1)
    spend: dict[str, dict[str, float]] = {k: {} for k in (s[0] for s in SERVICES)}
    for r in rows:
        if (r.get("集計の設定") or "").strip() == "集計に含めない":
            continue
        ym = (r.get("日付") or "")[:7]
        if not ym:
            continue
        method = r.get("方法")
        if method != "payment":
            continue
        yen = int(float(r.get("支出") or 0))
        sid = classify(r.get("お店") or "", r.get("メモ") or "", yen)
        if not sid or yen <= 0:
            continue
        if yen >= ANNUAL_MIN.get(sid, 10**12):
            for i in range(12):
                mm = add_months(ym, i)
                spend[sid][mm] = spend[sid].get(mm, 0) + yen / 12
        else:
            spend[sid][ym] = spend[sid].get(ym, 0) + yen
    amounts = {
        mm: {sid: round(spend[sid].get(mm, 0)) for sid in spend if spend[sid].get(mm, 0)}
        for mm in months
    }
    return {
        "generated_at": today.isoformat(timespec="seconds"),
        "months": months,
        "services": [{"id": i, "label": n, "group": g} for i, n, g in SERVICES],
        "amounts": amounts,
        # ai-usage に「枠切れの日数」の記録はまだ無い（週・月ごとのピークだけ）。残るようになったら入れる
        "usage": None,
    }


def push(rep: dict) -> bool:
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        print("# supabase skip: JARVIS_SUPABASE_* 未設定", file=sys.stderr)
        return False
    try:
        from supabase import create_client
        create_client(url, key).table("sync_meta").upsert(
            {"key": SYNC_KEY, "value": json.dumps(rep, ensure_ascii=False), "updated_at": rep["generated_at"]},
            on_conflict="key").execute()
        return True
    except Exception as e:
        print(f"# supabase skip: {type(e).__name__}: {e}"[:200], file=sys.stderr)
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default=str(DEFAULT_CSV))
    ap.add_argument("--push", action="store_true", help="Supabase sync_meta へ写す")
    args = ap.parse_args()
    p = Path(args.csv)
    if not p.is_file():
        print(f"# CSV が無い: {p.name}", file=sys.stderr)
        return 1
    with p.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    rep = aggregate(rows, datetime.now(JST))
    if args.push:
        ok = push(rep)
        print(f"# push: {'ok' if ok else '失敗'}（{len(rep['months'])}か月）", file=sys.stderr)
        return 0 if ok else 1
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
