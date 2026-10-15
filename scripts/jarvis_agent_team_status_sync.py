#!/usr/bin/env python3
"""AIエージェントチーム — 状態マーカー／部門状態ボードを registry から同期.

正本: docs/AIエージェントチーム/agents_registry.yaml の status
ルール: docs/AIエージェントチーム/22_運用状態の識別_20261011.md
Grok: config/grok_bots_registry.yaml（組織・社員・対応表）
ジャンル: config/agent_team_genres.yaml（上位分類・ダッシュ投影）

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
GROK_REG = REPO / "config" / "grok_bots_registry.yaml"
GENRE_REG = REPO / "config" / "agent_team_genres.yaml"
DASH_JSON = REPO / "apps" / "jarvis-dashboard" / "data" / "agentTeam.json"
# 閲覧共有URLの正本（git追跡）。ローカル上書きは .jarvis_state 側
FLOWFORGE_SHARE_CONFIG = REPO / "config" / "flowforge_share_urls.json"
FLOWFORGE_SHARE_STATE = REPO / ".jarvis_state" / "flowforge_share_urls.json"
FLOWFORGE_LOGIN_EMAIL = "m19m.hrts83@gmail.com"
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


def load_grok_registry() -> dict:
    if not GROK_REG.is_file():
        return {}
    return yaml.safe_load(GROK_REG.read_text(encoding="utf-8")) or {}


def load_genre_registry() -> dict:
    if not GENRE_REG.is_file():
        return {}
    return yaml.safe_load(GENRE_REG.read_text(encoding="utf-8")) or {}


def build_genre_maps(genre_reg: dict) -> tuple[dict[str, str], dict[str, str], list[dict]]:
    """ai_dept_id → genre_id, grok_dept_id → genre_id, genres list (skeleton)."""
    ai_map: dict[str, str] = {}
    grok_map: dict[str, str] = {}
    genres_out: list[dict] = []
    for g in sorted(genre_reg.get("genres") or [], key=lambda x: int(x.get("order") or 99)):
        gid = str(g.get("id") or "")
        if not gid:
            continue
        for did in g.get("ai_department_ids") or []:
            ai_map[str(did)] = gid
        for did in g.get("grok_department_ids") or []:
            grok_map[str(did)] = gid
        leaders = g.get("leaders") or {}
        genres_out.append(
            {
                "id": gid,
                "name": g.get("name") or gid,
                "order": int(g.get("order") or 99),
                "summary": g.get("summary") or "",
                "leaders": {
                    "grok": leaders.get("grok") or "",
                    "ai": leaders.get("ai") or "",
                },
                "ai_department_ids": [str(x) for x in (g.get("ai_department_ids") or [])],
                "grok_department_ids": [str(x) for x in (g.get("grok_department_ids") or [])],
                "nav_hints": list(g.get("nav_hints") or []),
                # filled in write_dashboard_json
                "ai_agent_ids": [],
                "grok_bot_ids": [],
                "counts": {
                    "ai": 0,
                    "grok": 0,
                    "paired": 0,
                    "ai_only": 0,
                    "grok_only": 0,
                },
            }
        )
    return ai_map, grok_map, genres_out


def enrich_genres_with_members(
    genres: list[dict],
    agents: list[dict],
    grok_bots: list[dict],
    mappings: list[dict],
) -> list[dict]:
    by_id = {g["id"]: g for g in genres}
    for a in agents:
        gid = a.get("genre_id") or ""
        g = by_id.get(gid)
        if not g:
            continue
        g["ai_agent_ids"].append(a["id"])
        g["counts"]["ai"] += 1
    for b in grok_bots:
        gid = b.get("genre_id") or ""
        g = by_id.get(gid)
        if not g:
            continue
        g["grok_bot_ids"].append(b["id"])
        g["counts"]["grok"] += 1
    agent_genre = {a["id"]: a.get("genre_id") or "" for a in agents}
    bot_genre = {b["id"]: b.get("genre_id") or "" for b in grok_bots}
    for m in mappings:
        side = m.get("side") or ""
        gids: set[str] = set()
        aid = m.get("agent_id") or ""
        if aid and agent_genre.get(aid):
            gids.add(agent_genre[aid])
        for bid in m.get("grok_ids") or []:
            bg = bot_genre.get(str(bid))
            if bg:
                gids.add(bg)
        # ミックスレーンのみ横断へ（ジャンル不明の全件は載せない）
        if not gids and m.get("mixup_kind") == "lane":
            if "jarvis_cross" in by_id:
                gids.add("jarvis_cross")
        for gid in gids:
            g = by_id.get(gid)
            if not g:
                continue
            if side == "paired":
                g["counts"]["paired"] += 1
            elif side == "ai_only":
                g["counts"]["ai_only"] += 1
            elif side == "grok_only":
                g["counts"]["grok_only"] += 1
    return genres


def _merge_flowforge_share_raw(raw: dict, out: dict[str, str]) -> None:
    for k, v in (raw.get("by_agent_id") or {}).items():
        if isinstance(v, str) and "/share/" in v:
            out[str(k)] = v
    by_flow = dict(raw.get("by_flow_id") or {})
    for k, v in raw.items():
        if str(k).startswith("flow_") and isinstance(v, str) and "/share/" in v:
            by_flow[str(k)] = v
    for k, v in by_flow.items():
        if isinstance(v, str) and "/share/" in v:
            out[f"flow:{k}"] = v


def load_flowforge_share_map() -> dict[str, str]:
    """agent_id / flow_id → share URL（閲覧専用・外部ブラウザ向け）.

    正本は config/flowforge_share_urls.json（git追跡）。
    .jarvis_state にあれば上書きマージ（ローカル再取得分）。
    """
    out: dict[str, str] = {}
    for path in (FLOWFORGE_SHARE_CONFIG, FLOWFORGE_SHARE_STATE):
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(raw, dict):
            _merge_flowforge_share_raw(raw, out)
    return out


def flowforge_edit_via_account_chooser(flow_url: str) -> str:
    """外部ブラウザ向け: m19m を選ばせる AccountChooser 経由."""
    from urllib.parse import quote

    if not flow_url:
        return ""
    cont = quote(flow_url, safe="")
    email = quote(FLOWFORGE_LOGIN_EMAIL, safe="")
    return (
        "https://accounts.google.com/AccountChooser?"
        f"Email={email}&continue={cont}"
    )


def build_grok_payload(agents_reg: dict, grok_reg: dict) -> dict:
    """Grok 組織・一覧・AIチーム対応表をダッシュ用に組み立てる."""
    if not grok_reg:
        return {
            "updated": "",
            "pillars": [],
            "departments": [],
            "bots": [],
            "mappings": [],
            "note": "config/grok_bots_registry.yaml がありません",
        }

    bot_by_id: dict[str, dict] = {}
    dept_out = []
    bots_out = []
    for dept in grok_reg.get("departments") or []:
        did = str(dept.get("id") or "")
        dname = dept.get("name") or ""
        bot_ids = []
        for b in dept.get("bots") or []:
            bid = str(b.get("id") or "")
            if not bid:
                continue
            row = {
                "id": bid,
                "code": b.get("code") or "",
                "name": b.get("name") or "",
                "kind": b.get("kind") or "",
                "work": b.get("work") or "",
                "schedule": b.get("schedule") or "",
                "drive_target": b.get("drive_target") or "",
                "paste": b.get("paste") or "",
                "department_id": did,
                "department_name": dname,
                "channel": dept.get("channel") or "",
                "exec_level": dept.get("exec_level") or "",
            }
            bot_by_id[bid] = row
            bots_out.append(row)
            bot_ids.append(bid)
        dept_out.append(
            {
                "id": did,
                "name": dname,
                "channel": dept.get("channel") or "",
                "exec_level": dept.get("exec_level") or "",
                "bot_ids": bot_ids,
                "bot_count": len(bot_ids),
            }
        )

    aliases: dict[str, list[str]] = grok_reg.get("counterpart_aliases") or {}
    role_splits: dict[str, str] = {
        str(k): str(v) for k, v in (grok_reg.get("role_splits") or {}).items()
    }
    agents = agents_reg.get("agents") or {}
    mappings: list[dict] = []
    covered_grok: set[str] = set()

    def _grok_labels(gids: list[str]) -> list[str]:
        labels = []
        for gid in gids:
            gb = bot_by_id.get(gid)
            if gb:
                label = gb.get("code") or gid
                labels.append(f"{label} {gb.get('name') or ''}".strip())
            else:
                labels.append(gid)
        return labels

    # 1) 全 AI社員（対応あり / AIのみ）
    for aid, a in sorted(agents.items(), key=lambda x: str(x[0])):
        kind = (a.get("mixup_kind") or "").strip()
        cp = (a.get("grok_counterpart") or "").strip()
        tag = (a.get("builder_tag") or "").strip()
        grok_ids: list[str] = []
        if kind == "lane":
            # レーンは特定Botのツインではない（covered に含めない）
            side = "paired"
            mix = "lane"
            role = role_splits.get(str(aid), a.get("note") or "両系統の比較レーン")
            g_labels: list[str] = []
        elif kind == "mac_twin" or cp:
            side = "paired"
            mix = kind or "mac_twin"
            grok_ids = [str(x) for x in (aliases.get(cp) or ([cp] if cp else []))]
            covered_grok.update(grok_ids)
            g_labels = _grok_labels(grok_ids)
            role = role_splits.get(str(aid), a.get("note") or "")
        else:
            side = "ai_only"
            mix = "ai_only"
            g_labels = []
            role = a.get("note") or "Grok同型なし（Jarvis／Slack／Mac本線）"
            tag = tag or ""
        mappings.append(
            {
                "side": side,
                "agent_id": str(aid),
                "agent_name": a.get("name") or "",
                "builder_tag": tag,
                "mixup_kind": mix,
                "grok_counterpart": cp,
                "grok_ids": grok_ids,
                "grok_labels": g_labels,
                "grok_department": "",
                "role_split": role,
            }
        )

    # 2) Grok Bot で AI社員のツイン未割当 → AI社員対応なし
    for bid, gb in sorted(bot_by_id.items(), key=lambda x: x[0]):
        if bid in covered_grok:
            continue
        code = gb.get("code") or ""
        label = f"{code} {gb.get('name') or ''}".strip() if code and code != "—" else (
            gb.get("name") or bid
        )
        mappings.append(
            {
                "side": "grok_only",
                "agent_id": "",
                "agent_name": "AI社員対応なし",
                "builder_tag": "",
                "mixup_kind": "grok_only",
                "grok_counterpart": bid,
                "grok_ids": [bid],
                "grok_labels": [label],
                "grok_department": gb.get("department_name") or "",
                "role_split": gb.get("work")
                or "AIエージェントチーム側に同系統の社員が未配置",
            }
        )

    counts = {
        "paired": sum(1 for m in mappings if m["side"] == "paired"),
        "ai_only": sum(1 for m in mappings if m["side"] == "ai_only"),
        "grok_only": sum(1 for m in mappings if m["side"] == "grok_only"),
        "all": len(mappings),
    }

    return {
        "updated": grok_reg.get("updated") or "",
        "index_doc": grok_reg.get("index_doc") or "",
        "mixup_doc": grok_reg.get("mixup_doc") or "",
        "pillars": grok_reg.get("pillars") or [],
        "departments": dept_out,
        "bots": bots_out,
        "mappings": mappings,
        "mapping_counts": counts,
        "note": (
            "対応表は全件。対応あり／AI社員のみ／Grokのみ（AI社員対応なし）を含む。"
            "〔Grok:◯◯〕は置き換えではなく並べて比較する相手。"
        ),
    }


def write_dashboard_json(data: dict, dry: bool) -> Path:
    """registry → jarvis-dashboard 投影 JSON."""
    depts = data.get("departments") or {}
    agents = data.get("agents") or {}
    builder = data.get("builder_source") or {}
    now = datetime.now(JST).isoformat(timespec="seconds")
    genre_reg = load_genre_registry()
    ai_genre_map, grok_genre_map, genres_skel = build_genre_maps(genre_reg)
    genre_name = {g["id"]: g["name"] for g in genres_skel}
    grok_payload = build_grok_payload(data, load_grok_registry())
    share_map = load_flowforge_share_map()

    for b in grok_payload.get("bots") or []:
        gid = grok_genre_map.get(str(b.get("department_id") or ""), "")
        b["genre_id"] = gid
        b["genre_name"] = genre_name.get(gid, "")
    for d in grok_payload.get("departments") or []:
        gid = grok_genre_map.get(str(d.get("id") or ""), "")
        d["genre_id"] = gid
        d["genre_name"] = genre_name.get(gid, "")

    dept_list = []
    for did, dept in sorted(depts.items(), key=lambda x: str(x[0])):
        sid = str(did)
        gid = ai_genre_map.get(sid, "")
        dept_list.append(
            {
                "id": sid,
                "name": dept.get("name") or "",
                "path": dept.get("path") or "",
                "genre_id": gid,
                "genre_name": genre_name.get(gid, ""),
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
        ff_id = a.get("flowforge_id") or ""
        ff_url = a.get("flowforge_url") or ""
        share = (
            share_map.get(str(aid))
            or a.get("flowforge_share_url")
            or (share_map.get(f"flow:{ff_id}") if ff_id else "")
            or ""
        )
        gid = ai_genre_map.get(str(dept_id), "")
        agent_list.append(
            {
                "id": str(aid),
                "name": a.get("name") or "",
                "path": a.get("path") or "",
                "department_id": str(dept_id),
                "department_name": dept_name,
                "genre_id": gid,
                "genre_name": genre_name.get(gid, ""),
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
                "flowforge_id": ff_id,
                "flowforge_url": ff_url,
                "flowforge_share_url": share,
                "flowforge_edit_url": flowforge_edit_via_account_chooser(ff_url),
            }
        )

    genres = enrich_genres_with_members(
        genres_skel,
        agent_list,
        list(grok_payload.get("bots") or []),
        list(grok_payload.get("mappings") or []),
    )

    payload = {
        "updated": now,
        "registry_updated": data.get("updated") or "",
        "flowforge_base": "https://flowforge-259747770348.asia-northeast1.run.app/",
        "flowforge_login_hint": FLOWFORGE_LOGIN_HINT,
        "flowforge_login_email": FLOWFORGE_LOGIN_EMAIL,
        "flowforge_open_note": (
            "Safari／Chrome で編集URLを開くと「同期失敗」「新しいフロー」になりやすいです。"
            "見るだけなら共有（閲覧）リンクを使う。"
            f" 編集は Cursor インブラウザで {FLOWFORGE_LOGIN_HINT}（{FLOWFORGE_LOGIN_EMAIL}）ログイン。"
        ),
        "builder": {
            "title": builder.get("title") or "",
            "url": builder.get("url") or "",
            "share_id": builder.get("share_id") or "",
        },
        "counts": counts,
        "genres": genres,
        "genre_note": genre_reg.get("note") or "",
        "departments": dept_list,
        "agents": agent_list,
        "grok": grok_payload,
    }
    if dry:
        print(
            f"  dashboard JSON (dry): {len(agent_list)} agents / "
            f"{len(grok_payload.get('bots') or [])} grok bots / "
            f"{len(genres)} genres → {DASH_JSON}"
        )
        return DASH_JSON
    DASH_JSON.parent.mkdir(parents=True, exist_ok=True)
    DASH_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"  dashboard: {DASH_JSON.relative_to(REPO)} "
        f"({len(agent_list)} agents / {len(grok_payload.get('bots') or [])} grok / "
        f"{len(genres)} genres)"
    )
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
        # ハブ直下の MD は Git 正本を Drive へ丸ごと写す（設計メモ・表紙含む。
        # Drive 側だけのメモは消さない＝上書きコピーのみ）
        for src in sorted(HUB.glob("*.md")):
            sync_drive(Path(src.name), False)
        for rel in ("agents_registry.yaml",):
            if (HUB / rel).exists():
                sync_drive(Path(rel), False)
        print(f"  drive: {DRIVE_HUB}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
