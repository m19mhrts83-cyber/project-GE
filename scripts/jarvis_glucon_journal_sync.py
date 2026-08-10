#!/usr/bin/env python3
"""Glucon: Obsidian ★Journal → glucon_journal_days（神大家関連のみ）.

Vercel はローカル Disk を見ないため、Mac で抜粋を jarvis-dashboard に投影する。
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

KEYWORD_RE = re.compile(
    r"神大家|神尾屋|WeStudy|グルコン|物件|融資|空室|戸建|アパート|"
    r"LEAF|ミニテック|Raimo|AI推進|購入相談|管理会社|利回り|修繕|"
    r"インベース|買付|決済|賃料|大家|オリックス|滋賀銀行|公庫",
    re.I,
)

# 会社人事・社内業務（キーワード偶発ヒットで混入しやすい行を除外）
EXCLUDE_RE = re.compile(
    r"人員計画|採用枠|人事部|工数計上|防衛省|コンプライアンス監査|"
    r"社内DX|評価面談|1on1|ワンオンワン|組織改編|異動発令|"
    r"採用協議|チェックリスト展開|工数教育",
    re.I,
)

# 除外行でもこれがあれば神大家関連として残す
STRONG_KAMIOOYA_RE = re.compile(
    r"神大家|神尾屋|WeStudy|グルコン|物件購入|融資実行|空室|戸建|"
    r"アパート|LEAF|ミニテック|大家さん|利回り|買付|決済",
    re.I,
)


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


def find_keywords(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for m in KEYWORD_RE.finditer(text):
        k = m.group(0)
        if k.lower() not in seen:
            seen.add(k.lower())
            found.append(k)
    return found


def line_is_kamiooya(line: str) -> bool:
    """キーワードヒットかつ会社人事行でないこと。"""
    if not KEYWORD_RE.search(line):
        return False
    if EXCLUDE_RE.search(line) and not STRONG_KAMIOOYA_RE.search(line):
        return False
    return True


def extract_kamiooya_excerpt(text: str, max_chars: int = 2400) -> tuple[str, list[str]]:
    """キーワードヒット行と周辺を抜粋。ヒットが無ければ空。"""
    keywords = find_keywords(text)
    if not keywords and not re.search(r"kamiooya|westudy|glucon", text, re.I):
        return "", []

    lines = text.splitlines()
    chunks: list[str] = []
    for i, line in enumerate(lines):
        if not line_is_kamiooya(line):
            continue
        for j in range(max(0, i - 1), min(len(lines), i + 5)):
            # 周辺行も人事だけの行は落とす
            if EXCLUDE_RE.search(lines[j]) and not STRONG_KAMIOOYA_RE.search(lines[j]):
                continue
            t = clean_line(lines[j])
            if t and t not in chunks:
                chunks.append(t)
        if sum(len(c) for c in chunks) >= max_chars:
            break

    # 「主要戦果」ブロック内のキーワード行も優先
    if not chunks:
        in_battle = False
        for line in lines:
            s = line.strip()
            if "主要戦果" in s:
                in_battle = True
                continue
            if s.startswith("## ") or s.startswith("---"):
                in_battle = False
            if in_battle and line_is_kamiooya(s):
                chunks.append(clean_line(s))

    excerpt = "\n".join(chunks)[:max_chars]
    if not excerpt:
        return "", []
    return excerpt, find_keywords(excerpt) or keywords


def main() -> int:
    ap = argparse.ArgumentParser(description="Glucon Journal sync (神大家関連)")
    ap.add_argument("--days", type=int, default=90)
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
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or ""
    ).strip()
    if not url or not key:
        print("JARVIS_SUPABASE_URL / SERVICE_ROLE_KEY missing", file=sys.stderr)
        return 2

    cutoff = date.today() - timedelta(days=max(1, args.days))
    rows: list[dict] = []
    for path in sorted(jdir.glob("*.md")):
        m = DATE_RE.match(path.name)
        if not m:
            continue
        day = date.fromisoformat(m.group(1))
        if day < cutoff:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        excerpt, keywords = extract_kamiooya_excerpt(text)
        if not excerpt:
            continue
        rows.append(
            {
                "recorded_at": day.isoformat(),
                "excerpt": excerpt,
                "keywords": keywords,
                "char_count": len(excerpt),
                "synced_at": datetime.now().astimezone().isoformat(),
            }
        )

    print(f"# glucon journal sync: dir={jdir} hits={len(rows)} days={args.days}")
    if args.dry_run:
        for r in rows[:8]:
            print(f"- {r['recorded_at']} kw={r['keywords'][:5]} chars={r['char_count']}")
        return 0

    sb = create_client(url, key)
    for r in rows:
        sb.table("glucon_journal_days").upsert(r, on_conflict="recorded_at").execute()
    print(f"# upserted={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
