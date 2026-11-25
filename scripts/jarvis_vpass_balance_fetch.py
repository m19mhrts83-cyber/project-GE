#!/usr/bin/env python3
"""Vpass（三井住友カード会員サイト）Myページから Vポイント残高と最短有効期限を読み取り専用で取る（614・2026-11-25）。

位置づけ: Tサイト履歴の「基準日つき残高」の確認用。付与履歴は Vpass では取れない
（調査 2026-11-25: ID連携後の履歴は Vサイトへ誘導される）。ここは残高の照合だけ。
  - 取るもの: Myページの『ご利用状況 ◯年◯月◯日現在』（基準日）・Vポイント残高・最短有効期限
  - 保存: .jarvis_state/vpoint_vpass_balance.json（非公開側。取得日時・基準日・取得元・Tサイトとの照合結果）
  - 照合: 最新の Tサイト履歴（vpoint_tsite_history_*.json）と、基準日が同日なら残高の一致を見る。
          別の日なら「照合できない」（不一致とは書かない）
  - 触らないもの: ポイント交換・支払・チャージ・設定変更は一切しない。ログインとMyページの閲覧のみ
  - routine への組み込みはしない（P1 = PR #647 のマージ後に別 PR で）

認証: .env.jarvis_private の VPASS_ID / VPASS_PASSWORD（値は出さない）。
プロファイル: ~/.jarvis_state/chrome_vpass_audit（jarvis_vpoint_audit.py と同じ流儀）。

使い方:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_vpass_balance_fetch.py
  ~/selenium_env/venv/bin/python scripts/jarvis_vpass_balance_fetch.py --json --no-save
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_DIR = REPO / ".jarvis_state"
OUT_PATH = STATE_DIR / "vpoint_vpass_balance.json"
TSITE_GLOB = "vpoint_tsite_history_*.json"
SOURCE = "vpass_mypage"

_ASOF_RE = re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*現在")
# 『Vポイント』の直後に数字＋pt が来る行だけ（キャンペーン文の「Vポイントが…」は拾わない）
_BALANCE_RE = re.compile(r"Vポイント\s*([0-9][0-9,]*)\s*pt", re.I)
_EXPIRY_RE = re.compile(r"最短有効期限\s*[：:]\s*(20\d{2})\s*[/年.]\s*(\d{1,2})\s*[/月.]\s*(\d{1,2})")


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def _to_date(y: str, m: str, d: str) -> str | None:
    try:
        return date(int(y), int(m), int(d)).isoformat()
    except ValueError:
        return None


def parse_mypage_balance(text: str) -> dict[str, Any]:
    """Myページの本文から基準日・残高・最短有効期限を取る。読めない項目は None。"""
    asof = None
    m = _ASOF_RE.search(text or "")
    if m:
        asof = _to_date(*m.groups())
    balance = None
    m = _BALANCE_RE.search(text or "")
    if m:
        balance = int(m.group(1).replace(",", ""))
    expiry = None
    m = _EXPIRY_RE.search(text or "")
    if m:
        expiry = _to_date(*m.groups())
    return {"asof": asof, "balance_pt": balance, "nearest_expiry": expiry}


def latest_tsite_history(state_dir: Path | None = None) -> dict[str, Any] | None:
    state_dir = state_dir or STATE_DIR
    files = sorted(state_dir.glob(TSITE_GLOB), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in files:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            return data
    return None


def tsite_asof(hist: dict[str, Any] | None) -> str | None:
    raw = str((hist or {}).get("fetched_at") or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(JST)
    return dt.date().isoformat()


def compare_with_tsite(vpass_asof: str | None, vpass_balance: int | None,
                       hist: dict[str, Any] | None) -> dict[str, Any]:
    """基準日が同日の時だけ残高の一致を見る。match: True/False/None（照合できない）。"""
    t_asof = tsite_asof(hist)
    t_bal = (hist or {}).get("balance_pt")
    out: dict[str, Any] = {
        "tsite_asof": t_asof,
        "tsite_balance_pt": t_bal if isinstance(t_bal, int) else None,
        "same_day": None,
        "match": None,
        "reason": "",
    }
    if hist is None:
        out["reason"] = "Tサイト履歴なし"
    elif vpass_asof is None or vpass_balance is None:
        out["reason"] = "Vpass の基準日または残高が読めない"
    elif t_asof is None or out["tsite_balance_pt"] is None:
        out["reason"] = "Tサイトの基準日または残高が読めない"
    else:
        out["same_day"] = vpass_asof == t_asof
        if not out["same_day"]:
            out["reason"] = f"基準日が違う（Vpass {vpass_asof} / Tサイト {t_asof}）ので照合しない"
        else:
            out["match"] = vpass_balance == out["tsite_balance_pt"]
            out["reason"] = "一致" if out["match"] else "同日だが残高が違う"
    return out


def build_record(parsed: dict[str, Any], fetched_at: str,
                 hist: dict[str, Any] | None) -> dict[str, Any]:
    ok = parsed.get("asof") is not None and parsed.get("balance_pt") is not None
    return {
        "ok": ok,
        "fetched_at": fetched_at,
        "asof": parsed.get("asof"),
        "balance_pt": parsed.get("balance_pt"),
        "nearest_expiry": parsed.get("nearest_expiry"),
        "source": SOURCE,
        "tsite_check": compare_with_tsite(parsed.get("asof"), parsed.get("balance_pt"), hist),
    }


def save_verified(record: dict[str, Any], path: Path | None = None) -> bool:
    """保存して読み戻し、取得日時が一致することを確認する。"""
    path = path or OUT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        back = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return back.get("fetched_at") == record.get("fetched_at") and back.get("balance_pt") == record.get("balance_pt")


def scrape_mypage_text() -> str:
    """ログイン → Myページ本文。ログインとMyページ閲覧のみ（クリックはログインとカード選択だけ）。"""
    from playwright.sync_api import sync_playwright

    from car_loan.chrome_cdp import cdp_ready, start_cdp_chrome, stop_cdp_chrome
    from car_loan.env_state import ENV_FILE, load_env
    import jarvis_vpass_payment_fetch as pay
    import jarvis_vpoint_audit as audit

    env = load_env(ENV_FILE)
    vid = (env.get("VPASS_ID") or "").strip()
    vpw = (env.get("VPASS_PASSWORD") or "").strip()
    if not vid or not vpw:
        raise RuntimeError("未設定: VPASS_ID / VPASS_PASSWORD")

    start_cdp_chrome(audit.CDP_PORT, audit.PROFILE, audit.LOGIN_URL)
    try:
        if not cdp_ready(audit.CDP_PORT):
            raise RuntimeError(f"CDP {audit.CDP_PORT} not ready")
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{audit.CDP_PORT}")
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            audit._login(page, vid, vpw)
            page.goto(audit.MYPAGE_URL, wait_until="domcontentloaded", timeout=90000)
            time.sleep(1.5)
            text = audit._body(page, 20000)
            if "アクセス集中" in text or "つながりにくい" in text:
                raise RuntimeError("Vpass アクセス集中（Myページ）")
            if parse_mypage_balance(text)["balance_pt"] is None:
                # カード選択画面が挟まる場合だけ、既存の選択処理を1回使う
                pay._select_olive_inf_if_needed(page)
                page.goto(audit.MYPAGE_URL, wait_until="domcontentloaded", timeout=90000)
                time.sleep(1.5)
                text = audit._body(page, 20000)
            return text
    finally:
        stop_cdp_chrome(audit.PROFILE, audit.CDP_PORT, force=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Vpass Myページから Vポイント残高（基準日つき）を取る")
    ap.add_argument("--json", action="store_true", help="結果を JSON で出す（残高の実額を含む。ログに残さない）")
    ap.add_argument("--no-save", action="store_true", help="state に保存しない")
    args = ap.parse_args(argv)

    try:
        text = scrape_mypage_text()
    except Exception as e:  # noqa: BLE001 - 失敗は1行で返す
        print(f"⚠️ Vpass 残高の取得に失敗: {e}", file=sys.stderr)
        return 1
    rec = build_record(parse_mypage_balance(text), now_iso(), latest_tsite_history())
    if not rec["ok"]:
        # 画面の写しは出さない（残高を含むため）。形が変わった合図だけ返す
        print("⚠️ Myページから基準日・残高を読めませんでした（画面の形が変わった可能性）", file=sys.stderr)
        return 2
    saved = True
    if not args.no_save:
        saved = save_verified(rec)
    if args.json:
        print(json.dumps(rec, ensure_ascii=False, indent=2))
    else:
        chk = rec["tsite_check"]
        print(
            f"✅ Vpass残高 取得OK 基準日={rec['asof']} 最短有効期限={rec['nearest_expiry']} "
            f"Tサイト照合={chk['reason']} 保存={'読み戻しOK' if saved and not args.no_save else ('なし' if args.no_save else '失敗')}"
        )
    return 0 if saved else 3


if __name__ == "__main__":
    sys.exit(main())
