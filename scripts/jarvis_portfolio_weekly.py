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


def run_json_script(
    args: list[str], timeout: int = 180, *, cwd: Path | None = None
) -> dict[str, Any]:
    env = os.environ.copy()
    r = subprocess.run(
        args,
        cwd=str(cwd or REPO),
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
    # JSON 行を末尾から探す（ログが混ざる場合に備える）
    for raw in reversed(line):
        raw = raw.strip()
        if raw.startswith("{") and raw.endswith("}"):
            return json.loads(raw)
    return json.loads(line[-1])


def fetch_sony() -> dict[str, Any]:
    """後方互換: 合計のみ。名義別は fetch_sony_by_account() を使う。"""
    multi = fetch_sony_by_account()
    if multi.get("status") != "ok":
        return multi
    return {
        "status": "ok",
        "value_jpy": int(multi["total_jpy"]),
        "note": multi.get("note") or "",
        "accounts": multi.get("accounts") or {},
    }


def fetch_sony_by_account() -> dict[str, Any]:
    """真治=sony_life / 千景=sony_life_chikage に分割して返す。"""
    if not (
        os.environ.get("SONYLIFE_USERNAME")
        or os.environ.get("SONYLIFE_USERNAME_1")
    ):
        return {"status": "skipped", "reason": "SONYLIFE_USERNAME 未設定"}
    script = FINANCE / "sony_life_surrender_value.py"
    if not script.is_file():
        return {"status": "skipped", "reason": "sony script missing"}
    data = run_json_script(
        [py_exe(), str(script), "--headless", "--json", "--save-debug"],
        timeout=360,
        cwd=FINANCE,
    )
    items = data.get("items") or []
    accounts: dict[str, dict[str, Any]] = {}
    loans: dict[str, dict[str, Any]] = {}
    # 既定: 1人目=真治, 2人目=千景（debug HTML の実績に合わせる）
    for it in items:
        idx = int(it.get("account_index") or 0)
        aid = "sony_life" if idx <= 1 else "sony_life_chikage"
        loan_aid = (
            "sony_life_policy_loan"
            if idx <= 1
            else "sony_life_chikage_policy_loan"
        )
        accounts[aid] = {
            "status": "ok",
            "value_jpy": int(it.get("value_jpy") or 0),
            "note": f"account{idx} {it.get('username') or ''}".strip(),
        }
        policy = int(it.get("policy_loan_jpy") or 0)
        auto = int(it.get("auto_premium_loan_jpy") or 0)
        loans[loan_aid] = {
            "status": "ok",
            "value_jpy": policy + auto,
            "note": f"契約者貸付{policy:,}+自動振替{auto:,}",
            "policy_loan_jpy": policy,
            "auto_premium_loan_jpy": auto,
        }
    if not accounts and data.get("value_jpy") is not None:
        accounts["sony_life"] = {
            "status": "ok",
            "value_jpy": int(data["value_jpy"]),
            "note": data.get("parser_mode") or "",
        }
        total_loan = int(data.get("total_loan_jpy") or 0)
        if total_loan or data.get("policy_loan_jpy") is not None:
            loans["sony_life_policy_loan"] = {
                "status": "ok",
                "value_jpy": total_loan
                or int(data.get("policy_loan_jpy") or 0)
                + int(data.get("auto_premium_loan_jpy") or 0),
                "note": "from aggregate",
            }
    return {
        "status": "ok",
        "total_jpy": int(data.get("value_jpy") or sum(a["value_jpy"] for a in accounts.values())),
        "note": data.get("parser_mode") or "",
        "accounts": accounts,
        "loans": loans,
    }


def fetch_bloomo() -> dict[str, Any]:
    if not (
        os.environ.get("BLOOMO_EMAIL")
        or os.environ.get("BLOOMO_USERNAME")
        or os.environ.get("BLOOMO_LOGIN_ID")
    ):
        return {"status": "skipped", "reason": "BLOOMO_EMAIL 未設定（.env.jarvis_private）"}
    script = REPO / "scripts" / "jarvis_bloomo_balance.py"
    if not script.is_file():
        return {"status": "skipped", "reason": "jarvis_bloomo_balance.py missing"}
    data = run_json_script(
        [py_exe(), str(script), "--headless", "--json"],
        timeout=240,
    )
    if data.get("status") and data.get("status") != "ok":
        return data
    return {
        "status": "ok",
        "value_jpy": int(data["value_jpy"]),
        "note": data.get("note") or data.get("parser_mode") or "",
    }


def _prudential_web_fetch_disabled() -> bool:
    return os.environ.get("PRUDENTIAL_WEB_FETCH_DISABLE", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def fetch_prudential_manual(account_id: str) -> dict[str, Any]:
    """手登録フォールバック（Web 未設定・失敗時）。"""
    env_key = {
        "prudential_life": "PRUDENTIAL_VALUE_JPY",
        "prudential_life_chikage": "PRUDENTIAL_CHIKAGE_VALUE_JPY",
        "prudential_life_policy_loan": "PRUDENTIAL_LOAN_JPY",
        "prudential_life_chikage_policy_loan": "PRUDENTIAL_CHIKAGE_LOAN_JPY",
    }.get(account_id)
    if not env_key:
        return {"status": "skipped", "reason": f"unknown account {account_id}"}
    raw = (os.environ.get(env_key) or "").strip().replace(",", "")
    if not raw:
        return {
            "status": "skipped",
            "reason": f"{env_key} 未設定",
        }
    try:
        value = int(float(raw))
    except ValueError:
        return {"status": "error", "reason": f"{env_key} が数値ではありません"}
    return {"status": "ok", "value_jpy": value, "note": f"env:{env_key}"}


def fetch_prudential_by_account() -> dict[str, Any]:
    """Myページ Web 取得（真治／千景）。未設定ならスキップ。"""
    if _prudential_web_fetch_disabled():
        return {
            "status": "skipped",
            "reason": "PRUDENTIAL_WEB_FETCH_DISABLE=1（手登録のみ）",
        }
    if not (
        os.environ.get("PRUDENTIAL_LOGIN_URL")
        and (
            os.environ.get("PRUDENTIAL_USERNAME_1")
            or os.environ.get("PRUDENTIAL_USERNAME")
        )
    ):
        return {
            "status": "skipped",
            "reason": "PRUDENTIAL_LOGIN_URL / USERNAME 未設定（手登録へフォールバック可）",
        }
    script = FINANCE / "prudential_life_surrender_value.py"
    if not script.is_file():
        return {"status": "skipped", "reason": "prudential script missing"}
    data = run_json_script(
        [py_exe(), str(script), "--headless", "--json", "--save-debug"],
        timeout=600,
        cwd=FINANCE,
    )
    items = data.get("items") or []
    accounts: dict[str, dict[str, Any]] = {}
    loans: dict[str, dict[str, Any]] = {}
    for it in items:
        idx = int(it.get("account_index") or 0)
        aid = "prudential_life" if idx <= 1 else "prudential_life_chikage"
        loan_aid = (
            "prudential_life_policy_loan"
            if idx <= 1
            else "prudential_life_chikage_policy_loan"
        )
        accounts[aid] = {
            "status": "ok",
            "value_jpy": int(it.get("value_jpy") or 0),
            "note": f"web account{idx}",
        }
        loan_v = int(
            it.get("policy_loan_jpy")
            or it.get("loan_jpy")
            or it.get("total_loan_jpy")
            or 0
        )
        if loan_v or "policy_loan_jpy" in it or "loan_jpy" in it:
            loans[loan_aid] = {
                "status": "ok",
                "value_jpy": loan_v,
                "note": "web policy loan",
            }
    if not accounts and data.get("value_jpy") is not None:
        accounts["prudential_life"] = {
            "status": "ok",
            "value_jpy": int(data["value_jpy"]),
            "note": data.get("parser_mode") or "web",
        }
    if not accounts:
        return {
            "status": data.get("status") or "error",
            "reason": data.get("reason")
            or data.get("error")
            or "prudential web 取得0件",
            "raw_note": data.get("note") or "",
        }
    return {
        "status": "ok",
        "total_jpy": int(
            data.get("value_jpy")
            or sum(a["value_jpy"] for a in accounts.values())
        ),
        "accounts": accounts,
        "loans": loans,
        "note": data.get("parser_mode") or "web",
    }


def fetch_prudential(account_id: str) -> dict[str, Any]:
    """互換: 単口座は手登録。Web 一括は fetch_prudential_by_account。"""
    return fetch_prudential_manual(account_id)

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
        timeout=300,
    )
    # 特別勘定 snap も更新（失敗しても評価は返す）
    try:
        import importlib.util

        alloc_path = REPO / "scripts" / "jarvis_insurance_allocations.py"
        spec = importlib.util.spec_from_file_location(
            "jarvis_insurance_allocations", alloc_path
        )
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            snap = mod.load_snap()
            snap.setdefault("accounts", {})
            prev = dict(snap["accounts"].get("axa_life") or {})
            funds = data.get("funds") or []
            if funds:
                prev["funds"] = funds
                prev["as_of"] = data.get("funds_as_of") or prev.get("as_of")
                prev["source"] = data.get("funds_source") or "web"
            else:
                prev["source"] = prev.get("source") or "manual_snapshot"
            prev["value_jpy"] = int(data["value_jpy"])
            snap["accounts"]["axa_life"] = prev
            mod.save_snap(snap)
    except Exception as exc:
        print(f"# axa allocation snap: {exc}", file=sys.stderr)
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
    if args.dry_run and not args.cloud_only:
        # ブラウザを起動せず、資格情報の有無だけ報告する
        checks = {
            "sony_life": bool(
                os.environ.get("SONYLIFE_USERNAME")
                or os.environ.get("SONYLIFE_USERNAME_1")
            ),
            "sony_life_chikage": bool(os.environ.get("SONYLIFE_USERNAME_2")),
            "bloomo": bool(
                os.environ.get("BLOOMO_EMAIL")
                or os.environ.get("BLOOMO_USERNAME")
                or os.environ.get("BLOOMO_LOGIN_ID")
            ),
            "prudential_life": bool(
                os.environ.get("PRUDENTIAL_VALUE_JPY")
                or (
                    not _prudential_web_fetch_disabled()
                    and os.environ.get("PRUDENTIAL_LOGIN_URL")
                    and (
                        os.environ.get("PRUDENTIAL_USERNAME_1")
                        or os.environ.get("PRUDENTIAL_USERNAME")
                    )
                )
            ),
            "prudential_life_chikage": bool(
                os.environ.get("PRUDENTIAL_CHIKAGE_VALUE_JPY")
                or (
                    not _prudential_web_fetch_disabled()
                    and os.environ.get("PRUDENTIAL_USERNAME_2")
                )
            ),
            "axa_life": bool(
                os.environ.get("AXA_MYAXA_ID") and os.environ.get("AXA_MYAXA_PASSWORD")
            ),
            "sbi_index": bool(
                os.environ.get("SBI_SEC_USER")
                and os.environ.get("SBI_SEC_LOGIN_PASSWORD")
            ),
            "akatsuki_bond": bool(
                (
                    os.environ.get("AKATSUKI_BRANCH_CODE")
                    and os.environ.get("AKATSUKI_ACCOUNT_NUMBER")
                    and os.environ.get("AKATSUKI_LOGIN_PASSWORD")
                )
                or (FINANCE / ".env.akatsuki").is_file()
            ),
            "mhi_stock": True,
        }
        for k, ok in checks.items():
            print(f"# dry-run {k}: {'creds_ok' if ok else 'missing_creds'}")
        print(
            f"📎 資産週次 dry-run: week={iso_week()} "
            f"creds_ok={sum(1 for v in checks.values() if v)}/{len(checks)} "
            "(ブラウザ未起動)"
        )
        return 0

    sb = None if args.dry_run else sb_client()
    sources: dict[str, Any] = {}

    jobs: list[tuple[str, Any]] = []
    if not args.cloud_only:
        jobs = [
            ("axa_life", fetch_axa),
            ("sbi_index", fetch_sbi),
            ("mhi_stock", fetch_mhi_zaim),
            ("akatsuki_bond", fetch_akatsuki),
            ("bloomo", fetch_bloomo),
        ]

    # ソニーは1回のログイン往復で名義別に分割
    if not args.cloud_only:
        try:
            sony_multi = fetch_sony_by_account()
        except Exception as exc:
            sony_multi = {"status": "error", "reason": str(exc)[:300]}
        if sony_multi.get("status") == "ok":
            for aid, rec in (sony_multi.get("accounts") or {}).items():
                sources[aid] = rec
                print(
                    f"# {aid}: {rec.get('status')} {rec.get('reason') or rec.get('note') or ''}"
                )
                if not args.dry_run and rec.get("status") == "ok":
                    upsert_snapshot(
                        sb,
                        aid,
                        float(rec["value_jpy"]),
                        source="weekly_web",
                        note=rec.get("note"),
                    )
            for aid, rec in (sony_multi.get("loans") or {}).items():
                sources[aid] = rec
                print(
                    f"# {aid}: {rec.get('status')} {rec.get('reason') or rec.get('note') or ''}"
                )
                if not args.dry_run and rec.get("status") == "ok":
                    upsert_snapshot(
                        sb,
                        aid,
                        float(rec["value_jpy"]),
                        source="weekly_web_loan",
                        note=rec.get("note"),
                    )
            if "sony_life_chikage" not in (sony_multi.get("accounts") or {}):
                sources["sony_life_chikage"] = {
                    "status": "skipped",
                    "reason": "SONYLIFE_USERNAME_2 未設定または取得0件",
                }
                print("# sony_life_chikage: skipped SONYLIFE_USERNAME_2 未設定または取得0件")
        else:
            sources["sony_life"] = sony_multi
            sources["sony_life_chikage"] = {
                "status": sony_multi.get("status") or "error",
                "reason": sony_multi.get("reason") or "sony parent failed",
            }
            print(
                f"# sony_life: {sony_multi.get('status')} "
                f"{sony_multi.get('reason') or sony_multi.get('note') or ''}"
            )

    # プルデンシャルも Web 一括 → 失敗時のみ手登録
    if not args.cloud_only:
        try:
            pru_multi = fetch_prudential_by_account()
        except Exception as exc:
            pru_multi = {"status": "error", "reason": str(exc)[:300]}
        pru_ids = (
            "prudential_life",
            "prudential_life_chikage",
            "prudential_life_policy_loan",
            "prudential_life_chikage_policy_loan",
        )
        if pru_multi.get("status") == "ok":
            for aid, rec in (pru_multi.get("accounts") or {}).items():
                sources[aid] = rec
                print(
                    f"# {aid}: {rec.get('status')} {rec.get('reason') or rec.get('note') or ''}"
                )
                if not args.dry_run and rec.get("status") == "ok":
                    upsert_snapshot(
                        sb,
                        aid,
                        float(rec["value_jpy"]),
                        source="weekly_web",
                        note=rec.get("note"),
                    )
            for aid, rec in (pru_multi.get("loans") or {}).items():
                sources[aid] = rec
                print(
                    f"# {aid}: {rec.get('status')} {rec.get('reason') or rec.get('note') or ''}"
                )
                if not args.dry_run and rec.get("status") == "ok":
                    upsert_snapshot(
                        sb,
                        aid,
                        float(rec["value_jpy"]),
                        source="weekly_web_loan",
                        note=rec.get("note"),
                    )
        else:
            print(
                f"# prudential_web: {pru_multi.get('status')} "
                f"{pru_multi.get('reason') or ''}"
            )
            for aid in pru_ids:
                rec = fetch_prudential_manual(aid)
                sources[aid] = rec
                print(
                    f"# {aid}: {rec.get('status')} {rec.get('reason') or rec.get('note') or ''}"
                )
                if not args.dry_run and rec.get("status") == "ok":
                    upsert_snapshot(
                        sb,
                        aid,
                        float(rec["value_jpy"]),
                        source="weekly_manual",
                        note=rec.get("note"),
                    )

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

    # 保険配分ビュー（スクレイプは fetch_axa 内で実施済み。ここでは表示用 merge）
    if not args.cloud_only:
        try:
            alloc_script = REPO / "scripts" / "jarvis_insurance_allocations.py"
            out = subprocess.run(
                [py_exe(), str(alloc_script), "--skip-web"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(REPO),
            )
            if out.stdout.strip():
                print(out.stdout.rstrip())
            if out.stderr.strip():
                print(out.stderr.rstrip(), file=sys.stderr)
        except Exception as exc:
            print(f"# insurance_allocations: {exc}", file=sys.stderr)

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
