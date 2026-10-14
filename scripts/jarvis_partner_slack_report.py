#!/usr/bin/env python3
"""パートナー連絡整理係（111）— Slack #report へ短報。

通常は更新があるときだけ投稿。運用確認期間（既定〜2026-10-18）は
更新ゼロでも「出なかった」を投稿して生存確認する。
投稿本体は jarvis_slack_webhook_post.py（Incoming Webhook）。
LLM 不使用（定型テンプレのみ）。

例:
  python scripts/jarvis_partner_slack_report.py --frame day \\
    --gmail 2 --chatwork 0 --dry-run
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
POST = REPO / "scripts" / "jarvis_slack_webhook_post.py"
PY = sys.executable
AGENT_ID = "111"
AGENT_NAME = "パートナー連絡整理係"
REPORTS_DIR = (
    REPO
    / "docs"
    / "AIエージェントチーム"
    / "100_連絡・物件動向把握室"
    / "111_パートナー連絡整理係"
    / "reports"
)
JST = ZoneInfo("Asia/Tokyo")
# 運用確認: ゼロ日も「出なかった」投稿（過ぎたら静かな既定に戻る）
_REPORT_ZERO_UNTIL = date(2026, 10, 18)

_FRAME_JA = {"day": "昼", "night": "夜", "manual": "副合図"}


def _archive_report(frame: str, text: str) -> Path | None:
    """係フォルダ reports/ に控えを残す（やり取り正本は 26 のまま）。"""
    try:
        day = datetime.now(JST).strftime("%Y-%m-%d")
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        path = REPORTS_DIR / f"{day}_{frame}.md"
        body = f"# Slack #report 控え — {day} / {frame}\n\n```\n{text}\n```\n"
        path.write_text(body, encoding="utf-8")
        print(f"📎 report archive: {path.relative_to(REPO)}")
        return path
    except OSError as e:
        print(f"⚠️ report archive failed: {e}", file=sys.stderr)
        return None


def _total(args: argparse.Namespace) -> int:
    return max(0, int(args.gmail)) + max(0, int(args.chatwork)) + max(
        0, int(args.line)
    ) + max(0, int(args.other))


def _report_zero_alive() -> bool:
    """ゼロ日も投稿するか。env 優先 → 期限日。"""
    env = (os.environ.get("JARVIS_PARTNER_111_REPORT_ZERO") or "").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    if env in ("1", "true", "yes", "on"):
        return True
    return date.today() <= _REPORT_ZERO_UNTIL


def _build_text(args: argparse.Namespace, total: int) -> str:
    """判断しやすい短報（番号先頭・スマホ1画面）。"""
    frame = (args.frame or "manual").strip()
    frame_ja = _FRAME_JA.get(frame, frame)
    fail = (args.failures or "なし").strip() or "なし"
    fail_ok = fail in ("なし", "none", "-")

    lines = [
        f"【報告】{AGENT_ID} {AGENT_NAME}・{frame_ja}",
        f"・件数: Gmail+{args.gmail} / Chatwork+{args.chatwork}",
    ]
    if int(args.line) or frame in ("night", "manual"):
        lines[-1] = lines[-1] + f" / LINE+{args.line}"
    if int(args.other):
        lines.append(f"・その他: +{args.other}")
    if total <= 0:
        lines.append("・結果: 更新なし（出なかった）")
    else:
        lines.append(f"・合計追記: {total}")
    lines.append(f"・失敗: {'なし' if fail_ok else fail}")
    if frame == "night":
        lines.append("・見る: ダッシュボード → 要対応は 5.やり取り.md / Gmail")
    else:
        lines.append("・見る: Gmail 要対応 → 詳細は 5.やり取り.md（LINEは夜枠）")
    next_ = (args.next or "").strip()
    if total <= 0 and not next_ and fail_ok:
        next_ = "対応不要（生存確認のみ）"
    if next_:
        lines.append(f"・次: {next_}")
    elif not fail_ok:
        lines.append("・次: 失敗行を確認（再実行 or #ops）")
    if args.note:
        lines.append(f"・メモ: {args.note.strip()}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--frame",
        default="manual",
        choices=("day", "night", "manual"),
        help="実行枠（昼/夜/副合図）",
    )
    ap.add_argument("--gmail", type=int, default=0)
    ap.add_argument("--chatwork", type=int, default=0)
    ap.add_argument("--line", type=int, default=0)
    ap.add_argument("--other", type=int, default=0)
    ap.add_argument("--failures", default="なし")
    ap.add_argument("--next", default="")
    ap.add_argument("--note", default="")
    ap.add_argument(
        "--force",
        action="store_true",
        help="合計0でも投稿（運用確認の自動判定を上書き）",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    total = _total(args)
    allow_zero = args.force or _report_zero_alive()
    if total <= 0 and not allow_zero:
        print("⏭ 更新ゼロのため Slack 投稿スキップ")
        return 0
    if total <= 0 and allow_zero and not args.force:
        print(
            f"📎 ゼロ日報告（運用確認〜{_REPORT_ZERO_UNTIL.isoformat()} "
            "または JARVIS_PARTNER_111_REPORT_ZERO=1）"
        )

    text = _build_text(args, total)
    if args.dry_run:
        print("--- dry-run ---")
        print(text)
        print("---")
        _archive_report(args.frame, text)
        return 0

    if not POST.is_file():
        print(f"❌ missing {POST}", file=sys.stderr)
        return 2

    proc = subprocess.run(
        [PY, str(POST), "--channel", "report", "--text", text],
        cwd=str(REPO),
        check=False,
    )
    if int(proc.returncode) == 0:
        _archive_report(args.frame, text)
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
