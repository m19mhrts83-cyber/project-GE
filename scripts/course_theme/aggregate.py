#!/usr/bin/env python3
"""講座テーマ提案ループウェア（試作）: 神大家 Q&A の Supabase を PostgREST で読み、集計 JSON を出す。

- 読み取りのみ。必要な列だけ取り、本文は件数を絞って先頭だけ残す（通信量対策）
- 会員名・メール・セッションID は出力しない
- 出力: resp.json（呼び出し側で暗号化する）
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request

BASE = os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/"
KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
NOW = dt.datetime.now(dt.timezone.utc)
D120 = (NOW - dt.timedelta(days=120)).isoformat()
D180 = (NOW - dt.timedelta(days=180)).isoformat()
total_bytes = 0


def get(table: str, params: dict, page: int = 1000, max_rows: int = 60000) -> list[dict]:
    global total_bytes
    rows: list[dict] = []
    offset = 0
    while offset < max_rows:
        lim = min(page, max_rows - offset)
        q = urllib.parse.urlencode({**params, "limit": lim, "offset": offset}, safe="*,().:")
        req = urllib.request.Request(BASE + table + "?" + q, headers={"apikey": KEY, "Authorization": f"Bearer {KEY}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
        total_bytes += len(body)
        chunk = json.loads(body)
        rows.extend(chunk)
        if len(chunk) < lim:
            break
        offset += lim
    return rows


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def clip(s: str, n: int) -> str:
    return re.sub(r"\s+", " ", s or "")[:n]


QLIKE = "(content.like.*？*,content.like.*?*,content.like.*教えて*,content.like.*悩*)"

out: dict = {"generated_at": NOW.isoformat()}

# 1) チャットボット質問ログ
ev = get("app_qa_search_events", {
    "select": "created_at,query_text,comment_hit_count,chunk_hit_count,result_status,user_id",
    "created_at": f"gte.{D120}", "order": "created_at.asc"})
qc = collections.Counter()
zc = collections.Counter()
weekly = collections.Counter()
users = set()
for e in ev:
    q = norm(e.get("query_text"))
    if not q:
        continue
    hits = (e.get("comment_hit_count") or 0) + (e.get("chunk_hit_count") or 0)
    qc[q] += 1
    if hits == 0 and e.get("result_status") == "ok":
        zc[q] += 1
    if e.get("user_id"):
        users.add(e["user_id"])
    d = dt.datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")).date()
    weekly[(d - dt.timedelta(days=d.weekday())).isoformat()] += 1
out["search"] = {"events": sum(qc.values()), "unique_queries": len(qc), "users": len(users),
                 "zero_hit": sum(zc.values()),
                 "first": ev[0]["created_at"] if ev else None, "last": ev[-1]["created_at"] if ev else None}
out["search_weekly"] = sorted(weekly.items())
out["search_top"] = [{"q": q[:120], "n": n, "zero": zc.get(q, 0)} for q, n in qc.most_common(300)]

# 2) コミュニティコメント（カテゴリ・トピック）
cm = get("comments", {"select": "forum_category,topic_title,posted_at"})
cat = collections.Counter()
cat180 = collections.Counter()
topic = collections.Counter()
for c in cm:
    k = c.get("forum_category") or "(なし)"
    cat[k] += 1
    if (c.get("posted_at") or "") >= D180:
        cat180[k] += 1
        topic[(c.get("forum_category") or "", clip(c.get("topic_title") or "", 100))] += 1
out["comments_total"] = len(cm)
out["comment_categories"] = [{"cat": k, "n": n, "n180": cat180.get(k, 0)} for k, n in cat.most_common()]
out["comment_topics_180d"] = [{"cat": a, "topic": b, "n": n} for (a, b), n in topic.most_common(200)]
cq = get("comments", {"select": "forum_category,posted_at,content", "posted_at": f"gte.{D120}",
                      "or": QLIKE, "order": "posted_at.desc"}, page=300, max_rows=300)
out["comment_questions_120d"] = [{"cat": c.get("forum_category") or "", "d": (c.get("posted_at") or "")[:7],
                                  "text": clip(c.get("content"), 140)} for c in cq]

# 3) LINEオプチャ
oc = get("line_openchat_logs", {"select": "chat_title,thread_title,post_date,is_repair_related,repair_category",
                                "post_date": f"gte.{D120[:10]}"})
out["openchat_120d"] = {
    "posts": len(oc),
    "by_chat": collections.Counter(o.get("chat_title") or "" for o in oc).most_common(),
    "repair_cat": collections.Counter(o.get("repair_category") or "(なし)" for o in oc if o.get("is_repair_related")).most_common(),
    "threads": collections.Counter(clip(o.get("thread_title") or "", 80) for o in oc if o.get("thread_title")).most_common(80),
}
oq = get("line_openchat_logs", {"select": "chat_title,post_date,content", "post_date": f"gte.{D120[:10]}",
                                "or": "(content.like.*？*,content.like.*?*)", "order": "post_date.desc"},
         page=200, max_rows=200)
out["openchat_120d"]["question_like"] = [{"chat": o.get("chat_title"), "d": o.get("post_date"),
                                          "text": clip(o.get("content"), 140)} for o in oq]

# 4) 既存講座（文字起こし済み動画など）
ks = get("knowledge_sources", {"select": "title,instructor,published_at,content_channel"})
out["knowledge_sources"] = [{"title": clip(k.get("title"), 100), "instructor": k.get("instructor"),
                             "pub": (k.get("published_at") or "")[:7], "ch": k.get("content_channel")} for k in ks]

out["egress_bytes"] = total_bytes
with open("resp.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False)
print(f"events={out['search']['events']} uniq={out['search']['unique_queries']} users={out['search']['users']} "
      f"comments={len(cm)} oc_posts={len(oc)} sources={len(ks)} egress_kb={total_bytes // 1024}", file=sys.stderr)
