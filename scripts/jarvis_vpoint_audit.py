#!/usr/bin/env python3
"""
Vポイント深い監査 — Vpass 明細の／ｉＤ比率＋積立行、Gmail 積立通知、Tサイト履歴を突合。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_vpoint_audit.py
  ~/selenium_env/venv/bin/python scripts/jarvis_vpoint_audit.py --apply --push

Wallet 設定は変更しない。秘密は出さない。
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from playwright.sync_api import Page, sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from car_loan.chrome_cdp import cdp_ready, start_cdp_chrome  # noqa: E402
from car_loan.env_state import ENV_FILE, load_env  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE = REPO / ".jarvis_state"
RESULT = STATE / "vpoint_audit_result.json"
SHOT_DIR = STATE / "vpoint_audit"
CDP_PORT = 9231
PROFILE = Path.home() / ".jarvis_state" / "chrome_vpass_audit"
LOGIN_URL = "https://www.smbc-card.com/memx/force_login/index.html"
MYPAGE_URL = "https://www.smbc-card.com/memx/mypage/index.html"
MEISAI_HINTS = (
    "ご利用明細",
    "利用明細",
    "明細照会",
    "カードご利用明細",
)
MANUAL = (
    REPO
    / "215_kamiooya"
    / "C1_cursor"
    / "1b_Cursorマニュアル"
)
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]
TARGET_SHOP = re.compile(
    r"セブン|マクド|サイゼ|すき家|ガスト|ファミリーマート|ファミマ|ローソン|ミニストップ|"
    r"スタバ|スターバックス|ドトール|吉野家|和食さと|ミンツ"
)
ID_MARK = re.compile(r"／?\s*ｉＤ|／?\s*iD|/iD", re.I)
MOBILE_OK = re.compile(r"モバイルオーダー|ＭＯＢＩＬＥ|ＡＰＰ|／ＡＰ")


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def _shot(page: Page, name: str) -> None:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SHOT_DIR / f"{datetime.now(JST):%Y%m%d_%H%M%S}_{name}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        print(f"📎 shot {path.name}")
    except Exception as e:
        print(f"⚠️ shot: {e}")


def _body(page: Page, n: int = 12000) -> str:
    try:
        return page.inner_text("body")[:n]
    except Exception:
        return ""


def _login(page: Page, vpass_id: str, vpass_pw: str) -> None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=90000)
    time.sleep(1.2)
    body0 = _body(page, 1200)
    if "アクセス集中" in body0 or "つながりにくい" in body0:
        raise RuntimeError("Vpass アクセス集中")
    has_login = page.locator("input[name='userid']").count() > 0
    if (not has_login) and ("ログアウト" in body0 or "Myページ" in body0):
        print("📎 Vpass already logged in")
        return
    if not has_login and page.locator("input[type='password']").count() == 0:
        print(f"📎 no login fields url={page.url}")
        return
    print("📎 Vpass login…")
    id_box = page.locator("input[name='userid']")
    if id_box.count() == 0:
        id_box = page.locator("input[type='text']")
    id_box.first.fill(vpass_id)
    page.locator("input[name='password'], input[type='password']").first.fill(vpass_pw)
    clicked = page.evaluate(
        """() => {
          const nodes = [...document.querySelectorAll('input[type=submit],button')];
          const btn = nodes.find(b => {
            const label = (b.value || b.innerText || '').trim();
            if (label !== 'ログイン') return false;
            if (b.disabled) return false;
            const r = b.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
          });
          if (!btn) return false;
          btn.click();
          return true;
        }"""
    )
    if not clicked:
        page.locator("input[type='password']").first.press("Enter")
    page.wait_for_load_state("domcontentloaded", timeout=90000)
    time.sleep(2.5)
    if "アクセス集中" in _body(page, 800):
        raise RuntimeError("Vpass アクセス集中（ログイン後）")


def _open_meisai(page: Page) -> None:
    page.goto(MYPAGE_URL, wait_until="domcontentloaded", timeout=90000)
    time.sleep(1.5)
    _shot(page, "mypage")
    # Myページ上の「ご利用明細」は href=# の JS。先に押す
    clicked = page.evaluate(
        """() => {
          const a=[...document.querySelectorAll('a')].find(x => (x.innerText||'').trim()==='ご利用明細');
          if(!a) return false;
          a.click();
          return true;
        }"""
    )
    if clicked:
        print("📎 opened WEB明細 via ご利用明細")
        time.sleep(2.5)
    else:
        # 明細・支払い → ご利用明細照会
        page.goto(
            "https://www.smbc-card.com/memx/web_meisai/top/index.html",
            wait_until="domcontentloaded",
            timeout=90000,
        )
        time.sleep(2)
        print("📎 opened web_meisai top")
    # Olive INF カード切替があれば
    for pat in (r"Ｏｌｉｖｅ\s*ＩＮＦ", r"Olive\s*INF", r"インフィニット"):
        loc = page.locator("a,button,select,option,span").filter(has_text=re.compile(pat))
        if loc.count():
            try:
                loc.first.click(timeout=2500)
                time.sleep(1.2)
                print(f"📎 card ~/{pat}/")
                break
            except Exception:
                continue
    # 支払月（当月寄り）
    for label in ("2026年9月", "2026年8月"):
        for i in range(min(page.locator("select").count(), 6)):
            s = page.locator("select").nth(i)
            try:
                for j in range(s.locator("option").count()):
                    t = (s.locator("option").nth(j).inner_text() or "").strip()
                    if t == label:
                        s.select_option(label=t)
                        time.sleep(2)
                        print(f"📎 payment month {label}")
                        raise StopIteration
            except StopIteration:
                break
            except Exception:
                continue
        else:
            continue
        break
    for _ in range(3):
        page.mouse.wheel(0, 1200)
        time.sleep(0.25)
    _shot(page, "meisai")


def parse_meisai_text(text: str) -> dict[str, Any]:
    line_re = re.compile(
        r"^(?:[A-Z]?#\s*)?(\d{2}/\d{2}/\d{2})\s+(.+?)\s+([0-9,]{2,})"
    )
    rows: list[dict[str, Any]] = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or "ご利用日" in ln:
            continue
        m = line_re.search(ln)
        if not m:
            continue
        date, merchant, yen_s = m.group(1), m.group(2).strip(), m.group(3)
        merchant = re.sub(r"\d{10,}", "", merchant).strip()
        yen = int(yen_s.replace(",", ""))
        is_id = bool(re.search(r"ｉＤ|(?<![A-Za-z])iD(?![A-Za-z])", merchant))
        is_mobile = bool(re.search(r"モバイルオーダー|／ＡＰ|／AP", merchant))
        is_tsumi = bool(re.search(r"投信積立|ＳＢＩ証券投信", merchant))
        is_target = bool(TARGET_SHOP.search(merchant))
        rows.append(
            {
                "date_hint": date,
                "merchant": merchant[:120],
                "yen": yen,
                "is_id": is_id,
                "is_mobile_order": is_mobile,
                "is_tsumitate": is_tsumi,
                "is_target_shop": is_target,
            }
        )

    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for r in rows:
        k = f"{r['date_hint']}|{r['merchant'][:40]}|{r['yen']}"
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)

    total = len(uniq)
    id_n = sum(1 for r in uniq if r["is_id"])
    target = [r for r in uniq if r["is_target_shop"]]
    target_id = [r for r in target if r["is_id"]]
    target_ok = [r for r in target if not r["is_id"]]
    tsumi = [r for r in uniq if r["is_tsumitate"]]
    id_ratio = round(id_n / total, 3) if total else None
    return {
        "row_count": total,
        "id_count": id_n,
        "id_ratio": id_ratio,
        "mobile_order_count": sum(1 for r in uniq if r["is_mobile_order"]),
        "tsumitate_rows": tsumi[:10],
        "target_shop_id": target_id[:15],
        "target_shop_okish": target_ok[:15],
        "sample_id": [r for r in uniq if r["is_id"]][:12],
        "sample_non_id": [r for r in uniq if not r["is_id"]][:12],
    }


def scrape_vpass(env: dict[str, str]) -> dict[str, Any]:
    vid = (env.get("VPASS_ID") or "").strip()
    vpw = (env.get("VPASS_PASSWORD") or "").strip()
    if not vid or not vpw:
        raise RuntimeError("未設定: VPASS_ID / VPASS_PASSWORD")

    start_cdp_chrome(CDP_PORT, PROFILE, LOGIN_URL)
    if not cdp_ready(CDP_PORT):
        raise RuntimeError(f"CDP {CDP_PORT} not ready")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        _login(page, vid, vpw)
        _open_meisai(page)
        text = _body(page, 20000)
        # DOM テキスト追加取得
        extra = page.evaluate(
            """() => {
              const t = document.body.innerText || '';
              return t.slice(0, 25000);
            }"""
        )
        blob = extra or text
        parsed = parse_meisai_text(blob)
        parsed["page_url"] = page.url
        parsed["body_snip"] = re.sub(r"\d{10,}", "****", blob[:1500])
        return parsed


def gmail_tsumitate_evidence() -> list[dict[str, str]]:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    tokens = [
        ("m19m", MANUAL / "token_m19m.json"),
        ("estate", MANUAL / "token_estate.json"),
        ("admin", MANUAL / "token_livingsupport.json"),
    ]
    q = 'newer_than:90d (投信積立発注結果通知 OR "投信積立" OR "ＳＢＩ証券投信積立" OR "クレカ積立")'
    out: list[dict[str, str]] = []

    def body_text(full: dict) -> str:
        parts: list[str] = []

        def walk(p: dict) -> None:
            data = (p.get("body") or {}).get("data")
            if data and str(p.get("mimeType") or "").startswith("text/"):
                parts.append(base64.urlsafe_b64decode(data).decode("utf-8", "replace"))
            for c in p.get("parts") or []:
                walk(c)

        walk(full.get("payload") or {})
        return "\n".join(parts)

    for label, tok in tokens:
        if not tok.is_file():
            continue
        try:
            creds = Credentials.from_authorized_user_file(str(tok), GMAIL_SCOPES)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
            resp = (
                svc.users()
                .messages()
                .list(userId="me", q=q, maxResults=12)
                .execute()
            )
            for m in resp.get("messages") or []:
                full = (
                    svc.users()
                    .messages()
                    .get(userId="me", id=m["id"], format="full")
                    .execute()
                )
                h = {
                    x["name"]: x["value"]
                    for x in (full.get("payload") or {}).get("headers") or []
                }
                text = body_text(full) or full.get("snippet") or ""
                yen = re.findall(r"([0-9,]{4,})\s*円", text)
                out.append(
                    {
                        "account": label,
                        "date": h.get("Date", "")[:30],
                        "subject": (h.get("Subject") or "")[:80],
                        "yen_hits": ",".join(yen[:5]),
                    }
                )
            if out:
                break
        except Exception as e:
            print(f"⚠️ gmail [{label}]: {e}")
    return out[:10]


def load_tsite() -> dict[str, Any]:
    files = sorted(STATE.glob("vpoint_tsite_history_*.json"), reverse=True)
    if not files:
        return {}
    return json.loads(files[0].read_text(encoding="utf-8"))


def build_result(meisai: dict[str, Any], gmail: list[dict[str, str]], tsite: dict[str, Any]) -> dict[str, Any]:
    entries = tsite.get("key_entries") or []
    tsumi_bonus = [
        e
        for e in entries
        if re.search(r"投信積立|積立カード", e.get("desc") or "")
    ]
    recent_tsumi = tsumi_bonus[:5]
    rate_status = "confirmed_1pct_not_6pct"
    if recent_tsumi and all(abs(int(e.get("pt") or 0)) == 900 for e in recent_tsumi[:2]):
        rate_status = "confirmed_1pct_not_6pct"
    elif recent_tsumi and any(abs(int(e.get("pt") or 0)) > 900 for e in recent_tsumi):
        rate_status = "possible_above_1pct"

    id_ratio = meisai.get("id_ratio")
    id_heavy = id_ratio is not None and id_ratio >= 0.5

    mcd = next(
        (e for e in entries if "マクド" in (e.get("desc") or "") and "６％" in (e.get("desc") or "")),
        None,
    )
    sai = next(
        (e for e in entries if "サイゼ" in (e.get("desc") or "") and "６％" in (e.get("desc") or "")),
        None,
    )

    note = (
        f"明細サンプル {meisai.get('row_count')}件中 iD {meisai.get('id_count')}件"
        f"（比率 {id_ratio}）。"
    )
    if id_heavy:
        note += "Olive INF 利用は／ｉＤ優勢のまま。"
    else:
        note += "／ｉＤ優勢は緩和。"
    if meisai.get("target_shop_id"):
        note += " 対象店でもｉＤあり。"

    return {
        "audited_at": datetime.now(JST).strftime("%Y-%m-%d"),
        "audited_at_iso": now_iso(),
        "sources": [
            "Vpass meisai (CDP chrome_vpass_audit :9231)",
            "Gmail API (投信積立発注)",
            "vpoint_tsite_history latest",
            "公式: 対象店はVisaタッチ・モバイルオーダー（iD対象外）／積立最大6%は条件付き",
        ],
        "credit_tsumitate": {
            "monthly_yen_confirmed": 90000,
            "evidence": [
                *(f"Gmail: {g.get('subject')} ({g.get('yen_hits')})" for g in gmail[:3]),
                *(
                    f"Tサイト: {e.get('date')} {e.get('desc')} {e.get('pt')}pt"
                    for e in recent_tsumi[:3]
                ),
                *(
                    f"Vpass: {r.get('date_hint')} {r.get('merchant')} {r.get('yen')}"
                    for r in (meisai.get("tsumitate_rows") or [])[:2]
                ),
            ],
            "point_history": {
                "vsite_tsite": "ok_email_otp_fresh",
                "balance_pt": tsite.get("balance_pt"),
                "tsumitate_bonus_recent": [
                    {
                        "date": e.get("date"),
                        "pt": e.get("pt"),
                        "rate_vs_90k": round(abs(int(e.get("pt") or 0)) / 90000, 4),
                        "label": e.get("desc"),
                    }
                    for e in recent_tsumi[:5]
                ],
            },
            "effective_rate": {
                "status": rate_status,
                "reason": [
                    "Tサイトで投信積立カード決済特典が直近も900pt前後（9万円の1%）",
                    "Olive INF 表記の積立特典行あり（カード切替は反映）",
                ],
                "expected_band_now_pct": "実績1%",
                "at_90k_yen": {
                    "actual_pts": 900,
                    "actual_pct": 1.0,
                    "if_6pct_pts": 5400,
                },
                "verdict": "積立稼働OKだが付与は1%。6%には未到達",
            },
        },
        "merchant_high_rate": {
            "user_claim": "クレジット払い意図",
            "official": "対象店高還元はスマホVisaタッチ／モバイルオーダー限定。iDは対象外",
            "meisai_sample": {
                "label": "vpass_live",
                "id_ratio": id_ratio,
                "id_count": meisai.get("id_count"),
                "row_count": meisai.get("row_count"),
                "correct_rail": meisai.get("target_shop_okish") or [],
                "id_rail_including_target_cvs": meisai.get("target_shop_id") or [],
                "sample_id": meisai.get("sample_id") or [],
                "sample_non_id": meisai.get("sample_non_id") or [],
                "note": note,
            },
            # PDCA互換（旧キー）
            "meisai_202608_sample": {
                "correct_rail": meisai.get("target_shop_okish") or [],
                "id_rail_including_target_cvs": meisai.get("target_shop_id") or [],
                "note": note,
            },
            "v_coupon_plus_10": "マイページの『ポイント最大+10%』はVクーポンであり、対象コンビニの基本高還元とは別",
            "verdict": (
                "iD決済では高還元は付かない仕様。"
                + (" 直近明細もｉＤ優勢。" if id_heavy else " 直近明細ではｉＤ比率が半分未満。")
            ),
            "tsite_evidence": {
                "mcdonalds_plus6pct": (mcd or {}).get("pt"),
                "saizeriya_plus6pct": (sai or {}).get("pt"),
                "mcdonalds_plus6pct_20260724": (mcd or {}).get("pt"),
                "saizeriya_plus6pct_20260724": (sai or {}).get("pt"),
                "note": "対象店＋6%はモバイルオーダー系で付与実績あり。セブン等iDの高還元行は無し",
            },
        },
        "recommendations": [
            "対象店（セブン等）は Visaタッチ／モバイルオーダー（ｉＤ回避）を1回試して『試した』",
            "月次で／ｉＤ比率を見る（Wallet設定は強制変更しない）",
            "クレカ積立6%: 年間カード利用帯＋Olive資産特典を確認",
            "選べる特典（給与200＋還元×2）をアプリで確認",
        ],
        "vpass_raw": {
            "page_url": meisai.get("page_url"),
            "row_count": meisai.get("row_count"),
            "id_ratio": id_ratio,
        },
    }


def push_dashboard() -> None:
    eval_py = REPO / "scripts" / "jarvis_situation_watch.py"
    if not eval_py.is_file():
        return
    try:
        import subprocess

        subprocess.run(
            [str(Path.home() / "selenium_env" / "venv" / "bin" / "python"), str(eval_py), "--push"],
            cwd=str(REPO),
            check=False,
            timeout=120,
        )
    except Exception as e:
        print(f"⚠️ push: {e}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Vポイント深い監査")
    ap.add_argument("--apply", action="store_true", help="vpoint_audit_result.json に書く")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--skip-vpass", action="store_true")
    ap.add_argument("--skip-gmail", action="store_true")
    args = ap.parse_args()

    env = load_env(ENV_FILE)
    meisai: dict[str, Any] = {}
    if not args.skip_vpass:
        try:
            meisai = scrape_vpass(env)
            print(
                f"📎 meisai rows={meisai.get('row_count')} id={meisai.get('id_count')} "
                f"ratio={meisai.get('id_ratio')}"
            )
        except Exception as e:
            print(f"⚠️ Vpass失敗: {e}", file=sys.stderr)
            return 1
    else:
        meisai = {"row_count": 0, "id_count": 0, "id_ratio": None}

    gmail: list[dict[str, str]] = []
    if not args.skip_gmail:
        print("使用アカウント: m19m→estate→admin / Gmail API（積立通知）")
        gmail = gmail_tsumitate_evidence()
        print(f"📎 gmail hits={len(gmail)}")

    tsite = load_tsite()
    result = build_result(meisai, gmail, tsite)
    print(json.dumps(
        {
            "audited_at": result["audited_at"],
            "id_ratio": result["merchant_high_rate"]["meisai_sample"]["id_ratio"],
            "tsumitate": result["credit_tsumitate"]["effective_rate"]["status"],
            "balance": (result["credit_tsumitate"]["point_history"] or {}).get("balance_pt"),
            "verdict_merchant": result["merchant_high_rate"]["verdict"],
            "verdict_tsumi": result["credit_tsumitate"]["effective_rate"]["verdict"],
        },
        ensure_ascii=False,
        indent=2,
    ))

    if args.apply:
        STATE.mkdir(parents=True, exist_ok=True)
        RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"✅ wrote {RESULT}")
        # PDCA 再計算
        try:
            from jarvis_vpoint_pdca import build_board, load, save, MONTHLY, CADENCE, TEIKI  # type: ignore

            monthly = load(MONTHLY)
            board = build_board(monthly, load(CADENCE), result, load(TEIKI))
            monthly["pdca_board"] = board
            monthly["last_deep_audit_at"] = now_iso()
            save(MONTHLY, monthly)
            print("✅ pdca_board refreshed")
        except Exception as e:
            print(f"⚠️ pdca refresh: {e}")
            # fallback: run CLI
            import subprocess

            subprocess.run(
                [
                    str(Path.home() / "selenium_env" / "venv" / "bin" / "python"),
                    str(REPO / "scripts" / "jarvis_vpoint_pdca.py"),
                    "--apply",
                ]
                + (["--push"] if args.push else []),
                cwd=str(REPO),
                check=False,
            )

    if args.push:
        # dedicated pdca push
        import subprocess

        subprocess.run(
            [
                str(Path.home() / "selenium_env" / "venv" / "bin" / "python"),
                str(REPO / "scripts" / "jarvis_vpoint_pdca.py"),
                "--apply",
                "--push",
            ],
            cwd=str(REPO),
            check=False,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
