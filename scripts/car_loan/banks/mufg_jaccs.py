"""三菱UFJ / JACCS（mncollect）アダプタ。"""
from __future__ import annotations

import re
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from ..chrome_cdp import start_cdp_chrome
from ..env_state import load_env, load_state, receipt_from_state, update_application_status
from ..upload_flow import (
    UploadFlowConfig,
    UploadSelectors,
    resolve_documents,
    run_upload_flow,
)
from .registry import expand_path, load_bank_config


def _credential(cfg: dict, env: dict, state: dict) -> tuple[str, str]:
    cred = cfg["credentials"]
    receipt = env.get(cred.get("receipt_env", ""), "") or receipt_from_state(
        cred["state_app_id"], env, state
    )
    password = env.get(cred.get("password_env", ""), "")
    return receipt, password


def upload_url(cfg: dict, receipt: str) -> str:
    tpl = cfg["entry"]["upload_url_template"]
    return tpl.format(receipt=receipt)


def open_jaccs_documents_guide(port: int, receipt: str, password: str) -> None:
    """ログイン＋書類提出案内ポップアップ（--documents 用）。"""
    from ..chrome_cdp import cdp_ready

    cfg = load_bank_config("mufg_jaccs")
    login_url = cfg["entry"]["jaccs_login_url"]
    popup_js = cfg["entry"]["guide_popup_js"]

    if not cdp_ready(port):
        start_cdp_chrome(port, expand_path(cfg["chrome_profile"]), login_url)

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context(locale="ja-JP")
        page = _find_jaccs_main(ctx)
        _jaccs_login_if_needed(page, login_url, receipt, password)
        for p in ctx.pages:
            if "書類提出" in p.title() or "書類提出案内" in p.inner_text("body")[:300]:
                print(f"✅ 既存タブの書類提出案内: {p.title()}")
                return
        with page.expect_popup(timeout=20000) as popup_info:
            page.evaluate(popup_js)
        popup = popup_info.value
        popup.wait_for_load_state("domcontentloaded", timeout=30000)
        print(f"✅ 書類提出案内: {popup.title()} / {popup.url}")


def _find_jaccs_main(ctx):
    for p in ctx.pages:
        if "ecredit.jaccs.co.jp/bank/Service" in p.url and "BWFLoginDL" not in p.url:
            return p
    for p in ctx.pages:
        if "BWFLoginDL" in p.url:
            return p
    return ctx.pages[0] if ctx.pages else ctx.new_page()


def _jaccs_login_if_needed(page: Page, login_url: str, receipt: str, password: str) -> None:
    login_input = page.locator('input[name="IUSERID"][type="text"]')
    if login_input.count() == 0 and "BWFLoginDL" in page.url:
        page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
        login_input = page.locator('input[name="IUSERID"][type="text"]')
    if login_input.count() > 0:
        login_input.fill(receipt)
        page.locator('input[name="IPASSWORD"]').fill(password)
        page.locator('img[alt="ログイン"]').click()
        page.wait_for_load_state("domcontentloaded", timeout=60000)
        time.sleep(1)


def extract_upload_url_from_guide(page: Page) -> str | None:
    html = page.content()
    m = re.search(r"doOpenExternalLink\('([^']+)'", html)
    if not m:
        return None
    return m.group(1).replace("&amp;", "&")


def _flow_from_config(cfg: dict) -> UploadFlowConfig:
    sel = cfg.get("selectors", {})
    return UploadFlowConfig(
        pre_pages=list(cfg["flow"].get("pre_pages", [])),
        upload_page=cfg["flow"]["upload_page"],
        confirm_page=cfg["flow"]["confirm_page"],
        done_page=cfg["flow"]["done_page"],
        done_success_text=cfg["flow"]["done_success_text"],
        selectors=UploadSelectors(
            block=sel.get("block", ".upLoad"),
            open_modal=sel.get("open_modal", ".fileBtn"),
            modal_file_button=sel.get("modal_file_button", "#mdlBtn"),
            confirm_image=sel.get("confirm_image", 'button:has-text("この画像を使用する")'),
            next_button=sel.get("next_button", "#btn-next"),
            consent_checkbox=sel.get("consent_checkbox", "#checkConsent02"),
            submit_button=sel.get("submit_button", 'button:has-text("アップロードを完了する")'),
            pre_next_button=sel.get("pre_next_button", "button.next.nextBtn"),
        ),
    )


def run_post_approval(
    folder: Path,
    *,
    port: int | None = None,
    dry_run: bool = False,
    update_state: bool = True,
) -> str:
    """本審査承認後の追加提出（振込先・注文書/契約書等）。"""
    cfg = load_bank_config("mufg_jaccs")
    env = load_env()
    state = load_state()
    receipt, password = _credential(cfg, env, state)
    if not receipt:
        raise RuntimeError("受付番号が未設定です（.env または car_loan.json）")

    pa = cfg.get("post_approval", {})
    doc_specs = pa.get("documents") or []
    documents = resolve_documents(folder, doc_specs)
    cdp_port = port or int(cfg.get("cdp_port", 9223))
    profile = expand_path(cfg["chrome_profile"])
    login_url = pa.get("entry", {}).get(
        "jaccs_login_url",
        "https://ecredit.jaccs.co.jp/bank/Service?_TRANID=BWFLoginDL&MAILID=20",
    )

    if dry_run:
        print("=== DRY RUN mufg_jaccs post_approval ===")
        print(f"login_url={login_url}")
        for d in documents:
            print(f"  {d.key}: skip={d.skip} file={d.file_path}")
        return login_url

    start_cdp_chrome(cdp_port, profile, login_url)

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context(locale="ja-JP")
        page = _find_jaccs_main(ctx)
        if "BWFLoginDL" in page.url or login_url not in page.url:
            page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
        _jaccs_login_if_needed(page, login_url, receipt, password)
        time.sleep(1.5)

        upload_page = None
        for p in ctx.pages:
            if "mncollect.bk.mufg.jp" in p.url and ("B010" in p.url or "A010" in p.url):
                upload_page = p
                break
        if not upload_page:
            upload_page = ctx.new_page()
            upload_page.goto(upload_url(cfg, receipt), wait_until="networkidle", timeout=90000)

        flow = _flow_from_config(cfg)
        final_url = run_upload_flow(upload_page, documents, flow)

    if update_state:
        update_application_status(
            cfg["credentials"]["state_app_id"],
            "post_approval_documents_submitted",
            "本審査承認後の追加書類提出完了（振込先・注文書/見積）",
        )
    return final_url


def run_resubmit_deficiency(
    folder: Path,
    *,
    port: int | None = None,
    dry_run: bool = False,
    update_state: bool = True,
) -> str:
    """書類不備の再提出（免許証表のみ。他は不要）。"""
    cfg = load_bank_config("mufg_jaccs")
    env = load_env()
    state = load_state()
    receipt, password = _credential(cfg, env, state)
    if not receipt:
        raise RuntimeError("受付番号が未設定です（.env または car_loan.json）")

    rs = cfg.get("resubmit_deficiency", {})
    doc_specs = rs.get("documents") or cfg["documents"]
    documents = resolve_documents(folder, doc_specs)
    cdp_port = port or int(cfg.get("cdp_port", 9223))
    profile = expand_path(cfg["chrome_profile"])
    login_url = rs.get("entry", {}).get(
        "jaccs_login_url",
        "https://ecredit.jaccs.co.jp/bank/Service?_TRANID=BWFLoginDL&MAILID=20",
    )

    if dry_run:
        print("=== DRY RUN mufg_jaccs resubmit ===")
        print(f"login_url={login_url}")
        for d in documents:
            print(f"  {d.key}: skip={d.skip} file={d.file_path}")
        return login_url

    start_cdp_chrome(cdp_port, profile, login_url)

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context(locale="ja-JP")
        page = _find_jaccs_main(ctx)
        if "BWFLoginDL" in page.url or login_url not in page.url:
            page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
        _jaccs_login_if_needed(page, login_url, receipt, password)
        time.sleep(1.5)

        upload_page = None
        for p in ctx.pages:
            if "mncollect.bk.mufg.jp" in p.url and "B010" in p.url:
                upload_page = p
                break
        if not upload_page:
            for p in ctx.pages:
                if "書類" in (p.title() or "") or "mncollect" in p.url:
                    upload_page = p
                    break
        if not upload_page:
            with page.expect_popup(timeout=25000) as popup_info:
                page.evaluate(cfg["entry"]["guide_popup_js"])
            upload_page = popup_info.value
            upload_page.wait_for_load_state("domcontentloaded", timeout=30000)
            link = extract_upload_url_from_guide(upload_page)
            if link:
                upload_page.goto(link, wait_until="networkidle", timeout=90000)
        if "B010" not in upload_page.url:
            link = extract_upload_url_from_guide(upload_page)
            if link:
                upload_page.goto(link, wait_until="networkidle", timeout=90000)
            elif "uppage.php" in cfg["entry"]["upload_url_template"]:
                upload_page.goto(upload_url(cfg, receipt), wait_until="networkidle", timeout=90000)

        flow = _flow_from_config(cfg)
        final_url = run_upload_flow(upload_page, documents, flow)

    if update_state:
        update_application_status(
            cfg["credentials"]["state_app_id"],
            "documents_resubmitted",
            "免許証（表）再提出完了（書類不備対応）",
        )
    return final_url


def run_upload(
    folder: Path,
    *,
    port: int | None = None,
    dry_run: bool = False,
    update_state: bool = True,
) -> str:
    cfg = load_bank_config("mufg_jaccs")
    env = load_env()
    state = load_state()
    receipt, password = _credential(cfg, env, state)
    if not receipt:
        raise RuntimeError("受付番号が未設定です（.env または car_loan.json）")

    documents = resolve_documents(folder, cfg["documents"])
    cdp_port = port or int(cfg.get("cdp_port", 9223))
    profile = expand_path(cfg["chrome_profile"])
    entry_url = upload_url(cfg, receipt)

    if dry_run:
        print("=== DRY RUN mufg_jaccs ===")
        print(f"entry_url={entry_url}")
        for d in documents:
            print(f"  {d.key}: {d.file_path}")
        return entry_url

    start_cdp_chrome(cdp_port, profile, entry_url)

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context(locale="ja-JP")
        page = ctx.new_page()
        page.goto(entry_url, wait_until="networkidle", timeout=90000)
        time.sleep(0.8)

        flow = _flow_from_config(cfg)
        final_url = run_upload_flow(page, documents, flow)

    if update_state:
        update_application_status(
            cfg["credentials"]["state_app_id"],
            "documents_submitted",
            "書類Webアップロード提出完了（jarvis_car_loan_upload.py）",
        )
    return final_url
