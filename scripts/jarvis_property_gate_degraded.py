#!/usr/bin/env python3
"""物件進行ゲート — Jarvis／Cursor 上限時の次善（プログラム本線）。

Cursor Agent が止まっても、Mac 上の Python だけで:
  1. handoff 誤ラベル修復
  2. 114 振分＋ Slack 投稿（Bカード／Cダイジェスト）
  3. 松野向け「いまやること」を stdout に出す

Yes/No は Slack リンク or CLI（511）。AI 会話は不要。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_property_gate_degraded.py
  ~/selenium_env/venv/bin/python scripts/jarvis_property_gate_degraded.py --dry-run

正本: docs/AIエージェントチーム/24_Jarvis上限時_物件進行ゲート_次善策_20261012.md
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")


def _py() -> str:
    return str(PY) if PY.is_file() else sys.executable


def _run(args: list[str], *, dry_run: bool) -> int:
    cmd = [_py(), *args]
    print("#", " ".join(cmd), flush=True)
    if dry_run and "--post" in args:
        # dry-run 時は --post を外して振分だけ
        cmd = [c for c in cmd if c != "--post"]
        cmd.append("--dry-run")
    elif dry_run and "--heal-handoff" not in args:
        if "--dry-run" not in cmd:
            cmd.append("--dry-run")
    r = subprocess.run(cmd, cwd=str(REPO), env=os.environ.copy())
    return int(r.returncode)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-post", action="store_true", help="Slack 投稿しない（振分のみ）")
    ap.add_argument("--skip-heal", action="store_true")
    args = ap.parse_args()

    if (os.environ.get("JARVIS_PROPERTY_GATE_DISABLE") or "").strip() == "1":
        print("JARVIS_PROPERTY_GATE_DISABLE=1 — skip")
        return 0

    # env
    env_path = REPO / ".env.jarvis_private"
    if env_path.is_file() and not os.environ.get("JARVIS_SUPABASE_URL"):
        # 呼び出し元が source していないとき
        print("# hint: source .env.jarvis_private してから実行推奨", file=sys.stderr)

    rc = 0
    if not args.skip_heal:
        rc |= _run(
            [str(REPO / "scripts" / "jarvis_property_gate_114.py"), "--heal-handoff"],
            dry_run=False,
        )

    scan = [str(REPO / "scripts" / "jarvis_property_gate_114.py"), "--scan"]
    if not args.no_post and not args.dry_run:
        scan.append("--post")
    if args.dry_run:
        scan.append("--dry-run")
    rc |= _run(scan, dry_run=False)

    print(
        """
---
📎 次善策（Jarvis 上限時）— 松野がやること
1. Slack #consult の【物件進行ゲート】Bカードを見る
2. Yes / No リンクをタップ（または CLI）:
   ~/selenium_env/venv/bin/python scripts/jarvis_property_gate_511.py --deal-id UUID --yes
   ~/selenium_env/venv/bin/python scripts/jarvis_property_gate_511.py --deal-id UUID --no
3. Mac job worker が動いていれば送信は自動。止まっていれば:
   launchctl kickstart -k gui/$(id -u)/com.matsunoma.jarvis.kurashift-job-worker
4. Cursor / Jarvis は不要（復旧後に会話で振り返るだけでよい）

正本: docs/AIエージェントチーム/24_Jarvis上限時_物件進行ゲート_次善策_20261012.md
---
""",
        flush=True,
    )
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
