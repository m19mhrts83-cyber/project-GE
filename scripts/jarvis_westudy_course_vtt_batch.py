#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""神大家0〜4（基礎以外も含む）レッスンの Vimeo 自動字幕を一括取得 → OneDrive へ MD 保存。

AI 使用料ゼロの経路（WeStudy ログイン → Vimeo の日本語自動字幕 VTT）。
字幕のない動画は scripts/jarvis_westudy_whisper_fallback.py（ローカル Whisper）で補う。

レッスン一覧は Supabase comments の lesson_desc 行（週次取込済み）から作る。
読むのは course_tab / section_name / lesson_title / lesson_url の数百行だけ（Free の通信量を抑える）。
取込済み（knowledge_sources に westudy:{slug}: がある）レッスンは飛ばす。

例:
  ~/selenium_env/venv/bin/python scripts/jarvis_westudy_course_vtt_batch.py --course 神大家2.応用
  ~/selenium_env/venv/bin/python scripts/jarvis_westudy_course_vtt_batch.py   # 0,2,3,4 をすべて
取得後の登録（差分のみ追加・誤記補正つき）は出力の最後に表示するコマンドで行う。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
QA_SCRIPTS = REPO / "215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/scripts"
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(QA_SCRIPTS))

ONEDRIVE_215 = Path.home() / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
TRANSCRIPT_REL = "C1_cursor/1c_神・大家さん倶楽部_AI推進/講座_文字起こし"
STATUS_DIR = REPO / "apps/jarvis-dashboard/data/course_transcripts"
DEFAULT_COURSES = ["神大家0.はじめに", "神大家2.応用", "神大家3.継承", "神大家4.グルコン"]


def course_code(course: str) -> str:
    m = re.match(r"神大家(\d+)", course)
    return f"course{m.group(1)}" if m else re.sub(r"\W+", "_", course)


def course_dir(course: str) -> Path:
    return ONEDRIVE_215 / TRANSCRIPT_REL / course / "jarvis"


def graph_root(course: str) -> str:
    """import_vimeo_transcripts.py の --graph-root（origin_path 記録用）。"""
    return f"215_神・大家さん倶楽部/{TRANSCRIPT_REL}/{course}/jarvis"


def md_name(slug: str) -> str:
    return f"文字起こし_{urllib.parse.unquote(slug).replace('/', '_')}.md"


def status_path(course: str) -> Path:
    return STATUS_DIR / f"{course_code(course)}_status.json"


def load_lessons(client, course: str) -> list[dict]:
    rows = (
        client.table("comments")
        .select("section_name,lesson_title,lesson_url")
        .eq("source_kind", "lesson_desc")
        .eq("course_tab", course)
        .order("id")
        .execute()
        .data
    )
    lessons, seen = [], set()
    for r in rows:
        url = (r.get("lesson_url") or "").strip()
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        if not slug or slug in seen:
            continue
        seen.add(slug)
        title = (r.get("lesson_title") or "").split("\t", 1)[0].strip()
        lessons.append({"slug": slug, "title": title or slug, "url": url, "section": r.get("section_name")})
    return lessons


def imported_slugs(client) -> set[str]:
    rows = client.table("knowledge_sources").select("source_key").like("source_key", "westudy:%").execute().data
    return {r["source_key"].split(":")[1] for r in rows if r.get("source_key", "").count(":") >= 2}


def summarize_md(text: str) -> list[dict]:
    """MD から動画ごとのキュー数を読む（再実行時に取得し直さないため）。"""
    videos: list[dict] = []
    for line in text.splitlines():
        m = re.match(r"^## 動画 \d+: Vimeo (\d+)\b", line)
        if m:
            videos.append({"video_id": m.group(1), "cues": 0})
        elif videos and re.match(r"^\[\d+:\d{2}(?::\d{2})?\]\s", line):
            videos[-1]["cues"] += 1
    return videos


def lesson_status(videos: list[dict]) -> str:
    if not videos:
        return "no_video"
    return "vtt_ready" if any(v["cues"] for v in videos) else "no_subtitles"


def run_course(client, course: str, *, skip: set[str], headless: bool, force: bool, limit: int | None) -> dict:
    import jarvis_westudy_lesson_vtt_to_md as vtt

    out_dir = course_dir(course)
    out_dir.mkdir(parents=True, exist_ok=True)
    lessons = [L for L in load_lessons(client, course) if L["slug"] not in skip]
    if limit:
        lessons = lessons[:limit]
    print(f"# {course}: 対象 {len(lessons)} レッスン（取込済み・基礎と重複は除外）", flush=True)
    driver_open = False
    rows = []
    try:
        for i, L in enumerate(lessons, 1):
            path = out_dir / md_name(L["slug"])
            if path.exists() and path.stat().st_size > 200 and not force:
                videos = summarize_md(path.read_text(encoding="utf-8"))
            else:
                data = None
                for attempt in range(2):
                    try:
                        if not driver_open:
                            vtt.open_logged_in_driver(headless=headless)
                            driver_open = True
                        data = vtt.fetch_lesson_vtts_logged_in(L["slug"])
                        break
                    except Exception as e:  # セッション切れ等は1回だけログインし直す
                        print(f"  ⚠️ {L['slug']}: {type(e).__name__}: {str(e)[:120]}", flush=True)
                        vtt.close_driver()
                        driver_open = False
                        time.sleep(3)
                if data is None:
                    rows.append({**L, "jarvis_file": path.name, "status": "error", "videos": []})
                    continue
                data["title"] = data.get("title") or L["title"]
                path.write_text(
                    vtt.render_md(data, source_note="jarvis_westudy_course_vtt_batch.py", heading=f"{course} 文字起こし"),
                    encoding="utf-8",
                )
                videos = [{"video_id": v.get("video_id"), "cues": len(v.get("cues") or [])} for v in data.get("videos") or []]
            row = {**L, "jarvis_file": path.name, "status": lesson_status(videos), "videos": videos}
            rows.append(row)
            print(f"  [{i}/{len(lessons)}] {row['status']:<12} videos={len(videos)} cues={sum(v['cues'] for v in videos)} {L['slug']}", flush=True)
    finally:
        if driver_open:
            vtt.close_driver()
    payload = {
        "course": course,
        "updated": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "transcript_dir": str(out_dir),
        "graph_root": graph_root(course),
        "lessons": rows,
    }
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    status_path(course).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def summary(payload: dict) -> dict:
    lessons = payload["lessons"]
    vids = [v for L in lessons for v in L["videos"]]
    return {
        "course": payload["course"],
        "lessons": len(lessons),
        "vtt_ready_lessons": sum(L["status"] == "vtt_ready" for L in lessons),
        "no_video_lessons": sum(L["status"] == "no_video" for L in lessons),
        "error_lessons": sum(L["status"] == "error" for L in lessons),
        "videos": len(vids),
        "videos_with_subtitles": sum(1 for v in vids if v["cues"]),
        "videos_without_subtitles": sum(1 for v in vids if not v["cues"]),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--course", action="append", help="course_tab（複数可）。未指定は 0,2,3,4")
    ap.add_argument("--force", action="store_true", help="既存MDがあっても取り直す")
    ap.add_argument("--show", action="store_true", help="ブラウザを表示")
    ap.add_argument("--limit", type=int, help="各コース先頭N件だけ（動作確認用）")
    ap.add_argument("--status-dir", type=Path, help="status JSON の置き場（週次はリポジトリ外に書く）")
    args = ap.parse_args()
    global STATUS_DIR
    if args.status_dir:
        STATUS_DIR = args.status_dir.expanduser()

    from embed_to_supabase import load_env, get_client

    load_env()
    client = get_client()
    kiso = json.loads((REPO / "apps/jarvis-dashboard/data/kiso_course_status.json").read_text(encoding="utf-8"))
    skip = imported_slugs(client) | {L["slug"] for L in kiso.get("lessons") or []}
    results = []
    for course in args.course or DEFAULT_COURSES:
        payload = run_course(client, course, skip=skip, headless=not args.show, force=args.force, limit=args.limit)
        skip |= {L["slug"] for L in payload["lessons"]}  # コースをまたぐ重複レッスンは最初のコースで扱う
        results.append(summary(payload))
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print("\n# 登録コマンド（差分のみ・誤記補正つき）:")
    importer = QA_SCRIPTS / "import_vimeo_transcripts.py"
    for course in args.course or DEFAULT_COURSES:
        print(
            f"~/selenium_env/venv/bin/python '{importer}' --manifest '{status_path(course)}' "
            f"--course '{course}' --input-dir '{course_dir(course)}' --graph-root '{graph_root(course)}' --apply --embed --mirror-raimo"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
