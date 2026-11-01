#!/usr/bin/env python3
"""神大家: 項目別の作業履歴と質問回答。ローカル正本→認証済みDashboard。

各変更は履歴として追加。--push は変更保存後に明示し、失敗時も正本を保持する。
実績不明はnull。agent_elapsedを本人の請求時間に算入しない。
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path.home() / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C2_ルーティン作業/26_パートナー社への相談/P806_神大家AI推進/工数管理"
TIME_KINDS = ("unrecorded", "owner_confirmed", "estimated", "agent_elapsed")
STATUSES = ("planned", "running", "waiting", "done")


def now() -> str:
    return datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="seconds")


def atomic_write(path: Path, text: str) -> None:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as f:
        temp = Path(f.name)
        try:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    temp.replace(path)


def load(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "updated_at": None, "projects": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("projects"), list):
        raise ValueError("対応していない履歴形式です")
    return data


def project(data: dict, pid: str) -> dict:
    return next(p for p in data["projects"] if p["id"] == pid)


def render(data: dict) -> str:
    lines = ["# 神大家運営 作業項目・履歴", "", "自動生成。編集は jarvis_kamiooya_work_history.py で行う。", f"最終更新: {data['updated_at']}", ""]
    for p in data["projects"]:
        lines += [f"## {p['title']} ({p['id']})", "", f"- 当初見積: {p.get('estimate_minutes') if p.get('estimate_minutes') is not None else '未記録'} 分", ""]
        for i in p["items"]:
            lines += [f"### {i['title']} ({i['id']}) — {i['status']}", ""]
            for e in p["events"]:
                if e["item_id"] == i["id"]:
                    minutes = e.get("minutes")
                    lines += [f"- {e['at']} / {e['actor']} / {e['kind']}: {e['summary']}", f"  時間: {minutes if minutes is not None else '未記録'} 分 ({e['time_kind']}) / 記録ID: {e['id']}"]
                    if e.get("question_id"):
                        lines += [f"  質問ID: {e['question_id']}"]
                    if e.get("supersedes"):
                        lines += [f"  訂正対象: {e['supersedes']}"]
                    lines += [f"  根拠: {url}" for url in e["evidence"]]
            lines.append("")
    return "\n".join(lines) + "\n"


def push(data: dict) -> None:
    import requests
    url = os.environ.get("JARVIS_SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise ValueError("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です")
    # 全公開はしない。既存sync_metaのauthenticated RLSを利用する。
    response = requests.post(
        url + "/rest/v1/sync_meta?on_conflict=key",
        headers={"apikey": key, "Authorization": "Bearer " + key, "Prefer": "resolution=merge-duplicates,return=minimal"},
        json={"key": "kamiooya_work_history", "value": json.dumps(data, ensure_ascii=False), "updated_at": now()},
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(f"Dashboard同期失敗 HTTP {response.status_code}（ローカル履歴は保存済み）")
    print("Dashboard同期完了")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", type=Path, default=BASE / "work_history.json")
    ap.add_argument("--push", action="store_true", help="保存後Dashboardへ同期。showでは同期のみ")
    subs = ap.add_subparsers(dest="command", required=True)
    plan = subs.add_parser("plan")
    plan.add_argument("--project", required=True)
    plan.add_argument("--title", required=True)
    plan.add_argument("--estimate-minutes", type=int)
    plan.add_argument("--item", action="append", required=True, help="項目ID:名称")
    for cmd in ("add-item", "log", "note", "ask", "answer"):
        p = subs.add_parser(cmd)
        p.add_argument("--project", required=True)
        p.add_argument("--item", required=True)
        p.add_argument("--actor", default="Chappy")
        p.add_argument("--summary", required=True)
        p.add_argument("--evidence", action="append", default=[])
        p.add_argument("--event-id", help="再試行時は同じIDで重複追記を防ぐ")
        p.add_argument("--supersedes", help="訂正する旧記録ID。元記録も保持する")
        p.add_argument("--minutes", type=int)
        p.add_argument("--time-kind", choices=TIME_KINDS, default="unrecorded")
        p.add_argument("--status", choices=STATUSES)
        if cmd == "answer":
            p.add_argument("--question-id", required=True)
    subs.add_parser("show")
    args = ap.parse_args(argv)
    path = args.file.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    # 正本単位のlock。pushも含め直列化し、古いスナップショットの上書きを防ぐ。
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = load(path)
        changed = False
        if args.command == "plan":
            if any(p["id"] == args.project for p in data["projects"]):
                raise ValueError("案件IDは登録済みです。変更は項目と履歴を追記してください")
            if args.estimate_minutes is not None and args.estimate_minutes < 0:
                raise ValueError("見積分は0以上です")
            items = []
            for item in args.item:
                ident, title = item.split(":", 1)
                if not re.fullmatch(r"[a-zA-Z0-9_-]+", ident) or not title.strip():
                    raise ValueError("項目IDと名称を確認してください")
                if any(i["id"] == ident for i in items):
                    raise ValueError("項目IDが重複しています")
                items.append({"id": ident, "title": title, "status": "planned"})
            data["projects"].append({"id": args.project, "title": args.title, "estimate_minutes": args.estimate_minutes, "created_at": now(), "items": items, "events": []})
            changed = True
        elif args.command != "show":
            p = project(data, args.project)
            eid = args.event_id or uuid.uuid4().hex
            existing = next((e for e in p["events"] if e["id"] == eid), None)
            if existing:
                print(f"登録済み: {eid}")
            else:
                if args.minutes is not None and args.minutes < 0:
                    raise ValueError("所要分は0以上です")
                if (args.minutes is None) != (args.time_kind == "unrecorded"):
                    raise ValueError("時間未記録はminutesを省略し、時間を入れる場合はtime-kindを明示してください")
                for url in args.evidence:
                    if not re.match(r"^https://", url):
                        raise ValueError("根拠リンクはHTTPS URLを指定してください。秘密やローカルパスは同期しません")
                if args.command == "add-item":
                    if any(i["id"] == args.item for i in p["items"]):
                        raise ValueError("項目IDは登録済みです")
                    p["items"].append({"id": args.item, "title": args.summary, "status": "planned"})
                item = next(i for i in p["items"] if i["id"] == args.item)
                if args.supersedes:
                    old = next(e for e in p["events"] if e["id"] == args.supersedes and e["item_id"] == args.item)
                    if old["kind"] == "ask" or args.command not in ("log", "answer"):
                        raise ValueError("質問は回答で紐づけ、実績の訂正はlog/answerで行ってください")
                    if any(e.get("supersedes") == old["id"] for e in p["events"]):
                        raise ValueError("既に訂正済みです。最新の記録IDを指定してください")
                if args.command == "answer":
                    q = next(e for e in p["events"] if e["id"] == args.question_id and e["kind"] == "ask" and e["item_id"] == args.item)
                    if any(e.get("question_id") == q["id"] for e in p["events"]):
                        raise ValueError("回答済みです。訂正はlogとして旧回答IDと理由を記録してください")
                if args.status:
                    item["status"] = args.status
                event = {"id": eid, "at": now(), "item_id": args.item, "kind": args.command, "actor": args.actor, "summary": args.summary, "minutes": args.minutes, "time_kind": args.time_kind, "evidence": args.evidence}
                if args.command == "answer":
                    event["question_id"] = args.question_id
                if args.status:
                    event["status"] = args.status
                if args.supersedes:
                    event["supersedes"] = args.supersedes
                p["events"].append(event)
                changed = True
                print(f"記録ID: {eid}")
        if changed:
            data["updated_at"] = now()
            atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            atomic_write(path.with_suffix(".md"), render(data))
        if args.push:
            push(data)
        if args.command == "show":
            print(render(data))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, StopIteration, OSError, RuntimeError) as exc:
        raise SystemExit(str(exc) or "指定された案件・項目・質問が見つかりません")
