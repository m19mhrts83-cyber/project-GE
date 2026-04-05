#!/usr/bin/env python3
"""
CHRLINE sync の差分と getRecentMessagesV2 補完から、指定した 1:1 またはグループ（chat mid 部分一致）の
メッセージを 215 のパートナー用 5.やり取り.md に追記する。

運用方針（2026-04〜）: **業務連絡はグループトークに集約**し、CHRLINE 取得も **グループを主**とする。
個人 1:1 はレガシー用プリセットのみ。

既定プリセット「line-default」（推奨）:
  - **1回の sync** で次をまとめて処理（別プロセスに分けると取りこぼす）:
    - Tcell: グループ「キャラメル管理G」のみ → 103_Tcell/5.やり取り.md
    - LEAF: グループ名に「Grandole志賀本通」を含むトーク → 104_LEAF/5.やり取り.md
  - グループ chatMid はトーク名の部分一致で解決、または LINE_TCELL_GROUP_CHAT_MID / LINE_LEAF_GROUP_CHAT_MID / 各 --*-group-chat-mid

プリセット「tcell-both」: Tcell のみ・**キャラメル管理G グループのみ**（旧「yuki+G」から変更）
プリセット「tcell-yuki」: Tcell **1:1 のみ**（yuki 相当。非推奨・過去互換）
プリセット「leaf-grandole」: LEAF のみ（上記 Grandole グループ）

状態・重複:
  - sync リビジョンは chrline_sync_delta_poc と同じ .chrline_sync_delta_state.json
  - 追記済みは LINE_UNOFFICIAL_AUTH_DIR の .chrline_sync_yoritoori_dedup.json（message id + 時刻）
  - グループは sync の Operation に乗らない／E2EE で本文がプレースホルダになり sync から落ちることがあるため、
    各ターゲットに対し getRecentMessagesV2 による直近補完（--direct-backfill-count、既定 120）を毎回実施する。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

from CHRLINE.services.thrift.ttypes import OpType

from chrline_client_utils import build_logged_in_client, save_root_from_env
from chrline_md_utils import (
    insert_block_after_timeline_header as md_insert_block_after_timeline_header,
    make_summary as md_make_summary,
    wrap_details as md_wrap_details,
)
from chrline_sync_delta_poc import (
    STATE_FILENAME,
    _MESSAGE_OP_TYPES,
    _chat_hint_from_op,
    _format_line_msg_when,
    _looks_like_line_chat_mid,
    _msg_body_line_with_e2ee_register,
    _msg_sender_mid,
    _msg_time,
    _op_revision,
    _op_type_name,
    _run_sync,
    _load_state,
    _save_state,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ONEDRIVE_TCELL_YORITOORI = (
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C2_ルーティン作業/26_パートナー社への相談/103_Tcell/5.やり取り.md"
)
_REPO_TCELL_YORITOORI = (
    _REPO_ROOT
    / "215_kamiooya"
    / "C2_ルーティン作業"
    / "26_パートナー社への相談"
    / "103_Tcell"
    / "5.やり取り.md"
)
_ONEDRIVE_LEAF_YORITOORI = (
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C2_ルーティン作業/26_パートナー社への相談/104_LEAF/5.やり取り.md"
)
_REPO_LEAF_YORITOORI = (
    _REPO_ROOT
    / "215_kamiooya"
    / "C2_ルーティン作業"
    / "26_パートナー社への相談"
    / "104_LEAF"
    / "5.やり取り.md"
)


def _default_tcell_yoritoori_path() -> Path:
    """実際に編集している 5.やり取り.md（OneDrive 優先）。"""
    env = (os.environ.get("LINE_TCELL_YORITOORI_MD") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    if _ONEDRIVE_TCELL_YORITOORI.is_file():
        return _ONEDRIVE_TCELL_YORITOORI.resolve()
    return _REPO_TCELL_YORITOORI.resolve()


def _default_leaf_yoritoori_path() -> Path:
    """104_LEAF の 5.やり取り.md（OneDrive 優先）。"""
    env = (os.environ.get("LINE_LEAF_YORITOORI_MD") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    if _ONEDRIVE_LEAF_YORITOORI.is_file():
        return _ONEDRIVE_LEAF_YORITOORI.resolve()
    return _REPO_LEAF_YORITOORI.resolve()


_YUKI_CHAT_NEEDLE_DEFAULT = "uc2410d38412ff86926c56af265f2a577"
_DEFAULT_GROUP_TITLE = "キャラメル管理G"
# 一覧の表示例: 「Grandole志賀本通 I    管理」（スペースの数・半角全角は環境で異なることがある）
_LEAF_GROUP_TITLE_DEFAULT = "Grandole志賀本通"
_LEAF_GROUP_PEER_LABEL_DEFAULT = "Grandole志賀本通 I 管理"

DEDUP_FILENAME = ".chrline_sync_yoritoori_dedup.json"
DECODE_STATS_FILENAME = ".chrline_sync_decode_stats.jsonl"
RETRY_QUEUE_FILENAME = ".chrline_sync_retry_queue.json"
LOCK_FILENAME = ".chrline_sync_to_yoritoori.lock"
TIMELINE_MARKER = "## やり取り（時系列）"
_PLACEHOLDER_PREFIX = "[本文なし"


def _make_summary(body: str, max_len: int = 50) -> str:
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


def _flatten_notion_headings(body: str) -> str:
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


def _wrap_details(body: str) -> str:
    flat = _flatten_notion_headings(body)
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


def _dedup_path(save_root: Path) -> Path:
    return save_root / DEDUP_FILENAME


def _load_dedup(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        keys = data.get("keys")
        if isinstance(keys, list):
            return {str(x) for x in keys if x}
    except (json.JSONDecodeError, OSError):
        pass
    return set()


def _save_dedup(path: Path, keys: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    trimmed = sorted(keys)[-3000:]
    path.write_text(
        json.dumps({"keys": trimmed}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@dataclass(frozen=True)
class _YoritooriTarget:
    needle: str
    recv_tag: str
    send_tag: str


@dataclass
class _YoritooriRoute:
    yoritoori_md: Path
    org_label: str
    targets: list[_YoritooriTarget]

@dataclass
class _PendingSyncPlaceholder:
    route: _YoritooriRoute
    target: _YoritooriTarget
    ts: int
    date_part: str
    body_raw: str
    dk: str
    tag: str


def _lock_path(save_root: Path) -> Path:
    return save_root / LOCK_FILENAME


def _retry_queue_path(save_root: Path) -> Path:
    return save_root / RETRY_QUEUE_FILENAME


def _acquire_lock(lock_path: Path, stale_sec: int) -> bool:
    now = int(time.time())
    payload = {"pid": os.getpid(), "ts": now}
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            data = json.loads(lock_path.read_text(encoding="utf-8"))
            ts = int(data.get("ts", 0))
        except Exception:
            ts = 0
        if stale_sec > 0 and ts > 0 and now - ts >= stale_sec:
            try:
                lock_path.unlink()
            except OSError:
                return False
            return _acquire_lock(lock_path, stale_sec)
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    return True


def _release_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except OSError:
        pass


def _load_retry_queue(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data.get("items", {})
        if isinstance(items, dict):
            return {str(k): v for k, v in items.items() if isinstance(v, dict)}
    except Exception:
        pass
    return {}


def _save_retry_queue(path: Path, items: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"items": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _decode_stats_path(save_root: Path) -> Path:
    return save_root / DECODE_STATS_FILENAME


def _is_textual_body(body: str) -> bool:
    b = (body or "").strip()
    if not b:
        return False
    if b.startswith(_PLACEHOLDER_PREFIX):
        return False
    if b in ("[メディア]", "[スタンプ]"):
        return False
    return True


def _is_placeholder_body(body: str) -> bool:
    return (body or "").lstrip().startswith(_PLACEHOLDER_PREFIX)


def _stats_key(route: _YoritooriRoute, target: _YoritooriTarget) -> str:
    return f"{route.org_label}|{target.needle}|{target.recv_tag}"


def _touch_stats_bucket(
    stats: dict[str, dict],
    route: _YoritooriRoute,
    target: _YoritooriTarget,
) -> dict:
    key = _stats_key(route, target)
    if key in stats:
        return stats[key]
    bucket = {
        "org_label": route.org_label,
        "yoritoori_md": str(route.yoritoori_md),
        "target_mid": target.needle,
        "target_label": target.recv_tag,
        "is_personal_u_mid": target.needle.startswith("u"),
        "seen": 0,
        "textual": 0,
        "media_or_stamp": 0,
        "placeholder": 0,
        "written": 0,
        "dedup_skipped": 0,
        "source_sync": 0,
        "source_direct_backfill": 0,
    }
    stats[key] = bucket
    return bucket


def _observe_decode_stats(
    stats: dict[str, dict],
    route: _YoritooriRoute,
    target: _YoritooriTarget,
    body_raw: str,
    *,
    source: str,
    wrote: bool = False,
    dedup_skipped: bool = False,
) -> None:
    b = _touch_stats_bucket(stats, route, target)
    b["seen"] += 1
    if source == "sync":
        b["source_sync"] += 1
    elif source == "direct_backfill":
        b["source_direct_backfill"] += 1
    if body_raw.startswith(_PLACEHOLDER_PREFIX):
        b["placeholder"] += 1
    elif body_raw in ("[メディア]", "[スタンプ]"):
        b["media_or_stamp"] += 1
    elif _is_textual_body(body_raw):
        b["textual"] += 1
    if wrote:
        b["written"] += 1
    if dedup_skipped:
        b["dedup_skipped"] += 1


def _append_decode_stats_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _resolve_group_mid_by_title(cl, title_sub: str) -> str | None:
    """getChats 一覧から、チャット名に title_sub を含むグループの chatMid を返す。"""
    from chrline_list_chats_poc import (
        _chat_mid_from,
        _chat_name,
        _iter_group_mids,
    )

    mids = _iter_group_mids(cl)
    if not mids:
        return None
    batch = 30
    title_sub = (title_sub or "").strip()
    if not title_sub:
        return None
    for i in range(0, len(mids), batch):
        chunk = mids[i : i + batch]
        try:
            res = cl.getChats(chunk)
        except Exception:
            return None
        chats = cl.checkAndGetValue(res, "chats", 1)
        if chats is None and isinstance(res, dict):
            chats = res.get(1) or res.get("chats")
        if not chats:
            continue
        if not isinstance(chats, (list, tuple)):
            chats = [chats]
        for j, c in enumerate(chats):
            fb = chunk[j] if j < len(chunk) else None
            mid = _chat_mid_from(cl, c, fb)
            if not mid:
                continue
            name = _chat_name(cl, c)
            if title_sub in name:
                return mid
    return None


def _group_fetch_mid_from_targets(matched: list[tuple[_YoritooriRoute, _YoritooriTarget]]) -> str | None:
    """直近取得・sync いずれも、グループ c mid を本文復号用に渡す。"""
    for _, tmeta in matched:
        n = (tmeta.needle or "").strip()
        if n.startswith("c") and _looks_like_line_chat_mid(n):
            return n
    return None


def _pick_target(chat: str, targets: list[_YoritooriTarget]) -> _YoritooriTarget | None:
    cl = chat.lower()
    for t in targets:
        if t.needle.lower() in cl:
            return t
    return None


def _message_dedup_key(cl, msg) -> str | None:
    mid = cl.checkAndGetValue(msg, "id", 4)
    if mid is None and isinstance(msg, dict):
        mid = msg.get(4) or msg.get("id")
    ts = _msg_time(cl, msg)
    if mid:
        return f"id:{mid}|ts:{ts}"
    if ts:
        return f"nts:{ts}"
    return None


def _enqueue_retry(
    queue_items: dict[str, dict],
    *,
    dk: str,
    route: _YoritooriRoute,
    target: _YoritooriTarget,
    tag: str,
    date_part: str,
    ts: int,
    body_raw: str,
    now_ts: int,
    retry_interval_sec: int,
) -> None:
    cur = queue_items.get(dk) or {}
    attempts = int(cur.get("attempts", 0))
    queue_items[dk] = {
        "dk": dk,
        "route_path": str(route.yoritoori_md),
        "org_label": route.org_label,
        "target_mid": target.needle,
        "target_label": target.recv_tag,
        "tag": tag,
        "date_part": date_part,
        "ts": int(ts),
        "body_raw": body_raw,
        "attempts": attempts,
        "next_retry_ts": now_ts + max(10, retry_interval_sec),
    }


def _messages_from_response(cl, res) -> list:
    """getRecentMessagesV2/getPreviousMessagesV2 応答から Message 配列を取り出す。"""
    if res is None:
        return []
    if isinstance(res, (list, tuple)):
        return list(res)
    for fid in range(1, 20):
        m = cl.checkAndGetValue(res, "messages", fid)
        if isinstance(m, (list, tuple)):
            return list(m)
    if isinstance(res, dict):
        for v in res.values():
            if isinstance(v, (list, tuple)):
                return list(v)
    if hasattr(res, "dd"):
        try:
            dd = res.dd()
            for v in dd.values():
                if isinstance(v, (list, tuple)):
                    return list(v)
        except Exception:
            pass
    return []


def _latest_heading_date_ts_ms(path: Path) -> int | None:
    """やり取り見出しの最新日付（00:00）をミリ秒で返す。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    dates = re.findall(r"^### ([12]\d{3}/\d{2}/\d{2})", text, flags=re.MULTILINE)
    if not dates:
        return None
    latest = max(dates)
    try:
        dt = datetime.strptime(latest, "%Y/%m/%d")
    except ValueError:
        return None
    return int(dt.timestamp() * 1000)


def _append_direct_backfill_from_recent(
    cl,
    *,
    route: _YoritooriRoute,
    target: _YoritooriTarget,
    receive_only: bool,
    count: int,
    seen_keys: set[str],
    new_keys: set[str],
    skip_e2ee_key_register: bool,
    dry_run: bool,
    verbose: bool,
    decode_stats: dict[str, dict] | None = None,
    retry_queue_items: dict[str, dict] | None = None,
    retry_interval_sec: int = 300,
) -> int:
    """
    sync 差分に載らない・または本文プレースホルダで sync から落ちた分の補完。
    getRecentMessagesV2 で 1:1(u*)・グループ(c* 等)の直近を取得し、
    やり取り.md の最新見出し日付より後の分だけ追記する（重複は dedup）。
    """
    if count <= 0:
        return 0
    my_mid = (getattr(cl, "mid", None) or "").strip()
    since_day = _latest_heading_date_ts_ms(route.yoritoori_md)
    since_ts = (since_day + 24 * 60 * 60 * 1000) if since_day else None
    try:
        res = cl.getRecentMessagesV2(target.needle, max(1, min(count, 300)))
    except Exception as e:
        if verbose:
            print(f"# 直近取得スキップ: getRecentMessagesV2 失敗 {e}", file=sys.stderr)
        return 0
    msgs = _messages_from_response(cl, res)
    if not msgs:
        return 0
    msgs.sort(key=lambda m: _msg_time(cl, m))
    e2ee_registered: set[str] = set()
    appended = 0
    for msg in msgs:
        ts = _msg_time(cl, msg)
        if since_ts is not None and ts and ts < since_ts:
            continue
        sender = (_msg_sender_mid(cl, msg) or "").strip()
        is_send = bool(my_mid and sender and sender == my_mid)
        if receive_only and is_send:
            continue
        fetch_mid = None
        n = (target.needle or "").strip()
        if n.startswith("c") and _looks_like_line_chat_mid(n):
            fetch_mid = n
        body_raw = _msg_body_line_with_e2ee_register(
            cl,
            msg,
            None,
            e2ee_registered,
            skip_register=skip_e2ee_key_register,
            fetch_chat_mid=fetch_mid,
        )
        # 空本文のみは捨てる。プレースホルダは再照会キューへ。
        if not body_raw.strip():
            continue
        dk = _message_dedup_key(cl, msg)
        if retry_queue_items is not None and dk and _is_placeholder_body(body_raw):
            when = _format_line_msg_when(ts)
            date_part = when.split()[0] if when and " " in when else when or "?"
            _enqueue_retry(
                retry_queue_items,
                dk=dk,
                route=route,
                target=target,
                tag=(target.send_tag if is_send else target.recv_tag),
                date_part=date_part,
                ts=ts,
                body_raw=body_raw,
                now_ts=int(time.time()),
                retry_interval_sec=retry_interval_sec,
            )
            if decode_stats is not None:
                _observe_decode_stats(
                    decode_stats,
                    route,
                    target,
                    body_raw,
                    source="direct_backfill",
                )
            continue
        if dk and dk in seen_keys:
            if decode_stats is not None:
                _observe_decode_stats(
                    decode_stats,
                    route,
                    target,
                    body_raw,
                    source="direct_backfill",
                    dedup_skipped=True,
                )
            continue
        when = _format_line_msg_when(ts)
        date_part = when.split()[0] if when and " " in when else when or "?"
        summary = md_make_summary(body_raw)
        tag = target.send_tag if is_send else target.recv_tag
        heading = f"### {date_part}｜{route.org_label}｜{tag}｜{summary}"
        block = f"""

{heading}

{md_wrap_details(body_raw)}

---
"""
        if dry_run:
            print(
                f"[dry-run][直近補完] 追記予定 → {route.yoritoori_md.name}:\n{heading}\n{body_raw[:200]!r}…\n"
            )
        else:
            content = route.yoritoori_md.read_text(encoding="utf-8")
            route.yoritoori_md.write_text(
                md_insert_block_after_timeline_header(content, block),
                encoding="utf-8",
            )
            if dk:
                seen_keys.add(dk)
                new_keys.add(dk)
        if decode_stats is not None:
            _observe_decode_stats(
                decode_stats,
                route,
                target,
                body_raw,
                source="direct_backfill",
                wrote=True,
            )
        appended += 1
    return appended


def _process_retry_queue(
    cl,
    *,
    queue_items: dict[str, dict],
    route_target_map: dict[tuple[str, str], tuple[_YoritooriRoute, _YoritooriTarget]],
    seen_keys: set[str],
    new_keys: set[str],
    dry_run: bool,
    skip_e2ee_key_register: bool,
    retry_fetch_count: int,
    retry_interval_sec: int,
    retry_max_attempts: int,
    verbose: bool,
) -> int:
    if not queue_items:
        return 0
    now_ts = int(time.time())
    appended = 0
    done_keys: list[str] = []

    for dk, item in list(queue_items.items()):
        if dk in seen_keys:
            done_keys.append(dk)
            continue
        if int(item.get("next_retry_ts", 0)) > now_ts:
            continue
        route_path = str(item.get("route_path", ""))
        target_mid = str(item.get("target_mid", ""))
        rt = route_target_map.get((route_path, target_mid))
        attempts = int(item.get("attempts", 0))
        if rt is None:
            attempts += 1
            item["attempts"] = attempts
            item["next_retry_ts"] = now_ts + retry_interval_sec
            if attempts >= retry_max_attempts:
                done_keys.append(dk)
            continue

        route, target = rt
        try:
            res = cl.getRecentMessagesV2(target_mid, max(1, min(retry_fetch_count, 300)))
            msgs = _messages_from_response(cl, res)
        except Exception:
            msgs = []
        hit = None
        for m in msgs:
            mdk = _message_dedup_key(cl, m)
            if mdk == dk:
                hit = m
                break

        resolved_text = None
        if hit is not None:
            fetch_mid = target_mid if target_mid.startswith("c") and _looks_like_line_chat_mid(target_mid) else None
            body = _msg_body_line_with_e2ee_register(
                cl,
                hit,
                None,
                set(),
                skip_register=skip_e2ee_key_register,
                fetch_chat_mid=fetch_mid,
            )
            if _is_textual_body(body):
                resolved_text = body

        if resolved_text is not None:
            date_part = str(item.get("date_part") or "?")
            tag = str(item.get("tag") or target.recv_tag)
            heading = f"### {date_part}｜{route.org_label}｜{tag}｜{md_make_summary(resolved_text)}"
            block = f"""

{heading}

{md_wrap_details(resolved_text)}

---
"""
            if dry_run:
                print(f"[dry-run][retry-resolved] {heading}", file=sys.stderr)
            else:
                content = route.yoritoori_md.read_text(encoding="utf-8")
                route.yoritoori_md.write_text(
                    md_insert_block_after_timeline_header(content, block),
                    encoding="utf-8",
                )
                seen_keys.add(dk)
                new_keys.add(dk)
            appended += 1
            done_keys.append(dk)
            continue

        attempts += 1
        item["attempts"] = attempts
        item["next_retry_ts"] = now_ts + retry_interval_sec
        if attempts >= retry_max_attempts:
            # 諦めてプレースホルダで確定
            body_raw = str(item.get("body_raw") or "[本文なし · E2EE 未復号またはコンパクトプレビューのみ]")
            date_part = str(item.get("date_part") or "?")
            tag = str(item.get("tag") or target.recv_tag)
            heading = f"### {date_part}｜{route.org_label}｜{tag}｜{md_make_summary(body_raw)}"
            block = f"""

{heading}

{md_wrap_details(body_raw)}

---
"""
            if dry_run:
                print(f"[dry-run][retry-fallback] {heading}", file=sys.stderr)
            else:
                content = route.yoritoori_md.read_text(encoding="utf-8")
                route.yoritoori_md.write_text(
                    md_insert_block_after_timeline_header(content, block),
                    encoding="utf-8",
                )
                seen_keys.add(dk)
                new_keys.add(dk)
            appended += 1
            done_keys.append(dk)
            if verbose:
                print(f"# retry queue fallback: attempts={attempts} dk={dk[:16]}...", file=sys.stderr)

    for dk in done_keys:
        queue_items.pop(dk, None)
    return appended


def _auto_backfill_count(default_count: int, stats_file: Path, *, lookback_runs: int = 10) -> int:
    """直近ログの本文率で backfill 件数を調整する（控えめ）。"""
    if not stats_file.is_file():
        return default_count
    rows: list[dict] = []
    try:
        with stats_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rows.append(rec)
    except OSError:
        return default_count
    if not rows:
        return default_count
    rows = rows[-lookback_runs:]
    seen = 0
    textual = 0
    for r in rows:
        stats = r.get("stats")
        if not isinstance(stats, list):
            continue
        for b in stats:
            if not isinstance(b, dict):
                continue
            seen += int(b.get("seen", 0))
            textual += int(b.get("textual", 0))
    if seen <= 0:
        return default_count
    rate = textual / seen
    if rate < 0.05:
        return min(300, max(default_count, 240))
    if rate < 0.20:
        return min(240, max(default_count, 160))
    if rate > 0.50:
        return max(60, min(default_count, 100))
    return default_count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="sync 差分を 5.やり取り.md に追記（1:1 / グループ）",
    )
    parser.add_argument(
        "--preset",
        choices=("line-default", "tcell-both", "tcell-yuki", "leaf-grandole", "none"),
        default="line-default",
        help="line-default: Tcell（キャラメルG のみ）+ LEAF（Grandole…）。tcell-both: Tcell グループのみ。tcell-yuki: 1:1 のみ（互換）",
    )
    parser.add_argument(
        "--yoritoori-md",
        type=Path,
        default=None,
        help="5.やり取り.md（line-default / tcell-both / tcell-yuki で未指定時は Tcell 既定）",
    )
    parser.add_argument(
        "--filter-chat-mid",
        default="",
        help="--preset tcell-yuki のとき 1:1 の chat 列部分一致（未指定時は yuki 既定 mid）",
    )
    parser.add_argument(
        "--org-label",
        default="Tcell",
        help="見出しの組織名（例: Tcell）",
    )
    parser.add_argument(
        "--peer-label",
        default="yukiさん",
        help="1:1 相手の呼び方（受信見出しに使用）",
    )
    parser.add_argument(
        "--group-chat-mid",
        default="",
        help="グループの chatMid（部分一致用）。空なら LINE_TCELL_GROUP_CHAT_MID または --group-title で名前解決",
    )
    parser.add_argument(
        "--group-title",
        default=_DEFAULT_GROUP_TITLE,
        help="Tcell グループの chatMid 未指定時、トーク名にこの文字列が含まれるものを使う",
    )
    parser.add_argument(
        "--group-peer-label",
        default=_DEFAULT_GROUP_TITLE,
        help="Tcell グループの見出し表示名",
    )
    parser.add_argument(
        "--leaf-yoritoori-md",
        type=Path,
        default=None,
        help="LEAF の 5.やり取り.md（leaf-grandole / line-default で未指定時は OneDrive または repo 既定）",
    )
    parser.add_argument(
        "--leaf-org-label",
        default="LEAF",
        help="LEAF 追記ブロックの組織名（見出し）",
    )
    parser.add_argument(
        "--leaf-group-chat-mid",
        default="",
        help="LEAF グループの chatMid（部分一致）。空なら LINE_LEAF_GROUP_CHAT_MID または --leaf-group-title で名前解決",
    )
    parser.add_argument(
        "--leaf-group-title",
        default=_LEAF_GROUP_TITLE_DEFAULT,
        help="LEAF グループの chatMid 未指定時、トーク名にこの文字列が含まれるものを使う",
    )
    parser.add_argument(
        "--leaf-group-peer-label",
        default="",
        help="LEAF グループの見出し表示名（空なら実名に近い既定ラベル）",
    )
    parser.add_argument(
        "--include-send",
        action="store_true",
        help="SEND_MESSAGE も追記（省略時は受信のみ）",
    )
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--sync-reason", type=int, default=None)
    parser.add_argument(
        "--state-file",
        default="",
        help=f"未指定時は LINE_UNOFFICIAL_AUTH_DIR/{STATE_FILENAME}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="MD・dedup・sync 状態を更新しない",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
    )
    parser.add_argument(
        "--direct-backfill-count",
        type=int,
        default=120,
        help="各ターゲットごとに getRecentMessagesV2 で直近を取得して補完する件数（グループ中心運用でも必須。0で無効）",
    )
    parser.add_argument(
        "--decode-stats-file",
        default="",
        help=f"本文取得成功率の JSONL ログ（未指定時は LINE_UNOFFICIAL_AUTH_DIR/{DECODE_STATS_FILENAME}）",
    )
    parser.add_argument("--skip-e2ee-key-register", action="store_true")
    parser.add_argument(
        "--allow-qr-login",
        action="store_true",
        help="保存トークン無効時に QR 再認証を許可する（明示実行時のみ付与推奨）",
    )
    parser.add_argument(
        "--lock-timeout-sec",
        type=int,
        default=1800,
        help="ロックファイルの期限秒。超過時は stale とみなして取り直す（既定 1800）",
    )
    parser.add_argument(
        "--retry-queue",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="本文プレースホルダを再照会キューに積んで後追い回収する（既定: 有効）",
    )
    parser.add_argument(
        "--retry-interval-sec",
        type=int,
        default=300,
        help="再照会キューの再試行間隔（秒）",
    )
    parser.add_argument(
        "--retry-max-attempts",
        type=int,
        default=6,
        help="再照会キューの最大試行回数（超過時はプレースホルダで確定）",
    )
    parser.add_argument(
        "--retry-fetch-count",
        type=int,
        default=120,
        help="再照会時に getRecentMessagesV2 で見る件数",
    )
    parser.add_argument(
        "--adaptive-backfill",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="直近ログの本文率に応じて backfill 件数を自動調整する（既定: 有効）",
    )
    parser.add_argument(
        "--defer-sync-placeholders",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="sync で本文プレースホルダの行は一旦保留し、直近補完後に未解決分だけ追記する（既定: 有効）",
    )
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    yoritoori_md_arg = args.yoritoori_md
    needle = args.filter_chat_mid.strip()
    routes: list[_YoritooriRoute] = []
    preset = args.preset

    if preset == "none":
        if yoritoori_md_arg is None:
            print("エラー: --preset none のときは --yoritoori-md が必要です。", file=sys.stderr)
            return 1
        if not needle:
            print("エラー: --filter-chat-mid が必要です。", file=sys.stderr)
            return 1
        npath = yoritoori_md_arg.expanduser().resolve()
        routes.append(
            _YoritooriRoute(
                npath,
                args.org_label,
                [
                    _YoritooriTarget(
                        needle=needle,
                        recv_tag=f"{args.peer_label}から返信（LINE・CHRLINE sync）",
                        send_tag="自分から送信（LINE・CHRLINE sync）",
                    )
                ],
            )
        )
    elif preset in ("line-default", "tcell-both"):
        if yoritoori_md_arg is None:
            tpath = _default_tcell_yoritoori_path()
        else:
            tpath = yoritoori_md_arg.expanduser().resolve()
        routes.append(_YoritooriRoute(tpath, args.org_label, []))

    elif preset == "tcell-yuki":
        if yoritoori_md_arg is None:
            tpath = _default_tcell_yoritoori_path()
        else:
            tpath = yoritoori_md_arg.expanduser().resolve()
        yuki_needle = needle or _YUKI_CHAT_NEEDLE_DEFAULT
        routes.append(
            _YoritooriRoute(
                tpath,
                args.org_label,
                [
                    _YoritooriTarget(
                        needle=yuki_needle,
                        recv_tag=f"{args.peer_label}から返信（LINE 1:1・CHRLINE sync）",
                        send_tag="自分から送信（LINE 1:1・CHRLINE sync）",
                    )
                ],
            )
        )

    if preset in ("line-default", "leaf-grandole"):
        if args.leaf_yoritoori_md is None:
            lpath = _default_leaf_yoritoori_path()
        else:
            lpath = args.leaf_yoritoori_md.expanduser().resolve()
        routes.append(_YoritooriRoute(lpath, args.leaf_org_label, []))

    if not routes:
        print("エラー: ルートが構成できません。", file=sys.stderr)
        return 1

    for r in routes:
        if not r.yoritoori_md.is_file():
            print(f"エラー: やり取りファイルがありません: {r.yoritoori_md}", file=sys.stderr)
            return 1

    save_root = save_root_from_env()
    lock_path = _lock_path(save_root)
    if not _acquire_lock(lock_path, max(0, int(args.lock_timeout_sec))):
        print(
            f"エラー: 実行ロック中のためスキップしました: {lock_path}"
            "（並列実行を避けるため。必要なら既存プロセス終了後に再実行）",
            file=sys.stderr,
        )
        return 3
    state_path = (
        Path(args.state_file)
        if args.state_file.strip()
        else (save_root / STATE_FILENAME)
    )
    state = _load_state(state_path)
    saved_rev = state.get("last_operation_revision")
    try:
        saved_rev_i = int(saved_rev) if saved_rev is not None else None
    except (TypeError, ValueError):
        saved_rev_i = None

    if args.init:
        local_rev = 0
        reason = args.sync_reason if args.sync_reason is not None else 3
    else:
        local_rev = saved_rev_i if saved_rev_i is not None else 0
        reason = args.sync_reason if args.sync_reason is not None else 2

    receive_only = not args.include_send

    dedup_file = _dedup_path(save_root)
    stats_file = (
        Path(args.decode_stats_file).expanduser().resolve()
        if args.decode_stats_file.strip()
        else _decode_stats_path(save_root)
    )
    seen_keys = _load_dedup(dedup_file)
    new_keys: set[str] = set()
    decode_stats: dict[str, dict] = {}

    try:
        cl = build_logged_in_client(save_root, allow_qr_login=bool(args.allow_qr_login))

        if preset in ("line-default", "tcell-both"):
            tcell_route = routes[0]
            gneedle = (args.group_chat_mid or "").strip() or (
                os.environ.get("LINE_TCELL_GROUP_CHAT_MID") or ""
            ).strip()
            if not gneedle:
                gneedle = _resolve_group_mid_by_title(cl, (args.group_title or "").strip()) or ""
            if not gneedle:
                print(
                    "エラー: Tcell グループの chatMid を特定できませんでした。"
                    " chrline_list_chats_poc.py で一覧を確認するか、"
                    " --group-chat-mid または環境変数 LINE_TCELL_GROUP_CHAT_MID を設定してください。",
                    file=sys.stderr,
                )
                return 1
            glabel = (args.group_peer_label or "").strip() or _DEFAULT_GROUP_TITLE
            tcell_route.targets.append(
                _YoritooriTarget(
                    needle=gneedle,
                    recv_tag=f"{glabel}（LINEグループ・CHRLINE sync・受信）",
                    send_tag="自分から送信（LINEグループ・CHRLINE sync）",
                )
            )

        if preset in ("line-default", "leaf-grandole"):
            leaf_route = routes[-1] if preset == "line-default" else routes[0]
            lneedle = (args.leaf_group_chat_mid or "").strip() or (
                os.environ.get("LINE_LEAF_GROUP_CHAT_MID") or ""
            ).strip()
            if not lneedle:
                lneedle = _resolve_group_mid_by_title(cl, (args.leaf_group_title or "").strip()) or ""
            if not lneedle:
                print(
                    "エラー: LEAF グループの chatMid を特定できませんでした。"
                    " chrline_list_chats_poc.py で一覧を確認するか、"
                    " --leaf-group-chat-mid または環境変数 LINE_LEAF_GROUP_CHAT_MID を設定してください。",
                    file=sys.stderr,
                )
                return 1
            lpeer = (
                (args.leaf_group_peer_label or "").strip() or _LEAF_GROUP_PEER_LABEL_DEFAULT
            )
            leaf_route.targets.append(
                _YoritooriTarget(
                    needle=lneedle,
                    recv_tag=f"{lpeer}（LINEグループ・CHRLINE sync・受信）",
                    send_tag="自分から送信（LINEグループ・CHRLINE sync）",
                )
            )

        route_target_map: dict[tuple[str, str], tuple[_YoritooriRoute, _YoritooriTarget]] = {}
        for route in routes:
            for tmeta in route.targets:
                route_target_map[(str(route.yoritoori_md), tmeta.needle)] = (route, tmeta)

        retry_queue_items: dict[str, dict] = {}
        retry_queue_path = _retry_queue_path(save_root)
        if args.retry_queue:
            retry_queue_items = _load_retry_queue(retry_queue_path)

        appended = 0
        if args.retry_queue and retry_queue_items:
            appended += _process_retry_queue(
                cl,
                queue_items=retry_queue_items,
                route_target_map=route_target_map,
                seen_keys=seen_keys,
                new_keys=new_keys,
                dry_run=args.dry_run,
                skip_e2ee_key_register=args.skip_e2ee_key_register,
                retry_fetch_count=int(args.retry_fetch_count),
                retry_interval_sec=int(args.retry_interval_sec),
                retry_max_attempts=int(args.retry_max_attempts),
                verbose=args.verbose,
            )

        ops = _run_sync(cl, local_rev, max(1, min(args.count, 500)), reason)
        if not isinstance(ops, list):
            ops = []

        max_seen = saved_rev_i or 0
        e2ee_registered: set[str] = set()
        pending_sync_placeholders: list[_PendingSyncPlaceholder] = []

        for op in ops:
            ot = cl.checkAndGetValue(op, "type", 3)
            if ot is None and isinstance(op, dict):
                ot = op.get(3)
            try:
                ot_i = int(ot)
            except (TypeError, ValueError):
                ot_i = -1

            rv = _op_revision(cl, op)
            if rv is not None and rv > max_seen:
                max_seen = rv

            msg = cl.checkAndGetValue(op, "message", 20)
            if msg is None and isinstance(op, dict):
                msg = op.get(20) or op.get("message")

            if ot_i not in _MESSAGE_OP_TYPES or msg is None:
                continue
            if receive_only and ot_i != OpType.RECEIVE_MESSAGE:
                continue
            if not receive_only and ot_i not in (OpType.RECEIVE_MESSAGE, OpType.SEND_MESSAGE):
                continue

            chat = _chat_hint_from_op(cl, op, msg)
            matched: list[tuple[_YoritooriRoute, _YoritooriTarget]] = []
            for route in routes:
                tmeta = _pick_target(chat, route.targets)
                if tmeta is not None:
                    matched.append((route, tmeta))
            if not matched:
                continue

            body_raw = _msg_body_line_with_e2ee_register(
                cl,
                msg,
                op,
                e2ee_registered,
                skip_register=args.skip_e2ee_key_register,
                fetch_chat_mid=_group_fetch_mid_from_targets(matched),
            )
            is_placeholder = _is_placeholder_body(body_raw)
            if is_placeholder and args.verbose:
                print(f"# sync: {_op_type_name(ot_i)} 本文プレースホルダー", file=sys.stderr)

            dk = _message_dedup_key(cl, msg)
            if dk and dk in seen_keys:
                for route, tmeta in matched:
                    _observe_decode_stats(
                        decode_stats,
                        route,
                        tmeta,
                        body_raw,
                        source="sync",
                        dedup_skipped=True,
                    )
                continue

            ts = _msg_time(cl, msg)
            when = _format_line_msg_when(ts)
            date_part = when.split()[0] if when and " " in when else when or "?"

            wrote = False
            for route, tmeta in matched:
                tag = tmeta.recv_tag if ot_i == OpType.RECEIVE_MESSAGE else tmeta.send_tag

                if args.retry_queue and is_placeholder and dk:
                    _enqueue_retry(
                        retry_queue_items,
                        dk=dk,
                        route=route,
                        target=tmeta,
                        tag=tag,
                        date_part=date_part,
                        ts=ts,
                        body_raw=body_raw,
                        now_ts=int(time.time()),
                        retry_interval_sec=int(args.retry_interval_sec),
                    )
                elif args.defer_sync_placeholders and is_placeholder and dk:
                    pending_sync_placeholders.append(
                        _PendingSyncPlaceholder(
                            route=route,
                            target=tmeta,
                            ts=ts,
                            date_part=date_part,
                            body_raw=body_raw,
                            dk=dk,
                            tag=tag,
                        )
                    )
                else:
                    summary = md_make_summary(body_raw)
                    heading = f"### {date_part}｜{route.org_label}｜{tag}｜{summary}"
                    block = f"""

{heading}

{md_wrap_details(body_raw)}

---
"""
                    if args.dry_run:
                        print(
                            f"[dry-run] 追記予定 → {route.yoritoori_md.name}:\n"
                            f"{heading}\n{body_raw[:200]!r}…\n"
                        )
                    else:
                        content = route.yoritoori_md.read_text(encoding="utf-8")
                        route.yoritoori_md.write_text(
                            md_insert_block_after_timeline_header(content, block),
                            encoding="utf-8",
                        )
                        if dk:
                            seen_keys.add(dk)
                            new_keys.add(dk)
                    wrote = True

                _observe_decode_stats(
                    decode_stats,
                    route,
                    tmeta,
                    body_raw,
                    source="sync",
                    wrote=wrote,
                )

            if wrote:
                appended += 1

        backfill_count = int(args.direct_backfill_count)
        if args.adaptive_backfill and backfill_count > 0:
            tuned = _auto_backfill_count(backfill_count, stats_file)
            if tuned != backfill_count and args.verbose:
                print(f"# adaptive-backfill: {backfill_count} -> {tuned}", file=sys.stderr)
            backfill_count = tuned

        if backfill_count > 0:
            for route in routes:
                for tmeta in route.targets:
                    appended += _append_direct_backfill_from_recent(
                        cl,
                        route=route,
                        target=tmeta,
                        receive_only=receive_only,
                        count=backfill_count,
                        seen_keys=seen_keys,
                        new_keys=new_keys,
                        skip_e2ee_key_register=args.skip_e2ee_key_register,
                        dry_run=args.dry_run,
                        verbose=args.verbose,
                        decode_stats=decode_stats,
                        retry_queue_items=(retry_queue_items if args.retry_queue else None),
                        retry_interval_sec=int(args.retry_interval_sec),
                    )

        if pending_sync_placeholders:
            pending_sync_placeholders.sort(key=lambda x: x.ts)
            wrote_pending = 0
            for p in pending_sync_placeholders:
                if p.dk in seen_keys:
                    continue
                summary = md_make_summary(p.body_raw)
                heading = f"### {p.date_part}｜{p.route.org_label}｜{p.tag}｜{summary}"
                block = f"""

{heading}

{md_wrap_details(p.body_raw)}

---
"""
                if args.dry_run:
                    print(
                        f"[dry-run][保留解放] 追記予定 → {p.route.yoritoori_md.name}:\n"
                        f"{heading}\n{p.body_raw[:200]!r}…\n"
                    )
                else:
                    content = p.route.yoritoori_md.read_text(encoding="utf-8")
                    p.route.yoritoori_md.write_text(
                        md_insert_block_after_timeline_header(content, block),
                        encoding="utf-8",
                    )
                    seen_keys.add(p.dk)
                    new_keys.add(p.dk)
                wrote_pending += 1
            if wrote_pending and args.verbose:
                print(f"# sync プレースホルダー保留分を追記: {wrote_pending} 件", file=sys.stderr)
            appended += wrote_pending

        if new_keys and not args.dry_run:
            _save_dedup(dedup_file, seen_keys)

        if not args.dry_run and (ops or max_seen > (saved_rev_i or 0)):
            _save_state(
                state_path,
                {
                    "last_operation_revision": max_seen,
                    "last_sync_local_revision_used": local_rev,
                    "last_op_count": len(ops),
                },
            )
            print(f"# sync 状態更新: {state_path} last_operation_revision={max_seen}", file=sys.stderr)

        if args.retry_queue and not args.dry_run:
            _save_retry_queue(retry_queue_path, retry_queue_items)

        stats_buckets = [b for b in decode_stats.values() if int(b.get("seen", 0)) > 0]
        if stats_buckets:
            for b in sorted(stats_buckets, key=lambda x: (x["org_label"], x["target_mid"])):
                seen = int(b.get("seen", 0))
                textual = int(b.get("textual", 0))
                pct = (textual / seen * 100.0) if seen else 0.0
                kind = "1:1" if b.get("is_personal_u_mid") else "G"
                print(
                    "# 本文取得率"
                    f" [{kind} {b['org_label']}:{b['target_mid'][:12]}...]"
                    f" seen={seen} textual={textual} placeholder={int(b.get('placeholder', 0))}"
                    f" media_or_stamp={int(b.get('media_or_stamp', 0))}"
                    f" written={int(b.get('written', 0))}"
                    f" rate={pct:.1f}%",
                    file=sys.stderr,
                )
            if not args.dry_run:
                _append_decode_stats_jsonl(
                    stats_file,
                    {
                        "ts": datetime.now().isoformat(timespec="seconds"),
                        "preset": preset,
                        "receive_only": receive_only,
                        "count": int(args.count),
                        "direct_backfill_count": int(backfill_count),
                        "defer_sync_placeholders": bool(args.defer_sync_placeholders),
                        "stats": sorted(
                            stats_buckets,
                            key=lambda x: (x["org_label"], x["target_mid"], x["target_label"]),
                        ),
                    },
                )
                print(f"# 本文取得率ログ追記: {stats_file}", file=sys.stderr)

        out_paths = ", ".join(str(r.yoritoori_md) for r in routes)
        print(f"# やり取り追記: {appended} 件 → {out_paths}", file=sys.stderr)
        return 0
    finally:
        _release_lock(lock_path)


if __name__ == "__main__":
    raise SystemExit(main())
