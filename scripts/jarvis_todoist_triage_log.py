#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Todoist ふるい分け（300 ラス隊長）の判断を owner_decisions（surface=todoist_triage）へ載せる。

既存のループウェアに乗せるだけで、新しい仕組みは作らない:

  記録（このスクリプト） → 土曜の週次（jarvis_loopware_weekly.py）が「同じ種類の判断2回以上」で
  ルール候補を出す → 松野さんが loopware で採用 → 313 の learned_rules.md「確定ルール」
  → 次のふるい分けの前に `context` で読む

surface を todoist_313 と分ける理由: todoist_313 は /313/bulk の画面で選んだ判断で、jarvis_todoist_cleanup_bulk.py の
reflect が「close/drop/reschedule を Todoist へ反映する元」として読む。ふるい分けの記録を混ぜると
誤って反映される恐れがあるため、別 surface にする。

action（契約 v1 の OUTCOME に合わせる）:
  close          済み（根拠あり）。ラス隊長が根拠を付けて閉じた
  owner_close    松野さんの判断で閉じた（本人の述べた理由は転記があるときだけ。AI で補作しない）
  drop_candidate やめる候補（松野さんの一括判断待ち）
  keep           残す（あと一手つき）

使い方（リポジトリルートから。値は表示しない。~/git-repos/.env.jarvis_private を必要な3キーだけ読む）:

  python3 scripts/jarvis_todoist_triage_log.py backfill --since 2026-11-24 --dry-run   # 件数だけ
  python3 scripts/jarvis_todoist_triage_log.py backfill --since 2026-11-24 --apply     # owner_decisions に書く
  python3 scripts/jarvis_todoist_triage_log.py context                                # ふるい分けの前に読む
  python3 scripts/jarvis_todoist_triage_log.py queue --ids-file ids.json --apply       # やめる候補を /313/bulk へ
  python3 scripts/jarvis_todoist_triage_log.py review                                 # 根拠が弱いまま閉じた件

Todoist は読むだけ（close・削除・コメント追加はしない）。DB へ書くのは社内の記録だけ。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from jarvis_owner_decision_log import contract_row  # noqa: E402

JST = timezone(timedelta(hours=9))
SURFACE = "todoist_triage"
EMPLOYEE = "313"
AUTHOR_PREFIX = "【300 ラス隊長"
ENV_FILE = Path.home() / "git-repos" / ".env.jarvis_private"
ENV_KEYS = ("TODOIST_API_TOKEN_OWNER", "JARVIS_SUPABASE_URL", "JARVIS_SUPABASE_SERVICE_ROLE_KEY")
DROP_QUEUE_KEY = "todoist_triage_drop_queue"
ACTIONS = ("close", "owner_close", "drop_candidate", "keep")
# 同じ件に複数のコメントがあるとき、最終の判断として採る順（強い順）
PRIORITY = {"owner_close": 0, "close": 1, "drop_candidate": 2, "keep": 3}

HEADER_RE = re.compile(r"^【300 ラス隊長([^】]*)】")
JUDGE_RE = re.compile(r"判定[:：]\s*(残す|やめる候補)")
REASON_RE = re.compile(r"^理由[:：]\s*(.+)$", re.M)
EVID_RE = re.compile(r"^根拠[:：]\s*(.+)$", re.M)
OWNER_RE = re.compile(r"松野さん(?:判断|了承)[:：]\s*([^\n]+)")
NEXT_RE = re.compile(r"あと一手[（(][^）)]*[）)][:：]?\s*(.*)|松野さんの一手[:：]\s*(.+)")

# 判断の「種類」（週次が同じ種類2回以上でルール候補にする）。言い回しは一般化した文だけ（個別名を入れない）
TAG_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("noreply_send", re.compile(r"noreply|no-reply|返信不可|mailer-daemon|宛先ガード", re.I)),
    ("trial_decided", re.compile(r"有料で続ける|(無料体験|試行|トライアル).*(有料で続ける|合格|続ける|満たした)|(有料で続ける|合格|満たした).*(無料体験|試行|トライアル)", re.S)),
    ("done_by_pr", re.compile(r"PR\s*#\d+.*(マージ|CI)|(マージ|CI緑).*PR\s*#\d+", re.S)),
    ("done_in_mail", re.compile(r"納付|着金|振込通知|送信済み|完了報告|入金通知|に送信済")),
    ("stale_notice", re.compile(r"(案内|通知|販促|優待|アンケート|任意|フォーラム|ダイジェスト).*(期限|経過|切れ|放置|不要|任意)|(期限|経過|放置).*(案内|通知|販促|アンケート)", re.S)),
    ("duplicate_merged", re.compile(r"重複")),
    ("no_trace_keep", re.compile(r"証跡[はが]?(なし|無し|無い)|通知は無し|メールは無し|未検出|印は無")),
]
TRIAGE_GUIDES: dict[str, str] = {
    "noreply_send": "返信不可アドレス宛の送信は、送信ガードで止まっていれば気にせず、そのタスクは閉じる",
    "trial_decided": "試用・無料体験の結論（合格・有料継続）が出たら、そのタスクは閉じて次の移行タスクへ進める",
    "done_by_pr": "原因の直しが PR マージ・CI 緑で完了条件を満たしているタスクは、根拠を添えて閉じる",
    "done_in_mail": "メール等に完了の証跡（納付・着金・送信済み）があるタスクは、根拠を添えて閉じる",
    "stale_notice": "期限切れで任意の案内・通知だけのタスクは『やめる候補』に回す（閉じるのは松野さんの一括判断）",
    "duplicate_merged": "重複で足りている件は、残す1件を決めてまとめる（実行前に了承を取る）",
    "no_trace_keep": "完了の証跡がメールに無い件は『残す』にして、2分で済む『あと一手』を添える",
}
EVID_KINDS: list[tuple[str, re.Pattern[str]]] = [
    ("owner", re.compile(r"松野さん(?:判断|了承)")),
    ("db", re.compile(r"\bDB\b|Supabase|triage_items|kurashift_re_deals|テーブル|embedding")),
    ("github", re.compile(r"PR\s*#\d+|マージ|CI緑|Issue")),
    ("slack", re.compile(r"Slack|#ai-hub|#consult|#ops")),
    ("mail", re.compile(r"gmail|Gmail|メール|送信済み|\b[0-9a-f]{16}\b")),
    ("agent_log", re.compile(r"ログ|launchd|pmset|スクリプト|ワーカー|exit\s*\d|読み取りのみ")),
]


def _clip(s: str | None, n: int) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()[:n]


def evidence_kinds(text: str) -> list[str]:
    return [k for k, rx in EVID_KINDS if rx.search(text)]


def tag_of(action: str, text: str) -> str | None:
    """判断の種類。keep は証跡なし系だけ、drop_candidate は stale_notice だけを当てる（種類が混ざらないように）"""
    allowed = {
        "keep": {"no_trace_keep"},
        "drop_candidate": {"stale_notice"},
        "close": {"trial_decided", "done_by_pr", "done_in_mail", "duplicate_merged"},
        "owner_close": {"noreply_send", "trial_decided", "done_by_pr", "duplicate_merged"},
    }.get(action)
    for tag, rx in TAG_RULES:
        if allowed is not None and tag not in allowed:
            continue
        if rx.search(text):
            return tag
    return None


def judge_comment(body: str) -> dict[str, Any] | None:
    """ラス隊長のコメント1件から判断を取り出す。判断でなければ None（追記など）。"""
    m = HEADER_RE.match(body)
    if not m:
        return None
    header = m.group(1)
    rest = body[m.end():]
    om = OWNER_RE.search(rest)
    if om:
        reason = re.split(r"→|。", om.group(1))[0].strip()
        if reason.count("）") > reason.count("（"):
            reason = reason.rstrip("）")  # 外側の閉じ括弧だけ落とす
        return {"action": "owner_close", "owner_reason": _clip(reason, 120), "text": rest, "inventory": False}
    jm = JUDGE_RE.search(rest)
    if jm:
        action = "keep" if jm.group(1) == "残す" else "drop_candidate"
        rm, em = REASON_RE.search(rest), EVID_RE.search(rest)
        return {"action": action, "reason": _clip(rm.group(1) if rm else "", 160),
                "evidence": _clip(em.group(1) if em else "", 160), "text": rest,
                "inventory": "棚卸し" in header}
    if "閉じます" in rest:
        em = EVID_RE.search(rest)
        first = rest.strip().splitlines()[0] if rest.strip() else ""
        return {"action": "close", "evidence": _clip(em.group(1) if em else first, 160), "text": rest, "inventory": False}
    return None


def next_step_of(body: str) -> str | None:
    if not HEADER_RE.match(body):
        return None
    for line in body.splitlines():
        m = NEXT_RE.search(line)
        if m:
            return _clip(m.group(1) or m.group(2), 160) or _clip(line, 160)
    return None


def decide_task(task: dict[str, Any], comments: list[dict[str, Any]], *, run_id: str) -> dict[str, Any] | None:
    """1タスク→最終判断1件（owner_close > close > drop_candidate > keep）。ラス隊長のコメントが無ければ None。"""
    mine = sorted((c for c in comments if str(c.get("content") or "").startswith(AUTHOR_PREFIX)),
                  key=lambda c: str(c.get("posted_at") or ""))
    if not mine:
        return None
    found: list[tuple[dict[str, Any], dict[str, Any]]] = []
    next_step = None
    for c in mine:
        j = judge_comment(str(c["content"]))
        if j:
            found.append((j, c))
        ns = next_step_of(str(c["content"]))
        if ns:
            next_step = ns
    if not found:
        return None
    best = min(PRIORITY[jc[0]["action"]] for jc in found)
    j, c = [jc for jc in found if PRIORITY[jc[0]["action"]] == best][-1]  # 同じ強さなら新しい方
    action = j["action"]
    text = str(j["text"])
    ev_text = j.get("evidence") or j.get("owner_reason") or text
    kinds = evidence_kinds(ev_text if action != "owner_close" else text) or []
    if action == "owner_close" and "owner" not in kinds:
        kinds.insert(0, "owner")
    completed = bool(task.get("checked") or task.get("completed_at"))
    pl: dict[str, Any] = {
        "kind": "triage",
        "run_id": run_id,
        "evidence_kind": (kinds[0] if kinds else "agent_log"),
        "evidence_kinds": kinds,
        "evidence_note": _clip(j.get("evidence") or j.get("reason") or "", 160),
        "todoist_state": "completed" if completed else "active",
        "inventory": bool(j.get("inventory")),
        "reason_tags": [action],
    }
    tag = tag_of(action, text)
    if tag:
        pl["rule_tag"] = tag
    if j.get("reason"):
        pl["reason_ai"] = j["reason"]  # ラス隊長の理由（本人の理由ではない）
    if action == "owner_close":
        pl["owner_reason"] = j["owner_reason"]
        pl["reason_source"] = "コメントに転記された本人の判断（補作なし）"
    if next_step and action == "keep":
        pl["next_step"] = next_step
    if completed and action in ("keep", "drop_candidate"):
        pl["closed_without_basis"] = True  # 判定だけで閉じ方のコメントが無い（根拠が弱い）
    if completed:
        pl["completed_at"] = str(task.get("completed_at") or "")[:19]
    return {
        "action": action,
        "task_id": str(task["id"]),
        "subject": _clip(task.get("content"), 120),
        "decided_at": str(c.get("posted_at") or ""),
        "payload": pl,
    }


def build_row(d: dict[str, Any]) -> dict[str, Any]:
    row = contract_row(
        surface=SURFACE, action=d["action"], source="script_todoist_triage_backfill",
        target_type="todoist_task", target_id=d["task_id"], employee=EMPLOYEE, subject=d["subject"],
        note=d["payload"].get("owner_reason") or d["payload"].get("reason_ai"),
        payload=d["payload"], idem_key=f"todoist_triage:{d['task_id']}:{d['action']}",
    )
    if d.get("decided_at"):
        row["decided_at"] = d["decided_at"]
    return row


# ---- Todoist（読むだけ） / DB ----------------------------------------------------------------

def load_env() -> None:
    """必要な3キーだけ .env.jarvis_private から読む（値は出さない）。既に環境にあればそのまま。"""
    if all(os.environ.get(k) for k in ENV_KEYS) or not ENV_FILE.is_file():
        return
    for line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        k, sep, v = line.partition("=")
        k = k.replace("export ", "").strip()
        if sep and k in ENV_KEYS and not os.environ.get(k):
            os.environ[k] = v.strip().strip("'\"")


def _pages(path: str, token: str, key: str = "results"):
    from jarvis_todoist_313_http import request  # noqa: PLC0415

    cur = None
    while True:
        p = f"{path}{'&' if '?' in path else '?'}limit=200" + (f"&cursor={cur}" if cur else "")
        d = request("GET", p, token)
        yield from d.get(key, [])
        cur = d.get("next_cursor")
        if not cur:
            break


def fetch_triaged(since: str, token: str) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """since（YYYY-MM-DD）以降に完了したタスクと、未完了の全タスクのうち、ラス隊長のコメントがあるもの。"""
    from jarvis_todoist_313_http import request  # noqa: PLC0415

    until = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
    tasks = list(_pages(f"/tasks/completed/by_completion_date?since={since}T00:00:00Z&until={until}", token, "items"))
    tasks += list(_pages("/tasks", token))
    out = []
    seen: set[str] = set()
    for t in tasks:
        tid = str(t["id"])
        if tid in seen:
            continue
        seen.add(tid)
        cs = request("GET", f"/comments?task_id={tid}&limit=100", token).get("results", [])
        if any(str(c.get("content") or "").startswith(AUTHOR_PREFIX) for c in cs):
            out.append((t, cs))
    return out


def _sb():
    from supabase import create_client  # noqa: PLC0415

    return create_client(os.environ["JARVIS_SUPABASE_URL"], os.environ["JARVIS_SUPABASE_SERVICE_ROLE_KEY"])


def summarize(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    by_action: dict[str, int] = {}
    by_tag: dict[str, int] = {}
    for d in decisions:
        by_action[d["action"]] = by_action.get(d["action"], 0) + 1
        t = d["payload"].get("rule_tag")
        if t:
            by_tag[f"{d['action']}:{t}"] = by_tag.get(f"{d['action']}:{t}", 0) + 1
    return {"total": len(decisions), "by_action": by_action, "by_rule_tag": by_tag,
            "closed_without_basis": sum(1 for d in decisions if d["payload"].get("closed_without_basis")),
            "owner_reason_present": sum(1 for d in decisions if d["payload"].get("owner_reason"))}


def cmd_backfill(args: argparse.Namespace) -> int:
    load_env()
    tok = os.environ.get("TODOIST_API_TOKEN_OWNER", "").strip()
    if not tok:
        print("TODOIST_API_TOKEN_OWNER が読めません", file=sys.stderr)
        return 2
    run_id = args.run_id or f"todoist_triage_backfill_{datetime.now(JST):%Y%m%d}"
    decisions = [d for t, cs in fetch_triaged(args.since, tok) if (d := decide_task(t, cs, run_id=run_id))]
    s = summarize(decisions)
    print(json.dumps(s, ensure_ascii=False, indent=2))
    if not args.apply:
        print("# dry-run（DB には書いていません）。--apply で記録")
        return 0
    sb = _sb()
    wrote = dup = 0
    for d in decisions:
        row = build_row(d)
        key = row["payload"]["idem_key"]
        if sb.table("owner_decisions").select("id").eq("payload->>idem_key", key).limit(1).execute().data:
            dup += 1
            continue
        sb.table("owner_decisions").insert(row).execute()
        wrote += 1
    print(f"# apply: 新規 {wrote} 件・既に記録済み {dup} 件")
    return 0


def recent_rows(limit: int) -> list[dict[str, Any]] | None:
    load_env()
    if not (os.environ.get("JARVIS_SUPABASE_URL") and os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")):
        return None
    try:
        res = (_sb().table("owner_decisions").select("decided_at,action,subject,payload")
               .eq("surface", SURFACE).order("decided_at", desc=True).limit(limit).execute())
        return res.data or []
    except Exception as e:  # noqa: BLE001 — 読めなくても本線は止めない
        print(f"owner_decisions 読み取り失敗: {type(e).__name__}", file=sys.stderr)
        return None


def context_text(recent: list[dict[str, Any]] | None, book=None) -> str:
    """ふるい分けの前に読む材料（採用済みルール → 最近の判断。後者はルールではない）"""
    import jarvis_learned_rules as lr  # noqa: PLC0415

    book = book or lr.load_rulebook(EMPLOYEE)
    lines = ["# ふるい分けの前に読む — 313（Todoist）", "", "## 採用済みのルール（必ず守る。松野さんが採用したものだけ）"]
    rules = lr.rewrite_lines(book, None)
    lines += [f"- {rid}: {text}" for rid, text in rules] or ["- （まだありません）"]
    lines += ["", "## 最近の判断（候補。ルールではない）"]
    if recent is None:
        lines.append("- （DBに接続できないため省略）")
    elif not recent:
        lines.append("- （まだありません）")
    for r in recent or []:
        pl = r.get("payload") or {}
        why = pl.get("owner_reason") or pl.get("evidence_note") or "根拠未記入"
        flag = " ⚠根拠が弱いまま閉じた" if pl.get("closed_without_basis") else ""
        lines.append(f"- {str(r.get('decided_at') or '')[:10]} {r.get('action')} [{pl.get('evidence_kind', '-')}"
                     f"/{pl.get('rule_tag', '-')}] {why[:70]}{flag}")
    lines += ["", "ふるい分けたら、判断を記録する（backfill 相当）。本人の理由が分からなければ省く（補作しない）。",
              "『済み』は根拠（メール・Slack・履歴・DB）を1行添えて閉じ、根拠が弱ければ『やめる候補』『残す＋あと一手』にする。"]
    return "\n".join(lines) + "\n"


def cmd_context(args: argparse.Namespace) -> int:
    sys.stdout.write(context_text(recent_rows(args.limit)))
    return 0


# ---- やめる候補を /313/bulk へ（既存の 313 週の整理キューと同じ形。別キーで置く） ----------------------

def drop_card(t: dict[str, Any], why: str, now: datetime) -> dict[str, Any]:
    due = ((t.get("due") or {}).get("date")) if isinstance(t.get("due"), dict) else None
    added = str(t.get("added_at") or "")[:10]
    try:
        age = (now.date() - datetime.fromisoformat(added).date()).days if added else None
    except ValueError:
        age = None
    return {
        "id": str(t["id"]), "title": str(t.get("content") or ""), "sender": "", "subject": "", "mail_date": "",
        "summary": "", "gmail_url": "", "due": (str(due)[:10] if due else None), "added_at": added, "age_days": age,
        "suggest": "drop", "why": _clip(why, 120) or "ラス隊長のやめる候補", "priority": t.get("priority"),
        "origin": "313", "evidence_url": None,
    }


def cmd_queue(args: argparse.Namespace) -> int:
    load_env()
    tok = os.environ.get("TODOIST_API_TOKEN_OWNER", "").strip()
    raw = json.loads(Path(args.ids_file).read_text(encoding="utf-8"))
    ids = [str(x[0] if isinstance(x, list) else x) for x in raw]
    from jarvis_todoist_313_http import request  # noqa: PLC0415

    now = datetime.now(JST)
    cards, closed, gone = [], 0, 0
    for tid in ids:
        try:
            t = request("GET", f"/tasks/{tid}", tok)
        except Exception:  # noqa: BLE001
            gone += 1
            continue
        if t.get("checked") or t.get("is_deleted"):
            closed += 1
            continue
        # 対象の件だけコメントを読む（全件を読むと Todoist の回数制限に当たる）
        cs = request("GET", f"/comments?task_id={tid}&limit=100", tok).get("results", [])
        d = decide_task(t, cs, run_id="queue")
        cards.append(drop_card(t, (d or {}).get("payload", {}).get("reason_ai", ""), now))
    print(f"やめる候補 {len(ids)} 件: カードにする {len(cards)}・既に完了 {closed}・見つからない {gone}")
    if not args.apply:
        print("# dry-run（置いていません）")
        return 0
    doc = {"v": 1, "published": True, "generated_at": now.isoformat(timespec="seconds"), "cards": cards}
    _sb().table("sync_meta").upsert({"key": DROP_QUEUE_KEY, "value": json.dumps(doc, ensure_ascii=False),
                                     "updated_at": now.isoformat()}, on_conflict="key").execute()
    print(f"# published {len(cards)} cards → sync_meta.{DROP_QUEUE_KEY}（次に cleanup_bulk --mode snapshot で画面へ）")
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    """判定だけで閉じ方のコメントが無いまま完了になった件（根拠が弱い）を一覧する。"""
    load_env()
    res = (_sb().table("owner_decisions").select("target_id,action,subject,payload")
           .eq("surface", SURFACE).execute())
    rows = [r for r in res.data or [] if (r.get("payload") or {}).get("closed_without_basis")]
    print(f"根拠が弱いまま完了になった件: {len(rows)}")
    for r in rows:
        print(f"- {r['target_id']} [{r['action']}] {_clip(r.get('subject'), 40)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backfill", help="ラス隊長のコメントから判断を拾って記録")
    b.add_argument("--since", default="2026-11-24", help="この日以降に完了した件＋未完了の全件を見る")
    b.add_argument("--run-id")
    g = b.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    c = sub.add_parser("context", help="ふるい分けの前に読む（採用済みルール・最近の判断）")
    c.add_argument("--limit", type=int, default=15)
    q = sub.add_parser("queue", help="やめる候補を /313/bulk のカードにする（選ぶまで閉じない）")
    q.add_argument("--ids-file", required=True)
    q.add_argument("--apply", action="store_true")
    sub.add_parser("review", help="根拠が弱いまま完了になった件")
    args = ap.parse_args(argv)
    return {"backfill": cmd_backfill, "context": cmd_context, "queue": cmd_queue, "review": cmd_review}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
