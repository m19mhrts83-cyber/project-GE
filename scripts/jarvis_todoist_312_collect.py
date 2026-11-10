#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""312 入口 — Slack の松野さんの発言から『起こり』を拾い、Nody（/312）のお題にする。

  collect（既定。月・水・金 20:30 JST）
    0. 台帳（comm_items: メール・パートナー・自分の送信）からも拾う（--comm-max 件まで・水曜だけ。既定 0＝止め）
       拾う条件: 受信・除外以外・14日以内・new／needs_reply（needs_reply は triage が pending のものだけ）、
       自分の送信は「〜します」の約束だけ。source_ref＝comm_items:<id> で二重にしない
    1. #consult／#ai-hub／#report から、松野さん本人の発言（直近 --hours 時間）を集める
       （AI が松野さんの名前で出した報告文は形で外す。Bot・Webhook 投稿も外す）
    2. 依頼語・問いかけ・「〜したい」で『起こり』を判定（ルールのみ。AI は使わない）
    3. 既存 Todoist の未完了タスクと照らし、近いものを「既存：…」として添える
    4. 3案（登録しない／既存タスクへ追記／別タスクを作る）を型で作り、
       task_loop_topics／task_loop_proposals に入れる（source_ref＝Slack パーマリンクで二重取込しない）
    5. #consult に「312 起票候補 N件 → Nody で開く」を1通

  reflect（30分ごと）
    Nody で「既存タスクへ追記」「別タスクを作る」を選んだお題だけ Todoist に反映し（Slack と台帳の両方）、
    台帳由来は comm_links(todoist_task) を足し、台帳の work_status を waiting にする。
    task_loop_decisions.reflected_todoist_id に記録する。「登録しない」は何もしない。
    close・統合・削除・期日変更はしない（313／人の担当）。

  python3 scripts/jarvis_todoist_312_collect.py --dry-run --hours 240
  python3 scripts/jarvis_todoist_312_collect.py --mode reflect --dry-run

環境変数: SLACK_BOT_TOKEN / TODOIST_API_TOKEN / JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY
任意: SLACK_OWNER_USER_ID（既定 U0C7X79N4P7）/ LOOPWARE_ACCESS_KEY（Slack リンクの署名）/
      JARVIS_LOOPWARE_URL / JARVIS_TODOIST_312_COLLECT_DISABLE=1（collect の投稿だけ止める）
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from jarvis_todoist_mark import mark_title, strip_mark  # noqa: E402

HERE = Path(__file__).resolve().parent
JST = timezone(timedelta(hours=9))
AGENT = "312"
PROMPT_VERSION = "rule-v1"  # 型で作った3案。AI に替えたら版を上げる
OWNER_DEFAULT = "U0C7X79N4P7"
CHANNELS = {
    "consult": "C0C7R0UF3MM",
    "ai-hub": "C0CA3M5SNNS",
    "report": "C0C866FNU3C",
}
WORKSPACE = "aiwsnetwork"
LOOPWARE_DEFAULT = "https://jarvis-loopware.vercel.app"
DONE_REACTIONS = {"white_check_mark", "heavy_check_mark", "ballot_box_with_check", "ok", "+1"}

# ---- 判定（ルール） ---------------------------------------------------------

REQUEST_RE = re.compile(
    r"(todoist|トゥドゥ|ToDo|起票|タスク(に|化)|追加して|入れて(おいて|ください)?|やっておいて|"
    r"お願い(します|したい)|依頼(します|したい)|宿題|あとで|後で|忘れずに|対応して|直して|調べて|確認して|して(ほしい|欲しい)|ようにして)",
    re.I,
)
QUESTION_RE = re.compile(r"(どうなって(ます|いる|る)|どうなった|進捗|まだ(です)?か|状況(は|を)教えて|できてる？|終わった？)")
WISH_RE = re.compile(r"(したい|やりたい|作りたい|進めたい|考えて(いる|る|ます)|いいなと思|検討したい|欲しい|ほしい)")
# AI が松野さんの名前で出した報告文の形（ヘッダ・記号始まり・長文）
AI_HEAD_RE = re.compile(r"^\s*(【|\[|\*|:[a-z0-9_+-]+:|•|>|```|\d+\.\s|訂正[:：]|補正|S\d+\S*\s)")
AI_MARK_RE = re.compile(r"(記録者[:：]|【Jarvis】|【FRIDAY】|【ホーク】|\[Jarvis|\[ホーク|Grok部長|次の担当|担当メモ|橋渡し|使用して送信されました|(部長|Banto|ホーク|Muse|Grok|Jarvis)(さん)?より|番頭さん)")
NOISE_RE = re.compile(r"^(ありがとう|了解|OK|おk|おけ|承知|はい|いいね)[!！。、\s]*$", re.I)


def is_human_like(msg: dict[str, Any], owner: str) -> bool:
    """松野さん本人が手で書いた短い発言だけ通す。"""
    if msg.get("user") != owner:
        return False
    if msg.get("bot_id") or msg.get("app_id") or msg.get("subtype"):
        return False
    text = (msg.get("text") or "").strip()
    if len(text) < 6 or len(text) > 500:
        return False
    if text.count("\n") > 6:
        return False
    if AI_HEAD_RE.search(text) or AI_MARK_RE.search(text):
        return False
    if NOISE_RE.match(text):
        return False
    return True


def classify(text: str) -> str | None:
    """起こりの種類: request（依頼）／question（どうなってますか）／wish（やりたい話）。"""
    t = text or ""
    if REQUEST_RE.search(t):
        return "request"
    if QUESTION_RE.search(t):
        return "question"
    if WISH_RE.search(t):
        return "wish"
    return None


def has_done_reaction(msg: dict[str, Any]) -> bool:
    return any((r.get("name") or "") in DONE_REACTIONS for r in (msg.get("reactions") or []))


KIND_JA = {"request": "依頼", "question": "問いかけ", "wish": "やりたい話"}

_LEAD_RE = re.compile(
    r"^(todoist(へ|に)?(追加し|入れ)て(おいて|ください)?[。、,\s]*|起票して[。、,\s]*|タスク(に|化)して[。、,\s]*)",
    re.I,
)


def derive_title(text: str, limit: int = 40) -> str:
    """発言からタスク名の案を作る（先頭の『todoistへ追加して。』等は外す）。"""
    t = re.sub(r"<[^>]+>", "", text or "")
    t = re.sub(r"\s+", " ", t).strip()
    t = _LEAD_RE.sub("", t).strip().lstrip("・•- ").strip()
    first = re.split(r"[。！!？?\n]", t, maxsplit=1)[0].strip() or t
    return first[:limit] + ("…" if len(first) > limit else "")


def parse_due(text: str, now: datetime) -> str | None:
    """『11/12』『11月12日』を YYYY-MM-DD に。無ければ None（AI が補わない）。"""
    m = re.search(r"(\d{1,2})\s*[/月]\s*(\d{1,2})\s*日?\s*(まで|迄|までに)", text or "")
    if not m:
        return None
    mo, d = int(m.group(1)), int(m.group(2))
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    y = now.year if mo >= now.month - 1 else now.year + 1
    try:
        return datetime(y, mo, d).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _bigrams(s: str) -> set[str]:
    s = re.sub(r"[\s\[\]【】（）()、。・／/:：]+", "", (s or "").lower())
    return {s[i : i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s}


def similarity(a: str, b: str) -> float:
    x, y = _bigrams(a), _bigrams(b)
    if not x or not y:
        return 0.0
    return len(x & y) / len(x | y)


def best_match(text: str, tasks: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, float]:
    """近い未完了タスク。社員番号（例 315）が両方にあれば強く寄せる。"""
    ids = set(re.findall(r"(?<!\d)([1-8]\d{2})(?!\d)", text or ""))
    best, score = None, 0.0
    for t in tasks:
        content = strip_mark(t.get("content") or "")
        s = similarity(text, content)
        if ids and any(f"[{i}]" in content for i in ids):
            s += 0.35
        if s > score:
            best, score = t, s
    return (best, score) if score >= 0.18 else (None, score)


# ---- 3案（型） --------------------------------------------------------------

LABELS = ("登録しない", "既存タスクへ追記", "別タスクを作る")


def build_proposals(
    *,
    text: str,
    kind: str,
    permalink: str,
    when: str,
    match: dict[str, Any] | None,
    now: datetime,
    where: str = "Slack で松野さんから",
    source_label: str = "Slack",
) -> list[dict[str, Any]]:
    """proposal.md の並び（1 登録しない → 2 既存へ追記 → 3 別タスク）で3案を作る。★は1つ。"""
    title = derive_title(text)
    due = parse_due(text, now)
    due_ja = due or "記載なし"
    origin = f"元の発言：{when} {permalink}"
    if match:
        m_title = match.get("content") or ""
        m_due = ((match.get("due") or {}) or {}).get("date") or "なし"
        keep = f"継続するタスク：{m_title}／期限 {m_due}"
    else:
        m_title, m_due, keep = "", "", "継続するタスク：なし（近い既存タスクは見つからない）"

    p1 = "\n".join(
        [
            f"登録対象：{title}",
            "扱い：新規作成も既存タスクへの追記もしません。",
            "理由：（決め手を押してください：もう済んだ／今やらない／タスクではない）",
            keep,
        ]
    )
    if match:
        p2 = "\n".join(
            [
                f"対象：{m_title}",
                f"期限：{m_due}（変えません）",
                f"追記文：{when} の {where}{KIND_JA[kind]}あり。「{title}」",
                origin,
                "扱い：既存タスク1件にコメントを足し、新しいタスクは作りません。",
            ]
        )
    else:
        p2 = "\n".join(
            [
                "対象：（近い既存タスクが見つかりません）",
                "扱い：追記先が無いので、この案は選ばないでください。",
                origin,
            ]
        )
    p3 = "\n".join(
        [
            f"タイトル：{title}",
            f"期限：{due_ja}",
            "プロジェクト：受信箱",
            f"説明：{source_label} の{KIND_JA[kind]}から起票。{origin}",
            ("注意：既存の「" + m_title + "」と同じ用件なら二重管理になります。") if match else "完了条件：（直して書く）",
        ]
    )
    star = 2 if (match and kind == "question") else 3 if kind == "request" else 1
    if match and kind == "request" and similarity(text, m_title) >= 0.35:
        star = 2
    return [
        {"proposal_index": i + 1, "label": LABELS[i], "body": b, "is_starred": star == i + 1}
        for i, b in enumerate((p1, p2, p3))
    ]


def topic_text_for(*, text: str, when: str, channel_name: str, kind: str, match: dict[str, Any] | None) -> str:
    head = f"[Slack #{channel_name} {when}・{KIND_JA[kind]}] {text.strip()}"
    if not match:
        return head + "\n既存：近いタスクなし。"
    due = ((match.get("due") or {}) or {}).get("date") or "期限なし"
    return head + f"\n既存：{match.get('content')}／{due}／未完了。"


def parse_body(body: str) -> dict[str, str]:
    """『キー：値』の行を辞書に（reflect 用。人が直した本文も読む）。"""
    out: dict[str, str] = {}
    for line in (body or "").splitlines():
        m = re.match(r"^([^：]{1,8})：(.*)$", line.strip())
        if m:
            out.setdefault(m.group(1), m.group(2).strip())
    return out


def link_token(key: str, now: datetime, days: int = 7) -> str:
    """apps/loopware/lib/access.ts の linkToken と同じ作り方。"""
    exp = int(now.timestamp()) + days * 86400
    sig = hmac.new(key.encode(), f"loopware-link-v1:{exp}".encode(), hashlib.sha256).digest()
    return f"{exp}." + base64.urlsafe_b64encode(sig).decode().rstrip("=")


def nody_url(path: str, now: datetime) -> str:
    base = (os.environ.get("JARVIS_LOOPWARE_URL") or LOOPWARE_DEFAULT).rstrip("/")
    key = (os.environ.get("LOOPWARE_ACCESS_KEY") or "").strip()
    url = f"{base}{path}"
    if key:
        url += ("&" if "?" in url else "?") + "t=" + link_token(key, now)
    return url


# ---- 外部 API ---------------------------------------------------------------


def _req(url: str, *, headers: dict[str, str], method: str = "GET", body: Any = None, timeout: int = 25) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode()
    return json.loads(raw) if raw.strip() else None


def slack(method: str, params: dict[str, Any]) -> dict[str, Any]:
    tok = os.environ["SLACK_BOT_TOKEN"]
    url = f"https://slack.com/api/{method}?" + urllib.parse.urlencode(params)
    return _req(url, headers={"Authorization": f"Bearer {tok}"}) or {}


def todoist(path: str, *, method: str = "GET", body: Any = None) -> Any:
    tok = os.environ["TODOIST_API_TOKEN"]
    return _req(
        f"https://api.todoist.com/api/v1/{path}",
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
        method=method,
        body=body,
    )


def sb(path: str, *, params: dict[str, str] | None = None, method: str = "GET", body: Any = None, prefer: str = "") -> Any:
    url = os.environ["JARVIS_SUPABASE_URL"].rstrip("/")
    key = os.environ["JARVIS_SUPABASE_SERVICE_ROLE_KEY"]
    q = ("?" + urllib.parse.urlencode(params, safe=",.:()*")) if params else ""
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return _req(f"{url}/rest/v1/{path}{q}", headers=h, method=method, body=body)


def permalink(channel: str, ts: str) -> str:
    return f"https://{WORKSPACE}.slack.com/archives/{channel}/p{ts.replace('.', '')}"


def slack_messages(channel: str, oldest: float) -> list[dict[str, Any]]:
    """チャンネルの親発言と、期間内に動いたスレッドの返信。"""
    out: list[dict[str, Any]] = []
    cursor = ""
    parents: list[dict[str, Any]] = []
    for _ in range(10):
        p: dict[str, Any] = {"channel": channel, "oldest": f"{oldest:.6f}", "limit": 200}
        if cursor:
            p["cursor"] = cursor
        res = slack("conversations.history", p)
        if not res.get("ok"):
            raise RuntimeError(f"{channel}: {res.get('error')}")
        parents.extend(res.get("messages") or [])
        cursor = ((res.get("response_metadata") or {}).get("next_cursor")) or ""
        if not cursor:
            break
    out.extend(parents)
    for m in parents:
        if int(m.get("reply_count") or 0) > 0:
            r = slack("conversations.replies", {"channel": channel, "ts": m["ts"], "oldest": f"{oldest:.6f}", "limit": 200})
            if r.get("ok"):
                out.extend(x for x in (r.get("messages") or [])[1:] if float(x.get("ts", 0)) >= oldest)
            time.sleep(0.4)
    return out


def active_tasks() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cursor = None
    for _ in range(10):
        path = "tasks?limit=200" + (f"&cursor={urllib.parse.quote(cursor)}" if cursor else "")
        data = todoist(path) or {}
        rows.extend(data.get("results") or [])
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return rows


def post_consult(text: str, dry: bool) -> None:
    if dry:
        print(f"--- dry-run（#consult）---\n{text}\n---")
        return
    r = subprocess.run(
        [sys.executable, str(HERE / "jarvis_slack_webhook_post.py"), "--channel", "consult", "--text", text, "--no-fb-footer"],
        capture_output=True,
        text=True,
    )
    print(r.stdout.strip() or r.stderr.strip())


# ---- 台帳（comm_items）からの入口 ---------------------------------------------
# 拾う条件（台帳スレッドと合意 2026-11-10）:
#   受信（inbound）・除外以外・14日以内・work_status が new／needs_reply
#   needs_reply は、つながった triage が pending で生きているものだけ（閉じ残しは入れない）
#   自分の送信（category=self）は「〜します」の約束っぽい文だけ
# お試し: 1回の上限は --comm-max（既定 0＝止める）。曜日は COMM_WEEKDAY（水）だけ。

COMM_DAYS = 14
COMM_WEEKDAY = 2  # 水曜（月=0）。お試しは週1回
COMM_COLS = "id,channel,account,category,direction,party_id,occurred_at,subject,summary,body_text,work_status,context_header,source_ref"
PROMISE_RE = re.compile(
    r"(お送りします|送ります|送付します|ご連絡(します|いたします)|確認(します|いたします)|対応(します|いたします)|"
    r"折り返し|手配(します|いたします)|準備(します|いたします)|提出(します|いたします)|ご返信(します|いたします)|"
    r"伺います|お持ちします|調整(します|いたします))"
)
ASK_RE = re.compile(r"(ください|いただけ|頂け|お願い|でしょうか|(です|でした|ます)か[、。？?\s]|ご確認|ご検討|ご連絡|ご返信|いかが|教えて)")
OWN_FIRST_RE = re.compile(r"^\s*\d{4}/\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2}\s+松野")  # LINE 等のブロックで先頭の発言者が自分
THANKS_RE = re.compile(r"^(いつも)?(ありがとう|お疲れ|おつかれ|了解|承知|よろしくお願い)\S{0,20}$")
AUTO_REPLY_RE = re.compile(r"(自動返信|自動送信|auto-?reply|out of office|不在通知|受付完了のお知らせ)", re.I)
_QUOTE_CUT_RE = re.compile(r"^(>|.*(wrote:|のメッセージ:|からのメッセージ|-----Original Message-----|─{6,}))")
ACCOUNT_EMAIL = {"admin": "admin@livingsupport-matsu.co.jp", "estate": "matsuno.estate@gmail.com"}
CAT_JA = {"partner": "パートナー", "inquiry": "メール", "property": "物件", "self": "自分の送信", "agent": "共有"}
CH_JA = {"gmail": "メール", "chatwork": "Chatwork", "line": "LINE", "line_oa": "公式LINE", "imessage": "iMessage", "slack": "Slack", "other": "その他"}


def own_text(body: str, limit: int = 1500) -> str:
    """送信メール本文から引用（> や「〜wrote:」以降）を落とし、自分が書いた部分だけにする。"""
    out: list[str] = []
    for line in (body or "").splitlines():
        if _QUOTE_CUT_RE.match(line.strip()):
            break
        out.append(line)
    return "\n".join(out)[:limit]


def comm_label(it: dict[str, Any]) -> str:
    cat = CAT_JA.get(str(it.get("category") or ""), "台帳")
    ch = CH_JA.get(str(it.get("channel") or ""), str(it.get("channel") or ""))
    return cat if cat == ch else f"{cat}・{ch}"


def comm_origin(it: dict[str, Any]) -> str:
    """元の1件へ戻る道（Gmail は URL、やり取り.md はパスと見出し）。"""
    ref = it.get("source_ref") or {}
    if isinstance(ref, str):
        try:
            ref = json.loads(ref)
        except ValueError:
            ref = {}
    th = ref.get("gmail_thread_id")
    if th:
        email = ACCOUNT_EMAIL.get(str(ref.get("account") or it.get("account") or "admin"), ACCOUNT_EMAIL["admin"])
        return f"https://mail.google.com/mail/u/{email}/#all/{th}"
    if ref.get("path"):
        return f"{ref['path']}（{str(ref.get('heading') or '')[:80]}）"
    return f"comm_items:{it.get('id')}"


def _plain(t: str) -> str:
    """md 由来の <details><summary>本文</summary> や先頭の「日時 名前」を落として1行に。"""
    t = re.sub(r"<[^>]+>", " ", t or "")
    t = re.sub(r"^\s*本文\s*", "", t)
    t = re.sub(r"^\s*\d{4}/\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2}\s+\S+\s+", "", t.strip())
    return re.sub(r"\s+", " ", t).strip()


def comm_text(it: dict[str, Any]) -> str:
    subject = re.sub(r"\s+", " ", str(it.get("subject") or "")).strip()
    summary = _plain(str(it.get("summary") or "")) or _plain(str(it.get("body_text") or ""))[:200]
    if subject in ("(件名なし)", "（件名なし）"):
        subject = ""
    if it.get("category") == "self":
        body = own_text(str(it.get("body_text") or ""))
        m = PROMISE_RE.search(body)
        line = ""
        if m:
            start = body.rfind("\n", 0, m.start()) + 1
            end = body.find("\n", m.end())
            line = body[start : end if end >= 0 else None].strip()
        return f"{subject}｜{line}" if line else subject
    if summary and summary != subject:
        return f"{subject}｜{summary}" if subject else summary
    return subject or summary


def pick_comm(rows: list[dict[str, Any]], pending_ids: set[str], known: set[str]) -> list[dict[str, Any]]:
    """台帳の行から、お題にするものを選ぶ（純関数・テスト用）。"""
    out: list[dict[str, Any]] = []
    for it in rows:
        ref = f"comm_items:{it['id']}"
        if ref in known:
            continue
        if AUTO_REPLY_RE.search(str(it.get("subject") or "")):
            continue  # 自動返信はやることにならない
        if it.get("category") != "self":
            body_plain = re.sub(r"<[^>]+>|本文", " ", str(it.get("body_text") or "")).strip()
            if OWN_FIRST_RE.match(body_plain):
                continue  # 受信扱いでも中身は自分の発言（LINE の既知の限界）
            if THANKS_RE.match(comm_text(it).strip()):
                continue  # お礼・あいさつだけ
            if it.get("channel") != "gmail" and not (classify(body_plain[:800]) or classify(comm_text(it)) or ASK_RE.search(body_plain[:800])):
                continue  # チャットは依頼・問いかけ・お願いの形があるものだけ（メールは仕分け済み）
        if it.get("category") == "self":
            if it.get("direction") != "outbound" or not PROMISE_RE.search(own_text(str(it.get("body_text") or ""))):
                continue
        else:
            if it.get("direction") != "inbound":
                continue
            ws = it.get("work_status")
            if ws == "needs_reply" and str(it["id"]) not in pending_ids:
                continue  # 閉じ残し（triage は済み）
            if ws not in ("new", "needs_reply"):
                continue
        out.append(it)
    out.sort(key=lambda x: str(x.get("occurred_at") or ""), reverse=True)
    return out


def comm_candidates(now: datetime, known: set[str], limit: int) -> list[dict[str, Any]]:
    since = (now - timedelta(days=COMM_DAYS)).isoformat()
    inbound = sb(
        "comm_items",
        params={
            "select": COMM_COLS,
            "direction": "eq.inbound",
            "ingest_status": "neq.excluded",
            "work_status": "in.(new,needs_reply)",
            "occurred_at": f"gte.{since}",
            "order": "occurred_at.desc",
            "limit": "200",
        },
    ) or []
    own = sb(
        "comm_items",
        params={
            "select": COMM_COLS,
            "direction": "eq.outbound",
            "category": "eq.self",
            "ingest_status": "neq.excluded",
            "occurred_at": f"gte.{since}",
            "order": "occurred_at.desc",
            "limit": "200",
        },
    ) or []
    nr = [str(r["id"]) for r in inbound if r.get("work_status") == "needs_reply"]
    pending: set[str] = set()
    for i in range(0, len(nr), 50):
        chunk = ",".join(nr[i : i + 50])
        for t in sb("triage_items", params={"select": "comm_item_id,status", "comm_item_id": f"in.({chunk})", "status": "eq.pending"}) or []:
            pending.add(str(t["comm_item_id"]))
    return pick_comm(inbound + own, pending, known)[: max(0, limit)]


def comm_topic(it: dict[str, Any], tasks: list[dict[str, Any]], now: datetime) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    text = comm_text(it)
    occurred = datetime.fromisoformat(str(it["occurred_at"]).replace("Z", "+00:00")).astimezone(JST)
    when = occurred.strftime("%-m/%-d %H:%M")
    label = comm_label(it)
    own = it.get("category") == "self"
    kind = "request" if own else (classify(text) or "request")
    origin = comm_origin(it)
    match, score = best_match(text, tasks)
    who = str(it.get("context_header") or "").split("｜")[0]
    head = f"[{label} {when}・{'自分の約束' if own else KIND_JA[kind]}] {text.strip()}"
    if who and not own:
        head += f"\n相手：{who}"
    topic = {
        "agent_id": AGENT,
        "source_kind": "comm",
        "source_ref": f"comm_items:{it['id']}",
        "comm_item_id": it["id"],
        "topic_text": head + (f"\n既存：{match.get('content')}／{((match.get('due') or {}) or {}).get('date') or '期限なし'}／未完了。" if match else "\n既存：近いタスクなし。"),
        "todoist_task_ids": [str(match["id"])] if match else [],
        "todoist_snapshot": (
            {"content": match.get("content"), "due": (match.get("due") or {}).get("date"), "project_id": match.get("project_id"), "score": round(score, 2)}
            if match
            else {}
        ),
        "status": "open",
    }
    props = build_proposals(
        text=text,
        kind=kind,
        permalink=origin,
        when=when,
        match=match,
        now=now,
        where=(f"{label}で自分から約束" if own else f"{label}で{who or '相手'}から"),
        source_label=label,
    )
    if own:
        props = [{**p, "body": p["body"].replace("約束依頼あり", "約束あり")} for p in props]
    return topic, props, {"kind": kind, "title": derive_title(text), "link": origin, "label": label, "when": when}


# ---- collect ----------------------------------------------------------------


def collect(*, hours: int, max_items: int, dry: bool, now: datetime, comm_max: int = 0, comm_any_day: bool = False) -> int:
    owner = os.environ.get("SLACK_OWNER_USER_ID") or OWNER_DEFAULT
    oldest = (now - timedelta(hours=hours)).timestamp()
    tasks = active_tasks()
    task_text = "\n".join((t.get("description") or "") for t in tasks)

    known: set[str] = set()
    for row in sb("task_loop_topics", params={"select": "source_ref", "agent_id": f"eq.{AGENT}", "source_ref": "not.is.null"}) or []:
        known.add(row["source_ref"])

    found: list[dict[str, Any]] = []
    errors: list[str] = []
    for name, cid in CHANNELS.items():
        try:
            msgs = slack_messages(cid, oldest)
        except Exception as e:  # noqa: BLE001 — 1チャンネルの失敗で全体を止めない
            errors.append(f"#{name}: {e}")
            continue
        for m in msgs:
            if not is_human_like(m, owner) or has_done_reaction(m):
                continue
            text = (m.get("text") or "").strip()
            kind = classify(text)
            if not kind:
                continue
            link = permalink(cid, m["ts"])
            if link in known or link in task_text:
                continue
            found.append({"channel": name, "ts": m["ts"], "text": text, "kind": kind, "link": link})

    found.sort(key=lambda x: float(x["ts"]))
    found = found[-max_items:]
    made: list[dict[str, Any]] = []
    for f in found:
        when = datetime.fromtimestamp(float(f["ts"]), JST).strftime("%-m/%-d %H:%M")
        match, score = best_match(f["text"], tasks)
        topic = {
            "agent_id": AGENT,
            "source_kind": "slack",
            "source_ref": f["link"],
            "topic_text": topic_text_for(text=f["text"], when=when, channel_name=f["channel"], kind=f["kind"], match=match),
            "todoist_task_ids": [str(match["id"])] if match else [],
            "todoist_snapshot": (
                {"content": match.get("content"), "due": (match.get("due") or {}).get("date"), "project_id": match.get("project_id"), "score": round(score, 2)}
                if match
                else {}
            ),
            "status": "open",
        }
        props = build_proposals(text=f["text"], kind=f["kind"], permalink=f["link"], when=when, match=match, now=now)
        if dry:
            print(json.dumps({"topic": topic, "proposals": props}, ensure_ascii=False, indent=1))
            made.append({**f, "id": "dry", "title": derive_title(f["text"])})
            continue
        rows = sb("task_loop_topics", method="POST", body=topic, prefer="return=representation")
        tid = rows[0]["id"]
        sb(
            "task_loop_proposals",
            method="POST",
            body=[{**p, "topic_id": tid, "prompt_version": PROMPT_VERSION} for p in props],
            prefer="return=minimal",
        )
        made.append({**f, "id": tid, "title": derive_title(f["text"])})

    # 台帳（メール・パートナー・自分の送信）。お試し: 上限 comm_max・水曜だけ。失敗しても Slack 分は止めない
    comm_made: list[dict[str, Any]] = []
    comm_on = comm_max > 0 and (comm_any_day or now.weekday() == COMM_WEEKDAY)
    if comm_on:
        try:
            for it in comm_candidates(now, known, comm_max):
                topic, props, info = comm_topic(it, tasks, now)
                if dry:
                    print(json.dumps({"topic": topic, "proposals": props}, ensure_ascii=False, indent=1))
                    comm_made.append({**info, "id": "dry"})
                    continue
                rows = sb("task_loop_topics", method="POST", body=topic, prefer="return=representation")
                tid = rows[0]["id"]
                sb(
                    "task_loop_proposals",
                    method="POST",
                    body=[{**p, "topic_id": tid, "prompt_version": PROMPT_VERSION} for p in props],
                    prefer="return=minimal",
                )
                comm_made.append({**info, "id": tid})
        except Exception as e:  # noqa: BLE001
            errors.append(f"comm: {e}")

    print(f"312 collect: 候補 {len(made)} 件（{hours}時間・チャンネル {len(CHANNELS)}）＋台帳 {len(comm_made)} 件（{'上限 ' + str(comm_max) if comm_on else '止め'}）")
    for e in errors:
        print(f"::warning::{e}")

    if not made and not comm_made:
        return 0
    if (os.environ.get("JARVIS_TODOIST_312_COLLECT_DISABLE") or "").strip() == "1":
        print("JARVIS_TODOIST_312_COLLECT_DISABLE=1 のため #consult には出さない")
        return 0
    lines = consult_lines(made, comm_made)
    first = (made or comm_made)[0]["id"]
    lines += [
        "",
        f"→ <{nody_url('/312' + ('' if first == 'dry' else f'?topic={first}'), now)}|Nody で扱いを決める>（登録しない／既存へ追記／別タスク）",
        "",
        "次: 松野さんが Nody で1件ずつ選ぶ（選んだものは30分以内に Todoist へ反映）",
        "担当メモ: 312（拾い方はルールのみ・AI 不使用）",
        "橋渡し: 反映は reflect（GHA 30分ごと）。close は 313",
    ]
    post_consult("\n".join(lines), dry)
    return 0


def consult_lines(made: list[dict[str, Any]], comm_made: list[dict[str, Any]]) -> list[str]:
    """#consult の見出しと一覧。台帳分が無いときは今までと同じ文面。"""
    total = len(made) + len(comm_made)
    head = f"【相談】312 Todoist起票整理｜起票候補 {total}件"
    if comm_made:
        head += f"（Slack {len(made)}件・メール等 {len(comm_made)}件）"
    lines = [head, ""]
    i = 0
    for f in made:
        i += 1
        lines.append(f"{i}. [{KIND_JA[f['kind']]}] {f['title']}  <{f['link']}|元の発言>")
    for f in comm_made:
        i += 1
        link = f["link"]
        tail = f"  <{link}|元のメール>" if link.startswith("http") else "  （やり取り.md）"
        lines.append(f"{i}. [{f['label']}] {f['title']}{tail}")
    return lines


# ---- reflect ----------------------------------------------------------------


def mark_comm_task(item_id: str, task_id: str) -> None:
    """台帳の行に Todoist をひもづけ、対応状況を waiting に（new／needs_reply のときだけ）。失敗しても反映は止めない。"""
    try:
        sb(
            "comm_links",
            params={"on_conflict": "item_id,target_type,target_id"},
            method="POST",
            body={"item_id": item_id, "target_type": "todoist_task", "target_id": task_id, "role": "312"},
            prefer="resolution=ignore-duplicates,return=minimal",
        )
        sb(
            "comm_items",
            params={"id": f"eq.{item_id}", "work_status": "in.(new,needs_reply)"},
            method="PATCH",
            body={"work_status": "waiting"},
            prefer="return=minimal",
        )
    except Exception as e:  # noqa: BLE001
        print(f"::warning::comm link {item_id}: {e}")


def reflect(*, dry: bool) -> int:
    decs = sb(
        "task_loop_decisions",
        params={
            "select": "id,topic_id,choice,chosen_index,final_text,reflected_todoist_id",
            "reflected_todoist_id": "is.null",
            "choice": "in.(use,edit_use)",
            "order": "updated_at.asc",
            "limit": "20",
        },
    ) or []
    if not decs:
        print("312 reflect: 反映待ちなし")
        return 0
    ids = ",".join(d["topic_id"] for d in decs)
    topics = {
        t["id"]: t
        for t in sb(
            "task_loop_topics",
            params={"select": "id,source_kind,source_ref,comm_item_id,todoist_task_ids,topic_text", "id": f"in.({ids})", "source_kind": "in.(slack,comm)"},
        )
        or []
    }
    props: dict[tuple[str, int], dict[str, Any]] = {}
    for p in sb("task_loop_proposals", params={"select": "topic_id,proposal_index,label,body", "topic_id": f"in.({ids})"}) or []:
        props[(p["topic_id"], int(p["proposal_index"]))] = p

    def mark(dec_id: str, value: str) -> None:
        # 反映しない判断にも印（"-"）を付け、次の回に読み直さない。決め直したら Nody 側で空に戻る
        if not dry:
            sb("task_loop_decisions", params={"id": f"eq.{dec_id}"}, method="PATCH", body={"reflected_todoist_id": value}, prefer="return=minimal")

    n = 0
    for d in decs:
        t = topics.get(d["topic_id"])
        p = props.get((d["topic_id"], int(d.get("chosen_index") or 0)))
        if not t or not p:
            mark(d["id"], "-")  # 見本・手入力のお題は反映しない
            continue
        body = d.get("final_text") or p["body"]
        f = parse_body(body)
        label = p["label"]
        src = t.get("source_ref") or ""
        if t.get("source_kind") == "comm" and t.get("comm_item_id"):
            try:
                items = sb("comm_items", params={"select": "id,account,source_ref", "id": f"eq.{t['comm_item_id']}"}) or []
                if items:
                    src = comm_origin(items[0])
            except Exception as e:  # noqa: BLE001
                print(f"::warning::comm origin {t['comm_item_id']}: {e}")
        if label == "既存タスクへ追記":
            target = (t.get("todoist_task_ids") or [None])[0]
            if not target:
                print(f"skip {d['id']}: 追記先なし")
                mark(d["id"], "-")
                continue
            comment = f"【Jarvis】\nサマリ: {f.get('追記文') or body[:200]}\nアウトプット:\n- [元の発言]({src})"
            if dry:
                print(f"dry: comment → {target}\n{comment}")
                continue
            todoist("comments", method="POST", body={"task_id": target, "content": comment})
            done_id = str(target)
        elif label == "別タスクを作る":
            title = f.get("タイトル") or derive_title(t.get("topic_text") or "")
            task: dict[str, Any] = {
                "content": mark_title(f"[{AGENT}] {title}", requested=True),
                "description": f"{f.get('説明') or ''}\n完了条件: {f.get('完了条件') or '記載なし'}\n出典: {src}".strip(),
                "labels": ["312"],
            }
            due = f.get("期限") or ""
            if re.match(r"^\d{4}-\d{2}-\d{2}$", due):
                task["due_date"] = due
            elif due and due != "記載なし":
                task["due_string"] = due
                task["due_lang"] = "ja"
            if dry:
                print("dry: create", json.dumps(task, ensure_ascii=False))
                continue
            created = todoist("tasks", method="POST", body=task) or {}
            done_id = str(created.get("id") or "")
            if not done_id:
                print(f"::warning::create failed {d['id']}: {json.dumps(created)[:200]}")
                continue
            todoist(
                "comments",
                method="POST",
                body={"task_id": done_id, "content": f"【Jarvis】\nサマリ: Nody 312 で「別タスクを作る」を選択。\nアウトプット:\n- [元の発言]({src})"},
            )
        else:
            mark(d["id"], "-")  # 登録しない
            continue
        mark(d["id"], done_id)
        if t.get("source_kind") == "comm" and t.get("comm_item_id") and not dry:
            mark_comm_task(str(t["comm_item_id"]), done_id)
        n += 1
        print(f"反映: {label} → {done_id}")
    print(f"312 reflect: {n} 件反映")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", choices=["collect", "reflect"], default="collect")
    ap.add_argument("--hours", type=int, default=96, help="何時間さかのぼるか（月→水 48h、金→月 72h ＋余裕）")
    ap.add_argument("--max", type=int, default=5, help="1回のお題の上限（ノイズ抑制）")
    ap.add_argument("--dry-run", action="store_true", help="DB に書かず Slack に出さない")
    ap.add_argument("--comm-max", type=int, default=0, help="台帳（comm_items）から拾う上限。0 で止める（お試しは 5）")
    ap.add_argument("--comm-any-day", action="store_true", help="台帳分を水曜以外でも拾う（手動の確認用）")
    a = ap.parse_args(argv)
    need = ["JARVIS_SUPABASE_URL", "JARVIS_SUPABASE_SERVICE_ROLE_KEY", "TODOIST_API_TOKEN"]
    if a.mode == "collect":
        need.append("SLACK_BOT_TOKEN")
    miss = [k for k in need if not os.environ.get(k)]
    if miss:
        print("未設定: " + ", ".join(miss), file=sys.stderr)
        return 2
    now = datetime.now(JST)
    try:
        if a.mode == "reflect":
            return reflect(dry=a.dry_run)
        return collect(hours=a.hours, max_items=a.max, dry=a.dry_run, now=now, comm_max=a.comm_max, comm_any_day=a.comm_any_day)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
