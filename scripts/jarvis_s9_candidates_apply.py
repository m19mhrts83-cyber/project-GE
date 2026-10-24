#!/usr/bin/env python3
"""S9 候補（部長ボックス action: s9_candidates）→ 管理会社台帳へ取り込み（AI なし）。

S9 は毎日 1 日 2〜3 社の候補を `10_inbox_from_grok/YYYY-MM-DD_s9_candidates.md` に置くが、
Jarvis 側に取り込み口が無く、台帳（config/kurashift_mgmt_vendor_list.yaml）の緑区は電話のみ
18 社＝S9 が送れる相手 0 社のまま止まっていた（最終送信 8/27・2026-10-24 判明）。

  - はっきりした候補（メールかフォームあり・重複なし）→ 台帳へ status=pending で自動追加
  - 判断が要る候補（関連／片方だけ／後回し／要確認）→ #consult に候補カードを出し、
    松野が［採用］［見送り］ボタンで判断（ボタン → kurashift_jobs → jarvis_s9_decision_apply.py）
  - 送らない候補（電話のみ・売買専門）→ 台帳に入れず #report に1行（consult しない）
  - 大手／全国は自動で台帳へ（2026-10-24 松野指示。地場優先は送信順ではなく内容で見る）
  - 処理した MD は 90_archive/inbox_from_grok へ

    ~/selenium_env/venv/bin/python scripts/jarvis_s9_candidates_apply.py --dry-run
    ~/selenium_env/venv/bin/python scripts/jarvis_s9_candidates_apply.py --apply --archive-done --post

入口: jarvis_bucho_inbox_poll.py（15 分 poll）から自動 apply
停止: JARVIS_S9_CANDIDATES_AUTO_APPLY=0
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jarvis_bucho_bridge_lib import STATE_DIR, folder, list_queue_files  # noqa: E402
import jarvis_s9_slack_blocks as s9blocks  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
JST = ZoneInfo("Asia/Tokyo")
ACTION = "s9_candidates"
LANE = "midori_caramel"
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
URL_RE = re.compile(r"https?://[^\s）)（(、，,]+")
TEL_RE = re.compile(r"0\d{1,4}-\d{1,4}-\d{3,4}")
# メモの語で自動判定を変える（2026-10-24 松野指示で見直し）
#   consult … 人が採否を決める（グループ・系列の重複疑い／先送り／要確認）
#   drop    … 送らないので台帳に入れず #report だけ（電話のみ・売買専門）
CONSULT_HINTS = ("関連", "片方だけ", "後回し", "要確認")
DROP_HINTS = ("売買のみ", "売買専門")
CORP_WORDS = ("株式会社", "有限会社", "合同会社", "（株）", "(株)", "（有）", "(有)")


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    meta: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip("\"'")
    return meta, text[end + 4 :]


def parse_candidates(body: str) -> list[dict[str, str]]:
    """`## N. 社名` 見出しごとに `- 項目: 値` を拾う。"""
    out: list[dict[str, str]] = []
    cur: dict[str, str] | None = None
    for line in body.splitlines():
        m = re.match(r"^##\s*\d+[.．]\s*(.+?)\s*$", line)
        if m:
            cur = {"heading": m.group(1)}
            out.append(cur)
            continue
        if line.startswith("## "):  # 「待ちの候補」等の別節
            cur = None
            continue
        if cur is None:
            continue
        m = re.match(r"^\s*-\s*([^:：]+)[:：]\s*(.+)$", line)
        if m:
            cur[m.group(1).strip()] = m.group(2).strip()
    return out


def _pick(c: dict[str, str], *keys: str) -> str:
    for k in keys:
        if c.get(k):
            return c[k]
    return ""


def _area_of(text: str) -> str:
    """名古屋市緑区 → 緑区、愛知県豊明市 → 豊明市（区があれば区を優先）。"""
    t = re.sub(r"[一-龥]{1,3}[都道府県]", " ", text).replace("名古屋市", " ")
    m = re.search(r"([一-龥]{1,3}区)", t) or re.search(r"([一-龥]{1,3}市)", t)
    return m.group(1) if m else ""


def to_row(c: dict[str, str], *, md_date: str) -> dict[str, Any]:
    heading = c["heading"]
    name = _pick(c, "社名") or re.sub(r"[（(][^）)]*[）)]\s*$", "", heading).strip() or heading
    addr = _pick(c, "所在")
    route = _pick(c, "連絡経路")
    official = (URL_RE.findall(_pick(c, "公式URL")) or [""])[0]
    emails = EMAIL_RE.findall(route)
    route_urls = [u for u in URL_RE.findall(route) if "@" not in u]
    form = next((u for u in route_urls if not official or u.rstrip("/") != official.rstrip("/")), "")
    form = form or (route_urls[0] if route_urls else "")
    memo = " ".join(x for x in (_pick(c, "備考", "メモ"), _pick(c, "賃貸を扱う根拠", "賃貸の根拠")) if x)
    phone = (TEL_RE.findall(" ".join(c.values())) or [""])[0]
    area = _area_of(f"{addr} {heading}")
    channel = "email" if emails else ("web_form" if form else "phone")
    return {
        "name": name,
        "area": f"愛知 {addr}".strip()[:80],
        "prefecture": "愛知県",
        "city": "名古屋市" if "名古屋" in addr else (area if area.endswith("市") else ""),
        "property_area": area,
        "property_lane": LANE,
        "url": official,
        "contact_url": form or official,
        "channel": channel,
        "contact_email": emails[0] if emails else "",
        "phone": phone,
        "status": "pending",
        "source": f"s9_candidates_{md_date}",
        "notes": f"S9候補 {md_date}。{memo}"[:400],
        "discovered_at": md_date,
        "_memo": memo,
    }


def _norm_name(s: str) -> str:
    for w in CORP_WORDS:
        s = s.replace(w, "")
    return re.sub(r"[\s・（）()]", "", s)


def _domain(u: str) -> str:
    try:
        h = urlparse(u).hostname or ""
    except ValueError:
        return ""
    return h.removeprefix("www.")


def find_existing(row: dict[str, Any], vendors: list[dict[str, Any]]) -> dict[str, Any] | None:
    keys = {
        "name": _norm_name(row["name"]),
        "domain": _domain(row["url"]) or _domain(row["contact_url"]),
        "email": row["contact_email"].lower(),
        "phone": row["phone"],
    }
    for v in vendors:
        if keys["name"] and keys["name"] == _norm_name(str(v.get("name") or "")):
            return v
        vd = {_domain(str(v.get("url") or "")), _domain(str(v.get("contact_url") or ""))} - {""}
        if keys["domain"] and keys["domain"] in vd:
            return v
        if keys["email"] and keys["email"] == str(v.get("contact_email") or "").lower():
            return v
        if keys["phone"] and keys["phone"] == str(v.get("phone") or ""):
            return v
    return None


def classify(row: dict[str, Any], vendors: list[dict[str, Any]]) -> tuple[str, str]:
    """('add'|'dup'|'consult'|'drop', 理由)。"""
    ex = find_existing(row, vendors)
    if ex:
        return "dup", f"台帳に既存（{ex.get('name')}・{ex.get('status')}）"
    if row["channel"] == "phone":
        return "drop", "メール／フォームが見つからない（送れない）"
    drop = next((h for h in DROP_HINTS if h in row["_memo"]), "")
    if drop:
        return "drop", f"メモに「{drop}」（送らない）"
    # 同一問合せ先／同一会社ドメイン（グループ・支店違い）は自動で入れず判断を仰ぐ
    import jarvis_kurashift_mgmt_vendor_list as ml

    dup_why = ml.duplicate_contact_reason(row, vendors)
    if dup_why:
        return "consult", dup_why
    hit = next((h for h in CONSULT_HINTS if h in row["_memo"]), "")
    if hit:
        return "consult", f"メモに「{hit}」"
    return "add", ""


def build_consult(items: list[tuple[dict[str, Any], str, str]]) -> str:
    """プレーン本文（ログ・通知用）。Slack はボタン付きカードで投稿する。"""
    rows = [{**row, "n": n, "why": why} for n, (row, why, _md) in enumerate(items, 1)]
    return s9blocks.build_consult_text(
        rows, md_note=items[0][2] if items else ""
    )


def build_report(
    added: list[dict[str, Any]],
    dups: int,
    consult: int,
    dropped: list[tuple[dict[str, Any], str]] | None = None,
) -> str:
    names = "・".join(r["name"] for r in added[:5]) or "なし"
    lines = [
        "【報告】S9 管理会社開拓・候補取り込み",
        f"台帳に追加 {len(added)}社: {names}",
        f"重複で除外 {dups}／#consult で判断 {consult}",
    ]
    if dropped:
        detail = "・".join(f"{r['name']}（{why}）" for r, why in dropped[:4])
        lines.append(f"送らないので台帳に入れず {len(dropped)}: {detail}")
    return "\n".join(lines)


def _post(channel: str, text: str) -> int:
    return subprocess.run(
        [sys.executable, str(REPO / "scripts" / "jarvis_slack_webhook_post.py"), "--channel", channel, "--text", text],
        cwd=REPO,
    ).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--archive-done", action="store_true")
    ap.add_argument("--post", action="store_true", help="#report（追加結果）と #consult（判断待ち）へ投稿")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if not (args.dry_run or args.apply):
        ap.error("--dry-run または --apply")
    if os.environ.get("JARVIS_S9_CANDIDATES_AUTO_APPLY", "1") == "0" and not args.dry_run:
        print(json.dumps({"ok": True, "skipped": "JARVIS_S9_CANDIDATES_AUTO_APPLY=0"}))
        return 0

    # 画面ロック解除・朝の更新・15分 poll が同時に走っても台帳追加と Slack 投稿は 1 回だけ
    lock_path = STATE_DIR / "s9_candidates_apply.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fh = open(lock_path, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_fh.close()
        print(json.dumps({"ok": True, "skipped": "another apply running"}))
        return 0

    import jarvis_kurashift_mgmt_vendor_list as ml

    data = ml.load_list()
    vendors = [v for v in data.get("vendors") or [] if isinstance(v, dict)]
    inbox = folder("inbox_from_grok")
    to_add: list[dict[str, Any]] = []
    consult: list[tuple[dict[str, Any], str, str]] = []
    dropped: list[tuple[dict[str, Any], str]] = []
    dups = 0
    files_done: list[Path] = []
    for p in list_queue_files(inbox):
        meta, body = parse_frontmatter(p.read_text(encoding="utf-8", errors="replace"))
        if (meta.get("action") or "").strip() != ACTION:
            continue
        md_date = (meta.get("date") or p.name[:10]).strip()
        for c in parse_candidates(body):
            row = to_row(c, md_date=md_date)
            kind, why = classify(row, vendors + to_add)
            if kind == "add":
                to_add.append(row)
            elif kind == "dup":
                dups += 1
            elif kind == "drop":
                dropped.append((row, why))
            else:
                consult.append((row, why, p.name))
        files_done.append(p)

    clean = [{k: v for k, v in r.items() if not k.startswith("_")} for r in to_add]
    res: dict[str, Any] = {"files": [f.name for f in files_done], "add": [r["name"] for r in clean], "dups": dups,
                           "consult": [(r["name"], why) for r, why, _ in consult],
                           "dropped": [(r["name"], why) for r, why in dropped]}
    if args.apply and files_done:
        res["merge"] = ml.merge_append(clean, dry_run=False)
        if args.post:
            if clean or dups or dropped:
                _post("report", build_report(clean, dups, len(consult), dropped))
            if consult:
                items = [
                    {**row, "n": n, "why": why, "source_md": md}
                    for n, (row, why, md) in enumerate(consult, 1)
                ]
                s9blocks.post_decision_card(
                    items, md_note=f"{consult[0][2]} ほか"
                )
        if args.archive_done:
            arch = inbox.parent / "90_archive" / "inbox_from_grok"
            arch.mkdir(parents=True, exist_ok=True)
            for f in files_done:
                dest = arch / f.name
                if dest.exists():
                    dest = arch / f"{f.stem}_{datetime.now(JST).strftime('%H%M%S')}{f.suffix}"
                shutil.move(str(f), str(dest))
    print(json.dumps({"ok": True, **res}, ensure_ascii=False, indent=None if args.json else 2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
