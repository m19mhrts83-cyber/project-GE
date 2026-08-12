#!/usr/bin/env python3
"""Shared paths/config for NotebookLM Studio automation (separate from MCP)."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
CFG_PATH = REPO / "config" / "notebooklm_studio.yaml"
SELECTORS_PATH = REPO / "config" / "notebooklm_studio_selectors.yaml"
STATE_PATH = REPO / ".jarvis_state" / "notebooklm_studio_run.json"

PROFILE_MCP = Path.home() / "Library/Application Support/notebooklm-mcp/chrome_profile"
STATE_MCP = Path.home() / "Library/Application Support/notebooklm-mcp/browser_state"
PROFILE_STUDIO = Path.home() / "Library/Application Support/notebooklm-studio/chrome_profile"
STATE_STUDIO = Path.home() / "Library/Application Support/notebooklm-studio/browser_state"


def expand(p: str | Path) -> Path:
    return Path(os.path.expanduser(str(p))).resolve()


def load_cfg() -> dict[str, Any]:
    return yaml.safe_load(CFG_PATH.read_text(encoding="utf-8")) or {}


def load_selectors() -> dict[str, Any]:
    if not SELECTORS_PATH.is_file():
        return {}
    return yaml.safe_load(SELECTORS_PATH.read_text(encoding="utf-8")) or {}


def save_selectors(data: dict[str, Any]) -> None:
    SELECTORS_PATH.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def profile_paths(kind: str) -> tuple[Path, Path]:
    """kind: mcp | studio"""
    if kind == "studio":
        return PROFILE_STUDIO, STATE_STUDIO
    return PROFILE_MCP, STATE_MCP


def resolve_notebook_url(cfg: dict[str, Any], url: str | None, key: str | None) -> str:
    if url:
        return url.strip()
    if key:
        nb = (cfg.get("notebooks") or {}).get(key) or {}
        if nb.get("url"):
            return str(nb["url"]).strip()
    return str(cfg.get("default_notebook_url") or "").strip()


def resolve_drive_out(cfg: dict[str, Any], folder: str | None = None) -> Path:
    root = expand(cfg.get("drive_root") or "")
    sub = folder or cfg.get("default_drive_folder") or ""
    out_sub = cfg.get("output_subdir") or "★アウトプット"
    return root / sub / out_sub


def write_run_state(payload: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def extract_prompt_section(text: str, section: str) -> str:
    """
    section: info | slides | full
    Looks for markdown fences under ①/インフォ or ②/スライド headings.
    """
    section = (section or "full").lower().strip()
    if section in ("full", "all", ""):
        return text.strip()

    # Prefer fenced blocks after markers
    markers_info = (
        r"①\s*インフォ",
        r"##\s*①",
        r"インフォグラフィック修正",
        r"prompt-section:\s*info",
    )
    markers_slides = (
        r"②\s*スライド",
        r"##\s*②",
        r"スライド修正",
        r"prompt-section:\s*slides",
    )
    markers = markers_info if section in ("info", "infographic", "インフォ") else markers_slides

    # Split by ``` fences
    parts = re.split(r"```(?:\w+)?\n", text)
    # Odd indices are often fence bodies if text starts outside fence
    # Safer: find marker then next fence
    for mpat in markers:
        m = re.search(mpat, text, re.I)
        if not m:
            continue
        after = text[m.end() :]
        fm = re.search(r"```(?:\w+)?\n(.*?)```", after, re.S)
        if fm:
            return fm.group(1).strip()
    # Fallback: whole file
    return text.strip()


def first_match(page, selectors: list[str], timeout_ms: int = 2000):
    """Return first visible locator or None."""
    for sel in selectors or []:
        try:
            loc = page.locator(sel)
            if loc.count() == 0:
                continue
            target = loc.first
            if target.is_visible(timeout=timeout_ms):
                return target, sel
        except Exception:
            continue
    return None, None
