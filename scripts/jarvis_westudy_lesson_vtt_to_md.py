#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WeStudy レッスン内 Vimeo 自動字幕（VTT）→ Markdown 正本化."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from selenium.webdriver.common.by import By

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "215_kamiooya" / "C1_cursor" / "westudy_common"))
sys.path.insert(0, str(REPO / "ProgramCode" / "alfred_python"))

from auth import load_westudy_env  # noqa: E402
import westudy_lesson_pages as wlp  # noqa: E402

_VTT_TIME_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[.,](\d{3})"
)
_VIMEO_ID_RE = re.compile(r"/video/(\d+)")


def _sec(h: str, m: str, s: str) -> int:
    return int(h) * 3600 + int(m) * 60 + int(s)


def _fmt_ts(sec: int) -> str:
    h, rem = divmod(max(0, sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def normalize_caption_text(text: str) -> str:
    t = (text or "").replace("\n", " ").strip()
    t = re.sub(r"\s+", " ", t)
    # Vimeo 自動字幕: 日本語の文字間スペースを除去
    t = re.sub(
        r"(?<=[\u3000-\u9fff\u3040-\u309f\u30a0-\u30ffA-Za-z0-9]) "
        r"(?=[\u3000-\u9fff\u3040-\u309f\u30a0-\u30ffA-Za-z0-9])",
        "",
        t,
    )
    t = re.sub(r"\s+", " ", t).strip()
    return t


def parse_vtt(body: str) -> list[tuple[int, int, str]]:
    cues: list[tuple[int, int, str]] = []
    blocks = re.split(r"\n\s*\n", body.strip())
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines or lines[0].upper().startswith("WEBVTT"):
            continue
        if lines[0].isdigit():
            lines = lines[1:]
        if not lines:
            continue
        m = _VTT_TIME_RE.search(lines[0])
        if not m:
            continue
        start = _sec(m.group(1), m.group(2), m.group(3))
        end = _sec(m.group(5), m.group(6), m.group(7))
        text = normalize_caption_text(" ".join(lines[1:]))
        if text:
            cues.append((start, end, text))
    return cues


def fetch_lesson_vtts(slug: str, *, headless: bool = True) -> dict:
    load_westudy_env(force=True)
    wlp._HEADLESS = headless
    wlp.driver = wlp.create_driver(headless=headless)
    url = f"https://westudy.co.jp/lesson/{slug}"
    out: dict = {"slug": slug, "url": url, "videos": []}
    try:
        wlp.login_westudy()
        wlp.driver.get(url)
        time.sleep(4)
        out["title"] = (
            wlp.driver.execute_script(
                "return (document.querySelector('h1')||{}).textContent||'';"
            )
            or ""
        ).strip()
        out["description"] = wlp.extract_lesson_description(url) or ""

        seen: set[str] = set()
        for frame in wlp.driver.find_elements(By.TAG_NAME, "iframe"):
            src = frame.get_attribute("src") or ""
            if "vimeo" not in src:
                continue
            m = _VIMEO_ID_RE.search(src)
            if not m:
                continue
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)

            wlp.driver.switch_to.frame(frame)
            time.sleep(1.5)
            tracks = wlp.driver.execute_script(
                """
                return [...document.querySelectorAll('track')].map(t => ({
                  kind: t.kind,
                  label: t.label,
                  src: t.src
                }));
                """
            ) or []
            wlp.driver.switch_to.default_content()

            if not tracks:
                out["videos"].append(
                    {
                        "video_id": vid,
                        "caption_label": None,
                        "cues": [],
                        "error": "no subtitle track",
                    }
                )
                continue

            track = tracks[0]
            vtt_url = track.get("src") or ""
            resp = requests.get(
                vtt_url,
                headers={"Referer": f"https://player.vimeo.com/video/{vid}"},
                timeout=60,
            )
            resp.raise_for_status()
            cues = parse_vtt(resp.text)
            out["videos"].append(
                {
                    "video_id": vid,
                    "caption_label": track.get("label"),
                    "vtt_url": vtt_url[:120],
                    "cue_count": len(cues),
                    "cues": cues,
                }
            )
    finally:
        try:
            wlp.driver.quit()
        except Exception:
            pass
        wlp.driver = None
    return out


def render_md(data: dict, *, source_note: str) -> str:
    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %z")
    lines = [
        f"# 基礎講座文字起こし — {data['slug']}",
        "",
        f"更新: {now}",
        f"レッスン: {data['url']}",
        f"タイトル: {data.get('title', '').strip()}",
        f"取得元: {source_note}",
        "",
        "## 取込状態",
        "",
        "| 項目 | 内容 |",
        "|---|---|",
        "| 方式 | WeStudy ログイン → Vimeo iframe `<track>` → VTT |",
        "| 字幕 | Vimeo 日本語（自動生成） |",
        f"| 動画本数 | {len(data.get('videos') or [])} |",
        "",
    ]
    desc = (data.get("description") or "").strip()
    if desc:
        lines.extend(["## レッスン説明文（ページテキスト）", "", desc, ""])

    for i, vid in enumerate(data.get("videos") or [], start=1):
        label = vid.get("caption_label") or "（字幕なし）"
        lines.extend(
            [
                f"## 動画 {i}: Vimeo {vid.get('video_id')} — {label}",
                "",
            ]
        )
        cues = vid.get("cues") or []
        if not cues:
            lines.append(f"_字幕取得不可: {vid.get('error', 'unknown')}_")
            lines.append("")
            continue
        lines.append(f"キュー数: {len(cues)}")
        lines.append("")
        for start, _end, text in cues:
            lines.append(f"[{_fmt_ts(start)}] {text}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="WeStudy lesson VTT → Markdown")
    parser.add_argument("--slug", required=True, help="lesson slug, e.g. kamiooya-kiso-step5-2")
    parser.add_argument("--output", required=True, help="出力 MD パス")
    parser.add_argument("--show", action="store_true", help="ブラウザ表示")
    parser.add_argument("--json", action="store_true", help="取得結果を JSON で stdout")
    args = parser.parse_args()

    data = fetch_lesson_vtts(args.slug, headless=not args.show)
    if args.json:
        slim = {
            **data,
            "videos": [
                {
                    **{k: v for k, v in v.items() if k != "cues"},
                    "cue_count": len(v.get("cues") or []),
                }
                for v in data.get("videos") or []
            ],
        }
        print(json.dumps(slim, ensure_ascii=False, indent=2))

    out_path = Path(args.output).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    md = render_md(data, source_note="scripts/jarvis_westudy_lesson_vtt_to_md.py")
    out_path.write_text(md, encoding="utf-8")

    ok = sum(len(v.get("cues") or []) for v in data.get("videos") or [])
    print(f"✅ wrote {out_path} ({ok} cues)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
