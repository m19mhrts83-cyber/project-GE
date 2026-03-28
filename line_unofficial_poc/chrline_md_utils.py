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
