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
import subprocess
import hashlib
import sys
import time
from datetime import date, datetime, timezone
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
CAPTURE_STARTED: str = ""
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


def log(status: str, name: str, path: str = "", note: str = "", *, fresh_screen: bool = False) -> None:
    row = {"status": status, "name": name, "path": path, "note": note, "fresh_screen": fresh_screen}
    RESULTS.append(row)
    print(f"[{status}] {name}")


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
    log("reference", "loan_tracker", str(dest), "derived_export_not_institution_screen")


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
    log("candidate", "paypay", str(dest), fresh_screen=True)


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
    log("candidate", "sbi_net", str(dest), fresh_screen=True)


def _copy_fresh(src: Path, dest: Path, name: str) -> None:
    from jarvis_asset_618_runtime import timestamp, Blocked
    if not src.is_file() or src.is_symlink() or datetime.fromtimestamp(src.stat().st_mtime, timezone.utc) < timestamp(CAPTURE_STARTED):
        raise Blocked('fresh_debug_image_missing')
    shutil.copy2(src, dest)
    log('candidate', name, str(dest), 'identity_and_date_review_required', fresh_screen=True)


def _run_collector(script: Path, extra: list[str] | None = None) -> dict:
    from jarvis_asset_618_runtime import Blocked
    result = subprocess.run([sys.executable, str(script), '--save-debug', '--json', *(extra or [])],
                            cwd=str(script.parent), env=os.environ.copy(), capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise Blocked('collector_failed_no_old_image_fallback')
    try:
        data = json.loads(result.stdout)
        if not isinstance(data, dict) or data.get('status') in ('error','skipped') or data.get('value_jpy') is None:
            raise ValueError()
        return data
    except (ValueError,TypeError):
        raise Blocked('collector_did_not_confirm_value') from None


def capture_axa() -> None:
    import jarvis_axa_balance as axa
    axa.fetch_axa_balance(headless=False, timeout_ms=60000, save_debug=True)
    _copy_fresh(axa.DEBUG_DIR / 'axa_last_page.png', OUT / '20_保険_アクサ生命_積立金.png', 'axa')


def capture_sbi_sec() -> None:
    import jarvis_sbi_index_balance as sbi
    sbi.fetch_sbi_balance(headless=False, timeout_ms=60000, save_debug=True)
    _copy_fresh(sbi.DEBUG_DIR / 'sbi_last_page.png', OUT / '30_証券_SBIインデックス_残高.png', 'sbi_sec')


def capture_bloomo_mf() -> None:
    _run_collector(REPO / 'scripts/jarvis_mf_bloomo_balance.py')
    _copy_fresh(REPO / '.jarvis_state/mf_bloomo_debug/bloomo_ok.png', OUT / '31_証券_Bloomo_評価.png', 'bloomo')


def capture_akatsuki() -> None:
    import akatsuki_bond_balance as ak
    ak.fetch_bond_balance(headless=False,timeout_ms=60000,save_debug=True,
                          allow_bond_nav_skip=False,env_file=FINANCE / '.env.akatsuki')
    _copy_fresh(ak.DEFAULT_DEBUG_DIR / 'akatsuki_last_page.png', OUT / '40_外国債_あかつき_残高.png', 'akatsuki')


def _copy_contract_candidates(prefix: str, pattern: str) -> None:
    from jarvis_asset_618_runtime import Blocked, timestamp
    from jarvis_asset_618_runtime import ROOT
    roots = [FINANCE/'debug', ROOT/'debug']
    found = {p.resolve() for root in roots for p in root.glob(pattern)
             if p.is_file() and not p.is_symlink() and datetime.fromtimestamp(p.stat().st_mtime,timezone.utc) >= timestamp(CAPTURE_STARTED)}
    if not found:
        raise Blocked('fresh_contract_capture_missing')
    for src in sorted(found):
        key=hashlib.sha256(src.name.encode()).hexdigest()[:12]
        _copy_fresh(src, OUT/f'20_保険_{prefix}_{key}.png', f'{prefix}_{key}')


def capture_sony() -> None:
    _run_collector(FINANCE/'sony_life_surrender_value.py')
    _copy_contract_candidates('sony','sony_life_last_page_account*_row*.png')


def capture_prudential() -> None:
    _run_collector(FINANCE/'prudential_life_surrender_value.py',['--no-fetch-otp-gmail'])
    _copy_contract_candidates('prudential','prudential_life_last_page_account*.png')


def _write_inventory() -> None:
    lines = [
        f"提出用スクショ一覧（{date.today().isoformat()}）",
        "",
        "取得候補（正常証拠の確定前。契約・基準日の確認が必要）:",
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


def _collect_main(args, run) -> int:
    global OUT, LOANS_JSON, CAPTURE_STARTED
    RESULTS.clear()
    artifacts = []
    OUT = Path(args.out).expanduser().resolve()
    if any((parent / ".git").exists() for parent in (OUT, *OUT.parents)):
        raise ValueError("capture_output_must_be_outside_git")
    OUT.mkdir(parents=True, exist_ok=True, mode=0o700)
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
    order = run.allowed
    for key in order:
        if key not in steps:
            log("error", key, "", "unknown step")
            continue
        before = len(RESULTS)
        CAPTURE_STARTED = datetime.now(timezone.utc).isoformat()
        if key in ('paypay','sbi_net','axa','akatsuki','sony','prudential') and getattr(args,'executor','codex') != 'jarvis':
            log('skip',key,'','jarvis_only_bank_ib_or_otp_capable_collector')
            run.data['results'][key] = 'skipped'
            run.persist()
            continue
        try:
            steps[key]()
        except Exception:
            log("error", key, "", "capture_failed")
        rows = RESULTS[before:]
        from jarvis_asset_618_evidence import capture_receipt
        finished = datetime.now(timezone.utc).isoformat()
        for row in rows:
            if row.get('path') and row.get('status') in ('ok','candidate','reference'):
                try:
                    artifact = capture_receipt(Path(row['path']), run_id=run.data['run_id'], step=key,
                        started_at=CAPTURE_STARTED, finished_at=finished, fresh_screen=row.get('fresh_screen') is True)
                    row['artifact_index'] = len(artifacts)
                    artifacts.append(artifact)
                except Exception:
                    row['status'] = 'error'
                    row['note'] = 'capture_receipt_invalid'
        statuses = {r.get("status") for r in rows}
        # Existing legacy capture can copy old debug images or create transfer notes.
        # Candidates remain references until their identity/date review and Storage readback pass.
        status = "error" if "error" in statuses else "skipped" if "skip" in statuses or "skipped" in statuses else "reference"
        run.data["results"][key] = status
        run.persist()

    from jarvis_asset_618_runtime import current_metadata, atomic_json
    atomic_json(OUT / "_capture_receipts.json", {"artifacts": artifacts})
    (OUT / "_asset618_run.json").write_text(json.dumps(current_metadata(), ensure_ascii=False, indent=2), encoding="utf-8")
    summary = OUT / "_capture_summary.json"
    summary.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_inventory()
    print("SUMMARY", summary)
    ok = sum(1 for r in RESULTS if r["status"] == "ok")
    print(f"done ok={ok} total_rows={len(RESULTS)} out={OUT}")
    return 1 if any(v == "error" for v in run.data["results"].values()) else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="購入時・金融資産／残債エビデンス収集")
    ap.add_argument(
        "--out",
        default=str(Path.home() / "Library/Logs/jarvis_portfolio/asset618-capture/latest"),
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
    ap.add_argument("--executor", choices=("codex","jarvis","misslemon","friday"), default="codex")
    ap.add_argument("--run-id", help="Reserved UUID for an explicit once-only decision")
    ap.add_argument("--retry-run")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    from jarvis_asset_618_runtime import Run, Busy, Blocked, retry_targets, current_metadata
    from jarvis_portfolio_weekly import load_private_env, sb_client
    try:
        if args.retry_run and args.only != 'all':
            raise Blocked('choose_one_scope')
        targets = (retry_targets(args.retry_run, 'evidence') if args.retry_run else
                   list(STEP_KEYS) if args.only == 'all' else args.only.split(','))
        if not targets or any(x not in STEP_KEYS for x in targets):
            raise Blocked('unknown_or_empty_target_scope')
        load_private_env()
        client = None if args.dry_run else sb_client()
        with Run('evidence', targets, client, preview=args.dry_run, retry_of=args.retry_run, run_id=args.run_id) as run:
            if args.dry_run:
                print(json.dumps({'preview': True, 'target_ids': run.allowed, **current_metadata()}))
                return 0
            if not run.allowed:
                print('# no executable targets'); return 2
            return _collect_main(args, run)
    except (Busy, Blocked) as exc:
        print('# asset618: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
