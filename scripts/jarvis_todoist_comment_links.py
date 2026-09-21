#!/usr/bin/env python3
"""Todoist コメント用: アウトプットを Markdown ハイパーリンクに整形する。

Todoist はコメントで Markdown リンク `[表示](https://…)` をサポートする。
相対パスは **origin/main に実在するときだけ** GitHub／Pages の https にする。
未push・新規ファイルは偽リンク（404）にせず、ローカルパス表記にする。
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Iterable
from urllib.parse import quote

REPO = Path(__file__).resolve().parents[1]
DEFAULT_GITHUB = "https://github.com/m19mhrts83-cyber/project-GE"
DEFAULT_PAGES = "https://m19mhrts83-cyber.github.io/project-GE"
DEFAULT_DASH = "https://jarvis-dashboard-amber.vercel.app"


def _github_base() -> str:
    return (os.environ.get("JARVIS_TODOIST_GITHUB_BASE") or DEFAULT_GITHUB).rstrip("/")


def _pages_base() -> str:
    return (os.environ.get("JARVIS_TODOIST_PAGES_BASE") or DEFAULT_PAGES).rstrip("/")


def _dash_base() -> str:
    return (os.environ.get("JARVIS_DASHBOARD_URL") or DEFAULT_DASH).rstrip("/")


def _label_for_url(url: str, fallback: str) -> str:
    if "jarvis-dashboard" in url or "jarvis-trade-desk" in url:
        return "ダッシュボード"
    if "github.com" in url and "/blob/" in url:
        return Path(url.split("/blob/", 1)[-1].split("?", 1)[0]).name or fallback
    if "github.io" in url:
        return Path(url.rstrip("/").split("/")[-1]) or "Pages"
    if url.startswith("http"):
        m = re.match(r"https?://([^/]+)(/.*)?$", url)
        if m:
            host = m.group(1)
            path = (m.group(2) or "").rstrip("/")
            leaf = path.split("/")[-1] if path else host
            return leaf[:40] or host
    return fallback[:40] or "link"


def _on_origin_main(rel: str) -> bool:
    """True if path exists on origin/main (avoids Todoist 404 for unpushed files)."""
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO), "cat-file", "-e", f"origin/main:{rel}"],
            capture_output=True,
            timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def resolve_output_href(raw: str) -> tuple[str, str]:
    """Return (display_label, href_or_plain). href は https 優先。解決不可なら plain。"""
    s = (raw or "").strip()
    if not s:
        return ("", "")
    m = re.match(r"^\[([^\]]+)\]\(([^)]+)\)\s*$", s)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    if s.startswith("http://") or s.startswith("https://"):
        return _label_for_url(s, s), s

    if s.startswith("/"):
        href = f"{_dash_base()}{s}"
        return _label_for_url(href, s), href

    rel = s[2:] if s.startswith("./") else s

    try:
        p = Path(s).expanduser()
        if p.is_absolute():
            try:
                rel = str(p.resolve().relative_to(REPO.resolve()))
            except ValueError:
                return Path(s).name or s, s
    except Exception:
        pass

    # docs HTML → Pages（公開済み想定）
    if rel.startswith("docs/") and rel.endswith(".html"):
        href = f"{_pages_base()}/{quote(rel, safe='/')}"
        return Path(rel).name, href

    repo_prefixes = (
        "scripts/",
        "config/",
        "apps/",
        ".cursor/rules/",
        "docs/",
        "launchd/",
    )
    if any(rel.startswith(prefix) for prefix in repo_prefixes) or (
        "/" in rel and not rel.startswith("[")
    ):
        if _on_origin_main(rel):
            href = f"{_github_base()}/blob/main/{quote(rel, safe='/')}"
            return Path(rel).name, href
        # 未push: 404リンクを作らない
        return f"{Path(rel).name}（未push・ローカル）", rel

    return s, s


def format_markdown_link(raw: str) -> str:
    label, href = resolve_output_href(raw)
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return f"[{label}]({href})"
    # non-http: plain path (clickableにしない＝Not Found回避)
    return f"`{href}` — {label}" if label and label != href else f"`{href}`"


def format_outputs_block(raws: Iterable[str]) -> list[str]:
    lines: list[str] = []
    for raw in raws:
        md = format_markdown_link(raw)
        if md:
            lines.append(f"- {md}")
    return lines


def split_link_field(raw: str) -> list[str]:
    if not (raw or "").strip():
        return []
    parts = re.split(r"\s*\|\s*|\s*;\s*|\n+", raw.strip())
    return [p.strip() for p in parts if p.strip()]
