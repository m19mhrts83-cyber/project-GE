#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""家族会議・週次（FRIDAY / 715 家族会議週次係）。

松野さんが前週ページを複製して当日ページ `(YYYY/MM/DD)` を用意した前提で、
会議終了後（日曜 21:30）に次を順番どおり実行する。

  1. Genspark AI Meeting Notes（Speakly 同一ストア）から当該週の会議を取得
  2. 議事録 MD を Drive `13_家族会議_週次/議事録/` へ保存（NLM ソース用）
  3. NotebookLM「家族会議」1ノートへソース追加
  4. Studio で週次インフォグラフィックを生成（当該週議事録のみ参照）
  5. Notion 当日ページ末尾へ「インフォ → 議事録要約」の順で挿入
  6. Slack #report（成功）／#ops（失敗）

ページの複製・アジェンダ編集はしない（松野さん担当）。
再実行しても二重挿入しない（見出しで判定）。使用量制限などで失敗したら
状態を pending に残し、月曜朝の --retry で再試行する。

例:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  export PATH="$HOME/.local/bin:$HOME/.genspark-tool-cli/bin:$PATH"

  ~/selenium_env/venv/bin/python scripts/friday_family_meeting_weekly.py --dry-run
  ~/selenium_env/venv/bin/python scripts/friday_family_meeting_weekly.py --date 2026-10-18
  ~/selenium_env/venv/bin/python scripts/friday_family_meeting_weekly.py --retry
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import date as Date
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import friday_notion_ops as nops  # noqa: E402
import jarvis_family_meeting_weekly as fmw  # noqa: E402
import jarvis_genspark_meeting_fetch as gsk  # noqa: E402

FAMILY_YAML = REPO / "config" / "notion_family_coaching.yaml"
STUDIO_YAML = REPO / "config" / "notebooklm_studio.yaml"
STATE_PATH = REPO / ".jarvis_state" / "friday_family_meeting_weekly.json"
LOCK_PATH = REPO / ".jarvis_state" / "friday_family_meeting_weekly.lock"
PY = Path(sys.executable)
JST = timezone(timedelta(hours=9))

FAMILY_HINTS = (
    "家族",
    "円香",
    "珠己",
    "紗和",
    "まどか",
    "たまき",
    "さわ",
    "チケット",
    "家事",
    "試験",
    "勉強",
    "宿題",
    "子ども",
    "子供",
)
BUSINESS_HINTS = (
    "不動産",
    "物件",
    "賃貸",
    "管理会社",
    "業務",
    "営業",
    "事業",
    "開発",
    "人員",
    "会場",
    "設備",
    "投資",
    "報道",
    "パートナー",
    "会議総括",
    "長時間",
    "長時間",
)

DEFAULT_ALIASES = {
    "さあちゃん": "さわ",
    "さーちゃん": "さわ",
    "まーくん": "たまき",
}

# 複製で残る旧週の見出し（当該週以外を削除してから挿入する）
WEEKLY_HEADING_RE = re.compile(
    r"^(週次インフォグラフィック|Genspark 議事録要約)（(\d{4}-\d{2}-\d{2})）"
)


# --------------------------------------------------------------------------
# 設定・状態
# --------------------------------------------------------------------------
def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def settings() -> dict[str, Any]:
    family = load_yaml(FAMILY_YAML)
    studio = load_yaml(STUDIO_YAML)
    auto = family.get("automation") if isinstance(family.get("automation"), dict) else {}
    notebooks = studio.get("notebooks") if isinstance(studio.get("notebooks"), dict) else {}
    key = str(auto.get("notebook_key") or "family_meeting_weekly")
    nb = notebooks.get(key) if isinstance(notebooks.get(key), dict) else {}
    return {
        "hub_page_id": str(family.get("root_page_id") or ""),
        "notebook_key": key,
        "notebook_url": str(nb.get("url") or ""),
        "drive_folder": str(nb.get("drive_folder") or auto.get("drive_folder") or "13_家族会議_週次"),
        "prompt_file": str(
            auto.get("prompt_file")
            or nb.get("revise_prompt")
            or "docs/N1_NotebookLM/13_家族会議_週次/Studioプロンプト_家族会議_週次インフォ.md"
        ),
        "keyword": str(auto.get("keyword") or "家族会議"),
        "aliases": {**DEFAULT_ALIASES, **(auto.get("speaker_aliases") or {})},
        "window_start": int(auto.get("window_start_hour") or 17),
        "window_end": int(auto.get("window_end_hour") or 24),
    }


def load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"version": 1, "dates": {}}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "dates": {}}
    if not isinstance(data, dict):
        return {"version": 1, "dates": {}}
    data.setdefault("version", 1)
    data.setdefault("dates", {})
    return data


def entry_for(state: dict[str, Any], iso: str) -> dict[str, Any]:
    dates = state.setdefault("dates", {})
    ent = dates.get(iso)
    if not isinstance(ent, dict):
        ent = {}
        dates[iso] = ent
    return ent


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATE_PATH)


class lock:
    def __init__(self, path: Path):
        self.path = path
        self.fh = None

    def __enter__(self) -> "lock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = self.path.open("w")
        try:
            fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.fh.close()
            self.fh = None
            raise SystemExit("既に実行中です（lock）")
        return self

    def __exit__(self, *exc: Any) -> None:
        if self.fh:
            fcntl.flock(self.fh, fcntl.LOCK_UN)
            self.fh.close()
            self.fh = None


# --------------------------------------------------------------------------
# 日付・会議
# --------------------------------------------------------------------------
def latest_sunday(today: Date | None = None) -> Date:
    d = today or Date.today()
    # Python: Monday=0 ... Sunday=6
    return d - timedelta(days=(d.weekday() - 6) % 7)


def parse_date(raw: str | None) -> Date:
    if not raw:
        return latest_sunday()
    s = raw.strip().replace("/", "-")
    if re.fullmatch(r"\d{8}", s):
        return Date(int(s[:4]), int(s[4:6]), int(s[6:]))
    return Date.fromisoformat(s)


def _parse_created(raw: str) -> datetime | None:
    s = (raw or "").strip().replace("Z", "+00:00")
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(JST)


def _jst_date(raw: str) -> Date | None:
    dt = _parse_created(raw)
    return dt.date() if dt else None


def _hours(raw: str) -> int | None:
    dt = _parse_created(raw)
    return dt.hour if dt else None


def _score(note: dict[str, Any], shaped: dict[str, Any] | None, s: dict[str, Any]) -> int:
    title = str((shaped or note).get("title") or "")
    summary = str((shaped or {}).get("summary") or "")
    hay = f"{title}\n{summary}"
    score = 0
    if any(h in hay for h in FAMILY_HINTS):
        score += 10
    if any(h in title for h in FAMILY_HINTS):
        score += 6
    if any(h in title for h in BUSINESS_HINTS) and not any(h in title for h in FAMILY_HINTS):
        score -= 12
    hour = _hours(str(note.get("created_at") or ""))
    if hour is not None and s["window_start"] <= hour < s["window_end"]:
        score += 6
    dur = shaped.get("duration_seconds") if shaped else note.get("duration_seconds")
    try:
        score += min(int(float(dur or 0)) // 600, 6)
    except (TypeError, ValueError):
        pass
    return score


def find_meeting(target: Date, s: dict[str, Any]) -> dict[str, Any]:
    """Search a 3-day window and pick the family-meeting candidate."""
    date_from = (target - timedelta(days=1)).isoformat()
    date_to = (target + timedelta(days=1)).isoformat()
    raw = gsk.run_gsk(
        [
            "search",
            "--keyword",
            s["keyword"],
            "--date_from",
            date_from,
            "--date_to",
            date_to,
            "--page_size",
            "30",
        ]
    )
    notes = (gsk.shape_list_or_search(raw).get("notes") or [])
    same_day = [n for n in notes if _jst_date(str(n.get("created_at") or "")) == target]
    if not same_day:
        # list fallback（search が内容一致で拾えない場合）
        raw = gsk.run_gsk(["list", "--page_size", "50"])
        notes = (gsk.shape_list_or_search(raw).get("notes") or [])
        same_day = [n for n in notes if _jst_date(str(n.get("created_at") or "")) == target]
    if not same_day:
        raise SystemExit(
            f"{target} の会議が見つかりません。Genspark の録音・議事録を確認するか "
            f"--meeting-id で指定してください。"
        )

    best: tuple[int, dict[str, Any]] | None = None
    for n in same_day:
        mid = n.get("id")
        if not mid:
            continue
        try:
            shaped = gsk.shape_get(
                gsk.run_gsk(["get", "--task_id", str(mid), "--detail_level", "full"]),
                "full",
            )
        except SystemExit:
            shaped = None
        sc = _score(n, shaped, s)
        if best is None or sc > best[0]:
            best = (sc, shaped or n)
    if best is None:
        raise SystemExit("会議 ID を特定できませんでした")
    shaped = best[1]
    shaped.setdefault("candidate_count", len(same_day))
    shaped.setdefault("score", best[0])
    return shaped


# --------------------------------------------------------------------------
# 議事録 MD
# --------------------------------------------------------------------------
def correct_text(text: str, aliases: dict[str, str]) -> tuple[str, list[str]]:
    used: list[str] = []
    out = text
    # 長いキーから置換（部分一致の取り違え防止）
    for key in sorted(aliases, key=len, reverse=True):
        alias = str(aliases[key])
        if not key or key == alias:
            continue
        count = out.count(key)
        if count:
            out = out.replace(key, alias)
            used.append(f"{key}→{alias}×{count}")
    return out, used


def build_minutes_md(
    shaped: dict[str, Any],
    target: Date,
    aliases: dict[str, str],
    *,
    dry_run: bool = False,
) -> tuple[Path, str, list[str]]:
    raw_md = fmw.meeting_to_markdown(shaped)
    md, used = correct_text(raw_md, aliases)
    stamp = target.strftime("%Y%m%d")
    if dry_run:
        dest = Path("/tmp") / f"{stamp}_家族会議_Genspark議事録.md"
    else:
        dest = fmw.resolve_drive_minutes_dir() / f"{stamp}_家族会議_Genspark議事録.md"
    dest.write_text(md, encoding="utf-8")
    return dest, md, used


def summary_for_notion(shaped: dict[str, Any], aliases: dict[str, str]) -> tuple[str, list[str]]:
    summary = shaped.get("summary") or ""
    if not isinstance(summary, str):
        summary = json.dumps(summary, ensure_ascii=False, indent=2)
    out, used = correct_text(summary.strip(), aliases)
    # 実名へ直せなかった話者ラベルは、勝手に推測せず要確認として残す（Jarvis回答 2026-10-19）
    if re.search(r"(?:Speaker|スピーカー)\s*\d+", out):
        used.append("Speaker N が残存（実名補正は要確認）")
    return out, used


# --------------------------------------------------------------------------
# NotebookLM / Studio
# --------------------------------------------------------------------------
def _run(cmd: list[str], *, timeout: int, label: str) -> None:
    print(f"# {label}: {' '.join(cmd[:4])} …", file=sys.stderr)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-12:]
        raise RuntimeError(f"{label} failed exit={proc.returncode}: " + " / ".join(tail))
    tail = (proc.stdout or "").strip().splitlines()[-3:]
    for line in tail:
        print(f"# {label}: {line}", file=sys.stderr)


def add_notebook_source(md_path: Path, s: dict[str, Any]) -> None:
    _run(
        [
            str(PY),
            str(REPO / "scripts/jarvis_notebooklm_add_source.py"),
            "--notebook-url",
            s["notebook_url"],
            "--file",
            str(md_path),
        ],
        timeout=600,
        label="NotebookLM source",
    )


def generate_infographic(target: Date, s: dict[str, Any]) -> Path:
    stem = f"{target.strftime('%Y%m%d')}_家族会議_週次インフォ"
    prompt = REPO / s["prompt_file"]
    if not prompt.is_file():
        raise RuntimeError(f"Studio プロンプトがありません: {prompt}")
    _run(
        [
            str(PY),
            str(REPO / "scripts/jarvis_notebooklm_studio_run.py"),
            "--notebook-key",
            s["notebook_key"],
            "--artifact",
            "infographic",
            "--mode",
            "create",
            "--prompt-file",
            str(prompt),
            "--prompt-section",
            "full",
            "--confirm-generate",
            "--wait-and-save",
            "--output-name",
            stem,
        ],
        timeout=1800,
        label="Studio infographic",
    )

    out_dir = fmw.DRIVE_ROOT / s["drive_folder"] / "★アウトプット"
    candidates: list[Path] = []
    for ext in (".png", ".pdf"):
        candidates.extend(out_dir.glob(f"{stem}*{ext}"))
    if not candidates:
        downloads = Path.home() / "Downloads"
        for ext in (".png", ".pdf"):
            candidates.extend(downloads.glob(f"{stem}*{ext}"))
    if not candidates:
        raise RuntimeError(f"インフォ出力が見つかりません: {out_dir}/{stem}*")
    newest = max(candidates, key=lambda p: p.stat().st_mtime)
    if newest.suffix.lower() == ".pdf":
        png = newest.with_suffix(".png")
        _pdf_to_png(newest, png)
        newest = png
    return newest


def _pdf_to_png(pdf: Path, png: Path) -> None:
    try:
        import fitz  # type: ignore
    except ImportError as e:
        raise RuntimeError("PDF→PNG には PyMuPDF(fitz) が必要です") from e
    doc = fitz.open(str(pdf))
    page = doc.load_page(0)
    pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
    pix.save(str(png))
    doc.close()


# --------------------------------------------------------------------------
# Notion 挿入
# --------------------------------------------------------------------------
def cleanup_old_weekly_sections(
    page_id: str, target_iso: str, *, dry_run: bool
) -> list[dict[str, Any]]:
    """前週複製で残った旧週の『インフォ／議事録要約』を削除する。

    当該週（target_iso）の見出しは残す（再実行時の二重挿入防止）。
    旧見出しから次の heading_1/2 までを1かたまりとして消す。
    直前に divider があれば一緒に消す。
    """
    kids = nops.list_children(page_id)
    if not dry_run:
        backup_dir = REPO / ".jarvis_state" / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / f"family_meeting_{target_iso}_before.json").write_text(
            json.dumps(kids, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    doomed: dict[int, dict[str, Any]] = {}
    i = 0
    while i < len(kids):
        b = kids[i]
        if b.get("type") != "heading_2":
            i += 1
            continue
        text = nops.plain_text(b).strip()
        m = WEEKLY_HEADING_RE.match(text)
        is_old = False
        if m:
            is_old = m.group(2) != target_iso
        elif text.startswith(("週次インフォグラフィック", "Genspark 議事録要約")):
            is_old = True  # 日付なしの旧形式
        if not is_old:
            i += 1
            continue

        if i > 0 and kids[i - 1].get("type") == "divider":
            doomed[i - 1] = kids[i - 1]
        j = i
        while j < len(kids):
            if j > i and kids[j].get("type") in ("heading_1", "heading_2"):
                break
            doomed[j] = kids[j]
            j += 1
        i = j

    removed = [
        {"index": idx, "type": b.get("type"), "text": nops.plain_text(b).strip()[:80]}
        for idx, b in sorted(doomed.items())
    ]
    if dry_run:
        return removed
    for idx, b in sorted(doomed.items()):
        nops.delete_block(b["id"])
        time.sleep(0.2)
    return removed


def insert_into_notion(
    target: Date,
    shaped: dict[str, Any],
    summary_md: str,
    corrections: list[str],
    infographic_png: Path,
    s: dict[str, Any],
    *,
    dry_run: bool,
) -> dict[str, Any]:
    page = nops.find_dated_child(
        s["hub_page_id"], target.year, target.month, target.day
    )
    if not page:
        raise RuntimeError(
            f"Notion に ({target.year:04d}/{target.month:02d}/{target.day:02d}) のページがありません。"
            " 先に前週ページを複製して日付を変えてください。"
        )
    iso = target.isoformat()
    removed = cleanup_old_weekly_sections(page["id"], iso, dry_run=dry_run)
    info_heading = f"週次インフォグラフィック（{iso}）"
    minutes_heading = f"Genspark 議事録要約（{iso}）"
    have_info = nops.has_heading(page["id"], info_heading)
    have_min = nops.has_heading(page["id"], minutes_heading)

    blocks: list[dict[str, Any]] = []
    upload_id = ""
    if not have_info:
        blocks.append(nops.divider())
        blocks.append(nops.heading_2(info_heading))
        if dry_run:
            blocks.append(nops.paragraph(f"[dry-run] image: {infographic_png.name}"))
        else:
            upload_id = nops.upload_file(infographic_png)
            blocks.append(nops.image_block(upload_id, caption=infographic_png.stem))
    if not have_min:
        blocks.append(nops.divider())
        blocks.append(nops.heading_2(minutes_heading))
        title = str(shaped.get("title") or "家族会議")
        dur = str(shaped.get("duration_human") or "—")
        pid = str(shaped.get("project_id") or "")
        share = (
            f"https://www.genspark.ai/meetingnotes/SharedMeetingNotes?id={pid}"
            if pid
            else ""
        )
        blocks.append(nops.bullet(f"タイトル: {title}"))
        meta = f"時間: {dur}"
        if share:
            meta += f" / 共有: {share}"
        blocks.append(nops.bullet(meta))
        blocks.append(nops.bullet(f"Meeting ID: {shaped.get('id') or '—'}"))
        if corrections:
            blocks.append(nops.bullet("注: " + "、".join(corrections) + "（自動補正・要確認）"))
        blocks.extend(nops.md_to_blocks(summary_md))

    inserted = 0
    if blocks and not dry_run:
        inserted = nops.append_blocks(page["id"], blocks)
    return {
        "page_id": page["id"],
        "page_title": page["title"],
        "page_url": nops.page_url(page["id"]),
        "have_info": have_info,
        "have_minutes": have_min,
        "removed_old": removed,
        "blocks": len(blocks),
        "inserted": inserted,
        "upload_id": upload_id,
        "dry_run": dry_run,
    }


# --------------------------------------------------------------------------
# Slack
# --------------------------------------------------------------------------
def slack(channel: str, text: str) -> None:
    try:
        subprocess.run(
            [
                str(PY),
                str(REPO / "scripts/jarvis_slack_webhook_post.py"),
                "--channel",
                channel,
                "--username",
                "FRIDAY 715",
                "--text",
                text,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except Exception as e:
        print(f"# slack soft-fail: {e}", file=sys.stderr)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def run(args: argparse.Namespace) -> int:
    if (os.environ.get("FRIDAY_FAMILY_MEETING_WEEKLY_DISABLE") or "").strip() == "1":
        print("# disabled by FRIDAY_FAMILY_MEETING_WEEKLY_DISABLE=1", file=sys.stderr)
        return 0
    s = settings()
    family = load_yaml(FAMILY_YAML)
    auto = family.get("automation") if isinstance(family.get("automation"), dict) else {}
    if auto.get("enabled") is False:
        print("# disabled by automation.enabled=false", file=sys.stderr)
        return 0
    if not s["hub_page_id"] or not s["notebook_url"]:
        raise SystemExit("設定不足: root_page_id / notebook url を確認してください")

    state = load_state()
    target = parse_date(args.date)
    iso = target.isoformat()
    ent = entry_for(state, iso)

    if args.retry and ent.get("status") == "done":
        print(f"# {iso} は完了済み。retry 不要", file=sys.stderr)
        return 0

    shaped: dict[str, Any]
    if args.meeting_id:
        shaped = gsk.shape_get(
            gsk.run_gsk(["get", "--task_id", args.meeting_id, "--detail_level", "full"]),
            "full",
        )
    else:
        shaped = find_meeting(target, s)

    mid = str(shaped.get("id") or "")
    print(f"# meeting: {mid} {shaped.get('title')}", file=sys.stderr)
    print(f"# created_at(UTC): {shaped.get('created_at')} duration={shaped.get('duration_human')}", file=sys.stderr)

    md_path, _raw_md, corrections = build_minutes_md(
        shaped, target, s["aliases"], dry_run=args.dry_run
    )
    summary_md, _ = summary_for_notion(shaped, s["aliases"])
    print(f"# minutes: {md_path} corrections={corrections}", file=sys.stderr)

    ent.update(
        {
            "meeting_id": mid,
            "meeting_title": shaped.get("title"),
            "created_at": shaped.get("created_at"),
            "md_path": str(md_path),
            "corrections": corrections,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    if args.dry_run:
        page = nops.find_dated_child(s["hub_page_id"], target.year, target.month, target.day)
        blocks = nops.md_to_blocks(summary_md)
        removed = (
            cleanup_old_weekly_sections(page["id"], iso, dry_run=True) if page else []
        )
        plan = {
            "date": iso,
            "meeting": {"id": mid, "title": shaped.get("title"), "score": shaped.get("score")},
            "minutes_md": str(md_path),
            "corrections": corrections,
            "notebook_url": s["notebook_url"],
            "page": page,
            "removed_old_blocks": removed,
            "summary_blocks": len(blocks),
            "summary_head": blocks[:6],
        }
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    try:
        if not args.skip_source and not ent.get("source_added"):
            add_notebook_source(md_path, s)
            ent["source_added"] = True
            save_state(state)

        if not args.skip_infographic and not ent.get("infographic_png"):
            png = generate_infographic(target, s)
            ent["infographic_png"] = str(png)
            save_state(state)

        png_path = Path(str(ent.get("infographic_png") or ""))
        if not png_path.is_file():
            raise RuntimeError(f"インフォ画像がありません: {png_path}")

        result = insert_into_notion(
            target, shaped, summary_md, corrections, png_path, s, dry_run=False
        )
        ent["notion"] = result
        ent["notion_inserted"] = bool(result["have_info"] and result["have_minutes"]) or result["inserted"] > 0
        ent["status"] = "done"
        ent["updated_at"] = datetime.now(timezone.utc).isoformat()
        ent.pop("error", None)
        save_state(state)

        slack(
            "report",
            f"【報告】715 家族会議週次 {iso}\n"
            f"- 会議: {shaped.get('title')}（{shaped.get('duration_human')}）\n"
            f"- Notion: {result['page_url']}\n"
            f"- 挿入: インフォ{'済' if not result['have_info'] else '既存'} → 議事録{'済' if not result['have_minutes'] else '既存'}"
            f"（{result['inserted']} blocks）\n"
            f"- 補正: {'、'.join(corrections) if corrections else 'なし'}\n"
            f"- 次回: 日曜21:30 自動",
        )
        print(f"# done page={result['page_url']} blocks={result['inserted']}", file=sys.stderr)
        return 0
    except Exception as e:
        ent["status"] = "pending"
        ent["error"] = str(e)
        ent["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_state(state)
        slack(
            "ops",
            f"【ops】715 家族会議週次 {iso} 失敗\n"
            f"- 会議: {shaped.get('title')}（{mid}）\n"
            f"- エラー: {str(e)[:400]}\n"
            f"- 済: source={bool(ent.get('source_added'))} infographic={bool(ent.get('infographic_png'))}\n"
            f"- 次: 月曜07:00 自動リトライ → だめなら FRIDAY が手当て",
        )
        print(f"# FAILED: {e}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="家族会議・週次（FRIDAY/715）")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD（既定: 直近の日曜）")
    ap.add_argument("--meeting-id", default=None, help="Genspark meeting task id")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--retry", action="store_true", help="未完了の直近日曜のみ実行")
    ap.add_argument("--skip-source", action="store_true")
    ap.add_argument("--skip-infographic", action="store_true")
    args = ap.parse_args(argv)

    with lock(LOCK_PATH):
        try:
            return run(args)
        except SystemExit as e:
            msg = str(e)
            if "既に実行中" in msg:
                return 0
            target = parse_date(args.date)
            slack("ops", f"【ops】715 家族会議週次 {target.isoformat()} 停止\n- 理由: {msg[:400]}")
            print(f"# STOP: {msg}", file=sys.stderr)
            return 1
        except Exception as e:  # noqa: BLE001
            target = parse_date(args.date)
            slack(
                "ops",
                f"【ops】715 家族会議週次 {target.isoformat()} 失敗\n"
                f"- エラー: {str(e)[:400]}\n- 次: 月曜07:00 自動リトライ → だめなら FRIDAY 手当て",
            )
            print(f"# FAILED: {e}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
