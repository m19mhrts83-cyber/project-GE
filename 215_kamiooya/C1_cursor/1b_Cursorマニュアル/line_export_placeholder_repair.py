#!/usr/bin/env python3
"""
LINE 公式エクスポート（linelog2py）のメッセージで、5.やり取り.md 内の
CHRLINE プレースホルダー（[本文なし …] 等）を in-place 差し替えする（Phase C 段階2）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from yoritoori_utils import format_line_heading

JST = ZoneInfo("Asia/Tokyo")
PLACEHOLDER_MARKERS = ("[本文なし", "[メディア]")
RE_HEADING = re.compile(
    r"^### (?P<date>[12]\d{3}/\d{2}/\d{2})(?:\s+\d{2}:\d{2})?｜(?P<org>[^｜]+)｜(?P<tag>[^｜]+)｜(?P<summary>.*)$"
)
RE_DETAILS_BODY = re.compile(
    r"(<details>\s*<summary>[^<]*</summary>\s*)(.*?)(\s*</details>)",
    re.DOTALL,
)


@dataclass
class ExportMessage:
    when: datetime
    username: str
    text: str

    @property
    def date_key(self) -> str:
        return self.when.strftime("%Y/%m/%d")


@dataclass
class MdBlock:
    start: int
    end: int
    heading: str
    raw: str
    date_part: str
    org_label: str
    tag: str
    summary: str
    body: str
    is_placeholder: bool


@dataclass
class RepairResult:
    replaced: int = 0
    skipped_no_match: int = 0
    messages_total: int = 0
    placeholders_total: int = 0
    details: list[str] | None = None


def is_placeholder_text(text: str) -> bool:
    t = (text or "").strip()
    return any(m in t for m in PLACEHOLDER_MARKERS)


def parse_export_messages(path: Path) -> tuple[list[ExportMessage], str]:
    """linelog2py でメッセージ列を取得。失敗時はプレーン行パースを試す。"""
    try:
        from linelog2py.reader import Reader
    except ImportError:
        return _parse_plain_lines(path), ""

    raw = path.read_text(encoding="utf-8", errors="replace")
    tmp = path.with_suffix(path.suffix + ".utf8tmp")
    try:
        tmp.write_text(raw, encoding="utf-8")
        items = Reader.readFile(str(tmp))
    except Exception as e:
        plain = _parse_plain_lines(path)
        if plain:
            return plain, ""
        return [], str(e)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass

    out: list[ExportMessage] = []
    for m in items:
        text = " ".join(m.textlines).strip()
        if not text:
            continue
        when = m.time
        if when.tzinfo is None:
            when = when.replace(tzinfo=JST)
        else:
            when = when.astimezone(JST)
        out.append(
            ExportMessage(
                when=when,
                username=(m.username or "").strip() or "（名前なし）",
                text=text,
            )
        )
    return out, ""


def _parse_plain_lines(path: Path) -> list[ExportMessage]:
    """`YYYY/MM/DD HH:MM  user  text` 形式のフォールバック。"""
    out: list[ExportMessage] = []
    pat = re.compile(
        r"^([12]\d{3}/\d{2}/\d{2})\s+(\d{1,2}:\d{2})\s+(.+?)\s{2,}(.+)$"
    )
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = pat.match(line.strip())
        if not m:
            continue
        date_s, time_s, user, text = m.groups()
        try:
            when = datetime.strptime(f"{date_s} {time_s}", "%Y/%m/%d %H:%M").replace(tzinfo=JST)
        except ValueError:
            continue
        if text.strip():
            out.append(ExportMessage(when=when, username=user.strip(), text=text.strip()))
    return out


def iter_md_blocks(content: str) -> list[MdBlock]:
    marker = "## やり取り（時系列）"
    start_idx = content.find(marker)
    search_in = content[start_idx:] if start_idx >= 0 else content
    base = start_idx if start_idx >= 0 else 0

    pattern = re.compile(r"(?m)^### [12]\d{3}/\d{2}/\d{2}")
    matches = list(pattern.finditer(search_in))
    blocks: list[MdBlock] = []
    for i, m in enumerate(matches):
        block_start = base + m.start()
        block_end = base + matches[i + 1].start() if i + 1 < len(matches) else len(content)
        raw = content[block_start:block_end].rstrip()
        lines = raw.split("\n")
        heading = lines[0] if lines else ""
        parsed = RE_HEADING.match(heading.strip())
        if not parsed:
            continue
        date_part = parsed.group("date")
        org_label = parsed.group("org")
        tag = parsed.group("tag")
        summary = parsed.group("summary")
        body_lines = lines[1:]
        while body_lines and not body_lines[0].strip():
            body_lines.pop(0)
        while body_lines and body_lines[-1].strip() in ("", "---"):
            body_lines.pop()
        body = "\n".join(body_lines).strip()
        ph = is_placeholder_text(summary) or is_placeholder_text(body)
        blocks.append(
            MdBlock(
                start=block_start,
                end=block_end,
                heading=heading,
                raw=raw,
                date_part=date_part,
                org_label=org_label,
                tag=tag,
                summary=summary,
                body=body,
                is_placeholder=ph,
            )
        )
    return blocks


def _format_message_body(msg: ExportMessage) -> str:
    ts = msg.when.strftime("%Y/%m/%d %H:%M")
    return f"{ts}  {msg.username}  {msg.text}"


def _rebuild_block(block: MdBlock, msg: ExportMessage) -> str:
    body_text = _format_message_body(msg)
    tag = block.tag
    if "公式エクスポート修復" not in tag:
        tag = f"{tag}・公式エクスポート修復"
    heading = format_line_heading(
        block.date_part, block.org_label, tag, body_for_tail=msg.text
    )

    m = RE_DETAILS_BODY.search(block.raw)
    if m:
        inner = f"{m.group(1)}{body_text}\n{m.group(3)}"
        rest = block.raw[block.raw.find(m.group(0)) + len(m.group(0)) :]
        body_part = inner + rest
        lines_after_heading = body_part.split("\n", 1)
        new_raw = heading + "\n\n" + (lines_after_heading[1] if len(lines_after_heading) > 1 else body_part)
    else:
        new_raw = (
            f"{heading}\n\n<details>\n<summary>本文</summary>\n\n{body_text}\n\n</details>\n\n---"
        )
    return new_raw.strip() + "\n\n"


def _pair_by_date(
    placeholders: list[MdBlock],
    messages: list[ExportMessage],
) -> list[tuple[MdBlock, ExportMessage]]:
    """同日のプレースホルダーとエクスポートメッセージを、MD上の順（新しい順）と時刻降順で対応付け。"""
    ph_by_date: dict[str, list[MdBlock]] = {}
    for b in placeholders:
        ph_by_date.setdefault(b.date_part, []).append(b)

    msg_by_date: dict[str, list[ExportMessage]] = {}
    for m in messages:
        msg_by_date.setdefault(m.date_key, []).append(m)

    pairs: list[tuple[MdBlock, ExportMessage]] = []
    for date_key, ph_list in ph_by_date.items():
        msgs = sorted(msg_by_date.get(date_key, []), key=lambda x: x.when, reverse=True)
        if not msgs:
            continue
        for block, msg in zip(ph_list, msgs):
            pairs.append((block, msg))
    return pairs


def repair_placeholders_in_content(
    content: str,
    messages: list[ExportMessage],
    *,
    include_media: bool = False,
) -> tuple[str, RepairResult]:
    blocks = iter_md_blocks(content)
    placeholders = [b for b in blocks if b.is_placeholder]
    if not include_media:
        placeholders = [b for b in placeholders if "[本文なし" in (b.summary + b.body)]

    result = RepairResult(
        messages_total=len(messages),
        placeholders_total=len(placeholders),
        details=[],
    )
    if not placeholders or not messages:
        result.skipped_no_match = len(placeholders)
        return content, result

    pairs = _pair_by_date(placeholders, messages)
    if not pairs:
        result.skipped_no_match = len(placeholders)
        return content, result

    # 後方から置換（インデックスずれ防止）
    pairs_sorted = sorted(pairs, key=lambda p: p[0].start, reverse=True)
    new_content = content
    used_msgs: set[int] = set()
    for block, msg in pairs_sorted:
        msg_id = id(msg)
        if msg_id in used_msgs:
            continue
        used_msgs.add(msg_id)
        new_block = _rebuild_block(block, msg)
        new_content = new_content[: block.start] + new_block + new_content[block.end :].lstrip("\n")
        result.replaced += 1
        if result.details is not None:
            result.details.append(f"{block.date_part} ← {msg.when.strftime('%H:%M')}")

    result.skipped_no_match = max(0, len(placeholders) - result.replaced)
    return new_content, result


def repair_placeholders_in_file(
    md_path: Path,
    export_path: Path,
    *,
    dry_run: bool = False,
    include_media: bool = False,
) -> RepairResult:
    messages, _ = parse_export_messages(export_path)
    if not messages:
        return RepairResult(messages_total=0, placeholders_total=0, details=["メッセージ0件"])

    content = md_path.read_text(encoding="utf-8")
    new_content, result = repair_placeholders_in_content(
        content, messages, include_media=include_media
    )
    if result.replaced and not dry_run:
        bak = md_path.with_suffix(md_path.suffix + f".bak-export-repair")
        if not bak.exists():
            bak.write_text(content, encoding="utf-8")
        md_path.write_text(new_content, encoding="utf-8")
    return result
