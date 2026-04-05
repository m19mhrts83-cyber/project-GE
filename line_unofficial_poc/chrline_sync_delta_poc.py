#!/usr/bin/env python3
"""
TalkService.sync() の operations から、メッセージ系の差分を標準出力する POC。

過去の全履歴は getRecentMessagesV2 等に依存するが、DESKTOP セッションで空になる場合でも、
sync ストリームに SEND_MESSAGE / RECEIVE_MESSAGE 等が載ることがある（環境・端末による）。

前回までに見た Operation.revision を .chrline_sync_delta_state.json に保存し、
次回は同じリビジョンを渡して差分だけ取り込む運用を想定する。

出力は TSV（時刻・op種別・chat 識別子・送信者・本文プレビュー）。トークンは出さない。
chat 列: グループは c mid、1:1 受信は「1:1:<相手 u mid>」（to=自分のとき）。
E2EE 本文は **CHRLINE が参照するローカル鍵（keyId）** が揃っている必要がある。
（LINE 公式アプリの同期の有無とは別経路。鍵不足・QR 直後の古い keyId 配信分などでは復号できないことがある。）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from CHRLINE.helpers.bulders.message import Message as BuilderMessage
from CHRLINE.serializers.DummyProtocol import DummyProtocol
from CHRLINE.services.thrift.ttypes import OpType

from chrline_client_utils import build_logged_in_client, save_root_from_env
from chrline_dump_messages_poc import (
    _coerce_line_mid_str,
    _format_line_msg_when,
    _msg_body_line,
    _msg_content_type,
    _msg_plain_text,
    _msg_sender_mid,
    _msg_time,
)


def _wrap_message_for_e2ee_decrypt(cl, op, msg):
    """
    sync の Operation 内 Message は素の DummyThrift のことがあり、
    decryptE2EEMessage が参照する .sender / .receiver（bulders.Message）が無い。
    多くの経路では thrift_ins が None のため、dd() を dict にして BuilderMessage を生成する。
    val_* をコピーし、受信方向のため Operation を _ref に付ける。
    """
    if msg is None or isinstance(msg, dict):
        return msg
    if isinstance(msg, BuilderMessage):
        try:
            msg.set_ref(op)
        except Exception:
            pass
        return msg
    wrapped: object | None = None
    ti = getattr(msg, "thrift_ins", None)
    if ti is not None:
        wrapped = DummyProtocol.wrap_thrift(
            cl, ti, isDummy=getattr(msg, "is_dummy", True)
        )
        if not isinstance(wrapped, BuilderMessage):
            wrapped = None
    if wrapped is None:
        try:
            dd = msg.dd()
        except Exception:
            dd = {}
        try:
            ins_map = {int(k): v for k, v in dd.items()}
            wrapped = BuilderMessage(ins=ins_map, cl=cl)
        except Exception:
            return msg
    for k, v in list(getattr(msg, "__dict__", {}).items()):
        if k.startswith("val_"):
            try:
                setattr(wrapped, k, v)
            except Exception:
                pass
    try:
        wrapped.set_ref(op)
    except Exception:
        pass
    return wrapped


def _normalize_content_metadata_for_decrypt(cl, msg) -> None:
    """
    e2ee.decryptE2EEMessage は contentMetadata.get を使う。
    Thrift の map が dict 以外だと AttributeError になりうるので str キーの dict に寄せる。
    """
    if msg is None:
        return
    md = cl.checkAndGetValue(msg, "contentMetadata", 18)
    if md is None and isinstance(msg, dict):
        md = msg.get(18) or msg.get("contentMetadata")
    if md is None:
        return
    if isinstance(md, dict) and md and all(isinstance(k, str) for k in md):
        return
    out: dict[str, str] = {}
    try:
        items = None
        if isinstance(md, dict):
            items = md.items()
        elif hasattr(md, "dd"):
            items = md.dd().items()
        if not items:
            return
        for k, v in items:
            if v is None:
                continue
            sk = k.decode("utf-8", errors="replace") if isinstance(k, bytes) else str(k)
            if isinstance(v, (bytes, bytearray)):
                try:
                    sv = v.decode("utf-8", errors="replace")
                except Exception:
                    sv = str(v)
            else:
                sv = str(v)
            out[sk] = sv
    except Exception:
        return
    if not out:
        return
    try:
        msg[18] = out
    except Exception:
        try:
            setattr(msg, "val_18", out)
        except Exception:
            pass


def _trace_e2ee_decrypt_failures(cl, op, msg) -> None:
    """verbose 時: プレースホルダ本文のとき復号を試して例外を stderr に出す。"""
    if msg is None:
        return
    if _msg_plain_text(cl, msg):
        return
    chunks = cl.checkAndGetValue(msg, "chunks", 20)
    if chunks is None and isinstance(msg, dict):
        chunks = msg.get(20) or msg.get("chunks")
    if not isinstance(chunks, (list, tuple)) or len(chunks) < 5:
        print(
            "# E2EE trace: chunks なしまたは短い（コンパクト／プレビューのみの可能性）",
            file=sys.stderr,
        )
        return
    ct = _msg_content_type(cl, msg)
    print(f"# E2EE trace: contentType={ct} chunk_len={len(chunks)}", file=sys.stderr)
    wmsg = _wrap_message_for_e2ee_decrypt(cl, op, msg)
    if not isinstance(wmsg, BuilderMessage):
        print(
            "# E2EE trace: Message ラップ不可（dict 等）",
            file=sys.stderr,
        )
        return
    msg = wmsg
    for is_self in (False, True):
        try:
            t = cl.decryptE2EETextMessage(msg, isSelf=is_self)
            if isinstance(t, str) and t.strip():
                print(
                    f"# E2EE trace: isSelf={is_self} で復号成功（表示経路の不整合の可能性）",
                    file=sys.stderr,
                )
            else:
                print(
                    f"# E2EE trace: isSelf={is_self} は空文字",
                    file=sys.stderr,
                )
        except Exception as e:
            print(
                f"# E2EE trace: isSelf={is_self} → {type(e).__name__}: {e}",
                file=sys.stderr,
            )


def _patch_message_to_when_sync_points_to_self(
    cl, msg, group_mid: str | None
) -> None:
    """
    sync の RECEIVE_MESSAGE 等で Message.to が自分の u mid のままになると、
    CHRLINE の E2EE 復号は receiver.mid（= to）を鍵コンテキストに使うため失敗しやすい。
    Operation / metadata から得たグループ c mid があるとき、to==自分だけ上書きする。
    """
    if msg is None:
        return
    g = (group_mid or "").strip()
    if not g.startswith("c"):
        return
    self_mid = (getattr(cl, "mid", None) or "").strip()
    if not self_mid:
        return
    cur = cl.checkAndGetValue(msg, "to", 2)
    cur_s = ""
    if cur is not None:
        cur_s = _coerce_line_mid_str(cur) or str(cur).strip()
    if cur_s == g:
        return
    if cur_s != self_mid:
        return
    try:
        msg[2] = g
    except Exception:
        try:
            setattr(msg, "val_2", g)
        except Exception:
            pass

STATE_FILENAME = ".chrline_sync_delta_state.json"

# メッセージ本文の取得を試みる Operation.type（OpType）
_MESSAGE_OP_TYPES = frozenset(
    {
        OpType.SEND_MESSAGE,
        OpType.RECEIVE_MESSAGE,
        OpType.NOTIFIED_UPDATE_MESSAGE,
        OpType.NOTIFIED_DESTROY_MESSAGE,
        OpType.DESTROY_MESSAGE,
        OpType.FAILED_SEND_MESSAGE,
        OpType.FAILED_DELIVERY_MESSAGE,
    }
)


def _op_type_name(t: int | None) -> str:
    if t is None:
        return "?"
    return OpType._VALUES_TO_NAMES.get(t, str(t))


def _msg_to_mid(cl, msg) -> str | None:
    m = cl.checkAndGetValue(msg, "to", 2)
    if m is None and isinstance(msg, dict):
        m = msg.get(2) or msg.get("to")
    if m is None:
        return None
    return _coerce_line_mid_str(m)


def _looks_like_line_chat_mid(s: str) -> bool:
    s = s.strip()
    return len(s) >= 24 and s[0] in "cu"


def _group_mids_from_operation_params(op) -> list[str]:
    out: list[str] = []
    for fld in ("param1", "param2", "param3"):
        v = getattr(op, fld, None)
        if isinstance(v, str) and v.strip().startswith("c") and _looks_like_line_chat_mid(v):
            out.append(v.strip())
    return out


def _guess_group_mid_from_message_metadata(cl, msg) -> str | None:
    md = cl.checkAndGetValue(msg, "contentMetadata", 18)
    if md is None and isinstance(msg, dict):
        md = msg.get(18) or msg.get("contentMetadata")
    if md is None:
        return None
    candidates: list[str] = []
    if hasattr(md, "dd"):
        try:
            candidates.extend(str(x) for x in md.dd().values() if x is not None)
        except Exception:
            pass
    if isinstance(md, dict):
        candidates.extend(str(x) for x in md.values() if x is not None)
    for s in candidates:
        t = s.strip()
        if t.startswith("c") and len(t) >= 24:
            return t
    return None


def _chat_hint_from_op(cl, op, msg) -> str:
    """
    sync の RECEIVE_MESSAGE で Message の to が自分の u mid になることがある。
    グループ E2EE では Operation.param か contentMetadata に c mid があるのでそれを優先する。
    1:1 の受信では to=自分が正しいので、チャット列は「1:1:<相手 mid>」に読み替える。
    """
    self_mid = (getattr(cl, "mid", None) or "").strip()
    for mid in _group_mids_from_operation_params(op):
        return mid
    if msg is not None:
        gm = _guess_group_mid_from_message_metadata(cl, msg)
        if gm:
            return gm
        mid = _msg_to_mid(cl, msg)
        if mid:
            if self_mid and mid == self_mid:
                snd = _msg_sender_mid(cl, msg)
                tt = cl.checkAndGetValue(msg, "toType", 3)
                if tt is None and isinstance(msg, dict):
                    tt = msg.get(3) or msg.get("toType")
                try:
                    tt_i = int(tt) if tt is not None else -1
                except (TypeError, ValueError):
                    tt_i = -1
                if tt_i == 0 and snd and snd != self_mid:
                    return f"1:1:{snd}"
            return mid
    for fld in ("param1", "param2", "param3"):
        v = getattr(op, fld, None)
        if isinstance(v, str) and v.strip() and _looks_like_line_chat_mid(v):
            return v.strip()
    return ""


def _collect_e2ee_group_mids(cl, op, msg) -> list[str]:
    """tryRegisterE2EEGroupKey 用のグループ mid（重複なし）。"""
    seen: dict[str, None] = {}
    for m in _group_mids_from_operation_params(op):
        seen[m] = None
    if msg is not None:
        gm = _guess_group_mid_from_message_metadata(cl, msg)
        if gm:
            seen[gm] = None
    return list(seen.keys())


def _msg_body_line_with_e2ee_register(
    cl,
    msg,
    op,
    registered: set[str],
    *,
    skip_register: bool,
    fetch_chat_mid: str | None = None,
) -> str:
    """
    fetch_chat_mid:
      getRecentMessagesV2 等で op が無いとき、メッセージの to が自分 u mid のままだと
      グループ E2EE 復号が失敗しやすい。取得対象のグループ c mid を明示すると
      _patch_message_to_when_sync_points_to_self が効いて本文が取れることがある。
    """
    gids = list(_collect_e2ee_group_mids(cl, op, msg))
    fc = (fetch_chat_mid or "").strip()
    if fc.startswith("c") and _looks_like_line_chat_mid(fc) and fc not in gids:
        gids.insert(0, fc)
    if gids:
        _patch_message_to_when_sync_points_to_self(cl, msg, gids[0])
    for gid in gids:
        if skip_register or gid in registered:
            continue
        try:
            cl.tryRegisterE2EEGroupKey(gid)
            registered.add(gid)
        except Exception:
            pass
    _normalize_content_metadata_for_decrypt(cl, msg)
    wmsg = _wrap_message_for_e2ee_decrypt(cl, op, msg)
    return _msg_body_line(cl, wmsg)


def _load_state(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _op_revision(cl, op) -> int | None:
    r = cl.checkAndGetValue(op, "revision", 1)
    if r is None and not isinstance(op, dict):
        r = getattr(op, "revision", None)
    if r is None and isinstance(op, dict):
        r = op.get(1) or op.get("revision")
    try:
        v = int(r)
        return v
    except (TypeError, ValueError):
        return None


def _run_sync(cl, local_revision: int, count: int, sync_reason: int | None) -> list:
    try:
        return cl.sync(local_revision, count, sync_reason)
    except RuntimeError as e:
        print(f"# sync RuntimeError: {e}", file=sys.stderr)
        return []
    except EOFError as e:
        print(f"# sync 応答エラー: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"# sync 例外: {type(e).__name__}: {e}", file=sys.stderr)
        return []


def main() -> int:
    parser = argparse.ArgumentParser(
        description="LINE sync() の operations からメッセージ差分を TSV 出力し、リビジョンを保存する",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=100,
        help="sync の取得件数（既定 100）",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="初回寄り: local revision を 0、fullSyncReason を MANUAL_SYNC(3) にする",
    )
    parser.add_argument(
        "--sync-reason",
        type=int,
        default=None,
        help="fullSyncRequestReason を上書き（0–4）。未指定時は --init で 3、それ以外は 2（PERIODIC）",
    )
    parser.add_argument(
        "--state-file",
        default="",
        help=f"状態 JSON のパス（未指定時は LINE_UNOFFICIAL_AUTH_DIR/{STATE_FILENAME}）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="状態ファイルを更新しない",
    )
    parser.add_argument(
        "--filter-chat-mid",
        default="",
        help="この chatMid（部分一致可）の行だけ標準出力する",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="stderr に Operation 種別の集計を出す",
    )
    parser.add_argument(
        "--skip-e2ee-key-register",
        action="store_true",
        help="tryRegisterE2EEGroupKey を呼ばない（副作用を避ける）",
    )
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

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

    cl = build_logged_in_client(save_root)
    ops = _run_sync(cl, local_rev, max(1, min(args.count, 500)), reason)

    if not isinstance(ops, list):
        ops = []

    type_counts: dict[int, int] = {}
    max_seen = saved_rev_i or 0
    needle = args.filter_chat_mid.strip().lower()
    e2ee_registered: set[str] = set()

    for op in ops:
        ot = cl.checkAndGetValue(op, "type", 3)
        if ot is None and isinstance(op, dict):
            ot = op.get(3)
        try:
            ot_i = int(ot)
        except (TypeError, ValueError):
            ot_i = -1
        type_counts[ot_i] = type_counts.get(ot_i, 0) + 1

        rv = _op_revision(cl, op)
        if rv is not None and rv > max_seen:
            max_seen = rv

        msg = cl.checkAndGetValue(op, "message", 20)
        if msg is None and isinstance(op, dict):
            msg = op.get(20) or op.get("message")

        if ot_i not in _MESSAGE_OP_TYPES or msg is None:
            continue

        chat = _chat_hint_from_op(cl, op, msg)
        if needle and needle not in chat.lower():
            continue

        before_reg = set(e2ee_registered)
        body_raw = _msg_body_line_with_e2ee_register(
            cl, msg, op, e2ee_registered, skip_register=args.skip_e2ee_key_register
        )
        if args.verbose and "[本文なし" in body_raw:
            _trace_e2ee_decrypt_failures(cl, op, msg)
        if args.verbose and e2ee_registered != before_reg:
            print(
                f"# E2EE tryRegister: {e2ee_registered - before_reg}",
                file=sys.stderr,
            )

        ts = _msg_time(cl, msg)
        when = _format_line_msg_when(ts)
        sender = _msg_sender_mid(cl, msg) or ""
        body = body_raw.replace("\t", " ").replace("\n", " ")
        line = f"{when}\t{ot_i}\t{_op_type_name(ot_i)}\t{chat}\t{sender}\t{body}"
        print(line)

    if args.verbose:
        print("# --- Operation.type 集計 ---", file=sys.stderr)
        for k in sorted(type_counts.keys()):
            print(f"#   {_op_type_name(k)}\t({k})\t{type_counts[k]}", file=sys.stderr)
        print(f"# ops 総数: {len(ops)}  max_revision: {max_seen}", file=sys.stderr)

    if not args.dry_run and (ops or max_seen > (saved_rev_i or 0)):
        _save_state(
            state_path,
            {
                "last_operation_revision": max_seen,
                "last_sync_local_revision_used": local_rev,
                "last_op_count": len(ops),
            },
        )
        print(f"# 状態を更新: {state_path} last_operation_revision={max_seen}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
