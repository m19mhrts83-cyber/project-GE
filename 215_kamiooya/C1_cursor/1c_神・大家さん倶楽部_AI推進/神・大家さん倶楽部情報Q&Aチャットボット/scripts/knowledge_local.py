#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ローカル SQLite ミラー（Supabase 復旧までの検証・開発用）。

保存先（既定）:
  OneDrive .../神・大家さん倶楽部情報Q&Aチャットボット/state/knowledge_local.sqlite3

用途:
  - comments のブートストラップ／差分 upsert
  - knowledge_sources / knowledge_chunks の upsert
  - 横断検索（コメント＋動画チャンク）
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB = Path(
    "/Users/matsunomasaharu2/Library/CloudStorage/OneDrive-個人用/"
    "215_神・大家さん倶楽部/C1_cursor/1c_神・大家さん倶楽部_AI推進/"
    "神・大家さん倶楽部情報Q&Aチャットボット/state/knowledge_local.sqlite3"
)

SCHEMA_SQL = """
create table if not exists comments (
  id integer primary key autoincrement,
  source_type text,
  comment_id text not null unique,
  posted_at text,
  author_name text,
  author_email text,
  content text not null,
  parent_comment_id text,
  ip_address text,
  user_agent text,
  created_at text not null,
  updated_at text not null
);

create table if not exists knowledge_sources (
  id integer primary key autoincrement,
  source_key text not null unique,
  source_kind text not null default 'video',
  content_channel text not null default 'seminar_video',
  title text not null,
  video_id text,
  video_url text,
  instructor text,
  published_at text,
  origin_path text,
  meta_json text not null default '{}',
  ingest_status text not null default 'ready',
  created_at text not null,
  updated_at text not null
);

create table if not exists knowledge_chunks (
  id integer primary key autoincrement,
  source_id integer not null references knowledge_sources(id) on delete cascade,
  chunk_key text not null unique,
  start_sec integer not null default 0,
  end_sec integer,
  speaker text,
  content text not null,
  content_hash text not null,
  search_text text not null,
  created_at text not null,
  updated_at text not null
);

create index if not exists comments_content_idx on comments(content);
create index if not exists knowledge_chunks_search_idx on knowledge_chunks(search_text);
create index if not exists knowledge_chunks_source_idx on knowledge_chunks(source_id, start_sec);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def resolve_db_path(path: str | Path | None = None) -> Path:
    if path:
        return Path(path).expanduser().resolve()
    env = (os.environ.get("KNOWLEDGE_LOCAL_DB") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return DEFAULT_DB


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    db_path = resolve_db_path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    conn.executescript(SCHEMA_SQL)
    # existing DBs: add content_channel if missing
    cols = {r[1] for r in conn.execute("pragma table_info(knowledge_sources)").fetchall()}
    if "content_channel" not in cols:
        conn.execute(
            "alter table knowledge_sources add column content_channel text not null default 'seminar_video'"
        )
        conn.commit()
    return conn


def content_hash(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:16]


def make_chunk_key(video_id: str, start_sec: int, text: str) -> str:
    return f"wv:{video_id}:{int(start_sec)}:{content_hash(text)}"


def upsert_comments(conn: sqlite3.Connection, records: list[dict[str, Any]]) -> int:
    n = 0
    ts = now_iso()
    for r in records:
        cid = str(r.get("comment_id") or "").strip()
        content = str(r.get("content") or "").strip()
        if not cid or not content:
            continue
        conn.execute(
            """
            insert into comments (
              source_type, comment_id, posted_at, author_name, author_email,
              content, parent_comment_id, ip_address, user_agent, created_at, updated_at
            ) values (?,?,?,?,?,?,?,?,?,?,?)
            on conflict(comment_id) do update set
              source_type=excluded.source_type,
              posted_at=excluded.posted_at,
              author_name=excluded.author_name,
              author_email=excluded.author_email,
              content=excluded.content,
              parent_comment_id=excluded.parent_comment_id,
              ip_address=excluded.ip_address,
              user_agent=excluded.user_agent,
              updated_at=excluded.updated_at
            """,
            (
                r.get("source_type") or "WeStudy",
                cid,
                r.get("posted_at"),
                r.get("author_name"),
                r.get("author_email"),
                content,
                r.get("parent_comment_id"),
                r.get("ip_address"),
                r.get("user_agent"),
                ts,
                ts,
            ),
        )
        n += 1
    conn.commit()
    return n


def upsert_source(
    conn: sqlite3.Connection,
    *,
    source_key: str,
    title: str,
    video_id: str | None = None,
    video_url: str | None = None,
    instructor: str | None = None,
    published_at: str | None = None,
    origin_path: str | None = None,
    meta: dict | None = None,
    content_channel: str = "seminar_video",
) -> int:
    ts = now_iso()
    meta_json = json.dumps(meta or {}, ensure_ascii=False)
    channel = content_channel or "seminar_video"
    conn.execute(
        """
        insert into knowledge_sources (
          source_key, source_kind, content_channel, title, video_id, video_url, instructor,
          published_at, origin_path, meta_json, ingest_status, created_at, updated_at
        ) values (?,?,?,?,?,?,?,?,?,?,'ready',?,?)
        on conflict(source_key) do update set
          content_channel=excluded.content_channel,
          title=excluded.title,
          video_id=excluded.video_id,
          video_url=excluded.video_url,
          instructor=excluded.instructor,
          published_at=excluded.published_at,
          origin_path=excluded.origin_path,
          meta_json=excluded.meta_json,
          updated_at=excluded.updated_at
        """,
        (
            source_key,
            "video",
            channel,
            title,
            video_id,
            video_url,
            instructor,
            published_at,
            origin_path,
            meta_json,
            ts,
            ts,
        ),
    )
    row = conn.execute(
        "select id from knowledge_sources where source_key = ?", (source_key,)
    ).fetchone()
    conn.commit()
    return int(row["id"])


def upsert_chunks(
    conn: sqlite3.Connection,
    source_id: int,
    chunks: list[dict[str, Any]],
) -> int:
    ts = now_iso()
    n = 0
    for c in chunks:
        text = str(c.get("content") or "").strip()
        if not text:
            continue
        start_sec = int(c.get("start_sec") or 0)
        end_sec = c.get("end_sec")
        end_sec = int(end_sec) if end_sec is not None else None
        speaker = (c.get("speaker") or None)
        video_id = str(c.get("video_id") or source_id)
        ch = content_hash(text)
        chunk_key = str(c.get("chunk_key") or make_chunk_key(video_id, start_sec, text))
        search_text = f"{speaker or ''} {text}".strip()
        conn.execute(
            """
            insert into knowledge_chunks (
              source_id, chunk_key, start_sec, end_sec, speaker, content,
              content_hash, search_text, created_at, updated_at
            ) values (?,?,?,?,?,?,?,?,?,?)
            on conflict(chunk_key) do update set
              source_id=excluded.source_id,
              start_sec=excluded.start_sec,
              end_sec=excluded.end_sec,
              speaker=excluded.speaker,
              content=excluded.content,
              content_hash=excluded.content_hash,
              search_text=excluded.search_text,
              updated_at=excluded.updated_at
            """,
            (
                source_id,
                chunk_key,
                start_sec,
                end_sec,
                speaker,
                text,
                ch,
                search_text,
                ts,
                ts,
            ),
        )
        n += 1
    conn.commit()
    return n


_TOKEN_RE = re.compile(r"[0-9A-Za-zぁ-んァ-ン一-龥]{2,}")


def tokenize(q: str) -> list[str]:
    stop = {"です", "ます", "こと", "方法", "教えて", "ください", "どこ", "なに", "何", "について"}
    toks = []
    for t in _TOKEN_RE.findall(q or ""):
        if t in stop:
            continue
        if t not in toks:
            toks.append(t)
    return toks[:8]


def format_mmss(sec: int | None) -> str:
    if sec is None:
        return ""
    s = max(0, int(sec))
    h, rem = divmod(s, 3600)
    m, ss = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{ss:02d}"
    return f"{m:02d}:{ss:02d}"


def search_all(conn: sqlite3.Connection, query: str, limit: int = 10) -> list[dict[str, Any]]:
    tokens = tokenize(query)
    if not tokens:
        tokens = [(query or "").strip()[:12]] if (query or "").strip() else []
    if not tokens:
        return []

    hits: list[dict[str, Any]] = []

    # comments
    where = " and ".join(["content like ?" for _ in tokens])
    params = [f"%{t}%" for t in tokens]
    rows = conn.execute(
        f"select * from comments where {where} order by posted_at desc nulls last limit ?",
        (*params, limit),
    ).fetchall()
    for r in rows:
        st = r["source_type"] or "WeStudy"
        if st in ("WeStudy", "westudy", ""):
            st = "WeStudyコミュニティ"
        hits.append(
            {
                "kind": "comment",
                "source_type": st,
                "comment_id": r["comment_id"],
                "posted_at": r["posted_at"],
                "author_name": r["author_name"],
                "content": r["content"],
                "snippet": (r["content"] or "")[:220],
                "score": sum(1 for t in tokens if t.lower() in (r["content"] or "").lower()),
            }
        )

    # chunks + sources
    where2 = " and ".join(["c.search_text like ?" for _ in tokens])
    rows2 = conn.execute(
        f"""
        select c.*, s.title as video_title, s.video_url, s.video_id as src_video_id,
               s.source_key, s.content_channel, s.origin_path
        from knowledge_chunks c
        join knowledge_sources s on s.id = c.source_id
        where {where2}
        order by c.start_sec asc
        limit ?
        """,
        (*params, limit),
    ).fetchall()
    for r in rows2:
        start = int(r["start_sec"] or 0)
        url = r["video_url"] or ""
        if url and "t=" not in url:
            # hash fragments (#LF) を保ったまま t= を付ける
            hash_idx = url.find("#")
            base = url[:hash_idx] if hash_idx >= 0 else url
            hash_part = url[hash_idx:] if hash_idx >= 0 else ""
            sep = "&" if "?" in base else "?"
            url = f"{base}{sep}t={start}{hash_part}"
        channel = (r["content_channel"] if "content_channel" in r.keys() else None) or "seminar_video"
        label = "WeStudyセミナー動画" if channel == "seminar_video" else "WeStudyコミュニティ"
        hits.append(
            {
                "kind": "video_chunk",
                "source_type": label,
                "chunk_key": r["chunk_key"],
                "video_title": r["video_title"],
                "video_id": r["src_video_id"] or r["source_key"],
                "video_url": url or None,
                "origin_path": r["origin_path"] if "origin_path" in r.keys() else None,
                "start_sec": start,
                "end_sec": r["end_sec"],
                "start_label": format_mmss(start),
                "speaker": r["speaker"],
                "content": r["content"],
                "snippet": (r["content"] or "")[:220],
                "score": sum(1 for t in tokens if t.lower() in (r["search_text"] or "").lower())
                + 1,
            }
        )

    hits.sort(key=lambda x: (-int(x.get("score") or 0), x.get("kind") != "video_chunk"))
    return hits[:limit]


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        "comments": conn.execute("select count(*) from comments").fetchone()[0],
        "knowledge_sources": conn.execute("select count(*) from knowledge_sources").fetchone()[0],
        "knowledge_chunks": conn.execute("select count(*) from knowledge_chunks").fetchone()[0],
    }


if __name__ == "__main__":
    c = connect()
    print("db:", resolve_db_path())
    print("counts:", counts(c))
