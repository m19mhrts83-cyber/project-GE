#!/usr/bin/env python3
"""パートナー連絡整理係（111）— Slack #report へ短報。

通常は更新があるときだけ投稿。運用確認期間（既定〜2026-10-18）は
更新ゼロでも1行の生存確認を投稿する。
失敗は人間語＋次の一手。定型の「見る／次」は繰り返さない（特記のみ）。
投稿本体は jarvis_slack_webhook_post.py（Incoming Webhook）。
LLM 不使用。

例:
  python scripts/jarvis_partner_slack_report.py --frame day \\
    --gmail 2 --chatwork 0 --dry-run
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
POST = REPO / "scripts" / "jarvis_slack_webhook_post.py"
PY = sys.executable
AGENT_ID = "111"
AGENT_NAME = "パートナー連絡整理"
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

# 機械語失敗 →（人間語, 次の一手）
_FAIL_HUMAN: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"^line exit=(\d+)$", re.I),
        "LINE取込が異常終了（CHRLINE／認証まわり・exit={g1}）",
        "Mac版LINE終了を確認 → run_patch.sh 再実行 or #ops",
    ),
    (
        re.compile(r"^Mac版LINE起動中"),
        "Mac版LINEと競合のため LINE をスキップ",
        "Mac版LINEを終了して夜枠を再実行",
    ),
    (
        re.compile(r"^export_gmail exit=(\d+)$", re.I),
        "LINE公式エクスポートの Gmail→inbox 取込失敗（exit={g1}）",
        "estate Gmail／inbox を確認",
    ),
    (
        re.compile(r"^export_inbox exit=(\d+)$", re.I),
        "LINE公式エクスポートの inbox→やり取り 取込失敗（exit={g1}）",
        "000_共通/LINE公式エクスポート/inbox を確認",
    ),
    (
        re.compile(r"^run_patch\.sh missing$", re.I),
        "LINE実行環境の run_patch.sh が無い",
        "git-repos/line_unofficial_poc を確認",
    ),
    (
        re.compile(r"^gmail exit=(\d+)$", re.I),
        "Gmail→やり取り 取込失敗（exit={g1}）",
        "admin token／scripts を確認 or #ops",
    ),
    (
        re.compile(r"^chatwork exit=(\d+)$", re.I),
        "Chatwork→やり取り 取込失敗（exit={g1}）",
        "CHATWORK_API_TOKEN／scripts を確認 or #ops",
    ),
]


def humanize_partner_fail(raw: str) -> tuple[str, str]:
    """機械語の失敗1件 →（人間語, 次の一手）。未知はそのまま。"""
    s = (raw or "").strip()
    if not s or s in ("なし", "none", "-"):
        return "なし", ""
    for pat, msg, nxt in _FAIL_HUMAN:
        m = pat.search(s)
        if m:
            out = msg
            for i, g in enumerate(m.groups(), start=1):
                out = out.replace(f"{{g{i}}}", g)
            return out, nxt
    m2 = re.match(r"^(\w+)\s+exit=(\d+)$", s, re.I)
    if m2:
        return (
            f"{m2.group(1)} が異常終了（exit={m2.group(2)}）",
            "ログ確認 → 再実行 or #ops",
        )
    return s, ""


def format_partner_failures(fails: list[str]) -> tuple[str, str]:
    """失敗リスト → Slack 用（結合文, 代表の次の一手）。"""
    if not fails:
        return "なし", ""
    msgs: list[str] = []
    nexts: list[str] = []
    for f in fails:
        msg, nxt = humanize_partner_fail(f)
        msgs.append(msg)
        if nxt and nxt not in nexts:
            nexts.append(nxt)
    return "／".join(msgs), "／".join(nexts)


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
    """特記のみ。ゼロ・失敗なしは1行。定型の「見る／次」は繰り返さない。"""
    frame = (args.frame or "manual").strip()
    frame_ja = _FRAME_JA.get(frame, frame)
    fail_raw = (args.failures or "なし").strip() or "なし"
    fail_ok = fail_raw in ("なし", "none", "-")
    note = (args.note or "").strip()
    next_ = (args.next or "").strip()

    # 機械語が残っていたら人間語化（パイプライン経由でも CLI 直でも）
    if not fail_ok:
        parts = [p.strip() for p in re.split(r"[／/]", fail_raw) if p.strip()]
        msgs: list[str] = []
        auto_nexts: list[str] = []
        for p in parts:
            msg, nxt = humanize_partner_fail(p)
            msgs.append(msg)
            if nxt and nxt not in auto_nexts:
                auto_nexts.append(nxt)
        fail = "／".join(msgs)
        if not next_ and auto_nexts:
            next_ = "／".join(auto_nexts)
    else:
        fail = fail_raw

    # 更新ゼロ・失敗なし → 1行（生存確認）
    if total <= 0 and fail_ok and not note and not next_:
        return f"【{AGENT_ID} {AGENT_NAME}・{frame_ja}】更新なし（生存確認）"

    lines = [f"【{AGENT_ID} {AGENT_NAME}・{frame_ja}】"]
    if total > 0:
        parts = [f"Gmail+{args.gmail}", f"Chatwork+{args.chatwork}"]
        if int(args.line) or frame in ("night", "manual"):
            parts.append(f"LINE+{args.line}")
        if int(args.other):
            parts.append(f"その他+{args.other}")
        lines.append(f"・件数: {' / '.join(parts)}（合計+{total}）")
    elif not fail_ok:
        lines.append("・件数: 更新なし")

    if not fail_ok:
        lines.append(f"・失敗: {fail}")
        if next_:
            lines.append(f"・次: {next_}")
        else:
            lines.append("・次: 失敗内容を確認（再実行 or #ops）")
    if note:
        lines.append(f"・特記: {note}")
    if next_ and fail_ok:
        lines.append(f"・次: {next_}")
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
