#!/usr/bin/env python3
"""614 ポイント・還元ウォッチ係 — Slack #report へ短報。

得る側（テイチャン／Vポイント／ETC還元）の定例結果を、ダッシュボードに加え
Slack でも「自動で動いた」と把握できるようにする。

  python scripts/jarvis_points_rebate_slack_report.py --kind teiki --from-state --dry-run
  python scripts/jarvis_points_rebate_slack_report.py --kind etc --from-state --dry-run
  python scripts/jarvis_points_rebate_slack_report.py --kind vpoint --note '窓Cサマリ' --dry-run

投稿: jarvis_slack_webhook_post.py（#report／失敗時 #ops）
無効化: JARVIS_POINTS_REBATE_SLACK_REPORT_DISABLE=1
  種別だけ切る: JARVIS_TEIKI_SLACK_REPORT_DISABLE / JARVIS_ETC_SLACK_REPORT_DISABLE /
                JARVIS_VPOINT_SLACK_REPORT_DISABLE
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
POST = REPO / "scripts" / "jarvis_slack_webhook_post.py"
TEIKI_STATE = REPO / ".jarvis_state" / "teiki_barai_chance.json"
ETC_STATE = REPO / ".jarvis_state" / "etc_monthly.json"
VPOINT_MONTHLY = REPO / ".jarvis_state" / "vpoint_monthly.json"
VPOINT_CADENCE = REPO / ".jarvis_state" / "vpoint_cadence.json"
DEDUPE_STATE = REPO / ".jarvis_state" / "points_rebate_slack_dedupe.json"
REPORTS_DIR = (
    REPO
    / "docs"
    / "AIエージェントチーム"
    / "600_リソース・家計室"
    / "614_ポイント・還元ウォッチ係"
    / "reports"
)
JST = ZoneInfo("Asia/Tokyo")
AGENT_ID = "614"
AGENT_NAME = "ポイント還元"
DASH_VPOINT = "https://jarvis-dashboard-amber.vercel.app/vpoint"
DASH_ETC = "https://jarvis-dashboard-amber.vercel.app/etc"

KIND_DISABLE = {
    "teiki": "JARVIS_TEIKI_SLACK_REPORT_DISABLE",
    "etc": "JARVIS_ETC_SLACK_REPORT_DISABLE",
    "vpoint": "JARVIS_VPOINT_SLACK_REPORT_DISABLE",
}


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _archive(text: str, tag: str) -> None:
    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        day = datetime.now(JST).strftime("%Y-%m-%d")
        path = REPORTS_DIR / f"{day}_{tag}.md"
        path.write_text(
            f"# Slack #report 控え — {day} / {tag}\n\n```\n{text}\n```\n",
            encoding="utf-8",
        )
        print(f"📎 report archive: {path.relative_to(REPO)}")
    except OSError as e:
        print(f"⚠️ report archive failed: {e}", file=sys.stderr)


def _header(scope: str) -> list[str]:
    return [f"【{AGENT_ID} {AGENT_NAME}｜{scope}】"]


def build_teiki(
    *,
    outcome: str,
    tickets: int | None,
    w_chance: int | None,
    enrolled: str | None,
    drew_summary: str,
    reason: str,
    error: str,
    note: str,
) -> str:
    lines = _header("テイチャン")
    out = (outcome or "checked").strip()
    if out == "skipped":
        lines.append(f"・結果: スキップ（{reason or '間隔内'}）")
    elif out == "disabled":
        lines.append("・結果: 無効化のため未実行")
    elif out == "failed":
        lines.append(f"・結果: 失敗 — {error or '不明'}")
        lines.append("・次: Vpass／Chrome／ログ（~/Library/Logs/jarvis_teiki）を確認 or #ops")
    elif out == "drew":
        lines.append(f"・結果: 抽選したよ — {drew_summary or '完了'}")
    else:
        lines.append("・結果: 確認のみ（抽選なし）")

    bits: list[str] = []
    if enrolled:
        bits.append(f"規約={enrolled}")
    if tickets is not None:
        bits.append(f"券={tickets}枚")
    if w_chance is not None:
        bits.append(f"W={w_chance}枚")
    if bits:
        lines.append(f"・状態: {' · '.join(bits)}")
    if note:
        lines.append(f"・特記: {note}")
    lines.append(f"・見る: {DASH_VPOINT}#teiki-barai")
    return "\n".join(lines)


def build_etc(
    *,
    outcome: str,
    target_month: str,
    rebate_yen: int | None,
    asayu_trip_count: int | None,
    asayu_rate_pct: int | None,
    savings_yen: int | None,
    reason: str,
    error: str,
    note: str,
) -> str:
    lines = _header("ETC還元")
    out = (outcome or "checked").strip()
    if out == "skipped":
        lines.append(f"・結果: スキップ（{reason or '対象外'}）")
    elif out == "disabled":
        lines.append("・結果: 無効化のため未実行")
    elif out == "failed":
        lines.append(f"・結果: 失敗 — {error or '不明'}")
        lines.append("・次: smile-etc／ログ or #ops")
    else:
        lines.append("・結果: 還元サマリ取得")

    if target_month:
        lines.append(f"・対象利用月: {target_month}")
    bits: list[str] = []
    if rebate_yen is not None:
        bits.append(f"還元額={rebate_yen:,}円")
    if asayu_trip_count is not None:
        bits.append(f"朝夕={asayu_trip_count}回")
    if asayu_rate_pct is not None:
        bits.append(f"率≈{asayu_rate_pct}%")
    if savings_yen is not None:
        bits.append(f"お得={savings_yen:,}円")
    if bits:
        lines.append(f"・数値: {' · '.join(bits)}")
    if note:
        lines.append(f"・特記: {note}")
    lines.append(f"・見る: {DASH_ETC}")
    return "\n".join(lines)


def build_vpoint(*, outcome: str, reason: str, error: str, note: str, asks_n: int | None) -> str:
    lines = _header("Vポイント")
    out = (outcome or "checked").strip()
    if out == "skipped":
        lines.append(f"・結果: スキップ（{reason or '間隔内'}）")
    elif out == "disabled":
        lines.append("・結果: 無効化のため未実行")
    elif out == "failed":
        lines.append(f"・結果: 失敗 — {error or '不明'}")
        lines.append("・次: cadence／月次ログ or #ops")
    else:
        lines.append("・結果: 定例ウォッチ更新")
    if asks_n is not None:
        lines.append(f"・要Jarvis確認: {asks_n}件")
    if note:
        lines.append(f"・特記: {note}")
    lines.append(f"・見る: {DASH_VPOINT}")
    return "\n".join(lines)


def _text_fingerprint(text: str) -> str:
    norm = "\n".join(line.rstrip() for line in (text or "").splitlines()).strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:20]


def _should_skip_duplicate(kind: str, text: str, *, force: bool) -> bool:
    """同一本文の同日再投稿を防ぐ（Slack UI FB: 同じメッセージ連投）。"""
    if force or (os.environ.get("JARVIS_POINTS_REBATE_SLACK_REPOST") or "").strip() in (
        "1",
        "true",
        "yes",
    ):
        return False
    day = datetime.now(JST).strftime("%Y-%m-%d")
    fp = _text_fingerprint(text)
    try:
        data = json.loads(DEDUPE_STATE.read_text(encoding="utf-8")) if DEDUPE_STATE.is_file() else {}
    except (OSError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    entry = data.get(kind) if isinstance(data.get(kind), dict) else {}
    if entry.get("day") == day and entry.get("fingerprint") == fp:
        print(f"⏭ {kind} Slack skip（同日・同一本文の再投稿防止） fp={fp}")
        return True
    return False


def _remember_post(kind: str, text: str) -> None:
    day = datetime.now(JST).strftime("%Y-%m-%d")
    fp = _text_fingerprint(text)
    try:
        data = json.loads(DEDUPE_STATE.read_text(encoding="utf-8")) if DEDUPE_STATE.is_file() else {}
    except (OSError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data[kind] = {"day": day, "fingerprint": fp, "at": datetime.now(JST).isoformat()}
    try:
        DEDUPE_STATE.parent.mkdir(parents=True, exist_ok=True)
        DEDUPE_STATE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as e:
        print(f"⚠️ dedupe state save failed: {e}", file=sys.stderr)


def _post(
    channel: str,
    text: str,
    *,
    dry_run: bool,
    archive_tag: str,
    kind: str,
    force: bool = False,
) -> int:
    if _should_skip_duplicate(kind, text, force=force):
        return 0
    if dry_run:
        print("--- dry-run ---")
        print(text)
        print("---")
        _archive(text, archive_tag)
        return 0
    if not POST.is_file():
        print(f"❌ missing {POST}", file=sys.stderr)
        return 2
    proc = subprocess.run(
        [sys.executable, str(POST), "--channel", channel, "--text", text],
        cwd=str(REPO),
        check=False,
    )
    if int(proc.returncode) == 0:
        _archive(text, archive_tag)
        _remember_post(kind, text)
    return int(proc.returncode)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kind", required=True, choices=("teiki", "etc", "vpoint"))
    ap.add_argument(
        "--outcome",
        default="checked",
        choices=("checked", "drew", "skipped", "failed", "disabled"),
    )
    ap.add_argument("--from-state", action="store_true")
    ap.add_argument("--tickets", type=int, default=None)
    ap.add_argument("--w-chance", type=int, default=None)
    ap.add_argument("--enrolled", default="")
    ap.add_argument("--drew-summary", default="")
    ap.add_argument("--target-month", default="")
    ap.add_argument("--rebate-yen", type=int, default=None)
    ap.add_argument("--asayu-trip-count", type=int, default=None)
    ap.add_argument("--asayu-rate-pct", type=int, default=None)
    ap.add_argument("--savings-yen", type=int, default=None)
    ap.add_argument("--asks", type=int, default=None)
    ap.add_argument("--reason", default="")
    ap.add_argument("--error", default="")
    ap.add_argument("--note", default="")
    ap.add_argument("--channel", default="report", choices=("report", "ops", "consult"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="無効化 env を無視")
    args = ap.parse_args()

    if not args.force:
        if (os.environ.get("JARVIS_POINTS_REBATE_SLACK_REPORT_DISABLE") or "").strip().lower() in (
            "1",
            "true",
            "yes",
        ):
            print("⏭ JARVIS_POINTS_REBATE_SLACK_REPORT_DISABLE=1 — Slack 投稿スキップ")
            return 0
        kind_env = KIND_DISABLE[args.kind]
        if (os.environ.get(kind_env) or "").strip().lower() in ("1", "true", "yes"):
            print(f"⏭ {kind_env}=1 — Slack 投稿スキップ")
            return 0

    channel = args.channel
    if args.outcome == "failed" and args.channel == "report":
        channel = "ops"

    if args.kind == "teiki":
        st = _load_json(TEIKI_STATE) if args.from_state else {}
        tickets = args.tickets if args.tickets is not None else st.get("ticket_count")
        w_chance = args.w_chance if args.w_chance is not None else st.get("w_chance_tickets")
        enrolled = (args.enrolled or st.get("enrolled") or "") or None
        if isinstance(tickets, str) and tickets.isdigit():
            tickets = int(tickets)
        if isinstance(w_chance, str) and w_chance.isdigit():
            w_chance = int(w_chance)
        text = build_teiki(
            outcome=args.outcome,
            tickets=tickets if isinstance(tickets, int) else None,
            w_chance=w_chance if isinstance(w_chance, int) else None,
            enrolled=str(enrolled) if enrolled else None,
            drew_summary=args.drew_summary,
            reason=args.reason,
            error=args.error,
            note=args.note,
        )
        return _post(
            channel,
            text,
            dry_run=args.dry_run,
            archive_tag=f"teiki_{args.outcome}",
            kind="teiki",
            force=args.force,
        )

    if args.kind == "etc":
        st = _load_json(ETC_STATE) if args.from_state else {}
        last_b = st.get("last_result_b") if isinstance(st.get("last_result_b"), dict) else {}
        target = (args.target_month or last_b.get("target_month") or "") or ""
        rebate = args.rebate_yen if args.rebate_yen is not None else last_b.get("rebate_yen")
        trips = (
            args.asayu_trip_count
            if args.asayu_trip_count is not None
            else last_b.get("asayu_trip_count")
        )
        rate = (
            args.asayu_rate_pct if args.asayu_rate_pct is not None else last_b.get("asayu_rate_pct")
        )
        savings = args.savings_yen if args.savings_yen is not None else last_b.get("savings_yen")
        for name, val in (("rebate", rebate), ("trips", trips), ("rate", rate), ("savings", savings)):
            if isinstance(val, str) and val.isdigit():
                if name == "rebate":
                    rebate = int(val)
                elif name == "trips":
                    trips = int(val)
                elif name == "rate":
                    rate = int(val)
                else:
                    savings = int(val)
        text = build_etc(
            outcome=args.outcome,
            target_month=str(target),
            rebate_yen=rebate if isinstance(rebate, int) else None,
            asayu_trip_count=trips if isinstance(trips, int) else None,
            asayu_rate_pct=rate if isinstance(rate, int) else None,
            savings_yen=savings if isinstance(savings, int) else None,
            reason=args.reason,
            error=args.error,
            note=args.note or (str(last_b.get("note") or "") if args.from_state else ""),
        )
        return _post(
            channel,
            text,
            dry_run=args.dry_run,
            archive_tag=f"etc_{args.outcome}",
            kind="etc",
            force=args.force,
        )

    # vpoint
    asks_n = args.asks
    if args.from_state and asks_n is None:
        monthly = _load_json(VPOINT_MONTHLY)
        cadence = _load_json(VPOINT_CADENCE)
        asks = monthly.get("jarvis_asks") or cadence.get("jarvis_asks") or []
        if isinstance(asks, list):
            asks_n = len(asks)
    text = build_vpoint(
        outcome=args.outcome,
        reason=args.reason,
        error=args.error,
        note=args.note,
        asks_n=asks_n,
    )
    return _post(
        channel,
        text,
        dry_run=args.dry_run,
        archive_tag=f"vpoint_{args.outcome}",
        kind="vpoint",
        force=args.force,
    )


if __name__ == "__main__":
    raise SystemExit(main())
