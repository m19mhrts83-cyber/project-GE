#!/usr/bin/env python3
"""家族会議・週次: Genspark 議事録 → Drive ＋（任意で）Notion 向け Markdown 準備。

Notion へのファイル添付は MCP create-attachment / insert_content が本線。
本 CLI は MD 生成・Drive 配置・要約表示までを一本化する。

例:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  export PATH="$HOME/.local/bin:$HOME/.genspark-tool-cli/bin:$PATH"

  # 当該週を検索して MD を Drive に置く
  ~/selenium_env/venv/bin/python scripts/jarvis_family_meeting_weekly.py \\
    --attach-minutes --date 2026-09-20 --keyword 家族会議

  # 共有 URL / project_id 指定
  ~/selenium_env/venv/bin/python scripts/jarvis_family_meeting_weekly.py \\
    --attach-minutes --genspark-url \\
    'https://www.genspark.ai/meetingnotes/SharedMeetingNotes?id=e8706170-...'

  # Notion 用の貼付案内だけ（添付はチャット側 MCP）
  ~/selenium_env/venv/bin/python scripts/jarvis_family_meeting_weekly.py \\
    --attach-minutes --date 2026-09-20 --print-notion-hint \\
    --notion-page-id 3e1f6bbe5a76803b8a3ac7cc13380ade
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_genspark_meeting_fetch as gsk  # noqa: E402

FAMILY_YAML = REPO / "config" / "notion_family_coaching.yaml"
STUDIO_YAML = REPO / "config" / "notebooklm_studio.yaml"
DRIVE_ROOT = Path.home() / (
    "Library/CloudStorage/GoogleDrive-admin@livingsupport-matsu.co.jp"
    "/マイドライブ/200_NoteBookLM"
)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def resolve_drive_minutes_dir() -> Path:
    cfg = _load_yaml(FAMILY_YAML)
    weekly = cfg.get("weekly_log_pattern") if isinstance(cfg.get("weekly_log_pattern"), dict) else {}
    folder = str(weekly.get("drive_folder") or "13_家族会議_週次").strip()
    studio = _load_yaml(STUDIO_YAML)
    notebooks = studio.get("notebooks") if isinstance(studio.get("notebooks"), dict) else {}
    meta = notebooks.get("family_meeting_weekly") if isinstance(notebooks.get("family_meeting_weekly"), dict) else {}
    if meta.get("drive_folder"):
        folder = str(meta["drive_folder"]).strip()
    out = DRIVE_ROOT / folder / "議事録"
    out.mkdir(parents=True, exist_ok=True)
    return out


def extract_project_id(url_or_id: str) -> str:
    s = (url_or_id or "").strip()
    if not s:
        return ""
    if re.fullmatch(r"[0-9a-fA-F-]{36}", s):
        return s
    q = parse_qs(urlparse(s).query)
    for key in ("id", "project_id"):
        vals = q.get(key) or []
        if vals and vals[0]:
            return vals[0].strip()
    m = re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", s)
    return m.group(0) if m else ""


def find_meeting(
    *,
    keyword: str,
    date_from: str | None,
    project_id: str | None,
    task_id: str | None,
) -> dict[str, Any]:
    """Return shaped get payload (full). Prefer task_id / project_id; else search."""
    if task_id:
        raw = gsk.run_gsk(
            ["get", "--task_id", task_id, "--detail_level", "full"]
        )
        return gsk.shape_get(raw, "full")

    if project_id:
        # SharedMeetingNotes?id=… は project_id（meeting task id とは別）
        raw = gsk.run_gsk(
            [
                "get",
                "--project_id",
                project_id,
                "--detail_level",
                "full",
            ]
        )
        return gsk.shape_get(raw, "full")

    args = ["search", "--keyword", keyword, "--page_size", "20"]
    if date_from:
        args.extend(["--date_from", date_from])
    raw = gsk.run_gsk(args)
    shaped = gsk.shape_list_or_search(raw)
    notes = shaped.get("notes") or []
    if not notes:
        raise SystemExit("該当する Genspark meeting がありません")

    chosen_id = None
    for n in notes:
        title = str(n.get("title") or "")
        if "家族会議" in title:
            chosen_id = n.get("id")
            break
    chosen_id = chosen_id or notes[0].get("id")
    if not chosen_id:
        raise SystemExit("meeting id を特定できませんでした")
    raw = gsk.run_gsk(
        ["get", "--task_id", str(chosen_id), "--detail_level", "full"]
    )
    return gsk.shape_get(raw, "full")


def meeting_to_markdown(shaped: dict[str, Any]) -> str:
    title = shaped.get("title") or "家族会議"
    project_id = shaped.get("project_id") or ""
    project_url = shaped.get("project_url") or (
        f"https://www.genspark.ai/agents?id={project_id}" if project_id else ""
    )
    share = (
        f"https://www.genspark.ai/meetingnotes/SharedMeetingNotes?id={project_id}"
        if project_id
        else ""
    )
    summary = shaped.get("summary") or ""
    if not isinstance(summary, str):
        summary = json.dumps(summary, ensure_ascii=False, indent=2)
    return (
        f"# {title}\n\n"
        f"- 日時: {shaped.get('created_at') or '—'}\n"
        f"- 時間: {shaped.get('duration_human') or '—'}\n"
        f"- Genspark: {project_url}\n"
        f"- Meeting ID: {shaped.get('id') or '—'}\n"
        f"- 共有: {share}\n\n"
        f"---\n\n"
        f"{summary.strip()}\n"
    )


def date_stamp_from_meeting(shaped: dict[str, Any], override: str | None) -> str:
    if override:
        s = override.strip().replace("/", "-")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            return s.replace("-", "")
        if re.fullmatch(r"\d{8}", s):
            return s
    created = str(shaped.get("created_at") or "")
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", created)
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}"
    return datetime.now().strftime("%Y%m%d")


def write_minutes_md(shaped: dict[str, Any], date_stamp: str) -> Path:
    md = meeting_to_markdown(shaped)
    dest = resolve_drive_minutes_dir() / f"{date_stamp}_家族会議_Genspark議事録.md"
    dest.write_text(md, encoding="utf-8")
    # docs ミラーは容量方針上不要（Drive 正本）
    return dest


def print_summary_block(shaped: dict[str, Any], md_path: Path) -> None:
    print("📎 家族会議・週次（議事録）")
    print(f"- title: {shaped.get('title')}")
    print(f"- meeting_id: {shaped.get('id')}")
    print(f"- project_id: {shaped.get('project_id')}")
    print(f"- md: {md_path}")
    summary = shaped.get("summary")
    if isinstance(summary, str) and summary.strip():
        lines = [ln for ln in summary.strip().splitlines() if ln.strip()][:8]
        print("- 要約抜粋:")
        for ln in lines:
            print(f"  {ln[:120]}")


def print_notion_hint(md_path: Path, shaped: dict[str, Any], page_id: str | None) -> None:
    project_id = shaped.get("project_id") or ""
    share = (
        f"https://www.genspark.ai/meetingnotes/SharedMeetingNotes?id={project_id}"
        if project_id
        else ""
    )
    print()
    print("📎 Notion 添付ヒント（MCP）")
    if page_id:
        print(f"- page_id: {page_id}")
    print(f"- ファイル: {md_path.name}")
    print("- 末尾に追加する見出し例:")
    print("  ## Genspark 議事録（YYYY-MM-DD）")
    if share:
        print(f"  - 共有リンク: {share}")
    print("  <file src=\"file-upload://…\">（create-attachment の suggested_markdown）")
    print("- NotebookLM: 上記 MD を固定ノート「家族会議」へソース追加（ノートは増やさない）")
    print(
        "- インフォ: jarvis_notebooklm_studio_run.py "
        "--notebook-key family_meeting_weekly --artifact infographic "
        "--prompt-file docs/N1_NotebookLM/13_家族会議_週次/Studioプロンプト_家族会議_週次インフォ.md "
        "--confirm-generate --wait-and-save"
    )


def cmd_attach_minutes(args: argparse.Namespace) -> int:
    project_id = extract_project_id(args.genspark_url or args.project_id or "")
    shaped = find_meeting(
        keyword=args.keyword,
        date_from=args.date_from or args.date,
        project_id=project_id or None,
        task_id=args.task_id,
    )
    stamp = date_stamp_from_meeting(shaped, args.date)
    md_path = write_minutes_md(shaped, stamp)
    print_summary_block(shaped, md_path)
    if args.print_notion_hint:
        print_notion_hint(md_path, shaped, args.notion_page_id)
    # 作業用コピー（/tmp）も残すと MCP 添付しやすい
    tmp = Path(f"/tmp/{md_path.name}")
    shutil.copy2(md_path, tmp)
    print(f"- tmp_copy: {tmp}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="家族会議・週次（Genspark→Drive MD）")
    p.add_argument(
        "--attach-minutes",
        action="store_true",
        help="Genspark から議事録 MD を生成し Drive 13_家族会議_週次/議事録/ へ保存",
    )
    p.add_argument("--keyword", default="家族会議", help="search キーワード")
    p.add_argument("--date", default=None, help="YYYY-MM-DD（ファイル名スタンプ／date-from）")
    p.add_argument("--date-from", default=None, help="search --date-from")
    p.add_argument("--task-id", default=None, help="Genspark meeting task id")
    p.add_argument("--project-id", default=None, help="共有 URL の id（project_id）")
    p.add_argument("--genspark-url", default=None, help="SharedMeetingNotes / agents URL")
    p.add_argument("--notion-page-id", default=None, help="案内用（添付は MCP）")
    p.add_argument(
        "--print-notion-hint",
        action="store_true",
        help="Notion MCP 添付手順のヒントを出す",
    )
    args = p.parse_args()
    if not args.attach_minutes:
        p.print_help()
        return 2
    return cmd_attach_minutes(args)


if __name__ == "__main__":
    raise SystemExit(main())
