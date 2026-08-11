#!/usr/bin/env python3
"""資産全体の週次収集（ソニー／アクサ／SBI／三菱重工／あかつき／立花）。

Mac（Playwright）が本線。GitHub Actions からは --cloud-only。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_portfolio_weekly.py
  ~/selenium_env/venv/bin/python scripts/jarvis_portfolio_weekly.py --cloud-only
  ~/selenium_env/venv/bin/python scripts/jarvis_portfolio_weekly.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from jarvis_trade_common import JST, REPO, sb_client, today_jst

STATE_PATH = REPO / ".jarvis_state" / "portfolio_weekly.json"
FINANCE = REPO / "215_kamiooya" / "C1_cursor" / "finance"
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"
def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def iso_week(d=None) -> str:
    d = d or today_jst()
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def week_start(d=None):
    d = d or today_jst()
    return d - timedelta(days=d.weekday())


def py_exe() -> str:
    return str(PY) if PY.is_file() else sys.executable


def load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(data: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def upsert_snapshot(
    sb,
    account_id: str,
    value_jpy: float,
    *,
    source: str,
    note: str | None = None,
    as_of: str | None = None,
) -> None:
    sb.table("portfolio_snapshots").upsert(
        {
            "account_id": account_id,
            "as_of": as_of or today_jst().isoformat(),
            "value_jpy": value_jpy,
            "source": source,
            "note": note,
        },
        on_conflict="account_id,as_of",
    ).execute()


def run_json_script(args: list[str], timeout: int = 180) -> dict[str, Any]:
    env = os.environ.copy()
    r = subprocess.run(
        args,
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        check=False,
    )
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip().splitlines()
        raise RuntimeError(err[-1] if err else f"exit {r.returncode}")
    line = (r.stdout or "").strip().splitlines()
    if not line:
        raise RuntimeError("empty stdout")
    return json.loads(line[-1])


def fetch_sony() -> dict[str, Any]:
    if not (
        os.environ.get("SONYLIFE_USERNAME")
        or os.environ.get("SONYLIFE_USERNAME_1")
    ):
        return {"status": "skipped", "reason": "SONYLIFE_USERNAME 未設定"}
    script = FINANCE / "run_sony_life_step3.py"
    if not script.is_file():
        return {"status": "skipped", "reason": "sony script missing"}
    env = os.environ.copy()
    r = subprocess.run(
        [py_exe(), str(script), "--headless"],
        cwd=str(FINANCE),
        capture_output=True,
        text=True,
        timeout=240,
        env=env,
        check=False,
    )
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "sony fail").strip().splitlines()[-1])
    for line in (r.stdout or "").splitlines():
        if "解約返戻金（合計）" in line:
            digits = "".join(ch for ch in line if ch.isdigit())
            if digits:
                return {"status": "ok", "value_jpy": int(digits), "note": line.strip()}
    raise RuntimeError("ソニー生命の金額行が見つかりません")


def fetch_akatsuki() -> dict[str, Any]:
    env_file = FINANCE / ".env.akatsuki"
    if not (
        os.environ.get("AKATSUKI_BRANCH_CODE")
        and os.environ.get("AKATSUKI_ACCOUNT_NUMBER")
        and os.environ.get("AKATSUKI_LOGIN_PASSWORD")
    ) and not env_file.is_file():
        return {"status": "skipped", "reason": "AKATSUKI_* 未設定"}
    script = FINANCE / "akatsuki_bond_balance.py"
    cmd = [py_exe(), str(script), "--headless", "--json"]
    if env_file.is_file():
        cmd += ["--env-file", str(env_file)]
    data = run_json_script(cmd, timeout=180)
    return {
        "status": "ok",
        "value_jpy": int(data["total_jpy"]),
        "note": data.get("parser_mode") or "",
    }


def fetch_axa() -> dict[str, Any]:
    if not (os.environ.get("AXA_MYAXA_ID") and os.environ.get("AXA_MYAXA_PASSWORD")):
        return {"status": "skipped", "reason": "AXA_MYAXA_* 未設定"}
    script = REPO / "scripts" / "jarvis_axa_balance.py"
    data = run_json_script(
        [py_exe(), str(script), "--headless", "--json", "--save-debug"],
        timeout=180,
    )
    return {
        "status": "ok",
        "value_jpy": int(data["value_jpy"]),
        "note": data.get("parser_mode") or "",
    }


def fetch_sbi() -> dict[str, Any]:
    if not (os.environ.get("SBI_SEC_USER") and os.environ.get("SBI_SEC_LOGIN_PASSWORD")):
        return {"status": "skipped", "reason": "SBI_SEC_* 未設定"}
    script = REPO / "scripts" / "jarvis_sbi_index_balance.py"
    data = run_json_script(
        [py_exe(), str(script), "--headless", "--json", "--save-debug"],
        timeout=180,
    )
    return {
        "status": "ok",
        "value_jpy": int(data["value_jpy"]),
        "note": data.get("parser_mode") or "",
    }


def fetch_mhi_zaim() -> dict[str, Any]:
    """持株は毎月買い足すので、Zaim 連携口座の評価額を正とする。"""
    script = REPO / "scripts" / "jarvis_zaim_mhi_balance.py"
    data = run_json_script([py_exe(), str(script), "--json"], timeout=180)
    if data.get("status") != "ok":
        return {
            "status": "error",
            "reason": data.get("reason") or "Zaim 持株が取れません",
        }
    return {
        "status": "ok",
        "value_jpy": int(data["value_jpy"]),
        "note": data.get("note") or "",
    }


def fetch_tachibana(sb) -> dict[str, Any]:
    row = (
        sb.table("trade_risk_state")
        .select("current_equity,tranche,kill_switch")
        .eq("id", "paper")
        .limit(1)
        .execute()
    )
    data = (row.data or [None])[0]
    if not data:
        return {"status": "skipped", "reason": "trade_risk_state paper なし"}
    return {
        "status": "ok",
        "value_jpy": float(data["current_equity"]),
        "note": f"paper tranche={data.get('tranche')} kill={data.get('kill_switch')}",
    }


def write_review(sb, sources: dict[str, Any]) -> None:
    lines = []
    total = 0.0
    for acc, rec in sources.items():
        if rec.get("status") == "ok" and rec.get("value_jpy") is not None:
            v = float(rec["value_jpy"])
            total += v
            lines.append(f"- {acc}: {v:,.0f}円")
        else:
            lines.append(f"- {acc}: {rec.get('status')} {rec.get('reason') or rec.get('note') or ''}")
    summary = f"週次資産レビュー {iso_week()}\n" + "\n".join(lines)
    if total:
        summary += f"\n合計（取れた口座）: {total:,.0f}円"
    sb.table("trade_reviews").insert(
        {
            "week_start": week_start().isoformat(),
            "summary": summary[:8000],
            "jarvis_proposal": "ブラウザ取得が skipped/OTP の口座は、次回 Mac 起動後に再試行されます。",
            "status": "open",
            "payload": {"iso_week": iso_week(), "sources": sources, "total_ok_jpy": total},
        }
    ).execute()


def upsert_sync_meta(sb, payload: dict[str, Any]) -> None:
    ts = now_iso()
    sb.table("sync_meta").upsert(
        [
            {"key": "portfolio_weekly_at", "value": ts, "updated_at": ts},
            {
                "key": "portfolio_weekly_summary",
                "value": json.dumps(payload, ensure_ascii=False)[:1800],
                "updated_at": ts,
            },
        ],
        on_conflict="key",
    ).execute()


def main() -> int:
    ap = argparse.ArgumentParser(description="資産全体 週次収集")
    ap.add_argument("--cloud-only", action="store_true", help="Yahoo / 既存DBのみ（GHA向け）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if os.environ.get("JARVIS_PORTFOLIO_WEEKLY_DISABLE") == "1":
        print("# skip: JARVIS_PORTFOLIO_WEEKLY_DISABLE=1")
        return 0

    prev = load_state()
    if (
        not args.force
        and not args.cloud_only
        and prev.get("last_full_iso_week") == iso_week()
        and prev.get("last_full_ok")
    ):
        print(f"# skip: full weekly already ok {iso_week()}")
        return 0

    print(f"# portfolio_weekly start {now_iso()} cloud_only={args.cloud_only}")
    sb = None if args.dry_run else sb_client()
    sources: dict[str, Any] = {}

    jobs: list[tuple[str, Any]] = []
    if not args.cloud_only:
        jobs = [
            ("sony_life", fetch_sony),
            ("axa_life", fetch_axa),
            ("sbi_index", fetch_sbi),
            ("mhi_stock", fetch_mhi_zaim),
            ("akatsuki_bond", fetch_akatsuki),
        ]

    for account_id, fn in jobs:
        try:
            rec = fn()
        except Exception as exc:
            rec = {"status": "error", "reason": str(exc)[:300]}
        sources[account_id] = rec
        print(f"# {account_id}: {rec.get('status')} {rec.get('reason') or rec.get('note') or ''}")

        if args.dry_run or rec.get("status") != "ok":
            continue
        upsert_snapshot(
            sb,
            account_id,
            float(rec["value_jpy"]),
            source="zaim" if account_id == "mhi_stock" else "weekly_web",
            note=rec.get("note"),
        )

    if not args.cloud_only and not args.dry_run:
        try:
            rec = fetch_tachibana(sb)
        except Exception as exc:
            rec = {"status": "error", "reason": str(exc)[:300]}
        sources["tachibana_trade"] = rec
        print(f"# tachibana_trade: {rec.get('status')} {rec.get('note') or rec.get('reason') or ''}")
        if rec.get("status") == "ok":
            upsert_snapshot(
                sb,
                "tachibana_trade",
                float(rec["value_jpy"]),
                source="trade_risk_state",
                note=rec.get("note"),
            )
    elif args.cloud_only and not args.dry_run:
        try:
            rec = fetch_tachibana(sb)
            sources["tachibana_trade"] = rec
            print(
                f"# tachibana_trade: {rec.get('status')} {rec.get('note') or rec.get('reason') or ''}"
            )
            if rec.get("status") == "ok":
                upsert_snapshot(
                    sb,
                    "tachibana_trade",
                    float(rec["value_jpy"]),
                    source="trade_risk_state",
                    note=rec.get("note"),
                )
        except Exception as exc:
            sources["tachibana_trade"] = {"status": "error", "reason": str(exc)[:300]}

    if (
        not args.cloud_only
        and not args.dry_run
        and sources.get("akatsuki_bond", {}).get("status") == "ok"
    ):
        zaim_script = REPO / "scripts" / "jarvis_zaim_akatsuki_weekly.py"
        try:
            zrc = subprocess.run(
                [
                    py_exe(),
                    str(zaim_script),
                    "--skip-fetch",
                    "--value",
                    str(int(sources["akatsuki_bond"]["value_jpy"])),
                    "--apply",
                    "--yes",
                    "--headless",
                ],
                cwd=str(REPO),
                timeout=240,
                check=False,
            )
            sources["akatsuki_zaim"] = {
                "status": "ok" if zrc.returncode == 0 else "error",
                "reason": f"exit={zrc.returncode}",
            }
        except Exception as exc:
            sources["akatsuki_zaim"] = {"status": "error", "reason": str(exc)[:300]}
        print(
            f"# akatsuki_zaim: {sources['akatsuki_zaim'].get('status')} "
            f"{sources['akatsuki_zaim'].get('reason')}"
        )

    ok_n = sum(1 for r in sources.values() if r.get("status") == "ok")
    err_n = sum(1 for r in sources.values() if r.get("status") == "error")
    skip_n = sum(1 for r in sources.values() if r.get("status") == "skipped")
    last_ok = err_n == 0 and ok_n > 0
    full_ok = (not args.cloud_only) and err_n == 0

    payload = {
        **prev,
        "iso_week": iso_week(),
        "cloud_only": args.cloud_only,
        "ok": ok_n,
        "error": err_n,
        "skipped": skip_n,
        "sources": sources,
        "last_success_at": now_iso() if last_ok else prev.get("last_success_at"),
        "last_ok": last_ok,
        "last_iso_week": iso_week() if last_ok else prev.get("last_iso_week"),
        "last_full_ok": full_ok if not args.cloud_only else prev.get("last_full_ok"),
        "last_full_iso_week": iso_week() if full_ok else prev.get("last_full_iso_week"),
        "last_full_at": now_iso() if full_ok else prev.get("last_full_at"),
        "finished_at": now_iso(),
    }

    if not args.dry_run:
        write_review(sb, sources)
        upsert_sync_meta(sb, {k: payload[k] for k in ("iso_week", "ok", "error", "skipped", "cloud_only")})
        save_state(payload)

    print(
        f"📎 資産週次: week={iso_week()} ok={ok_n} skipped={skip_n} error={err_n} last_ok={last_ok}"
    )
    return 0 if err_n == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
