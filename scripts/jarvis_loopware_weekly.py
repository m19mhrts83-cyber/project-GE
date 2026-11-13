#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ループウェアの週次分析（機械で束ねる部分。AI は使わない）。

判断ログ（owner_decisions）を束ねて、
  - ルール候補（最大3件。少ないログでも「仮説」として出す）
  - 効いたルール（applied_rules ごとの結果）
  - 残っている理由の多い順（迷った・見ていない）
  - 次の一手の型の当たり外れ
  - あなたの判断で変わったこと（今週採用したルール）
を作る。314（Miss Lemon）はこの結果だけを読んで、言い回しの文言など AI が要る所だけ埋める
（差分だけ・束ねてから・候補は最大3件 = AI 使用量を抑える）。

  python scripts/jarvis_owner_decisions_weekly.py --loopware ...   # 週次まとめに節を足す
  python scripts/jarvis_loopware_weekly.py --days 7 --json out.json  # 単体（候補 JSON）

ルール候補は sync_meta.loopware_rule_candidates にも置き、loopware の「ルール候補」で
採用／今回だけ／違う を押せる（押した結果は owner_decisions surface=rule_review）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
MAX_CANDIDATES = 3
SMALL_LOG = 20  # これより少ない週は「仮説」として出す

NG_ACTIONS = {"skipped", "dismiss", "skip", "reject", "wrong"}
TAKE_ACTIONS = {"sent", "replied", "todo", "todoist", "done", "adopt", "accept", "create", "close"}
HIDE_REASONS = {"no_reply", "promo", "not_important", "self_or_grok"}

STAY_LABEL = {"no_time": "時間がない", "unsure": "迷った", "need_info": "情報が足りない", "waiting": "誰かの返事待ち"}


def _pl(r: dict[str, Any]) -> dict[str, Any]:
    p = r.get("payload")
    return p if isinstance(p, dict) else {}


def outcome(r: dict[str, Any]) -> str:
    # 送り手の設定で自動で閉じたもの（source_detail=auto_policy）は、本人の判断ではないので「採った」に数えない
    if _pl(r).get("source_detail") == "auto_policy":
        return "note"
    o = _pl(r).get("outcome")
    if isinstance(o, str):
        return o
    a = str(r.get("action") or "")
    if a in NG_ACTIONS:
        return "ng"
    if a in TAKE_ACTIONS:
        return "take"
    if a == "hesitated":
        return "hesitate"
    if a == "unseen":
        return "none"
    return "note"


def addr_of(r: dict[str, Any]) -> str:
    s = str(r.get("from_email") or _pl(r).get("from_email") or "")
    m = re.search(r"[\w.+-]+@[\w.-]+", s)
    return m.group(0).lower() if m else ""


def cand_id(kind: str, key: str) -> str:
    """同じ候補は週をまたいでも同じ番号（前週の「違う」を覚えておける）"""
    return "C" + hashlib.sha1(f"{kind}|{key}".encode("utf-8")).hexdigest()[:8]


def _employee(r: dict[str, Any]) -> str:
    if r.get("employee"):
        return str(r["employee"])
    return {"partner": "111", "general": "116"}.get(str(r.get("lane") or ""), "116")


def hypotheses(rows: list[dict[str, Any]], *, rejected: set[str] | None = None) -> list[dict[str, Any]]:
    """機械で作るルール候補。強いものから最大3件"""
    rejected = rejected or set()
    small = len(rows) < SMALL_LOG
    out: list[dict[str, Any]] = []

    # 1) 同じ送り手を2回以上見送り（理由が「回答不要」系）で、採ったことがない → hide
    by_addr: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if str(r.get("surface") or "").startswith("triage") and r.get("surface") != "triage_miss":
            a = addr_of(r)
            if a:
                by_addr[a].append(r)
    for a, rs in by_addr.items():
        ng = [r for r in rs if outcome(r) == "ng"]
        took = [r for r in rs if outcome(r) == "take"]
        reasons = Counter(t for r in ng for t in (_pl(r).get("reason_tags") or []))
        if len(ng) >= 2 and not took:
            strong = sum(n for t, n in reasons.items() if t in HIDE_REASONS)
            out.append({
                "id": cand_id("hide", a),
                "kind": "hide",
                "employee": "116",
                "key": a,
                "rule_line": f"hide | from:{a} | scope=partner",
                "text": f"{a} からのメールは、次から判断デスクにも Slack にも出しません",
                "why": f"見送り {len(ng)} 回・採ったこと 0 回" + (f"（理由: {', '.join(reasons)}）" if reasons else ""),
                "evidence": [r.get("id") for r in ng][:10],
                "score": len(ng) * 10 + strong * 5,
                "needs_ai": False,
            })

    # 2) 見落としだった（仕分けが外れた）送り手 → keep（例外）
    for r in rows:
        if r.get("surface") == "triage_miss" and r.get("action") == "wrong":
            a = addr_of(r)
            if not a:
                continue
            out.append({
                "id": cand_id("keep", a),
                "kind": "keep",
                "employee": "116",
                "key": a,
                "rule_line": f"keep | from:{a}",
                "text": f"{a} は自動で見送らず、必ず出します（見落としだった）",
                "why": "見落としで「要対応だった」",
                "evidence": [r.get("id")],
                "score": 40,
                "needs_ai": False,
            })

    # 3) 同じ相手に「直して送った」「下書きを直した（draft_review の版直し）」が2回以上
    #    → 言い回し（文言は 314 が差分と payload.reason / rule_hint から決める）
    by_partner: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        revised = r.get("surface") == "draft_review" and r.get("action") == "revise"
        if ((r.get("action") == "sent" and r.get("edited")) or revised) and r.get("partner"):
            by_partner[str(r["partner"])].append(r)
    for p, rs in by_partner.items():
        if len(rs) >= 2:
            out.append({
                "id": cand_id("rewrite", p),
                "kind": "rewrite",
                "employee": "211",
                "key": p,
                "rule_line": f"rewrite | partner:{p}",
                "text": f"{p} への下書きで、毎回同じ直しをしています（{len(rs)} 回）。直し方を下書きに入れます",
                "why": f"直した {len(rs)} 回"
                + ("（ヒント: " + " / ".join(h for h in (_pl(r).get("rule_hint") for r in rs) if h)[:300] + "）"
                   if any(_pl(r).get("rule_hint") for r in rs) else ""),
                "evidence": [r.get("id") for r in rs][:10],
                "score": len(rs) * 8,
                "needs_ai": True,  # 文言は差分から 314 が埋める
            })

    # 4) 次の一手の型が2回以上「違う」 → 型を直す（コード）
    wrong_steps = Counter(str(_pl(r).get("next_step_id") or "") for r in rows if r.get("action") == "next_wrong")
    for sid, n in wrong_steps.items():
        if sid and n >= 2:
            out.append({
                "id": cand_id("template", sid),
                "kind": "template",
                "employee": "116",
                "key": sid,
                "rule_line": "",
                "text": f"次の一手「{sid}」が {n} 回外れました。この型の出し方を見直します",
                "why": f"違う {n} 回",
                "evidence": [r.get("id") for r in rows if _pl(r).get("next_step_id") == sid][:10],
                "score": n * 6,
                "needs_ai": False,
            })

    out = [c for c in out if c["id"] not in rejected]
    out.sort(key=lambda c: -c["score"])
    for c in out:
        c["status"] = "hypothesis" if small else "candidate"
        c["options"] = options_for(c)
    return out[:MAX_CANDIDATES]


FREE_MAIL = {"gmail.com", "yahoo.co.jp", "icloud.com", "outlook.com", "hotmail.com", "outlook.jp", "me.com", "docomo.ne.jp", "ezweb.ne.jp", "softbank.ne.jp"}


def options_for(c: dict[str, Any]) -> list[dict[str, str]]:
    """候補ごとの「どう効かせるか」の選択肢。最初が既定（今の rule_line）。
    どれも jarvis_learned_rules.py が読める書き方だけにする（効き目 hide/demote/boost/keep/rewrite）"""
    k, key = c.get("kind"), str(c.get("key") or "")
    first = {"id": "main", "label": "", "rule_line": c.get("rule_line") or "", "text": c.get("text") or ""}
    if k == "hide":
        first["label"] = "出さない"
        opts = [first, {
            "id": "demote",
            "label": "出すが後回し",
            "rule_line": f"demote-20 | from:{key} | scope=partner",
            "text": f"{key} からのメールは出しますが、並びを下げて後回しにします（見送り寄り）",
        }]
        dom = key.split("@", 1)[1] if "@" in key else ""
        if dom and dom not in FREE_MAIL:
            opts.append({
                "id": "domain",
                "label": f"@{dom} ごと出さない",
                "rule_line": f"hide | from:@{dom} | scope=partner",
                "text": f"@{dom} から届くメールは、送り手に関係なく出しません",
            })
        return opts
    if k == "keep":
        first["label"] = "必ず出す"
        return [first, {
            "id": "boost",
            "label": "必ず出して上の方に",
            "rule_line": f"boost+20 | from:{key}",
            "text": f"{key} は必ず出し、並びも上げます（見落とし防止）",
        }]
    first["label"] = "このとおり"
    return [first]


def rule_effects(rows: list[dict[str, Any]]) -> dict[str, Counter]:
    """ルール番号ごとの結果（効いたか）"""
    eff: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        for rid in _pl(r).get("applied_rules") or []:
            eff[str(rid)][outcome(r)] += 1
    return eff


def stay_reasons(rows: list[dict[str, Any]]) -> Counter:
    c: Counter = Counter()
    for r in rows:
        s = _pl(r).get("stay_reason")
        if s:
            c[str(s)] += 1
    return c


def next_step_hits(rows: list[dict[str, Any]]) -> dict[str, Counter]:
    h: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        if r.get("action") in ("next_good", "next_wrong"):
            h[str(_pl(r).get("next_step_id") or "-")][r["action"]] += 1
    return h


def changes(rows: list[dict[str, Any]]) -> list[str]:
    """あなたの判断で変わったこと（今週の rule_review）"""
    out = []
    for r in rows:
        if r.get("surface") != "rule_review":
            continue
        pl = _pl(r)
        line = pl.get("rule_line") or pl.get("rule_id") or r.get("target_id")
        if r.get("action") == "rule_accept":
            out.append(f"- 採用: {pl.get('text') or line}")
        elif r.get("action") == "rule_revert":
            out.append(f"- 取り消し: {pl.get('text') or line}")
    return out


def owner_comments(rows: list[dict[str, Any]]) -> list[str]:
    """ルール候補への「直してひとこと」（ダッシュボード /review・loopware）。314 が修正案に反映する"""
    out = []
    for r in rows:
        if r.get("surface") != "rule_review" or not r.get("note"):
            continue
        pl = _pl(r)
        about = pl.get("text") or pl.get("rule_line") or pl.get("candidate_id") or r.get("target_id")
        verb = {"rule_accept": "採用", "rule_once": "今回だけ", "rule_reject": "違う"}.get(str(r.get("action")), "")
        head = f"（{verb}{'・' + str(pl['option_label']) if pl.get('option_label') else ''}）" if verb else ""
        out.append(f"- [{pl.get('candidate_id') or r.get('target_id')}]{head} {about} → 「{str(r['note'])[:300]}」")
    return out


def sections(rows: list[dict[str, Any]], cands: list[dict[str, Any]]) -> str:
    """週次まとめに足す節（Markdown）"""
    o = Counter(outcome(r) for r in rows)
    lines = [
        "",
        "## ループウェア（機械で束ねた結果）",
        "",
        f"- 採った {o['take']}・見送った {o['ng']}・迷った {o['hesitate']}・未判断 {o['none']}・後で {o['later']}・ひとこと {o['note']}",
        f"- 声のひとこと: {sum(1 for r in rows if _pl(r).get('voice'))} 件",
    ]
    ch = changes(rows)
    lines += ["", "### あなたの判断で変わったこと", *(ch or ["- 今週はありません"])]
    oc = owner_comments(rows)
    if oc:
        lines += ["", "### あなたのひとこと（314 はこれを修正案・文言に必ず反映する）", *oc]
    lines += ["", f"### ルール候補（最大 {MAX_CANDIDATES} 件{'・ログが少ないので仮説' if len(rows) < SMALL_LOG else ''}）"]
    if not cands:
        lines.append("- 今週はありません")
    for c in cands:
        lines.append(f"- [{c['id']}] {c['text']}（{c['why']}）" + ("　※文言は 314 が差分から" if c.get("needs_ai") else ""))
    eff = rule_effects(rows)
    lines += ["", "### 効いたルール（applied_rules）"]
    if not eff:
        lines.append("- 今週はルールが効いた判断がありません")
    for rid, c in sorted(eff.items()):
        lines.append(f"- {rid}: 採った {c['take']}・見送った {c['ng']}・迷った {c['hesitate']}")
    st = stay_reasons(rows)
    lines += ["", "### 残っている理由（多い順に潰す）"]
    lines += [f"- {STAY_LABEL.get(k, k)} {n}" for k, n in st.most_common()] or ["- なし"]
    fixes = [r for r in rows if r.get("surface") == "uiux_fix"]
    if fixes or any(r.get("surface") in ("uiux_plan", "uiux_rule") for r in rows):
        from jarvis_uiux_loop import fix_metrics, metrics_lines  # noqa: PLC0415

        lines += ["", "### 画面の好み（UI/UX。擦り合わせは減っているか）", *metrics_lines(fix_metrics(fixes))]
    hits = next_step_hits(rows)
    if hits:
        lines += ["", "### 次の一手の型"]
        for sid, c in sorted(hits.items()):
            n = c["next_good"] + c["next_wrong"]
            lines.append(f"- {sid}: 良い {c['next_good']}／{n}（{c['next_good'] / n:.0%}）")
    return "\n".join(lines) + "\n"


def obsidian_note(rows: list[dict[str, Any]], cands: list[dict[str, Any]], *, week: str) -> str:
    """松野さん用の週報（Obsidian）。数字と変わったことだけ、短く"""
    o = Counter(outcome(r) for r in rows)
    ch = changes(rows)
    body = [
        "---",
        f"week: {week}",
        "tags: [判断ログ, ループウェア]",
        "---",
        f"# 判断ログ {week}",
        "",
        f"判断 {len(rows)} 件（採った {o['take']}・見送った {o['ng']}・迷った {o['hesitate']}・未判断 {o['none']}）",
        "",
        "## あなたの判断で変わったこと",
        *(ch or ["- 今週はありません"]),
        "",
        "## 来週見るルール候補",
        *([f"- {c['text']}" for c in cands] or ["- なし"]),
        "",
    ]
    return "\n".join(body)


def improvement_lines(rows: list[dict[str, Any]], *, week: str) -> dict[str, list[str]]:
    """社員ごとの改善ログ（logs/改善ログ.md に足す行）: 採用・取り消したルールと、効いた回数"""
    eff = rule_effects(rows)
    out: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        if r.get("surface") != "rule_review" or r.get("action") not in ("rule_accept", "rule_revert"):
            continue
        pl = _pl(r)
        emp = str(pl.get("employee") or r.get("employee") or "")
        rid = str(pl.get("rule_id") or "")
        verb = "採用" if r.get("action") == "rule_accept" else "取り消し"
        out[emp].append(f"- {week} {verb} {rid} {pl.get('text') or pl.get('rule_line') or ''}".rstrip())
    for rid, c in eff.items():
        m = re.match(r"R(\w+?)-\d+", rid)
        if m:
            out[m.group(1)].append(f"- {week} {rid} が効いた判断 {sum(c.values())} 件（採った {c['take']}・見送った {c['ng']}）")
    return out


# ---------------------------------------------------------------- DB


def _sb():
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY 未設定")
    return create_client(url, key)


def attach_from_email(sb, rows: list[dict[str, Any]]) -> None:
    """triage の行に送り手アドレスを付ける（判断ログには入っていないため）"""
    ids = sorted({str(r["target_id"]) for r in rows if r.get("target_type") == "triage_item" and not addr_of(r)})
    found: dict[str, str] = {}
    for i in range(0, len(ids), 200):
        res = sb.table("triage_items").select("id,from_email").in_("id", ids[i : i + 200]).execute()
        for x in res.data or []:
            found[str(x["id"])] = str(x.get("from_email") or "")
    for r in rows:
        if r.get("target_type") == "triage_item" and not r.get("from_email"):
            r["from_email"] = found.get(str(r.get("target_id")), "")


def rejected_ids(sb, days: int = 56) -> set[str]:
    """「違う」と言われた候補は8週間出さない"""
    since = (datetime.now(JST) - timedelta(days=days)).isoformat()
    res = (
        sb.table("owner_decisions").select("target_id")
        .eq("surface", "rule_review").eq("action", "rule_reject").gte("decided_at", since).execute()
    )
    return {str(x["target_id"]) for x in res.data or []}


def publish_candidates(sb, cands: list[dict[str, Any]], *, week: str) -> None:
    """loopware が読む置き場（sync_meta）。新しい表は作らない"""
    value = {"week": week, "at": datetime.now(JST).isoformat(timespec="seconds"), "candidates": cands}
    sb.table("sync_meta").upsert(
        {"key": "loopware_rule_candidates", "value": json.dumps(value, ensure_ascii=False),
         "updated_at": datetime.now(JST).isoformat()},
        on_conflict="key",
    ).execute()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--json", help="候補を JSON で書き出す")
    ap.add_argument("--publish", action="store_true", help="候補を sync_meta に置く（loopware のルール候補）")
    args = ap.parse_args(argv)
    from jarvis_owner_decisions_weekly import fetch  # noqa: PLC0415

    until = datetime.now(JST)
    sb = _sb()
    rows = fetch(sb, until - timedelta(days=args.days))
    attach_from_email(sb, rows)
    cands = hypotheses(rows, rejected=rejected_ids(sb))
    week = until.strftime("%G-W%V")
    sys.stdout.write(sections(rows, cands))
    if args.json:
        Path(args.json).write_text(json.dumps(cands, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.publish:
        publish_candidates(sb, cands, week=week)
        print(f"# published {len(cands)} candidates week={week}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
