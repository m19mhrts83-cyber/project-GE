#!/usr/bin/env python3
"""
Jarvis: MS_GRAPH_* を GitHub Secrets（project-GE）へ反映

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_ms_graph_secrets_to_gha.py
  python scripts/jarvis_ms_graph_secrets_to_gha.py --dry-run

値は表示しない。gh がログイン済みであること。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

REPO = os.environ.get("GITHUB_GMAIL_SECRET_REPO") or "m19mhrts83-cyber/project-GE"
KEYS = (
    "MS_GRAPH_CLIENT_ID",
    "MS_GRAPH_CLIENT_SECRET",
    "MS_GRAPH_REFRESH_TOKEN",
    "MS_GRAPH_AUTHORITY",
    "MS_GRAPH_TENANT_ID",
    "MS_GRAPH_USER_UPN",
    "MS_GRAPH_DRIVE_ID",
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--repo", default=REPO)
    args = ap.parse_args(argv)

    present: list[str] = []
    missing_required: list[str] = []
    # 委任（個人）なら CLIENT_ID + REFRESH 必須
    # アプリ専用なら TENANT + CLIENT + SECRET + (UPN|DRIVE)
    refresh_mode = bool((os.environ.get("MS_GRAPH_REFRESH_TOKEN") or "").strip())
    if refresh_mode:
        for k in ("MS_GRAPH_CLIENT_ID", "MS_GRAPH_REFRESH_TOKEN"):
            if not (os.environ.get(k) or "").strip():
                missing_required.append(k)
    else:
        for k in ("MS_GRAPH_TENANT_ID", "MS_GRAPH_CLIENT_ID", "MS_GRAPH_CLIENT_SECRET"):
            if not (os.environ.get(k) or "").strip():
                missing_required.append(k)
        if not (
            (os.environ.get("MS_GRAPH_USER_UPN") or "").strip()
            or (os.environ.get("MS_GRAPH_DRIVE_ID") or "").strip()
        ):
            missing_required.append("MS_GRAPH_USER_UPN|MS_GRAPH_DRIVE_ID")

    if missing_required:
        print(f"missing: {', '.join(missing_required)}", file=sys.stderr)
        return 1

    for k in KEYS:
        v = (os.environ.get(k) or "").strip()
        if not v:
            continue
        present.append(k)
        if args.dry_run:
            print(f"would set {k} (len={len(v)})")
            continue
        p = subprocess.run(
            ["gh", "secret", "set", k, "--repo", args.repo],
            input=v.encode(),
            capture_output=True,
        )
        if p.returncode != 0:
            print(p.stderr.decode()[:300], file=sys.stderr)
            return p.returncode
        print(f"set {k}")

    print(f"done mode={'refresh' if refresh_mode else 'app'} keys={len(present)} repo={args.repo}")
    print("next: gh workflow run jarvis-dashboard-lanes.yml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
