#!/usr/bin/env python3
"""313 期日超過の整理 — 優先順位づけとリスケ提案（L1）.

- 既定: 期日超過を読み、上位N件の「新期日案」を Slack #consult へ（書き込みなし）
- `--apply --select 📅3,📅5`: その番号だけ due_date を未来へ移動（コメント付き）
- 自動では動かさない（人の「リスケ 📅N」が条件）
- 番号は **📅N**（完了候補の ✅N と区別・別投稿）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_PATH = REPO / ".jarvis_state" / "todoist_313_overdue.json"
MAX_TOP = 5
AGENT_ID = "313"
AGENT_ROLE = "完了候補確認"
ITEM_MARK = "📅"  # 完了候補は ✅（別投稿・記号で区別）
USERNAME = f"{AGENT_ID} {AGENT_ROLE}"

IMPORTANT_RE = re.compile(r"(要ボス|優先1|優先２|優先2|緊急|高)", re.I)
IMPLEMENT_RE = re.compile(r"(実装|設計|調査)", re.I)
EASY_RE = re.compile(r"(quick|すぐ|確認のみ)", re.I)
LANE_BONUS = {"properties": 10, "apps": 6, "kamiooya": 6}


def _today() -> date:
    return datetime.now(JST).date()


def _token() -> str:
    return (
        os.environ.get("TODOIST_API_TOKEN_OWNER")
        or os.environ.get("TODOIST_API_TOKEN")
        or ""
    ).strip()


def _api(method: str, path: str, body: dict | None = None) -> dict:
    tok = _token()
    if not tok:
        raise SystemExit("TODOIST_API_TOKEN がありません（.env.jarvis_private を source）")
    url = "https://api.todoist.com/api/v1" + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {tok}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=40) as r:
        raw = r.read().decode("utf-8")
    return json.loads(raw) if raw.strip() else {}


def _fetch_overdue(limit: int = 200) -> list[dict]:
    d = _api("GET", f"/tasks?filter=overdue&limit={limit}")
    items = d.get("results", d) if isinstance(d, dict) else d
    today = _today()
    out = []
    for t in items or []:
        due = (t.get("due") or {}).get("date")
        if not due:
            continue
        try:
            d0 = date.fromisoformat(due[:10])
        except ValueError:
            continue
        if d0 >= today:
            continue
        out.append(t)
    return out


def _score(t: dict, today: date) -> tuple[int, int, list[str]]:
    labels = [str(x) for x in (t.get("labels") or [])]
    title = str(t.get("content") or "")
    blob = title + " " + " ".join(labels)
    days = (today - date.fromisoformat(t["due"]["date"][:10])).days
    why: list[str] = []
    score = min(days, 60)
    if IMPORTANT_RE.search(blob):
        score += 30
        why.append("重要")
    if IMPLEMENT_RE.search(blob):
        score += 10
        why.append("実装/調査")
    if EASY_RE.search(blob):
        score += 5
        why.append("すぐ終わる")
    for lane, bonus in LANE_BONUS.items():
        if lane in labels:
            score += bonus
            break
    return score, days, why


def _next_business_day(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _propose_date(days_over: int, today: date) -> date:
    if days_over <= 7:
        target = today + timedelta(days=2)
    elif days_over <= 30:
        target = today + timedelta(days=7)
    else:
        target = today + timedelta(days=14)
    return _next_business_day(target)


def _short(s: str, width: int = 44) -> str:
    t = " ".join(str(s or "").split())
    t = re.sub(r"\[[0-9a-f]{8,}\]\s*", " ", t)
    if len(t) <= width:
        return t.strip()
    head = t[:width]
    for sep in ("：", "。", " — ", " - ", " "):
        i = head.rfind(sep)
        if i >= width * 0.5:
            return head[:i].rstrip("：。 -—") + "…"
    return head.rstrip() + "…"


def _items(tasks: list[dict], top: int) -> list[dict]:
    today = _today()
    rows = []
    for t in tasks:
        score, days, why = _score(t, today)
        rows.append(
            {
                "task_id": str(t.get("id")),
                "title": str(t.get("content") or ""),
                "labels": [str(x) for x in (t.get("labels") or [])],
                "due": str(t["due"]["date"])[:10],
                "days_over": days,
                "why": why,
                "score": score,
                "new_due": _propose_date(days, today).isoformat(),
            }
        )
    rows.sort(key=lambda r: (-r["score"], -r["days_over"]))
    for i, r in enumerate(rows[:top], 1):
        r["n"] = i
    return rows[:top]


def _parse_select_nums(select: str) -> set[int]:
    """「📅1,📅3」「リスケ 📅2」「1,3」を番号集合に。"""
    nums: set[int] = set()
    for m in re.finditer(rf"(?:{re.escape(ITEM_MARK)})?\s*(\d+)", select or ""):
        nums.add(int(m.group(1)))
    return nums


def _format(items: list[dict], total: int) -> str:
    stamp = datetime.now(JST).strftime("%m/%d %H:%M")
    lines = [
        f"【相談】{AGENT_ID} {AGENT_ROLE}｜期日超過",
        f"{ITEM_MARK} *期日超過の整理*（{ITEM_MARK}番号・最大{MAX_TOP}）",
        f"超過 *{total}件* ／ 上位{len(items)}件 ／ {stamp}",
        "",
        "*この順番で見ています*",
        "",
    ]
    for it in items:
        lane = next(
            (x for x in it["labels"] if x in LANE_BONUS or x in ("ai_raimo", "kazoku", "agent_team")),
            "",
        )
        meta = "・".join(x for x in [lane.replace("_", " "), f"{it['days_over']}日超過",
                                     "/".join(it["why"])] if x)
        lines.append(
            f"*{ITEM_MARK}{it['n']}.* <https://app.todoist.com/app/task/{it['task_id']}|{_short(it['title'])}>"
            f"  _({meta})_"
        )
        lines.append(f"→ *{it['new_due']}* へ")
        lines.append("")
    lines.extend(
        [
            f"*リスケしてよければ {ITEM_MARK}番号で返信（またはボタン）*",
            f"「→MM-DD へ延期」ボタン → 提案日へ移動（確認画面／アプリ内）",
            f"「リスケ {ITEM_MARK}3,{ITEM_MARK}5」または「{ITEM_MARK}3,5」→ 番号で延期",
            "「全部そのまま」→ 何もしない（次回また出ます）",
            "タイトルリンク → Todoist 詳細（リンクだけでは延期しません）",
            "※完了候補は別投稿の ✅番号（このスレではリスケのみ）",
            "",
            f"次: 人判断（リスケ {ITEM_MARK}N）",
            "",
            "担当メモ: 新期日＝超過が浅い+2営業日／中+7日／深い+14日（土日は翌営業日）",
            "",
            "橋渡し: 期日変更のみ。完了は313本体の ✅番号",
        ]
    )
    return "\n".join(lines)


def _post(text: str) -> int:
    url = (os.environ.get("SLACK_WEBHOOK_AI_TEAM_CONSULT") or "").strip()
    if not url:
        print("❌ SLACK_WEBHOOK_AI_TEAM_CONSULT がありません", file=sys.stderr)
        return 2
    payload = {"text": text, "username": USERNAME}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"✅ Slack 投稿 OK status={r.status}")
            return 0
    except Exception as e:  # noqa: BLE001
        print(f"❌ Slack failed: {e}", file=sys.stderr)
        return 1


def _load_state() -> dict:
    if not STATE_PATH.is_file():
        return {"proposals": []}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"proposals": []}


def _save_state(d: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _apply(items: list[dict], nums: set[int], dry: bool) -> list[dict]:
    author = (os.environ.get("TODOIST_313_AUTHOR") or "Jarvis").strip()
    results = []
    for it in items:
        if int(it["n"]) not in nums:
            continue
        if dry:
            results.append({"ok": True, "dry": True, **it})
            continue
        try:
            _api(
                "POST",
                "/comments",
                {
                    "task_id": it["task_id"],
                    "content": (
                        f"【{author}】\n"
                        f"サマリ: 期日を {it['due']} → {it['new_due']} にリスケ"
                        f"（{it['days_over']}日超過・「リスケ {ITEM_MARK}{it['n']}」了承）\n"
                        "アウトプット:\n"
                        f"- [該当タスク](https://app.todoist.com/app/task/{it['task_id']})\n"
                    ),
                },
            )
            _api("POST", f"/tasks/{it['task_id']}", {"due_date": it["new_due"]})
            results.append({"ok": True, **it})
        except urllib.error.HTTPError as e:
            results.append({"ok": False, "error": f"HTTP {e.code}", **it})
        except Exception as e:  # noqa: BLE001
            results.append({"ok": False, "error": str(e), **it})
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--top", type=int, default=MAX_TOP)
    ap.add_argument(
        "--select",
        default=None,
        help=f"リスケする番号（例 {ITEM_MARK}3,{ITEM_MARK}5 または 3,5）",
    )
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument(
        "--url-buttons",
        action="store_true",
        help="延期を URL ボタンにする（Interactivity 不要・確認画面あり）",
    )
    ap.add_argument("--force-webhook", action="store_true")
    ap.add_argument("--blocks-preview", action="store_true")
    args = ap.parse_args(argv)

    top_n = max(1, min(args.top, MAX_TOP))
    state = _load_state()
    items = list(state.get("proposals") or [])
    total = int(state.get("scanned") or len(items))
    # apply は既存提案を使う（--refresh で再収集可）。投稿時も空なら収集。
    if args.refresh or not items:
        tasks = _fetch_overdue()
        items = _items(tasks, top_n)
        state = {
            "proposals": items,
            "scanned": len(tasks),
            "at": datetime.now(JST).isoformat(timespec="seconds"),
        }
        _save_state(state)
        total = len(tasks)
    elif len(items) > top_n:
        items = items[:top_n]
        for i, r in enumerate(items, 1):
            r["n"] = i
        state["proposals"] = items
        _save_state(state)

    if args.apply:
        if not args.select:
            raise SystemExit(f"--select {ITEM_MARK}3,{ITEM_MARK}5 が必要です（一括は不可）")
        nums = _parse_select_nums(args.select.strip())
        results = _apply(items, nums, args.dry_run)
        for r in results:
            mark = "[dry] " if r.get("dry") else ""
            if r.get("ok"):
                print(f"- {mark}rescheduled {r['due']} → {r['new_due']}  {r['title'][:50]}")
            else:
                print(f"- FAIL {r.get('error')} {r['title'][:50]}", file=sys.stderr)
        return 0 if all(r.get("ok") for r in results) else 1

    text = _format(items, total)
    print(text)
    print()
    print(f"📎 313 overdue: total={total} top={len(items)} state={STATE_PATH.name}")
    if not items:
        print("超過0件のため投稿スキップ")
        return 0

    try:
        from jarvis_todoist_313_slack_blocks import (  # type: ignore
            build_reschedule_blocks,
            prefer_url_mode,
            post_slack,
        )
    except ImportError:
        sys.path.insert(0, str(REPO / "scripts"))
        from jarvis_todoist_313_slack_blocks import (  # type: ignore
            build_reschedule_blocks,
            prefer_url_mode,
            post_slack,
        )

    url_mode = prefer_url_mode(force_url=bool(getattr(args, "url_buttons", False)))
    for it in items:
        it["title_short"] = _short(it.get("title") or "")
    payload = build_reschedule_blocks(
        items,
        header_text="313 期日超過の整理",
        fallback_text=text,
        url_mode=url_mode,
        total=total,
    )
    if getattr(args, "blocks_preview", False):
        print("# blocks preview url_mode=", url_mode)
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:4000])
    if args.dry_run:
        print("（--dry-run: Slack 未投稿）")
        return 0
    return post_slack(
        payload,
        dry_run=False,
        force_webhook=bool(getattr(args, "force_webhook", False)),
        force_url_buttons=url_mode,
    )


if __name__ == "__main__":
    sys.exit(main())
