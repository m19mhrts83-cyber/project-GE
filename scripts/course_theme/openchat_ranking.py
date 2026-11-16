#!/usr/bin/env python3
"""(4) の拡張: LINEオープンチャットの質問ランキングの週次の回を作る（2026-11-16）。

1. DB 関数 qa_openchat_question_digest(120) で、質問らしい投稿だけを DB の中で選んで受け取る
   （120日で 3,000 件前後・600KB 前後。投稿者名は来ない。人数用のハッシュだけ）。
2. Gemini に、オープンチャットごとに「同じ趣旨の質問のまとまり」を作らせる（1回 最大 250 件）。
3. できたまとまりの名前を Gemini にもう一度渡し、オープンチャットをまたいで同じ話題を1つにまとめさせる。
4. 件数・人数・返信数・直近30日の数はこのスクリプトが数える（Gemini には数えさせない）。
5. qa_openchat_rankings に1行入れる。運営分析（スイッチ openchat_ranking）で見る。

必要な環境変数: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, GEMINI_API_KEY（任意 GEMINI_MODEL, THEME_DAYS, DRY_RUN=1）
結果の本文はログに出さない（件数だけ）。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from weekly_round import GEMINI_KEY, JST, KEY, MODEL, STR, URL, gemini, rest, s_  # noqa: E402

DAYS = int(os.environ.get("THEME_DAYS", "120"))
BATCH = 250
RECENT_DAYS = 30

GROUP_SCHEMA = {"type": "OBJECT", "required": ["groups"], "properties": {
    "groups": {"type": "ARRAY", "items": {"type": "OBJECT", "required": ["topic", "ids"], "properties": {
        "topic": STR, "ids": {"type": "ARRAY", "items": STR}}}}}}
MERGE_SCHEMA = {"type": "OBJECT", "required": ["topics"], "properties": {
    "topics": {"type": "ARRAY", "items": {"type": "OBJECT", "required": ["topic", "ids"], "properties": {
        "topic": STR, "ids": {"type": "ARRAY", "items": STR}}}}}}

GROUP_PROMPT = """不動産投資家コミュニティ「神・大家さん倶楽部」の LINE オープンチャット「%s」に投稿された、
質問らしい投稿の一覧です。同じ趣旨の質問（言い方が違っても聞きたいことが同じもの）を1つのまとまりにしてください。
- 各投稿は id で指定し、1つの投稿は1つのまとまりにだけ入れる。どこにも当てはまらない投稿は、その1件だけのまとまりにする。
- topic は会員が聞いていることを会員の言葉で20字以内（例: 「築古戸建の修繕費の目安」「融資の自己資金はいくら必要か」）。
  具体的な物件名・地名・個人名・会社名は入れない。
- お礼・あいさつ・相づち・感想・お知らせなど、ほかの人に答えを求めていない投稿は topic を「(質問以外)」にする。
- 数を数える必要はありません。

出力は次の形の JSON だけ: {"groups":[{"topic":"","ids":["p1","p2"]}]}

投稿一覧（id, 投稿日, 本文）:
%s
"""

MERGE_PROMPT = """神・大家さん倶楽部の LINE オープンチャットごとに、似た質問をまとめた「話題」の一覧です。
オープンチャットをまたいで同じ趣旨の話題を1つにまとめ、会員に分かる共通の名前を付けてください。
- 各話題は id で指定し、1つの id は1つのまとまりにだけ入れる。ほかと同じでない話題は、その1件だけのまとまりにする。
- topic は20字以内。具体的な物件名・地名・個人名・会社名は入れない。
- 細かくしすぎない（「火災保険の選び方」と「火災保険の補償の決め方」は同じ）。ただし別の悩みはまとめない
  （「融資の金利」と「融資の自己資金」は別）。
- 数を数える必要はありません。

出力は次の形の JSON だけ: {"topics":[{"topic":"","ids":["g1","g2"]}]}

話題一覧（id, オープンチャット, 話題, 投稿数）:
%s
"""


def short_chat(name: str) -> str:
    return str(name or "").replace("【神大家】", "").strip()[:40]


def batches(questions: list[dict]) -> list[tuple[str, list[dict]]]:
    by: dict[str, list[dict]] = {}
    for q in questions:
        by.setdefault(q["chat"], []).append(q)
    out = []
    for chat, qs in by.items():
        for i in range(0, len(qs), BATCH):
            out.append((chat, qs[i:i + BATCH]))
    return out


def group_batch(chat: str, qs: list[dict]) -> list[tuple[str, list[dict]]]:
    """1つのオープンチャット（の一部）を Gemini でまとめる。入れ忘れた投稿は1件のまとまりにする。"""
    by_id = {f"p{i + 1}": q for i, q in enumerate(qs)}
    listing = "\n".join(f'{i}\t{q["d"]}\t{q["text"]}' for i, q in by_id.items())
    groups = gemini(GROUP_PROMPT % (short_chat(chat), listing), GROUP_SCHEMA).get("groups") or []
    used: set[str] = set()
    out = []
    for g in groups:
        if not isinstance(g, dict):
            continue
        ids = [i for i in dict.fromkeys(str(x) for x in (g.get("ids") or [])) if i in by_id and i not in used]
        if not ids:
            continue
        used.update(ids)
        out.append((s_(g.get("topic"), 40) or "(名前なし)", [by_id[i] for i in ids]))
    for i, q in by_id.items():
        if i not in used:
            out.append((s_(q.get("text"), 30), [q]))
    return [(t, ps) for t, ps in out if t != "(質問以外)"]


def merge_topics(local: list[dict]) -> dict[str, str]:
    """オープンチャットごとの話題（g1..）を、共通の話題名に対応させる。返り値 {gid: 共通の話題名}。"""
    listing = "\n".join(f'{g["gid"]}\t{short_chat(g["chat"])}\t{g["topic"]}\t{len(g["posts"])}' for g in local)
    res = gemini(MERGE_PROMPT % listing, MERGE_SCHEMA).get("topics") or []
    known = {g["gid"] for g in local}
    name: dict[str, str] = {}
    for t in res:
        if not isinstance(t, dict):
            continue
        topic = s_(t.get("topic"), 40)
        for gid in (str(x) for x in (t.get("ids") or [])):
            if gid in known and gid not in name and topic:
                name[gid] = topic
    for g in local:
        name.setdefault(g["gid"], g["topic"])
    return name


def build(local: list[dict], name: dict[str, str], today: dt.date) -> tuple[list[dict], list[dict]]:
    """件数（投稿数）・人数（ハッシュの重複なし）・返信数・直近30日をスクリプトで数える。"""
    recent_from = (today - dt.timedelta(days=RECENT_DAYS)).isoformat()
    topics: dict[str, dict] = {}
    chats: dict[str, dict] = {}
    for g in local:
        topic = name[g["gid"]]
        t = topics.setdefault(topic, {"posts": [], "chats": {}})
        t["posts"].extend(g["posts"])
        t["chats"][g["chat"]] = t["chats"].get(g["chat"], 0) + len(g["posts"])
        c = chats.setdefault(g["chat"], {})
        c.setdefault(topic, []).extend(g["posts"])

    def people(posts):
        return len({p.get("u") for p in posts if p.get("u")})

    def examples(posts, n):
        seen, out = set(), []
        # 返信の多かった（よく答えた）投稿を先に、同じなら新しい順
        newest = sorted(posts, key=lambda p: p.get("d") or "", reverse=True)
        for p in sorted(newest, key=lambda p: -int(p.get("r") or 0)):
            key = s_(p.get("text"), 40)
            if key in seen:
                continue
            seen.add(key)
            out.append(p)
            if len(out) >= n:
                break
        return out

    ranking = []
    for topic, t in topics.items():
        posts = t["posts"]
        ranking.append({
            "topic": topic, "count": len(posts), "people": people(posts),
            "replies": sum(int(p.get("r") or 0) for p in posts),
            "recent": sum(1 for p in posts if (p.get("d") or "") >= recent_from),
            "chats": [{"chat": short_chat(c), "n": n} for c, n in sorted(t["chats"].items(), key=lambda x: -x[1])][:8],
            "examples": [{"chat": short_chat(p["chat"]), "d": p.get("d") or "", "text": s_(p.get("text"), 140)} for p in examples(posts, 3)],
        })
    ranking.sort(key=lambda r: (-r["count"], -r["people"], r["topic"]))

    by_chat = []
    for chat, tmap in chats.items():
        allp = [p for ps in tmap.values() for p in ps]
        top = sorted(({"topic": tp, "count": len(ps), "people": people(ps),
                       "examples": [s_(p.get("text"), 140) for p in examples(ps, 2)]} for tp, ps in tmap.items()),
                     key=lambda x: (-x["count"], -x["people"], x["topic"]))[:10]
        by_chat.append({"chat": short_chat(chat), "questions": len(allp), "people": people(allp), "top": top})
    by_chat.sort(key=lambda c: (-c["questions"], c["chat"]))
    return ranking[:30], by_chat[:40]


def main() -> None:
    if not (URL and KEY and GEMINI_KEY):
        raise SystemExit("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / GEMINI_API_KEY が必要です")
    digest = rest("rpc/qa_openchat_question_digest", "POST", {"p_days": DAYS})
    size = len(json.dumps(digest, ensure_ascii=False).encode())
    questions = digest.get("questions") or []
    local: list[dict] = []
    for chat, qs in batches(questions):
        for topic, posts in group_batch(chat, qs):
            local.append({"gid": f"g{len(local) + 1}", "chat": chat, "topic": topic, "posts": posts})
    try:
        name = merge_topics(local) if local else {}
    except SystemExit as e:  # まとめ直しに失敗しても、オープンチャットごとの名前のまま出す
        print(f"話題のまとめ直しを省きました: {e}", file=sys.stderr)
        name = {g["gid"]: g["topic"] for g in local}
    today = dt.datetime.now(JST).date()
    ranking, by_chat = build(local, name, today)
    counted = [p for g in local for p in g["posts"]]
    now = dt.datetime.now(JST)
    rid = "r" + now.strftime("%Y%m%d")
    if rest(f"qa_openchat_rankings?select=id&id=eq.{rid}"):
        rid += now.strftime("-%H%M")
    row = {"id": rid, "period_days": DAYS, "model": MODEL, "ranking": ranking, "by_chat": by_chat,
           "stats": {"posts": int(digest.get("posts") or 0), "candidates": len(questions), "questions": len(counted),
                     "people": len({p.get("u") for p in counted if p.get("u")}), "chats": len(by_chat)}}
    print(f"round={rid} digest_kb={size // 1024} candidates={len(questions)} questions={len(counted)} "
          f"local_topics={len(local)} ranking={len(ranking)} chats={len(by_chat)}")
    if os.environ.get("DRY_RUN") == "1":
        return
    rest("qa_openchat_rankings", "POST", row, prefer="return=minimal")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300] if "googleapis" in (e.url or "") else ""
        print(f"HTTP {e.code} {e.url.split('?')[0]} {detail}", file=sys.stderr)
        sys.exit(1)
