#!/usr/bin/env python3
"""111 夜のまとめ（Orca 定時自動化）の事前チェック（--precheck 用）。

終了コードの意味（Orca の precheck: 0=本体実行 / 0以外=スキップ）:
  exit 0 = 異常、または確かめられない  → AI を動かす
  exit 1 = すべて正常と確信できる      → AI を動かさない

読み取りだけ。標準ライブラリのみ。ネットワークは gh（GitHub Actions 実行履歴の参照）のみ。
Slack 投稿・DB 書込はしない。標準出力は件数と種類のみ（固有名は出さない）。
例外が起きたら必ず exit 0（安全側）。

判定（今日=JST。1つでも当てはまれば exit 0）:
  1. LINE取込 poll ログ: exit!=0 / 最後の実行が 90 分以上前 / 今日の実行なし
  2. 111 夜ログ: 無い・0バイト・fails が なし 以外・Mac版LINE起動中・CHRLINE sync 失敗・last_good 使用
  3. Mac版LINE が起動中
  4. GHA(triage / day-report): 今日 failure/cancelled、triage の朝の本便が無い、gh 失敗
  5. 116朝: mail_action_slack が exit!=0（ログ無し・今日の記録なしは「確認不可」で判定に含めない）
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
HOME = Path.home()
POLL_DIR = HOME / "Library" / "Logs" / "jarvis_line_export"
NIGHT_DIR = HOME / "Library" / "Logs" / "jarvis_partner_111_night"
MORNING_LOG = HOME / "Library" / "Logs" / "jarvis_night_triage" / "mac_morning_refresh.out.log"
GH_REPO = "m19mhrts83-cyber/project-GE"
WORKFLOWS = ("jarvis-dashboard-gmail-triage.yml", "jarvis-partner-day-report.yml")
MORNING_MAIN_WORKFLOW = "jarvis-dashboard-gmail-triage.yml"
POLL_STEPS = ("line_oa_pull", "gmail_to_inbox", "inbox_to_yoritoori")
STALE_MINUTES = 90
NIGHT_BAD_MARKERS = {
    "Mac版LINE起動中": "夜ログにMac版LINE起動中",
    "CHRLINE sync 失敗": "夜ログにCHRLINE sync失敗",
    "last_good を使用": "夜ログにlast_good使用",
}

# 各 check は (異常の理由リスト, 確認不可の理由リスト) を返す。
Result = tuple[list[str], list[str]]


def check_poll(entries: list[tuple[str, str]], now: datetime) -> Result:
    """entries: [(ファイル名 poll_YYYYMMDD_HHMMSS.log, 本文)]（今日分）。"""
    if not entries:
        return ["poll: 今日の実行ログなし"], []
    entries = sorted(entries)
    ab: list[str] = []
    bad = 0
    for _name, text in entries:
        for step in POLL_STEPS:
            for m in re.finditer(rf"^# {step} exit=(\d+)", text, re.M):
                if int(m.group(1)) != 0:
                    bad += 1
    if bad:
        ab.append(f"poll: exit!=0 が{bad}件")
    m = re.match(r"poll_(\d{8})_(\d{6})", entries[-1][0])
    if not m:
        ab.append("poll: 最終ログ名を読めない")
    else:
        last = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(tzinfo=JST)
        age = (now - last).total_seconds() / 60
        if age >= STALE_MINUTES:
            ab.append(f"poll: 最後の実行が{int(age)}分前")
    return ab, []


def check_night(files: list[tuple[str, str]]) -> Result:
    """files: [(ファイル名, 本文)] 今日の夜ログ。0バイト/読めないものは本文が空。"""
    if not files:
        return ["夜ログ: 今日のファイルなし"], []
    text = sorted(files)[-1][1]
    if not text.strip():
        return ["夜ログ: 最新が0バイト（読めない）"], []
    ab: list[str] = []
    fails = re.findall(r"fails=(\S+)", text)
    if not fails:
        ab.append("夜ログ: fails= の行なし（未完了の可能性）")
    elif fails[-1] != "なし":
        ab.append("夜ログ: fails が なし 以外")
    for marker, reason in NIGHT_BAD_MARKERS.items():
        if marker in text:
            ab.append(reason)
    return ab, []


def check_line_running(ps_output: str) -> Result:
    for ln in ps_output.splitlines():
        if re.search(r"/LINE\.app/Contents/MacOS/LINE(\s|$)", ln):
            return ["Mac版LINEが起動中"], []
    return [], []


def check_gha(runs: dict[str, list[dict] | None], today: str) -> Result:
    """runs: {workflow: [{event, conclusion, createdAt(UTC ISO)}] | None(取得失敗)}。"""
    ab: list[str] = []
    for wf in WORKFLOWS:
        lst = runs.get(wf)
        if lst is None:
            ab.append("GHA: 取得失敗（確かめられない）")
            continue
        todays = []
        for r in lst:
            try:
                t = datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00")).astimezone(JST)
            except Exception:
                ab.append("GHA: 時刻を読めない")
                continue
            if t.strftime("%Y%m%d") == today:
                todays.append((t, r))
        bad = sum(1 for _t, r in todays if r.get("conclusion") in ("failure", "cancelled", "timed_out"))
        if bad:
            ab.append(f"GHA: failure/cancelled が{bad}件")
        if wf == MORNING_MAIN_WORKFLOW:
            ok = any(r.get("event") == "workflow_dispatch" or t.hour == 5 for t, r in todays)
            if not ok:
                ab.append("GHA: 朝の本便が今日なし")
    return ab, []


def check_morning(text: str | None, mtime_date: str | None, today: str) -> Result:
    """116朝ログ。最後の「# step:mail_action_slack: exit=N」を見る。"""
    if text is None or mtime_date != today:
        return [], ["116朝: ログ確認不可（今日の記録なし）"]
    hits = re.findall(r"^# step:mail_action_slack: exit=(\S+)", text, re.M)
    if not hits:
        return [], ["116朝: mail_action_slack の記録なし（確認不可）"]
    if hits[-1] != "0":
        return ["116朝: mail_action_slack が exit!=0"], []
    return [], []


def decide(results: list[Result]) -> tuple[int, list[str]]:
    """exit 0=異常（AI を動かす）/ 1=正常。理由行も返す。"""
    ab = [x for a, _u in results for x in a]
    un = [x for _a, u in results for x in u]
    if ab:
        return 0, ab + un
    return 1, ["すべて正常"] + un


# ---- 読み取り（副作用なし） ----


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def collect(now: datetime) -> list[Result]:
    today = now.strftime("%Y%m%d")
    poll = [(p.name, _read(p)) for p in sorted(POLL_DIR.glob(f"poll_{today}_*"))]
    night = []
    for p in sorted(NIGHT_DIR.glob(f"night_{today}_*.log")):
        try:
            night.append((p.name, _read(p)))
        except Exception:
            night.append((p.name, ""))
    ps = subprocess.run(["ps", "-axo", "command="], capture_output=True, text=True, timeout=10).stdout
    runs: dict[str, list[dict] | None] = {}
    for wf in WORKFLOWS:
        try:
            r = subprocess.run(
                ["gh", "run", "list", "-R", GH_REPO, "--workflow", wf, "--limit", "30",
                 "--json", "event,conclusion,createdAt"],
                capture_output=True, text=True, timeout=25,
            )
            runs[wf] = json.loads(r.stdout) if r.returncode == 0 else None
        except Exception:
            runs[wf] = None
    try:
        text = _read(MORNING_LOG)
        mdate = datetime.fromtimestamp(MORNING_LOG.stat().st_mtime, JST).strftime("%Y%m%d")
    except Exception:
        text, mdate = None, None
    return [
        check_poll(poll, now),
        check_night(night),
        check_line_running(ps),
        check_gha(runs, today),
        check_morning(text, mdate, today),
    ]


def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="111 夜のまとめ 事前チェック（exit 0=AI起動 / 1=スキップ）")
    ap.add_argument("--dry-run", action="store_true", help="判定理由の表示のみ（終了コードは通常どおり）")
    ap.add_argument("--json", action="store_true", help="JSON で出力")
    args = ap.parse_args(argv)
    try:
        code, reasons = decide(collect(datetime.now(JST)))
    except Exception as e:  # 安全側: AI を動かす
        code, reasons = 0, [f"例外: {type(e).__name__}（確かめられない）"]
    if args.json:
        print(json.dumps({"exit": code, "run_ai": code == 0, "reasons": reasons}, ensure_ascii=False))
    else:
        print("要対応(AI起動)" if code == 0 else "正常(AIスキップ)")
        for r in reasons:
            print(f"- {r}")
    return code


def main(argv: list[str] | None = None) -> int:
    try:
        return run(sys.argv[1:] if argv is None else argv)
    except SystemExit as e:
        # --help は 0。引数エラー等の非0は「スキップ」を意味してしまうので安全側 0 に倒す。
        return 0
    except BaseException:
        print("例外（確かめられない）")
        return 0


if __name__ == "__main__":
    sys.exit(main())
