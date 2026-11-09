#!/usr/bin/env python3
"""611 Cursor 使用量の自動取得（ログイン済みブラウザ・ルールのみ）。

cursor.com のダッシュボードが裏で呼ぶ JSON（非公開）を、普通の Google Chrome を
専用プロフィール（.jarvis_state/cursor_usage_chrome/、Git 管理外）で起動して読み、
％だけを .jarvis_state/cursor_usage_watch.json に反映する。
自動操作フラグ付きのブラウザは Google ログインで弾かれるため、Chrome 本体を
リモートデバッグポート付きで起動し、そこへ接続して読むだけにする。

  初回だけ（Chrome が開くので松野さんが手でログイン）:
    ~/selenium_env/venv/bin/python scripts/jarvis_cursor_usage_fetch.py --login
  週次（314 の土曜 runner から。画面は出ない）:
    ~/selenium_env/venv/bin/python scripts/jarvis_cursor_usage_fetch.py

守ること:
  - 非公開 API なので、失敗しても終了コード 0（他の処理を止めない）。state は手入力値のまま残す
  - Cookie・トークン・レスポンス本文はログにも state にも書かない。書くのは数値だけ
  - 読むだけ。設定変更・課金・送信はしない
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_PATH = REPO / ".jarvis_state" / "cursor_usage_watch.json"
PROFILE_DIR = REPO / ".jarvis_state" / "cursor_usage_chrome"
CHROME_BIN = os.environ.get(
    "JARVIS_CHROME_BIN", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
DASHBOARD_URL = "https://cursor.com/dashboard/spending"

# ページ内の fetch で読む（同一オリジンなので Cookie はブラウザが付ける。こちらでは触らない）
FETCH_JS = """
async () => {
  const out = {};
  const get = async (url, opts) => {
    try {
      const ac = new AbortController();
      const t = setTimeout(() => ac.abort(), 10000);  // 1 回 10 秒で打ち切る（ログイン待ちの固まり防止）
      const r = await fetch(url, Object.assign({credentials: 'include', signal: ac.signal}, opts || {}));
      clearTimeout(t);
      if (!r.ok) return {status: r.status};
      return {status: r.status, json: await r.json()};
    } catch (e) { return {status: -1}; }
  };
  out.summary = await get('/api/usage-summary');
  out.grok = await get('/api/dashboard/get-sand-usage-status',
    {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'});
  return out;
}
"""


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def _num(v: Any) -> float | None:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return round(max(0.0, min(100.0, n)), 1)


def _day(v: Any) -> str | None:
    """ISO 文字列またはミリ秒の数値を JST の日付へ。"""
    if v in (None, ""):
        return None
    try:
        if isinstance(v, (int, float)) or str(v).isdigit():
            dt = datetime.fromtimestamp(int(v) / 1000, timezone.utc)
        else:
            dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return dt.astimezone(JST).date().isoformat()
    except (ValueError, OSError, OverflowError):
        return None


def _when(v: Any) -> str | None:
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return dt.astimezone(JST).isoformat(timespec="minutes")
    except (TypeError, ValueError):
        return None


def parse_usage(raw: dict[str, Any]) -> dict[str, Any]:
    """2 本の JSON から数値だけ抜き出す。形が変わっていたら取れた分だけ返す。"""
    out: dict[str, Any] = {}
    s = (raw.get("summary") or {}).get("json")
    if isinstance(s, dict):
        plan = ((s.get("individualUsage") or {}).get("plan") or {})
        out["cursor_models_pct_used"] = _num(plan.get("autoPercentUsed"))
        out["other_models_pct_used"] = _num(plan.get("apiPercentUsed"))
        out["total_pct_used"] = _num(plan.get("totalPercentUsed"))
        out["billing_cycle_end"] = _day(s.get("billingCycleEnd"))
        if s.get("membershipType"):
            mt = str(s["membershipType"]).lower().replace("+", "_plus")
            out["plan"] = "pro_plus" if mt in ("pro_plus", "proplus") else mt
        od = ((s.get("individualUsage") or {}).get("onDemand") or {})
        if isinstance(od.get("enabled"), bool):
            out["on_demand_enabled"] = od["enabled"]
    g = (raw.get("grok") or {}).get("json")
    if isinstance(g, dict):
        out["grok_bot_weekly_pct"] = _num(g.get("usagePercent"))
        out["grok_bot_resets_at"] = _when(g.get("nextResetTimestampUtc"))
    return {k: v for k, v in out.items() if v is not None}


def statuses(raw: dict[str, Any]) -> dict[str, Any]:
    return {k: (raw.get(k) or {}).get("status") for k in ("summary", "grok")}


def apply_to_state(state: dict[str, Any], vals: dict[str, Any], st: dict[str, Any]) -> dict[str, Any]:
    out = dict(state)
    if vals.get("cursor_models_pct_used") is not None or vals.get("other_models_pct_used") is not None:
        out.update(vals)
        out["updated_at"] = now_iso()
        out["auto_fetched_at"] = now_iso()
        out["fetch_source"] = "auto"
        out.pop("last_fetch_error", None)
    else:
        if vals:  # Grok Bot だけ取れた等
            out.update(vals)
        out["last_fetch_error"] = {"at": now_iso(), "status": st}
    return out


def load_state() -> dict[str, Any]:
    try:
        d = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict[str, Any]) -> None:
    try:
        sys.path.insert(0, str(REPO / "scripts"))
        import jarvis_cursor_usage_watch as cw  # 判定（level/verdict）は既存ルールで付け直す
        state = cw.evaluate(state)
    except Exception:
        pass
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _free_port() -> int:
    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        return sk.getsockname()[1]


def chrome_args(port: int, headless: bool, profile: Path = PROFILE_DIR) -> list[str]:
    """普通の Chrome を専用プロフィールで。--enable-automation は付けない。"""
    args = [CHROME_BIN, f"--user-data-dir={profile}", f"--remote-debugging-port={port}",
            "--remote-debugging-address=127.0.0.1", "--no-first-run", "--no-default-browser-check"]
    if headless:
        args.append("--headless=new")
    args.append(DASHBOARD_URL)
    return args


def _wait_cdp(port: int, timeout: float = 30) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def _poll_pages(ctx) -> dict[str, Any] | None:
    """cursor.com を開いているタブの中で読む（ログイン画面中は読まない）。200 のタブを優先。"""
    last = None
    for pg in ctx.pages:
        url = pg.url or ""
        if url.startswith("https://cursor.com/") and "/login" not in url:
            try:
                got = pg.evaluate(FETCH_JS)
            except Exception:
                continue
            if statuses(got)["summary"] == 200:
                return got
            last = got
    return last


def fetch_raw(headless: bool, wait_login_sec: int = 0) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    if not Path(CHROME_BIN).exists():
        raise FileNotFoundError("Google Chrome が見つからない")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    proc = subprocess.Popen(chrome_args(port, headless), stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    try:
        if not _wait_cdp(port):
            raise TimeoutError("Chrome のデバッグポートに繋がらない")
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            ctx = browser.contexts[0]
            if not wait_login_sec:
                # 画面なしの Chrome は起動引数の URL を開かないことがあるので、自分で開く
                try:
                    ctx.new_page().goto(DASHBOARD_URL, wait_until="domcontentloaded", timeout=60_000)
                except Exception:
                    pass
            deadline = time.time() + max(wait_login_sec, 20)
            raw: dict[str, Any] = {"summary": {"status": 0}, "grok": {"status": 0}}
            if wait_login_sec:
                print("# Chrome でCursor にログインしてください（GitHub でログインしたアカウント）。"
                      f"最大 {wait_login_sec // 60} 分待ちます", file=sys.stderr)
            while time.time() < deadline:
                got = _poll_pages(ctx)
                if got:
                    raw = got
                    if statuses(raw)["summary"] == 200:
                        break
                time.sleep(3)
            # 強制終了だと更新されたログイン Cookie がディスクに書かれず、次回ログアウト扱いになる。
            # Chrome 自身に閉じさせて保存させる
            try:
                browser.new_browser_cdp_session().send("Browser.close")
            except Exception:
                pass
            return raw
    finally:
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


def main() -> int:
    ap = argparse.ArgumentParser(description="Cursor 使用量の自動取得（非公開 API・失敗しても 0）")
    ap.add_argument("--login", action="store_true", help="画面を出してログインを待つ（初回だけ）")
    ap.add_argument("--dry-run", action="store_true", help="state を書かない")
    args = ap.parse_args()
    try:
        raw = fetch_raw(headless=not args.login, wait_login_sec=600 if args.login else 0)
    except Exception as e:  # ブラウザ起動失敗など
        print(f"# cursor fetch skip: {type(e).__name__}", file=sys.stderr)
        if not args.dry_run:
            st = load_state()
            st["last_fetch_error"] = {"at": now_iso(), "status": type(e).__name__}
            save_state(st)
        return 0
    vals, st = parse_usage(raw), statuses(raw)
    del raw  # 本文はここで捨てる
    print(json.dumps({"status": st, "values": vals}, ensure_ascii=False))
    if not args.dry_run:
        save_state(apply_to_state(load_state(), vals, st))
    if st.get("summary") != 200:
        print("# cursor fetch: 未ログインか API 変更。手入力値を残した（--login で再ログイン）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
