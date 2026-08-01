#!/usr/bin/env python3
"""
Jarvis: Cloud Agents「My Secrets」貼り付け用の .env 断片を作る（値は表示しない）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_cloud_secrets_prepare.py
  # → ~/.jarvis_state/cloud_agent_secrets.env
  # Dashboard → Cloud Agents → My Secrets → Add Secrets に中身を貼って Save
  # 終わったら: rm ~/.jarvis_state/cloud_agent_secrets.env

Git にコミットしないこと。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

OUT = Path.home() / ".jarvis_state" / "cloud_agent_secrets.env"
KEYS = (
    "JARVIS_SUPABASE_URL",
    "JARVIS_SUPABASE_SERVICE_ROLE_KEY",
    "GEMINI_API_KEY",
)


def main() -> int:
    lines: list[str] = []
    missing: list[str] = []
    for k in KEYS:
        v = (os.environ.get(k) or "").strip()
        if not v:
            missing.append(k)
            continue
        lines.append(f"{k}={v}")
    if missing:
        print(f"missing: {', '.join(missing)}", file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    OUT.chmod(0o600)
    print(f"wrote {OUT} ({len(lines)} keys). Paste into Cloud Agents → My Secrets, then delete the file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
