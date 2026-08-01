#!/usr/bin/env python3
"""
Zaim 銀行・カード連携の鮮度チェック（Phase1: 特定＋手動更新プレイブック）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_zaim_bank_sync_check.py
  python scripts/jarvis_zaim_bank_sync_check.py --year 2026
  python scripts/jarvis_zaim_bank_sync_check.py --mark-prompted   # 金曜促し記録
  python scripts/jarvis_zaim_bank_sync_check.py --status

CSV の支払元/入金先の最終日付と、CSV 全体の最新日の差で「止まっていそう」を検知。
値（パスワード等）は出力しない。env_hint の変数名のみ示す。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
CFG_PATH = REPO / "config" / "zaim_bank_sync_watch.yaml"
OUT_PATH = REPO / ".jarvis_state" / "zaim_bank_sync.json"
EXAMPLE_PATH = REPO / ".jarvis_state" / "zaim_bank_sync.example.json"


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def load_cfg() -> dict[str, Any]:
    return yaml.safe_load(CFG_PATH.read_text(encoding="utf-8")) or {}


def resolve_csv(cfg: dict[str, Any], year: int) -> Path:
    base = Path(cfg.get("csv_base_dir") or "").expanduser()
    return base / f"{year}年度" / f"Zaim.{year}年度.csv"


def parse_d(s: str) -> date | None:
    s = (s or "").strip()[:10]
    if len(s) < 10:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def scan_csv(path: Path) -> tuple[date | None, dict[str, dict[str, Any]]]:
    """source_name -> {last, count, as_pay, as_deposit}"""
    sources: dict[str, dict[str, Any]] = {}
    csv_max: date | None = None
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            d = parse_d(row.get("日付") or "")
            if d and (csv_max is None or d > csv_max):
                csv_max = d
            for col, flag in (("支払元", "as_pay"), ("入金先", "as_deposit")):
                name = (row.get(col) or "").strip()
                if not name or name == "-":
                    continue
                bucket = sources.setdefault(
                    name,
                    {"last": None, "count": 0, "as_pay": 0, "as_deposit": 0},
                )
                bucket["count"] += 1
                bucket[flag] += 1
                if d and (bucket["last"] is None or d > bucket["last"]):
                    bucket["last"] = d
    return csv_max, sources


def match_account(
    acc: dict[str, Any], sources: dict[str, dict[str, Any]]
) -> tuple[str | None, dict[str, Any] | None]:
    needle = str(acc.get("match") or "")
    if not needle:
        return None, None
    hits = [(n, info) for n, info in sources.items() if needle in n]
    if not hits:
        return None, None
    # 最も新しい最終日の名前を採用
    hits.sort(key=lambda x: x[1].get("last") or date.min, reverse=True)
    return hits[0][0], hits[0][1]


def env_present(names: list[str]) -> list[str]:
    ok = []
    for n in names:
        if (os.environ.get(n) or "").strip():
            ok.append(n)
    return ok


def evaluate(cfg: dict[str, Any], year: int) -> dict[str, Any]:
    path = resolve_csv(cfg, year)
    if not path.is_file():
        return {
            "updated_at": now_iso(),
            "year": year,
            "csv": str(path),
            "level": "warn",
            "summary": f"CSV なし: {path.name}",
            "detail": "zaim_csv_weekly_runner.sh で CSV を取ってから再実行",
            "stale": [],
            "missing": [],
            "ok": [],
            "unlinkable": [],
            "phase1_steps": [],
        }

    csv_max, sources = scan_csv(path)
    default_days = int(cfg.get("default_stale_days") or 12)
    stale: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    ok_list: list[dict[str, Any]] = []
    unlinkable: list[dict[str, Any]] = []

    for acc in cfg.get("accounts") or []:
        aid = str(acc.get("id") or "")
        label = str(acc.get("label") or aid)
        note = str(acc.get("note") or "")
        hints = list(acc.get("env_hint") or [])
        hints_ok = env_present(hints)
        row: dict[str, Any] = {
            "id": aid,
            "label": label,
            "match": acc.get("match"),
            "note": note,
            "env_hint": hints,
            "env_hint_ready": hints_ok,
            "env_hint_missing": [h for h in hints if h not in hints_ok],
        }
        if acc.get("unlinkable"):
            row["status"] = "unlinkable"
            unlinkable.append(row)
            continue

        name, info = match_account(acc, sources)
        if not info or not name:
            row["status"] = "missing"
            row["csv_name"] = None
            row["last"] = None
            row["lag_days"] = None
            missing.append(row)
            continue

        last: date | None = info.get("last")
        lag = (csv_max - last).days if csv_max and last else None
        thresh = int(acc.get("stale_days") or default_days)
        row.update(
            {
                "csv_name": name,
                "last": last.isoformat() if last else None,
                "count": info.get("count"),
                "lag_days": lag,
                "stale_days_threshold": thresh,
            }
        )
        if lag is not None and lag >= thresh:
            row["status"] = "stale"
            stale.append(row)
        else:
            row["status"] = "ok"
            ok_list.append(row)

    for note in cfg.get("unlinkable_notes") or []:
        unlinkable.append(
            {
                "id": "note",
                "label": str(note),
                "status": "unlinkable",
                "note": str(note),
                "env_hint": [],
                "env_hint_ready": [],
                "env_hint_missing": [],
            }
        )

    level = "ok"
    if missing or stale:
        level = "attention"
    if not ok_list and (missing or stale):
        level = "warn"

    lines: list[str] = []
    if stale:
        lines.append("■ 連携が止まっていそう（CSV最終日からのラグ）")
        for s in stale:
            lines.append(
                f"- {s['label']}: 最終 {s.get('last') or '—'}（{s.get('lag_days')}日遅れ・閾値{s.get('stale_days_threshold')}日）"
                + (f" / {s['note']}" if s.get("note") else "")
            )
    if missing:
        lines.append("■ CSV に見当たらない（未連携 or 名称変更）")
        for s in missing:
            lines.append(f"- {s['label']}（match={s.get('match')}）")
    if unlinkable:
        lines.append("■ 事情により連携できない／既知スキップ")
        for s in unlinkable:
            lines.append(f"- {s.get('label') or s.get('note')}")

    phase1: list[str] = [
        "1. Zaim Web にログイン（ZAIM_LOGIN_EMAIL / ZAIM_PASSWORD）",
        f"2. 口座一覧（連携設定）を開く: {cfg.get('zaim_accounts_url') or 'https://zaim.net/online_accounts'}",
        "3. 上の『止まっていそう』口座ごとに『連携設定』→『連携データを更新』（または jarvis_zaim_bank_sync_manual.py）",
        "4. OTP・追加認証が出たら Jarvis に『回答して』→ .env.jarvis_private の env_hint を使う（値はチャットに貼らない）",
        "5. 更新後: launchd/zaim_csv_weekly_runner.sh または zaim_csv_export で CSV 再取得 → 本スクリプト再実行で lag 解消を確認",
        "6. Phase2: 手順が安定したら Playwright 定期実行へ（未実装）",
    ]
    if stale or missing:
        phase1.insert(
            3,
            "対象: "
            + "、".join(
                [s["label"] for s in stale[:8]] + [s["label"] for s in missing[:4]]
            ),
        )

    summary_parts = []
    if stale:
        summary_parts.append(f"連携遅れ {len(stale)}件")
    if missing:
        summary_parts.append(f"未検出 {len(missing)}件")
    if unlinkable:
        summary_parts.append(f"連携不可(既知) {len(unlinkable)}件")
    if not summary_parts:
        summary_parts.append(f"監視口座 OK（{len(ok_list)}件）")
    summary_parts.append(f"CSV最新 {csv_max.isoformat() if csv_max else '—'}")

    return {
        "updated_at": now_iso(),
        "year": year,
        "csv": str(path),
        "csv_max_date": csv_max.isoformat() if csv_max else None,
        "level": level,
        "summary": " · ".join(summary_parts),
        "detail": "\n".join(lines) if lines else "監視対象の銀行・カードは鮮度 OK",
        "stale": stale,
        "missing": missing,
        "ok": ok_list,
        "unlinkable": unlinkable,
        "phase1_steps": phase1,
        "zaim_accounts_url": cfg.get("zaim_accounts_url"),
    }


def load_state() -> dict[str, Any]:
    if OUT_PATH.is_file():
        return json.loads(OUT_PATH.read_text(encoding="utf-8"))
    return {}


def save_result(result: dict[str, Any], *, merge_prompt: dict[str, Any] | None = None) -> None:
    prev = load_state()
    out = dict(result)
    if merge_prompt:
        out.update(merge_prompt)
    else:
        for k in ("last_prompted_at", "last_check_friday"):
            if k in prev:
                out[k] = prev[k]
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not EXAMPLE_PATH.is_file():
        EXAMPLE_PATH.write_text(
            json.dumps(
                {
                    "disabled": False,
                    "note": "runner / jarvis_zaim_bank_sync_check.py が更新。秘密は書かない",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def format_block(result: dict[str, Any]) -> str:
    lines = [
        "📎 Zaim銀行連携（週次・金曜）",
        f"- 判定: {result.get('summary')}",
        f"- level: {result.get('level')}",
    ]
    if result.get("detail"):
        for ln in str(result["detail"]).splitlines()[:16]:
            lines.append(f"  {ln}")
    lines.append("- Phase1 次の一手:")
    for s in (result.get("phase1_steps") or [])[:8]:
        lines.append(f"  · {s}")
    return "\n".join(lines)


def should_prompt_friday(cfg: dict[str, Any], state: dict[str, Any]) -> bool:
    if state.get("disabled") or os.environ.get("JARVIS_ZAIM_BANK_SYNC_DISABLE") == "1":
        return False
    today = datetime.now(JST).date()
    # Friday = 4 in Python weekday() if Mon=0... wait: Monday=0, Friday=5
    want = int(cfg.get("friday_weekday", 5))
    if today.weekday() != want:
        return False
    last = state.get("last_prompted_at") or state.get("last_check_friday")
    if last:
        try:
            dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=JST)
            age = (datetime.now(JST) - dt.astimezone(JST)).days
            if age < int(cfg.get("prompt_interval_days") or 6):
                return False
        except ValueError:
            pass
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=datetime.now(JST).year)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--mark-prompted", action="store_true")
    ap.add_argument("--force-prompt", action="store_true", help="金曜以外でもブロック出力")
    args = ap.parse_args(argv)

    cfg = load_cfg()
    result = evaluate(cfg, args.year)
    save_result(result)

    if args.status:
        print(json.dumps(load_state(), ensure_ascii=False, indent=2))
        return 0

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    state = load_state()
    show = args.force_prompt or args.mark_prompted or should_prompt_friday(cfg, state)
    # 常に stderr に要約、ブロックは金曜 or force
    print(f"# wrote {OUT_PATH} level={result.get('level')} {result.get('summary')}", file=sys.stderr)
    if show or result.get("level") in ("attention", "warn"):
        if args.mark_prompted or should_prompt_friday(cfg, state) or args.force_prompt:
            save_result(
                result,
                merge_prompt={
                    "last_prompted_at": now_iso(),
                    "last_check_friday": date.today().isoformat(),
                },
            )
        print(format_block(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
