#!/usr/bin/env python3
"""5.やり取り.md のブロック列挙・プレースホルダー検出・in-place 置換。"""
from __future__ import annotations

import re
from dataclasses import dataclass

from chrline_md_utils import format_line_heading, wrap_details

PLACEHOLDER_PREFIX = "[本文なし"
RE_HEADING = re.compile(
    r"^### (?P<date>[12]\d{3}/\d{2}/\d{2})｜(?P<org>[^｜]+)｜(?P<tag>[^｜]+)｜(?P<summary>.*)$"
)
RE_DK_COMMENT = re.compile(r"<!--\s*chrline-dk:([^>]+)\s*-->")


@dataclass
class YoritooriBlock:
    """やり取りタイムライン内の1ブロック（見出し〜---）。"""

    start: int
    end: int
    heading: str
    body: str
    raw: str
    date_part: str
    org_label: str
    tag: str
    summary: str
    dk: str | None
    is_placeholder: bool

    @property
    def is_group_tag(self) -> bool:
        return "グループ" in self.tag or "1:1" not in self.tag and "グループ" in self.tag


def is_placeholder_text(text: str) -> bool:
    t = (text or "").lstrip()
    return t.startswith(PLACEHOLDER_PREFIX) or PLACEHOLDER_PREFIX in t


def extract_dk_from_block(raw: str) -> str | None:
    m = RE_DK_COMMENT.search(raw)
    return m.group(1).strip() if m else None


def parse_heading(heading_line: str) -> tuple[str, str, str, str] | None:
    m = RE_HEADING.match(heading_line.strip())
    if not m:
        return None
    return m.group("date"), m.group("org"), m.group("tag"), m.group("summary")


def iter_yoritoori_blocks(content: str) -> list[YoritooriBlock]:
    """`### YYYY/MM/DD` 始まりのブロックを時系列マーカー以降から列挙。"""
    marker = "## やり取り（時系列）"
    start_idx = content.find(marker)
    if start_idx < 0:
        search_in = content
        base = 0
    else:
        search_in = content[start_idx:]
        base = start_idx

    pattern = re.compile(r"(?m)^### [12]\d{3}/\d{2}/\d{2}｜")
    matches = list(pattern.finditer(search_in))
    if not matches:
        return []

    blocks: list[YoritooriBlock] = []
    for i, m in enumerate(matches):
        block_start = base + m.start()
        block_end = base + matches[i + 1].start() if i + 1 < len(matches) else len(content)
        raw = content[block_start:block_end].rstrip()
        lines = raw.split("\n")
        heading = lines[0] if lines else ""
        parsed = parse_heading(heading)
        if not parsed:
            continue
        date_part, org_label, tag, summary = parsed
        body_lines = lines[1:]
        while body_lines and not body_lines[0].strip():
            body_lines.pop(0)
        while body_lines and body_lines[-1].strip() in ("", "---"):
            body_lines.pop()
        if body_lines and body_lines[-1].strip() == "---":
            body_lines.pop()
        body = "\n".join(body_lines).strip()
        dk = extract_dk_from_block(raw)
        ph = is_placeholder_text(summary) or is_placeholder_text(body)
        blocks.append(
            YoritooriBlock(
                start=block_start,
                end=block_end,
                heading=heading,
                body=body,
                raw=raw,
                date_part=date_part,
                org_label=org_label,
                tag=tag,
                summary=summary,
                dk=dk,
                is_placeholder=ph,
            )
        )
    return blocks


def find_placeholder_blocks(content: str) -> list[YoritooriBlock]:
    return [b for b in iter_yoritoori_blocks(content) if b.is_placeholder]


def build_yoritoori_block(
    *,
    date_part: str,
    org_label: str,
    tag: str,
    body: str,
    dk: str | None = None,
) -> str:
    dk_line = f"<!-- chrline-dk:{dk} -->" if dk else ""
    heading = format_line_heading(
        date_part, org_label, tag, body_for_tail=body, extra_suffix=dk_line
    )
    return f"""{heading}

{wrap_details(body)}

---
"""


def replace_block_at(content: str, block: YoritooriBlock, new_block: str) -> str:
    new_block = new_block.strip() + "\n\n"
    return content[: block.start] + new_block + content[block.end :].lstrip("\n")


def replace_placeholder_block(
    content: str,
    *,
    date_part: str,
    tag: str,
    org_label: str | None = None,
    dk: str | None = None,
    new_body: str,
    new_dk: str | None = None,
) -> tuple[str, bool]:
    """
    条件に合う最初のプレースホルダーブロックを置換。
    戻り値: (新content, 置換したか)
    """
    for block in find_placeholder_blocks(content):
        if dk and block.dk and block.dk != dk:
            continue
        if dk and not block.dk:
            pass
        elif dk is None:
            if block.date_part != date_part:
                continue
            if org_label and block.org_label != org_label:
                continue
            if block.tag != tag:
                continue
        new_block = build_yoritoori_block(
            date_part=block.date_part,
            org_label=block.org_label,
            tag=block.tag,
            body=new_body,
            dk=new_dk or dk or block.dk,
        )
        return replace_block_at(content, block, new_block), True
    return content, False


def upsert_resolved_block(
    content: str,
    *,
    date_part: str,
    org_label: str,
    tag: str,
    body: str,
    dk: str | None = None,
) -> tuple[str, bool]:
    """
    retry 成功時: 既存プレースホルダーがあれば in-place 置換、なければ先頭追記用ブロック文字列のみ返す。
    戻り値: (content, replaced_inplace)
    """
    replaced = False
    if dk:
        for block in find_placeholder_blocks(content):
            if block.dk == dk:
                nb = build_yoritoori_block(
                    date_part=block.date_part,
                    org_label=block.org_label,
                    tag=block.tag,
                    body=body,
                    dk=dk,
                )
                content = replace_block_at(content, block, nb)
                replaced = True
                break
    if not replaced:
        content, replaced = replace_placeholder_block(
            content,
            date_part=date_part,
            tag=tag,
            org_label=org_label,
            dk=dk,
            new_body=body,
            new_dk=dk,
        )
    return content, replaced
