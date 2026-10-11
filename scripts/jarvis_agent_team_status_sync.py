#!/usr/bin/env python3
"""AIエージェントチーム — 状態マーカー／部門状態ボードを registry から同期.

正本: docs/AIエージェントチーム/agents_registry.yaml の status
ルール: docs/AIエージェントチーム/22_運用状態の識別_20261011.md

社員フォルダ作成・status 変更のあと必ず実行（Drive 写しも任意で可）。
ダッシュ投影: apps/jarvis-dashboard/data/agentTeam.json（commit/push で本番反映）
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "docs" / "AIエージェントチーム"
REG = HUB / "agents_registry.yaml"
DASH_JSON = REPO / "apps" / "jarvis-dashboard" / "data" / "agentTeam.json"
DRIVE_HUB = (
    Path.home()
    / "Library/CloudStorage/GoogleDrive-admin@livingsupport-matsu.co.jp"
    / "マイドライブ"
    / "★AIエージェントチーム"
)
JST = ZoneInfo("Asia/Tokyo")
FLOWFORGE_LOGIN_HINT = "m19m"  # FlowForge 作成アカウント（セミナー・作成文脈）

MARKER = {
    "設計中": "00_🔵設計中.md",
    "運用確認": "00_🟡運用確認.md",
    "運用": "00_🟢運用.md",
    "停止": "00_⛔停止.md",
}
ICON = {
    "候補": "⚪",
    "設計中": "🔵",
    "運用確認": "🟡",
    "運用": "🟢",
    "停止": "⛔",
}
README_PREFIX = {
    "設計中": "【設計中】",
    "運用確認": "【運用確認】",
    "運用": "【運用】",
    "停止": "【停止】",
}


def load_registry() -> dict:
    return yaml.safe_load(REG.read_text(encoding="utf-8"))


def wipe_markers(folder: Path) -> None:
    if not folder.is_dir():
        return
    for p in folder.iterdir():
        if not p.is_file():
            continue
        n = p.name
        if n == "STATUS.md" or n in MARKER.values():
            p.unlink(missing_ok=True)
            continue
        if n.startswith("00_") and any(
            x in n for x in ("運用", "設計中", "停止", "🟢", "🟡", "🔵", "⛔")
        ):
            p.unlink(missing_ok=True)


def write_marker(folder: Path, aid: str, name: str, status: str, dry: bool) -> str | None:
    fname = MARKER.get(status)
    if dry:
        return fname
    folder.mkdir(parents=True, exist_ok=True)
    wipe_markers(folder)
    if not fname:
        return None
    depth = len(Path(folder.relative_to(HUB)).parts)
    rel22 = "/".join([".."] * depth) + "/22_運用状態の識別_20261011.md"
    body = (
        f"# {status}\n\n"
        f"この**ファイル名**が状態の印です（中身を開かなくてよい）。\n\n"
        f"- ID: `{aid}`\n"
        f"- 名前: {name}\n"
        f"- 正本: `agents_registry.yaml` → `agents[\"{aid}\"].status`\n"
        f"- ルール: [`22_運用状態の識別_20261011.md`]({rel22})\n"
        f"- 更新: {date.today().isoformat()}\n"
    )
    (folder / fname).write_text(body, encoding="utf-8")
    return fname


def ensure_readme_prefix(readme: Path, status: str, dry: bool) -> None:
    pref = README_PREFIX.get(status)
    if not pref or not readme.is_file():
        return
    text = readme.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines:
        return
    import re

    m = re.match(r"^#\s*(【[^】]+】)?\s*(.+)$", lines[0])
    if not m:
        return
    rest = m.group(2).strip()
    new_first = f"# {pref}{rest}"
    if lines[0] == new_first:
        return
    if dry:
        return
    lines[0] = new_first
    body = "\n".join(lines)
    if not body.endswith("\n"):
        body += "\n"
    readme.write_text(body, encoding="utf-8")


def write_dept_board(
    dept_id: str, dept: dict, agents: list[tuple[str, dict]], dry: bool
) -> Path:
    dpath = HUB / dept["path"]
    out = dpath / "00_状態ボード.md"
    rows = []
    for aid, a in sorted(agents, key=lambda x: x[0]):
        st = a.get("status") or "候補"
        icon = ICON.get(st, "⚪")
        mark = MARKER.get(st, "—（候補はマーカーなし）")
        folder = Path(a["path"]).name
        rows.append(
            f"| `{aid}` | {icon} | {st} | [{folder}](./{folder}/) | `{mark}` |"
        )
    body = (
        f"# {dept_id} {dept['name']} — 状態ボード\n\n"
        f"部門を展開したときに**一目で**配下の運用状態がわかる一覧。\n\n"
        f"- 正本: [`../agents_registry.yaml`](../agents_registry.yaml) の `status`\n"
        f"- 識別ルール: [`../22_運用状態の識別_20261011.md`](../22_運用状態の識別_20261011.md)\n"
        f"- 同期: `scripts/jarvis_agent_team_status_sync.py`（作成・status変更のあと実行）\n"
        f"- 更新: {date.today().isoformat()}\n\n"
        f"| ID | 印 | 状態 | フォルダ | マーカーファイル |\n"
        f"|---|---|---|---|---|\n"
        + "\n".join(rows)
        + "\n"
    )
    if not dry:
        dpath.mkdir(parents=True, exist_ok=True)
        out.write_text(body, encoding="utf-8")
        # link from 01_部門.md if present（並び: 00_状態ボード → 01_部門）
        dept_md = dpath / "01_部門.md"
        legacy = dpath / "00_部門.md"
        if legacy.is_file() and not dept_md.is_file():
            legacy.rename(dept_md)
        elif legacy.is_file() and dept_md.is_file():
            legacy.unlink()
        if dept_md.is_file():
            t = dept_md.read_text(encoding="utf-8")
            if "00_状態ボード.md" not in t:
                t = t.rstrip() + (
                    "\n\n配下の状態: [`00_状態ボード.md`](./00_状態ボード.md)"
                    "（registry 同期）\n"
                )
                dept_md.write_text(t, encoding="utf-8")
    return out


def sync_drive(rel: Path, dry: bool) -> None:
    if dry or not DRIVE_HUB.is_dir():
        return
    src = HUB / rel
    if not src.exists():
        return
    dst = DRIVE_HUB / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_file():
        shutil.copy2(src, dst)
    # for markers we copy file-by-file from callers


def _extract_readme_role(readme: Path) -> str:
    if not readme.is_file():
        return ""
    text = readme.read_text(encoding="utf-8")
    m = re.search(r"\|\s*役割\s*\|\s*(.+?)\s*\|", text)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    return ""


def _extract_flow_summary(flow_md: Path) -> str:
    if not flow_md.is_file():
        return ""
    text = flow_md.read_text(encoding="utf-8")
    m = re.search(
        r"##\s*いまの結論[^\n]*\n+(.+?)(?:\n\n|\n## |\Z)",
        text,
        re.DOTALL,
    )
    if m:
        line = m.group(1).strip().splitlines()[0].strip()
        return re.sub(r"\s+", " ", line)[:240]
    return ""


def write_dashboard_json(data: dict, dry: bool) -> Path:
    """registry → jarvis-dashboard 投影 JSON."""
    depts = data.get("departments") or {}
    agents = data.get("agents") or {}
    builder = data.get("builder_source") or {}
    now = datetime.now(JST).isoformat(timespec="seconds")

    dept_list = []
    for did, dept in sorted(depts.items(), key=lambda x: str(x[0])):
        dept_list.append(
            {
                "id": str(did),
                "name": dept.get("name") or "",
                "path": dept.get("path") or "",
            }
        )

    counts: dict[str, int] = {
        "候補": 0,
        "設計中": 0,
        "運用確認": 0,
        "運用": 0,
        "停止": 0,
    }
    agent_list = []
    for aid, a in sorted(agents.items(), key=lambda x: str(x[0])):
        st = a.get("status") or "候補"
        counts[st] = counts.get(st, 0) + 1
        folder = HUB / (a.get("path") or "")
        role = _extract_readme_role(folder / "README.md")
        flow_summary = _extract_flow_summary(folder / "flow.md")
        summary = role or (a.get("note") or "") or flow_summary
        top = Path(a.get("path") or "").parts[0] if a.get("path") else ""
        dept_id = (
            top[:3] if len(top) >= 3 and top[:3].isdigit() else str(aid)[:1] + "00"
        )
        dept_name = (depts.get(dept_id) or depts.get(str(dept_id)) or {}).get(
            "name"
        ) or ""
        agent_list.append(
            {
                "id": str(aid),
                "name": a.get("name") or "",
                "path": a.get("path") or "",
                "department_id": str(dept_id),
                "department_name": dept_name,
                "status": st,
                "status_icon": ICON.get(st, "⚪"),
                "report": a.get("report") or "",
                "trigger": a.get("trigger") or "",
                "schedule": a.get("schedule") or "",
                "tool_assigned": a.get("tool_assigned") or "",
                "tool_fit": a.get("tool_fit") or "",
                "tool_notes": a.get("tool_notes") or "",
                "note": a.get("note") or "",
                "summary": summary,
                "flow_summary": flow_summary,
                "builder_tag": a.get("builder_tag") or "",
                "mixup_kind": a.get("mixup_kind") or "",
                "grok_counterpart": a.get("grok_counterpart") or "",
                "flowforge_id": a.get("flowforge_id") or "",
                "flowforge_url": a.get("flowforge_url") or "",
            }
        )

    payload = {
        "updated": now,
        "registry_updated": data.get("updated") or "",
        "flowforge_base": "https://flowforge-259747770348.asia-northeast1.run.app/",
        "flowforge_login_hint": FLOWFORGE_LOGIN_HINT,
        "flowforge_open_note": (
            "作業フローの作り込み・拡大・要素詳細は Cursor インブラウザの "
            "FlowForge で行う。ダッシュは状況確認と深リンク用。"
            f" FlowForge は {FLOWFORGE_LOGIN_HINT} でログインしたブラウザで開く。"
        ),
        "builder": {
            "title": builder.get("title") or "",
            "url": builder.get("url") or "",
            "share_id": builder.get("share_id") or "",
        },
        "counts": counts,
        "departments": dept_list,
        "agents": agent_list,
    }
    if dry:
        print(f"  dashboard JSON (dry): {len(agent_list)} agents → {DASH_JSON}")
        return DASH_JSON
    DASH_JSON.parent.mkdir(parents=True, exist_ok=True)
    DASH_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"  dashboard: {DASH_JSON.relative_to(REPO)} ({len(agent_list)} agents)")
    return DASH_JSON


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--no-drive",
        action="store_true",
        help="Drive ★AIエージェントチーム へ写さない",
    )
    args = ap.parse_args()
    data = load_registry()
    agents = data.get("agents") or {}
    depts = data.get("departments") or {}

    by_dept: dict[str, list[tuple[str, dict]]] = {str(k): [] for k in depts}
    for aid, a in agents.items():
        p = str(a.get("path") or "")
        top = Path(p).parts[0] if p else ""
        did = top[:3] if len(top) >= 3 and top[:3].isdigit() else str(aid)[:1] + "00"
        by_dept.setdefault(did, []).append((str(aid), a))

    print("📎 agent_team status sync")
    for aid, a in sorted(agents.items(), key=lambda x: str(x[0])):
        st = a.get("status") or "候補"
        folder = HUB / a["path"]
        fname = write_marker(folder, str(aid), a.get("name") or "", st, args.dry_run)
        if not args.dry_run:
            ensure_readme_prefix(folder / "README.md", st, False)
            if not args.no_drive:
                # Drive 側もマーカーを一旦消してから正を写す（旧印の二重残し防止）
                drive_folder = DRIVE_HUB / a["path"]
                wipe_markers(drive_folder)
                if fname:
                    sync_drive(Path(a["path"]) / fname, False)
                sync_drive(Path(a["path"]) / "README.md", False)
                (drive_folder / "STATUS.md").unlink(missing_ok=True)
        mark = fname or "—"
        print(f"  [{aid}] {st} → {mark}")

    for did, dept in sorted(depts.items(), key=lambda x: str(x[0])):
        alist = by_dept.get(str(did), [])
        out = write_dept_board(str(did), dept, alist, args.dry_run)
        print(f"  board {did}: {out.relative_to(HUB)} ({len(alist)} agents)")
        if not args.dry_run and not args.no_drive:
            sync_drive(Path(dept["path"]) / "00_状態ボード.md", False)
            sync_drive(Path(dept["path"]) / "01_部門.md", False)
            # 旧名の残骸を Drive から消す
            old_drive = DRIVE_HUB / dept["path"] / "00_部門.md"
            if not args.dry_run:
                old_drive.unlink(missing_ok=True)

    write_dashboard_json(data, args.dry_run)

    if not args.dry_run and not args.no_drive:
        for rel in (
            "22_運用状態の識別_20261011.md",
            "agents_registry.yaml",
            "00_チーム索引.md",
            "AGENTS.md",
            "CLAUDE.md",
        ):
            if (HUB / rel).exists():
                sync_drive(Path(rel), False)
        print(f"  drive: {DRIVE_HUB}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
