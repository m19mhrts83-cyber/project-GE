#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GenMail（admin）要対応 → Todoist 候補提案（了承後 create）.

無言の自動起票はしない。入口 MD を読んで提案 → 了承後 `--apply`。

入口: `.jarvis_state/genmail_action_needed.md`（GenMail Super Agent の要対応を追記）

形式（1件1ブロック）:

  ## 件名または短いタイトル
  lane: ai_raimo
  summary: 1行要約
  account: admin

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_genmail_propose.py
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_genmail_propose.py --apply --select 1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
STATE_PATH = REPO / ".jarvis_state" / "todoist_genmail_propose.json"
INBOX_DEFAULT = REPO / ".jarvis_state" / "genmail_action_needed.md"
EXAMPLE_PATH = REPO / ".jarvis_state" / "genmail_action_needed.example.md"
YAML_PATH = REPO / "config" / "todoist_projects.yaml"
PY = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")
JST = timezone(timedelta(hours=9))

LANE_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"幹事|飲み会|懇親会|新年会|BBQ|遊愛会", re.I), "kanji"),
    (re.compile(r"家族|珠己|円香|千景|家族会議", re.I), "kazoku"),
    (re.compile(r"戸建|土地値|楽待|健美家|物件調査|千三つ", re.I), "kodate"),
    (
        re.compile(
            r"LEAF|ミニテック|ホームプランナー|修繕|退去|原状|空室|管理会社|Grandole|キャラメル|Tcell",
            re.I,
        ),
        "properties",
    ),
    (re.compile(r"神大家|WeStudy|グルコン|815|オプチャ", re.I), "kamiooya"),
    (
        re.compile(r"Todoist|ダッシュボード|KURASHIFT|アプリ|FRIDAY|GenCode|Mesh", re.I),
        "apps",
    ),
    (re.compile(r"Raimo|チャプロ|Cursor|Grok|AI|Jarvis|Genspark|GenMail|課金|カード", re.I), "ai_raimo"),
]


def _now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def _inbox_path() -> Path:
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8")) or {}
        rel = ((data.get("genmail_propose") or {}).get("inbox_path") or "").strip()
        if rel:
            p = Path(rel)
            return p if p.is_absolute() else REPO / p
    except Exception:
        pass
    return INBOX_DEFAULT


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"proposals": [], "created_fingerprints": [], "last_propose_at": None}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"proposals": [], "created_fingerprints": [], "last_propose_at": None}


def _save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _guess_lane(title: str, summary: str) -> str:
    blob = f"{title}\n{summary}"
    for pat, lane in LANE_HINTS:
        if pat.search(blob):
            return lane
    return "ai_raimo"


def _parse_inbox(text: str) -> list[dict[str, Any]]:
    """## 見出しブロックを候補に。"""
    text = (text or "").strip()
    if not text or text.startswith("# GenMail") and "まだ項目がありません" in text:
        # example-only
        pass
    parts = re.split(r"(?m)^##\s+", text)
    items: list[dict[str, Any]] = []
    for part in parts[1:]:
        lines = part.strip().splitlines()
        if not lines:
            continue
        title = lines[0].strip()
        if title.lower().startswith("example") or "例:" in title[:10]:
            continue
        meta: dict[str, str] = {}
        body_lines: list[str] = []
        for ln in lines[1:]:
            m = re.match(r"^([a-zA-Z_]+)\s*:\s*(.+)$", ln.strip())
            if m:
                meta[m.group(1).strip().lower()] = m.group(2).strip()
            elif ln.strip():
                body_lines.append(ln.strip())
        summary = meta.get("summary") or (" ".join(body_lines)[:200] if body_lines else title)
        lane = meta.get("lane") or _guess_lane(title, summary)
        account = meta.get("account") or "admin"
        fp = hashlib.sha1(f"{title}|{summary}".encode("utf-8")).hexdigest()[:16]
        items.append(
            {
                "title": title[:200],
                "summary": summary[:500],
                "lane": lane,
                "account": account,
                "fingerprint": fp,
            }
        )
    return items


def _print_block(cands: list[dict[str, Any]]) -> None:
    print("📎 GenMail要対応（提案）")
    print("- 接続Gmail: admin（m19m/estate 集約）")
    print("- 無言起票なし。了承後: --apply --select N")
    if not cands:
        print("- 候補なし（入口 MD に ## 見出しで追記してください）")
        print(f"- 入口: {_inbox_path()}")
        return
    for c in cands:
        print(f"#{c['n']} [{c['lane']}] {c['title']}")
        if c.get("summary") and c["summary"] != c["title"]:
            print(f"    {c['summary']}")
    print(
        "  了承後: ~/selenium_env/venv/bin/python scripts/jarvis_todoist_genmail_propose.py"
        " --apply --select 1"
    )


def cmd_propose(args: argparse.Namespace) -> int:
    path = Path(args.inbox) if args.inbox else _inbox_path()
    if not path.is_file():
        EXAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not EXAMPLE_PATH.is_file():
            EXAMPLE_PATH.write_text(
                "# GenMail 要対応（例）\n\n"
                "## 例: 件名をここに\n"
                "lane: ai_raimo\n"
                "summary: 1行要約\n"
                "account: admin\n",
                encoding="utf-8",
            )
        print(
            f"入口ファイルがありません: {path}\n"
            f"GenMail の要対応を ## 見出しで追記するか、例をコピー:\n"
            f"  cp {EXAMPLE_PATH} {path}",
            file=sys.stderr,
        )
        return 1

    text = path.read_text(encoding="utf-8")
    raw = _parse_inbox(text)
    state = _load_state()
    done = set(state.get("created_fingerprints") or [])
    cands = []
    n = 0
    for item in raw:
        if item["fingerprint"] in done:
            continue
        n += 1
        item["n"] = n
        item["label"] = "quick"
        cands.append(item)

    state["proposals"] = cands
    state["last_propose_at"] = _now_iso()
    state["inbox_path"] = str(path)
    _save_state(state)

    if args.json:
        print(json.dumps({"proposals": cands, "inbox": str(path)}, ensure_ascii=False, indent=2))
    else:
        _print_block(cands)
    return 0


def _create_task(c: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    lane = str(c.get("lane") or "ai_raimo")
    title = str(c.get("title") or "").strip()
    note = (
        f"出典: GenMail要対応（{c.get('account') or 'admin'}）\n"
        f"サマリ: {c.get('summary') or ''}"
    )
    comment = (
        f"サマリ: {c.get('summary') or title}\n"
        f"アウトプット:\n"
        f"- [GenMail入口](file://{_inbox_path()})"
    )
    if dry_run:
        return {"ok": True, "dry": True, "lane": lane, "title": title}
    cmd = [
        str(PY),
        str(REPO / "scripts" / "jarvis_todoist_api.py"),
        "create-task",
        "--lane",
        lane,
        "--title",
        title,
        "--note",
        note[:1500],
        "--label",
        "quick",
        "--comment",
        comment[:1900],
        "--json",
    ]
    # properties レーンは物件+PM必須 → GenMailでは避ける（ヒントが properties でも ai_raimo に落とす）
    if lane == "properties":
        # タイトルに物件が無いと失敗するため、運用レーンへ
        cmd[cmd.index("--lane") + 1] = "ai_raimo"
        lane = "ai_raimo"
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
    if proc.returncode != 0:
        return {
            "ok": False,
            "error": (proc.stderr or proc.stdout or "").strip()[:500],
            "lane": lane,
            "title": title,
        }
    try:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:
        data = {"ok": True, "raw": proc.stdout.strip()[:300]}
    data["lane"] = lane
    data["title"] = title
    data["fingerprint"] = c.get("fingerprint")
    return data


def cmd_apply(args: argparse.Namespace) -> int:
    state = _load_state()
    cands: list[dict[str, Any]] = list(state.get("proposals") or [])
    if not cands:
        raise SystemExit("提案がありません。先に propose（引数なし）を実行してください。")

    select = (args.select or "").strip().lower()
    if not select:
        raise SystemExit("--select 1,2 または --select all が必要です")

    chosen: list[dict[str, Any]] = []
    if select in ("all", "*"):
        chosen = list(cands)
    else:
        nums = set()
        for part in re.split(r"[,\s]+", select):
            if part.isdigit():
                nums.add(int(part))
        for c in cands:
            if int(c.get("n") or 0) in nums:
                chosen.append(c)
        if not chosen:
            raise SystemExit(f"番号に一致する候補がありません: {select}")

    dry = bool(args.dry_run)
    results = []
    fps = list(state.get("created_fingerprints") or [])
    for c in chosen:
        r = _create_task(c, dry_run=dry)
        results.append(r)
        if r.get("ok") and not dry and c.get("fingerprint"):
            fps.append(str(c["fingerprint"]))

    state["created_fingerprints"] = fps[-200:]
    state["last_apply_at"] = _now_iso()
    state["last_apply_results"] = results
    _save_state(state)

    print("📎 Todoist起票（GenMail）" + (" DRY-RUN" if dry else ""))
    for r in results:
        if r.get("ok"):
            if dry:
                print(f"- [dry] [{r.get('lane')}] {r.get('title')}")
            else:
                print(f"- created id={r.get('id')} lane={r.get('lane')} {r.get('title')}")
        else:
            print(f"- FAIL: {r.get('error')} / {r.get('title')}", file=sys.stderr)
    return 0 if all(x.get("ok") for x in results) else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="GenMail要対応 → Todoist 提案")
    p.add_argument("--inbox", default=None, help="入口 MD パス")
    p.add_argument("--json", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--select", default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    if args.apply:
        return cmd_apply(args)
    return cmd_propose(args)


if __name__ == "__main__":
    raise SystemExit(main())
