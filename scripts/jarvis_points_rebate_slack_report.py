#!/usr/bin/env python3
"""614 ポイント・還元ウォッチ係 — Slack #report へ短報。

得る側（テイチャン／Vポイント／ETC還元）の定例結果を、ダッシュボードに加え
Slack でも「自動で動いた」と把握できるようにする。

  python scripts/jarvis_points_rebate_slack_report.py --kind teiki --from-state --dry-run
  python scripts/jarvis_points_rebate_slack_report.py --kind etc --from-state --dry-run
  python scripts/jarvis_points_rebate_slack_report.py --kind vpoint --note '窓Cサマリ' --dry-run
  python scripts/jarvis_points_rebate_slack_report.py --kind card_benefit --dry-run   # 年間特典（Olive／Bonvoy）

投稿: jarvis_slack_webhook_post.py（#report／失敗時 #ops）
無効化: JARVIS_POINTS_REBATE_SLACK_REPORT_DISABLE=1
  種別だけ切る: JARVIS_TEIKI_SLACK_REPORT_DISABLE / JARVIS_ETC_SLACK_REPORT_DISABLE /
                JARVIS_VPOINT_SLACK_REPORT_DISABLE / JARVIS_CARD_BENEFIT_SLACK_REPORT_DISABLE
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_614_ops as ops614  # noqa: E402
import jarvis_614_runlog as runlog614  # noqa: E402
import jarvis_614_slack_ledger as ledger614  # noqa: E402

EXIT_HELD = 3  # 控えを保存できず投稿を保留
EXIT_SKIPPED = 5  # 614 全体停止中のため送らなかった（送っていない。『投稿済み』として数えない）
EXIT_UNKNOWN = 4  # 結果不明（jarvis_slack_webhook_post.EXIT_UNKNOWN と同じ）。再投稿しない

REPO = Path(__file__).resolve().parents[1]
POST = REPO / "scripts" / "jarvis_slack_webhook_post.py"
TEIKI_STATE = REPO / ".jarvis_state" / "teiki_barai_chance.json"
ETC_STATE = REPO / ".jarvis_state" / "etc_monthly.json"
VPOINT_MONTHLY = REPO / ".jarvis_state" / "vpoint_monthly.json"
VPOINT_CADENCE = REPO / ".jarvis_state" / "vpoint_cadence.json"
DEDUPE_STATE = REPO / ".jarvis_state" / "points_rebate_slack_dedupe.json"
JST = ZoneInfo("Asia/Tokyo")
AGENT_ID = "614"
AGENT_NAME = "ポイント還元"
DASH_VPOINT = "https://jarvis-dashboard-amber.vercel.app/vpoint"
DASH_ETC = "https://jarvis-dashboard-amber.vercel.app/etc"

KIND_DISABLE = {
    "teiki": "JARVIS_TEIKI_SLACK_REPORT_DISABLE",
    "etc": "JARVIS_ETC_SLACK_REPORT_DISABLE",
    "vpoint": "JARVIS_VPOINT_SLACK_REPORT_DISABLE",
    "card_benefit": "JARVIS_CARD_BENEFIT_SLACK_REPORT_DISABLE",
}


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _md(iso: object) -> str:
    """ISO 日時 → 『11/23』（読めなければ空）。"""
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return f"{dt.month}/{dt.day}"
    except (ValueError, TypeError):
        return ""


def reports_dir(tag: str) -> Path:
    """控えの置き場。金額・基準日・券数を含み得るため、公開リポの docs ではなく
    gitignore 済みの state 側（F8・2026-11-23）。JARVIS_STATE_DIR があればそちら。"""
    sd = (os.environ.get("JARVIS_STATE_DIR") or "").strip()
    base = Path(sd).expanduser() if sd else REPO / ".jarvis_state"
    # 年間特典は従来の置き場を維持
    return base / ("card_benefit_reports" if tag.startswith("card_benefit") else "points_rebate_reports")


def _archive_path(tag: str, *, dry_run: bool = False) -> Path:
    day = datetime.now(JST).strftime("%Y-%m-%d")
    # dry-run の控えは別名（配信の証拠にしない・F8/n21）
    suffix = "_dryrun" if dry_run else ""
    return reports_dir(tag) / f"{day}_{tag}{suffix}.md"


def _write_archive(path: Path, body: str) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return True
    except OSError as e:
        print(f"⚠️ report archive failed: {e}", file=sys.stderr)
        return False


def _archive(text: str, tag: str, *, dry_run: bool = False) -> None:
    """（後方互換）控えを書く。dry-run の控えは別名・冒頭に『dry-run・未配信』。"""
    path = _archive_path(tag, dry_run=dry_run)
    day = datetime.now(JST).strftime("%Y-%m-%d")
    ok = _write_archive(
        path,
        f"# Slack #report 控え{'（dry-run・未配信）' if dry_run else ''} — {day} / {tag}\n\n```\n{text}\n```\n",
    )
    if ok:
        try:
            shown = path.relative_to(REPO)
        except ValueError:
            shown = path
        print(f"📎 report archive: {shown}")


def _archive_before(text: str, tag: str, run_id: str) -> Path | None:
    """投稿の前に本文の控えを保存する（P1・工程21）。失敗したら保存だけ1回やり直す。なお失敗なら None。"""
    path = _archive_path(tag)
    day = datetime.now(JST).strftime("%Y-%m-%d")
    body = (
        f"# Slack #report 控え — {day} / {tag}\n\n- run: {run_id}\n- 状態: 送信前（投稿結果は下に追記される）\n\n"
        f"```\n{text}\n```\n"
    )
    for _ in range(2):
        if _write_archive(path, body):
            return path
    return None


def _archive_append_result(path: Path | None, line: str) -> bool:
    """投稿後に結果を追記する。失敗したら追記だけ1回やり直す（投稿はやり直さない）。"""
    if path is None:
        return False
    for _ in range(2):
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"\n- {datetime.now(JST).isoformat(timespec='seconds')} {line}\n")
            return True
        except OSError as e:
            print(f"⚠️ report archive append failed: {e}", file=sys.stderr)
    return False


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
    last_check: str = "",
    maintenance_note: str = "",
) -> str:
    lines = _header("テイチャン")
    out = (outcome or "checked").strip()
    if out == "maintenance":
        # 停止中は『確認のみ・券=◯枚』と読ませない（券数は前回値で古い）。D4・2026-11-23
        lines.append(f"・結果: メンテナンス停止中（最終確認 {last_check or '—'}）")
        if maintenance_note:
            lines.append(f"・サイト: {maintenance_note}")
        lines.append("・次: 3日ごとに再開を確認します（再開したら通常に戻ります）")
        if note:
            lines.append(f"・特記: {note}")
        lines.append(f"・見る: {DASH_VPOINT}#teiki-barai")
        return "\n".join(lines)
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
    elif out == "waiting":
        # 未付与は失敗ではない（取得待ち）。窓内は自動で翌日に再確認する
        lines.append(f"・結果: 取得待ち（{reason or '付与前'}）")
        lines.append("・次: 窓内（20〜26日）は翌日に自動で再確認。月印は付けていません")
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
    elif out == "partial":
        # Slack は松野さん本人への通知。基準日などの具体値を出してよい（D6・2026-11-23）
        lines.append(f"・結果: 部分成功（{reason or '付与サマリが完全でない'}）")
        lines.append("・次: Tサイトの履歴を取り直す（『Tサイト取って』）。月印は付けていません")
    else:
        lines.append("・結果: 定例ウォッチ更新")
    if asks_n is not None:
        # 「要Jarvis確認」「窓C」は伝わらない（FB 10/29）。人が見る項目数と一覧の場所を書く
        lines.append(f"・手で確認する項目: {asks_n}件（一覧は下のページ）")
    if note:
        lines.append(f"・特記: {note}")
    lines.append(f"・見る: {DASH_VPOINT}")
    return "\n".join(lines)


def build_card_benefit(*, outcome: str, error: str, note: str) -> str:
    """年間特典ウォッチ（Olive Infinite／Marriott Bonvoy）。実額は state（gitignore）から。"""
    header = _header("年間特典")[0]
    out = (outcome or "checked").strip()
    if out == "disabled":
        return "\n".join([header, "・結果: 無効化のため未実行"])
    if out == "failed":
        return "\n".join(
            [header, f"・結果: 失敗 — {error or '不明'}", "・次: 年間特典の state／Gmail 取込を確認 or #ops"]
        )
    sys.path.insert(0, str(REPO / "scripts"))
    import jarvis_card_benefit_watch as cbw  # noqa: E402

    text = cbw.build_slack_text(
        cbw.compute_from_files(), header=header, dash_url=f"{DASH_VPOINT}#card-benefit"
    )
    if note:
        text += f"\n特記: {note}"
    return text


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


_OPS_EXTRA: dict[str, str] = {}  # main が --stage / --next を入れる（#ops の障害通知に工程・次の対応を足す）


def _with_ops_extra(channel: str, text: str, run_id: str) -> str:
    if channel != "ops" or not _OPS_EXTRA:
        return text
    lines = [text]
    if _OPS_EXTRA.get("stage"):
        lines.append(f"・工程: {_OPS_EXTRA['stage']}")
    if _OPS_EXTRA.get("next"):
        lines.append(f"・次の対応: {_OPS_EXTRA['next']}")
    lines.append(f"・run: {run_id}")
    return "\n".join(lines)


def _run_post(channel: str, text: str) -> int:
    env = os.environ.copy()
    if channel == "ops":
        env["JARVIS_614_OPS_ACTIVE"] = "1"  # ops 送信中の失敗から通知を作らない（再帰防止）
    try:
        return subprocess.run(
            [sys.executable, str(POST), "--channel", channel, "--text", text],
            cwd=str(REPO), env=env, check=False,
        ).returncode
    except OSError as e:
        print(f"❌ post spawn failed: {e}", file=sys.stderr)
        return 1


def _post(
    channel: str,
    text: str,
    *,
    dry_run: bool,
    archive_tag: str,
    kind: str,
    force: bool = False,
) -> int:
    """投稿の流れ（P1・工程19/21）。終了コード: 0=送信済み/対象外、3=控えを保存できず保留、
    4=結果不明（再投稿していない）、それ以外=送信失敗（届いていない）。

    1) 投稿前に本文の控えを保存（失敗は保存だけ1回再試行→なお失敗なら投稿を保留）
    2) 台帳で再投稿してよい状態か確認（sent／unknown／sending は再投稿しない）
    3) 投稿。結果不明（タイムアウト等）は Slack の履歴で送信済みか確認 → 無かった時だけ1回再試行
    4) 結果を控えに追記（追記だけ失敗しても再投稿しない）"""
    if _should_skip_duplicate(kind, text, force=force):
        return 0
    if dry_run:
        print("--- dry-run ---")
        print(text)
        print("---")
        _archive(text, archive_tag, dry_run=True)
        return 0
    if not POST.is_file():
        print(f"❌ missing {POST}", file=sys.stderr)
        return 2
    run_id = runlog614.new_run_id(kind)
    is_ops = channel == "ops"
    text = _with_ops_extra(channel, text, run_id)
    if ops614.global_stop():
        # 全体停止中は送らない。障害通知は保留に積み、停止を解いた次回起動で再送する
        if is_ops:
            ops614.enqueue_pending(text, nid=ledger614.fingerprint(text), system=kind, stage="slack", run_id=run_id)
        print("⏭ 614 全体停止中 — Slack 投稿せず保留" if is_ops else "⏭ 614 全体停止中 — Slack 投稿スキップ")
        return EXIT_SKIPPED
    k = ledger614.key(kind, channel, text)
    blocked = ledger614.should_skip(k)
    if blocked and not (force and blocked == "sent"):
        print(f"⏭ {kind} Slack skip（台帳: {blocked}。再投稿しない） key={k.split('|')[-1]}")
        return 0

    path = _archive_before(text, archive_tag, run_id)
    if path is None and not is_ops:
        # 控えを保存できない時は投稿を保留し、#ops へ（#ops 自身の控え失敗では再通知しない）
        ledger614.record(k, "held", run_id=run_id, note="archive_failed")
        ops614.notify_ops(
            system=kind, stage="n21 Slack 控え保存", run_id=run_id,
            cause="投稿前の控えを保存できず、短報を保留した",
            next_action="state 領域の空き・権限を確認。直るまで短報は出ません（取得・保存は済み）",
        )
        return EXIT_HELD

    ledger614.record(k, "sending", run_id=run_id)
    rc = _run_post(channel, text)
    final = "sent" if rc == 0 else ("unknown" if rc == EXIT_UNKNOWN else "not_sent")
    if final == "unknown":
        # 結果不明: 履歴で送信済みか確認。確認できなければ unknown のまま（再投稿しない）
        found = ledger614.confirm_sent(channel, text)
        if found is True:
            final = "sent"
        elif found is False:
            final = "not_sent"
            ledger614.record(k, "not_sent", run_id=run_id, note="timeout_then_history_none")
            rc2 = _run_post(channel, text)  # 未送信を確認できた時だけ、最大1回
            final = "sent" if rc2 == 0 else ("unknown" if rc2 == EXIT_UNKNOWN else "not_sent")
            rc = rc2
    ledger614.record(k, final, run_id=run_id)
    if final == "sent":
        _remember_post(kind, text)
        if not _archive_append_result(path, "投稿結果: 送信済み"):
            ledger614.record(k, "sent", run_id=run_id, note="result_append_failed")
            ops614.emergency_log(f"Slack 控えへの結果追記に失敗（投稿は済み・再投稿しない） {kind} run={run_id}")
        return 0
    if final == "unknown":
        _archive_append_result(path, "投稿結果: 結果不明（届いたか確認できず。再投稿していません）")
        if not is_ops:
            ops614.notify_ops(
                system=kind, stage="n19 Slack 投稿", run_id=run_id,
                cause="短報の投稿結果が不明（応答待ちで切れ、履歴でも確認できず）",
                next_action="#report を見て届いているか確認。届いていなければ人の依頼で再投稿（自動では再投稿しません）",
            )
        else:
            ops614.emergency_log(f"ops 通知の結果不明（再投稿しない） {kind} run={run_id}")
        return EXIT_UNKNOWN
    # 届いていない（確定）
    _archive_append_result(path, "投稿結果: 送信失敗（届いていない）")
    if is_ops:
        ops614.enqueue_pending(text, nid=ledger614.fingerprint(text), system=kind, stage="slack", run_id=run_id)
    return int(rc) or 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kind", required=True, choices=("teiki", "etc", "vpoint", "card_benefit"))
    ap.add_argument(
        "--outcome",
        default="checked",
        choices=("checked", "drew", "skipped", "failed", "disabled", "partial", "maintenance", "waiting"),
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
    ap.add_argument("--stage", default="", help="#ops 障害通知: 失敗した工程（例: n13 Olive 取込）")
    ap.add_argument("--next", dest="next_action", default="", help="#ops 障害通知: 次の対応")
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

    _OPS_EXTRA.update({k: v[:160] for k, v in (("stage", args.stage), ("next", args.next_action)) if v})
    channel = args.channel
    if args.outcome == "failed" and args.channel == "report":
        channel = "ops"
    if not args.dry_run:
        # 保留中の #ops 通知を再送（全体停止中は何もしない）
        try:
            ops614.flush_pending()
        except Exception as e:  # noqa: BLE001 — 再送の失敗で本線の短報を止めない
            ops614.emergency_log(f"flush_pending 例外 {type(e).__name__}")

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
            last_check=_md(st.get("last_check_at")),
            maintenance_note=str(st.get("maintenance_note") or ""),
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

    if args.kind == "card_benefit":
        text = build_card_benefit(outcome=args.outcome, error=args.error, note=args.note)
        return _post(
            channel,
            text,
            dry_run=args.dry_run,
            archive_tag=f"card_benefit_{args.outcome}",
            kind="card_benefit",
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
