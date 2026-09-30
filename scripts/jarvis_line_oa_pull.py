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


def build_export_txt(group_label: str, events: list[dict], cache: dict, token: str) -> str:
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
        lines.append(f"{dt.strftime('%H:%M')}\t{name}\t{fmt_text(ev)}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="LINE OA Webhook 受信 → 公式エクスポート形式 .txt 生成")
    p.add_argument("--route-id", help="line_export_routes.yaml の route id（例 tcell_caramel_g）")
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

    if not args.route_id:
        raise SystemExit("--route-id が必要です（--list-groups 以外）")

    from line_export_inbox_to_yoritoori import default_inbox_dir, default_routes_path  # noqa: E402

    routes_path = default_routes_path()
    cfg = route_config(routes_path, args.route_id)
    group_label = str(cfg.get("group_label") or cfg.get("display_name") or args.route_id)
    group_id = (args.group_id or oa_group_id(routes_path, args.route_id) or "").strip()
    if not group_id:
        raise SystemExit(f"group_id 不明。--group-id を指定するか line_export_routes.yaml の line_oa.group_ids.{args.route_id} に追記してください")

    q = (
        "line_oa_events?select=id,event_type,group_id,user_id,message_type,text,event_timestamp"
        f"&group_id=eq.{group_id}&processed_at=is.null&order=event_timestamp.asc,id.asc&limit={args.limit}"
    )
    events = _rest(url, key, q)
    if not args.include_system:
        events = [e for e in events if str(e.get("event_type")) == "message"]
    if not events:
        print(f"# 未処理イベントなし（route={args.route_id} group={group_id}）")
        return 0

    cache = load_name_cache()
    txt = build_export_txt(group_label, events, cache, token)
    save_name_cache(cache)

    if args.dry_run:
        print(f"# dry-run: {len(events)}件 → inbox へ書き込み予定（route={args.route_id}）")
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
    print(f"  route={args.route_id} group={group_id} label={group_label}")
    print("  次: line_export_inbox_to_yoritoori.py が inbox から取り込みます（line-export-poll は15分間隔）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
