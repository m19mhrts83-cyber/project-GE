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
# 数は Gemini に数えさせない（11/11 松野さん「Q&Aに問い合わせた数を出したい」）。
# Gemini は「どの質問が同じ趣旨か」のまとめ方だけを返し、回数・人数はこのスクリプトが質問ログから正確に数える。
GROUP_SCHEMA = {"type": "OBJECT", "required": ["groups"], "properties": {
    "groups": {"type": "ARRAY", "items": {"type": "OBJECT", "required": ["topic", "ids"], "properties": {
        "topic": STR, "ids": {"type": "ARRAY", "items": STR}}}}}}
THEME_SCHEMA = {"type": "OBJECT", "required": ["themes"], "properties": {
    "themes": {"type": "ARRAY", "items": {"type": "OBJECT", "required": ["id", "title", "why", "evidence"], "properties": {
        "id": STR, "title": STR, "why": STR, "evidence": STR, "format": STR, "target": STR}}}}}


def gemini(prompt: str, schema: dict, tries: int = 3) -> dict:
    for i in range(tries):
        try:
            return _gemini_once(prompt, schema)
        except (ValueError, KeyError, IndexError) as e:
            print(f"Gemini の応答を読めませんでした（{i + 1}回目）: {type(e).__name__} {str(e)[:120]}", file=sys.stderr)
    raise SystemExit("Gemini の応答を3回とも読めませんでした")


def _gemini_once(prompt: str, schema: dict) -> dict:
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        # Gemini 3 は温度を下げると同じ出力を繰り返しやすい（数字が延々と続く等）ので既定の 1.0 のまま。
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema,
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


GROUP_PROMPT = """神大家Q&Aチャット（不動産投資家コミュニティの会員がAIに質問するチャット）に届いた質問の一覧です。
同じ趣旨の質問（言い方が違っても聞きたいことが同じもの）を1つのまとまりにしてください。
- 各質問は id で指定し、1つの質問は1つのまとまりにだけ入れる。どこにも当てはまらない質問は、その1件だけのまとまりにする。
- topic は会員が聞いていることを会員の言葉で20字以内（例: 「築古戸建の修繕費の目安」）。
- 「テスト」「こんにちは」のように中身のない質問は topic を「(質問以外)」にする。
- 数を数える必要はありません。

出力は次の形の JSON だけ: {"groups":[{"topic":"","ids":["q1","q2"]}]}

質問一覧（id, 質問, この文面で聞かれた回数）:
%s
"""

THEME_PROMPT = """あなたは不動産投資家コミュニティ「神・大家さん倶楽部」の講座企画を手伝う担当です。
次の材料から、講座またはグループコンサル（グルコン）のテーマ案をちょうど5つ出してください。id は t1〜t5。

材料:
- ranking: Q&Aチャットでよく聞かれていること（回数・人数は質問ログから数えた正確な値）
- forum / openchat: コミュニティとLINEオープンチャットの投稿の集計と質問の抜粋（件数は投稿数）
- courses.titles: 既存の講座

決まりごと:
- 需要（ranking の回数・人数、コミュニティ・オプチャで多い話題）に対して既存講座が少ない「すき間」を優先する。
- 既存講座が多いテーマは、新しい切り口（最新動向・事例・実務の手順）がある場合だけにする。
- 過去の判断（decisions）を必ず反映する。不採用の理由に当てはまる案は出さない。直して採用された題名の傾向
  （具体さ・言い回し）に合わせる。採用済みと同じ案は繰り返さない。
- title は30字以内、why は「なぜ今これか」を2文以内、evidence は根拠の数字（どこで何回・何人・何件）を1文、
  format は形式（例: 60分講座、グルコン、連載3回）、target は対象（例: 1棟目購入前、築古戸建の保有者）。
- 個人名・会社名・物件の住所・電話番号などは書かない。

出力は次の形の JSON だけ: {"themes":[{"id":"t1","title":"","why":"","evidence":"","format":"","target":""}]}

decisions:
%s

ranking:
%s

forum / openchat / courses:
%s
"""


def s_(v, n):
    return str(v or "").strip()[:n]


def build_ranking(top: list[dict], groups: list[dict]) -> list[dict]:
    """Gemini のまとめ方に、質問ログの回数（n）と人数（u のハッシュの重複なし）を当てる。"""
    by_id = {f"q{i + 1}": q for i, q in enumerate(top)}
    used: set[str] = set()
    out = []
    for g in groups:
        if not isinstance(g, dict):
            continue
        ids = [i for i in dict.fromkeys(str(x) for x in (g.get("ids") or [])) if i in by_id and i not in used]
        if not ids:
            continue
        used.update(ids)
        out.append((s_(g.get("topic"), 80) or "(名前なし)", [by_id[i] for i in ids]))
    # Gemini が入れ忘れた質問も落とさない（その文面のまとまりにする）
    for i, q in by_id.items():
        if i not in used:
            out.append((s_(q.get("q"), 40), [q]))
    ranking = []
    for topic, qs in out:
        if topic == "(質問以外)":
            continue
        users = set()
        for q in qs:
            users.update(str(u) for u in (q.get("u") or []))
        qs = sorted(qs, key=lambda q: -int(q.get("n") or 0))
        ranking.append({"topic": topic, "count": sum(int(q.get("n") or 0) for q in qs), "people": len(users),
                        "variants": len(qs), "examples": [s_(q.get("q"), 140) for q in qs[:3]]})
    ranking.sort(key=lambda r: (-r["count"], -r["people"], r["topic"]))
    return ranking[:20]


def clean_themes(res: dict) -> list:
    themes = [{"id": f"t{i + 1}", "title": s_(t.get("title"), 120), "why": s_(t.get("why"), 400),
               "evidence": s_(t.get("evidence"), 400), "format": s_(t.get("format"), 120), "target": s_(t.get("target"), 120)}
              for i, t in enumerate([t for t in (res.get("themes") or []) if isinstance(t, dict) and t.get("title")][:5])]
    if len(themes) < 3:
        raise SystemExit("テーマ案が足りません（Gemini の応答が想定と違う）")
    return themes


def main() -> None:
    if not (URL and KEY and GEMINI_KEY):
        raise SystemExit("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / GEMINI_API_KEY が必要です")
    digest = rest("rpc/qa_theme_source_digest", "POST", {"p_days": DAYS})
    size = len(json.dumps(digest, ensure_ascii=False).encode())
    decisions = past_decisions()
    top = digest["chatbot"]["top"]
    listing = "\n".join(f'q{i + 1}\t{q["q"]}\t{q["n"]}' for i, q in enumerate(top))
    groups = gemini(GROUP_PROMPT % listing, GROUP_SCHEMA).get("groups") or [] if top else []
    ranking = build_ranking(top, groups)
    rest_part = {k: digest[k] for k in ("forum", "openchat", "courses")}
    themes = clean_themes(gemini(THEME_PROMPT % (json.dumps(decisions, ensure_ascii=False),
                                                 json.dumps(ranking, ensure_ascii=False),
                                                 json.dumps(rest_part, ensure_ascii=False)), THEME_SCHEMA))
    now = dt.datetime.now(JST)
    rid = "r" + now.strftime("%Y%m%d")
    if rest(f"qa_theme_rounds?select=id&id=eq.{rid}"):
        rid += now.strftime("-%H%M")
    row = {"id": rid, "period_days": DAYS, "model": MODEL, "ranking": ranking, "themes": themes,
           "stats": {"chatbot": digest["chatbot"]["events"], "chatbot_users": digest["chatbot"]["users"], "forum": digest["forum"]["posts"],
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
