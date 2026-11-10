#!/usr/bin/env python3
"""(4) 質問ランキング＋講座テーマ案の週次の回を作る（2026-11-11）。

1. DB 関数 qa_theme_source_digest(120) で、質問ログ・コミュニティ・オプチャ・既存講座を DB の中で小さく集計して受け取る
   （全件は取らない。無料プランの通信量対策で 1 回 百KB前後）。
2. 直近の回の「採用／直して採用／不採用＋理由」を読む（ループウェアの判断ログ）。
3. Gemini に「似た質問のまとまりランキング」と「講座・グルコンのテーマ案5つ」を JSON で作らせる。
4. qa_theme_rounds に1行入れる。運営分析（スイッチ ranking_themes）で見る。

必要な環境変数: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, GEMINI_API_KEY（任意 GEMINI_MODEL, DRY_RUN=1）
投稿者の名前・メールは集計に含まれない。結果の本文はログに出さない（件数だけ）。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")
DAYS = int(os.environ.get("THEME_DAYS", "120"))
JST = dt.timezone(dt.timedelta(hours=9))


def rest(path: str, method: str = "GET", body: object | None = None, prefer: str = "") -> object:
    headers = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
    if prefer:
        headers["Prefer"] = prefer
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(f"{URL}/rest/v1/{path}", data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


STR = {"type": "STRING"}
INT = {"type": "INTEGER"}
SCHEMA = {"type": "OBJECT", "required": ["ranking", "themes"], "properties": {
    "ranking": {"type": "ARRAY", "items": {"type": "OBJECT", "required": ["topic", "count"], "properties": {
        "topic": STR, "count": INT, "chatbot": INT, "forum": INT, "openchat": INT,
        "examples": {"type": "ARRAY", "items": STR}}}},
    "themes": {"type": "ARRAY", "items": {"type": "OBJECT", "required": ["id", "title", "why", "evidence"], "properties": {
        "id": STR, "title": STR, "why": STR, "evidence": STR, "format": STR, "target": STR}}}}}


def gemini(prompt: str, tries: int = 3) -> dict:
    for i in range(tries):
        try:
            return _gemini_once(prompt)
        except (ValueError, KeyError, IndexError) as e:
            print(f"Gemini の応答を読めませんでした（{i + 1}回目）: {type(e).__name__}", file=sys.stderr)
    raise SystemExit("Gemini の応答を3回とも読めませんでした")


def _gemini_once(prompt: str) -> dict:
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        # Gemini 3 は温度を下げると同じ出力を繰り返しやすい（数字が延々と続く等）ので既定の 1.0 のまま。
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": SCHEMA,
                             "maxOutputTokens": 16384},
    }
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
        data=json.dumps(body, ensure_ascii=False).encode(), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_KEY})
    with urllib.request.urlopen(req, timeout=180) as r:
        res = json.loads(r.read())
    text = "".join(p.get("text", "") for p in res["candidates"][0]["content"]["parts"])
    return json.loads(text)


def past_decisions() -> list[dict]:
    rounds = rest("qa_theme_rounds?select=id,themes&order=created_at.desc&limit=4") or []
    if not rounds:
        return []
    ids = ",".join(r["id"] for r in rounds)
    decs = rest(f"qa_theme_decisions?select=round_id,theme_id,choice,revised_title,reason&round_id=in.({ids})") or []
    by = {(d["round_id"], d["theme_id"]): d for d in decs}
    out = []
    for r in rounds:
        for t in r.get("themes") or []:
            d = by.get((r["id"], t.get("id")))
            out.append({"round": r["id"], "title": t.get("title"),
                        "choice": d["choice"] if d else "undecided",
                        "revised_title": (d or {}).get("revised_title", ""), "reason": (d or {}).get("reason", "")})
    return out


PROMPT = """あなたは不動産投資家コミュニティ「神・大家さん倶楽部」の講座企画を手伝う担当です。
会員が実際に聞いていることを集計した材料（JSON）と、運営が過去のテーマ案に付けた判断を渡します。

やること:
1. ranking: 材料の質問（chatbot.top / forum.questions / forum.topics / openchat.questions / openchat.threads）を、
   意味の近いもの同士でまとめ、多い順に最大20個。count はまとまりの件数の目安（chatbot.top の n も足す。0〜20000 の整数）。
   chatbot / forum / openchat はそれぞれの内訳の目安。examples は実際の質問を短く言い直したもの最大3つ
   （個人名・会社名・物件の住所・電話番号などは入れない）。topic は会員の言葉で20字以内。
2. themes: 講座またはグループコンサル（グルコン）のテーマ案をちょうど5つ。id は t1〜t5。
   - 需要（ranking の多さ）に対して既存講座（courses.titles）が少ない「すき間」を優先する。
   - 既存講座が多いテーマは、新しい切り口（最新動向・事例・実務の手順）がある場合だけにする。
   - 過去の判断（decisions）を必ず反映する。不採用の理由に当てはまる案は出さない。直して採用された題名の傾向
     （具体さ・言い回し）に合わせる。採用済みと同じ案は繰り返さない。
   - title は30字以内、why は「なぜ今これか」を2文以内、evidence は根拠の数字（何件・どこで）を1文、
     format は形式（例: 60分講座、グルコン、連載3回）、target は対象（例: 1棟目購入前、築古戸建の保有者）。

出力は次の形の JSON だけ:
{"ranking":[{"topic":"","count":0,"chatbot":0,"forum":0,"openchat":0,"examples":[""]}],
 "themes":[{"id":"t1","title":"","why":"","evidence":"","format":"","target":""}]}

decisions:
%s

材料:
%s
"""


def clean(res: dict) -> tuple[list, list]:
    def s(v, n):
        return str(v or "").strip()[:n]

    def n(v):
        try:
            return max(0, int(round(float(v))))
        except (TypeError, ValueError):
            return 0

    ranking = [{"topic": s(x.get("topic"), 80), "count": n(x.get("count")), "chatbot": n(x.get("chatbot")),
                "forum": n(x.get("forum")), "openchat": n(x.get("openchat")),
                "examples": [s(e, 140) for e in (x.get("examples") or [])[:3]]}
               for x in (res.get("ranking") or [])[:20] if isinstance(x, dict) and x.get("topic")]
    themes = [{"id": f"t{i + 1}", "title": s(t.get("title"), 120), "why": s(t.get("why"), 400),
               "evidence": s(t.get("evidence"), 400), "format": s(t.get("format"), 120), "target": s(t.get("target"), 120)}
              for i, t in enumerate([t for t in (res.get("themes") or []) if isinstance(t, dict) and t.get("title")][:5])]
    if len(themes) < 3:
        raise SystemExit("テーマ案が足りません（Gemini の応答が想定と違う）")
    return ranking, themes


def main() -> None:
    if not (URL and KEY and GEMINI_KEY):
        raise SystemExit("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / GEMINI_API_KEY が必要です")
    digest = rest("rpc/qa_theme_source_digest", "POST", {"p_days": DAYS})
    size = len(json.dumps(digest, ensure_ascii=False).encode())
    decisions = past_decisions()
    res = gemini(PROMPT % (json.dumps(decisions, ensure_ascii=False), json.dumps(digest, ensure_ascii=False)))
    ranking, themes = clean(res)
    now = dt.datetime.now(JST)
    rid = "r" + now.strftime("%Y%m%d")
    if rest(f"qa_theme_rounds?select=id&id=eq.{rid}"):
        rid += now.strftime("-%H%M")
    row = {"id": rid, "period_days": DAYS, "model": MODEL, "ranking": ranking, "themes": themes,
           "stats": {"chatbot": digest["chatbot"]["events"], "forum": digest["forum"]["posts"],
                     "openchat": digest["openchat"]["posts"], "courses": digest["courses"]["total"]}}
    print(f"round={rid} digest_kb={size // 1024} ranking={len(ranking)} themes={len(themes)} past_decisions={len(decisions)}")
    if os.environ.get("DRY_RUN") == "1":
        return
    rest("qa_theme_rounds", "POST", row, prefer="return=minimal")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300] if "googleapis" in (e.url or "") else ""
        print(f"HTTP {e.code} {e.url.split('?')[0]} {detail}", file=sys.stderr)
        sys.exit(1)
