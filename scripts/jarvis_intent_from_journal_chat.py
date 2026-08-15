#!/usr/bin/env python3
"""
★Journal＋直近 Cursor チャットから関心シグナルを抽出し、
その他メールの要確認を軽量アップデートする。

負荷方針: 1日1回想定。常時監視なし。Gemini 1回／実行。昇格最大3件。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_intent_from_journal_chat.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_intent_from_journal_chat.py --push
  ~/selenium_env/venv/bin/python scripts/jarvis_intent_from_journal_chat.py --pull-journal --push
  ~/selenium_env/venv/bin/python scripts/jarvis_intent_from_journal_chat.py --no-llm --push
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
JOURNAL_DIR = (
    Path.home() / "Documents" / "500_Obsidian_r1" / "01_Journaling" / "★Journal"
)
TRANSCRIPT_ROOTS = [
    Path.home()
    / ".cursor"
    / "projects"
    / "Users-matsunomasaharu2-Downloads"
    / "agent-transcripts",
    Path.home() / ".cursor" / "projects" / "Users-matsunomasaharu2-git-repos" / "agent-transcripts",
]
STATE_PATH = REPO / ".jarvis_state" / "intent_sync.json"
OUT_PATH = REPO / ".jarvis_state" / "intent_digest.json"
OGD_PULL = REPO / "scripts" / "jarvis_obsidian_ogd_pull.py"
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"

JOURNAL_DAYS = 3
TRANSCRIPT_HOURS = 48
CHAT_CHAR_BUDGET = 15_000
JOURNAL_CHAR_BUDGET = 12_000
PROMOTE_MAX = 3

# 規則フォールバック用（テーマ id → キーワード）
RULE_THEMES: list[tuple[str, str, list[str]]] = [
    ("card_mig", "カード切替・年会費", ["カード", "Olive", "PP", "年会費", "CCNet", "Vpass", "切替"]),
    ("re_purchase", "不動産購入・物件紹介", ["物件紹介", "戸建", "買付", "利回り", "クラシフト", "KURASHIFT"]),
    ("partner_ops", "パートナー・管理運用", ["ミニテック", "LEAF", "退去", "修繕", "空室", "パートナー"]),
    ("ai_tooling", "AI・Cursor・Jarvis", ["Jarvis", "Cursor", "AI", "プロンプト", "ダッシュボード"]),
    ("finance_cash", "家計・振分・引落", ["引落", "振分", "Olive", "給与", "Zaim", "契約者貸付"]),
]


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def today_jst() -> datetime:
    return datetime.now(JST)


def load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def sb_client() -> Any:
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    return create_client(url, key)


def maybe_pull_journal() -> int:
    if not OGD_PULL.is_file():
        print("# ogd_pull missing", file=sys.stderr)
        return -1
    exe = str(PY) if PY.is_file() else sys.executable
    r = subprocess.run(
        [
            exe,
            str(OGD_PULL),
            "--prefix",
            "01_Journaling/★Journal",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if r.stdout:
        print(r.stdout, end="", file=sys.stderr)
    if r.stderr:
        print(r.stderr, end="", file=sys.stderr)
    return r.returncode


def read_recent_journals(days: int = JOURNAL_DAYS) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if not JOURNAL_DIR.is_dir():
        print(f"# journal dir missing: {JOURNAL_DIR}", file=sys.stderr)
        return out
    for i in range(days):
        d = (today_jst() - timedelta(days=i)).strftime("%Y-%m-%d")
        path = JOURNAL_DIR / f"{d}.md"
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        out.append({"date": d, "path": str(path), "text": text[:4000]})
    return out


def _extract_user_text(obj: dict[str, Any]) -> str:
    if obj.get("role") != "user":
        return ""
    msg = obj.get("message") or {}
    content = msg.get("content") if isinstance(msg, dict) else None
    chunks: list[str] = []
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                t = str(part.get("text") or "")
                # strip timestamp / user_query wrappers lightly
                t = re.sub(r"<timestamp>[\s\S]*?</timestamp>\s*", "", t)
                t = re.sub(r"</?user_query>", "", t)
                chunks.append(t.strip())
    elif isinstance(content, str):
        chunks.append(content.strip())
    return "\n".join(c for c in chunks if c)


def read_recent_user_chats(
    hours: int = TRANSCRIPT_HOURS, budget: int = CHAT_CHAR_BUDGET
) -> tuple[str, list[str]]:
    """Returns (blob, list of transcript paths used)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    files: list[Path] = []
    for root in TRANSCRIPT_ROOTS:
        if not root.is_dir():
            continue
        for p in root.rglob("*.jsonl"):
            if "subagents" in p.parts:
                continue
            try:
                mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            if mtime >= cutoff:
                files.append(p)
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    parts: list[str] = []
    used: list[str] = []
    total = 0
    for path in files[:40]:
        used.append(str(path))
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        # prefer last user turns
        user_bits: list[str] = []
        for line in lines[-80:]:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            ut = _extract_user_text(obj)
            if ut:
                user_bits.append(ut[:800])
        if not user_bits:
            continue
        block = f"[chat {path.stem[:8]}]\n" + "\n---\n".join(user_bits[-6:])
        if total + len(block) > budget:
            remain = budget - total
            if remain > 200:
                parts.append(block[:remain])
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts), used


def journal_blob(journals: list[dict[str, str]]) -> str:
    parts = []
    total = 0
    for j in journals:
        block = f"[journal {j['date']}]\n{j['text']}"
        if total + len(block) > JOURNAL_CHAR_BUDGET:
            parts.append(block[: max(0, JOURNAL_CHAR_BUDGET - total)])
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts)


def fetch_pending_other(sb: Any) -> list[dict[str, Any]]:
    import time

    last_err: Exception | None = None
    for attempt in range(3):
        try:
            r = (
                sb.table("triage_items")
                .select(
                    "id,lane,kind,status,partner,subject,summary,priority,from_email,"
                    "original_body,payload"
                )
                .eq("status", "pending")
                .neq("lane", "partner")
                .neq("kind", "activity")
                .order("received_at", desc=True)
                .limit(80)
                .execute()
            )
            return list(r.data or [])
        except Exception as e:
            last_err = e
            msg = str(e)
            # Mac 時計ずれで JWT iat が未来扱いになることがある
            if "future" in msg.lower() or "PGRST303" in msg:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
    print(f"# fetch_pending_other failed: {last_err}", file=sys.stderr)
    return []


def rule_extract_themes(blob: str) -> list[dict[str, Any]]:
    themes: list[dict[str, Any]] = []
    low = blob.lower()
    for tid, label, kws in RULE_THEMES:
        hits = [k for k in kws if k.lower() in low or k in blob]
        if len(hits) >= 2 or (len(hits) == 1 and hits[0] in ("CCNet", "クラシフト", "KURASHIFT")):
            themes.append(
                {
                    "id": tid,
                    "label": label,
                    "why": f"キーワード: {', '.join(hits[:5])}",
                    "keywords": hits[:8],
                }
            )
    return themes[:6]


def gemini_extract(journal: str, chat: str, catalog: list[dict[str, Any]]) -> dict[str, Any] | None:
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        return None
    models = [
        (os.environ.get("GEMINI_MODEL") or "").strip(),
        "gemini-flash-lite-latest",
        "gemini-flash-latest",
    ]
    models = [m for i, m in enumerate(models) if m and m not in models[:i]]

    prompt = f"""あなたは秘書 Jarvis です。ユーザーの日誌と直近チャットから「いま考えていること」を抽出し、
未読メール一覧のうち要確認に上げるべきものを選んでください。

【Journal】
{journal[:JOURNAL_CHAR_BUDGET]}

【Chat user turns】
{chat[:CHAT_CHAR_BUDGET]}

【pending triage 候補】
{json.dumps(catalog, ensure_ascii=False)}

次の JSON のみ（Markdown不可）:
{{
  "themes": [
    {{"id": "snake_id", "label": "短い題", "why": "なぜ今関心か", "keywords": ["語1","語2"]}}
  ],
  "promote_candidates": [
    {{"triage_id": "入力にあるid", "reason": "なぜ昇格か"}}
  ],
  "digest_notes": ["ホーム向け1行メモ"]
}}

ルール:
- themes は最大6。promote_candidates は最大{PROMOTE_MAX}。無理に埋めない。
- triage_id は入力の id のみ。捏造禁止。
- 大きな方針転換ではなく、詰まっている手続き・次の一手に近いものを優先。
"""

    last_err = ""
    for model in models:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={key}"
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1536},
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
            last_err = "empty"
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
                last_err = "json"
                continue
            try:
                obj = json.loads(m.group(0))
            except json.JSONDecodeError:
                last_err = "json2"
                continue
        if isinstance(obj, dict):
            obj["_via"] = f"gemini:{model}"
            return obj
    print(f"# intent llm failed: {last_err}", file=sys.stderr)
    return None


def score_item_against_themes(it: dict[str, Any], themes: list[dict[str, Any]]) -> tuple[float, str]:
    blob = " ".join(
        [
            str(it.get("subject") or ""),
            str(it.get("summary") or ""),
            str(it.get("from_email") or ""),
            str(it.get("partner") or ""),
            str(it.get("original_body") or "")[:500],
        ]
    )
    # ノイズになりやすい単独語は、もう1語と組にならない限り加点しない
    weak = {"カード", "olive", "ai", "cursor", "jarvis", "pp"}
    best = 0.0
    reason = ""
    for th in themes:
        kws = [str(k) for k in (th.get("keywords") or []) if k]
        hits = [k for k in kws if k and k in blob]
        if not hits:
            continue
        strong = [h for h in hits if h.lower() not in weak]
        if not strong and len(hits) < 2:
            continue
        sc = float(len(strong) * 2 + max(0, len(hits) - len(strong)))
        if (it.get("kind") or "") == "skim":
            sc += 1.0
        # 既に high の mail は二重注釈を避ける
        if (it.get("kind") or "mail") == "mail" and (it.get("priority") or "") == "high":
            payload = it.get("payload") if isinstance(it.get("payload"), dict) else {}
            if payload.get("intent_promoted_at"):
                continue
            sc -= 0.5
        if sc > best:
            best = sc
            reason = f"{th.get('label')}: {', '.join((strong or hits)[:4])}"
    return best, reason


def match_promotes(
    items: list[dict[str, Any]],
    themes: list[dict[str, Any]],
    llm_promotes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ids = {str(it.get("id")) for it in items}
    by_id = {str(it.get("id")): it for it in items}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    for p in llm_promotes or []:
        if not isinstance(p, dict):
            continue
        tid = str(p.get("triage_id") or "")
        if tid not in ids or tid in seen:
            continue
        it = by_id[tid]
        payload = it.get("payload") if isinstance(it.get("payload"), dict) else {}
        if payload.get("intent_promoted_at"):
            continue
        seen.add(tid)
        out.append(
            {
                "triage_id": tid,
                "reason": str(p.get("reason") or "関心と一致")[:200],
                "kind": it.get("kind"),
            }
        )
        if len(out) >= PROMOTE_MAX:
            return out

    scored: list[tuple[float, str, str, int]] = []
    for it in items:
        tid = str(it.get("id") or "")
        if not tid or tid in seen:
            continue
        sc, reason = score_item_against_themes(it, themes)
        kind = it.get("kind") or "mail"
        # skim は 1.5、既存 mail はより厳しめ
        need = 1.5 if kind == "skim" else 2.5
        if sc >= need:
            skim_boost = 0 if kind == "skim" else 1
            scored.append((sc, tid, reason, skim_boost))
    scored.sort(key=lambda x: (x[3], -x[0]))
    for sc, tid, reason, _ in scored:
        if len(out) >= PROMOTE_MAX:
            break
        seen.add(tid)
        out.append(
            {
                "triage_id": tid,
                "reason": reason[:200],
                "kind": by_id[tid].get("kind"),
            }
        )
    return out


def apply_promotes(
    sb: Any,
    items: list[dict[str, Any]],
    promotes: list[dict[str, Any]],
    *,
    dry_run: bool,
) -> list[dict[str, Any]]:
    by_id = {str(it.get("id")): it for it in items}
    applied: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()
    for p in promotes[:PROMOTE_MAX]:
        tid = p["triage_id"]
        it = by_id.get(tid)
        if not it:
            continue
        kind = it.get("kind") or "mail"
        payload = it.get("payload") if isinstance(it.get("payload"), dict) else {}
        payload = {
            **payload,
            "intent_promoted_at": now,
            "intent_reason": p.get("reason"),
        }
        summary = str(it.get("summary") or "")
        note = f"【関心】{p.get('reason')}"
        if note not in summary:
            summary = f"{note} / {summary}".strip(" /")[:500]

        if kind == "skim":
            update = {
                "kind": "mail",
                "priority": "high",
                "summary": summary,
                "payload": payload,
                "updated_at": now_iso(),
            }
            action = "skim_to_mail"
        else:
            update = {
                "priority": "high",
                "summary": summary,
                "payload": payload,
                "updated_at": now_iso(),
            }
            action = "annotate_mail"

        applied.append(
            {
                "triage_id": tid,
                "subject": it.get("subject"),
                "action": action,
                "reason": p.get("reason"),
            }
        )
        if dry_run:
            print(f"# dry-run promote {action} id={tid} {it.get('subject')}", file=sys.stderr)
            continue
        sb.table("triage_items").update(update).eq("id", tid).execute()
        print(f"📎 intent_promote: {action} id={tid}", file=sys.stderr)
    return applied


def push_intent_digest(sb: Any, digest: dict[str, Any]) -> None:
    meta = now_iso()
    sb.table("sync_meta").upsert(
        {
            "key": "intent_digest",
            "value": json.dumps(digest, ensure_ascii=False),
            "updated_at": meta,
        },
        on_conflict="key",
    ).execute()


def build_digest(
    *,
    themes: list[dict[str, Any]],
    notes: list[str],
    applied: list[dict[str, Any]],
    via: str,
    journal_dates: list[str],
) -> dict[str, Any]:
    return {
        "generated_at": now_iso(),
        "via": via,
        "journal_dates": journal_dates,
        "themes": themes,
        "digest_notes": notes[:5],
        "promoted": applied,
        "load_note": "朝1回＋手動。常時監視なし。昇格最大3件。",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Journal/Chat → 要確認アップデート")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--push", action="store_true", help="昇格＋sync_meta 反映")
    ap.add_argument("--pull-journal", action="store_true", help="先に OGD Journal pull")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--skip-promote", action="store_true", help="抽出のみ（昇格しない）")
    args = ap.parse_args(argv)

    if args.pull_journal:
        maybe_pull_journal()

    journals = read_recent_journals()
    jblob = journal_blob(journals)
    cblob, chat_paths = read_recent_user_chats()
    print(
        f"# journals={len(journals)} chat_files={len(chat_paths)} "
        f"j_chars={len(jblob)} c_chars={len(cblob)}",
        file=sys.stderr,
    )

    do_write = bool(args.push) and not args.dry_run
    sb = None
    items: list[dict[str, Any]] = []
    if do_write or args.push or args.dry_run:
        try:
            sb = sb_client()
            items = fetch_pending_other(sb)
        except SystemExit:
            if args.push and not args.dry_run:
                raise
            print("# supabase skip (no env)", file=sys.stderr)
        except Exception as e:
            if args.push and not args.dry_run:
                raise
            print(f"# supabase fetch skip: {e}", file=sys.stderr)

    catalog = [
        {
            "id": it.get("id"),
            "kind": it.get("kind"),
            "subject": it.get("subject"),
            "from": it.get("from_email") or it.get("partner"),
            "summary": (it.get("summary") or "")[:120],
        }
        for it in items[:50]
    ]

    via = "rule"
    themes: list[dict[str, Any]] = []
    llm_promotes: list[dict[str, Any]] = []
    notes: list[str] = []

    if not args.no_llm:
        obj = gemini_extract(jblob, cblob, catalog)
        if obj:
            via = str(obj.get("_via") or "gemini")
            themes = [t for t in (obj.get("themes") or []) if isinstance(t, dict)][:6]
            llm_promotes = [
                p for p in (obj.get("promote_candidates") or []) if isinstance(p, dict)
            ]
            notes = [str(x) for x in (obj.get("digest_notes") or []) if str(x).strip()][
                :5
            ]

    if not themes:
        themes = rule_extract_themes(jblob + "\n" + cblob)
        via = "rule" if via == "rule" else via + "+rule_themes"

    if not notes and themes:
        notes = [f"いまの関心: {', '.join(t.get('label') or t.get('id') for t in themes[:3])}"]

    promotes = match_promotes(items, themes, llm_promotes) if items else []
    applied: list[dict[str, Any]] = []
    if not args.skip_promote and promotes and sb is not None:
        applied = apply_promotes(sb, items, promotes, dry_run=args.dry_run or not args.push)

    digest = build_digest(
        themes=themes,
        notes=notes,
        applied=applied if applied else [
            {"triage_id": p["triage_id"], "reason": p.get("reason"), "action": "candidate"}
            for p in promotes
        ],
        via=via,
        journal_dates=[j["date"] for j in journals],
    )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(digest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if args.push and not args.dry_run and sb is not None:
        push_intent_digest(sb, digest)
        # 要確認件数が変わったので digest 再生成（軽量）
        try:
            sys.path.insert(0, str(REPO / "scripts"))
            from jarvis_other_mail_digest import build_and_maybe_push

            build_and_maybe_push(do_push=True, use_llm=False, reclassify=False)
        except Exception as e:
            print(f"# other_mail_digest refresh skipped: {e}", file=sys.stderr)

        st = load_state()
        st.update(
            {
                "last_run_at": now_iso(),
                "last_journal_dates": digest["journal_dates"],
                "last_chat_files": chat_paths[:20],
                "last_promoted": [a.get("triage_id") for a in applied],
            }
        )
        save_state(st)
        print(
            f"# intent_digest pushed themes={len(themes)} promoted={len(applied)} via={via}",
            file=sys.stderr,
        )

    print(json.dumps(digest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
