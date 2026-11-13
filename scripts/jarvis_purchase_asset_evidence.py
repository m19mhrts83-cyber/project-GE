#!/usr/bin/env python3
"""購入時・金融資産／借入残債の提出用スクショ収集（汎用）。

スキル: .cursor/skills/purchase-asset-evidence/SKILL.md
スラッシュ: /purchase-asset-evidence

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_purchase_asset_evidence.py \\
    --out '…/3.送信添付/YYYY-MM-DD_金融資産スクショ' --only all

秘密はチャットに出さない。対外送信はこのスクリプトの範囲外（了承後 yoritoori）。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from datetime import date
from pathlib import Path

OUT: Path = Path(".")
LOANS_JSON = Path(
    "/Users/matsunomasaharu2/Library/CloudStorage/OneDrive-個人用/240_融資/"
    "loan_tracker_export/loans.json"
)
REPO = Path(__file__).resolve().parents[1]
FINANCE = REPO / "215_kamiooya/C1_cursor/finance"
sys.path.insert(0, str(FINANCE))
sys.path.insert(0, str(REPO / "scripts"))

RESULTS: list[dict] = []
STEP_KEYS = (
    "loan",
    "paypay",
    "sbi_net",
    "axa",
    "sbi_sec",
    "bloomo",
    "akatsuki",
    "sony",
    "prudential",
)


def log(status: str, name: str, path: str = "", note: str = "") -> None:
    row = {"status": status, "name": name, "path": path, "note": note}
    RESULTS.append(row)
    print(f"[{status}] {name} {path} {note}".strip())


def shot_loan_tracker_from_json() -> None:
    """Render loans.json (loan-tracker export) to a printable HTML → PNG."""
    from playwright.sync_api import sync_playwright

    data = json.loads(LOANS_JSON.read_text(encoding="utf-8"))
    loans = data.get("loans") or []
    updated = data.get("updatedAt") or ""
    total = sum(int(L.get("balance") or 0) for L in loans)
    rows = []
    for L in loans:
        bal = int(L.get("balance") or 0)
        rows.append(
            "<tr>"
            f"<td>{L.get('name') or L.get('id') or ''}</td>"
            f"<td>{L.get('lender') or ''}</td>"
            f"<td>{L.get('borrower') or ''}</td>"
            f"<td style='text-align:right'>{bal:,}</td>"
            f"<td style='text-align:right'>{int(L.get('monthlyPayment') or 0):,}</td>"
            f"<td>{L.get('rate') or ''}</td>"
            "</tr>"
        )
    html = f"""<!doctype html><html lang=ja><head><meta charset=utf-8>
<title>借入残高一覧（残高チェッカー／イマザン）</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Hiragino Sans',sans-serif;margin:32px;color:#222}}
h1{{font-size:22px;margin:0 0 8px}}
.meta{{color:#555;margin-bottom:20px;font-size:13px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{border:1px solid #ccc;padding:8px 10px}}
th{{background:#f5f0e8;text-align:left}}
.total{{font-size:18px;font-weight:700;margin-top:16px}}
.badge{{display:inline-block;background:#6b4f2a;color:#fff;padding:4px 10px;border-radius:4px;font-size:12px}}
</style></head><body>
<span class=badge>借入残高トラッカー（イマザン）データ</span>
<h1>きょう時点の借入残高一覧</h1>
<div class=meta>出典: loan-tracker / imazan エクスポート（{LOANS_JSON.name}）<br>
as-of / updatedAt: {updated}<br>出力日: {date.today().isoformat()} / 件数: {len(loans)}</div>
<table>
<thead><tr><th>名称</th><th>金融機関</th><th>名義</th><th>残高（円）</th><th>月返済</th><th>金利</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
<div class=total>合計残高: {total:,} 円</div>
</body></html>"""
    tmp = OUT / "_loan_tracker_view.html"
    tmp.write_text(html, encoding="utf-8")
    dest = OUT / "05_借入残債_残高トラッカー.png"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.goto(tmp.as_uri())
        page.screenshot(path=str(dest), full_page=True)
        browser.close()
    log("ok", "loan_tracker", str(dest), f"total={total:,} from loans.json")


def capture_paypay() -> None:
    from playwright.sync_api import sync_playwright
    import jarvis_paypay_bank_transfer as pp_mod

    store = os.environ["PAYPAY_STORE_NO"]
    acct = os.environ["PAYPAY_ACCOUNT_NO"]
    pw = os.environ["PAYPAY_PASSWORD"]
    dest = OUT / "10_銀行_PayPay銀行_残高.png"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="ja-JP")
        page = context.new_page()
        page = pp_mod.login_with_retry(page, store, acct, pw)
        pp_mod.dismiss_privacy_modal(page)
        time.sleep(2)
        page.screenshot(path=str(dest), full_page=True)
        browser.close()
    log("ok", "paypay", str(dest))


def capture_sbi_net() -> None:
    from playwright.sync_api import sync_playwright
    import jarvis_sbi_net_transfer as sbi

    user = os.environ["SBI_NET_USER"]
    pw = os.environ["SBI_NET_LOGIN_PASSWORD"]
    dest = OUT / "10_銀行_ドコモSMTB_NEOBANK_残高.png"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_context(locale="ja-JP").new_page()
        # reuse login helpers if present
        if hasattr(sbi, "_fill_login"):
            # open login URL from module constants if any
            url = getattr(sbi, "LOGIN_URL", None) or getattr(sbi, "HOME_URL", None)
            if not url:
                url = "https://www.netbk.co.jp/contents/pages/wpl010101/i010101CT/DI01010200"
            page.goto(url, wait_until="domcontentloaded")
            time.sleep(2)
            sbi._fill_login(page, user, pw)
            # click login
            for sel in (
                "button:has-text('ログイン')",
                "input[type=submit]",
                "a:has-text('ログイン')",
            ):
                loc = page.locator(sel).first
                if loc.count():
                    try:
                        loc.click(timeout=3000)
                        break
                    except Exception:
                        pass
            time.sleep(5)
            page.screenshot(path=str(dest), full_page=True)
        else:
            raise RuntimeError("sbi login helper missing")
        browser.close()
    log("ok", "sbi_net", str(dest))


def capture_axa() -> None:
    import jarvis_axa_balance as axa

    dest = OUT / "20_保険_アクサ生命_積立金.png"
    # force save-debug then copy
    result = axa.fetch_axa_balance(headless=False, timeout_ms=60000, save_debug=True)
    src = Path.home() / "Library/Logs/jarvis_portfolio/debug/axa_last_page.png"
    if src.exists():
        shutil.copy2(src, dest)
        log("ok", "axa", str(dest), result.value_text)
    else:
        log("error", "axa", "", "debug png missing after fetch")


def capture_sbi_sec() -> None:
    import jarvis_sbi_index_balance as sbi

    dest = OUT / "30_証券_SBIインデックス_残高.png"
    result = sbi.fetch_sbi_balance(headless=False, timeout_ms=60000, save_debug=True)
    debug = Path(getattr(sbi, "DEBUG_DIR", Path.home() / "Library/Logs/jarvis_portfolio/debug"))
    src = debug / "sbi_last_page.png"
    if src.exists():
        shutil.copy2(src, dest)
        log("ok", "sbi_sec", str(dest), getattr(result, "value_text", str(result)))
    else:
        log("error", "sbi_sec", "", "sbi_last_page.png missing")


def capture_bloomo_mf() -> None:
    import jarvis_mf_bloomo_balance as bloomo

    dest = OUT / "31_証券_Bloomo_評価.png"
    # prefer fresh save-debug
    ap_like = type("A", (), {})()
    # call main path via fetch if available
    if hasattr(bloomo, "fetch_bloomo"):
        bloomo.fetch_bloomo(headless=False, save_debug=True)
    else:
        # run module style
        from playwright.sync_api import sync_playwright

        url = os.environ.get("MONEYFORWARD_BLOOMO_SHOW_URL") or ""
        if not url:
            log("skip", "bloomo", "", "MONEYFORWARD_BLOOMO_SHOW_URL empty")
            return
        # use existing ok shot if fresh fetch hard
        dbg = REPO / ".jarvis_state/mf_bloomo_debug/bloomo_ok.png"
        if dbg.exists():
            shutil.copy2(dbg, dest)
            log("ok", "bloomo", str(dest), "copied recent bloomo_ok (refresh preferred)")
            return
    src = REPO / ".jarvis_state/mf_bloomo_debug/bloomo_ok.png"
    if src.exists():
        shutil.copy2(src, dest)
        log("ok", "bloomo", str(dest))
    else:
        log("error", "bloomo", "", "no png")


def capture_akatsuki() -> None:
    dest = OUT / "40_外国債_あかつき_残高.png"
    # run existing script with save-debug via import
    sys.path.insert(0, str(FINANCE))
    import akatsuki_bond_balance as ak

    # Prefer API that screenshots
    if hasattr(ak, "fetch_balance"):
        try:
            ak.fetch_balance(headless=False, save_debug=True)
        except Exception as exc:
            log("warn", "akatsuki_fetch", "", str(exc)[:120])
    src = FINANCE / "debug/akatsuki_last_page.png"
    if src.exists():
        shutil.copy2(src, dest)
        log("ok", "akatsuki", str(dest), "from debug (refresh attempted)")
    else:
        log("error", "akatsuki", "", "png missing")


def capture_sony() -> None:
    dest_dir_patterns = [
        REPO / ".jarvis_state/mf_bloomo_debug",
        Path.home() / "Library/Logs/jarvis_portfolio/debug",
        FINANCE / "debug",
    ]
    # try live fetch
    try:
        sys.path.insert(0, str(FINANCE))
        # run via subprocess for isolation
        import subprocess

        env = os.environ.copy()
        cmd = [
            "/Users/matsunomasaharu2/selenium_env/venv/bin/python",
            str(FINANCE / "sony_life_surrender_value.py"),
            "--save-debug",
        ]
        subprocess.run(cmd, cwd=str(FINANCE), env=env, timeout=180)
    except Exception as exc:
        log("warn", "sony_fetch", "", str(exc)[:120])
    # copy any recent sony pngs
    found = list((REPO / ".jarvis_state/mf_bloomo_debug").glob("sony_life_*.png"))
    found += list((Path.home() / "Library/Logs/jarvis_portfolio/debug").glob("sony*.png"))
    found += list((FINANCE / "debug").glob("sony*.png")) if (FINANCE / "debug").exists() else []
    found = sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)
    if not found:
        log("skip", "sony", "", "no png / may be service down")
        return
    # copy up to 3 distinct account shots
    used = 0
    for src in found:
        if used >= 3:
            break
        if "nav_fail" in src.name:
            continue
        dest = OUT / f"20_保険_ソニー生命_{src.stem}.png"
        shutil.copy2(src, dest)
        log("ok", f"sony_{used}", str(dest))
        used += 1


def capture_prudential() -> None:
    dest = OUT / "20_保険_プルデンシャル_評価.png"
    try:
        import subprocess

        cmd = [
            "/Users/matsunomasaharu2/selenium_env/venv/bin/python",
            str(FINANCE / "prudential_life_surrender_value.py"),
            "--save-debug",
        ]
        subprocess.run(cmd, cwd=str(FINANCE), env=os.environ.copy(), timeout=180)
    except Exception as exc:
        log("warn", "prudential_fetch", "", str(exc)[:120])
    found = list((FINANCE / "debug").glob("prudential*.png")) if (FINANCE / "debug").exists() else []
    found += list((Path.home() / "Library/Logs/jarvis_portfolio/debug").glob("prudential*.png"))
    found = sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)
    if found:
        shutil.copy2(found[0], dest)
        log("ok", "prudential", str(dest))
    else:
        # write value note image via html
        from playwright.sync_api import sync_playwright

        v = os.environ.get("PRUDENTIAL_VALUE_JPY") or ""
        vc = os.environ.get("PRUDENTIAL_CHIKAGE_VALUE_JPY") or ""
        html = f"""<!doctype html><html lang=ja><meta charset=utf-8>
<style>body{{font-family:sans-serif;margin:40px}}h1{{font-size:20px}}</style>
<body><h1>プルデンシャル生命（評価メモ）</h1>
<p>Web自動取得は無効／未成功のため、正本 env の評価額を記載。</p>
<p>真治: {int(v):,} 円</p>
<p>千景: {int(vc):,} 円</p>
<p>取得日メモ: {date.today().isoformat()}</p>
<p>※可能ならマイページ画面の手撮影に差し替え推奨</p>
</body></html>"""
        tmp = OUT / "_prudential_note.html"
        tmp.write_text(html, encoding="utf-8")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(tmp.as_uri())
            page.screenshot(path=str(dest), full_page=True)
            browser.close()
        log("ok", "prudential", str(dest), "env value note (replace if live shot available)")


def _write_inventory() -> None:
    lines = [
        f"提出用スクショ一覧（{date.today().isoformat()}）",
        "",
        "成功・提出候補:",
    ]
    skips: list[str] = []
    for row in RESULTS:
        line = f"- [{row['status']}] {row['name']}: {row.get('path') or '-'} {row.get('note') or ''}".rstrip()
        if row["status"] in ("skip", "error"):
            skips.append(line)
        else:
            lines.append(line)
    if skips:
        lines += ["", "スキップ／エラー（送付対象外・_skip_内部用へ移すこと）:", *skips]
    (OUT / "_提出用一覧.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    global OUT, LOANS_JSON
    ap = argparse.ArgumentParser(description="購入時・金融資産／残債エビデンス収集")
    ap.add_argument(
        "--out",
        required=True,
        help="出力ディレクトリ（…/3.送信添付/YYYY-MM-DD_金融資産スクショ）",
    )
    ap.add_argument(
        "--only",
        default="all",
        help=f"カンマ区切りステップ。all または {','.join(STEP_KEYS)}",
    )
    ap.add_argument(
        "--loans-json",
        default=str(LOANS_JSON),
        help="loan-tracker エクスポート JSON",
    )
    args = ap.parse_args()
    OUT = Path(args.out).expanduser().resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "_skip_内部用").mkdir(exist_ok=True)
    LOANS_JSON = Path(args.loans_json).expanduser()

    steps = {
        "loan": shot_loan_tracker_from_json,
        "paypay": capture_paypay,
        "sbi_net": capture_sbi_net,
        "axa": capture_axa,
        "sbi_sec": capture_sbi_sec,
        "bloomo": capture_bloomo_mf,
        "akatsuki": capture_akatsuki,
        "sony": capture_sony,
        "prudential": capture_prudential,
    }
    raw = [x.strip() for x in args.only.split(",") if x.strip()]
    order = list(steps.keys()) if "all" in raw else raw
    for key in order:
        if key not in steps:
            log("error", key, "", "unknown step")
            continue
        try:
            steps[key]()
        except Exception as exc:
            log("error", key, "", str(exc)[:200])

    summary = OUT / "_capture_summary.json"
    summary.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_inventory()
    print("SUMMARY", summary)
    ok = sum(1 for r in RESULTS if r["status"] == "ok")
    print(f"done ok={ok} total_rows={len(RESULTS)} out={OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
