#!/usr/bin/env python3
"""
815 オープンチャット 5.やり取り.md の見出しを旧形式から A+B 形式へ一括変換する。

旧: ### 日付｜グループ｜LINEオープンチャット・メイン・受信｜要約
新: ### 日付｜【メイン】｜グループ｜受信｜要約
    ### 日付｜【スレッド】｜グループ｜「タイトル」｜受信｜要約
    ### 日付｜【スレッド返信】｜グループ｜受信｜要約

--infer-thread-titles: API 未取得時、各スレッドの最古メッセージ要約をタイトル候補にする。
--refresh-titles: 既に新形式の【スレッド】見出しのタイトル部分だけ差し替える。
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

from chrline_open_chat_to_md import (
    Route,
    _append_thread_titles_to_routes_yaml,
    _is_placeholder_thread_label,
    _parse_routes,
)

OLD = "LINEオープンチャット"

RE_NEW = re.compile(r"^### [^｜]+｜【(?:メイン|スレッド返信|スレッド)】")

RE_NEW_THREAD = re.compile(
    r"^### (?P<date>[^｜]+)｜【スレッド】｜(?P<org>[^｜]+)｜「(?P<thread>[^」]+)」｜(?P<dir>受信|送信)｜(?P<summary>.*)$"
)

RE_THREAD_REPLY = re.compile(
    rf"^### (?P<date>[^｜]+)｜(?P<org>[^｜]+)｜{OLD}・スレッド「(?P<thread>[^」]+)」・スレッド返信・(?P<dir>受信|送信)｜(?P<summary>.*)$"
)
RE_MAIN_REPLY = re.compile(
    rf"^### (?P<date>[^｜]+)｜(?P<org>[^｜]+)｜{OLD}・メイン・スレッド返信・(?P<dir>受信|送信)｜(?P<summary>.*)$"
)
RE_THREAD = re.compile(
    rf"^### (?P<date>[^｜]+)｜(?P<org>[^｜]+)｜{OLD}・スレッド「(?P<thread>[^」]+)」・(?P<dir>受信|送信)｜(?P<summary>.*)$"
)
RE_MAIN = re.compile(
    rf"^### (?P<date>[^｜]+)｜(?P<org>[^｜]+)｜{OLD}・メイン・(?P<dir>受信|送信)｜(?P<summary>.*)$"
)

MAX_INFER_TITLE_LEN = 48


def _load_thread_titles(routes: list[Route]) -> dict[str, str]:
    out: dict[str, str] = {}
    for route in routes:
        out.update(route.thread_titles)
    return out


def _build_prefix_to_mid(routes: list[Route]) -> dict[str, str]:
    out: dict[str, str] = {}
    for route in routes:
        for tmid in route.thread_mids:
            if len(tmid) >= 8:
                out.setdefault(tmid[:8], tmid)
    return out


def _is_thread_mid(s: str) -> bool:
    return len(s) >= 24 and s[:1] == "t"


def _normalize_thread_key(raw: str, prefix_to_mid: dict[str, str]) -> str:
    raw = raw.strip()
    if _is_thread_mid(raw):
        return raw
    if raw.endswith("…"):
        prefix = raw[:-1]
        if prefix in prefix_to_mid:
            return prefix_to_mid[prefix]
    if raw in prefix_to_mid:
        return prefix_to_mid[raw]
    return raw


def _truncate_title(summary: str) -> str:
    s = re.sub(r"\s+", " ", (summary or "").strip())
    if not s or s.startswith("[非テキスト"):
        return ""
    if len(s) <= MAX_INFER_TITLE_LEN:
        return s
    return s[: MAX_INFER_TITLE_LEN - 1] + "…"


def infer_thread_titles_from_md(
    path: Path,
    route: Route,
    prefix_to_mid: dict[str, str],
) -> dict[str, str]:
    """各スレッドの最古【スレッド】見出し要約をタイトル候補にする。"""
    earliest: dict[str, tuple[str, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = RE_NEW_THREAD.match(line)
        if not m:
            continue
        g = m.groupdict()
        mid = _normalize_thread_key(g["thread"], prefix_to_mid)
        if not _is_thread_mid(mid):
            continue
        date_part = g["date"]
        summary = g["summary"]
        prev = earliest.get(mid)
        if prev is None or date_part < prev[0]:
            title = _truncate_title(summary)
            if title:
                earliest[mid] = (date_part, title)

    out: dict[str, str] = {}
    for mid, (_, title) in earliest.items():
        existing = route.thread_titles.get(mid, "")
        if existing and not _is_placeholder_thread_label(existing, mid):
            continue
        out[mid] = title
    return out


def _display_thread_title(raw: str, titles: dict[str, str], prefix_to_mid: dict[str, str]) -> str:
    raw = raw.strip()
    mid = _normalize_thread_key(raw, prefix_to_mid)
    if mid in titles and titles[mid].strip():
        return titles[mid].strip()
    if raw in titles and titles[raw].strip():
        return titles[raw].strip()
    if _is_thread_mid(raw):
        return f"{raw[:8]}…" if len(raw) > 8 else raw
    if _is_thread_mid(mid):
        return f"{mid[:8]}…" if len(mid) > 8 else mid
    return raw


def convert_line(
    line: str,
    titles: dict[str, str],
    prefix_to_mid: dict[str, str],
    *,
    refresh_titles: bool,
) -> tuple[str, str | None]:
    """戻り値: (新行, 変換種別 or None)。"""
    if not line.startswith("### "):
        return line, None

    m = RE_NEW_THREAD.match(line)
    if m and refresh_titles:
        g = m.groupdict()
        raw = g["thread"]
        mid = _normalize_thread_key(raw, prefix_to_mid)
        new_title = _display_thread_title(raw, titles, prefix_to_mid)
        if new_title == raw:
            return line, None
        if _is_placeholder_thread_label(raw, mid) and _is_placeholder_thread_label(new_title, mid):
            return line, None
        return (
            f"### {g['date']}｜【スレッド】｜{g['org']}｜「{new_title}」｜{g['dir']}｜{g['summary']}",
            "thread_title_refresh",
        )

    if RE_NEW.match(line):
        return line, None

    m = RE_THREAD_REPLY.match(line)
    if m:
        g = m.groupdict()
        return (
            f"### {g['date']}｜【スレッド返信】｜{g['org']}｜{g['dir']}｜{g['summary']}",
            "thread_reply",
        )

    m = RE_MAIN_REPLY.match(line)
    if m:
        g = m.groupdict()
        return (
            f"### {g['date']}｜【スレッド返信】｜{g['org']}｜{g['dir']}｜{g['summary']}",
            "main_reply",
        )

    m = RE_THREAD.match(line)
    if m:
        g = m.groupdict()
        title = _display_thread_title(g["thread"], titles, prefix_to_mid)
        return (
            f"### {g['date']}｜【スレッド】｜{g['org']}｜「{title}」｜{g['dir']}｜{g['summary']}",
            "thread",
        )

    m = RE_MAIN.match(line)
    if m:
        g = m.groupdict()
        return (
            f"### {g['date']}｜【メイン】｜{g['org']}｜{g['dir']}｜{g['summary']}",
            "main",
        )

    return line, None


def migrate_file(
    path: Path,
    titles: dict[str, str],
    prefix_to_mid: dict[str, str],
    *,
    dry_run: bool,
    refresh_titles: bool,
) -> dict[str, int]:
    text = path.read_text(encoding="utf-8")
    counts: dict[str, int] = {}
    out_lines: list[str] = []
    for line in text.splitlines(keepends=True):
        bare = line.rstrip("\n\r")
        newline, kind = convert_line(
            bare, titles, prefix_to_mid, refresh_titles=refresh_titles
        )
        if kind:
            counts[kind] = counts.get(kind, 0) + 1
            suffix = line[len(bare) :] if len(line) > len(bare) else "\n"
            out_lines.append(newline + suffix)
        else:
            out_lines.append(line)
    if counts and not dry_run:
        path.write_text("".join(out_lines), encoding="utf-8")
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="オープンチャット見出しの一括変換（旧→A+B）")
    parser.add_argument("--routes-yaml", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--infer-thread-titles",
        action="store_true",
        help="各スレッド最古メッセージ要約から thread_titles 候補を生成（API 代替）",
    )
    parser.add_argument(
        "--write-yaml-titles",
        action="store_true",
        help="推定・既存タイトルを open_chat_routes.yaml に書き込む",
    )
    parser.add_argument(
        "--refresh-titles",
        action="store_true",
        help="既存の【スレッド】見出しのタイトル部分を thread_titles で差し替え",
    )
    args = parser.parse_args(argv)

    routes_yaml = args.routes_yaml
    if routes_yaml is None:
        routes_yaml = (Path(__file__).resolve().parent / "open_chat_routes.yaml").resolve()
    routes = _parse_routes(routes_yaml)
    titles = _load_thread_titles(routes)
    prefix_to_mid = _build_prefix_to_mid(routes)

    refresh_titles = bool(args.refresh_titles or args.infer_thread_titles)

    route_id_to_new: dict[str, dict[str, str]] = defaultdict(dict)
    if args.infer_thread_titles:
        for route in routes:
            path = route.output_md
            if not path.is_file():
                continue
            inferred = infer_thread_titles_from_md(path, route, prefix_to_mid)
            if inferred:
                route_id_to_new[route.rid].update(inferred)
                titles.update(inferred)
                print(
                    f"# 推定タイトル [{route.rid}]: {len(inferred)} 件",
                    file=sys.stderr,
                )

    if route_id_to_new and args.write_yaml_titles and not args.dry_run:
        added = _append_thread_titles_to_routes_yaml(routes_yaml, dict(route_id_to_new))
        print(f"# open_chat_routes.yaml thread_titles 追記: {added} 件", file=sys.stderr)
    elif route_id_to_new and args.dry_run:
        n = sum(len(v) for v in route_id_to_new.values())
        print(f"# [dry-run] thread_titles を {n} 件追記する予定", file=sys.stderr)

    total: dict[str, int] = {}
    files_changed = 0
    for route in routes:
        path = route.output_md
        if not path.is_file():
            print(f"# スキップ（ファイルなし）: {path}", file=sys.stderr)
            continue
        c = migrate_file(
            path,
            titles,
            prefix_to_mid,
            dry_run=bool(args.dry_run),
            refresh_titles=refresh_titles,
        )
        if c:
            files_changed += 1
            for k, n in c.items():
                total[k] = total.get(k, 0) + n
            print(f"# {path.name} [{route.rid}]: {c}", file=sys.stderr)

    print(
        f"# 変換{'予定' if args.dry_run else '完了'}: ファイル {files_changed} 件 / {total}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
