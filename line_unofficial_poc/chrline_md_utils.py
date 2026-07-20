#!/usr/bin/env python3
from __future__ import annotations

import re

TIMELINE_MARKER = "## やり取り（時系列）"


def make_summary(body: str, max_len: int = 50) -> str:
    if not body or not body.strip():
        return "（要約を記入）"
    text = re.sub(r"\s+", " ", body.strip())
    for prefix in (
        r"^松野\s*様\s*",
        r"^お世話になっております[.。]?\s*",
        r"^お世話になります[.。]?\s*",
        r"^[\s　]+",
    ):
        text = re.sub(prefix, "", text)
    text = text.strip()
    if not text:
        return "（要約を記入）"
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


_LINE_HEADING_MARKERS = ("[本文なし", "[メディア]", "[画像]", "[動画]", "[音声]", "[ファイル]")


def line_heading_tail(body: str) -> str:
    text = (body or "").strip().split("\n", 1)[0].strip()
    if any(text.startswith(m) for m in _LINE_HEADING_MARKERS):
        return text if len(text) <= 80 else text[:79] + "…"
    return ""


def format_line_heading(
    date_part: str,
    org_label: str,
    tag: str,
    *,
    body_for_tail: str = "",
    extra_suffix: str = "",
) -> str:
    tail = line_heading_tail(body_for_tail)
    if extra_suffix:
        tail = f"{tail}{extra_suffix}"
    return f"### {date_part}｜{org_label}｜{tag}｜{tail}"


def flatten_notion_headings(body: str) -> str:
    if not body:
        return ""
    lines = body.split("\n")
    out: list[str] = []
    for line in lines:
        if re.match(r"^### \d{4}/\d{2}/\d{2}", line):
            out.append(line)
        elif re.match(r"^### +", line):
            rest = re.sub(r"^### +\s*", "", line)
            out.append(f"**{rest}**" if rest else line)
        elif re.match(r"^## +", line):
            rest = re.sub(r"^## +\s*", "", line)
            out.append(f"**{rest}**" if rest else line)
        elif re.match(r"^# +", line):
            rest = re.sub(r"^# +\s*", "", line)
            out.append(f"**{rest}**" if rest else line)
        else:
            out.append(line)
    return "\n".join(out)


def wrap_details(body: str) -> str:
    flat = flatten_notion_headings(body)
    return f"<details>\n<summary>本文</summary>\n\n{flat}\n\n</details>"


def insert_block_after_timeline_header(content: str, block: str) -> str:
    if TIMELINE_MARKER not in content:
        return content + block
    start = content.find(TIMELINE_MARKER)
    after = content[start:]
    m = re.search(r"\n\n### [12]\d{3}/\d{2}/\d{2}", after)
    if m:
        pos = start + m.start() + 2
        return content[:pos] + block.strip() + "\n\n" + content[pos:]
    pos = start + len(TIMELINE_MARKER)
    return content[:pos].rstrip() + "\n\n" + block.strip() + "\n\n" + content[pos:].lstrip()
