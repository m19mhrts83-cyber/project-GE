#!/usr/bin/env python3
"""
Jarvis: 露出後のキー Rotate 反映ヘルパー。

ユーザーが Dashboard で新キーを発行したあと、次のファイルに書いてから実行する
（値はチャットに貼らない）:

  ~/.jarvis_state/rotate_keys.env
    GEMINI_API_KEY=新キー
    JARVIS_SUPABASE_SERVICE_ROLE_KEY=新キー

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_rotate_dashboard_keys.py
  # → .env.jarvis_private 更新 + gh secret set（project-GE）
  # 完了後 rotate_keys.env を削除

旧キーの無効化は各 Dashboard で実施（このスクリプトは反映のみ）。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PRIVATE = REPO / ".env.jarvis_private"
ROTATE = Path.home() / ".jarvis_state" / "rotate_keys.env"
GH_REPO = os.environ.get("GITHUB_GMAIL_SECRET_REPO") or "m19mhrts83-cyber/project-GE"
KEYS = ("GEMINI_API_KEY", "JARVIS_SUPABASE_SERVICE_ROLE_KEY")


def load_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def upsert_private(updates: dict[str, str]) -> None:
    text = PRIVATE.read_text(encoding="utf-8") if PRIVATE.is_file() else ""
    lines = text.splitlines(keepends=True)
    found = set()
    new_lines: list[str] = []
    for line in lines:
        m = re.match(r"^([A-Za-z0-9_]+)=(.*)$", line.rstrip("\n"))
        if m and m.group(1) in updates:
            new_lines.append(f"{m.group(1)}={updates[m.group(1)]}\n")
            found.add(m.group(1))
        else:
            new_lines.append(line if line.endswith("\n") else line + "\n")
    for k, v in updates.items():
        if k not in found:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines[-1] += "\n"
            new_lines.append(f"{k}={v}\n")
    PRIVATE.write_text("".join(new_lines), encoding="utf-8")


def gh_secret_set(name: str, value: str) -> None:
    p = subprocess.run(
        ["gh", "secret", "set", name, "-R", GH_REPO, "--body", value],
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        raise RuntimeError(f"gh secret set {name} failed: {p.stderr[:300]}")


def main() -> int:
    data = load_env_file(ROTATE)
    updates = {k: data[k] for k in KEYS if data.get(k)}
    if not updates:
        print(f"Put new values in {ROTATE} then re-run.", file=sys.stderr)
        return 1
    for k, v in updates.items():
        print(f"updating {k} (len={len(v)} suffix=…{v[-4:]})")
    upsert_private(updates)
    print(f"updated {PRIVATE.name}")
    for k, v in updates.items():
        gh_secret_set(k, v)
        print(f"gh secret set {k} ok")
    try:
        ROTATE.unlink()
        print(f"deleted {ROTATE}")
    except OSError:
        pass
    print("Done. Also paste into Cloud Agents → My Secrets if used. Revoke old keys in Dashboards.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
