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
ENV_PRIVATE = REPO / ".env.jarvis_private"


def load_private_env() -> None:
    """launchd の source 失敗でも動くよう、Python 側で .env.jarvis_private を読む。"""
    if not ENV_PRIVATE.is_file():
        return
    try:
        text = ENV_PRIVATE.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, _, val = line.partition("=")
        key = key.strip()
        if not key or not key.replace("_", "").isalnum():
            continue
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        # 既にシェルで入っている値は上書きしない（手動実行の上書きを尊重）
        if key not in os.environ or os.environ.get(key, "") == "":
            os.environ[key] = val


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def sony_web_hours_ok(now: datetime | None = None) -> tuple[bool, str]:
    """お客さまWEB / LIFEPLANNER WEB の目安は 9:00–17:30。"""
    n = now or datetime.now(JST)
    hm = n.hour * 60 + n.minute
    if hm < 9 * 60 or hm >= 17 * 60 + 30:
        return False, "ソニーお客さまWEBは目安 9:00–17:30（今回は時間外）"
    return True, ""


def axa_web_hours_ok(now: datetime | None = None) -> tuple[bool, str]:
    """MyAXA 積立金ページは営業日 5:00–8:00 がメンテナンス。"""
    n = now or datetime.now(JST)
    hm = n.hour * 60 + n.minute
    if 5 * 60 <= hm < 8 * 60:
        return False, "MyAXA 積立金は 5:00–8:00 メンテナンス（8:00以降に再実行）"
    return True, ""


def rec_from_exc(exc: BaseException) -> dict[str, Any]:
    msg = str(exc)[:300]
    hours = (
        "サービス時間外",
        "時間外／メンテナンス",
        "時間外/メンテナンス",
        "5:00–8:00",
        "9:00–17:30",
    )
    if any(x in msg for x in hours):
        return {"status": "skipped", "reason": msg}
    return {"status": "error", "reason": msg}


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
    ok, reason = sony_web_hours_ok()
    if not ok:
        return {"status": "skipped", "reason": reason}
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


def _mf_bloomo_ready() -> bool:
    mf = REPO / "scripts" / "jarvis_mf_bloomo_balance.py"
    if not mf.is_file():
        return False
    mf_state = (os.environ.get("MONEYFORWARD_STORAGE_STATE") or "").strip()
    state = Path(mf_state).expanduser() if mf_state else (
        REPO / ".jarvis_state" / "mf_me_storage_state.json"
    )
    if state.is_file():
        return True
    prof_raw = (os.environ.get("MONEYFORWARD_BROWSER_PROFILE") or "").strip()
    profile = Path(prof_raw).expanduser() if prof_raw else (
        REPO / ".jarvis_state" / "mf_me_browser_profile"
    )
    if profile.is_dir() and any(profile.iterdir()):
        return True
    return bool(
        (os.environ.get("MONEYFORWARD_EMAIL") or "").strip()
        and (os.environ.get("MONEYFORWARD_PASSWORD") or "").strip()
    )


def fetch_bloomo() -> dict[str, Any]:
    """優先: マネーフォワード ME。失敗時のみ直スクレイプ（BLOOMO_*）。"""
    mf_err = ""
    if _mf_bloomo_ready():
        mf = REPO / "scripts" / "jarvis_mf_bloomo_balance.py"
        data = run_json_script(
            [py_exe(), str(mf), "--headless", "--json"],
            timeout=240,
        )
        if data.get("status") == "ok":
            return {
                "status": "ok",
                "value_jpy": int(data["value_jpy"]),
                "note": data.get("note") or "moneyforward",
                "source": "moneyforward",
            }
        if data.get("status") != "skipped":
            mf_err = str(data.get("reason") or data.get("status") or "mf_error")

    if not (
        os.environ.get("BLOOMO_EMAIL")
        or os.environ.get("BLOOMO_USERNAME")
        or os.environ.get("BLOOMO_LOGIN_ID")
    ):
        if mf_err:
            return {"status": "error", "reason": f"MF取得失敗: {mf_err}"}
        return {
            "status": "skipped",
            "reason": "MFセッション未設定かつ BLOOMO_EMAIL 未設定",
        }
    script = REPO / "scripts" / "jarvis_bloomo_balance.py"
    if not script.is_file():
        return {"status": "skipped", "reason": "jarvis_bloomo_balance.py missing"}
    data = run_json_script(
        [py_exe(), str(script), "--headless", "--json"],
        timeout=240,
    )
    if data.get("status") and data.get("status") != "ok":
        return data
    note = data.get("note") or data.get("parser_mode") or ""
    if mf_err:
        note = f"{note}; mf_fallback={mf_err}"
    return {
        "status": "ok",
        "value_jpy": int(data["value_jpy"]),
        "note": note,
        "source": "bloomo_direct",
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
    ok, reason = axa_web_hours_ok()
    if not ok:
        return {"status": "skipped", "reason": reason}
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
    """インデックス枠は Zaim「SBI 証券」を正本（サイト直ログインはフォールバックしない）。"""
    script = REPO / "scripts" / "jarvis_zaim_sbi_balance.py"
    data = run_json_script([py_exe(), str(script), "--json"], timeout=180)
    if data.get("status") != "ok":
        return {
            "status": "error",
            "reason": data.get("reason") or "Zaim SBI証券が取れません",
        }
    return {
        "status": "ok",
        "value_jpy": int(data["value_jpy"]),
        "note": data.get("note") or "",
        "source": "zaim",
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
    """ホーム鮮度カード用。ソース別 status を必ず含める（Vercel は Mac JSON を読めない）。"""
    ts = now_iso()
    sources_raw = payload.get("sources") or {}
    sources_brief: dict[str, Any] = {}
    for aid, rec in sources_raw.items():
        if not isinstance(rec, dict):
            continue
        sources_brief[str(aid)] = {
            "status": rec.get("status") or ("ok" if rec.get("ok") else "unknown"),
            "reason": str(rec.get("reason") or rec.get("error") or "")[:120],
        }
    meta = {
        "iso_week": payload.get("iso_week"),
        "ok": payload.get("ok"),
        "error": payload.get("error"),
        "skipped": payload.get("skipped"),
        "cloud_only": payload.get("cloud_only"),
        "last_full_ok": payload.get("last_full_ok"),
        "last_full_at": payload.get("last_full_at"),
        "last_full_iso_week": payload.get("last_full_iso_week"),
        "finished_at": payload.get("finished_at"),
        "sources": sources_brief,
    }
    raw = json.dumps(meta, ensure_ascii=False)
    # sync_meta.value は長文可。sources を落とさないよう余裕を持たせる
    if len(raw) > 12000:
        raw = json.dumps({**meta, "sources": {k: {"status": v.get("status")} for k, v in sources_brief.items()}}, ensure_ascii=False)[:12000]
    sb.table("sync_meta").upsert(
        [
            {"key": "portfolio_weekly_at", "value": ts, "updated_at": ts},
            {
                "key": "portfolio_weekly_summary",
                "value": raw,
                "updated_at": ts,
            },
        ],
        on_conflict="key",
    ).execute()


def ingest_sony(sb, sources: dict[str, Any], *, dry_run: bool) -> None:
    """ソニーはバッチ後半（9:00 開店直後の混雑を避ける）。"""
    try:
        sony_multi = fetch_sony_by_account()
    except Exception as exc:
        sony_multi = rec_from_exc(exc)
    if sony_multi.get("status") == "ok":
        for aid, rec in (sony_multi.get("accounts") or {}).items():
            sources[aid] = rec
            print(
                f"# {aid}: {rec.get('status')} {rec.get('reason') or rec.get('note') or ''}"
            )
            if not dry_run and rec.get("status") == "ok":
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
            if not dry_run and rec.get("status") == "ok":
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
        return
    sources["sony_life"] = sony_multi
    sources["sony_life_chikage"] = {
        "status": sony_multi.get("status") or "error",
        "reason": sony_multi.get("reason") or "sony parent failed",
    }
    print(
        f"# sony_life: {sony_multi.get('status')} "
        f"{sony_multi.get('reason') or sony_multi.get('note') or ''}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="資産全体 週次収集")
    ap.add_argument("--cloud-only", action="store_true", help="Yahoo / 既存DBのみ（GHA向け）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    load_private_env()

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
                _mf_bloomo_ready()
                or os.environ.get("BLOOMO_EMAIL")
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
            "sbi_index": True,  # Zaim「SBI 証券」正本（サイト直ログイン不要）
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
            rec = rec_from_exc(exc)
        sources[account_id] = rec
        print(f"# {account_id}: {rec.get('status')} {rec.get('reason') or rec.get('note') or ''}")

        if args.dry_run or rec.get("status") != "ok":
            continue
        upsert_snapshot(
            sb,
            account_id,
            float(rec["value_jpy"]),
            source=(
                "zaim"
                if account_id in ("mhi_stock", "sbi_index")
                or rec.get("source") == "zaim"
                else "weekly_web"
            ),
            note=rec.get("note"),
        )

    # ソニーは他サイトのあと（9:00 開店直後の混雑回避）
    if not args.cloud_only:
        ingest_sony(sb, sources, dry_run=args.dry_run)

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

    # 証券内訳（SBI=Zaim／Bloomo=MF。失敗しても週次本体は継続）
    if not args.cloud_only and not args.dry_run:
        try:
            hold_script = REPO / "scripts" / "jarvis_securities_holdings.py"
            out = subprocess.run(
                [py_exe(), str(hold_script), "--push-db"],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(REPO),
            )
            if out.stdout.strip():
                print(out.stdout.rstrip())
            if out.stderr.strip():
                print(out.stderr.rstrip(), file=sys.stderr)
        except Exception as exc:
            print(f"# securities_holdings: {exc}", file=sys.stderr)

    # 流動性・週次家計（銀行残高＋収支要約）
    if not args.cloud_only and not args.dry_run:
        try:
            liq_script = REPO / "scripts" / "jarvis_liquidity_weekly.py"
            out = subprocess.run(
                [py_exe(), str(liq_script), "--json"],
                capture_output=True,
                text=True,
                timeout=240,
                cwd=str(REPO),
            )
            if out.stdout.strip():
                print(out.stdout.rstrip())
            if out.stderr.strip():
                print(out.stderr.rstrip(), file=sys.stderr)
            sources["liquidity_weekly"] = {
                "status": "ok" if out.returncode == 0 else "error",
                "reason": f"exit={out.returncode}",
            }
        except Exception as exc:
            sources["liquidity_weekly"] = {"status": "error", "reason": str(exc)[:300]}
            print(f"# liquidity_weekly: {exc}", file=sys.stderr)

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
                capture_output=True,
                text=True,
            )
            if zrc.stdout:
                print(zrc.stdout.rstrip())
            reason = f"exit={zrc.returncode}"
            if zrc.returncode != 0:
                err = (zrc.stderr or zrc.stdout or "").strip().splitlines()
                if err:
                    reason = err[-1][:300]
                if zrc.stderr:
                    print(zrc.stderr.rstrip(), file=sys.stderr)
            sources["akatsuki_zaim"] = {
                "status": "ok" if zrc.returncode == 0 else "error",
                "reason": reason,
            }
        except Exception as exc:
            sources["akatsuki_zaim"] = {"status": "error", "reason": str(exc)[:300]}
        print(
            f"# akatsuki_zaim: {sources['akatsuki_zaim'].get('status')} "
            f"{sources['akatsuki_zaim'].get('reason')}"
        )

    if (
        not args.cloud_only
        and not args.dry_run
        and sources.get("bloomo", {}).get("status") == "ok"
    ):
        zaim_script = REPO / "scripts" / "jarvis_zaim_bloomo_weekly.py"
        try:
            zrc = subprocess.run(
                [
                    py_exe(),
                    str(zaim_script),
                    "--skip-fetch",
                    "--value",
                    str(int(sources["bloomo"]["value_jpy"])),
                    "--apply",
                    "--yes",
                    "--headless",
                ],
                cwd=str(REPO),
                timeout=240,
                check=False,
                capture_output=True,
                text=True,
            )
            if zrc.stdout:
                print(zrc.stdout.rstrip())
            reason = f"exit={zrc.returncode}"
            if zrc.returncode != 0:
                err = (zrc.stderr or zrc.stdout or "").strip().splitlines()
                if err:
                    reason = err[-1][:300]
                if zrc.stderr:
                    print(zrc.stderr.rstrip(), file=sys.stderr)
            sources["bloomo_zaim"] = {
                "status": "ok" if zrc.returncode == 0 else "error",
                "reason": reason,
            }
        except Exception as exc:
            sources["bloomo_zaim"] = {"status": "error", "reason": str(exc)[:300]}
        print(
            f"# bloomo_zaim: {sources['bloomo_zaim'].get('status')} "
            f"{sources['bloomo_zaim'].get('reason')}"
        )

    ok_n = sum(1 for r in sources.values() if r.get("status") == "ok")
    err_n = sum(1 for r in sources.values() if r.get("status") == "error")
    skip_n = sum(1 for r in sources.values() if r.get("status") == "skipped")
    hours_skip = any(
        r.get("status") == "skipped"
        and any(
            x in str(r.get("reason") or "")
            for x in ("時間外", "メンテナンス", "9:00", "5:00–8:00")
        )
        for r in sources.values()
    )
    last_ok = err_n == 0 and ok_n > 0
    full_ok = (not args.cloud_only) and err_n == 0 and not hours_skip

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
        upsert_sync_meta(sb, payload)
        save_state(payload)

    print(
        f"📎 資産週次: week={iso_week()} ok={ok_n} skipped={skip_n} error={err_n} "
        f"last_ok={last_ok} last_full_ok={full_ok}"
    )
    return 0 if err_n == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
