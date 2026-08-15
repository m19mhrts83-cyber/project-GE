#!/usr/bin/env python3
"""
パートナー以外の pending メールからジャンル別ダイジェストを生成し sync_meta へ保存。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_other_mail_digest.py
  python scripts/jarvis_other_mail_digest.py --push
  python scripts/jarvis_other_mail_digest.py --no-llm --push
  python scripts/jarvis_other_mail_digest.py --reclassify --push

呼び出し元: jarvis_dashboard_push / jarvis_gha_gmail_triage（push 後）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_DIR = REPO / ".jarvis_state" / "night_triage"
OUT_PATH = STATE_DIR / "other_mail_digest.json"

# id → label（不動産・AIは細かく）
GENRE_LABELS: dict[str, str] = {
    "re_mgmt_news": "不動産 / 管理・市況ニュース",
    "re_seminar": "不動産 / セミナー・勉強会",
    "re_finance": "不動産 / 融資・金利",
    "re_other": "不動産 / その他",
    "ai_models": "AI / モデル・研究",
    "ai_tools": "AI / ツール・プロダクト",
    "ai_course": "AI / 講座・コミュニティ",
    "ai_other": "AI / その他",
    "finance": "金融・カード・ポイント",
    "gov": "公務・行政・税",
    "shopping": "EC・サブスク・領収",
    "other": "その他",
}

RULE_GENRE_RES: list[tuple[str, re.Pattern[str]]] = [
    ("ai_models", re.compile(r"(GPT|Claude|Gemini|LLM|モデル|論文|research)", re.I)),
    ("ai_course", re.compile(r"(講座|スクール|コミュニティ|リスキリング|勉強会.*AI|AI.*講座)", re.I)),
    ("ai_tools", re.compile(r"(Cursor|ChatGPT|Notion\s*AI|プロンプト|生成AI|Copilot)", re.I)),
    ("ai_other", re.compile(r"\bAI\b|人工知能|機械学習", re.I)),
    ("re_seminar", re.compile(r"(セミナー|勉強会|懇親会|グルコン|ウェビナー)", re.I)),
    ("re_finance", re.compile(r"(融資|金利|ローン|団信|銀行)", re.I)),
    ("re_mgmt_news", re.compile(r"(空室|原状回復|管理会社|家賃|入居|退去|修繕)", re.I)),
    ("re_other", re.compile(r"(不動産|賃貸|オーナー|大家)", re.I)),
    ("gov", re.compile(r"(市役所|税務|確定申告|ねんきん|マイナ|役所|免許)", re.I)),
    ("finance", re.compile(r"(カード|ポイント|Vポイント|明細|引落|Olive|証券|NISA)", re.I)),
    ("shopping", re.compile(r"(ご注文|発送|領収|Amazon|楽天|サブスク|請求書)", re.I)),
]


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def client():
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY 未設定")
    return create_client(url, key)


def fetch_pending_other(sb) -> list[dict[str, Any]]:
    r = (
        sb.table("triage_items")
        .select(
            "id,lane,kind,status,partner,subject,summary,priority,from_email,"
            "received_at,original_body"
        )
        .eq("status", "pending")
        .neq("lane", "partner")
        .neq("kind", "activity")
        .order("received_at", desc=True)
        .limit(100)
        .execute()
    )
    return list(r.data or [])


def reclassify_pending_kinds(sb, *, dry_run: bool = False) -> dict[str, int]:
    """既存 pending general を mail/skim に再分類。"""
    sys.path.insert(0, str(REPO / "scripts"))
    from jarvis_night_triage_general import classify_general_kind

    rows = fetch_pending_other(sb)
    counts = Counter()
    for it in rows:
        if (it.get("lane") or "") != "general":
            continue
        kind = classify_general_kind(
            it.get("subject") or "",
            it.get("original_body") or it.get("summary") or "",
            it.get("from_email") or "",
        )
        counts[kind] += 1
        if dry_run:
            continue
        if it.get("kind") == kind:
            continue
        pri = "high" if kind == "mail" else "low"
        sb.table("triage_items").update(
            {
                "kind": kind,
                "priority": pri,
                "updated_at": now_iso(),
            }
        ).eq("id", it["id"]).execute()
    return dict(counts)


def rule_genre_for(it: dict[str, Any]) -> str:
    blob = f"{it.get('subject') or ''}\n{it.get('summary') or ''}\n{it.get('from_email') or ''}"
    for gid, rx in RULE_GENRE_RES:
        if rx.search(blob):
            return gid
    return "other"


def rule_digest(items: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(items)
    if n == 0:
        return {
            "generated_at": now_iso(),
            "pending_count": 0,
            "mail_count": 0,
            "skim_count": 0,
            "overview": "パートナー以外の未読はありません。",
            "action_items": [],
            "genres": [],
            "lines": [],
            "via": "rule",
        }
    mail_items = [it for it in items if (it.get("kind") or "mail") == "mail"]
    skim_items = [it for it in items if (it.get("kind") or "") == "skim"]
    # kind 未設定は従来どおり両方にカウント
    unset = [it for it in items if (it.get("kind") or "mail") not in ("mail", "skim")]
    mail_items = mail_items + [it for it in unset if (it.get("priority") or "").lower() in ("high", "attention", "med")]
    skim_items = skim_items + [it for it in unset if it not in mail_items]

    by_genre: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for it in items:
        by_genre[rule_genre_for(it)].append(it)

    genres: list[dict[str, Any]] = []
    for gid, rows in sorted(by_genre.items(), key=lambda x: -len(x[1])):
        bullets = []
        for it in rows[:4]:
            who = it.get("from_email") or it.get("partner") or "—"
            bullets.append(f"{who}: {it.get('subject') or '（件名なし）'}")
        genres.append(
            {
                "id": gid,
                "label": GENRE_LABELS.get(gid, gid),
                "item_ids": [str(it.get("id")) for it in rows if it.get("id")],
                "bullets": bullets,
                "ask_hint": f"「{GENRE_LABELS.get(gid, gid)}」について詳しく聞きたいとき用",
            }
        )

    action: list[dict[str, Any]] = []
    for it in mail_items[:5]:
        action.append(
            {
                "id": it.get("id"),
                "subject": it.get("subject") or "（件名なし）",
                "from": it.get("from_email") or it.get("partner"),
                "reason": "要確認（返信・依頼の可能性）",
            }
        )

    domains: Counter[str] = Counter()
    for it in items:
        frm = (it.get("from_email") or it.get("partner") or "不明").strip()
        dom = frm.split("@")[-1] if "@" in frm else frm
        domains[dom] += 1
    top = "、".join(f"{d}×{c}" for d, c in domains.most_common(3))

    return {
        "generated_at": now_iso(),
        "pending_count": n,
        "mail_count": len(mail_items),
        "skim_count": len(skim_items),
        "overview": (
            f"未読 {n} 件（要確認 {len(mail_items)} / 要約 {len(skim_items)}）。"
            f"主な差出: {top or '—'}。"
            "要約はジャンルごとに確認したよで消し込めます。"
        ),
        "action_items": action,
        "genres": genres,
        "lines": [f"{g['label']}（{len(g['item_ids'])}）" for g in genres[:5]],
        "via": "rule",
    }


def gemini_digest(items: list[dict[str, Any]], api_key: str) -> dict[str, Any] | None:
    if not items or not api_key:
        return None
    models = [
        (os.environ.get("GEMINI_MODEL") or "").strip(),
        "gemini-flash-latest",
        "gemini-flash-lite-latest",
    ]
    models = [m for i, m in enumerate(models) if m and m not in models[:i]]

    catalog = []
    for it in items[:50]:
        catalog.append(
            {
                "id": it.get("id"),
                "kind": it.get("kind") or "mail",
                "from": it.get("from_email") or it.get("partner"),
                "subject": it.get("subject"),
                "summary": (it.get("summary") or "")[:160],
                "priority": it.get("priority"),
            }
        )
    genre_ids = list(GENRE_LABELS.keys())
    prompt = f"""あなたは秘書です。パートナー以外の未読メールをジャンル別ダイジェストにしてください。

入力（JSON）:
{json.dumps(catalog, ensure_ascii=False)}

使える genre id（これ以外は other）:
{json.dumps(genre_ids, ensure_ascii=False)}
ラベル目安: {json.dumps(GENRE_LABELS, ensure_ascii=False)}

次の JSON のみ（Markdown不可）:
{{
  "overview": "全体2〜4文。要確認とざっと見る分の区別に触れてよい",
  "action_items": [
    {{"id": "kind=mail のうち対応候補のid", "subject": "", "from": "", "reason": ""}}
  ],
  "genres": [
    {{
      "id": "genre_id",
      "label": "表示名",
      "item_ids": ["id", "..."],
      "bullets": ["短い要点1", "要点2"],
      "ask_hint": "このジャンルで聞くときの一文"
    }}
  ]
}}

ルール:
- 不動産・AI は細かい id を優先。購入の個別物件紹介は通常ここに来ない想定。
- action_items は最大5・kind=mail 優先。なければ空。
- 各メール id はどれか1ジャンルにだけ入れる。捏造しない。
"""

    last_err = ""
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
        except Exception as e:
            last_err = str(e)[:200]
            continue
        cands = data.get("candidates") or []
        if not cands:
            last_err = "empty candidates"
            continue
        parts = (((cands[0] or {}).get("content") or {}).get("parts")) or []
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
                last_err = "json parse"
                continue
            try:
                obj = json.loads(m.group(0))
            except json.JSONDecodeError:
                last_err = "json parse2"
                continue
        if not isinstance(obj, dict):
            continue
        ids = {str(it.get("id")) for it in items}
        actions = []
        for a in obj.get("action_items") or []:
            if not isinstance(a, dict):
                continue
            aid = str(a.get("id") or "")
            if aid and aid not in ids:
                continue
            actions.append(
                {
                    "id": aid or None,
                    "subject": a.get("subject") or "（件名なし）",
                    "from": a.get("from"),
                    "reason": a.get("reason") or "",
                }
            )
        genres = []
        for g in obj.get("genres") or []:
            if not isinstance(g, dict):
                continue
            gid = str(g.get("id") or "other")
            if gid not in GENRE_LABELS:
                gid = "other"
            gids = [str(x) for x in (g.get("item_ids") or []) if str(x) in ids]
            if not gids:
                continue
            genres.append(
                {
                    "id": gid,
                    "label": str(g.get("label") or GENRE_LABELS.get(gid, gid)),
                    "item_ids": gids,
                    "bullets": [str(x) for x in (g.get("bullets") or []) if str(x).strip()][
                        :5
                    ],
                    "ask_hint": str(g.get("ask_hint") or "")[:120],
                }
            )
        mail_n = sum(1 for it in items if (it.get("kind") or "mail") == "mail")
        skim_n = sum(1 for it in items if (it.get("kind") or "") == "skim")
        return {
            "generated_at": now_iso(),
            "pending_count": len(items),
            "mail_count": mail_n,
            "skim_count": skim_n,
            "overview": str(obj.get("overview") or "").strip()
            or rule_digest(items)["overview"],
            "action_items": actions[:5],
            "genres": genres,
            "lines": [f"{g['label']}（{len(g['item_ids'])}）" for g in genres[:5]],
            "via": f"gemini:{model}",
        }
    print(f"# digest llm failed: {last_err}", file=sys.stderr)
    return None


def push_digest(sb, digest: dict[str, Any]) -> None:
    meta = now_iso()
    sb.table("sync_meta").upsert(
        {
            "key": "other_mail_digest",
            "value": json.dumps(digest, ensure_ascii=False),
            "updated_at": meta,
        },
        on_conflict="key",
    ).execute()


def build_and_maybe_push(
    *, do_push: bool, use_llm: bool, reclassify: bool = False
) -> dict[str, Any]:
    sb = client()
    if reclassify:
        counts = reclassify_pending_kinds(sb, dry_run=not do_push)
        print(f"# reclassify kinds={counts}", file=sys.stderr)
    items = fetch_pending_other(sb)
    digest = None
    if use_llm:
        key = (os.environ.get("GEMINI_API_KEY") or "").strip()
        digest = gemini_digest(items, key)
    if digest is None:
        digest = rule_digest(items)

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(digest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if do_push:
        push_digest(sb, digest)
        print(
            f"# other_mail_digest pushed pending={digest.get('pending_count')} "
            f"mail={digest.get('mail_count')} skim={digest.get('skim_count')} "
            f"via={digest.get('via')}",
            file=sys.stderr,
        )
    else:
        print(
            f"# other_mail_digest dry pending={digest.get('pending_count')} via={digest.get('via')}",
            file=sys.stderr,
        )
    return digest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="その他メール・ジャンル別ダイジェスト")
    ap.add_argument("--push", action="store_true", help="sync_meta へ保存")
    ap.add_argument("--no-llm", action="store_true", help="ルールのみ（Gemini なし）")
    ap.add_argument(
        "--reclassify",
        action="store_true",
        help="pending を mail/skim に再分類してから digest",
    )
    args = ap.parse_args(argv)
    digest = build_and_maybe_push(
        do_push=args.push, use_llm=not args.no_llm, reclassify=args.reclassify
    )
    print(json.dumps(digest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
