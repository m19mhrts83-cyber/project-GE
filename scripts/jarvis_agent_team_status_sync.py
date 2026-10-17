#!/usr/bin/env python3
"""AIエージェントチーム — 状態マーカー／部門状態ボードを registry から同期.

正本: docs/AIエージェントチーム/agents_registry.yaml の status
ルール: docs/AIエージェントチーム/22_運用状態の識別_20261011.md
Grok: config/grok_bots_registry.yaml（組織・社員・対応表）
ジャンル: config/agent_team_genres.yaml（上位分類・ダッシュ投影）
権限: config/agent_team_permissions.yaml（実行権限・サイトログイン俯瞰）
運用: config/agent_team_ops.yaml（合図4種・手順書・報告先メタ）

社員フォルダ作成・status 変更・権限／秘密／合図・報告先の追加のあと必ず実行（Drive 写しも任意で可）。
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
PERMS_REG = REPO / "config" / "agent_team_permissions.yaml"
OPS_REG = REPO / "config" / "agent_team_ops.yaml"
PERM_MD = HUB / "25_実行権限一覧_20261015.md"
OPS_MD = HUB / "26_合図手順報告一覧_20261015.md"
DASH_JSON = REPO / "apps" / "jarvis-dashboard" / "data" / "agentTeam.json"
GITHUB_BLOB = "https://github.com/m19mhrts83-cyber/project-GE/blob/main"
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


def load_permissions_registry() -> dict:
    if not PERMS_REG.is_file():
        return {}
    return yaml.safe_load(PERMS_REG.read_text(encoding="utf-8")) or {}


def load_ops_registry() -> dict:
    if not OPS_REG.is_file():
        return {}
    return yaml.safe_load(OPS_REG.read_text(encoding="utf-8")) or {}


TRIGGER_KIND_ORDER = ("human", "schedule", "event", "watch")

TRIGGER_KIND_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("human", re.compile(r"人が頼む|人依頼|手動")),
    ("schedule", re.compile(r"時間|スケジュール|定時|cron|launchd|GHA|毎朝|毎週|毎日")),
    ("event", re.compile(r"何かが届いた|イベント|届いたら|inbox|取込後|Webhook|consult-action")),
    ("watch", re.compile(r"変化|失敗|見回り|Fail|異常|停滞|逼迫|枠切れ|鮮度")),
]


def _parse_claude_triggers(claude: Path) -> tuple[list[dict], bool]:
    """CLAUDE.md「## 2. 動き出す合図」のチェックボックスを4種に正規化."""
    if not claude.is_file():
        return [], False
    text = claude.read_text(encoding="utf-8")
    m = re.search(
        r"##\s*2\.\s*動き出す合図[^\n]*\n(.*?)(?=\n##\s*\d|\n##\s*状態|\Z)",
        text,
        re.DOTALL,
    )
    if not m:
        return [], False
    body = m.group(1)
    items: list[dict] = []
    seen: set[str] = set()
    for line in body.splitlines():
        cm = re.match(r"^[-*]\s*\[([xX ])\]\s*(.+)$", line.strip())
        if not cm:
            continue
        checked = cm.group(1).lower() == "x"
        raw = cm.group(2).strip()
        # "人が頼む: detail" / "**時間（本線）**: detail"
        if "：" in raw:
            label_part, detail = raw.split("：", 1)
        elif ":" in raw:
            label_part, detail = raw.split(":", 1)
        else:
            label_part, detail = raw, ""
        label_part = label_part.strip()
        detail = detail.strip()
        kind_id = ""
        for kid, pat in TRIGGER_KIND_PATTERNS:
            if pat.search(re.sub(r"[*_`]", "", label_part)):
                kind_id = kid
                break
        if not kind_id:
            continue
        if kind_id in seen:
            # 同じ種別の追記行 → detail を結合
            for it in items:
                if it["id"] == kind_id and detail:
                    prev = it.get("detail") or ""
                    it["detail"] = (prev + " / " + detail).strip(" /") if prev else detail
                    if checked:
                        it["on"] = True
            continue
        seen.add(kind_id)
        items.append(
            {
                "id": kind_id,
                "on": checked,
                "detail": detail or re.sub(r"[*_`]", "", label_part),
                "raw": raw[:200],
            }
        )
    filled = any(it.get("on") for it in items)
    return items, filled


def _trigger_kinds_from_registry(trigger: str, ops_reg: dict) -> list[str]:
    """registry.trigger 文言から4種 ID を推定（CLAUDE 未記入の補完）."""
    t = trigger or ""
    hint_map: dict = ops_reg.get("trigger_hint_map") or {}
    found: list[str] = []
    for key, kinds in hint_map.items():
        if key and key in t:
            for k in kinds or []:
                if k not in found:
                    found.append(str(k))
    # 追加ヒューリスティック
    for kid, pat in TRIGGER_KIND_PATTERNS:
        if pat.search(t) and kid not in found:
            found.append(kid)
    return found


def _parse_claude_reports(claude: Path) -> list[dict]:
    """CLAUDE.md「## 4. 報告先」表を抽出."""
    if not claude.is_file():
        return []
    text = claude.read_text(encoding="utf-8")
    m = re.search(
        r"##\s*4\.\s*報告先\s*\n(.*?)(?=\n##\s*\d|\n##\s*状態|\Z)",
        text,
        re.DOTALL,
    )
    if not m:
        return []
    rows: list[dict] = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        kind, dest = cells[0], cells[1]
        if kind in ("種別", "---") or set(kind) <= {"-", "—"}:
            continue
        if not kind:
            continue
        channels: list[str] = []
        for ch in ("report", "consult", "ops"):
            if re.search(rf"#\s*{ch}\b|`#{ch}`", dest, re.I):
                channels.append(ch)
        rows.append({"kind": kind, "destination": dest, "channels": channels})
    return rows


def _collect_procedure_docs(folder: Path, agent_path: str, ops_reg: dict) -> list[dict]:
    """社員フォルダ内の手順書リンク一覧."""
    if not folder.is_dir():
        return []
    basenames = list(ops_reg.get("procedure_basenames") or [])
    globs = list(ops_reg.get("procedure_doc_globs") or [])
    out: list[dict] = []
    seen: set[str] = set()

    def add(rel: str, title: str = "") -> None:
        rel = rel.replace("\\", "/")
        if rel in seen:
            return
        seen.add(rel)
        hub_rel = f"docs/AIエージェントチーム/{agent_path}/{rel}".replace("//", "/")
        out.append(
            {
                "title": title or Path(rel).name,
                "path": hub_rel,
                "url": f"{GITHUB_BLOB}/{hub_rel}",
                "kind": "doc",
            }
        )

    for name in basenames:
        if (folder / name).is_file():
            add(name)
    for pattern in globs:
        for p in sorted(folder.glob(pattern)):
            if p.is_file():
                add(str(p.relative_to(folder)))
    return out


def _channels_from_registry_report(report: str) -> list[str]:
    r = (report or "").strip().lstrip("#").lower()
    if not r:
        return []
    if r in ("report", "consult", "ops"):
        return [r]
    found = []
    for ch in ("report", "consult", "ops"):
        if ch in r:
            found.append(ch)
    return found


def build_agent_ops(
    aid: str,
    folder: Path,
    agent_path: str,
    registry_row: dict,
    ops_reg: dict,
    flowforge_url: str = "",
    flowforge_share_url: str = "",
) -> dict:
    """AI社員の合図・手順・報告先オブジェクト."""
    kinds_meta = {k["id"]: k for k in (ops_reg.get("trigger_kinds") or []) if k.get("id")}
    claude = folder / "CLAUDE.md"
    triggers, triggers_filled = _parse_claude_triggers(claude)
    if not triggers_filled:
        # registry から補完（on=True 推定）
        for kid in _trigger_kinds_from_registry(registry_row.get("trigger") or "", ops_reg):
            meta = kinds_meta.get(kid) or {}
            triggers.append(
                {
                    "id": kid,
                    "on": True,
                    "detail": registry_row.get("schedule")
                    or registry_row.get("trigger")
                    or (meta.get("label") or kid),
                    "raw": "",
                    "from_registry": True,
                }
            )
        triggers_filled = bool(triggers)

    # 不足種別を off で埋めて4種揃える（ダッシュ表示用）
    have = {t["id"] for t in triggers}
    for kid in TRIGGER_KIND_ORDER:
        if kid not in have:
            meta = kinds_meta.get(kid) or {}
            triggers.append(
                {
                    "id": kid,
                    "on": False,
                    "detail": "",
                    "raw": "",
                }
            )
    triggers.sort(key=lambda t: TRIGGER_KIND_ORDER.index(t["id"]) if t["id"] in TRIGGER_KIND_ORDER else 99)

    on_ids = [t["id"] for t in triggers if t.get("on")]
    on_labels = [
        (kinds_meta.get(i) or {}).get("short")
        or (kinds_meta.get(i) or {}).get("label")
        or i
        for i in on_ids
    ]

    reports = _parse_claude_reports(claude)
    primary = _channels_from_registry_report(registry_row.get("report") or "")
    report_channels: list[str] = list(primary)
    for row in reports:
        for ch in row.get("channels") or []:
            if ch not in report_channels:
                report_channels.append(ch)

    procedures = _collect_procedure_docs(folder, agent_path, ops_reg)
    if flowforge_share_url or flowforge_url:
        procedures.insert(
            0,
            {
                "title": "FlowForge（作業フロー）",
                "path": "",
                "url": flowforge_share_url or flowforge_url,
                "kind": "flowforge",
            },
        )

    when = (registry_row.get("schedule") or "").strip()
    if not when:
        # CLAUDE の on 詳細から要約
        bits = [t.get("detail") or "" for t in triggers if t.get("on") and t.get("detail")]
        when = " / ".join(bits)[:240] if bits else ""

    return {
        "trigger_kinds": triggers,
        "trigger_kinds_on": on_ids,
        "trigger_kinds_label": " · ".join(on_labels) if on_labels else "（未記入）",
        "triggers_filled": triggers_filled,
        "when": when,
        "registry_trigger": registry_row.get("trigger") or "",
        "registry_schedule": registry_row.get("schedule") or "",
        "primary_report": (registry_row.get("report") or "").strip(),
        "report_channels": report_channels,
        "reports": reports,
        "procedures": procedures,
        "procedure_count": len(procedures),
        "source": "claude+registry+ops_yaml",
    }


def build_bot_ops(bot_row: dict, ops_reg: dict) -> dict:
    """Grok Bot の合図・報告先（簡易）."""
    schedule = (bot_row.get("schedule") or "").strip()
    kinds: list[dict] = []
    on_ids: list[str] = []
    # 多くは時間 or 依頼。schedule 文言から推定
    inferred = _trigger_kinds_from_registry(schedule or "依頼時", ops_reg)
    if not inferred:
        inferred = ["schedule"] if schedule else ["human"]
    kinds_meta = {k["id"]: k for k in (ops_reg.get("trigger_kinds") or []) if k.get("id")}
    for kid in TRIGGER_KIND_ORDER:
        on = kid in inferred
        if on:
            on_ids.append(kid)
        detail = ""
        if on:
            detail = schedule if kid == "schedule" else (bot_row.get("work") or "")
        kinds.append({"id": kid, "on": on, "detail": detail})
    channel = (bot_row.get("channel") or "").strip()
    return {
        "trigger_kinds": kinds,
        "trigger_kinds_on": on_ids,
        "trigger_kinds_label": " · ".join(
            (kinds_meta.get(i) or {}).get("short") or i for i in on_ids
        )
        or "—",
        "when": schedule or "依頼時／統括経由",
        "primary_report": channel or "Grok チャンネル",
        "report_channels": [],
        "reports": [
            {
                "kind": "Grok チャンネル",
                "destination": channel or "（registry.channel）",
                "channels": [],
            }
        ],
        "procedures": [
            {
                "title": "paste 正本",
                "path": bot_row.get("paste") or "",
                "url": (
                    f"{GITHUB_BLOB}/{bot_row.get('paste')}"
                    if bot_row.get("paste")
                    else ""
                ),
                "kind": "paste",
            }
        ]
        if bot_row.get("paste")
        else [],
        "procedure_count": 1 if bot_row.get("paste") else 0,
        "source": "grok_registry+ops_yaml",
    }


def write_ops_md(agent_list: list[dict], grok_bots: list[dict], ops_reg: dict, dry: bool) -> Path:
    """人向け 合図・手順・報告一覧 MD."""
    today = date.today().isoformat()
    kinds = ops_reg.get("trigger_kinds") or []
    lines = [
        "# 合図・手順書・報告先一覧",
        "",
        f"**更新**: {today}（`jarvis_agent_team_status_sync.py` が再生成）",
        f"**メタ**: [`config/agent_team_ops.yaml`](../../config/agent_team_ops.yaml)",
        f"**ダッシュ**: `/agent-team` →「運用」タブ",
        "",
        "## 動き出す合図（4種・友利さん／いけとも）",
        "",
        "| ID | 呼び名 | 意味 |",
        "|---|---|---|",
    ]
    for k in kinds:
        lines.append(
            f"| `{k.get('id')}` | {k.get('label')} | {k.get('meaning')} |"
        )
    lines += [
        "",
        "## AIエージェントチーム",
        "",
        "| ID | 名前 | 合図（4種） | 具体的に動くとき | 主報告 | 手順書 |",
        "|---|---|---|---|---|---|",
    ]
    for a in agent_list:
        o = a.get("ops") or {}
        procs = o.get("procedures") or []
        proc_n = len(procs)
        proc_cell = f"{proc_n}件" if proc_n else "—"
        if procs and procs[0].get("kind") == "flowforge":
            proc_cell = f"FF＋{max(0, proc_n - 1)}"
        lines.append(
            "| `{id}` | {name} | {kinds} | {when} | {rep} | {proc} |".format(
                id=a.get("id") or "",
                name=(a.get("name") or "").replace("|", "/"),
                kinds=(o.get("trigger_kinds_label") or "—").replace("|", "/"),
                when=(o.get("when") or "—").replace("|", "/")[:80],
                rep=("#" + (o.get("primary_report") or "").lstrip("#"))
                if o.get("primary_report")
                else "—",
                proc=proc_cell,
            )
        )
    lines += [
        "",
        "## Grok Bot（参考）",
        "",
        "| コード | 名前 | 合図 | スケジュール | チャンネル | paste |",
        "|---|---|---|---|---|---|",
    ]
    for b in grok_bots:
        o = b.get("ops") or {}
        paste = ""
        for p in o.get("procedures") or []:
            if p.get("kind") == "paste":
                paste = p.get("path") or ""
                break
        lines.append(
            "| {code} | {name} | {kinds} | {when} | {ch} | {paste} |".format(
                code=b.get("code") or "—",
                name=(b.get("name") or "").replace("|", "/"),
                kinds=(o.get("trigger_kinds_label") or "—").replace("|", "/"),
                when=(o.get("when") or "—").replace("|", "/")[:60],
                ch=(b.get("channel") or "—").replace("|", "/")[:40],
                paste=(paste or "—").replace("|", "/"),
            )
        )
    lines += [
        "",
        "## 更新手順",
        "",
        "1. 社員 `CLAUDE.md` §2（合図）／§4（報告）／手順 MD を直す",
        "2. 必要なら `agents_registry.yaml` の `trigger` / `schedule` / `report`",
        "3. `python scripts/jarvis_agent_team_status_sync.py`",
        "4. `agentTeam.json` を commit＋push",
        "",
    ]
    body = "\n".join(lines)
    if not dry:
        OPS_MD.write_text(body, encoding="utf-8")
        print(f"  ops MD: {OPS_MD.relative_to(REPO)}")
    else:
        print(f"  ops MD (dry): → {OPS_MD}")
    return OPS_MD


def _parse_claude_permission_methods(claude: Path) -> tuple[list[dict], str]:
    """CLAUDE.md「## 3. 実行権限」表と人が確かめる行を抽出."""
    if not claude.is_file():
        return [], ""
    text = claude.read_text(encoding="utf-8")
    m = re.search(
        r"##\s*3\.\s*実行権限\s*\n(.*?)(?=\n##\s*\d|\n##\s*状態|\Z)",
        text,
        re.DOTALL,
    )
    if not m:
        return [], ""
    body = m.group(1)
    methods: list[dict] = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        name, level = cells[0], cells[1]
        detail = cells[2] if len(cells) > 2 else ""
        if name in ("方法", "---") or set(name) <= {"-", "—", "–"}:
            continue
        if not name:
            continue
        # 空の level/detail だけの雛形行は「未記入」扱いのため残す
        methods.append(
            {
                "name": name,
                "level": level or "",
                "detail": detail or "",
            }
        )
    human = ""
    hm = re.search(
        r"\*\*人が確かめる[^*]*\*\*\s*[:：]?\s*(.+)",
        body,
    )
    if hm:
        human = re.sub(r"\s+", " ", hm.group(1)).strip()
    return methods, human


def _parse_env_example_keys(folder: Path) -> list[str]:
    """`.env.example` のキー名のみ（値は捨てる・例コメント含む未設定キーも拾う）."""
    path = folder / ".env.example"
    if not path.is_file():
        return []
    keys: list[str] = []
    seen: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("# この社員") or line.startswith("# 追加"):
            continue
        # "# KEY=" or "KEY=" or "# 例:" skipped
        if line.startswith("# 例"):
            continue
        m = re.match(r"^#?\s*([A-Z][A-Z0-9_]*)\s*=", line)
        if not m:
            continue
        key = m.group(1)
        if key in ("SOME_API_KEY",):
            continue
        if key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def _methods_filled(methods: list[dict]) -> bool:
    """level か detail が1つでも埋まっていれば記入済み."""
    for row in methods:
        if (row.get("level") or "").strip() or (row.get("detail") or "").strip():
            return True
    return False


def _site_logins_summary(logins: list[dict]) -> str:
    if not logins:
        return "なし"
    parts = []
    for s in logins:
        svc = (s.get("service") or "").strip()
        acc = (s.get("access") or "").strip()
        if svc and acc:
            parts.append(f"{svc}（{acc}）")
        elif svc:
            parts.append(svc)
    return " · ".join(parts) if parts else "なし"


def build_agent_permissions(
    aid: str,
    folder: Path,
    perms_reg: dict,
    registry_note: str = "",
) -> dict:
    """AI社員1体の権限オブジェクト（ダッシュ投影用）."""
    defaults = (perms_reg.get("defaults") or {}).get("ai") or {}
    override = ((perms_reg.get("agents") or {}).get(str(aid)) or {})
    methods, human_from_md = _parse_claude_permission_methods(folder / "CLAUDE.md")
    env_keys = _parse_env_example_keys(folder)
    site_logins = list(override.get("site_logins") or [])
    can_do = (
        (override.get("can_do") or "").strip()
        or (registry_note or "").strip()
        or ""
    )
    human_gate = (
        (override.get("human_gate") or "").strip()
        or human_from_md
        or (defaults.get("human_gate") or "お金・外に出す・消す")
    )
    filled = _methods_filled(methods)
    has_site = bool(site_logins)
    return {
        "can_do": can_do[:280],
        "methods": methods,
        "methods_filled": filled,
        "env_keys": env_keys,
        "site_logins": site_logins,
        "site_logins_summary": _site_logins_summary(site_logins),
        "has_site_logins": has_site,
        "human_gate": human_gate[:320],
        "secrets_note": (override.get("secrets_note") or defaults.get("secrets_note") or ""),
        "source": "claude+permissions_yaml",
    }


def build_bot_permissions(bid: str, bot_row: dict, perms_reg: dict) -> dict:
    """Grok Bot 1体の権限オブジェクト."""
    defaults = (perms_reg.get("defaults") or {}).get("grok") or {}
    override = ((perms_reg.get("bots") or {}).get(str(bid)) or {})
    site_logins = list(override.get("site_logins") or [])
    can_do = (
        (override.get("can_do") or "").strip()
        or (bot_row.get("work") or "").strip()
    )
    secrets_policy = (
        (override.get("secrets_policy") or "").strip()
        or (defaults.get("secrets_policy") or "none")
    )
    return {
        "can_do": can_do[:280],
        "exec_level": bot_row.get("exec_level") or "",
        "secrets_policy": secrets_policy,
        "secrets_note": (
            override.get("secrets_note")
            or defaults.get("secrets_note")
            or ""
        ),
        "site_logins": site_logins,
        "site_logins_summary": _site_logins_summary(site_logins),
        "has_site_logins": bool(site_logins),
        "human_gate": (
            (override.get("human_gate") or "").strip()
            or (defaults.get("human_gate") or "")
        ),
        "source": "grok_registry+permissions_yaml",
    }


def write_permissions_md(
    agent_list: list[dict],
    grok_bots: list[dict],
    perms_reg: dict,
    dry: bool,
) -> Path:
    """人向け一覧 MD を sync で再生成."""
    today = date.today().isoformat()
    lines = [
        "# 実行権限・秘密アクセス一覧",
        "",
        f"**更新**: {today}（`jarvis_agent_team_status_sync.py` が再生成）",
        f"**正本 YAML**: [`config/agent_team_permissions.yaml`](../../config/agent_team_permissions.yaml)",
        f"**ダッシュ**: `/agent-team` →「権限」タブ",
        "",
        "## 方針",
        "",
        "- **値は書かない**（キー名・サービス名・アクセス種別のみ）",
        "- AI社員: `CLAUDE.md` §3 ＋ 本 YAML の `can_do`／`site_logins` ＋ `.env.example`",
        "- Grok Bot: 既定はサイトID／PWなし（JarvisBox フォーク）。例外だけ YAML `bots:` に追記",
        "",
        "## AIエージェントチーム",
        "",
        "| ID | 名前 | できること | サイト／ログイン | envキー | 人が確かめる |",
        "|---|---|---|---|---|---|",
    ]
    for a in agent_list:
        p = a.get("permissions") or {}
        keys = " · ".join(p.get("env_keys") or []) or "—"
        lines.append(
            "| `{id}` | {name} | {can} | {site} | {keys} | {gate} |".format(
                id=a.get("id") or "",
                name=a.get("name") or "",
                can=(p.get("can_do") or "—").replace("|", "/"),
                site=(p.get("site_logins_summary") or "なし").replace("|", "/"),
                keys=keys.replace("|", "/"),
                gate=(p.get("human_gate") or "—").replace("|", "/")[:80],
            )
        )
    lines += [
        "",
        "## Grok Bot（秘密は原則なし）",
        "",
        f"> {(perms_reg.get('defaults') or {}).get('grok', {}).get('secrets_note') or ''}",
        "",
        "| コード | 名前 | できること | 実行レベル | サイト／ログイン |",
        "|---|---|---|---|---|",
    ]
    for b in grok_bots:
        p = b.get("permissions") or {}
        code = b.get("code") or "—"
        lines.append(
            "| {code} | {name} | {can} | {lvl} | {site} |".format(
                code=code,
                name=b.get("name") or "",
                can=(p.get("can_do") or "—").replace("|", "/"),
                lvl=(p.get("exec_level") or b.get("exec_level") or "—").replace("|", "/"),
                site=(p.get("site_logins_summary") or "なし").replace("|", "/"),
            )
        )
    lines += [
        "",
        "## サイトログインあり（要注目）",
        "",
    ]
    flagged = [
        a
        for a in agent_list
        if (a.get("permissions") or {}).get("has_site_logins")
    ] + [
        b
        for b in grok_bots
        if (b.get("permissions") or {}).get("has_site_logins")
    ]
    if not flagged:
        lines.append("（現時点で Grok 側の例外なし。AI社員は上表の「サイト／ログイン」列）")
    else:
        lines.append("| 側 | ID | サービス |")
        lines.append("|---|---|---|")
        for row in flagged:
            side = "AI" if "department_id" in row and str(row.get("id", "")).isdigit() else "Grok"
            # AI ids are numeric strings; bots are not
            rid = str(row.get("id") or "")
            side = "AI" if rid.isdigit() else "Grok"
            p = row.get("permissions") or {}
            for s in p.get("site_logins") or []:
                lines.append(
                    f"| {side} | `{rid}` | {(s.get('service') or '').replace('|', '/')} |"
                )
    lines += [
        "",
        "## 更新手順",
        "",
        "1. `config/agent_team_permissions.yaml` と社員 `CLAUDE.md` / `.env.example` を直す",
        "2. `python scripts/jarvis_agent_team_status_sync.py`",
        "3. `apps/jarvis-dashboard/data/agentTeam.json` を commit＋push（本番ダッシュ反映）",
        "",
    ]
    body = "\n".join(lines)
    if not dry:
        PERM_MD.write_text(body, encoding="utf-8")
        print(f"  permissions MD: {PERM_MD.relative_to(REPO)}")
    else:
        print(f"  permissions MD (dry): → {PERM_MD}")
    return PERM_MD


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


def build_grok_payload(
    agents_reg: dict,
    grok_reg: dict,
    perms_reg: dict | None = None,
    ops_reg: dict | None = None,
) -> dict:
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

    perms_reg = perms_reg if perms_reg is not None else load_permissions_registry()
    ops_reg = ops_reg if ops_reg is not None else load_ops_registry()
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
            row["permissions"] = build_bot_permissions(bid, row, perms_reg)
            row["ops"] = build_bot_ops(row, ops_reg)
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
    perms_reg = load_permissions_registry()
    ops_reg = load_ops_registry()
    ai_genre_map, grok_genre_map, genres_skel = build_genre_maps(genre_reg)
    genre_name = {g["id"]: g["name"] for g in genres_skel}
    grok_payload = build_grok_payload(
        data, load_grok_registry(), perms_reg, ops_reg
    )
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
        permissions = build_agent_permissions(
            str(aid),
            folder,
            perms_reg,
            registry_note=a.get("note") or "",
        )
        ops = build_agent_ops(
            str(aid),
            folder,
            a.get("path") or "",
            a,
            ops_reg,
            flowforge_url=ff_url,
            flowforge_share_url=share,
        )
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
                "permissions": permissions,
                "ops": ops,
            }
        )

    genres = enrich_genres_with_members(
        genres_skel,
        agent_list,
        list(grok_payload.get("bots") or []),
        list(grok_payload.get("mappings") or []),
    )

    site_login_agent_ids = [
        a["id"] for a in agent_list if (a.get("permissions") or {}).get("has_site_logins")
    ]
    site_login_bot_ids = [
        b["id"]
        for b in (grok_payload.get("bots") or [])
        if (b.get("permissions") or {}).get("has_site_logins")
    ]

    payload = {
        "updated": now,
        "registry_updated": data.get("updated") or "",
        "permissions_updated": perms_reg.get("updated") or "",
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
        "permissions_meta": {
            "defaults": perms_reg.get("defaults") or {},
            "site_login_agent_ids": site_login_agent_ids,
            "site_login_bot_ids": site_login_bot_ids,
            "doc": "docs/AIエージェントチーム/25_実行権限一覧_20261015.md",
            "yaml": "config/agent_team_permissions.yaml",
            "note": (
                "サイトID／パスワードを渡したら config/agent_team_permissions.yaml を更新し、"
                "本 sync → agentTeam.json を push すること。"
            ),
        },
        "ops_meta": {
            "updated": ops_reg.get("updated") or "",
            "trigger_kinds": ops_reg.get("trigger_kinds") or [],
            "slack_channels": ops_reg.get("slack_channels") or {},
            "doc": "docs/AIエージェントチーム/26_合図手順報告一覧_20261015.md",
            "yaml": "config/agent_team_ops.yaml",
            "note": (
                ops_reg.get("note")
                or "合図・手順書・報告先は CLAUDE.md と registry が正。変更後は sync → push。"
            ),
        },
    }
    write_permissions_md(
        agent_list, list(grok_payload.get("bots") or []), perms_reg, dry
    )
    write_ops_md(agent_list, list(grok_payload.get("bots") or []), ops_reg, dry)
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
        f"{len(genres)} genres / site_logins AI={len(site_login_agent_ids)} "
        f"Grok={len(site_login_bot_ids)})"
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
        # Drive ハブ直下は入口だけ。番号付き設計MDは 90_ハブ文書/ へ写す
        # （Git 正本は docs/AIエージェントチーム/ 直下のまま＝相対リンク維持）
        drive_root_keep = {
            "00_このフォルダ.md",
            "00_チーム索引.md",
            "CLAUDE.md",
            "AGENTS.md",
        }
        docs_subdir = Path("90_ハブ文書")
        for src in sorted(HUB.glob("*.md")):
            if src.name in drive_root_keep:
                sync_drive(Path(src.name), False)
            else:
                sync_drive(docs_subdir / src.name, False)
                # 旧配置（Drive直下）の残骸を消す
                stale = DRIVE_HUB / src.name
                if stale.is_file():
                    stale.unlink(missing_ok=True)
        for rel in ("agents_registry.yaml",):
            if (HUB / rel).exists():
                sync_drive(Path(rel), False)
        # Drive 側の 90_ 案内（Git に無い場合のみ作る／更新は上書きしない方針なら skip）
        guide = DRIVE_HUB / docs_subdir / "00_このフォルダ.md"
        if not guide.is_file():
            guide.parent.mkdir(parents=True, exist_ok=True)
            guide.write_text(
                "# 90_ハブ文書（Drive）\n\n"
                "番号付き設計・進捗 MD の置き場。"
                "Git 正本は `docs/AIエージェントチーム/` 直下。\n",
                encoding="utf-8",
            )
        print(f"  drive: {DRIVE_HUB}（ハブMD→90_ハブ文書／入口は直下）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
