"""書類Webアップロード共通エンジン（Playwright + CDP Chrome）。

今回の MUFG 実績から得た知見:
- file input 直叩きはサーバー 400 になりやすい → モーダル経由の file chooser を使う
- 書類は B010 でブロックが1つずつ増える → block index と documents の順序を一致させる
- 全点アップロード完了後に #btn-next → E010 確認 → チェック → 完了ボタン
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DocumentSpec:
    key: str
    option_keywords: list[str]
    file_path: Path | None = None
    skip: bool = False


@dataclass
class UploadSelectors:
    block: str = ".upLoad"
    select: str = "select"
    open_modal: str = ".fileBtn"
    modal_file_button: str = "#mdlBtn"
    confirm_image: str = 'button:has-text("この画像を使用する")'
    next_button: str = "#btn-next"
    consent_checkbox: str = "#checkConsent02"
    submit_button: str = 'button:has-text("アップロードを完了する")'
    pre_next_button: str = "button.next.nextBtn"


@dataclass
class UploadFlowConfig:
    pre_pages: list[str]
    upload_page: str
    confirm_page: str
    done_page: str
    done_success_text: str
    selectors: UploadSelectors
    block_wait_sec: float = 45.0
    thumb_wait_sec: float = 30.0


def resolve_documents(folder: Path, specs: list[dict]) -> list[DocumentSpec]:
    """YAML documents 定義から実ファイルを解決。"""
    if not folder.is_dir():
        raise FileNotFoundError(f"提出フォルダが見つかりません: {folder}")
    out: list[DocumentSpec] = []
    for spec in specs:
        skip = bool(spec.get("skip"))
        globs = spec.get("file_globs") or [spec.get("file_glob", "*")]
        found: Path | None = None
        if not skip:
            for pattern in globs:
                matches = sorted(folder.glob(pattern))
                if matches:
                    found = matches[0]
                    break
            if not found:
                raise FileNotFoundError(
                    f"書類ファイル未検出: key={spec['key']} patterns={globs} in {folder}"
                )
        out.append(
            DocumentSpec(
                key=spec["key"],
                option_keywords=list(spec.get("option_keywords", [])),
                file_path=found,
                skip=skip,
            )
        )
    return out


def _wait_block_count(page, selector: str, min_count: int, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.locator(selector).count() >= min_count:
            return
        time.sleep(0.4)
    raise TimeoutError(f"アップロード枠が {min_count} 個に増えませんでした")


def _select_option(block, keywords: list[str]) -> str:
    opts = block.locator("select").locator("option").all_inner_texts()
    for o in opts:
        if any(k in o for k in keywords):
            block.locator("select").select_option(label=o)
            return o
    raise ValueError(f"選択肢が見つかりません: keywords={keywords} options={opts}")


def skip_block_no_upload(page, block_idx: int, doc: DocumentSpec, sel: UploadSelectors) -> dict:
    """提出済み書類を「不要」等でスキップ（再提出時）。"""
    block = page.locator(sel.block).nth(block_idx)
    chosen = _select_option(block, doc.option_keywords)
    time.sleep(0.8)
    confirmed = page.evaluate(
        """(args) => {
          const b = document.querySelectorAll(args.block)[args.idx];
          const btn = b?.querySelector('.verifyBtn .nextBtn');
          return btn?.classList.contains('on') || b?.querySelector('.skipMsg, .message')?.textContent || '';
        }""",
        {"block": sel.block, "idx": block_idx},
    )
    if confirmed is not True and not confirmed:
        block.locator(sel.confirm_image).click(force=True, timeout=3000)
        time.sleep(0.8)
        confirmed = page.evaluate(
            """(args) => document.querySelectorAll(args.block)[args.idx]
                ?.querySelector('.verifyBtn .nextBtn')?.classList.contains('on')""",
            {"block": sel.block, "idx": block_idx},
        )
    return {"key": doc.key, "chosen": chosen, "file": "(skip)", "confirmed": bool(confirmed)}


def upload_block_modal(page, block_idx: int, doc: DocumentSpec, sel: UploadSelectors) -> dict:
    """1ブロック分: 種別選択 → モーダル file chooser → プレビュー → この画像を使用する。"""
    block = page.locator(sel.block).nth(block_idx)
    chosen = _select_option(block, doc.option_keywords)
    time.sleep(0.5)
    # 種別選択で .mdl が開く。fileBtn を押すと閉じることがあるため mdlBtn を直接使う。
    deadline = time.time() + 10
    while time.time() < deadline:
        if page.evaluate("() => getComputedStyle(document.querySelector('.mdl')).display === 'block'"):
            break
        block.locator(sel.open_modal).click(force=True)
        time.sleep(0.4)
    with page.expect_file_chooser(timeout=15000) as fc_info:
        page.evaluate(
            """() => {
              const btn = document.querySelector('.mdl #mdlBtn') || document.getElementById('mdlBtn');
              if (btn) btn.click();
            }"""
        )
    fc_info.value.set_files(str(doc.file_path))

    state: dict = {}
    deadline = time.time() + 30
    while time.time() < deadline:
        state = page.evaluate(
            """(args) => {
              const b = document.querySelectorAll(args.block)[args.idx];
              const vb = b?.querySelector('.verifyBox');
              return {
                verify: vb ? getComputedStyle(vb).display : null,
                thumb: !!b?.querySelector('.thumbnail img'),
                name: b?.querySelector('.name span')?.textContent || '',
                msg: b?.querySelector('.message')?.textContent || '',
              };
            }""",
            {"block": sel.block, "idx": block_idx},
        )
        if state.get("verify") == "block" and state.get("thumb"):
            break
        if state.get("msg"):
            break
        time.sleep(0.5)

    if state.get("msg"):
        raise RuntimeError(f"アップロードエラー ({doc.key}): {state['msg']}")

    block.locator(sel.confirm_image).click(force=True)
    time.sleep(1.0)
    confirmed = page.evaluate(
        """(args) => document.querySelectorAll(args.block)[args.idx]
            ?.querySelector('.verifyBtn .nextBtn')?.classList.contains('on')""",
        {"block": sel.block, "idx": block_idx},
    )
    return {"key": doc.key, "chosen": chosen, "file": doc.file_path.name, "confirmed": confirmed}


def run_upload_flow(page, documents: list[DocumentSpec], flow: UploadFlowConfig) -> str:
    """B010 から F010 まで一気通貫。完了時の URL を返す。"""
    sel = flow.selectors

    for marker in flow.pre_pages:
        if marker in page.url:
            page.locator(sel.pre_next_button).click()
            page.wait_for_load_state("networkidle", timeout=60000)
            time.sleep(0.8)
            break

    if flow.upload_page.split("/")[-1] not in page.url:
        raise RuntimeError(f"アップロード画面にいません: {page.url}")

    results = []
    for i, doc in enumerate(documents):
        _wait_block_count(page, sel.block, i + 1, flow.block_wait_sec)
        if doc.skip:
            print(f"📎 [{i + 1}/{len(documents)}] {doc.key} → スキップ（{doc.option_keywords}）")
            res = skip_block_no_upload(page, i, doc, sel)
        else:
            print(f"📎 [{i + 1}/{len(documents)}] {doc.key} ← {doc.file_path.name}")
            res = upload_block_modal(page, i, doc, sel)
        results.append(res)
        print(f"   ✅ {res['chosen']} / confirmed={res['confirmed']}")

    disabled = page.evaluate(
        f"() => document.querySelector('{sel.next_button}')?.disabled"
    )
    if disabled:
        time.sleep(2)
    page.locator(sel.next_button).click()
    page.wait_for_load_state("networkidle", timeout=60000)
    time.sleep(1)

    if flow.confirm_page.split("/")[-1] not in page.url:
        raise RuntimeError(f"確認画面に遷移できません: {page.url}")

    body = page.inner_text("body")
    for doc in documents:
        if doc.skip or not doc.file_path:
            continue
        if doc.file_path.name not in body:
            print(f"⚠️  確認画面に {doc.file_path.name} が見当たりません（続行）")

    # ラベルクリックが最も確実（#checkConsent02 だけでは submit が有効化されない）
    try:
        page.locator('label:has-text("内容を確認しました")').click(force=True, timeout=5000)
    except Exception:
        page.evaluate(
            """(id) => {
              const cb = document.querySelector(id);
              if (cb) { cb.checked = true; cb.click(); }
            }""",
            sel.consent_checkbox,
        )
    time.sleep(0.5)
    submit = page.locator(sel.submit_button)
    for _ in range(30):
        if submit.get_attribute("disabled") is None:
            break
        time.sleep(0.2)
    submit.click()
    page.wait_for_load_state("networkidle", timeout=60000)
    time.sleep(1.5)

    final_body = page.inner_text("body")
    if flow.done_success_text not in final_body:
        raise RuntimeError(f"受付完了を確認できません: {page.url}\n{final_body[:500]}")

    print(f"✅ {flow.done_success_text} — {page.url}")
    return page.url
