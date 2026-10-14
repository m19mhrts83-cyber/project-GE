#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""211 返信案内下書き係 — 管理会社向け朝便（正本下書き＋Slack報告）.

Phase2: 管理会社101〜104横断・見積B分岐・古い候補の自動起案抑制。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_reply_draft_211.py --scan
  ~/selenium_env/venv/bin/python scripts/jarvis_reply_draft_211.py --morning
  ~/selenium_env/venv/bin/python scripts/jarvis_reply_draft_211.py --morning --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

PM_FOLDER_PREFIXES = ("101_", "102_", "103_", "104_")
ESTIMATE_RE = re.compile(r"(退去|原状回復|修繕費|見積|請求|精算)")
B_NAME_RE = re.compile(r"(提示用|見積B|見積_B|_B_|退去者提示)", re.I)
JST = ZoneInfo("Asia/Tokyo")


def _partner_base() -> Path:
    for key in ("YORITOORI_BASE_PATH", "YORITOORI_PARTNER_BASE"):
        env = (os.environ.get(key) or "").strip()
        if env:
            p = Path(env).expanduser()
            if p.is_dir() or key == "YORITOORI_BASE_PATH":
                return p
    return Path.home() / (
        "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/"
        "C2_ルーティン作業/26_パートナー社への相談"
    )


def _is_pm_folder(folder: str) -> bool:
    return any((folder or "").startswith(p) for p in PM_FOLDER_PREFIXES)


def _parse_received(s: str) -> datetime | None:
    s = (s or "").strip()
    for fmt in ("%Y/%m/%d %H:%M", "%Y/%m/%d", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[: len(fmt) + 2], fmt).replace(tzinfo=JST)
        except ValueError:
            continue
    m = re.match(r"(\d{4})/(\d{2})/(\d{2})", s)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=JST)
    return None


def _run_night_triage(skip_fetch: bool, dry_run: bool, limit: int) -> int:
    cmd = [
        sys.executable,
        str(REPO / "scripts" / "jarvis_night_triage.py"),
        "--lane",
        "partner",
        "--limit",
        str(limit),
    ]
    if skip_fetch:
        cmd.append("--skip-fetch")
    if dry_run:
        cmd.append("--dry-run")
    print("# run:", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(REPO))


def _load_queue() -> dict:
    qpath = REPO / ".jarvis_state" / "night_triage" / "queue.json"
    if not qpath.is_file():
        return {"items": []}
    return json.loads(qpath.read_text(encoding="utf-8"))


def _blob(it: dict) -> str:
    parts = [
        str(it.get("subject") or ""),
        str(it.get("summary") or ""),
        str(it.get("reason") or ""),
        str(it.get("original_body") or "")[:2000],
        str(it.get("draft_text") or "")[:2000],
    ]
    return "\n".join(parts)


def _needs_estimate_b(it: dict) -> bool:
    return bool(ESTIMATE_RE.search(_blob(it)))


def _has_estimate_b_file(folder: str) -> bool | None:
    """提示用見積Bファイルの有無。

    True/False = 判定できた。None = 一覧失敗（呼び出し側は安全側で B 待ち）。
    """
    base = _partner_base() / folder
    stock = base / "1.受信添付(Stock)"
    if stock.is_dir():
        for p in stock.rglob("*"):
            if not p.is_file():
                continue
            if B_NAME_RE.search(p.name):
                return True
        return False

    # GHA 等: ローカル Stock が無いとき Graph で列挙
    try:
        from jarvis_onedrive_graph import (  # type: ignore
            graph_configured,
            list_children_graph_depth,
        )

        if not graph_configured():
            return False
        rel = (
            "215_神・大家さん倶楽部/C2_ルーティン作業/26_パートナー社への相談/"
            f"{folder}/1.受信添付(Stock)"
        )
        for ch in list_children_graph_depth(rel, max_depth=2):
            if B_NAME_RE.search(str(ch.get("name") or "")):
                return True
        return False
    except FileNotFoundError:
        return False
    except Exception as e:
        print(f"# estimate-B list fail {folder}: {e}", file=sys.stderr)
        return None


def _template_draft(it: dict) -> str:
    """heuristic キューは draft_text 空のため、管理会社向けの控えめテンプレを埋める。"""
    channel = (it.get("channel") or "Gmail").strip() or "Gmail"
    summary = (it.get("summary") or it.get("subject") or "").strip()
    hint = summary[:80] if summary else "ご連絡の件"
    if channel == "LINE":
        return (
            "お疲れ様です！\n\n"
            f"「{hint}」確認しました。\n"
            "内容を拝見し、必要なら追ってご連絡します。\n\n"
            "（211自動下書き・送信前に人手で調整してください）\n\n"
            "松野\n"
        )
    return (
        "お世話になっております。\n\n"
        f"「{hint}」につきまして、ご連絡ありがとうございます。\n"
        "内容を確認のうえ、改めてご連絡いたします。\n\n"
        "（211自動下書き・送信前に人手で調整してください）\n\n"
        "松野\n"
    )


def _pm_candidates(items: list[dict], lookback_days: int) -> tuple[list[dict], list[dict], list[dict]]:
    """Return (applyable, b_waiting, skipped_old)."""
    cutoff = datetime.now(JST) - timedelta(days=lookback_days)
    applyable: list[dict] = []
    b_waiting: list[dict] = []
    skipped_old: list[dict] = []
    for it in items:
        if (it.get("lane") or "partner") != "partner":
            continue
        if it.get("status") not in (None, "pending"):
            continue
        folder = str(it.get("folder") or "")
        if not _is_pm_folder(folder):
            continue
        received = _parse_received(str(it.get("received_at") or ""))
        if received and received < cutoff:
            skipped_old.append(it)
            continue
        if not (it.get("draft_text") or "").strip():
            it["draft_text"] = _template_draft(it)
            it["engine"] = (it.get("engine") or "heuristic") + "+211template"
        if _needs_estimate_b(it):
            has_b = _has_estimate_b_file(folder)
            if has_b is not True:
                # False=未検出 / None=一覧失敗 → いずれも起案せず相談
                b_waiting.append(it)
                continue
        applyable.append(it)
    # 社ごとに最新1件のみ（テンプレ乱発防止）
    applyable.sort(
        key=lambda x: str(x.get("received_at") or ""),
        reverse=True,
    )
    seen_folders: set[str] = set()
    deduped: list[dict] = []
    for it in applyable:
        folder = str(it.get("folder") or "")
        if folder in seen_folders:
            continue
        seen_folders.add(folder)
        deduped.append(it)
    return deduped, b_waiting, skipped_old


def _apply_one(seq_or_id: str) -> Path | None:
    import jarvis_night_triage as nt  # type: ignore

    return nt.apply_draft_to_partner(seq_or_id)


def _slack(channel: str, lines: list[str]) -> int:
    text = "\n".join(lines)
    cmd = [
        sys.executable,
        str(REPO / "scripts" / "jarvis_slack_webhook_post.py"),
        "--channel",
        channel,
        "--username",
        "返信案内下書き係",
        "--text",
        text,
    ]
    return subprocess.call(cmd, cwd=str(REPO))


def _id_of(it: dict) -> str:
    return str(it.get("seq") or it.get("id") or "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scan", action="store_true", help="dry-run triage＋PM候補一覧")
    ap.add_argument("--triage", action="store_true", help="night_triage partner 実行")
    ap.add_argument("--morning", action="store_true", help="朝便一式（triage→見積B分岐→apply→report）")
    ap.add_argument("--apply", action="store_true", help="PM候補を正本へ書込")
    ap.add_argument("--report", action="store_true", help="起案があれば Slack #report")
    ap.add_argument("--dry-run", action="store_true", help="書込・Slackなし（判定のみ）")
    ap.add_argument("--with-fetch", action="store_true", help="Gmail取込も行う")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--lookback-days", type=int, default=21, help="これより古い候補は自動起案しない")
    ap.add_argument("--ids", nargs="*", help="apply 対象 seq/id")
    args = ap.parse_args()

    if not any([args.scan, args.triage, args.morning, args.apply, args.report]):
        ap.print_help()
        return 2

    if args.morning:
        args.triage = True
        args.apply = True
        args.report = True

    skip_fetch = not args.with_fetch
    if args.scan or args.triage:
        # scan alone = dry-run triage; morning/triage = real triage (still LLM off)
        dry = bool(args.scan) and not args.triage and not args.morning
        if args.morning and args.dry_run:
            dry = True
        rc = _run_night_triage(skip_fetch=skip_fetch, dry_run=dry, limit=args.limit)
        if rc != 0:
            print(f"# triage rc={rc}", file=sys.stderr)
            if args.morning and not args.dry_run:
                _slack(
                    "ops",
                    [
                        "【ops】返信案内下書き係・朝便",
                        f"・失敗: night_triage rc={rc}",
                        "・正本書込は中止",
                    ],
                )
                return rc

    q = _load_queue()
    items = q.get("items") or []
    applyable, b_waiting, skipped_old = _pm_candidates(items, args.lookback_days)
    # テンプレで埋めた draft_text を queue に戻す（apply が再読込するため）
    if applyable and not args.dry_run:
        qpath = REPO / ".jarvis_state" / "night_triage" / "queue.json"
        try:
            qpath.parent.mkdir(parents=True, exist_ok=True)
            qpath.write_text(
                json.dumps(q, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        except Exception as e:
            print(f"# queue save fail: {e}", file=sys.stderr)

    print(f"# PM applyable: {len(applyable)}")
    for it in applyable:
        print(
            f"  - {_id_of(it)} | {it.get('folder')} | "
            f"{it.get('channel') or 'Gmail'} | {(it.get('subject') or '')[:40]}"
        )
    print(f"# PM 見積B待ち: {len(b_waiting)}")
    for it in b_waiting:
        print(f"  - {_id_of(it)} | {it.get('folder')} | {(it.get('subject') or '')[:40]}")
    print(f"# PM 古いためスキップ({args.lookback_days}日超): {len(skipped_old)}")

    if args.scan and not args.apply:
        return 0

    written: list[tuple[str, str]] = []
    if args.apply:
        targets = args.ids or [_id_of(it) for it in applyable]
        if not targets:
            print("# apply: 対象なし")
        for tid in targets:
            if not tid:
                continue
            if args.dry_run:
                print(f"# dry-run would write {tid}")
                written.append((tid, "(dry-run)"))
                continue
            path = _apply_one(str(tid))
            if path:
                written.append((str(tid), str(path)))
                print(f"# wrote {tid} -> {path}")

    if b_waiting and not args.dry_run and (args.morning or args.report):
        lines = [
            "【相談】返信案内下書き係",
            "・決めてほしいこと: 退去/修繕/見積案件で提示用見積Bが見つからない。起案を止めています",
        ]
        for it in b_waiting[:5]:
            lines.append(
                f"・{it.get('folder')} / {(it.get('subject') or '')[:50]} / {it.get('received_at')}"
            )
        lines.append("・急ぐか: 朝便内なら今日中")
        _slack("consult", lines)

    if args.report:
        n = len([w for w in written if w[1] != "(dry-run)"]) if not args.dry_run else len(written)
        b_n = len(b_waiting)
        if n == 0 and b_n == 0:
            print("# report skip: 起案0・要確認0")
            return 0
        if args.dry_run:
            print(f"# dry-run report: 起案候補{n} / 見積B待ち{b_n}")
            return 0
        today = datetime.now(JST).strftime("%Y-%m-%d")
        partners = [Path(p).parent.name for _, p in written if p != "(dry-run)"]
        lines = [
            "【報告】返信案内下書き係・朝便",
            f"・日付: {today}",
            f"・起案: {n}" + (f"（{'／'.join(partners)}）" if partners else ""),
            f"・見積B待ち: {b_n}",
            f"・古い候補スキップ: {len(skipped_old)}（{args.lookback_days}日超）",
            "・正本: OneDrive 4.送信下書き.txt / 4.LINE送信下書き.txt",
            "・次: 人が確認。送信はこの報告ではしない",
            "・失敗: なし",
        ]
        return _slack("report", lines)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
