#!/usr/bin/env python3
"""Just Press Record の未文字起こし .m4a を見つけて jarvis_transcribe_m4a.py で起こす（AI チャット不使用）。

共通ルール R2（docs/AIエージェントチーム/49_共通ルール_AI使用量と入力_20261024.md）の自動化。
launchd（install_jpr_auto_transcribe_launchd.sh）から 1 時間ごとに呼ぶ想定。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_jpr_auto_transcribe.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_jpr_auto_transcribe.py

- 対象: 隣に `*_文字起こし.md` が無い .m4a のうち、最終更新から --min-age-min 分以上たったもの（録音・同期の途中を避ける）
- 1 回の上限 --limit 件（Gemini 無料枠の節約）
- 失敗（音声データ欠損など）は state に記録し、同じファイルは再試行しない（ファイルが更新されたら再試行）
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
JPR_DIR = (
    Path.home()
    / "Library/Mobile Documents/iCloud~com~openplanetsoftware~just-press-record/Documents"
)
STATE = REPO / ".jarvis_state" / "jpr_auto_transcribe.json"
TRANSCRIBE = REPO / "scripts" / "jarvis_transcribe_m4a.py"
LOG = "🎙️ jpr auto transcribe"


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"failed": {}}


def save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pending(root: Path, min_age_sec: float, failed: dict) -> list[Path]:
    now = time.time()
    out = []
    for m4a in sorted(root.glob("*/*.m4a")):
        if m4a.with_name(f"{m4a.stem}_文字起こし.md").exists():
            continue
        st = m4a.stat()
        if now - st.st_mtime < min_age_sec:
            continue
        prev = failed.get(str(m4a))
        if prev and prev.get("mtime") == st.st_mtime:
            continue
        out.append(m4a)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--min-age-min", type=float, default=30)
    args = ap.parse_args()

    if not JPR_DIR.is_dir():
        print(f"{LOG}: 録音フォルダが無い（iCloud 未同期？）: {JPR_DIR}", file=sys.stderr)
        return 1
    state = load_state()
    failed = state.setdefault("failed", {})
    todo = pending(JPR_DIR, args.min_age_min * 60, failed)
    print(f"{LOG}: 未文字起こし {len(todo)} 件（今回 最大 {args.limit} 件）")
    for m4a in todo[: args.limit]:
        rel = m4a.relative_to(JPR_DIR)
        if args.dry_run:
            print(f"  # dry-run {rel}")
            continue
        r = subprocess.run(
            [sys.executable, str(TRANSCRIBE), "--input", str(m4a)],
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
        if r.returncode == 0:
            failed.pop(str(m4a), None)
            print(f"  ✅ {rel}")
        else:
            reason = (r.stderr or r.stdout).strip().splitlines()[-1:] or ["unknown"]
            failed[str(m4a)] = {"mtime": m4a.stat().st_mtime, "reason": reason[0][:200]}
            print(f"  ❌ {rel}: {reason[0][:120]}", file=sys.stderr)
    if not args.dry_run:
        save_state(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
