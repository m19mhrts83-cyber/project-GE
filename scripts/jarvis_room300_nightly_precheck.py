#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""300室「本日のまとめ（毎晩21:10・#report）」の事前チェック（AI なし）。

Orca の定時実行の precheck に設定する:
  ~/selenium_env/venv/bin/python ~/git-repos/scripts/jarvis_room300_nightly_precheck.py
  終了コード 0=異常あり（AI のまとめを動かす）／1=正常の晩（AI を起こさない・何も投稿しない）
  `show` を付けると状態を動かさず判定だけ JSON で出す。

正常の晩に何も出さない理由: 毎晩の「異常なし」1行は読む価値が低い。Orca 自体が動いているかは
金曜の「300室 週次の生存確認」（#ai-hub）と 315-B が見る。止まった晩は異常の晩として AI が動く。

見るもの（どれも既存の状態ファイル・ログ・GHA。新しい収集はしない）:
  1. 315-B（stall_watch_315b.json）: 無い／14 時間より古い／311・312・313・314・317 のどれかが遅れ・空回り。
     「読取不可」は 2 晩続いたときだけ異常（一時的な Timeout で毎晩起こさない）
  2. 318 の今日の実行（.jarvis_state/todoist_318/runs/*.json）: 成功以外・errors あり
  3. launchd のエラーログ（311・313・318）: 前回から増えた分にエラー行
  4. 312 の GHA（todoist-312-collect.yml）: 今日の失敗・取消。gh が読めない晩は記録だけ
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_nightly_precheck_lib import (  # noqa: E402
    JST, Ctx, age_hours, gha_failed_today, load_json, log_delta_errors, run_precheck,
)

STATE_PATH = REPO / ".jarvis_state" / "room300_nightly_precheck.json"
STALL = REPO / ".jarvis_state" / "stall_watch_315b.json"
RUNS_318 = REPO / ".jarvis_state" / "todoist_318" / "runs"
LOGS = Path.home() / "Library" / "Logs"
ERR_LOGS = [
    LOGS / "jarvis_send_gate_311" / "poll.err.log",
    LOGS / "jarvis_send_gate_311" / "launchd.err.log",
    LOGS / "jarvis_todoist_313_digest" / "todoist_313_digest.err.log",
]
SLUG = "m19mhrts83-cyber/project-GE"
STALL_MAX_AGE_H = 14.0


def _is_error_line():
    import jarvis_weekly_review_314 as wr  # 週次レビューと同じ「エラー行」の定義を使う
    return wr.is_error_line


def collect(ctx: Ctx) -> None:
    now = ctx.now
    st = ctx.state
    # 1. 315-B
    sw = load_json(STALL, {})
    if not sw:
        ctx.add("red", "315b_missing", "315-B の状態ファイルが読めない")
    else:
        a = age_hours(sw.get("checked_at"), now)
        if a is None or a > STALL_MAX_AGE_H:
            ctx.add("red", "315b_stale", f"315-B の最終確認が{'不明' if a is None else f'{a:.0f}時間前'}")
        unknown_prev = set(st.get("unknown_ids") or [])
        unknown_now = set()
        for r in sw.get("rows") or []:
            rid = str(r.get("id"))
            stat = {r.get("status"), r.get("stop_status"), r.get("idle_status")}
            if stat & {"stale", "idle"}:
                ctx.add("red", f"315b_{rid}", f"{rid} {r.get('why') or r.get('idle_why') or '遅れ・空回り'}")
            elif "unknown" in stat:
                unknown_now.add(rid)
                if rid in unknown_prev:
                    ctx.add("red", f"315b_unknown_{rid}", f"{rid} 読取不可が2晩続いている（{r.get('why')}）")
                else:
                    ctx.add("yellow", f"315b_unknown_{rid}", f"{rid} 読取不可（初回・記録のみ）")
        st["unknown_ids"] = sorted(unknown_now)
    # 2. 318 の今日の実行
    today = now.astimezone(JST).date().isoformat()
    if RUNS_318.is_dir():
        for p in sorted(RUNS_318.glob("r318-*.json")):
            d = load_json(p, {})
            if str(d.get("started_at", ""))[:10] != today:
                continue
            if d.get("mode") == "dry-run":
                continue
            if d.get("result") != "success" or d.get("errors"):
                ctx.add("red", f"318_{d.get('run_id')}", f"318 の実行が成功でない（{d.get('result')}・errors {len(d.get('errors') or [])}）")
    # 3. launchd エラーログ
    is_err = _is_error_line()
    for p in ERR_LOGS:
        errs = log_delta_errors(p, st, is_err)
        if errs:
            ctx.add("red", f"log_{p.parent.name}", f"{p.parent.name}: エラー行 {len(errs)} 件（例: {errs[0][:80]}）")
    # 4. 312 の GHA
    bad, why = gha_failed_today(SLUG, "todoist-312-collect.yml", now)
    if bad:
        ctx.add("red", "gha_312", f"312 の GHA が失敗: {', '.join(bad[:3])}")
    elif why:
        ctx.add("yellow", "gha_312_unreadable", f"312 の GHA を読めなかった（{why}）")


def main() -> int:
    return run_precheck("room300", collect, STATE_PATH)


if __name__ == "__main__":
    raise SystemExit(main())
