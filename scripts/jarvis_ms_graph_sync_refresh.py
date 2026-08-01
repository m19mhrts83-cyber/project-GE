#!/usr/bin/env python3
"""
Jarvis: 回転した MS_GRAPH_REFRESH_TOKEN を .env.jarvis_private へ反映し、任意で GHA Secrets へ。

入力:
  ~/.jarvis_state/ms_graph_new_refresh.env
  または --from-env（現在の環境変数）

使い方:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_ms_graph_sync_refresh.py
  python scripts/jarvis_ms_graph_sync_refresh.py --push-gha
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PRIVATE = REPO / ".env.jarvis_private"
NEW_REFRESH = Path.home() / ".jarvis_state" / "ms_graph_new_refresh.env"


def _read_new_refresh() -> str:
    if NEW_REFRESH.is_file():
        for line in NEW_REFRESH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("MS_GRAPH_REFRESH_TOKEN="):
                return line.split("=", 1)[1].strip()
    return (os.environ.get("MS_GRAPH_REFRESH_TOKEN") or "").strip()


def apply_rotated_refresh(*, push_gha: bool = False, from_env: bool = False) -> dict[str, str]:
    token = (os.environ.get("MS_GRAPH_REFRESH_TOKEN") or "").strip() if from_env else _read_new_refresh()
    if not token:
        raise SystemExit(
            f"新しい refresh がありません（{NEW_REFRESH} または MS_GRAPH_REFRESH_TOKEN）"
        )
    if not PRIVATE.is_file():
        raise SystemExit(f"missing {PRIVATE}")

    text = PRIVATE.read_text(encoding="utf-8")
    # bash source で $ ! * が展開されないよう単一引用符で保存
    qtoken = "'" + token.replace("'", "'\\''") + "'"
    if re.search(r"^MS_GRAPH_REFRESH_TOKEN=", text, re.M):
        text = re.sub(
            r"^MS_GRAPH_REFRESH_TOKEN=.*$",
            f"MS_GRAPH_REFRESH_TOKEN={qtoken}",
            text,
            count=1,
            flags=re.M,
        )
    else:
        text = text.rstrip() + f"\nMS_GRAPH_REFRESH_TOKEN={qtoken}\n"
    PRIVATE.write_text(text, encoding="utf-8")
    os.environ["MS_GRAPH_REFRESH_TOKEN"] = token
    if NEW_REFRESH.is_file():
        NEW_REFRESH.unlink()
    out = {"private": "updated", "refresh_len": str(len(token))}
    if push_gha:
        r = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "jarvis_ms_graph_secrets_to_gha.py")],
            cwd=str(REPO),
            env=os.environ.copy(),
            capture_output=True,
            text=True,
        )
        out["gha_exit"] = str(r.returncode)
        out["gha_tail"] = (r.stdout + r.stderr)[-400:]
        if r.returncode != 0:
            raise SystemExit(f"GHA secrets push failed:\n{r.stdout}\n{r.stderr}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--push-gha", action="store_true")
    ap.add_argument("--from-env", action="store_true", help="state ファイルではなく現在の env")
    args = ap.parse_args(argv)
    result = apply_rotated_refresh(push_gha=args.push_gha, from_env=args.from_env)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
