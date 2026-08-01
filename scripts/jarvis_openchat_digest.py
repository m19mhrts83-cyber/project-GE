#!/usr/bin/env python3
"""
815 神大家オプチャの有益情報ダイジェスト → sync_meta.openchat_digest

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_openchat_digest.py
  python scripts/jarvis_openchat_digest.py --push
  python scripts/jarvis_openchat_digest.py --no-llm --push
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
OUT_PATH = REPO / ".jarvis_state" / "night_triage" / "openchat_digest.json"
OPENCHAT_BASE = Path(
    "~/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    "/C2_ルーティン作業/26_パートナー社への相談/815_神大家オプチャ"
).expanduser()

# 815-openchat-no-reply-proposal.mdc 準拠（キーワード粗いフィルタ）
THEME_HINTS: dict[str, tuple[str, ...]] = {
    "12東海北陸G": ("愛知", "岐阜", "戸建", "土地", "物件", "駐車場"),
    "11関西地域G": ("関西", "大阪", "融資", "管理", "物件"),
    "21中古APにチャレンジ": ("中古", "AP", "愛知", "岐阜", "物件"),
    "25神コンセプト物件にチャレンジ": ("コンセプト", "物件", "愛知", "岐阜"),
    "30空室相談G": ("空室", "募集", "内覧", "家賃", "入居"),
    "31修繕相談G": ("修繕", "リフォーム", "水漏れ", "設備"),
    "32売却相談G": ("売却", "査定", "出口"),
    "33融資相談G": ("融資", "銀行", "金利", "借入", "愛知"),
    "34保険相談G": ("保険", "火災", "賠償"),
    "35税金・確定申告G": ("税", "確定申告", "減価", "経費"),
    "39その他相談共有G": ("共有", "相談"),
}

EXCLUDE_PAT = re.compile(r"会社を紹介|業者を紹介|紹介してください")
HEADING_RE = re.compile(
    r"^###\s+(\d{4})[/-](\d{1,2})[/-](\d{1,2}).*"
)


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def slugify(name: str) -> str:
    from urllib.parse import quote

    return quote(name.strip().replace(" ", "_"), safe="")


def client():
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    return create_client(url, key)


def parse_recent_blocks(path: Path, since: date) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    blocks: list[dict[str, Any]] = []
    cur_date: date | None = None
    buf: list[str] = []
    subject = ""

    def flush() -> None:
        nonlocal buf, subject
        if cur_date and cur_date >= since and buf:
            body = "\n".join(buf)
            if EXCLUDE_PAT.search(body) and "紹介" in (subject + body):
                # 業者紹介依頼のみはスキップ（本文に有益情報もある場合は残す簡易判定）
                if re.search(r"会社を紹介してください|業者を紹介してください", body):
                    buf = []
                    subject = ""
                    return
            blocks.append(
                {
                    "date": cur_date.isoformat(),
                    "subject": subject,
                    "body": body[:1200],
                }
            )
        buf = []
        subject = ""

    for line in text.splitlines():
        hm = HEADING_RE.match(line.strip())
        if hm:
            flush()
            try:
                cur_date = date(int(hm.group(1)), int(hm.group(2)), int(hm.group(3)))
            except ValueError:
                cur_date = None
            continue
        if "**件名**" in line[:20]:
            subject = re.sub(r".*\*\*件名\*\*\s*:?\s*", "", line).strip()
        buf.append(line)
    flush()
    return blocks


def theme_hit(folder: str, text: str) -> bool:
    hints = THEME_HINTS.get(folder)
    if not hints:
        return False
    return any(h in text for h in hints)


def collect_candidates(days: int) -> list[dict[str, Any]]:
    since = date.today() - timedelta(days=days)
    out: list[dict[str, Any]] = []
    if not OPENCHAT_BASE.is_dir():
        return out
    for d in sorted(OPENCHAT_BASE.iterdir()):
        if not d.is_dir() or d.name.startswith("000_") or d.name.startswith("."):
            continue
        if d.name in ("東海飲み会幹事やりとり",):
            continue
        md = d / "5.やり取り.md"
        folder = d.name
        for b in parse_recent_blocks(md, since)[-15:]:
            blob = f"{b['subject']}\n{b['body']}"
            if folder in THEME_HINTS and not theme_hit(folder, blob):
                continue
            if folder not in THEME_HINTS:
                # 全体周知などはキーワード弱め: 物件・融資などがあれば
                if not any(
                    k in blob for k in ("物件", "融資", "空室", "修繕", "保険", "税", "売却")
                ):
                    continue
            out.append(
                {
                    "group": folder,
                    "date": b["date"],
                    "subject": b["subject"][:120],
                    "excerpt": re.sub(r"\s+", " ", b["body"])[:280],
                }
            )
    return out


def rule_digest(cands: list[dict[str, Any]]) -> dict[str, Any]:
    by: dict[str, list[dict[str, Any]]] = {}
    for c in cands:
        by.setdefault(c["group"], []).append(c)
    groups = []
    for name, items in sorted(by.items(), key=lambda x: x[0]):
        lines = []
        for it in items[:3]:
            s = (it.get("subject") or "").strip()
            ex = (it.get("excerpt") or "")[:100]
            lines.append(f"{it['date']}: {s or ex}"[:160])
        # 東海北陸 + 駐車場
        if name.startswith("12") and any("駐車場" in (i.get("excerpt") or "") for i in items):
            lines.insert(0, "【駐車場】本文に記載あり（詳細はやり取り参照）")
        groups.append(
            {
                "name": name,
                "slug": slugify(name),
                "lines": lines[:3],
                "updated_at": items[0]["date"] if items else None,
                "count": len(items),
            }
        )
    overview = (
        f"直近の有益候補 {len(cands)} 件・{len(groups)} グループ。"
        if cands
        else "直近の有益情報はありません。"
    )
    return {
        "generated_at": now_iso(),
        "overview": overview,
        "groups": groups,
        "via": "rule",
    }


def gemini_digest(cands: list[dict[str, Any]], api_key: str) -> dict[str, Any] | None:
    if not cands or not api_key:
        return None
    models = [
        (os.environ.get("GEMINI_MODEL") or "").strip(),
        "gemini-flash-latest",
        "gemini-flash-lite-latest",
    ]
    models = [m for i, m in enumerate(models) if m and m not in models[:i]]
    prompt = f"""あなたは不動産大家の秘書です。神大家オープンチャットの抜粋から、大家業に役立つ情報だけをグループ別に要約してください。
返信提案・対応催促は禁止。業者紹介依頼だけの投稿は無視。

入力JSON:
{json.dumps(cands[:60], ensure_ascii=False)}

次の JSON のみ（Markdown不可）:
{{
  "overview": "全体を1〜2文",
  "groups": [
    {{"name": "フォルダ名そのまま", "lines": ["2〜3行の要約"], "updated_at": "YYYY-MM-DD"}}
  ]
}}

ルール:
- groups の name は入力の group と一致
- lines は各グループ最大3行、各行120字以内
- 12東海北陸G で駐車場の記載があれば lines 先頭に「【駐車場】…」
- 該当が無ければ groups は空配列
"""
    for model in models:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2048},
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            continue
        cands_g = data.get("candidates") or []
        if not cands_g:
            continue
        parts = (((cands_g[0] or {}).get("content") or {}).get("parts")) or []
        text = "\n".join(
            p.get("text", "") for p in parts if isinstance(p, dict) and p.get("text")
        ).strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{[\s\S]*\}", text)
            if not m:
                continue
            try:
                obj = json.loads(m.group(0))
            except json.JSONDecodeError:
                continue
        if not isinstance(obj, dict):
            continue
        groups = []
        for g in obj.get("groups") or []:
            if not isinstance(g, dict):
                continue
            name = str(g.get("name") or "").strip()
            if not name:
                continue
            lines = [str(x).strip()[:160] for x in (g.get("lines") or []) if str(x).strip()][
                :3
            ]
            if not lines:
                continue
            groups.append(
                {
                    "name": name,
                    "slug": slugify(name),
                    "lines": lines,
                    "updated_at": g.get("updated_at"),
                    "count": len(lines),
                }
            )
        return {
            "generated_at": now_iso(),
            "overview": str(obj.get("overview") or "")[:400]
            or f"有益候補 {len(groups)} グループ。",
            "groups": groups,
            "via": "gemini",
        }
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    args = ap.parse_args(argv)

    cands = collect_candidates(args.days)
    digest = rule_digest(cands)
    if not args.no_llm:
        key = (os.environ.get("GEMINI_API_KEY") or "").strip()
        gem = gemini_digest(cands, key)
        if gem:
            digest = gem

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(digest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"# wrote {OUT_PATH} groups={len(digest.get('groups') or [])} via={digest.get('via')}")

    if args.push:
        sb = client()
        now = datetime.now(tz=JST).isoformat()
        sb.table("sync_meta").upsert(
            {
                "key": "openchat_digest",
                "value": json.dumps(digest, ensure_ascii=False),
                "updated_at": now,
            }
        ).execute()
        print("# pushed sync_meta.openchat_digest")

    print(json.dumps({"groups": len(digest.get("groups") or []), "via": digest.get("via")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
