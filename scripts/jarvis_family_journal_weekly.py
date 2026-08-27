#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""家族コーチ向け — Obsidian ★Journal 週次要約 → Notion（フォールバック · 2026-08-28〜）。

**Grok 正本**: admin Drive 上の Obsidian ★Journal（統括が直読み）。本スクリプトは Drive 読取 NG 時の
Notion 投影用。移行安定後は launchd 停止可（`jarvis-family-coaching-weekly.mdc` Phase 3）。

週の区切り: **土曜始まり〜金曜終わり（金締）**。
土日の後追いログは月曜に残ることが多いため、日曜朝の投影は金曜までの分を正とする。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_family_journal_weekly.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_family_journal_weekly.py --pull --apply
  ~/selenium_env/venv/bin/python scripts/jarvis_family_journal_weekly.py --pull --apply --auto
  ~/selenium_env/venv/bin/python scripts/jarvis_family_journal_weekly.py --apply --force

正本 Journal: ~/Documents/500_Obsidian_r1/01_Journaling/★Journal/
Notion 親: 子供コーチング配下の「Journal週次」ハブ（無ければ作成）
自動: launchd 日曜 08:00（WeStudy Drive と同刻）＋ RunAtLoad ＋ 朝オープン取りこぼし（--auto）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
FAMILY_YAML = REPO / "config" / "notion_family_coaching.yaml"
STATE_PATH = REPO / ".jarvis_state" / "family_journal_weekly.json"
JOURNAL_ROOT = (
    Path.home() / "Documents" / "500_Obsidian_r1" / "01_Journaling" / "★Journal"
)
OGD_PULL = REPO / "scripts" / "jarvis_obsidian_ogd_pull.py"
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"
NOTION_VERSION = "2022-06-28"
API = "https://api.notion.com/v1"
# WeStudy Drive 添付週次（日曜 08:00）に合わせる。Grok 家族コーチは日曜 21:00
SLOT_HOUR = 8
SLOT_MINUTE = 0
FRI_WEEK_DAYS = 7  # 土〜金

CHILD_KEYWORDS: list[tuple[str, list[str]]] = [
    ("まどか", ["まどか", "円香", "水田"]),
    ("たまき", ["たまき", "珠己", "日能研"]),
    ("さわ", ["さわ", "紗和"]),
]
QOL_KEYWORDS = [
    "睡眠",
    "就寝",
    "起床",
    "朝ルーティン",
    "帰宅",
    "疲れ",
    "QOL",
    "家族会議",
    "塾",
    "受験",
    "勉強",
]
PER_DAY_MAX = 1200
TOTAL_MAX = 7500


def now_jst() -> datetime:
    return datetime.now(JST)


def iso_week_label(d: datetime) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def friday_on_or_before(d: datetime) -> datetime:
    """指定日以前の直近金曜（当日が金曜なら当日）0:00 JST。"""
    d0 = d.replace(hour=0, minute=0, second=0, microsecond=0)
    return d0 - timedelta(days=(d0.weekday() - 4) % 7)


def most_recent_friday(hour: int = 0, minute: int = 0) -> datetime:
    """直近の金曜（今日が金曜なら今日）の指定時刻 JST。"""
    fri = friday_on_or_before(now_jst())
    return fri.replace(hour=hour, minute=minute, second=0, microsecond=0)


def fri_week_label(end_friday: datetime) -> str:
    """金締ラベル（例: 金締-2026-08-22）。"""
    return f"金締-{end_friday.strftime('%Y-%m-%d')}"


def sunday_slot_for_friday(end_friday: datetime) -> datetime:
    """その金締週を投影する日曜 08:00（金曜の2日後）。"""
    sun = end_friday + timedelta(days=2)
    return sun.replace(hour=SLOT_HOUR, minute=SLOT_MINUTE, second=0, microsecond=0)


def _token() -> str:
    tok = (os.environ.get("NOTION_API_TOKEN") or "").strip()
    if not tok:
        print("ERROR: NOTION_API_TOKEN 未設定", file=sys.stderr)
        sys.exit(2)
    return tok


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _req(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{API}{path}", data=data, headers=_headers(), method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", "replace")[:600]
        print(f"ERROR: HTTP {e.code} {path}: {err}", file=sys.stderr)
        sys.exit(1)


def _load_yaml() -> dict[str, Any]:
    import yaml  # type: ignore

    return yaml.safe_load(FAMILY_YAML.read_text(encoding="utf-8")) or {}


def _save_yaml(data: dict[str, Any]) -> None:
    import yaml  # type: ignore

    FAMILY_YAML.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _normalize_id(raw: str) -> str:
    page_id = (raw or "").replace("-", "").strip()
    if len(page_id) == 32:
        return (
            f"{page_id[:8]}-{page_id[8:12]}-{page_id[12:16]}-"
            f"{page_id[16:20]}-{page_id[20:]}"
        )
    return (raw or "").strip()


def pull_journal() -> None:
    if not OGD_PULL.is_file():
        print("WARN: ogd_pull なし · スキップ", file=sys.stderr)
        return
    cmd = [
        str(PY),
        str(OGD_PULL),
        "--prefix",
        "01_Journaling/★Journal",
    ]
    print("# ogd_pull …")
    subprocess.run(cmd, cwd=str(REPO), check=False)


def find_journal_file(day: datetime) -> Path | None:
    ymd = day.strftime("%Y-%m-%d")
    ym = day.strftime("%Y-%m")
    candidates = [
        JOURNAL_ROOT / ym / f"{ymd}.md",
        JOURNAL_ROOT / f"{ymd}.md",
        JOURNAL_ROOT / ym / f"{ymd}.markdown",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def extract_day_digest(text: str, day: datetime) -> dict[str, Any]:
    # Prefer 生ログ section if present
    m = re.search(
        r"##\s*[🎙️🎤]?\s*本日の生ログ[^\n]*\n(.*?)(?=\n##\s|\Z)",
        text,
        re.S,
    )
    body = (m.group(1).strip() if m else text.strip())
    # Drop huge karl review tables noise if we fell back to full text
    if not m and "カール参謀" in text:
        m2 = re.search(r"生ログ[^\n]*\n(.*)", text, re.S)
        if m2:
            body = m2.group(1).strip()
    lines = [ln.rstrip() for ln in body.splitlines() if ln.strip()]
    clipped = "\n".join(lines)
    if len(clipped) > PER_DAY_MAX:
        clipped = clipped[: PER_DAY_MAX - 20].rstrip() + "\n…（省略）"

    children_hit = []
    for name, kws in CHILD_KEYWORDS:
        if any(k in text for k in kws):
            children_hit.append(name)
    qol_hit = [k for k in QOL_KEYWORDS if k in text]
    return {
        "date": day.strftime("%Y-%m-%d"),
        "path": "",
        "chars": len(text),
        "children": children_hit,
        "qol_keywords": qol_hit[:8],
        "excerpt": clipped,
    }


def build_pack(days: int, end: datetime | None = None) -> dict[str, Any]:
    """既定は金締（土〜金）。end は金曜にスナップ（手動 --end も同様）。"""
    raw_end = end or now_jst()
    end_fri = friday_on_or_before(raw_end)
    # days 既定=7 のときは金締固定。明示的に日数を変えたときだけ rolling
    if days == FRI_WEEK_DAYS:
        start = end_fri - timedelta(days=6)
        span = FRI_WEEK_DAYS
        week = fri_week_label(end_fri)
        title = (
            f"Journal週次 {week}（{start.strftime('%Y-%m-%d')}土"
            f"〜{end_fri.strftime('%Y-%m-%d')}金）"
        )
        end = end_fri
    else:
        end = raw_end.replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=days - 1)
        span = days
        week = iso_week_label(end)
        title = (
            f"Journal週次 {week}（{start.strftime('%Y-%m-%d')}〜{end.strftime('%Y-%m-%d')}）"
        )

    day_rows: list[dict[str, Any]] = []
    missing: list[str] = []
    for i in range(span):
        d = start + timedelta(days=i)
        path = find_journal_file(d)
        if not path:
            missing.append(d.strftime("%Y-%m-%d"))
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        row = extract_day_digest(text, d)
        row["path"] = str(path.relative_to(JOURNAL_ROOT.parent.parent))
        day_rows.append(row)

    child_counts: dict[str, int] = {n: 0 for n, _ in CHILD_KEYWORDS}
    for r in day_rows:
        for c in r["children"]:
            child_counts[c] = child_counts.get(c, 0) + 1

    md_parts = [
        f"# {title}",
        "",
        f"更新: {now_jst().strftime('%Y-%m-%d %H:%M JST')} · source: Obsidian ★Journal · Jarvis",
        f"区切り: 土曜始まり〜金曜終わり（金締）。土日後追いログは翌週以降に載ることがある。",
        "",
        "## 週の俯瞰",
        f"- 取得日数: {len(day_rows)} / 対象 {span} 日",
        f"- 欠日: {', '.join(missing) if missing else 'なし'}",
        f"- 子ども言及日数: "
        + " / ".join(f"{k}={v}" for k, v in child_counts.items()),
        "",
        "## 統括への依頼（テンプレ）",
        "- 今週の Journal 傾向を見て、まどか／たまき／さわ／マサハルQOL の優先を1つずつ提案してください。",
        "- Notion の直近「家族会議」と突き合わせてください。",
        "",
    ]
    for r in day_rows:
        tags = []
        if r["children"]:
            tags.append("子ども:" + ",".join(r["children"]))
        if r["qol_keywords"]:
            tags.append("QOL:" + ",".join(r["qol_keywords"][:5]))
        tag_s = " · ".join(tags) if tags else "（タグなし）"
        md_parts.append(f"## {r['date']}")
        md_parts.append(f"- {tag_s}")
        md_parts.append("")
        md_parts.append(r["excerpt"])
        md_parts.append("")

    body = "\n".join(md_parts)
    if len(body) > TOTAL_MAX:
        body = body[: TOTAL_MAX - 30].rstrip() + "\n\n…（全体省略）"

    return {
        "week": week,
        "title": title,
        "start": start.strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
        "days_found": len(day_rows),
        "missing": missing,
        "child_counts": child_counts,
        "markdown": body,
        "end_friday": end_fri.strftime("%Y-%m-%d"),
        "day_rows": [
            {k: v for k, v in r.items() if k != "excerpt"} for r in day_rows
        ],
    }


def _rich_text(content: str) -> list[dict[str, Any]]:
    # Notion rich_text limit 2000 per item
    chunks: list[dict[str, Any]] = []
    s = content or ""
    while s:
        part, s = s[:1900], s[1900:]
        chunks.append({"type": "text", "text": {"content": part}})
    return chunks or [{"type": "text", "text": {"content": ""}}]


def markdown_to_blocks(md: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for raw in md.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if line.startswith("# "):
            blocks.append(
                {
                    "object": "block",
                    "type": "heading_1",
                    "heading_1": {"rich_text": _rich_text(line[2:].strip())},
                }
            )
        elif line.startswith("## "):
            blocks.append(
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {"rich_text": _rich_text(line[3:].strip())},
                }
            )
        elif line.startswith("- "):
            blocks.append(
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": _rich_text(line[2:].strip())},
                }
            )
        else:
            blocks.append(
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": _rich_text(line)},
                }
            )
    return blocks


def list_child_pages(parent_id: str) -> list[dict[str, str]]:
    parent_id = _normalize_id(parent_id)
    out: list[dict[str, str]] = []
    cursor = None
    while True:
        q = f"/blocks/{parent_id}/children?page_size=100"
        if cursor:
            q += f"&start_cursor={cursor}"
        data = _req("GET", q)
        for b in data.get("results") or []:
            if b.get("type") == "child_page":
                out.append(
                    {
                        "id": b["id"],
                        "title": (b.get("child_page") or {}).get("title") or "",
                    }
                )
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return out


def ensure_journal_hub(coaching_hub_id: str, cfg: dict[str, Any]) -> str:
    existing = (cfg.get("journal_weekly_hub_page_id") or "").strip()
    if existing:
        return _normalize_id(existing)
    for ch in list_child_pages(coaching_hub_id):
        if ch["title"] == "Journal週次":
            cfg["journal_weekly_hub_page_id"] = ch["id"]
            cfg["journal_weekly_hub_page_url"] = (
                f"https://app.notion.com/p/{ch['id'].replace('-', '')}"
            )
            return ch["id"]
    created = _req(
        "POST",
        "/pages",
        {
            "parent": {"page_id": _normalize_id(coaching_hub_id)},
            "properties": {
                "title": {
                    "title": [{"type": "text", "text": {"content": "Journal週次"}}]
                }
            },
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": _rich_text(
                            "Jarvis が週1で Obsidian ★Journal 要約を子ページに置くハブ。"
                            "Grok 家族コーチ統括が読む想定。"
                        )
                    },
                }
            ],
        },
    )
    pid = created["id"]
    cfg["journal_weekly_hub_page_id"] = pid
    cfg["journal_weekly_hub_page_url"] = created.get("url") or (
        f"https://app.notion.com/p/{pid.replace('-', '')}"
    )
    print(f"# created Journal週次 hub: {pid}")
    return pid


def find_week_page(hub_id: str, title: str) -> str | None:
    for ch in list_child_pages(hub_id):
        if ch["title"] == title:
            return ch["id"]
    return None


def clear_page_blocks(page_id: str) -> None:
    page_id = _normalize_id(page_id)
    cursor = None
    while True:
        q = f"/blocks/{page_id}/children?page_size=100"
        if cursor:
            q += f"&start_cursor={cursor}"
        data = _req("GET", q)
        for b in data.get("results") or []:
            bid = b.get("id")
            if bid:
                _req("DELETE", f"/blocks/{bid}")
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")


def append_blocks(page_id: str, blocks: list[dict[str, Any]]) -> None:
    page_id = _normalize_id(page_id)
    for i in range(0, len(blocks), 90):
        chunk = blocks[i : i + 90]
        _req("PATCH", f"/blocks/{page_id}/children", {"children": chunk})


def upsert_week_page(hub_id: str, pack: dict[str, Any]) -> dict[str, Any]:
    title = pack["title"]
    blocks = markdown_to_blocks(pack["markdown"])
    existing = find_week_page(hub_id, title)
    if existing:
        clear_page_blocks(existing)
        append_blocks(existing, blocks)
        page = _req("GET", f"/pages/{_normalize_id(existing)}")
        return {
            "page_id": existing,
            "url": page.get("url") or "",
            "created": False,
            "title": title,
        }
    created = _req(
        "POST",
        "/pages",
        {
            "parent": {"page_id": _normalize_id(hub_id)},
            "properties": {
                "title": {"title": [{"type": "text", "text": {"content": title[:200]}}]}
            },
            "children": blocks[:90],
        },
    )
    pid = created["id"]
    if len(blocks) > 90:
        append_blocks(pid, blocks[90:])
    return {
        "page_id": pid,
        "url": created.get("url") or "",
        "created": True,
        "title": title,
    }


def load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def most_recent_sunday(hour: int = 0, minute: int = 0) -> datetime:
    """直近の日曜（今日が日曜なら今日）の指定時刻 JST。"""
    now = now_jst()
    days_since_sun = (now.weekday() + 1) % 7
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0) - timedelta(
        days=days_since_sun
    )


def parse_state_ts(raw: str) -> datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(JST)
    except ValueError:
        try:
            return datetime.strptime(raw[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=JST)
        except ValueError:
            return None


def auto_should_skip() -> tuple[bool, str]:
    """launchd / 朝取りこぼし用。金締週を日曜08:00以降に成功していればスキップ。"""
    if os.environ.get("JARVIS_FAMILY_JOURNAL_WEEKLY_DISABLE") == "1":
        return True, "JARVIS_FAMILY_JOURNAL_WEEKLY_DISABLE=1"
    state = load_state()
    if state.get("disabled") is True:
        return True, "state.disabled"
    end_fri = most_recent_friday(0, 0)
    week = fri_week_label(end_fri)
    slot_done = sunday_slot_for_friday(end_fri)
    now = now_jst()
    if now < slot_done:
        return True, f"before Sunday slot {slot_done.strftime('%Y-%m-%d %H:%M')}"
    if not state.get("page_id") or state.get("last_ok") is False:
        return False, ""
    if str(state.get("week") or "") != week:
        return False, ""
    ts = parse_state_ts(str(state.get("last_success_at") or ""))
    if ts is None:
        return False, ""
    if ts >= slot_done:
        return True, f"already ok since slot {slot_done.strftime('%Y-%m-%d %H:%M')}"
    return False, ""


def save_state(
    pack: dict[str, Any],
    page: dict[str, Any] | None,
    *,
    last_ok: bool | None = None,
) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    prev = load_state()
    ok = True if last_ok is None else last_ok
    now = now_jst()
    applied = bool(page and page.get("page_id"))
    STATE_PATH.write_text(
        json.dumps(
            {
                "updated_at": now.isoformat(),
                "last_success_at": (
                    now.isoformat()
                    if applied and ok
                    else prev.get("last_success_at")
                ),
                "last_ok": ok if applied else prev.get("last_ok"),
                "week": pack["week"],
                "title": pack["title"],
                "end_friday": pack.get("end_friday"),
                "days_found": pack["days_found"],
                "missing": pack["missing"],
                "page_id": (page or {}).get("page_id") or prev.get("page_id"),
                "url": (page or {}).get("url") or prev.get("url"),
                "disabled": prev.get("disabled", False),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=FRI_WEEK_DAYS)
    ap.add_argument("--pull", action="store_true", help="OGD Pull してから実行")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true", help="Notion に作成／更新")
    ap.add_argument(
        "--end",
        default="",
        help="終了日 YYYY-MM-DD（金にスナップ。既定=直近金曜）",
    )
    ap.add_argument("--print-md", action="store_true", help="要約 MD を stdout")
    ap.add_argument(
        "--auto",
        action="store_true",
        help="launchd／朝取りこぼし用。金締パック＋日曜08:00成功済みならスキップ",
    )
    ap.add_argument("--force", action="store_true", help="--auto のスキップを無視")
    args = ap.parse_args()

    if args.auto and not args.force:
        skip, reason = auto_should_skip()
        if skip:
            print(f"# skip: {reason}", flush=True)
            return 0

    if args.pull:
        pull_journal()

    end = None
    if args.end.strip():
        end = datetime.strptime(args.end.strip(), "%Y-%m-%d").replace(tzinfo=JST)
    else:
        end = most_recent_friday(0, 0)

    pack = build_pack(args.days, end)
    print(
        f"📎 Journal週次パック {pack['week']} · {pack['start']}〜{pack['end']} · "
        f"{pack['days_found']}日 · 欠日={pack['missing'] or 'なし'}"
    )
    print(f"  子ども言及日数: {pack['child_counts']}")
    if args.print_md or args.dry_run:
        print("--- markdown ---")
        print(pack["markdown"][:4000])
        if len(pack["markdown"]) > 4000:
            print("…")

    if not args.apply:
        if not args.dry_run:
            print("# --apply で Notion 反映。--dry-run で MD 確認可")
        # dry-run / プレビューでは state を触らない（誤スキップ防止）
        return 0

    try:
        cfg = _load_yaml()
        hub_parent = cfg.get("coaching_hub_page_id") or ""
        if not hub_parent:
            print("ERROR: coaching_hub_page_id が YAML に無い", file=sys.stderr)
            save_state(pack, None, last_ok=False)
            return 2
        hub_id = ensure_journal_hub(hub_parent, cfg)
        # persist hub id if newly found/created
        if cfg.get("journal_weekly_hub_page_id"):
            # keep existing yaml comments: rewrite carefully via patch keys only
            text = FAMILY_YAML.read_text(encoding="utf-8")
            if "journal_weekly_hub_page_id" not in text:
                insert = (
                    f'\njournal_weekly_hub_page_id: "{cfg["journal_weekly_hub_page_id"]}"\n'
                    f'journal_weekly_hub_page_url: "{cfg.get("journal_weekly_hub_page_url", "")}"\n'
                    f'journal_weekly_note: "Jarvis 週次 · Obsidian ★Journal 要約。Grok 家族コーチが読む"\n'
                )
                # after coaching_hub_title line
                if "coaching_hub_title:" in text:
                    text = text.replace(
                        "coaching_hub_title: 子供コーチング\n",
                        "coaching_hub_title: 子供コーチング\n" + insert.lstrip("\n"),
                        1,
                    )
                    FAMILY_YAML.write_text(text, encoding="utf-8")
                else:
                    _save_yaml(cfg)

        page = upsert_week_page(hub_id, pack)
        save_state(pack, page, last_ok=True)
        print(
            f"✅ Notion {'作成' if page['created'] else '更新'}: {page['title']}\n"
            f"   {page.get('url') or page['page_id']}"
        )
        print(
            "📎 Grok向け: 子供コーチング → Journal週次 → 上記ページを Notion プラグインで開いてください"
        )
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        save_state(pack, None, last_ok=False)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
