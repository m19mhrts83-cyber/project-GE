"""りそな銀行マイカーローン — テンプレートアダプタ。"""
from __future__ import annotations

from pathlib import Path

from ..chrome_cdp import open_in_chrome
from ..env_state import load_env, load_state, receipt_from_state
from ..upload_flow import UploadFlowConfig, UploadSelectors, resolve_documents, run_upload_flow
from .registry import expand_path, load_bank_config


class ResonaNotReadyError(RuntimeError):
    pass


def _flow_from_config(cfg: dict) -> UploadFlowConfig:
    sel = cfg.get("selectors", {})
    flow = cfg["flow"]
    return UploadFlowConfig(
        pre_pages=list(flow.get("pre_pages", [])),
        upload_page=flow.get("upload_page", ""),
        confirm_page=flow.get("confirm_page", ""),
        done_page=flow.get("done_page", ""),
        done_success_text=flow.get("done_success_text", "受付完了"),
        selectors=UploadSelectors(**{k: v for k, v in sel.items() if k in UploadSelectors.__dataclass_fields__}),
    )


def run_upload(
    folder: Path,
    *,
    portal_url: str | None = None,
    port: int | None = None,
    dry_run: bool = False,
) -> str:
    cfg = load_bank_config("resona")
    if cfg.get("implementation_status") == "portal_form":
        from . import resona_portal

        return resona_portal.open_and_prepare(port=port, dry_run=dry_run, save=not dry_run)

    if cfg.get("implementation_status") == "template":
        entry = cfg.get("entry", {})
        url = portal_url or entry.get("portal_url") or entry.get("upload_url_template", "")
        if not url or not cfg["flow"].get("upload_page"):
            raise ResonaNotReadyError(
                "りそなの書類提出URL・画面定義が未設定です。\n"
                "本審査可決メールの提出リンクを確認し、\n"
                "  scripts/car_loan/configs/resona.yaml\n"
                "の entry.portal_url / flow / selectors を更新してください。\n"
                "画面が MUFG(mncollect) 同型なら mufg_jaccs.yaml をコピーして銀行名だけ差し替えで可。"
            )

    env = load_env()
    state = load_state()
    cred = cfg["credentials"]
    receipt = env.get(cred.get("receipt_env", ""), "") or receipt_from_state(
        cred["state_app_id"], env, state
    )

    documents = resolve_documents(folder, cfg["documents"])
    entry_url = (portal_url or cfg["entry"].get("portal_url", "")).format(receipt=receipt)

    if dry_run:
        print("=== DRY RUN resona ===")
        print(f"entry_url={entry_url}")
        for d in documents:
            print(f"  {d.key}: {d.file_path}")
        return entry_url

    cdp_port = port or int(cfg.get("cdp_port", 9224))
    from ..chrome_cdp import start_cdp_chrome
    from playwright.sync_api import sync_playwright

    start_cdp_chrome(cdp_port, expand_path(cfg["chrome_profile"]), entry_url)

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context(locale="ja-JP")
        page = ctx.new_page()
        page.goto(entry_url, wait_until="networkidle", timeout=90000)
        flow = _flow_from_config(cfg)
        return run_upload_flow(page, documents, flow)


def open_portal() -> None:
    cfg = load_bank_config("resona")
    url = cfg.get("url") or "https://www.resonabank.co.jp/kojin/mycar"
    open_in_chrome(url)
    print("📎 りそなマイカーローン公式ページを開きました。審査結果メールの提出リンクを確認してください。")
