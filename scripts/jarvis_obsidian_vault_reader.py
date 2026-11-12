#!/usr/bin/env python3
"""Read-only, allowlist-scoped search and excerpt extraction for the Obsidian Vault."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path, PurePosixPath
from typing import Any

VAULT = Path.home() / "Documents/500_Obsidian_r1"
ALLOWLIST = (
    PurePosixPath("01_Journaling/★Journal"),
    PurePosixPath("04_Permanent Note"),
)
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_EXCERPT_CHARS = 3200
MAX_SNIPPET_CHARS = 900
MAX_FILES_SCANNED = 12000
MAX_BYTES_SCANNED = 64 * 1024 * 1024


class VaultReadError(ValueError):
    """Safe, user-displayable read failure without note contents."""


def _is_allowed(relative: PurePosixPath) -> bool:
    return any(relative == base or base in relative.parents for base in ALLOWLIST)


def _resolve_note(relative_text: str) -> tuple[Path, str]:
    if not isinstance(relative_text, str) or not relative_text or len(relative_text) > 420:
        raise VaultReadError("invalid_source_path")
    if "\\" in relative_text or relative_text.startswith("/"):
        raise VaultReadError("invalid_source_path")
    relative = PurePosixPath(relative_text)
    if any(part in ("", ".", "..") or part.startswith(".") for part in relative.parts):
        raise VaultReadError("invalid_source_path")
    if relative.suffix.lower() != ".md" or not _is_allowed(relative):
        raise VaultReadError("source_path_outside_allowlist")

    root = VAULT.resolve()
    candidate = root.joinpath(*relative.parts)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise VaultReadError("symlink_path_rejected")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise VaultReadError("source_path_not_found")
    if resolved.stat().st_size > MAX_FILE_BYTES:
        raise VaultReadError("source_file_too_large")
    return resolved, relative.as_posix()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        raise VaultReadError("source_read_failed") from None


def _note_date(path: Path, text: str) -> str | None:
    frontmatter = text[: min(len(text), 5000)]
    match = re.search(r"(?m)^date:\s*[\"']?(\d{4}-\d{2}-\d{2})", frontmatter)
    candidate = match.group(1) if match else None
    if not candidate:
        name_match = re.search(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)", path.name)
        candidate = name_match.group(1) if name_match else None
    if not candidate:
        return None
    try:
        return date.fromisoformat(candidate).isoformat()
    except ValueError:
        return None


def _current_heading(lines: list[str], index: int) -> str | None:
    for line in reversed(lines[: index + 1]):
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match:
            return match.group(1).strip()
    return None


def _snippet(lines: list[str], index: int) -> str:
    start = max(0, index - 2)
    end = min(len(lines), index + 3)
    value = "\n".join(lines[start:end]).strip()
    if len(value) > MAX_SNIPPET_CHARS:
        value = value[:MAX_SNIPPET_CHARS].rstrip() + "…"
    return value


def _date_bounds(payload: dict[str, Any]) -> tuple[date | None, date | None]:
    end_text = payload.get("to_date")
    start_text = payload.get("from_date")
    days = payload.get("days")
    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    if days in (7, 30):
        end = today
        return today - timedelta(days=int(days) - 1), end
    try:
        start = date.fromisoformat(start_text) if start_text else None
        end = date.fromisoformat(end_text) if end_text else None
    except (TypeError, ValueError):
        raise VaultReadError("invalid_date_range") from None
    if start and end and start > end:
        raise VaultReadError("invalid_date_range")
    return start, end


def search_notes(payload: dict[str, Any]) -> dict[str, Any]:
    query = str(payload.get("query") or "").strip()
    if len(query) > 200:
        raise VaultReadError("invalid_query")
    terms = [part.casefold() for part in re.split(r"\s+", query) if part]
    start_date, end_date = _date_bounds(payload)
    if not terms and not start_date and not end_date:
        raise VaultReadError("query_or_date_range_required")
    try:
        limit = max(1, min(10, int(payload.get("limit") or 6)))
    except (TypeError, ValueError):
        limit = 6

    root = VAULT.resolve()
    if not root.is_dir():
        raise VaultReadError("canonical_vault_unavailable")
    ranked: list[tuple[int, str, str | None, Path, list[str], list[int]]] = []
    scanned = 0
    bytes_scanned = 0
    scan_truncated = False
    for scope in ALLOWLIST:
        directory = root.joinpath(*scope.parts)
        if directory.is_symlink() or not directory.is_dir():
            continue
        for path in directory.rglob("*.md"):
            if scanned >= MAX_FILES_SCANNED:
                break
            scanned += 1
            if path.is_symlink() or not path.is_file():
                continue
            try:
                relative = PurePosixPath(path.relative_to(root).as_posix())
                size = path.stat().st_size
                if not _is_allowed(relative) or size > MAX_FILE_BYTES:
                    continue
                scope_depth = len(scope.parts)
                if any(part.startswith(".") for part in relative.parts[scope_depth:]):
                    continue
                if bytes_scanned + size > MAX_BYTES_SCANNED:
                    scan_truncated = True
                    break
                bytes_scanned += size
                resolved = path.resolve(strict=True)
                if not resolved.is_relative_to(root):
                    continue
                content = _read_text(resolved)
            except (OSError, ValueError):
                continue
            note_date = _note_date(path, content)
            if start_date or end_date:
                if not note_date:
                    continue
                parsed = date.fromisoformat(note_date)
                if start_date and parsed < start_date:
                    continue
                if end_date and parsed > end_date:
                    continue
            folded = content.casefold()
            if terms and not all(term in folded for term in terms):
                continue
            score = sum(folded.count(term) for term in terms)
            lines = content.splitlines()
            if terms:
                matches = [i for i, line in enumerate(lines) if any(term in line.casefold() for term in terms)]
            else:
                matches = [i for i, line in enumerate(lines) if line.strip() and line.strip() != "---"][:2]
            ranked.append((score, note_date or "", relative.as_posix(), resolved, lines, matches))

    ranked.sort(key=lambda row: (row[0], row[1], row[2]), reverse=True)
    results = []
    for score, note_date, rel_path, _, lines, matches in ranked[:limit]:
        selected = matches[:2]
        excerpts = [
            {"heading": _current_heading(lines, index), "snippet": _snippet(lines, index)}
            for index in selected
        ]
        results.append({
            "source_path": rel_path,
            "date": note_date or None,
            "score": score,
            "excerpts": excerpts,
        })
    return {
        "result_count": len(results),
        "scanned_files": scanned,
        "scan_truncated": scan_truncated,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }


def read_excerpt(payload: dict[str, Any]) -> dict[str, Any]:
    path, relative = _resolve_note(str(payload.get("source_path") or ""))
    content = _read_text(path)
    lines = content.splitlines()
    requested_heading = str(payload.get("heading") or "").strip().lstrip("#").strip()
    chosen_heading = None
    if requested_heading:
        start = None
        start_level = 7
        for index, line in enumerate(lines):
            match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
            if match and match.group(2).strip().casefold() == requested_heading.casefold():
                start = index
                start_level = len(match.group(1))
                chosen_heading = match.group(2).strip()
                break
        if start is None:
            raise VaultReadError("heading_not_found")
        end = len(lines)
        for index in range(start + 1, len(lines)):
            match = re.match(r"^(#{1,6})\s+", lines[index])
            if match and len(match.group(1)) <= start_level:
                end = index
                break
        text = "\n".join(lines[start:end]).strip()
    else:
        text = content.strip()
        first_heading = next((re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line) for line in lines if line.startswith("#")), None)
        chosen_heading = first_heading.group(1).strip() if first_heading else None
    if len(text) > MAX_EXCERPT_CHARS:
        text = text[:MAX_EXCERPT_CHARS].rstrip() + "\n…（抜粋上限）"
    return {
        "source_path": relative,
        "date": _note_date(path, content),
        "heading": chosen_heading,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "excerpt": text,
    }


def process_request(item: dict[str, Any]) -> dict[str, Any]:
    request_type = item.get("request_type")
    payload = item.get("request_payload")
    if not isinstance(payload, dict):
        raise VaultReadError("invalid_request")
    if request_type == "search":
        return search_notes(payload)
    if request_type == "excerpt":
        return read_excerpt(payload)
    raise VaultReadError("unsupported_request")
