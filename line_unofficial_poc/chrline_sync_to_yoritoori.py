#!/usr/bin/env python3
"""
CHRLINE sync の差分から、指定 1:1（chat mid 部分一致）のメッセージだけを
215 のパートナー用 5.やり取り.md に追記する。

既定プリセット「line-default」（推奨）:
  - **1回の sync** で次をまとめて処理（別プロセスに分けると取りこぼす）:
    - Tcell: yuki 1:1 + グループ「キャラメル管理G」→ 103_Tcell/5.やり取り.md
    - LEAF: グループ名に「Grandole志賀本通」を含むトーク（一覧例: Grandole志賀本通 I … 管理）→ 104_LEAF/5.やり取り.md
  - グループ chatMid はトーク名の部分一致で解決、または各種 LINE_*_GROUP_CHAT_MID / --group-chat-mid・--leaf-group-chat-mid

プリセット「tcell-both」: Tcell のみ（yuki + キャラメル管理G）
プリセット「tcell-yuki」: Tcell 1:1 のみ
プリセット「leaf-grandole」: LEAF のみ（上記 Grandole グループ）

状態・重複:
  - sync リビジョンは chrline_sync_delta_poc と同じ .chrline_sync_delta_state.json
  - 追記済みは LINE_UNOFFICIAL_AUTH_DIR の .chrline_sync_yoritoori_dedup.json（message id + 時刻）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="sync 差分を 5.やり取り.md に追記（1:1 / グループ）",
    )
    parser.add_argument(
        "--preset",
        choices=("line-default", "tcell-both", "tcell-yuki", "leaf-grandole", "none"),
        default="line-default",
        help="line-default: Tcell（yuki+キャラメルG）+ LEAF（Grandole志賀本通…）を同一 sync で。tcell-both / tcell-yuki / leaf-grandole / none",
    )
    parser.add_argument(
        "--yoritoori-md",
        type=Path,
        default=None,
        help="5.やり取り.md（Tcell 系 preset で未指定時は Tcell 既定）",
    )
    parser.add_argument(
        "--filter-chat-mid",
        default="",
        help="1:1 の chat 列部分一致（Tcell 系で未指定時は yuki 側 mid 既定）",
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
    parser.add_argument("--skip-e2ee-key-register", action="store_true")
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
    elif preset in ("line-default", "tcell-yuki", "tcell-both"):
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
    seen_keys = _load_dedup(dedup_file)
    new_keys: set[str] = set()

    cl = build_logged_in_client(save_root)

    if preset in ("tcell-both", "line-default"):
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

    ops = _run_sync(cl, local_rev, max(1, min(args.count, 500)), reason)
    if not isinstance(ops, list):
        ops = []

    max_seen = saved_rev_i or 0
    e2ee_registered: set[str] = set()
    appended = 0

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
        if not receive_only and ot_i not in (
            OpType.RECEIVE_MESSAGE,
            OpType.SEND_MESSAGE,
        ):
            continue

        chat = _chat_hint_from_op(cl, op, msg)

        body_raw = _msg_body_line_with_e2ee_register(
            cl, msg, op, e2ee_registered, skip_register=args.skip_e2ee_key_register
        )
        if body_raw.startswith(_PLACEHOLDER_PREFIX):
            if args.verbose:
                print(f"# スキップ（本文未取得）: {_op_type_name(ot_i)}", file=sys.stderr)
            continue

        dk = _message_dedup_key(cl, msg)
        if dk and dk in seen_keys:
            continue

        ts = _msg_time(cl, msg)
        when = _format_line_msg_when(ts)
        date_part = when.split()[0] if when and " " in when else when or "?"
        summary = md_make_summary(body_raw)

        wrote = False
        for route in routes:
            tmeta = _pick_target(chat, route.targets)
            if tmeta is None:
                continue

            if ot_i == OpType.RECEIVE_MESSAGE:
                tag = tmeta.recv_tag
            else:
                tag = tmeta.send_tag

            heading = f"### {date_part}｜{route.org_label}｜{tag}｜{summary}"
            block = f"""

{heading}

{md_wrap_details(body_raw)}

---
"""

            if args.dry_run:
                print(f"[dry-run] 追記予定 → {route.yoritoori_md.name}:\n{heading}\n{body_raw[:200]!r}…\n")
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

        if wrote:
            appended += 1

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

    out_paths = ", ".join(str(r.yoritoori_md) for r in routes)
    print(f"# やり取り追記: {appended} 件 → {out_paths}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
