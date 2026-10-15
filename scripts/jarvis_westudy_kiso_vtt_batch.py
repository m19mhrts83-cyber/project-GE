#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基礎講座レッスンの Vimeo 自動字幕を一括取得 → OneDrive jarvis/ へ。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_westudy_lesson_vtt_to_md import fetch_lesson_vtts, render_md  # noqa: E402

CONFIG = REPO / "config" / "kamiooya_kiso_transcripts.yaml"
ONEDRIVE_215 = (
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
)
CATALOG_JSON = REPO / "apps" / "jarvis-dashboard" / "data" / "kiso_transcripts.json"


def load_config() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}


def root_dir(cfg: dict) -> Path:
    rel = (cfg.get("onedrive_root") or "").strip()
    return ONEDRIVE_215 / rel


def out_path_for(jarvis_dir: Path, slug: str) -> Path:
    return jarvis_dir / f"基礎講座文字起こし_{slug}.md"


def summarize_file(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    title = ""
    cues = 0
    for line in text.splitlines():
        if line.startswith("タイトル:"):
            title = line.split(":", 1)[-1].strip()
        if line.startswith("キュー数:"):
            try:
                cues += int(line.split(":", 1)[-1].strip())
            except ValueError:
                pass
        if line.startswith("[") and "]" in line[:12]:
            cues += 1  # fallback rough
    # prefer explicit キュー数 sum; if we double-counted, clamp via unique heuristic
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "title": title,
        "mtime": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
    }


def write_catalog(cfg: dict, lessons: list[dict]) -> None:
    payload = {
        "version": 1,
        "updated": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "policy": cfg.get("policy") or {},
        "onedrive_root": cfg.get("onedrive_root"),
        "lessons": lessons,
    }
    CATALOG_JSON.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"# wrote {CATALOG_JSON}")


def refresh_catalog_only(cfg: dict) -> int:
    root = root_dir(cfg)
    jarvis = root / "jarvis"
    imamura_c = root / "imamura" / "canonical"
    imamura_i = root / "imamura" / "inbox"
    lessons: list[dict] = []
    for slug in cfg.get("priority_slugs") or []:
        jp = out_path_for(jarvis, slug)
        ip = None
        for folder in (imamura_c, imamura_i):
            for pat in (f"*{slug}*", f"*{slug.replace('-', '_')}*"):
                hits = list(folder.glob(pat)) if folder.exists() else []
                if hits:
                    ip = hits[0]
                    break
            if ip:
                break
        row = {
            "slug": slug,
            "jarvis_status": "ready" if jp.exists() and jp.stat().st_size > 200 else "missing",
            "imamura_status": "ready" if ip else "missing",
            "jarvis_file": jp.name if jp.exists() else None,
            "imamura_file": ip.name if ip else None,
        }
        if jp.exists():
            row.update({k: v for k, v in summarize_file(jp).items() if k != "path"})
            row["title"] = row.get("title") or slug
        lessons.append(row)
    # also list extra jarvis files not in priority
    known = {x["slug"] for x in lessons}
    if jarvis.exists():
        for p in sorted(jarvis.glob("基礎講座文字起こし_*.md")):
            slug = p.stem.replace("基礎講座文字起こし_", "", 1)
            if slug in known:
                continue
            s = summarize_file(p)
            lessons.append(
                {
                    "slug": slug,
                    "title": s.get("title") or slug,
                    "jarvis_status": "ready",
                    "imamura_status": "missing",
                    "jarvis_file": p.name,
                    "imamura_file": None,
                    "bytes": s.get("bytes"),
                    "mtime": s.get("mtime"),
                    "extra": True,
                }
            )
    write_catalog(cfg, lessons)
    return 0


def run_batch(cfg: dict, *, slugs: list[str], headless: bool, force: bool) -> int:
    root = root_dir(cfg)
    jarvis = root / "jarvis"
    jarvis.mkdir(parents=True, exist_ok=True)
    ok = 0
    fail = 0
    for slug in slugs:
        out = out_path_for(jarvis, slug)
        if out.exists() and out.stat().st_size > 500 and not force:
            print(f"skip {slug} (exists)")
            ok += 1
            continue
        print(f"fetch {slug} …")
        try:
            data = fetch_lesson_vtts(slug, headless=headless)
            md = render_md(data, source_note="jarvis_westudy_kiso_vtt_batch.py")
            out.write_text(md, encoding="utf-8")
            cues = sum(len(v.get("cues") or []) for v in data.get("videos") or [])
            print(f"  ✅ {out.name} cues={cues}")
            ok += 1
        except Exception as e:
            print(f"  ❌ {slug}: {e}")
            fail += 1
    refresh_catalog_only(cfg)
    print(f"# done ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--priority", action="store_true", help="config の priority_slugs を取得")
    ap.add_argument("--slug", action="append", default=[], help="個別 slug（複数可）")
    ap.add_argument("--catalog-only", action="store_true", help="取得せずカタログだけ更新")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    cfg = load_config()
    if args.catalog_only:
        return refresh_catalog_only(cfg)
    slugs = list(args.slug)
    if args.priority or not slugs:
        slugs = list(cfg.get("priority_slugs") or [])
    if not slugs:
        print("no slugs", file=sys.stderr)
        return 2
    return run_batch(cfg, slugs=slugs, headless=not args.show, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
