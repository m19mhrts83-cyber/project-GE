#!/usr/bin/env python3
"""Jarvis: LINE 公式アカウント（Messaging API）で受信したグループ本文を
公式エクスポート形式の .txt に整形し、inbox へ置く（Tcell PoC）。

- 受信側: apps/jarvis-dashboard/app/api/line/webhook → Supabase `line_oa_events`
- 本スクリプト: 未処理イベントを pull → linelog2py 互換の .txt → inbox
- 後続: 既存 line_export_inbox_to_yoritoori.py が 5.やり取り.md へ取り込む

使い方:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_line_oa_pull.py --list-groups
  python scripts/jarvis_line_oa_pull.py --route-id tcell_caramel_g --group-id Cxxxxx --dry-run
  python scripts/jarvis_line_oa_pull.py --route-id tcell_caramel_g --group-id Cxxxxx

必要な環境変数:
  JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY（or _SECRET_KEY）
  LINE_OA_CHANNEL_ACCESS_TOKEN  … 任意。あると表示名・添付が解決できる
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
NAME_CACHE = Path.home() / ".cursor" / "line_oa_names.json"
YOUBI = "月火水木金土日"

if str(MANUAL) not in sys.path:
    sys.path.insert(0, str(MANUAL))


def _supabase() -> tuple[str, str]:
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip().rstrip("/")
    key = (
        os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("JARVIS_SUPABASE_SECRET_KEY")
        or ""
    ).strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が未設定です")
    return url, key


def _rest(url: str, key: str, path: str, method: str = "GET", body: object | None = None, prefer: str = ""):
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(f"{url}/rest/v1/{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw.strip() else []


def load_name_cache() -> dict:
    if NAME_CACHE.is_file():
        try:
            data = json.loads(NAME_CACHE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_name_cache(cache: dict) -> None:
    NAME_CACHE.parent.mkdir(parents=True, exist_ok=True)
    NAME_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_name(group_id: str, user_id: str | None, cache: dict, token: str) -> str:
    if not user_id:
        return "（名前なし）"
    ck = f"{group_id}:{user_id}"
    if ck in cache:
        return cache[ck]
    if not token:
        cache[ck] = user_id
        return user_id
    url = f"https://api.line.me/v2/bot/group/{group_id}/member/{user_id}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            name = json.loads(resp.read().decode("utf-8")).get("displayName") or user_id
    except urllib.error.HTTPError as e:
        name = user_id if e.code != 200 else user_id
    except Exception:
        name = user_id
    cache[ck] = name
    return name


def route_config(routes_path: Path, route_id: str) -> dict:
    data = yaml.safe_load(routes_path.read_text(encoding="utf-8")) or {}
    for item in data.get("routes") or []:
        if isinstance(item, dict) and str(item.get("id") or "").strip() == route_id:
            return item
    raise SystemExit(f"route-id '{route_id}' が {routes_path} にありません")


def oa_group_id(routes_path: Path, route_id: str) -> str | None:
    data = yaml.safe_load(routes_path.read_text(encoding="utf-8")) or {}
    oa = data.get("line_oa") or {}
    gids = oa.get("group_ids") or {}
    gid = gids.get(route_id)
    return str(gid).strip() if gid else None


MEDIA_TYPES = {"image", "file", "video", "audio"}
CONTENT_API = "https://api-data.line.me/v2/bot/message/{mid}/content"
_CT_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "video/mp4": ".mp4",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "application/zip": ".zip",
}


def _safe_name(name: str) -> str:
    s = "".join(c for c in name if c not in '\\/:*?"<>|').strip()
    return s[:120] or "file"


def download_media(ev: dict, partner_root: Path, folder: str, token: str) -> str:
    """画像/ファイル等の実体を `1.受信添付(Stock)/YYYY-MM-DD/` へ保存し、表示ラベルを返す。

    保存名は messageId から決まる（再取得しても同じ名前＝重複しない）。
    filename は LINE の raw.message.fileName（file のみ）を使う。
    """
    mtype = (ev.get("message_type") or "").lower()
    label = {"image": "[画像]", "file": "[ファイル]", "video": "[動画]", "audio": "[音声]"}.get(mtype, f"[{mtype}]")
    mid = str(ev.get("message_id") or "")
    if not mid:
        return label
    if not token:
        return f"{label}（未保存: LINE_OA_CHANNEL_ACCESS_TOKEN 未設定）"
    ts = ev.get("event_timestamp")
    dt = datetime.fromtimestamp(ts / 1000, tz=JST) if ts else datetime.now(JST)
    day = dt.strftime("%Y-%m-%d")
    try:
        req = urllib.request.Request(
            CONTENT_API.format(mid=mid), headers={"Authorization": f"Bearer {token}"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
            ct = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    except Exception as e:  # noqa: BLE001
        return f"{label}（取得失敗: {type(e).__name__}）"
    raw = ev.get("raw") if isinstance(ev.get("raw"), dict) else {}
    orig = str((raw.get("message") or {}).get("fileName") or "").strip()
    ext = Path(orig).suffix if orig else (_CT_EXT.get(ct) or ".bin")
    stem = f"LINE_{dt.strftime('%Y%m%d_%H%M%S')}_{mid[:8]}"
    fname = f"{stem}_{_safe_name(orig)}" if orig else f"{stem}{ext}"
    dest_dir = partner_root / folder / "1.受信添付(Stock)" / day
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / fname).write_bytes(data)
    return f"{label}（受信添付: {day}/{fname}）"


def fmt_text(ev: dict) -> str:
    mtype = (ev.get("message_type") or "").lower()
    if mtype == "text" or (not mtype and ev.get("text")):
        return (ev.get("text") or "").replace("\t", " ")
    if mtype == "image":
        return "[画像]"
    if mtype == "video":
        return "[動画]"
    if mtype == "audio":
        return "[音声]"
    if mtype == "file":
        return "[ファイル]"
    if mtype == "sticker":
        return "[スタンプ]"
    if mtype == "location":
        return "[位置情報]"
    return f"[{mtype or 'unknown'}]"


def build_export_txt(
    group_label: str, events: list[dict], cache: dict, token: str, labels: dict | None = None
) -> str:
    lines = [f"[LINE] {group_label}のトーク履歴", f"保存日時：{datetime.now(JST).strftime('%Y/%m/%d %H:%M')}", ""]
    cur_date = None
    for ev in events:
        ts = ev.get("event_timestamp")
        dt = datetime.fromtimestamp(ts / 1000, tz=JST) if ts else datetime.now(JST)
        d = dt.strftime("%Y/%m/%d")
        if d != cur_date:
            if cur_date is not None:
                lines.append("")
            lines.append(f"{d}({YOUBI[dt.weekday()]})")
            cur_date = d
        name = resolve_name(str(ev.get("group_id") or ""), ev.get("user_id"), cache, token)
        body = (labels or {}).get(ev.get("id")) or fmt_text(ev)
        lines.append(f"{dt.strftime('%H:%M')}\t{name}\t{body}")
    lines.append("")
    return "\n".join(lines)


def oa_group_ids(routes_path: Path) -> list[tuple[str, str]]:
    """line_export_routes.yaml の line_oa.group_ids（route id → groupId）を列挙。"""
    data = yaml.safe_load(routes_path.read_text(encoding="utf-8")) or {}
    gids = ((data.get("line_oa") or {}).get("group_ids")) or {}
    out: list[tuple[str, str]] = []
    for rid, gid in gids.items():
        if gid:
            out.append((str(rid).strip(), str(gid).strip()))
    return out


def pull_route(url: str, key: str, token: str, routes_path: Path, route_id: str, group_id: str, args) -> int:
    cfg = route_config(routes_path, route_id)
    group_label = str(cfg.get("group_label") or cfg.get("display_name") or route_id)
    q = (
        "line_oa_events?select=id,event_type,group_id,user_id,message_type,message_id,text,"
        "event_timestamp,raw"
        f"&group_id=eq.{group_id}&processed_at=is.null&order=event_timestamp.asc,id.asc&limit={args.limit}"
    )
    fetched = _rest(url, key, q)
    if args.include_system:
        events = fetched
    else:
        events = [e for e in fetched if str(e.get("event_type")) == "message"]
    # 出力対象外（join/leave 等）は processed へ寄せて未処理の滞留を防ぐ
    rendered_ids = {e.get("id") for e in events}
    dropped = [str(e.get("id")) for e in fetched if e.get("id") is not None and e.get("id") not in rendered_ids]
    if dropped and not args.dry_run:
        _rest(
            url,
            key,
            f"line_oa_events?id=in.({','.join(dropped)})",
            method="PATCH",
            body={"processed_at": datetime.now(JST).isoformat(timespec="seconds")},
            prefer="return=minimal",
        )
    if not events:
        print(f"# 未処理イベントなし（route={route_id} group={group_id}）")
        return 0

    from line_export_inbox_to_yoritoori import default_common_dir, default_inbox_dir  # noqa: E402

    # 画像・ファイル等は実体を 1.受信添付(Stock) へ保存し、本文には保存先を書く
    labels: dict[int, str] = {}
    media_events = [e for e in events if str(e.get("message_type") or "").lower() in MEDIA_TYPES]
    if media_events:
        if args.dry_run:
            for ev in media_events:
                labels[ev.get("id")] = f"{fmt_text(ev)}（dry-run: 保存予定）"
        else:
            partner_root = default_common_dir().parent
            folder = str(cfg.get("folder") or "")
            for ev in media_events:
                labels[ev.get("id")] = download_media(ev, partner_root, folder, token)

    cache = load_name_cache()
    txt = build_export_txt(group_label, events, cache, token, labels)
    save_name_cache(cache)

    if args.dry_run:
        print(f"# dry-run: {len(events)}件 → inbox へ書き込み予定（route={route_id}）")
        print(txt[:1500])
        return 0

    inbox = default_inbox_dir()
    inbox.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
    out = inbox / f"[LINE] {group_label}のトーク_OA{stamp}.txt"
    out.write_text(txt, encoding="utf-8")

    ids = ",".join(str(e["id"]) for e in events if e.get("id") is not None)
    if ids:
        _rest(
            url,
            key,
            f"line_oa_events?id=in.({ids})",
            method="PATCH",
            body={"processed_at": datetime.now(JST).isoformat(timespec="seconds")},
            prefer="return=minimal",
        )

    print(f"📎 LINE OA pull: {len(events)}件 → {out.name}")
    print(f"  route={route_id} group={group_id} label={group_label}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="LINE OA Webhook 受信 → 公式エクスポート形式 .txt 生成")
    p.add_argument("--route-id", help="line_export_routes.yaml の route id（例 tokai_dx_gojokai）")
    p.add_argument("--all", action="store_true", help="line_oa.group_ids の全ルートを処理（定常向け）")
    p.add_argument("--group-id", help="LINE の groupId（未指定なら routes yaml の line_oa.group_ids から）")
    p.add_argument("--list-groups", action="store_true", help="受信済み group_id を集計して表示")
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--dry-run", action="store_true", help="ファイルを書かず・processed も立てない")
    p.add_argument("--include-system", action="store_true", help="join/leave 等も出力")
    args = p.parse_args()

    url, key = _supabase()
    token = (os.environ.get("LINE_OA_CHANNEL_ACCESS_TOKEN") or "").strip()

    if args.list_groups:
        rows = _rest(url, key, "line_oa_events?select=group_id,processed_at,message_type&order=created_at.desc&limit=2000")
        tally: dict[str, list[int]] = {}
        for r in rows:
            gid = r.get("group_id") or "(1:1/room)"
            t = tally.setdefault(gid, [0, 0])
            t[0] += 1
            if r.get("processed_at") is None:
                t[1] += 1
        if not tally:
            print("受信イベントはまだありません（Webhook 未着）")
            return 0
        print("group_id / 総件数 / 未処理")
        for gid, (total, unproc) in sorted(tally.items(), key=lambda x: -x[1][0]):
            print(f"  {gid}\t{total}\t{unproc}")
        return 0

    from line_export_inbox_to_yoritoori import default_routes_path  # noqa: E402

    routes_path = default_routes_path()

    if args.all:
        pairs = oa_group_ids(routes_path)
        if not pairs:
            print("# line_oa.group_ids が空です（line_export_routes.yaml）")
            return 0
        rc = 0
        for rid, gid in pairs:
            rc |= pull_route(url, key, token, routes_path, rid, gid, args)
        return rc

    if not args.route_id:
        raise SystemExit("--route-id か --all が必要です（--list-groups 以外）")
    group_id = (args.group_id or oa_group_id(routes_path, args.route_id) or "").strip()
    if not group_id:
        raise SystemExit(
            f"group_id 不明。--group-id を指定するか "
            f"line_export_routes.yaml の line_oa.group_ids.{args.route_id} に追記してください"
        )
    return pull_route(url, key, token, routes_path, args.route_id, group_id, args)


if __name__ == "__main__":
    raise SystemExit(main())
