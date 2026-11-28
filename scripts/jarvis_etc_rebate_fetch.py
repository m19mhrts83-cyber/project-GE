#!/usr/bin/env python3
"""
ETC 平日朝夕・還元額の自動取得（smile-etc）→ etc_monthly → ダッシュボード。

公式（NEXCO / smile-etc Q&A）:
  利用月（1日〜末日）の対象走行 → 翌月20日に還元額付与。

定例:
  launchd 毎月 20〜26日 09:30 JST（付与当日〜遅延吸収）。
  朝オープン取りこぼしも jarvis_morning_mac_refresh から拾う。

使い方:
  python scripts/jarvis_etc_rebate_fetch.py --dry-run
  python scripts/jarvis_etc_rebate_fetch.py --apply --push
  python scripts/jarvis_etc_rebate_fetch.py --target-month 2026-07 --apply --push --force
  # --push → /etc 投影 ＋ Slack #report（614）。Slackだけ切る: --no-slack
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_614_display as display614  # noqa: E402
import jarvis_614_ops as ops614  # noqa: E402
import jarvis_614_runlog as runlog614  # noqa: E402
import jarvis_614_verified_state as vs  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_PATH = REPO / ".jarvis_state" / "etc_monthly.json"
PRIVATE_ENV = REPO / ".env.jarvis_private"
LOGIN_URL = (
    "https://www2.smile-etc.jp/NASApp/etcmlg/MlgReq"
    "?gvlddpef=1013000000&mdwsetmb=1013000000"
)
REBATE_URL = (
    "https://www2.smile-etc.jp/NASApp/etcmlg/MlgReq"
    "?gvlddpef=1015000000&mdwsetmb=1015000000"
)
POINTS_URL = (
    "https://www2.smile-etc.jp/NASApp/etcmlg/MlgReq"
    "?gvlddpef=1014000000&mdwsetmb=1014000000&H_KBN=NEXCO"
)

# 付与日は翌月20日。表示遅れを見て 20〜26 を定例窓とする（既存ウィンドウBと整合）。
AUTO_WINDOW_DAYS = frozenset(range(20, 27))


def load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$", line)
        if m and not line.lstrip().startswith("#"):
            out[m.group(1)] = m.group(2).strip().strip("\"'")
    return out


def load_state() -> dict[str, Any]:
    if STATE_PATH.is_file():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"disabled": False, "rebate_history": []}


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def save_state_verified(state: dict[str, Any]) -> dict[str, Any]:
    """tmp→置換→読み戻し照合。失敗時は取得済みの結果を非公開の pending に残し、保存だけ1回やり直す。"""
    return vs.save_json_verified(
        STATE_PATH, state, pending_path=STATE_PATH.with_name(STATE_PATH.stem + ".pending.json"),
        remedy_system="etc",
    )


def month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def add_months(ym: str, delta: int) -> str:
    y, m = map(int, ym.split("-"))
    m += delta
    while m > 12:
        m -= 12
        y += 1
    while m < 1:
        m += 12
        y -= 1
    return f"{y}-{m:02d}"


def ym_label(ym: str) -> str:
    """smile-etc 画面は『2026年08月分』のように月がゼロ埋め。"""
    y, m = ym.split("-")
    return f"{y}年{int(m):02d}月"


def parse_label(label: str) -> tuple[int, int] | None:
    """『2026年08月』→ (2026, 8)。読めなければ None。"""
    m = re.match(r"^\s*(\d{4})年(\d{1,2})月", label or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def classify_unavailable(first_label: str, grant_label: str) -> str:
    """付与月の明細を開けなかった時の分類。

    画面の最新の月が付与月より前＝まだ付与・掲載されていない → 'waiting'（取得待ち）。
    月が読めない・ログインできていない・付与月より後ろしか無い等は 'failed'（技術障害）。"""
    f, g = parse_label(first_label), parse_label(grant_label)
    return "waiting" if f and g and f < g else "failed"


def validate_scraped(scraped: dict[str, Any], target: str) -> str | None:
    """取得結果が対象月のものか確かめる。問題があれば理由、なければ None（古い月・別の月は完了扱いにしない）。"""
    if scraped.get("target_month") != target:
        return f"対象月が一致しません（要求 {target}／取得 {scraped.get('target_month')}）"
    if scraped.get("grant_month") != add_months(target, 1):
        return "付与月が対象月の翌月と一致しません"
    y = scraped.get("rebate_yen")
    if not isinstance(y, int) or isinstance(y, bool) or y < 0:
        return "還元額が数値として確認できません"
    return None


def default_target_month(now: datetime) -> str | None:
    """定例窓（20〜26日）なら前月＝直前に付与された利用月。それ以外は None。"""
    if now.day not in AUTO_WINDOW_DAYS:
        return None
    return add_months(month_key(now), -1)


def history_has(state: dict[str, Any], target: str) -> bool:
    for h in state.get("rebate_history") or []:
        if isinstance(h, dict) and h.get("target_month") == target and h.get("rebate_yen") is not None:
            return True
    return False


def rate_from_trip_count(count: int | None) -> int | None:
    if count is None:
        return None
    if count <= 4:
        return 0
    if count <= 9:
        return 30
    return 50


def upsert_rebate_history(state: dict[str, Any], result: dict[str, Any]) -> None:
    target = result.get("target_month")
    if not target:
        return
    entry = {
        "target_month": target,
        "rebate_yen": result.get("rebate_yen"),
        "asayu_trip_count": result.get("asayu_trip_count"),
        "asayu_rate_pct": result.get("asayu_rate_pct"),
        "savings_yen": result.get("savings_yen"),
        "at": result.get("at"),
        "note": result.get("note") or "",
        "source": result.get("source") or "smile-etc_auto",
    }
    hist = [h for h in (state.get("rebate_history") or []) if isinstance(h, dict)]
    hist = [h for h in hist if h.get("target_month") != target]
    hist.append(entry)
    hist.sort(key=lambda h: str(h.get("target_month") or ""), reverse=True)
    state["rebate_history"] = hist[:24]


def parse_tokuten_yen(text: str) -> int | None:
    """還元額明細本文から『特典 … 平日朝夕』金額を取る。"""
    # 例: 特典 5,190 … [平日朝夕割引（ＮＥＸＣＯ）]
    m = re.search(
        r"特典\s*([0-9,]+).*?平日朝夕",
        text,
        flags=re.S,
    )
    if m:
        return int(m.group(1).replace(",", ""))
    m2 = re.search(r"平日朝夕割引[^0-9]{0,40}?([0-9,]+)\s*円", text)
    if m2:
        return int(m2.group(1).replace(",", ""))
    # 特典行のみ（平日朝夕表記が別セル）
    m3 = re.search(r"特典\s*([0-9,]+)", text)
    if m3 and "特典" in text:
        return int(m3.group(1).replace(",", ""))
    return None


def parse_opening_balance(text: str) -> int | None:
    """
    特典行が欠ける月のフォールバック。
    最初の『利用』行の（還元額利用絶対値 + 残高）＝付与直後の開始残高。
    """
    pairs = re.findall(r"-([0-9,]+)\s+([0-9,]+)\s+確定", text)
    if not pairs:
        return None
    first_use = int(pairs[0][0].replace(",", ""))
    first_bal = int(pairs[0][1].replace(",", ""))
    return first_use + first_bal


def parse_nexco_points_for_usage(text: str, usage_ym: str) -> int | None:
    """ポイント明細の『2026年07月分』行のプラスポイント。"""
    label = ym_label(usage_ym)
    # 例: 26/08/20  2026年07月分  2028/03  2,574    3,983
    m = re.search(
        rf"{re.escape(label)}分\s+(?:\d{{4}}/\d{{2}}\s+)?([0-9,]+)",
        text,
    )
    if m:
        return int(m.group(1).replace(",", ""))
    return None


def scrape_rebate(
    *,
    mileage_id: str,
    password: str,
    target_month: str,
    headless: bool = True,
) -> dict[str, Any]:
    """smile-etc から target_month（利用月）の還元額を取得。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError("playwright が必要です（selenium_env）") from e

    grant_month = add_months(target_month, 1)
    grant_label = ym_label(grant_month)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page(locale="ja-JP")
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        page.fill("input[name=mlgloginid]", mileage_id)
        page.fill("input[name=mlgpassword]", password)
        page.click("input[type=submit]")
        page.wait_for_timeout(2500)

        page.goto(REBATE_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1200)

        found = False
        first_label = None
        for _ in range(10):
            body = page.inner_text("body")
            m = re.search(r"(20\d{2}年\d{1,2}月)分", body)
            cur = m.group(1) if m else ""
            if first_label is None:
                first_label = cur
            if cur == grant_label:
                found = True
                break
            prev = page.locator("a:has-text('前月')")
            if prev.count() == 0:
                break
            prev.first.click()
            page.wait_for_timeout(1500)
        if not found:
            browser.close()
            kind = classify_unavailable(first_label or "", grant_label)
            return {
                "ok": False,
                "kind": kind,
                "error": (
                    f"還元額明細の最新は {first_label} で、{grant_label}分はまだ掲載されていません（付与前）"
                    if kind == "waiting"
                    else f"還元額明細で {grant_label}分 を開けませんでした"
                ),
                "target_month": target_month,
                "grant_month": grant_month,
            }

        rebate_text = page.inner_text("body")
        method = "tokuten"
        yen = parse_tokuten_yen(rebate_text)
        if yen is None:
            yen = parse_opening_balance(rebate_text)
            method = "opening_balance"
        if yen is None:
            browser.close()
            return {
                "ok": False,
                "kind": "waiting",  # 月の明細は開けたが特典行も開始残高も無い＝付与前
                "error": (
                    f"{grant_label}分に特典行も開始残高も取れません。"
                    "付与前（翌月20日前）の可能性あり"
                ),
                "target_month": target_month,
                "grant_month": grant_month,
                "method": method,
            }

        # NEXCO ポイント（参考）
        nexco_pts = None
        try:
            page.goto(POINTS_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1200)
            pts_text = page.inner_text("body")
            nexco_pts = parse_nexco_points_for_usage(pts_text, target_month)
        except Exception:
            nexco_pts = None

        browser.close()

    note_bits = [
        f"smile-etc 自動取得: 利用月 {target_month} → 付与月 {grant_month}（翌月20日ルール）",
        f"取得方法={method}",
    ]
    if nexco_pts is not None:
        note_bits.append(f"NEXCOポイント（{target_month}分）+{nexco_pts:,}")
    if method == "opening_balance":
        note_bits.append("特典行なしのため還元額明細の開始残高から確定")

    return {
        "ok": True,
        "target_month": target_month,
        "grant_month": grant_month,
        "rebate_yen": yen,
        "savings_yen": yen,
        "asayu_trip_count": None,
        "asayu_rate_pct": None,
        "method": method,
        "nexco_points": nexco_pts,
        "note": "。".join(note_bits),
        "source": "smile-etc_auto",
    }


def apply_result(state: dict[str, Any], scraped: dict[str, Any], now: datetime) -> dict[str, Any]:
    result = {
        "at": now.isoformat(),
        "ok": True,
        "target_month": scraped["target_month"],
        "rebate_yen": scraped["rebate_yen"],
        "asayu_trip_count": scraped.get("asayu_trip_count"),
        "asayu_rate_pct": scraped.get("asayu_rate_pct")
        or rate_from_trip_count(scraped.get("asayu_trip_count")),
        "savings_yen": scraped.get("savings_yen", scraped["rebate_yen"]),
        "note": scraped.get("note") or "",
        "source": scraped.get("source") or "smile-etc_auto",
        "method": scraped.get("method"),
        "nexco_points": scraped.get("nexco_points"),
    }
    # 月印 last_check_b は『今月の定例の対象（前月利用分）』を取れた時だけ。古い月の手動取得で今月を完了扱いにしない
    if scraped["target_month"] == add_months(month_key(now), -1):
        state["last_check_b"] = month_key(now)
    # 最新結果 last_result_b は、より新しい月の結果を古い月で上書きしない
    cur = state.get("last_result_b") if isinstance(state.get("last_result_b"), dict) else {}
    if str(cur.get("target_month") or "") <= str(result["target_month"]):
        state["last_result_b"] = result
    upsert_rebate_history(state, result)
    state.pop("etc_wait", None)
    state["last_auto_fetch_at"] = now.isoformat()
    state["last_auto_fetch_target"] = scraped["target_month"]
    return result


def push_dashboard() -> dict[str, Any]:
    py = Path.home() / "selenium_env" / "venv" / "bin" / "python"
    cmd = [str(py), str(REPO / "scripts" / "jarvis_dashboard_push.py"), "--watch-only"]
    env = os.environ.copy()
    # private env for supabase
    if PRIVATE_ENV.is_file():
        for k, v in load_dotenv(PRIVATE_ENV).items():
            env.setdefault(k, v)
    proc = subprocess.run(
        cmd,
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    return {
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-800:],
        "stderr_tail": (proc.stderr or "")[-400:],
    }


def push_slack_report(
    *,
    outcome: str,
    target_month: str = "",
    rebate_yen: int | None = None,
    asayu_trip_count: int | None = None,
    asayu_rate_pct: int | None = None,
    savings_yen: int | None = None,
    reason: str = "",
    error: str = "",
    note: str = "",
    stage: str = "",
    next_action: str = "",
) -> dict[str, Any]:
    """614 ポイント・還元ウォッチ係 → Slack #report。失敗は #ops へ（工程・次の対応つき）。"""
    script = REPO / "scripts" / "jarvis_points_rebate_slack_report.py"
    if not script.is_file():
        return {"ok": False, "error": "jarvis_points_rebate_slack_report.py missing"}
    py = Path.home() / "selenium_env" / "venv" / "bin" / "python"
    if not py.is_file():
        py = Path(sys.executable)
    cmd = [
        str(py),
        str(script),
        "--kind",
        "etc",
        "--outcome",
        outcome,
    ]
    if target_month:
        cmd.extend(["--target-month", target_month])
    if rebate_yen is not None:
        cmd.extend(["--rebate-yen", str(rebate_yen)])
    if asayu_trip_count is not None:
        cmd.extend(["--asayu-trip-count", str(asayu_trip_count)])
    if asayu_rate_pct is not None:
        cmd.extend(["--asayu-rate-pct", str(asayu_rate_pct)])
    if savings_yen is not None:
        cmd.extend(["--savings-yen", str(savings_yen)])
    if reason:
        cmd.extend(["--reason", reason[:200]])
    if error:
        cmd.extend(["--error", error[:200]])
    if note:
        cmd.extend(["--note", note[:200]])
    if stage:
        cmd.extend(["--stage", stage[:160]])
    if next_action:
        cmd.extend(["--next", next_action[:160]])
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.stdout:
            print(proc.stdout.rstrip())
        if proc.stderr:
            print(proc.stderr.rstrip(), file=sys.stderr)
        return {"ok": proc.returncode == 0, "returncode": proc.returncode}
    except Exception as e:
        return {"ok": False, "error": str(e)}


REC: runlog614.RunRecord | None = None
SYS = "etc"


def _stage(stage: str, status: str, detail: str = "", code: str | None = None) -> None:
    if REC is not None:
        REC.stage(SYS, stage, status, detail, code)


def _slack_stage(res: dict[str, Any] | None) -> None:
    """短報の結果を工程に。結果不明(4)は成功に数えない。"""
    if not res:
        return
    rc = res.get("returncode")
    if res.get("ok"):
        _stage("slack", "success", "短報を投稿済み（または重複・停止で送らず）")
    elif rc == 5:
        _stage("slack", "skipped", "614 全体停止中のため送らず")
    elif rc == 4:
        _stage("slack", "unverified", "投稿結果不明（再投稿していない）", "post_unknown")
    elif rc == 3:
        _stage("slack", "failed", "控えを保存できず投稿を保留", "archive_failed")
    else:
        _stage("slack", "failed", f"exit {rc}", "post_failed")


def main() -> int:
    """run を集約記録（P1・工程31）して本体を実行する。記録の失敗で本線は落とさない。"""
    global REC
    argv = sys.argv[1:]
    dry = "--dry-run" in argv or "--apply" not in argv
    REC = runlog614.RunRecord(
        run_id=runlog614.new_run_id(SYS), dry_run=dry,
        trigger="manual" if "--target-month" in argv or "--force" in argv else "auto",
        script="jarvis_etc_rebate_fetch.py",
    )
    os.environ["JARVIS_614_RUN_ID"] = REC.run_id  # 子（Slack 短報）が同じ run_id を使う
    try:
        rc = _main()
    except Exception as e:  # noqa: BLE001
        _stage("run", "failed", f"想定外のエラー（{type(e).__name__}）", "unexpected_error")
        REC.finish()
        raise
    REC.finish()
    return rc


def _main() -> int:
    ap = argparse.ArgumentParser(description="ETC 平日朝夕還元額の自動取得")
    ap.add_argument("--dry-run", action="store_true", help="取得のみ（state/push しない）")
    ap.add_argument("--apply", action="store_true", help="etc_monthly.json に反映")
    ap.add_argument("--push", action="store_true", help="dashboard_push --watch-only（Slack 相乗り）")
    ap.add_argument(
        "--slack",
        action="store_true",
        help="Slack #report へ短報（614）。--push 時は既定で付く",
    )
    ap.add_argument("--no-slack", action="store_true", help="Slack 短報を付けない")
    ap.add_argument("--force", action="store_true", help="履歴にあっても再取得・上書き")
    ap.add_argument(
        "--target-month",
        default="",
        help="利用月 YYYY-MM（省略時: 定例窓なら前月）",
    )
    ap.add_argument("--headed", action="store_true", help="ブラウザ表示")
    args = ap.parse_args()
    want_slack = (args.slack or args.push) and not args.no_slack

    now = datetime.now(JST)
    env = load_dotenv(PRIVATE_ENV)
    state = load_state()

    if not (args.dry_run or not args.apply):
        try:
            ops614.flush_pending()  # 保留中の #ops 通知を再送（全体停止中は何もしない）
        except Exception as e:  # noqa: BLE001
            ops614.emergency_log(f"flush_pending 例外 {type(e).__name__}")
    stopped_all = ops614.global_stop()
    disabled = (
        state.get("disabled")
        or stopped_all
        or env.get("JARVIS_ETC_MONTHLY_DISABLE", "").strip().lower() in ("1", "true", "yes")
        or env.get("JARVIS_ETC_REBATE_AUTO_DISABLE", "").strip().lower() in ("1", "true", "yes")
    )
    report: dict[str, Any] = {
        "now_jst": now.isoformat(),
        "window_day": now.day in AUTO_WINDOW_DAYS,
        "disabled": bool(disabled),
    }
    if (disabled and not args.force) or stopped_all:  # 全体停止は --force でも解除しない
        report["skipped"] = "614 全体停止" if stopped_all else "disabled"
        _stage("fetch", "skipped", report["skipped"])
        if want_slack:
            report["slack"] = push_slack_report(outcome="disabled", reason="disabled")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    target = (args.target_month or "").strip() or default_target_month(now)
    if not target:
        report["skipped"] = (
            f"定例窓外（本日{now.day}日）。付与は利用月の翌月20日。"
            "手動は --target-month YYYY-MM"
        )
        # 窓外の定例ポーリングでは Slack しない（ノイズ防止）
        _stage("fetch", "skipped", "定例窓外")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    report["target_month"] = target
    report["grant_month"] = add_months(target, 1)

    if history_has(state, target) and not args.force:
        report["skipped"] = f"history already has {target}"
        _stage("fetch", "skipped", f"{target} は履歴済み")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    wait = state.get("etc_wait") if isinstance(state.get("etc_wait"), dict) else {}
    if (
        not args.force
        and not (args.target_month or "").strip()
        and wait.get("target_month") == target
        and wait.get("last_attempt_day") == now.strftime("%Y-%m-%d")
    ):
        # 取得待ちは窓内の翌日に再確認する。同じ日に何度もサイトへ取りに行かない（手動・--force は別）
        report["skipped"] = "取得待ち: 今日は確認済み（翌日に再確認）"
        report["status"] = "waiting"
        _stage("fetch", "skipped", "取得待ち: 今日は確認済み")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    mid = env.get("ETC_MILEAGE_ID") or ""
    pw = env.get("ETC_MILEAGE_WEB_PASSWORD") or ""
    if not mid or not pw:
        report["ok"] = False
        report["error"] = "ETC_MILEAGE_ID / ETC_MILEAGE_WEB_PASSWORD 未設定"
        _stage("fetch", "failed", "資格情報が未設定", "credentials_missing")
        if want_slack:
            report["slack"] = push_slack_report(
                outcome="failed",
                target_month=target,
                error=str(report["error"]),
                stage="n09 ETC 取得",
                next_action=".env.jarvis_private の ETC 資格情報を確認",
            )
            _slack_stage(report["slack"])
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    try:
        scraped = scrape_rebate(
            mileage_id=mid,
            password=pw,
            target_month=target,
            headless=not args.headed,
        )
    except Exception as e:
        report["ok"] = False
        report["error"] = str(e)
        _stage("fetch", "failed", f"取得中の例外（{type(e).__name__}）", "scrape_exception")
        if want_slack:
            report["slack"] = push_slack_report(
                outcome="failed",
                target_month=target,
                error=str(e),
                stage="n09 ETC 取得",
                next_action="smile-etc のログイン・画面変更を確認（窓内は翌日に再試行）",
            )
            _slack_stage(report["slack"])
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    report["scrape"] = scraped
    if not scraped.get("ok") and scraped.get("kind") == "waiting":
        # 未付与＝取得待ち。技術障害（失敗）とは区別する。窓内は翌日に再確認、窓の最終日を過ぎても未取得なら #ops
        report["ok"] = None
        report["status"] = "waiting"
        report["waiting_reason"] = str(scraped.get("error") or "付与前")
        _stage("fetch", "waiting", "付与前（取得待ち）", "not_granted_yet")
        last_day = max(AUTO_WINDOW_DAYS)
        window_over = now.day >= last_day and not (args.target_month or "").strip()
        attempts = 1
        if not (args.dry_run or not args.apply):
            wait = state.get("etc_wait") if isinstance(state.get("etc_wait"), dict) else {}
            attempts = int(wait.get("attempts") or 0) + 1 if wait.get("target_month") == target else 1
            state["etc_wait"] = {
                "target_month": target,
                "last_attempt_day": now.strftime("%Y-%m-%d"),
                "attempts": attempts,
                "reason": report["waiting_reason"][:120],
            }
            sv = save_state_verified(state)
            report["save_verify"] = {"ok": sv["ok"], "errors": sv["errors"]}
            _stage("save", "success" if sv["ok"] else "failed", "取得待ちの記録（etc_wait）")
            _stage("save_verify", "success" if sv["ok"] else "failed", "; ".join(sv["errors"])[:100],
                   None if sv["ok"] else "save_verify_mismatch")
        else:
            _stage("save", "not_applicable", "dry-run／--apply なし")
        _stage("stamp", "skipped", "取得待ちのため月印なし")
        if want_slack:
            if window_over:
                report["slack"] = push_slack_report(
                    outcome="failed",
                    target_month=target,
                    error=f"取得窓（20〜{last_day}日）の最終日まで未付与のまま。smile-etc の還元額明細を確認",
                    stage="n09 ETC 取得（取得待ちが窓の最終日を超過）",
                    next_action="smile-etc の還元額明細で付与を確認。付与後は --target-month で手動取得",
                )
            elif attempts == 1:  # 毎日同じ『取得待ち』を出さない（最初の1回だけ）
                report["slack"] = push_slack_report(
                    outcome="waiting",
                    target_month=target,
                    reason="付与前。窓内は翌日に再確認",
                )
            if report.get("slack"):
                _slack_stage(report["slack"])
            else:
                _stage("slack", "skipped", "取得待ちの2回目以降は短報を出さない")
        else:
            _stage("slack", "skipped", "短報なし")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if not scraped.get("ok"):
        report["ok"] = False
        _stage("fetch", "failed", "取得に失敗", "scrape_failed")
        if want_slack:
            report["slack"] = push_slack_report(
                outcome="failed",
                target_month=target,
                error=str(scraped.get("error") or scraped.get("note") or "scrape not ok"),
                stage="n09 ETC 取得",
                next_action="smile-etc の画面・ログインを確認（窓内は翌日に再試行）",
            )
            _slack_stage(report["slack"])
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    invalid = validate_scraped(scraped, target)
    if invalid:
        # 対象月が違う・還元額が確認できない結果は完了扱いにしない
        report["ok"] = False
        report["error"] = invalid
        _stage("fetch", "failed", "対象月・還元額の検証に失敗", "invalid_result")
        if want_slack:
            report["slack"] = push_slack_report(
                outcome="failed", target_month=target, error=invalid,
                stage="n09 ETC 取得結果の検証", next_action="取得結果の対象月を確認（完了扱いにしていません）",
            )
            _slack_stage(report["slack"])
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    report["ok"] = True
    _stage("fetch", "success", f"{target} の還元額を取得（対象月・付与月・還元額を検証済み）")
    if args.dry_run or not args.apply:
        if not args.apply:
            report["note"] = "取得のみ（--apply で state 反映）"
        for name in ("save", "save_verify", "stamp", "push", "display", "slack"):
            _stage(name, "not_applicable", "dry-run／--apply なし")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    result = apply_result(state, scraped, now)
    sv = save_state_verified(state)
    report["save_verify"] = {"ok": sv["ok"], "attempts": sv["attempts"], "errors": sv["errors"]}
    if not sv["ok"]:
        # 保存を確認できない結果は成功として画面・短報へ渡さない（外部は取り直さず、取得済みは pending に保持）
        report["ok"] = False
        report["error"] = "state の保存を読み戻して確認できませんでした（取得済みデータは非公開側に一時保持）"
        _stage("save", "failed", "保存の読み戻し不一致", "save_verify_mismatch")
        _stage("save_verify", "failed", "; ".join(sv["errors"])[:100], "save_verify_mismatch")
        if want_slack:
            report["slack"] = push_slack_report(
                outcome="failed", target_month=target, error=str(report["error"]),
                stage="n16 ETC 保存", next_action="state 領域の空き・権限を確認し --force で保存だけやり直す（取得済みは一時保持）",
            )
            _slack_stage(report["slack"])
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    report["applied"] = result
    _stage("save", "success", "tmp→置換で保存")
    _stage("save_verify", "success", "読み戻し照合 OK")
    _stage(
        "stamp", "success" if state.get("last_check_b") == month_key(now) else "skipped",
        "今月の月印" if state.get("last_check_b") == month_key(now) else "古い月の取得のため今月の月印は付けない",
    )

    if args.push:
        # 保存済み state から push → 実表示を読み戻して照合（不一致は最大1回再 push）。失敗しても取得・保存は取り消さない
        sync = display614.sync_and_verify(["etc_mileage"], remedy_system=SYS)
        report["push"] = sync
        _stage("push", "success" if sync["push"] == "success" else "failed", f"{sync['attempts']}回目まで",
               None if sync["push"] == "success" else "push_failed")
        disp = {"success": "success", "failed": "failed"}.get(sync["display"], "unverified")
        _stage("display", disp, sync["error"] or "画面の行を読み戻して一致",
               None if disp == "success" else f"display_{sync['display']}")
        if sync["push"] != "success" or sync["display"] == "failed":
            ops614.notify_ops(
                system=SYS, stage="n17/18 画面反映", run_id=REC.run_id if REC else "-",
                cause=sync["error"] or "画面反映を確認できず（取得・保存は済み）",
                next_action="/etc を確認。保存済み state から再 push（dashboard_push.py --watch-only）",
            )
    else:
        _stage("push", "not_applicable", "--push なし")
        _stage("display", "not_applicable", "--push なし")

    if want_slack:
        report["slack"] = push_slack_report(
            outcome="checked",
            target_month=str(result.get("target_month") or target),
            rebate_yen=result.get("rebate_yen")
            if isinstance(result.get("rebate_yen"), int)
            else None,
            asayu_trip_count=result.get("asayu_trip_count")
            if isinstance(result.get("asayu_trip_count"), int)
            else None,
            asayu_rate_pct=result.get("asayu_rate_pct")
            if isinstance(result.get("asayu_rate_pct"), int)
            else None,
            savings_yen=result.get("savings_yen")
            if isinstance(result.get("savings_yen"), int)
            else None,
            note=str(result.get("note") or "")[:200],
        )
        _slack_stage(report["slack"])
    else:
        _stage("slack", "not_applicable", "短報なし")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
