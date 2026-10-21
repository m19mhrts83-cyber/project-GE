#!/usr/bin/env python3
"""Grok 定型報告 → Slack（Drive inbox `action: slack_report`）。

都度の相談は Grok チャットのまま。定型（デイリー／夕方／週次／完了サマリ）だけ
`10_inbox_from_grok/` に MD を置くと、Jarvis が `#report` / `#consult` / `#ops` / `#ai-hub` へ投稿する。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_grok_slack_report_apply.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_grok_slack_report_apply.py --apply
  ~/selenium_env/venv/bin/python scripts/jarvis_grok_slack_report_apply.py --apply --archive-done

Inbox 例:

---
action: slack_report
channel: report
source: hawk
bot: ホークアイ（参謀）
title: 週次統括 YYYY-MM-DD
---

本文（短く。秘密・トークン禁止）

iPhone 可読（必須・2026-10-19）: 先頭に📌要ボス最大3つ（無ければ「要ボス: なし」）／
1項目は2行以内・入れ子と長い（）は使わない／管理情報は末尾「参考」かスレッド／
変化なしは1行まとめ。正本: docs/AIエージェントチーム/33_Slack日次集約_第1段階_20261017.md「レイアウト」

channel: consult のとき本文末尾に「次:」が無いと、橋渡し3行を補完する
（正本: docs/AIエージェントチーム/36_Slack_consult手渡し_次の担当_20261018.md）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jarvis_bucho_bridge_lib import folder, list_queue_files  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"
POST = REPO / "scripts" / "jarvis_slack_webhook_post.py"
ACTION = "slack_report"
BODY_LIMIT = 3500


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    raw = text[3:end].strip()
    meta: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip().strip("\"'")
    return meta, text[end + 4 :].lstrip("\n")


def first_heading(body: str) -> str:
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("#"):
            return s.lstrip("#").strip()
    return ""


def normalize_channel(raw: str) -> str:
    ch = (raw or "report").strip().lstrip("#").lower()
    if ch in ("ai-hub", "ai_hub"):
        return "hub"
    if ch in ("deal-active", "deal_active"):
        return "deal"
    if ch in ("report", "consult", "ops", "hub", "deal"):
        return ch
    return "report"


_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_SEP_CELL = re.compile(r":?-{2,}:?$")


def _inline_marks(s: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"*\1*", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"<\2|\1>", s)
    return s


def _is_sep_row(cells: list[str]) -> bool:
    return bool(cells) and all(_SEP_CELL.fullmatch(c or "") for c in cells)


def _render_table(block: list[str]) -> list[str]:
    """Markdown 表（| a | b |）を Slack 向けの箇条へ。iPhone の折返しでも崩れない。"""
    rows: list[list[str]] = []
    has_header = False
    for ln in block:
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if _is_sep_row(cells):
            has_header = True
            continue
        rows.append(cells)
    if has_header and rows:
        rows = rows[1:]
    out: list[str] = []
    for cells in rows:
        cells = [_inline_marks(c) for c in cells]
        if len(cells) == 1:
            out.append(f"• {cells[0]}")
        elif len(cells) == 2:
            out.append(f"• {cells[0]}：{cells[1]}")
        else:
            out.append(f"• {cells[0]}：{' ／ '.join(cells[1:])}")
    return out


def _inline(line: str) -> str:
    m = re.match(r"^\s*(#{1,6})\s+(.*)$", line)
    if m:
        return f"*{_inline_marks(m.group(2))}*"
    if re.match(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$", line):
        return "———"
    m2 = re.match(r"^(\s*)[-*]\s+(.*)$", line)
    if m2:
        return f"{m2.group(1)}• {_inline_marks(m2.group(2))}"
    return _inline_marks(line)


def markdown_to_slack(text: str) -> str:
    """Markdown を Slack mrkdwn へ（表→箇条、# → 太字、[t](u) → リンク）。"""
    lines = text.splitlines()
    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        if _TABLE_ROW.match(lines[i]):
            block: list[str] = []
            while i < n and _TABLE_ROW.match(lines[i]):
                block.append(lines[i])
                i += 1
            out += _render_table(block)
            continue
        out.append(_inline(lines[i]))
        i += 1
    return "\n".join(out)


_CONSULT_NEXT_RE = re.compile(r"(?m)^\s*次\s*[:：]")


def normalize_consult_handoff_spacing(body: str) -> str:
    """次／担当メモ／橋渡しの間に空行を入れる（Slack UI FB 2026-10-22）。"""
    text = (body or "").rstrip()
    # 次 → 担当メモ
    text = re.sub(
        r"(?m)^([ \t]*次\s*[:：][^\n]*)\n+(?=[ \t]*担当メモ\s*[:：])",
        r"\1\n\n",
        text,
    )
    # 担当メモ → 橋渡し
    text = re.sub(
        r"(?m)^([ \t]*担当メモ\s*[:：][^\n]*)\n+(?=[ \t]*橋渡し\s*[:：])",
        r"\1\n\n",
        text,
    )
    return text


def ensure_consult_handoff_footer(body: str) -> str:
    """#consult 用。末尾に「次:」が無いとき橋渡し3行を補完（忘却防止）。"""
    text = (body or "").rstrip()
    if _CONSULT_NEXT_RE.search(text):
        return normalize_consult_handoff_spacing(text)
    stub = (
        "\n\n次: 人判断のみ\n"
        "\n担当メモ: （Grok未記入・Jarvisが補完）了承後に担当を決めて一声\n"
        "\n橋渡し: 松野が了承したら Grok／Jarvis へ一声（当面は人が橋）"
    )
    return normalize_consult_handoff_spacing(text + stub)


def build_text(meta: dict[str, str], body: str, name: str) -> str:
    bot = meta.get("bot") or meta.get("source") or "Grok"
    title = meta.get("title") or first_heading(body) or name
    channel = normalize_channel(meta.get("channel") or "report")
    kind = meta.get("kind") or "定型報告"
    body_clean = body.strip()
    if channel == "consult":
        body_clean = ensure_consult_handoff_footer(body_clean)
    if len(body_clean) > BODY_LIMIT:
        body_clean = body_clean[: BODY_LIMIT - 1] + "…"
    # 秘密っぽい行を落とす（値は出さない）
    filtered: list[str] = []
    for line in body_clean.splitlines():
        low = line.lower()
        if any(
            x in low
            for x in (
                "password",
                "api_key",
                "api-key",
                "secret",
                "token=",
                "webhook",
                "hooks.slack.com",
            )
        ):
            continue
        filtered.append(line)
    body_clean = "\n".join(filtered).strip() or "（本文なし）"
    body_clean = markdown_to_slack(body_clean)
    return (
        f"【Grok定型報告】{bot}\n"
        f"・種別: {kind}\n"
        f"・題: {title}\n"
        f"・ch: #{channel}\n"
        f"\n{body_clean}"
    )


def iter_targets() -> list[tuple[Path, dict[str, str], str]]:
    inbox = folder("inbox_from_grok")
    out: list[tuple[Path, dict[str, str], str]] = []
    for path in list_queue_files(inbox):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        meta, body = parse_frontmatter(text)
        if (meta.get("action") or "").strip() != ACTION:
            continue
        out.append((path, meta, body))
    return out


def archive_path(path: Path) -> Path:
    arch = folder("archive")
    dest = arch / path.name
    if dest.exists():
        stem, suf = path.stem, path.suffix
        dest = arch / f"{stem}_archived{suf}"
    path.rename(dest)
    return dest


def post_slack(channel: str, text: str, *, dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return {"ok": True, "dry_run": True, "channel": channel, "chars": len(text)}
    if not POST.is_file():
        return {"ok": False, "error": "jarvis_slack_webhook_post.py missing"}
    cmd = [
        str(PY),
        str(POST),
        "--channel",
        channel,
        "--text",
        text,
        "--username",
        "Grok via Jarvis",
    ]
    try:
        r = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, timeout=60)
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
    return {
        "ok": r.returncode == 0,
        "returncode": r.returncode,
        "stdout": (r.stdout or "")[-300:],
        "stderr": (r.stderr or "")[-300:],
        "channel": channel,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true", help="Slack 投稿を実行")
    ap.add_argument(
        "--archive-done",
        action="store_true",
        help="投稿成功した MD を 90_archive へ",
    )
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if not args.dry_run and not args.apply:
        args.dry_run = True

    if (os.environ.get("JARVIS_GROK_SLACK_REPORT_DISABLE") or "").strip() in (
        "1",
        "true",
        "yes",
    ):
        result = {"ok": True, "skipped": True, "reason": "JARVIS_GROK_SLACK_REPORT_DISABLE"}
        print(json.dumps(result, ensure_ascii=False) if args.json else f"📎 skipped: {result}")
        return 0

    items = iter_targets()
    results: list[dict[str, Any]] = []
    for path, meta, body in items:
        channel = normalize_channel(meta.get("channel") or "report")
        text = build_text(meta, body, path.name)
        posted = post_slack(channel, text, dry_run=args.dry_run)
        entry: dict[str, Any] = {
            "file": path.name,
            "channel": channel,
            "bot": meta.get("bot") or meta.get("source"),
            "title": meta.get("title") or first_heading(body),
            "post": posted,
        }
        if posted.get("ok") and args.apply and args.archive_done and not args.dry_run:
            try:
                dest = archive_path(path)
                entry["archived"] = str(dest)
            except OSError as e:
                entry["archive_error"] = str(e)[:120]
        results.append(entry)

    summary = {
        "ok": all((r.get("post") or {}).get("ok") for r in results) if results else True,
        "count": len(results),
        "dry_run": bool(args.dry_run),
        "items": results,
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        mode = "dry-run" if args.dry_run else "apply"
        print(f"📎 Grok→Slack定型報告 ({mode}) count={summary['count']}")
        for r in results:
            st = "OK" if (r.get("post") or {}).get("ok") else "FAIL"
            print(f"  - [{st}] #{r.get('channel')} {r.get('file')} — {r.get('title')}")
            if not (r.get("post") or {}).get("ok"):
                err = (r.get("post") or {}).get("stderr") or (r.get("post") or {}).get("error")
                if err:
                    print(f"    {err[:160]}")
        if not results:
            print("  （対象なし）")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
