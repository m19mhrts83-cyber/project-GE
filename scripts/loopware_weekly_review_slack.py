#!/usr/bin/env python3
"""Nody（apps/loopware）週1レビュー：判断ログを集めて Slack で確認を求め、確認済みになるまで見届ける。

流れ（毎日の仕分けでログを貯め、週1で基準を更新する。仮説づくりと判断は Miss Lemon（Claude）のセッションで行い、アプリの従量課金APIは使わない）:
  report … 月曜朝。先週（月〜日・JST）のログを集計して #consult に「確認をお願い」を1通。
  nudge  … 毎朝。確認待ちなら2日後・4日後に1通ずつ催促。
           アプリで「この週のレビューを完了」が押されたら、#report に「確認済み」を1通返して終わり。

状態は Supabase owner_decisions に追記（surface=loopware_review: report_sent / nudge_sent / done_ack）。
確認済みは アプリ側が review_done を追記する。生ログは読むだけで、書き換えない。
Slack の書式は 41_Slackスマホレイアウト（先頭1行＝番号＋役割語／要ボス／空行／1項目2行以内）に合わせる。

必要な環境変数: JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY
                SLACK_WEBHOOK_AI_TEAM_CONSULT（未設定なら REPORT に落ちる＝jarvis_slack_webhook_post.py）
使い方: python scripts/loopware_weekly_review_slack.py --mode report|nudge [--dry-run] [--week YYYY-MM-DD]
Miss Lemon 用（週次レビューのセッションで使う。Slack には出さない）:
  --mode export                      … その週の判断ログを Markdown で出力（仮説づくりの材料）
  --mode criteria-list               … 承認済みの基準を表示
  --mode criteria-add --text ... [--range ...] [--basis ...]   … 松野さんが了承した基準を追記
  --mode criteria-revoke --id cr-...  … 基準の取り消し（履歴は残る）
  --mode review-done [--week ...]    … 週を「確認済み」にする（翌朝の「確認済み」返信につながる）
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
APP_URL = os.environ.get("LOOPWARE_URL", "https://jarvis-loopware.vercel.app")
HERE = Path(__file__).resolve().parent


def _env() -> tuple[str, str]:
    url = os.environ.get("JARVIS_SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        print("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が未設定", file=sys.stderr)
        sys.exit(2)
    return url, key


def rest(path: str, params: dict | None = None, method: str = "GET", body: dict | None = None):
    url, key = _env()
    q = ("?" + urllib.parse.urlencode(params, safe=",.:()*")) if params else ""
    req = urllib.request.Request(
        f"{url}/rest/v1/{path}{q}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def week_bounds(monday: datetime) -> tuple[str, str]:
    start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7)
    return start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat()


def last_monday(now: datetime) -> datetime:
    d = now - timedelta(days=(now.weekday()))
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def collect(monday: datetime) -> dict:
    frm, to = week_bounds(monday)
    items: list[dict] = []

    ds = rest(
        "task_loop_decisions",
        {
            "select": "topic_id,choice,final_text,before_text,after_text,reason_tags,free_note,updated_at",
            "updated_at": f"gte.{frm}",
            "and": f"(updated_at.lt.{to})",
            "limit": "1000",
        },
    ) or []
    for d in ds:
        items.append(
            {
                "choice": d["choice"],
                "reasons": d.get("reason_tags") or [],
                "edited": bool(d.get("before_text") and d.get("after_text")),
                "scope": "once",
            }
        )

    od = rest(
        "owner_decisions",
        {
            "select": "surface,action,payload,decided_at",
            "surface": "in.(todoist_313,loopware_voice,loopware_daily)",
            "decided_at": f"gte.{frm}",
            "and": f"(decided_at.lt.{to})",
            "limit": "1000",
        },
    ) or []
    voice = 0
    for r in od:
        p = r.get("payload") or {}
        if r["surface"] == "loopware_voice":
            if r["action"] == "voice_comment":
                voice += 1
        elif r["surface"] == "loopware_daily":
            continue  # 日数は下で target_id から数える
        elif p.get("kind") == "loopware":
            items.append(
                {
                    "choice": r["action"],
                    "reasons": p.get("reason_tags") or [],
                    "edited": bool(p.get("before_text") and p.get("after_text")),
                    "scope": p.get("scope") or "once",
                }
            )

    # 毎日の仕分け：target_id の日付で数え直す
    dd = rest(
        "owner_decisions",
        {
            "select": "target_id",
            "surface": "eq.loopware_daily",
            "action": "eq.daily_done",
            "decided_at": f"gte.{frm}",
            "and": f"(decided_at.lt.{to})",
        },
    ) or []
    days = {r["target_id"] for r in dd}

    crit = rest(
        "owner_decisions",
        {
            "select": "action,target_id",
            "surface": "eq.loopware_criteria",
            "order": "id.asc",
            "limit": "1000",
        },
    ) or []
    live: set[str] = set()
    for c in crit:
        if c["action"] == "criteria_revoked":
            live.discard(c["target_id"])
        else:
            live.add(c["target_id"])

    take = sum(1 for i in items if i["choice"] in ("take", "use", "close"))
    skip = sum(1 for i in items if i["choice"] in ("skip", "none_of_above", "drop"))
    hold = sum(1 for i in items if i["choice"] == "hold")
    why: dict[str, int] = {}
    for i in items:
        if i["choice"] in ("skip", "none_of_above", "drop"):
            for t in i["reasons"]:
                why[t] = why.get(t, 0) + 1
    return {
        "n": len(items),
        "take": take,
        "skip": skip,
        "hold": hold,
        "edits": sum(1 for i in items if i["edited"]),
        "rules": sum(1 for i in items if i["scope"] == "rule"),
        "voice": voice,
        "days": len(days),
        "why": sorted(why.items(), key=lambda x: -x[1])[:3],
        "criteria": len(live),
    }


def collect_detail(monday: datetime) -> tuple[list[dict], list[dict], list[str]]:
    """仮説づくり用の詳細。(判断, 音声コメント, 完了した日) を返す。"""
    frm, to = week_bounds(monday)
    items: list[dict] = []
    ds = rest(
        "task_loop_decisions",
        {
            "select": "topic_id,chosen_index,choice,final_text,before_text,after_text,reason_tags,free_note,updated_at",
            "updated_at": f"gte.{frm}",
            "and": f"(updated_at.lt.{to})",
            "order": "updated_at.asc",
            "limit": "1000",
        },
    ) or []
    topics: dict[str, str] = {}
    if ds:
        ids = ",".join(d["topic_id"] for d in ds)
        for t in rest("task_loop_topics", {"select": "id,topic_text", "id": f"in.({ids})"}) or []:
            topics[t["id"]] = t["topic_text"]
    for d in ds:
        note = d.get("free_note") or ""
        rule = note.startswith("【次も同じに】")
        items.append(
            {
                "at": d["updated_at"],
                "agent": "312",
                "topic": topics.get(d["topic_id"], ""),
                "choice": d["choice"],
                "reasons": d.get("reason_tags") or [],
                "note": note.replace("【次も同じに】", ""),
                "final": d.get("final_text") or "",
                "before": d.get("before_text") or "",
                "after": d.get("after_text") or "",
                "scope": "rule" if rule else "once",
            }
        )
    od = rest(
        "owner_decisions",
        {
            "select": "surface,action,subject,note,payload,decided_at",
            "surface": "in.(todoist_313,loopware_voice)",
            "decided_at": f"gte.{frm}",
            "and": f"(decided_at.lt.{to})",
            "order": "decided_at.asc",
            "limit": "1000",
        },
    ) or []
    voice: list[dict] = []
    for r in od:
        p = r.get("payload") or {}
        if r["surface"] == "loopware_voice":
            if r["action"] == "voice_comment":
                voice.append({"at": r["decided_at"], "target": r.get("subject") or "", "text": r.get("note") or "",
                              "alt": p.get("alt_target_label")})
        elif p.get("kind") == "loopware":
            items.append(
                {
                    "at": r["decided_at"],
                    "agent": "313",
                    "topic": r.get("subject") or "",
                    "choice": r["action"],
                    "reasons": p.get("reason_tags") or [],
                    "note": r.get("note") or "",
                    "final": p.get("final_text") or "",
                    "before": p.get("before_text") or "",
                    "after": p.get("after_text") or "",
                    "scope": p.get("scope") or "once",
                }
            )
    dd = rest(
        "owner_decisions",
        {"select": "target_id", "surface": "eq.loopware_daily", "action": "eq.daily_done",
         "decided_at": f"gte.{frm}", "and": f"(decided_at.lt.{to})"},
    ) or []
    return items, voice, sorted({r["target_id"] for r in dd})


def criteria_live() -> list[dict]:
    rows = rest(
        "owner_decisions",
        {"select": "action,target_id,note,payload,decided_at", "surface": "eq.loopware_criteria",
         "order": "id.asc", "limit": "1000"},
    ) or []
    live: dict[str, dict] = {}
    for r in rows:
        if r["action"] == "criteria_revoked":
            live.pop(r["target_id"], None)
        else:
            p = r.get("payload") or {}
            live[r["target_id"]] = {"id": r["target_id"], "text": r.get("note") or "",
                                    "range": p.get("range") or "", "basis": p.get("basis") or ""}
    return list(live.values())


def export_md(monday: datetime) -> str:
    items, voice, days = collect_detail(monday)
    L = [f"# Nody 判断ログ {span(monday)}（週の月曜 {monday:%Y-%m-%d}）", ""]
    L += [f"- 仕分けを完了した日: {len(days)}日（{', '.join(days) or 'なし'}）",
          f"- 判断: {len(items)}件／音声・文字コメント: {len(voice)}件", ""]
    L += ["## 承認済みの基準（現在）"]
    live = criteria_live()
    L += [f"- {c['id']}: {c['text']}" + (f"（範囲：{c['range']}）" if c["range"] else "") +
          (f"（根拠：{c['basis']}）" if c["basis"] else "") for c in live] or ["- なし"]
    L += ["", "## 判断（生ログ。AIの解釈は含まない）"]
    for i, it in enumerate(items, 1):
        title = (it["topic"] or it["final"]).replace("\n", " / ")[:120]
        L.append(f"{i}. [{it['agent']}] {title} → {it['choice']}（{'次も同じに' if it['scope'] == 'rule' else '今回だけ'}）")
        if it["reasons"]:
            L.append(f"   - 理由：{'・'.join(it['reasons'])}")
        elif it["choice"] in ("skip", "hold", "none_of_above", "drop"):
            L.append("   - 理由：未選択（理由不明として扱う）")
        if it["note"]:
            L.append(f"   - コメント：{it['note']}")
        if it["before"] and it["after"]:
            L.append(f"   - 修正前：{it['before'].replace(chr(10), ' / ')}")
            L.append(f"   - 修正後：{it['after'].replace(chr(10), ' / ')}")
    if voice:
        L += ["", "## 音声・文字コメント（話し始めた時点に見ていたカードごと）"]
        for v in voice:
            L.append(f"- {v['target']}：{v['text']}" + (f"（話し終えたときは「{v['alt']}」を見ていた）" if v.get("alt") else ""))
    L += ["", "## 仮説づくりの注意（設計書）",
          "- 「次も同じに」が付いていない判断は『今回だけ』。基準の根拠にしない。",
          "- 本人の理由とAIの推測を分ける。理由が未選択のものは、理由不明のまま扱う。",
          "- 『知っている』『今は不要』『誤り』を同じ×にしない。見送った＝嫌い、ではない。",
          "- 件数が少ない週は、断定せず『見直す候補』として出す。",
          "- 顧客名・社名・連絡先は、外へ出す前に伏せる。"]
    return "\n".join(L)


def review_rows(week: str) -> list[dict]:
    return (
        rest(
            "owner_decisions",
            {
                "select": "surface,action,decided_at",
                "surface": "in.(loopware_review)",
                "target_id": f"eq.{week}",
                "order": "id.asc",
            },
        )
        or []
    )


def record(week: str, action: str, note: str = ""):
    rest(
        "owner_decisions",
        method="POST",
        body={
            "surface": "loopware_review",
            "action": action,
            "source": "weekly_job",
            "employee": "312",
            "target_type": "loopware_week",
            "target_id": week,
            "subject": f"週次レビュー {week}",
            "note": note or None,
            "payload": {"kind": "loopware"},
        },
    )


def post(channel: str, text: str, dry: bool):
    if dry:
        print(f"--- dry-run（#{channel}）---\n{text}\n---")
        return
    r = subprocess.run(
        [sys.executable, str(HERE / "jarvis_slack_webhook_post.py"), "--channel", channel, "--text", text, "--no-fb-footer"],
        capture_output=True,
        text=True,
    )
    print(r.stdout.strip() or r.stderr.strip())
    if r.returncode != 0:
        sys.exit(r.returncode)


def span(monday: datetime) -> str:
    end = monday + timedelta(days=6)
    return f"{monday.month}/{monday.day}〜{end.month}/{end.day}"


def report_text(monday: datetime, s: dict) -> str:
    why = "／".join(f"{t}×{n}" for t, n in s["why"]) or "理由の記録なし"
    return "\n\n".join(
        [
            f"【相談】Nody 週1レビュー {span(monday)}",
            "📌要ボス: 判断ログの確認（5分）",
            f"・毎日の仕分け: {s['days']}／7日 完了",
            f"・判断: {s['n']}件（採る{s['take']}／見送り{s['skip']}／保留{s['hold']}）",
            f"・見送り理由: {why}",
            f"・直し{s['edits']}件／次も同じに{s['rules']}件／音声{s['voice']}件",
            f"・基準: 承認済み{s['criteria']}件",
            f"見る: {APP_URL}/review",
            "次: Miss Lemonで続行\n\n担当メモ: 「Nodyの週次レビューをして」と声をかけると、仮説をまとめて提案します\n\n橋渡し: 松野さんが了承した基準だけ反映。完了にすると翌朝ここへ「確認済み」を返す",
        ]
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--mode",
        choices=["report", "nudge", "export", "criteria-list", "criteria-add", "criteria-revoke", "review-done"],
        required=True,
    )
    ap.add_argument("--text")
    ap.add_argument("--range", dest="rng", default="")
    ap.add_argument("--basis", default="")
    ap.add_argument("--id")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--week", help="対象週の月曜（YYYY-MM-DD, JST）。既定は先週")
    ap.add_argument("--channel", default="consult")
    a = ap.parse_args()

    now = datetime.now(JST)
    if a.week:
        monday = datetime.strptime(a.week, "%Y-%m-%d").replace(tzinfo=JST)
    else:
        monday = last_monday(now) - timedelta(days=7)
    wk = monday.strftime("%Y-%m-%d")

    if a.mode == "export":
        print(export_md(monday))
        return 0
    if a.mode == "criteria-list":
        for c in criteria_live():
            print(f"- {c['id']}: {c['text']}" + (f"（範囲：{c['range']}）" if c["range"] else "") + (f"（根拠：{c['basis']}）" if c["basis"] else ""))
        return 0
    if a.mode == "criteria-add":
        if not a.text:
            print("--text が必要", file=sys.stderr)
            return 2
        cid = f"cr-{int(datetime.now().timestamp() * 1000)}"
        body = {"surface": "loopware_criteria", "action": "criteria_approved", "source": "miss_lemon",
                "employee": "312", "target_type": "loopware_criteria", "target_id": cid,
                "subject": a.text[:200], "note": a.text, "payload": {"kind": "loopware", "range": a.rng or None, "basis": a.basis or None}}
        if a.dry_run:
            print(json.dumps(body, ensure_ascii=False, indent=2))
        else:
            rest("owner_decisions", method="POST", body=body)
            print(f"承認済みの基準に追記: {cid}")
        return 0
    if a.mode == "criteria-revoke":
        if not a.id:
            print("--id が必要", file=sys.stderr)
            return 2
        body = {"surface": "loopware_criteria", "action": "criteria_revoked", "source": "miss_lemon",
                "employee": "312", "target_type": "loopware_criteria", "target_id": a.id,
                "subject": "基準の取り消し", "payload": {"kind": "loopware"}}
        if a.dry_run:
            print(json.dumps(body, ensure_ascii=False))
        else:
            rest("owner_decisions", method="POST", body=body)
            print(f"取り消し: {a.id}")
        return 0
    if a.mode == "review-done":
        if a.dry_run:
            print(f"review_done を {wk} に記録（dry-run）")
        else:
            record(wk, "review_done", "miss_lemon")
            print(f"{wk} を確認済みにした")
        return 0

    if a.mode == "report":
        rows = review_rows(wk)
        if any(r["action"] == "report_sent" for r in rows) and not a.dry_run:
            print(f"{wk} は報告済み")
            return 0
        s = collect(monday)
        if s["n"] == 0 and s["days"] == 0:
            post("report", f"【報告】Nody 週1レビュー {span(monday)}\n\n判断ログの更新なし（確認は不要）", a.dry_run)
            if not a.dry_run:
                record(wk, "report_sent", "no_data")
            return 0
        post(a.channel, report_text(monday, s), a.dry_run)
        if not a.dry_run:
            record(wk, "report_sent", "ask")
        return 0

    # nudge：直近2週のうち、確認待ちの週を見る
    for back in (7, 0):
        m = monday if a.week else last_monday(now) - timedelta(days=back)
        w = m.strftime("%Y-%m-%d")
        rows = review_rows(w)
        sent = [r for r in rows if r["action"] == "report_sent"]
        if not sent or sent[-1].get("note") == "no_data":
            continue
        done = any(r["action"] == "review_done" for r in rows)
        acked = any(r["action"] == "done_ack" for r in rows)
        if done and not acked:
            s = collect(m)
            post(
                "report",
                "\n\n".join(
                    [
                        f"【報告】Nody 週1レビュー 確認済み {span(m)}",
                        f"・判断{s['n']}件を確認、基準は承認済み{s['criteria']}件",
                        "次: 来週月曜に次の報告",
                    ]
                ),
                a.dry_run,
            )
            if not a.dry_run:
                record(w, "done_ack")
            return 0
        if not done:
            first = datetime.fromisoformat(
                rest("owner_decisions", {"select": "decided_at", "surface": "eq.loopware_review",
                     "action": "eq.report_sent", "target_id": f"eq.{w}", "limit": "1"})[0]["decided_at"].replace("Z", "+00:00")
            )
            nudges = [r for r in rows if r["action"] == "nudge_sent"]
            age = (datetime.now(timezone.utc) - first).days
            if len(nudges) < 2 and age >= 2 * (len(nudges) + 1):
                post(
                    a.channel,
                    "\n\n".join(
                        [
                            f"【相談】Nody 週1レビュー（確認待ち） {span(m)}",
                            "📌要ボス: 判断ログの確認（5分）",
                            "次: Miss Lemonで続行\n\n担当メモ: 「Nodyの週次レビューをして」と声をかける",
                        ]
                    ),
                    a.dry_run,
                )
                if not a.dry_run:
                    record(w, "nudge_sent", f"{len(nudges) + 1}")
            else:
                print(f"{w}: 確認待ち（催促は {len(nudges)}回済み／経過{age}日）")
            return 0
    print("確認待ちなし")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
