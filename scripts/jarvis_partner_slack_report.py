#!/usr/bin/env python3
"""パートナー連絡整理係（111）— 更新時のみ Slack #report へ短報。

更新差分がゼロなら投稿しない（静かに終了コード 0）。
投稿本体は jarvis_slack_webhook_post.py（Incoming Webhook）。
LLM 不使用（定型テンプレのみ）。

例:
  python scripts/jarvis_partner_slack_report.py --frame day \\
    --gmail 2 --chatwork 0 --dry-run
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
POST = REPO / "scripts" / "jarvis_slack_webhook_post.py"
PY = sys.executable

_FRAME_JA = {"day": "昼", "night": "夜", "manual": "副合図"}


def _total(args: argparse.Namespace) -> int:
    return max(0, int(args.gmail)) + max(0, int(args.chatwork)) + max(
        0, int(args.line)
    ) + max(0, int(args.other))


def _build_text(args: argparse.Namespace, total: int) -> str:
    """判断しやすい短報（スマホ1画面・見る場所を明示）。"""
    frame = (args.frame or "manual").strip()
    frame_ja = _FRAME_JA.get(frame, frame)
    fail = (args.failures or "なし").strip() or "なし"
    fail_ok = fail in ("なし", "none", "-")

    lines = [
        f"【報告】パートナー連絡整理係・{frame_ja}",
        f"・件数: Gmail+{args.gmail} / Chatwork+{args.chatwork}",
    ]
    if int(args.line) or frame in ("night", "manual"):
        lines[-1] = lines[-1] + f" / LINE+{args.line}"
    if int(args.other):
        lines.append(f"・その他: +{args.other}")
    lines.append(f"・合計追記: {total}（この通は更新ありのときだけ）")
    lines.append(f"・失敗: {'なし' if fail_ok else fail}")
    # 判断の入口を固定（運用確認で磨ける）
    if frame == "night":
        lines.append("・見る: ダッシュボード → 要対応は 5.やり取り.md / Gmail")
    else:
        lines.append("・見る: Gmail 要対応 → 詳細は 5.やり取り.md（LINEは夜枠）")
    next_ = (args.next or "").strip()
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
        help="合計0でも投稿（通常は使わない）",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    total = _total(args)
    if total <= 0 and not args.force:
        print("⏭ 更新ゼロのため Slack 投稿スキップ")
        return 0

    text = _build_text(args, total)
    if args.dry_run:
        print("--- dry-run ---")
        print(text)
        print("---")
        return 0

    if not POST.is_file():
        print(f"❌ missing {POST}", file=sys.stderr)
        return 2

    proc = subprocess.run(
        [PY, str(POST), "--channel", "report", "--text", text],
        cwd=str(REPO),
        check=False,
    )
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
