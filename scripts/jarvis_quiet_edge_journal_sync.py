#!/usr/bin/env python3
"""Quiet Edge: Obsidian ★Journal → vital_journal_daily 同期.

Vercel はローカル Disk を見ないため、Mac で抜粋を Supabase に投影する。
睡眠関連（夜の防衛線など）を優先抽出し、分析用タグも付ける。
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

try:
    from supabase import create_client
except ImportError:
    print("need supabase-py", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
YAML_PATH = ROOT / "config" / "dashboard_lanes.yaml"
ENV_PATH = ROOT / ".env.jarvis_private"
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")


def load_env() -> None:
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def journal_dir() -> Path:
    reg = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8")) or {}
    raw = (
        os.environ.get("JARVIS_LANES_OBSIDIAN_JOURNAL")
        or os.environ.get("QUIET_EDGE_JOURNAL_DIR")
        or reg.get("obsidian_journal")
        or ""
    )
    return Path(str(raw)).expanduser()


def clean_line(s: str) -> str:
    s = re.sub(r"[*`_]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_sleep_signal(text: str) -> str:
    for line in text.splitlines():
        if "夜の防衛線" in line:
            return clean_line(line)[:220]
    # fallback: first sleep-ish line
    for line in text.splitlines():
        if any(k in line for k in ("就寝", "睡眠", "いびき", "飲酒")):
            return clean_line(line)[:220]
    return ""


def extract_sleep_tags(text: str, signal: str) -> list[str]:
    blob = f"{signal}\n{text}"
    tags: list[str] = []
    if "夜の防衛線" in blob:
        tags.append("defense_line")
    if any(k in blob for k in ("達成（〇）", "就寝達成", "達成(〇)", "`達成")):
        tags.append("bedtime_ok")
    if any(
        k in blob
        for k in ("就寝超過", "超過（×）", "24:00超過", "就寝未定", "遅延", "未達成")
    ):
        tags.append("bedtime_late")
    if any(k in blob for k in ("飲酒", "酒", "ワイン", "ビール", "飲み会")):
        tags.append("alcohol")
    if any(k in blob for k in ("鼻", "鼻づまり", "花粉症")):
        tags.append("nasal")
    if any(k in blob for k in ("残業", "深夜作業", "深追い", "没頭")):
        tags.append("late_work")
    if any(k in blob for k in ("疲れ", "疲労", "爆睡", "猛烈な眠気")):
        tags.append("fatigue")
    # unique preserve order
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def excerpt_text(text: str, signal: str, max_chars: int = 900) -> str:
    """睡眠関連を先頭に置き、その後に本文要約を足す。"""
    chunks: list[str] = []
    if signal:
        chunks.append(signal)

    # pull a few more sleep-related lines
    sleep_lines: list[str] = []
    other: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if signal and clean_line(s) == signal:
            continue
        if any(
            k in s
            for k in (
                "就寝",
                "睡眠",
                "いびき",
                "夜の防衛",
                "飲酒",
                "風呂",
                "24:00",
                "鼻",
            )
        ):
            sleep_lines.append(s)
        else:
            other.append(s)

    for s in sleep_lines[:6]:
        chunks.append(s)
        if sum(len(c) for c in chunks) >= max_chars:
            break
    if sum(len(c) for c in chunks) < max_chars // 2:
        for s in other[:8]:
            chunks.append(s)
            if sum(len(c) for c in chunks) >= max_chars:
                break
    out = "\n".join(chunks)
    return out[:max_chars]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    load_env()
    jdir = journal_dir()
    if not jdir.is_dir():
        print(f"journal dir missing: {jdir}", file=sys.stderr)
        return 2

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (
        os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("JARVIS_SUPABASE_SECRET_KEY")
        or ""
    ).strip()
    if not url or not key:
        print("JARVIS_SUPABASE_* missing", file=sys.stderr)
        return 2

    since = date.today() - timedelta(days=max(1, args.days) - 1)
    rows: list[dict] = []
    for f in sorted(jdir.rglob("????-??-??.md")):
        m = DATE_RE.match(f.name)
        if not m:
            continue
        d = date.fromisoformat(m.group(1))
        if d < since:
            continue
        raw = f.read_text(encoding="utf-8", errors="ignore")
        signal = extract_sleep_signal(raw)
        tags = extract_sleep_tags(raw, signal)
        ex = excerpt_text(raw, signal)
        rows.append(
            {
                "recorded_at": m.group(1),
                "excerpt": ex,
                "char_count": len(raw),
                "sleep_signal": signal,
                "sleep_tags": tags,
                "source": "obsidian_star_journal",
                "payload": {"filename": f.name, "tags": tags},
                "updated_at": datetime.utcnow().isoformat() + "Z",
            }
        )

    print(f"dir={jdir} files={len(rows)} since={since.isoformat()}")
    if args.dry_run:
        for r in rows[-5:]:
            print(
                r["recorded_at"],
                r["sleep_tags"],
                (r["sleep_signal"] or "")[:70],
            )
        return 0

    sb = create_client(url, key)
    batch = 40
    for i in range(0, len(rows), batch):
        chunk = rows[i : i + batch]
        sb.table("vital_journal_daily").upsert(
            chunk, on_conflict="recorded_at"
        ).execute()
        print(f"upserted {i + len(chunk)}/{len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
