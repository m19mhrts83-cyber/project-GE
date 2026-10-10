#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GHA: 211 管理会社向け朝便（Graph 読取 materialize → night_triage → 正本 PUT）.

Mac ローカル OneDrive なしで動かす。送信はしない。

  python scripts/jarvis_gha_reply_draft_211.py --dry-run
  python scripts/jarvis_gha_reply_draft_211.py
  python scripts/jarvis_gha_reply_draft_211.py --limit 20

停止: JARVIS_REPLY_DRAFT_211_GHA_DISABLE=1
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

PARTNER_BASE_REL = (
    "215_神・大家さん倶楽部/C2_ルーティン作業/26_パートナー社への相談"
)
CONTACT_REL = f"{PARTNER_BASE_REL}/000_共通/連絡先一覧.yaml"
PM_PREFIXES = ("101_", "102_", "103_", "104_")
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
CONTACT_CI = MANUAL / "連絡先一覧.snapshot.yaml"


def _disabled() -> bool:
    return (os.environ.get("JARVIS_REPLY_DRAFT_211_GHA_DISABLE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _materialize_partners(tmp: Path) -> Path:
    from jarvis_onedrive_graph import (  # type: ignore
        graph_configured,
        list_children_graph,
        read_file,
    )

    if not graph_configured():
        raise SystemExit("MS_GRAPH_* 未設定（graph_configured=false）")

    base = tmp / "partners"
    base.mkdir(parents=True, exist_ok=True)

    # 連絡先
    common = base / "000_共通"
    common.mkdir(parents=True, exist_ok=True)
    contact_dest = common / "連絡先一覧.yaml"
    try:
        contact_dest.write_bytes(read_file("onedrive", CONTACT_REL))
        print(f"# contact: graph -> {contact_dest}", file=sys.stderr)
    except Exception as e:
        print(f"# contact graph fail: {e}", file=sys.stderr)
        if CONTACT_CI.is_file():
            contact_dest.write_bytes(CONTACT_CI.read_bytes())
            print(f"# contact: snapshot -> {contact_dest}", file=sys.stderr)
        else:
            raise SystemExit("連絡先一覧.yaml 不可") from e

    # 管理会社フォルダを列挙
    try:
        children = list_children_graph(PARTNER_BASE_REL)
    except Exception as e:
        raise SystemExit(f"partner base list fail: {e}") from e

    folders = [
        str(c["name"])
        for c in children
        if c.get("is_folder")
        and any(str(c.get("name") or "").startswith(p) for p in PM_PREFIXES)
    ]
    folders.sort()
    print(f"# PM folders: {len(folders)} ({', '.join(folders)})", file=sys.stderr)

    n_md = 0
    for folder in folders:
        rel_md = f"{PARTNER_BASE_REL}/{folder}/5.やり取り.md"
        dest_dir = base / folder
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "5.やり取り.md"
        try:
            dest.write_bytes(read_file("onedrive", rel_md))
            n_md += 1
        except Exception as e:
            print(f"# md skip {folder}: {e}", file=sys.stderr)
            # 空ファイルでもスキャン対象にしない
            continue
    print(f"# materialized MD: {n_md}", file=sys.stderr)
    if n_md == 0:
        raise SystemExit("管理会社の 5.やり取り.md が0件（Graph 読取失敗の可能性）")
    return base


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="正本書込・Slack なし")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--lookback-days", type=int, default=21)
    args = ap.parse_args()

    if _disabled():
        print("# skipped: JARVIS_REPLY_DRAFT_211_GHA_DISABLE=1")
        return 0

    py = sys.executable
    with tempfile.TemporaryDirectory(prefix="jarvis_211_") as td:
        tmp = Path(td)
        partner_base = _materialize_partners(tmp)
        env = os.environ.copy()
        env["YORITOORI_BASE_PATH"] = str(partner_base)
        env["YORITOORI_PARTNER_BASE"] = str(partner_base)
        env["JARVIS_TRIAGE_NO_GEMINI"] = "1"
        # state はリポ内（GHA checkout 上）
        state_dir = REPO / ".jarvis_state" / "night_triage"
        state_dir.mkdir(parents=True, exist_ok=True)

        # triage は常に queue 保存（--dry-run だと draft_text が残らず 211 が空振りする）。
        # 正本 PUT / Slack だけ args.dry_run で抑止する。
        triage_cmd = [
            py,
            str(REPO / "scripts" / "jarvis_night_triage.py"),
            "--lane",
            "partner",
            "--skip-fetch",
            "--limit",
            str(args.limit),
        ]
        print("# run:", " ".join(triage_cmd), file=sys.stderr)
        rc = subprocess.call(triage_cmd, cwd=str(REPO), env=env)
        if rc != 0:
            print(f"# triage rc={rc}", file=sys.stderr)
            if not args.dry_run:
                subprocess.call(
                    [
                        py,
                        str(REPO / "scripts" / "jarvis_slack_webhook_post.py"),
                        "--channel",
                        "ops",
                        "--username",
                        "返信案内下書き係",
                        "--text",
                        f"【ops】返信案内下書き係・GHA朝便\n・失敗: night_triage rc={rc}\n・正本書込は中止",
                    ],
                    cwd=str(REPO),
                    env=env,
                )
            return rc

        # 211 は triage 済み queue を読む（再 triage しない）
        morning_cmd = [
            py,
            str(REPO / "scripts" / "jarvis_reply_draft_211.py"),
            "--apply",
            "--report",
            "--limit",
            str(args.limit),
            "--lookback-days",
            str(args.lookback_days),
        ]
        if args.dry_run:
            morning_cmd.append("--dry-run")
        print("# run:", " ".join(morning_cmd), file=sys.stderr)
        return subprocess.call(morning_cmd, cwd=str(REPO), env=env)


if __name__ == "__main__":
    raise SystemExit(main())
