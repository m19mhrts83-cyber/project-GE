#!/usr/bin/env python3
"""アドバイザー週次材料パック（SB要約＋パートナー差分＋git＋Journalギャップ）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_advisor_weekly_pack.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_advisor_weekly_pack.py --apply
  ~/selenium_env/venv/bin/python scripts/jarvis_advisor_weekly_pack.py --stdout  # 応答ボディ相当

Cloud 本線は Vercel /api/advisor-weekly-pack（Mac スリープ可）。
本スクリプトは Mac／FRIDAY フォールバックと dry-run 用。
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
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from jarvis_bucho_bridge_lib import outbox_dir_for_target, sanitize_title  # noqa: E402
from jarvis_bucho_outbox_write import build_md, now_stamp  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
PRIVATE_ENV = REPO / ".env.jarvis_private"
ROUTING_PATH = REPO / "config" / "advisor_weekly_pack_routing.yaml"
STATE_PATH = REPO / ".jarvis_state" / "advisor_weekly_pack.json"
JOURNAL_ROOT = Path.home() / "Documents" / "500_Obsidian_r1" / "01_Journaling" / "★Journal"
PARTNERS_ROOT = Path.home() / (
    "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/"
    "C2_ルーティン作業/26_パートナー社への相談"
)
GSK_BASE = (os.environ.get("GSK_BASE_URL") or "https://www.genspark.ai").rstrip("/")
HEADING_RE = re.compile(
    r"^###\s+(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2})\s+(.+?)\s+[—\-]\s+(.+?)\s*[—\-]\s+(.+)\s*$"
)


def load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$", line)
        if m and not line.lstrip().startswith("#"):
            out[m.group(1)] = m.group(2).strip().strip("\"'")
    return out


def ensure_env() -> None:
    if (os.environ.get("GSK_API_KEY") or "").strip():
        return
    env = load_dotenv(PRIVATE_ENV)
    key = (env.get("GSK_API_KEY") or "").strip()
    if key:
        os.environ["GSK_API_KEY"] = key


def disabled() -> bool:
    if (os.environ.get("JARVIS_ADVISOR_WEEKLY_PACK_DISABLE") or "").strip() in (
        "1",
        "true",
        "yes",
    ):
        return True
    if STATE_PATH.is_file():
        try:
            st = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if st.get("disabled"):
                return True
        except (OSError, json.JSONDecodeError):
            pass
    return False


def now_jst() -> datetime:
    return datetime.now(JST)


def kinshu_range(today: date | None = None) -> tuple[date, date]:
    """直近の完了金締（土〜金）。今日が土曜〜金曜の途中なら直前金曜終わり。"""
    d = today or now_jst().date()
    # 直近の金曜（今日が金曜なら当日）
    days_since_fri = (d.weekday() - 4) % 7
    end = d - timedelta(days=days_since_fri)
    start = end - timedelta(days=6)
    return start, end


def load_routing() -> dict[str, Any]:
    if yaml is None or not ROUTING_PATH.is_file():
        return {"teams": {}, "unclassified_team": "hawk"}
    data = yaml.safe_load(ROUTING_PATH.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {"teams": {}}


def label_teams(title: str, summary: str, routing: dict[str, Any]) -> list[str]:
    blob = f"{title}\n{summary}".lower()
    teams = routing.get("teams") or {}
    hit: list[str] = []
    for team_id, spec in teams.items():
        kws = (spec or {}).get("keywords") or []
        for kw in kws:
            if str(kw).lower() in blob:
                hit.append(str(team_id))
                break
    if not hit:
        hit.append(str(routing.get("unclassified_team") or "hawk"))
    return hit


def gsk_meeting(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_env()
    key = (os.environ.get("GSK_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("GSK_API_KEY 未設定")
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{GSK_BASE}/api/tool_cli/meeting",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Api-Key": key,
            "X-GSK-CLI-Version": "jarvis-advisor-weekly-pack",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_sb_notes(start: date, end: date) -> tuple[list[dict[str, Any]], str | None]:
    """金締期間のノート＋summary。失敗時は ([], error)。"""
    notes: list[dict[str, Any]] = []
    err: str | None = None
    try:
        token: str | None = None
        while True:
            payload: dict[str, Any] = {"action": "list", "page_size": 50}
            if token:
                payload["continuation_token"] = token
            raw = gsk_meeting(payload)
            data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
            batch = data.get("notes") if isinstance(data.get("notes"), list) else []
            hit_older = False
            for n in batch:
                if not isinstance(n, dict):
                    continue
                created = str(n.get("created_at") or "")[:10]
                if not created:
                    continue
                try:
                    cd = date.fromisoformat(created)
                except ValueError:
                    continue
                if start <= cd <= end:
                    notes.append(n)
                elif cd < start:
                    hit_older = True
            if hit_older or not data.get("has_more"):
                break
            token = data.get("continuation_token")
            if not token:
                break
            if len(notes) >= 80:
                break

        enriched: list[dict[str, Any]] = []
        for n in notes[:40]:
            nid = n.get("id")
            summary = ""
            if nid:
                try:
                    det = gsk_meeting(
                        {
                            "action": "get",
                            "task_id": str(nid),
                            "detail_level": "summary",
                        }
                    )
                    d2 = det.get("data") if isinstance(det.get("data"), dict) else det
                    if isinstance(d2, dict):
                        summary = str(d2.get("summary") or d2.get("ai_summary") or "")
                except Exception as e:  # noqa: BLE001
                    summary = f"(summary取得失敗: {e})"
            enriched.append(
                {
                    "id": nid,
                    "title": n.get("title") or "(無題)",
                    "created_at": n.get("created_at"),
                    "duration_human": n.get("duration_human"),
                    "summary": summary[:1200],
                }
            )
        return enriched, None
    except Exception as e:  # noqa: BLE001
        return [], str(e)


def fetch_partner_diff(start: date, end: date) -> tuple[list[str], str | None]:
    if not PARTNERS_ROOT.is_dir():
        return [], f"partners root missing: {PARTNERS_ROOT}"
    lines: list[str] = []
    try:
        for folder in sorted(PARTNERS_ROOT.iterdir()):
            if not folder.is_dir() or folder.name.startswith("000_") or folder.name.startswith("."):
                continue
            if folder.name.startswith("815_"):
                continue
            md = folder / "5.やり取り.md"
            if not md.is_file():
                continue
            hits: list[str] = []
            for line in md.read_text(encoding="utf-8", errors="replace").splitlines():
                m = HEADING_RE.match(line)
                if not m:
                    continue
                raw_dt = m.group(1)  # YYYY/MM/DD HH:MM
                try:
                    d = date(int(raw_dt[0:4]), int(raw_dt[5:7]), int(raw_dt[8:10]))
                except ValueError:
                    continue
                if start <= d <= end:
                    hits.append(
                        f"- {raw_dt} {m.group(2).strip()} / {m.group(3).strip()}: "
                        f"{m.group(4).strip()[:120]}"
                    )
            if hits:
                lines.append(f"### {folder.name}")
                lines.extend(hits[:12])
                if len(hits) > 12:
                    lines.append(f"- …他 {len(hits) - 12} 件")
        return lines, None
    except Exception as e:  # noqa: BLE001
        return [], str(e)


def fetch_git_summary(start: date) -> tuple[list[str], str | None]:
    since = start.isoformat()
    try:
        log = subprocess.run(
            [
                "git",
                "-C",
                str(REPO),
                "log",
                f"--since={since}",
                "--pretty=format:%h %ad %s",
                "--date=short",
                "-n",
                "25",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        lines = [ln for ln in (log.stdout or "").splitlines() if ln.strip()]
        pr = subprocess.run(
            ["gh", "pr", "list", "--state", "open", "--limit", "10", "--json", "number,title,url"],
            capture_output=True,
            text=True,
            cwd=str(REPO),
            check=False,
        )
        pr_lines: list[str] = []
        if pr.returncode == 0 and pr.stdout.strip():
            for item in json.loads(pr.stdout):
                pr_lines.append(
                    f"- PR#{item.get('number')}: {item.get('title')} ({item.get('url')})"
                )
        out = ["#### commits"] + [f"- {x}" for x in lines[:20]]
        if pr_lines:
            out += ["#### open PRs"] + pr_lines
        if not lines and not pr_lines:
            out = ["- （期間内の commit / open PR なし）"]
        return out, None
    except Exception as e:  # noqa: BLE001
        return [], str(e)


def journal_text(start: date, end: date) -> str:
    chunks: list[str] = []
    d = start
    while d <= end:
        for candidate in (
            JOURNAL_ROOT / f"{d.isoformat()}.md",
            JOURNAL_ROOT / f"{d.strftime('%Y-%m')}" / f"{d.isoformat()}.md",
        ):
            if candidate.is_file():
                chunks.append(candidate.read_text(encoding="utf-8", errors="replace")[:4000])
                break
        d += timedelta(days=1)
    return "\n".join(chunks).lower()


def gap_candidates(
    sb_notes: list[dict[str, Any]],
    partner_lines: list[str],
    journal_blob: str,
) -> list[str]:
    gaps: list[str] = []
    for n in sb_notes:
        title = str(n.get("title") or "")
        # タイトルの主要語が Journal に無ければ候補
        tokens = [t for t in re.split(r"[\s　、。・:：/]+", title) if len(t) >= 2][:4]
        if not tokens:
            continue
        missing = [t for t in tokens if t.lower() not in journal_blob]
        if len(missing) >= max(1, len(tokens) // 2):
            gaps.append(
                f"- [SB] {n.get('created_at', '')[:10]} {title[:80]} "
                f"（Journalに薄い語: {', '.join(missing[:3])}）"
            )
    for line in partner_lines:
        if not line.startswith("- "):
            continue
        # 簡易: 見積・退去・要確認 等
        if any(k in line for k in ("見積", "退去", "要確認", "ご確認", "修繕", "空室")):
            key = line[2:40]
            if key.lower() not in journal_blob:
                gaps.append(f"- [メール] {line[2:100]}")
    if not gaps:
        gaps.append("- （機械候補なし。アドバイザー判断で「ギャップなし」可）")
    return gaps[:20]


def build_pack_md(
    *,
    start: date,
    end: date,
    sb_notes: list[dict[str, Any]],
    sb_err: str | None,
    partner_lines: list[str],
    partner_err: str | None,
    git_lines: list[str],
    git_err: str | None,
    routing: dict[str, Any],
) -> str:
    journal_blob = journal_text(start, end)
    gaps = gap_candidates(sb_notes, partner_lines, journal_blob)

    by_team: dict[str, list[dict[str, Any]]] = {
        "family": [],
        "somu": [],
        "partner_dx": [],
        "app_dev": [],
        "hawk": [],
    }
    for n in sb_notes:
        labels = label_teams(str(n.get("title") or ""), str(n.get("summary") or ""), routing)
        n = {**n, "labels": labels}
        for lab in labels:
            by_team.setdefault(lab, []).append(n)
        if "hawk" not in labels:
            by_team["hawk"].append(n)

    parts: list[str] = [
        f"# 週次材料パック · 金締 {start.isoformat()}〜{end.isoformat()}",
        f"生成: {now_jst().strftime('%Y-%m-%d %H:%M JST')} · Jarvis advisor_weekly_pack",
        "",
        "## A. SecondBrain（要約のみ・全文なし）",
    ]
    if sb_err:
        parts.append(f"- SB: 取得不可（{sb_err}）")
    else:
        parts.append(f"- 件数: {len(sb_notes)}")
        for n in sb_notes:
            labels = ",".join(n.get("labels") or label_teams(str(n["title"]), str(n.get("summary") or ""), routing))
            parts.append(
                f"- {str(n.get('created_at') or '')[:10]} | {n.get('duration_human') or '—'} | "
                f"**{n.get('title')}** `[{labels}]`\n"
                f"  - id: `{n.get('id')}`\n"
                f"  - summary: {(n.get('summary') or '（なし）').replace(chr(10), ' ')[:400]}"
            )

    parts += ["", "## B. パートナーやり取り（差分）"]
    if partner_err:
        parts.append(f"- 取得不可（{partner_err}）")
    elif not partner_lines:
        parts.append("- （期間内の見出しなし）")
    else:
        parts.extend(partner_lines)

    parts += ["", "## C. アプリ更新"]
    if git_err:
        parts.append(f"- 取得不可（{git_err}）")
    else:
        parts.extend(git_lines)

    parts += ["", "## D. Journalギャップ候補（必須・断定しない）"]
    parts.extend(gaps)

    parts += ["", "## E. チーム別フォーカス（SB抜粋）"]
    for team in ("family", "somu", "partner_dx", "app_dev"):
        parts.append(f"### {team}")
        items = by_team.get(team) or []
        if not items:
            parts.append("- （該当SBなし）")
        else:
            for n in items[:8]:
                parts.append(f"- {str(n.get('created_at') or '')[:10]} {n.get('title')}")

    parts += [
        "",
        "---",
        "使い方: ★Journalは理解の正本。全部の出来事が載っている前提にしない。",
        "返答に「Journalに無い重要」節を必ず1つ（該当なしならギャップなしと明記）。",
    ]
    return "\n".join(parts) + "\n"


def write_state(payload: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_outboxes(body: str, start: date, end: date, apply: bool) -> list[str]:
    day, hm = now_stamp()
    title = f"週次材料パック_{start.isoformat()}_{end.isoformat()}"
    targets = ("hawk", "family", "somu", "partner_dx", "app_dev")
    written: list[str] = []
    for target in targets:
        md = build_md(
            title=title,
            body=body,
            action="memo",
            priority="normal",
            target=target,
        )
        # チーム別は E 節だけ薄くしてもよいが、初版は共通本編を全先へ（hawk以外も全文可読）
        out_dir = outbox_dir_for_target(target)
        fname = f"{day}_{hm}_{sanitize_title(title)}_{target}.md"
        path = out_dir / fname
        if apply:
            path.write_text(md, encoding="utf-8")
        written.append(str(path))
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Advisor weekly materials pack")
    ap.add_argument("--dry-run", action="store_true", help="outbox に書かない")
    ap.add_argument("--apply", action="store_true", help="outbox に書く")
    ap.add_argument("--stdout", action="store_true", help="パック本文を stdout に出す")
    ap.add_argument("--end", default=None, help="金締金曜 YYYY-MM-DD（省略時=直近金曜）")
    args = ap.parse_args(argv)

    if disabled():
        print("📎 advisor_weekly_pack: disabled")
        return 0

    if args.end:
        end = date.fromisoformat(args.end)
        start = end - timedelta(days=6)
    else:
        start, end = kinshu_range()

    routing = load_routing()
    sb_notes, sb_err = fetch_sb_notes(start, end)
    # attach labels for rendering
    for n in sb_notes:
        n["labels"] = label_teams(str(n.get("title") or ""), str(n.get("summary") or ""), routing)

    partner_lines, partner_err = fetch_partner_diff(start, end)
    git_lines, git_err = fetch_git_summary(start)

    body = build_pack_md(
        start=start,
        end=end,
        sb_notes=sb_notes,
        sb_err=sb_err,
        partner_lines=partner_lines,
        partner_err=partner_err,
        git_lines=git_lines,
        git_err=git_err,
        routing=routing,
    )

    apply = bool(args.apply) and not args.dry_run
    paths = write_outboxes(body, start, end, apply=apply)

    write_state(
        {
            "last_run_at": now_jst().isoformat(),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "sb_count": len(sb_notes),
            "sb_error": sb_err,
            "partner_error": partner_err,
            "git_error": git_err,
            "outbox_paths": paths,
            "applied": apply,
        }
    )

    print(
        f"📎 advisor_weekly_pack {start}〜{end} · SB={len(sb_notes)}"
        f"{' · SB_ERR=' + sb_err if sb_err else ''}"
        f" · apply={apply}"
    )
    for p in paths:
        print(f"  → {p}")

    if args.stdout or args.dry_run:
        print("--- pack ---")
        print(body)

    return 0 if not sb_err else 0  # soft-fail


if __name__ == "__main__":
    raise SystemExit(main())
