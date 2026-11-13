#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UI/UX の好みループ — 画面づくりの判断を owner_decisions に溜め、好み帳で次に効かせる。

3アプリ（ジャービスダッシュボード・KURASHIFT・ループウェア）の画面を作る／直すときに使う。
資料作成ループ（apps/loopware/scripts/slides_loop.py）と同じ型。AI は呼ばない（AI はこれを使うエージェント自身）。

  作る前   context で好み帳を読む → 大きな変更は2〜3案を put（Nody /uiux）→ 松野さんが 良い／違う／迷う（uiux_plan）
  作った後 チャットでの「ここ違う」「これいいね」を log-fix で1件ずつ記録（uiux_fix。何往復目か・使ったルール）
  土曜     直しをまとめた好みルール案を put（stage=review）→ 松野さんが 採用／今回だけ／違う（uiux_rule）
           → sync-book で採用分を好み帳（uiux_taste.md の ## 確定ルール）へ書き出す
  毎週     metrics で 1案目OK率・平均往復回数・ルール命中（jarvis_loopware_weekly.py の週次にも出る）

使い方（リポジトリルートで .env.jarvis_private を読んでから。値は表示しない）:

  S=scripts/jarvis_uiux_loop.py
  python $S context --app dashboard                 # 作る前に必ず読む（確定ルール・参照例・最近の直し）
  python $S put --file round.json --image A=a.png --image B=b.png [--dry-run]
  python $S log-fix --app dashboard --work pr395-home-order --trip 1 --verdict wrong \\
      --what '並べ替えはiPhoneのホーム画面と同じ長押しがいい' --item efficiency --tags steps --applied R800-001
  python $S log-fix ... --verdict good --done        # 確定（「これでいい」）。--done は最後の1件に付ける
  python $S state | metrics [--days 90] | export --work ID | sync-book [--dry-run]

--verdict: good（これいいね）/ wrong（ここ違う）/ hesitated（迷う）/ comment（ひとこと）。
--trip を省くと、同じ --work の記録数＋1（新しい往復）として数える。同じ往復で複数の指摘があるときは --trip を揃える。
理由が分からない直しは推測で埋めない（--what だけ書き、--tags を省く）。

環境変数: JARVIS_SUPABASE_URL, JARVIS_SUPABASE_SERVICE_ROLE_KEY
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from jarvis_owner_decision_log import contract_row  # noqa: E402

META_KEY = "loopware_uiux"
BUCKET = "uiux-shots"
EMPLOYEE = "814"
NODY_URL = os.environ.get("LOOPWARE_URL", "https://jarvis-loopware.vercel.app").rstrip("/")
BOOK = REPO / "docs" / "AIエージェントチーム" / "800_俯瞰UI・投影更新室" / "uiux_taste.md"
SCORECARD = REPO / "apps" / "jarvis-dashboard" / "config" / "uiux_scorecard.json"
APPS = ("dashboard", "kurashift", "loopware")
VERDICTS = ("good", "wrong", "hesitated", "comment")
PLAN_TAGS = ("info_more", "info_less", "layout", "color", "text_size", "motion", "ui_words", "phone", "steps")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
ROUND_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
WORK_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
MAX_CONFIRMED = 15


# ---------------------------------------------------------------- 純粋な部品（テスト対象）

def scorecard_items() -> dict[str, str]:
    try:
        d = json.loads(SCORECARD.read_text(encoding="utf-8"))
        return {a["key"]: a["label"] for a in d.get("axes", [])}
    except Exception:  # noqa: BLE001
        return {}


def validate_round(d: dict[str, Any]) -> list[str]:
    errs = []
    if not ROUND_RE.match(str(d.get("id", ""))):
        errs.append("id は英数字と - _ . で80字まで（例 2026-11-14-home-order）")
    if not str(d.get("title", "")).strip():
        errs.append("title が空")
    if d.get("app", "*") not in (*APPS, "*"):
        errs.append("app は dashboard / kurashift / loopware / *")
    if d.get("stage") not in ("plan", "review", "done"):
        errs.append("stage は plan / review / done")
    plans = d.get("plans", []) or []
    if len(plans) > 4:
        errs.append("plans は4つまで（2〜3つ推奨）")
    for p in plans:
        if not ID_RE.match(str(p.get("id", ""))) or not str(p.get("label", "")).strip():
            errs.append(f"plans の id/label が不正: {p.get('id')}")
    ids = [p.get("id") for p in d.get("proposals", []) or []]
    if len(ids) != len(set(ids)):
        errs.append("proposals の id が重複")
    for p in d.get("proposals", []) or []:
        if not ID_RE.match(str(p.get("id", ""))) or not str(p.get("text", "")).strip():
            errs.append(f"proposals の id/text が不正: {p.get('id')}")
    if d.get("stage") == "plan" and len(plans) < 2:
        errs.append("stage=plan なら plans を2つ以上（1案で済む小さな直しは put せず log-fix だけ）")
    if d.get("stage") == "review" and not d.get("proposals"):
        errs.append("stage=review なら proposals が要る")
    return errs


def fix_row(
    *, app: str, work: str, trip: int, verdict: str, what: str, item: str | None = None,
    tags: list[str] | None = None, applied: list[str] | None = None, pr: int | None = None,
    screen: str | None = None, done: bool = False, before: str | None = None, after: str | None = None,
    idem_key: str | None = None,
) -> dict[str, Any]:
    """uiux_fix の1行（契約 v1）。ネットワーク不要。"""
    if app not in APPS:
        raise ValueError("--app は dashboard / kurashift / loopware")
    if not WORK_RE.match(work):
        raise ValueError("--work は英数字と - _ . で80字まで（例 pr395-home-order）")
    if verdict not in VERDICTS:
        raise ValueError(f"--verdict は {' / '.join(VERDICTS)}")
    items = scorecard_items()
    if item and items and item not in items:
        raise ValueError(f"--item は採点表の項目: {', '.join(items)}")
    tags = [t for t in (tags or []) if t]
    bad = [t for t in tags if t not in PLAN_TAGS]
    if bad:
        raise ValueError(f"--tags は {', '.join(PLAN_TAGS)}（不明: {', '.join(bad)}）")
    action = "comment" if verdict == "comment" else verdict
    payload: dict[str, Any] = {
        "app": app,
        "work_id": work,
        "round_trip": max(1, int(trip)),
        "done": bool(done),
        "item": item or None,
        "concept": items.get(item or "", None) if item else None,
        "reason_tags": tags,
        "applied_rules": [a for a in (applied or []) if a],
    }
    if pr:
        payload["pr"] = int(pr)
    if screen:
        payload["screen"] = screen[:80]
    if before or after:
        payload["images"] = {k: v for k, v in (("before", before), ("after", after)) if v}
    row = contract_row(
        surface="uiux_fix", action=action, source="script", target_type="uiux_work", target_id=work,
        employee=EMPLOYEE, subject=(screen or work)[:200], note=(what or "").strip()[:1000] or None,
        payload=payload, idem_key=idem_key or f"uiux-fix-{uuid.uuid4()}",
    )
    return row


def fix_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """uiux_fix の行を画面づくり（work_id）ごとに束ねる。

    1案目OK＝最初の往復（round_trip=1）の最初の判断が good。往復回数＝round_trip の最大。
    ルール命中＝applied_rules がある画面づくりと無いものの 1案目OK率。
    """
    works: dict[str, dict[str, Any]] = {}
    for r in sorted(rows, key=lambda x: str(x.get("decided_at") or "")):
        pl = r.get("payload") or {}
        wid = str(pl.get("work_id") or "")
        if not wid:
            continue
        w = works.setdefault(wid, {"first": None, "trips": 0, "applied": set(), "app": pl.get("app"), "wrong_tags": defaultdict(int)})
        trip = int(pl.get("round_trip") or 1)
        if trip == 1 and w["first"] is None and r.get("action") != "comment":
            w["first"] = r.get("action")
        w["trips"] = max(w["trips"], trip)
        w["applied"].update(pl.get("applied_rules") or [])
        if r.get("action") == "wrong":
            for t in pl.get("reason_tags") or []:
                w["wrong_tags"][t] += 1

    def rate(ws: list[dict[str, Any]]) -> float | None:
        return round(sum(1 for w in ws if w["first"] == "good") / len(ws), 3) if ws else None

    ws = list(works.values())
    with_rules = [w for w in ws if w["applied"]]
    without = [w for w in ws if not w["applied"]]
    tags: dict[str, int] = defaultdict(int)
    for w in ws:
        for t, n in w["wrong_tags"].items():
            tags[t] += n
    by_app: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for w in ws:
        by_app[str(w["app"] or "-")].append(w)
    return {
        "works": len(ws),
        "first_ok": sum(1 for w in ws if w["first"] == "good"),
        "first_ok_rate": rate(ws),
        "avg_trips": round(sum(w["trips"] for w in ws) / len(ws), 2) if ws else None,
        "with_rules": {"works": len(with_rules), "first_ok_rate": rate(with_rules)},
        "without_rules": {"works": len(without), "first_ok_rate": rate(without)},
        "by_app": {a: {"works": len(x), "first_ok_rate": rate(x)} for a, x in sorted(by_app.items())},
        "wrong_tags": dict(sorted(tags.items(), key=lambda kv: -kv[1])),
    }


def metrics_lines(m: dict[str, Any]) -> list[str]:
    """週次まとめ用の Markdown 行"""
    if not m["works"]:
        return ["- 今週は画面づくりの記録がありません"]
    pct = lambda v: "-" if v is None else f"{v:.0%}"  # noqa: E731
    lines = [
        f"- 1案目OK {m['first_ok']}／{m['works']} 件（{pct(m['first_ok_rate'])}）・平均 {m['avg_trips']} 往復（目標：3か月後50%・1年後70%）",
        f"- 好み帳を使った案 {pct(m['with_rules']['first_ok_rate'])}（{m['with_rules']['works']}件）／使わなかった案 {pct(m['without_rules']['first_ok_rate'])}（{m['without_rules']['works']}件）",
    ]
    if m["wrong_tags"]:
        lines.append("- 「違う」の理由: " + "・".join(f"{k} {v}" for k, v in m["wrong_tags"].items()))
    return lines


def adopted_rules(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    last: dict[str, dict[str, Any]] = {}
    for r in sorted(rows, key=lambda x: str(x.get("decided_at") or "")):
        last[r["target_id"]] = r
    out = []
    for k, r in last.items():
        if r.get("action") == "rule_accept":
            pl = r.get("payload") or {}
            out.append({"key": k, "text": pl.get("text"), "concept": pl.get("concept"), "app": pl.get("app") or "*",
                        "why": pl.get("why"), "at": r.get("decided_at"), "id": r.get("id")})
    return sorted(out, key=lambda x: str(x["at"] or ""))


def book_lines(rules: list[dict[str, Any]]) -> list[str]:
    """採用済みルール → 好み帳の ## 確定ルール 行（古い順に R800-001…。最大15行）"""
    out = []
    for i, r in enumerate(rules[:MAX_CONFIRMED], 1):
        date = str(r.get("at") or "")[:10]
        cond = f"app:{r['app']}" + (f" & item:{r['concept']}" if r.get("concept") else "")
        out.append(f"- R800-{i:03d} | ui | {cond} | v1 {date} | 根拠 {r.get('id') or r['key']} | {r['text']}")
    return out


def replace_section(md: str, heading: str, lines: list[str], empty: str) -> str:
    pat = re.compile(rf"(^## {re.escape(heading)}\n)(.*?)(?=^## |\Z)", re.S | re.M)
    body = "\n" + ("\n".join(lines) if lines else empty) + "\n\n"
    if not pat.search(md):
        return md.rstrip() + f"\n\n## {heading}\n{body}"
    return pat.sub(lambda m: m.group(1) + body, md, count=1)


def book_section(md: str, heading: str) -> list[str]:
    m = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", md, re.S | re.M)
    if not m:
        return []
    return [ln for ln in m.group(1).splitlines() if ln.startswith("- ")]


# ---------------------------------------------------------------- Supabase（REST）

def env() -> tuple[str, str]:
    url = os.environ.get("JARVIS_SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or ""
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        sys.exit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が未設定です（.env.jarvis_private を読んでください）")
    return url.rstrip("/"), key


def http(method: str, path: str, body: Any = None, *, prefer: str | None = None, raw: bytes | None = None,
         ctype: str = "application/json", extra: dict[str, str] | None = None) -> Any:
    url, key = env()
    req = urllib.request.Request(f"{url}{path}", method=method)
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", ctype)
    if prefer:
        req.add_header("Prefer", prefer)
    for k, v in (extra or {}).items():
        req.add_header(k, v)
    data = raw if raw is not None else (json.dumps(body, ensure_ascii=False).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, data=data, timeout=60) as r:
            txt = r.read().decode() or "null"
            try:
                return json.loads(txt)
            except json.JSONDecodeError:
                return txt
    except urllib.error.HTTPError as e:
        sys.exit(f"Supabase {method} {path.split('?')[0]} 失敗: {e.code} {e.read().decode()[:300]}")


def rest(method: str, path: str, body: Any = None, prefer: str | None = None) -> Any:
    return http(method, f"/rest/v1/{path}", body, prefer=prefer)


def upload(local: str, dest: str) -> str:
    """画像を uiux-shots バケットへ。戻り値は "storage:<パス>" """
    p = Path(local)
    if not p.is_file():
        sys.exit(f"画像がありません: {local}")
    ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    if not ctype.startswith("image/"):
        sys.exit(f"画像ではありません: {local}")
    http("POST", f"/storage/v1/object/{BUCKET}/{urllib.parse.quote(dest)}", raw=p.read_bytes(), ctype=ctype,
         extra={"x-upsert": "true"})
    return f"storage:{dest}"


def fetch_rows(surfaces: str, days: int | None = None, extra: str = "") -> list[dict[str, Any]]:
    q = f"owner_decisions?surface=in.({surfaces})&select=id,surface,action,target_id,subject,note,payload,decided_at&order=decided_at.asc&limit=2000{extra}"
    if days:
        since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - days * 86400))
        q += f"&decided_at=gte.{since}"
    return rest("GET", q) or []


# ---------------------------------------------------------------- コマンド

def cmd_context(a) -> None:
    md = BOOK.read_text(encoding="utf-8") if BOOK.exists() else ""
    rules = [r for r in adopted_rules(fetch_rows("uiux_rule")) if r["app"] in ("*", a.app)] if not a.offline else []
    fixes = [] if a.offline else [r for r in fetch_rows("uiux_fix", days=60) if (r.get("payload") or {}).get("app") == a.app][-a.recent:]
    print(f"# 画面づくりの前に読む（{a.app}）\n")
    print("## 確定ルール（好み帳。案を見せるときに使ったルール番号を一言添える）")
    lines = [ln for ln in book_section(md, "確定ルール") if f"app:{a.app}" in ln or "app:*" in ln]
    print("\n".join(lines) if lines else "（まだありません）")
    if rules and len(rules) != len(lines):
        print("\n※ DB の採用済みルールと好み帳がずれています。`sync-book` で揃えてください:")
        for r in rules:
            print(f"- {r['text']}（{r['app']}）")
    for h in ("例外", "参照例", "仮説"):
        ls = book_section(md, h)
        if ls:
            print(f"\n## {h}" + ("（効かせない。確かめる候補）" if h == "仮説" else ""))
            print("\n".join(ls))
    print("\n## 最近の直し（新しい順）")
    if not fixes:
        print("（まだありません）")
    for r in reversed(fixes):
        pl = r.get("payload") or {}
        mark = {"good": "👍", "wrong": "✋", "hesitated": "…", "comment": "💬"}.get(r["action"], r["action"])
        print(f"- {mark} {pl.get('work_id')} {pl.get('round_trip')}往復目: {r.get('note') or ''}" + (f"［{','.join(pl.get('reason_tags') or [])}］" if pl.get("reason_tags") else ""))


def cmd_state(_a) -> None:
    meta = rest("GET", f"sync_meta?key=eq.{META_KEY}&select=value")
    rnd = None
    if meta:
        v = meta[0]["value"]
        try:
            rnd = json.loads(v) if isinstance(v, str) else v
        except Exception:  # noqa: BLE001
            rnd = None
    picked = None
    if rnd:
        got = rest("GET", f"owner_decisions?surface=eq.uiux_plan&target_id=eq.{urllib.parse.quote(rnd['id'])}&select=action,payload,note,decided_at&order=decided_at.desc&limit=1") or []
        picked = got[0] if got else None
    print(json.dumps({"round": rnd, "picked": picked, "uiux_rules": adopted_rules(fetch_rows("uiux_rule"))}, ensure_ascii=False, indent=2))


def cmd_put(a) -> None:
    rnd = json.loads(Path(a.file).read_text(encoding="utf-8"))
    rnd.setdefault("created_at", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    rnd.setdefault("app", "*")
    errs = validate_round(rnd)
    imgs = dict(x.split("=", 1) for x in (a.image or []) if "=" in x)
    plan_ids = {p.get("id") for p in rnd.get("plans", []) or []}
    errs += [f"--image の案 {k} が plans にありません" for k in imgs if k not in plan_ids]
    if errs:
        sys.exit("ラウンドの形が不正:\n- " + "\n- ".join(errs))
    for p in rnd.get("plans", []) or []:
        if p.get("id") in imgs:
            ext = Path(imgs[p["id"]]).suffix.lower() or ".png"
            dest = f"{rnd['id']}/{p['id']}{ext}"
            p["image"] = f"storage:{dest}" if a.dry_run else upload(imgs[p["id"]], dest)
    if a.dry_run:
        print(json.dumps(rnd, ensure_ascii=False, indent=2))
        print("(dry-run: 書き込みません)")
        return
    rest("POST", "sync_meta?on_conflict=key", [{"key": META_KEY, "value": json.dumps(rnd, ensure_ascii=False)}],
         prefer="resolution=merge-duplicates,return=minimal")
    print(f"置きました: {rnd['id']}（stage={rnd['stage']}）→ {NODY_URL}/uiux")


def cmd_log_fix(a) -> None:
    trip = a.trip
    if trip is None:
        if a.dry_run or a.sql:
            trip = 1
        else:
            got = rest("GET", f"owner_decisions?surface=eq.uiux_fix&target_id=eq.{urllib.parse.quote(a.work)}&select=payload") or []
            trip = max([int((g.get("payload") or {}).get("round_trip") or 0) for g in got] or [0]) + 1
    before = after = None
    if a.before_img or a.after_img:
        stamp = time.strftime("%Y%m%d%H%M%S")
        if a.before_img:
            before = f"storage:fix/{a.work}/{stamp}-before{Path(a.before_img).suffix}" if (a.dry_run or a.sql) else upload(a.before_img, f"fix/{a.work}/{stamp}-before{Path(a.before_img).suffix}")
        if a.after_img:
            after = f"storage:fix/{a.work}/{stamp}-after{Path(a.after_img).suffix}" if (a.dry_run or a.sql) else upload(a.after_img, f"fix/{a.work}/{stamp}-after{Path(a.after_img).suffix}")
    try:
        row = fix_row(app=a.app, work=a.work, trip=trip, verdict=a.verdict, what=a.what, item=a.item,
                      tags=(a.tags or "").split(",") if a.tags else [], applied=(a.applied or "").split(",") if a.applied else [],
                      pr=a.pr, screen=a.screen, done=a.done, before=before, after=after)
    except ValueError as e:
        sys.exit(str(e))
    if a.sql:
        cols = ", ".join(row)
        vals = ", ".join("NULL" if v is None else ("'" + (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)).replace("'", "''") + "'" + ("::jsonb" if isinstance(v, dict) else "")) for v in row.values())
        print(f"insert into owner_decisions ({cols}) values ({vals});")
        return
    if a.dry_run:
        print(json.dumps(row, ensure_ascii=False, indent=2))
        return
    rest("POST", "owner_decisions", row, prefer="return=minimal")
    print(f"記録しました: {a.work} {trip}往復目 {a.verdict}" + ("（確定）" if a.done else ""))


def cmd_metrics(a) -> None:
    m = fix_metrics(fetch_rows("uiux_fix", days=a.days))
    print(json.dumps(m, ensure_ascii=False, indent=2) if a.json else "\n".join(metrics_lines(m)))


def cmd_export(a) -> None:
    w = urllib.parse.quote(a.work)
    print(json.dumps(fetch_rows("uiux_plan,uiux_fix,uiux_rule", extra=f"&or=(target_id.eq.{w},target_id.like.{w}:*)"), ensure_ascii=False, indent=2))


def cmd_sync_book(a) -> None:
    rules = adopted_rules(fetch_rows("uiux_rule"))
    md = BOOK.read_text(encoding="utf-8")
    new = replace_section(md, "確定ルール", book_lines(rules), f"（最大{MAX_CONFIRMED}行。まだありません）")
    if len(rules) > MAX_CONFIRMED:
        print(f"注意: 採用済みが {len(rules)} 件あり、{MAX_CONFIRMED} 件を超えた分は効かせていません", file=sys.stderr)
    if a.dry_run:
        print(new)
        return
    if new != md:
        BOOK.write_text(new, encoding="utf-8")
        print(f"好み帳を更新しました（確定ルール {min(len(rules), MAX_CONFIRMED)} 件）: {BOOK.relative_to(REPO)}")
    else:
        print("好み帳は最新です")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("context")
    p.add_argument("--app", required=True, choices=APPS)
    p.add_argument("--recent", type=int, default=8)
    p.add_argument("--offline", action="store_true", help="DB を読まず好み帳だけ")
    sp.add_parser("state")
    p = sp.add_parser("put")
    p.add_argument("--file", required=True)
    p.add_argument("--image", action="append", help="案ID=画像ファイル（例 A=a.png）")
    p.add_argument("--dry-run", action="store_true")
    p = sp.add_parser("log-fix")
    p.add_argument("--app", required=True, choices=APPS)
    p.add_argument("--work", required=True, help="画面づくり1件のID（例 pr395-home-order）")
    p.add_argument("--trip", type=int)
    p.add_argument("--verdict", required=True, choices=VERDICTS)
    p.add_argument("--what", required=True, help="松野さんの言葉を短く")
    p.add_argument("--item", help="採点表の項目 key（clarity / efficiency / mobile …）")
    p.add_argument("--tags", help=f"カンマ区切り: {','.join(PLAN_TAGS)}")
    p.add_argument("--applied", help="使った好みルール（カンマ区切り。例 R800-001,R800-003）")
    p.add_argument("--pr", type=int)
    p.add_argument("--screen")
    p.add_argument("--done", action="store_true", help="この画面づくりの確定")
    p.add_argument("--before-img")
    p.add_argument("--after-img")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--sql", action="store_true", help="DB に書かず INSERT 文を出す")
    p = sp.add_parser("metrics")
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--json", action="store_true")
    p = sp.add_parser("export")
    p.add_argument("--work", required=True)
    p = sp.add_parser("sync-book")
    p.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    {"context": cmd_context, "state": cmd_state, "put": cmd_put, "log-fix": cmd_log_fix, "metrics": cmd_metrics,
     "export": cmd_export, "sync-book": cmd_sync_book}[a.cmd](a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
