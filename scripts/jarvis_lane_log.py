#!/usr/bin/env python3
"""Jarvis 処置ログ — レーン別 MD 追記ヘルパー。

正本:
  OneDrive …/000_共通/Jarvis処置ログ/{lane}/5.処置ログ.md

使い方:
  from jarvis_lane_log import append_lane_log, ensure_lane_log_tree
  append_lane_log("kazoku", "決定", "- 採用 → …")
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

DEFAULT_ROOT = (
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    / "C2_ルーティン作業/26_パートナー社への相談/000_共通/Jarvis処置ログ"
)

LANE_META: dict[str, str] = {
    "kamiooya": "神大家運営",
    "kanji": "飲み会幹事",
    "properties": "所有物件",
    "kodate": "戸建て",
    "ai_raimo": "AI・Raimo",
    "kazoku": "家族",
}

LOG_FILENAME = "5.処置ログ.md"


def log_root() -> Path:
    env = (os.environ.get("JARVIS_LANE_LOG_ROOT") or "").strip()
    return Path(env).expanduser() if env else DEFAULT_ROOT


def lane_dir(lane: str) -> Path:
    return log_root() / lane.strip()


def lane_log_path(lane: str) -> Path:
    return lane_dir(lane) / LOG_FILENAME


def now_stamp() -> str:
    return datetime.now(JST).strftime("%Y/%m/%d %H:%M")


def ensure_lane_log_tree(lanes: list[str] | None = None) -> Path:
    root = log_root()
    root.mkdir(parents=True, exist_ok=True)
    readme = root / "README.md"
    if not readme.is_file():
        lines = [
            "# Jarvis 処置ログ",
            "",
            "レーンごとの判断・コメント・Notion 登録の正本（Cursor で @ 参照可）。",
            "",
            "| フォルダ | レーン |",
            "|---|---|",
        ]
        for lid, title in LANE_META.items():
            lines.append(f"| `{lid}/` | {title} |")
        lines += [
            "",
            f"各レーンは `{LOG_FILENAME}` に時系列追記。",
            "",
        ]
        readme.write_text("\n".join(lines), encoding="utf-8")

    index = root / "index.md"
    if not index.is_file():
        index.write_text(
            "# Jarvis 処置ログ — 索引\n\n"
            "横断リンク用。詳細は各レーンの `5.処置ログ.md` を参照。\n",
            encoding="utf-8",
        )

    targets = lanes or list(LANE_META.keys())
    for lid in targets:
        d = lane_dir(lid)
        d.mkdir(parents=True, exist_ok=True)
        p = lane_log_path(lid)
        if not p.is_file():
            title = LANE_META.get(lid, lid)
            p.write_text(
                f"# {title} — Jarvis 処置ログ\n\n"
                f"レーン `{lid}`。要約確認・採用／見送り・コメント・Notion 登録を追記する。\n",
                encoding="utf-8",
            )
    return root


def append_lane_log(lane: str, heading: str, body: str) -> Path:
    """Append a dated section to the lane log. Returns path written."""
    lid = (lane or "").strip()
    if not lid:
        raise ValueError("lane required")
    ensure_lane_log_tree([lid])
    path = lane_log_path(lid)
    block = f"\n### {now_stamp()}｜{heading.strip()}\n{body.rstrip()}\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(block)
    return path


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--lane")
    ap.add_argument("--heading", default="メモ")
    ap.add_argument("--body", default="")
    args = ap.parse_args()
    if args.init:
        root = ensure_lane_log_tree()
        print(f"# init {root}")
    elif args.lane and args.body:
        p = append_lane_log(args.lane, args.heading, args.body)
        print(f"# append {p}")
    else:
        ap.print_help()
