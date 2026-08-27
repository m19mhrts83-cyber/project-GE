#!/usr/bin/env python3
"""
NotebookLM Studio 生成ランナー（Infographic / Slide Deck）。

モード:
  create     … Studio から新規作成（既定）
  recreate   … 新規作成と同じ UI（インフォ等の作り直し）
  revise     … 既存スライドを開き、ページ別「変更」で修正

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  # dry-run（生成クリックなし）
  python scripts/jarvis_notebooklm_studio_run.py --artifact infographic \\
    --prompt-file PATH.md --prompt-section info --dry-run
  # インフォ再作成
  python scripts/jarvis_notebooklm_studio_run.py --artifact infographic \\
    --mode recreate --prompt-file PATH.md --prompt-section info \\
    --confirm-generate --wait-and-save
  # スライド 3・8 をページ別修正
  python scripts/jarvis_notebooklm_studio_run.py --artifact slide_deck \\
    --mode revise --slide-pages 3,8 --prompt-file PATH.md \\
    --confirm-generate --wait-and-save
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_notebooklm_studio_lib import (  # noqa: E402
    expand,
    extract_prompt_section,
    extract_slide_page_prompt,
    first_match,
    load_cfg,
    load_selectors,
    resolve_drive_out,
    resolve_notebook_meta,
    resolve_notebook_url,
    write_run_state,
)


def _launch(headed: bool, downloads_path: Path):
    from playwright.sync_api import sync_playwright

    cfg = load_cfg()
    profile = expand(
        cfg.get("profile_dir")
        or "~/Library/Application Support/notebooklm-studio/chrome_profile"
    )
    profile.mkdir(parents=True, exist_ok=True)
    downloads_path.mkdir(parents=True, exist_ok=True)
    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(profile),
        headless=not headed,
        channel="chrome",
        args=["--disable-blink-features=AutomationControlled"],
        viewport={"width": 1600, "height": 1000},
        ignore_default_args=["--enable-automation"],
        accept_downloads=True,
        downloads_path=str(downloads_path),
    )
    page = context.pages[0] if context.pages else context.new_page()
    # Chrome channel often skips Playwright's download event; allow native save.
    for p in context.pages:
        try:
            client = context.new_cdp_session(p)
            try:
                client.send(
                    "Browser.setDownloadBehavior",
                    {
                        "behavior": "allow",
                        "downloadPath": str(downloads_path),
                        "eventsEnabled": True,
                    },
                )
            except Exception:
                client.send(
                    "Page.setDownloadBehavior",
                    {"behavior": "allow", "downloadPath": str(downloads_path)},
                )
        except Exception as e:
            print(f"# cdp download behavior skipped: {e}", file=sys.stderr)
    return pw, context, page


def _click_first(page, selectors: list[str], what: str):
    loc, sel = first_match(page, selectors, timeout_ms=2000)
    if not loc:
        for s in selectors:
            if s.startswith("text="):
                label = s[5:]
                try:
                    page.get_by_text(label, exact=False).first.click(timeout=2000)
                    return label
                except Exception:
                    continue
        raise RuntimeError(f"not_found:{what}")
    loc.click(timeout=5000)
    return sel


def _js_click_aria_description(page, description: str) -> bool:
    return bool(
        page.evaluate(
            """(desc) => {
              const b = [...document.querySelectorAll('button')].find(
                x => (x.getAttribute('aria-description') || '') === desc
              );
              if (!b) return false;
              b.click();
              return true;
            }""",
            description,
        )
    )


def _fill_prompt(page, selectors: list[str], prompt: str) -> str:
    loc, sel = first_match(page, selectors, timeout_ms=2500)
    if not loc:
        for s in ("textarea", '[contenteditable="true"]', 'div[role="textbox"]'):
            loc2 = page.locator(s)
            if loc2.count():
                loc, sel = loc2.first, s
                break
    if not loc:
        raise RuntimeError("prompt_field_not_found")
    try:
        loc.click(timeout=3000)
        page.wait_for_timeout(300)
        page.keyboard.press("Meta+A")
        page.keyboard.press("Backspace")
        loc.fill(prompt)
    except Exception:
        page.keyboard.press("Meta+A")
        page.keyboard.press("Backspace")
        page.keyboard.insert_text(prompt)
    return sel or "prompt"


def _pick_model(page, selectors: dict, model_name: str) -> None:
    open_sels = (selectors.get("model_picker") or {}).get("open") or []
    opt_sels = (selectors.get("model_picker") or {}).get("option_nano_banana_pro") or []
    if model_name and "Nano Banana" not in model_name:
        opt_sels = [f'text={model_name}', f'button:has-text("{model_name}")'] + list(opt_sels)
    loc, _ = first_match(page, open_sels, timeout_ms=1500)
    if loc:
        try:
            loc.click(timeout=3000)
            page.wait_for_timeout(800)
        except Exception:
            pass
    opt, _ = first_match(page, opt_sels, timeout_ms=1500)
    if opt:
        try:
            opt.click(timeout=3000)
            page.wait_for_timeout(500)
        except Exception:
            pass
    else:
        try:
            page.get_by_text(model_name or "Nano Banana Pro", exact=False).first.click(
                timeout=2000
            )
        except Exception:
            print("# model pick skipped (not found)", file=sys.stderr)


def _wait_idle(page, selectors: dict, timeout_sec: int, poll: float) -> bool:
    busy_sels = selectors.get("busy") or []
    deadline = time.time() + timeout_sec
    saw_busy = False
    while time.time() < deadline:
        busy = False
        for sel in busy_sels:
            try:
                loc = page.locator(sel)
                if loc.count() and loc.first.is_visible(timeout=300):
                    busy = True
                    saw_busy = True
                    break
            except Exception:
                continue
        # also treat enabled→disabled generate as busy for revise
        try:
            gen = page.get_by_label("改訂版のスライドを生成")
            if gen.count() and not gen.is_enabled():
                busy = True
                saw_busy = True
        except Exception:
            pass
        if saw_busy and not busy:
            return True
        dl_sels = selectors.get("download") or []
        loc, _ = first_match(page, dl_sels, timeout_ms=400)
        if loc and saw_busy:
            return True
        # 旧成果物のダウンロードボタンは生成中でも残る。saw_busy なしで早期 return しない
        page.wait_for_timeout(int(poll * 1000))
    return False


def _save_playwright_download(download, dest_dir: Path, stem: str) -> str:
    suggested = download.suggested_filename or f"{stem}.bin"
    ext = Path(suggested).suffix or ".pdf"
    out = dest_dir / f"{stem}{ext}"
    download.save_as(str(out))
    print(f"# saved {out}", file=sys.stderr)
    return str(out)


def _watch_new_download(watch_dirs: list[Path], before: set[str], timeout_sec: int = 90) -> Path | None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        for d in watch_dirs:
            if not d.is_dir():
                continue
            for p in d.iterdir():
                if not p.is_file():
                    continue
                if p.suffix.lower() not in {".pdf", ".pptx"}:
                    continue
                if str(p) in before:
                    continue
                if p.name.endswith(".crdownload") or p.name.endswith(".tmp"):
                    continue
                return p
        time.sleep(1)
    return None


def _snapshot_download_files(watch_dirs: list[Path]) -> set[str]:
    out: set[str] = set()
    for d in watch_dirs:
        if not d.is_dir():
            continue
        for p in d.iterdir():
            if p.is_file():
                out.add(str(p))
    return out


def _click_pdf_download_menu(page) -> None:
    """Open viewer more_vert (last match) and click the PDF download item."""
    labels = ("その他のオプション", "More options", "その他")
    opened = False
    for lab in labels:
        try:
            locs = page.get_by_label(lab)
            n = locs.count()
            if n == 0:
                continue
            locs.nth(n - 1).click(timeout=2000)
            opened = True
            page.wait_for_timeout(600)
            break
        except Exception:
            continue
    if not opened:
        try:
            locs = page.locator('[aria-label*="その他"]')
            n = locs.count()
            locs.nth(max(n - 1, 0)).click(timeout=2000, force=True)
            page.wait_for_timeout(600)
        except Exception as e:
            raise RuntimeError(f"more_vert_not_found:{e}") from e
    exact = "PDF ドキュメント (.pdf) をダウンロード"
    try:
        page.get_by_role("menuitem", name=exact).click(timeout=3000, force=True)
        return
    except Exception:
        pass
    for txt in (exact, "PDF ドキュメント", "Download PDF", ".pdf"):
        try:
            page.get_by_text(txt, exact=False).first.click(timeout=2500, force=True)
            return
        except Exception:
            continue
    raise RuntimeError("pdf_download_menu_item_not_found")


def _download_and_save(page, selectors: dict, dest_dir: Path, stem: str) -> list[str]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    home_dl = Path.home() / "Downloads"
    watch_dirs = [dest_dir, home_dl]
    before = _snapshot_download_files(watch_dirs)

    dl_sels = selectors.get("download") or []
    loc, _sel = first_match(page, dl_sels, timeout_ms=1500)

    try:
        with page.expect_download(timeout=15000) as di:
            try:
                _click_pdf_download_menu(page)
            except Exception as menu_err:
                print(f"# pdf menu skipped: {menu_err}", file=sys.stderr)
                if loc:
                    loc.click()
                else:
                    raise
        saved.append(_save_playwright_download(di.value, dest_dir, stem))
        return saved
    except Exception as e:
        print(f"# expect_download missed ({e}); watching folders", file=sys.stderr)

    found = _watch_new_download(watch_dirs, before, timeout_sec=90)
    if not found:
        # retry menu once more, then watch
        try:
            _click_pdf_download_menu(page)
        except Exception as e2:
            print(f"# menu retry failed: {e2}", file=sys.stderr)
        found = _watch_new_download(watch_dirs, before, timeout_sec=60)
    if not found:
        raise RuntimeError("download_not_captured")
    ext = found.suffix or ".pdf"
    out = dest_dir / f"{stem}{ext}"
    try:
        import shutil

        shutil.copy2(found, out)
    except Exception:
        out = found
    saved.append(str(out))
    print(f"# saved_from_watch {out} (src={found})", file=sys.stderr)
    return saved


def _open_studio(page, selectors: dict) -> None:
    try:
        _click_first(page, selectors.get("studio_tab") or [], "studio_tab")
        page.wait_for_timeout(1500)
        return
    except Exception:
        pass
    for label in ("Studio", "スタジオ"):
        try:
            page.get_by_text(label, exact=True).first.click(timeout=2000)
            page.wait_for_timeout(1500)
            return
        except Exception:
            continue
    try:
        page.locator('[aria-label*="Studio"]').first.click(timeout=2000, force=True)
        page.wait_for_timeout(1500)
    except Exception:
        print("# studio open soft-fail (may already be open)", file=sys.stderr)


def _open_create_dialog(page, artifact: str) -> None:
    """Studio パネル内の新規作成タイルをクリック（インフォ／スライド）。"""
    label = "インフォグラフィック" if artifact == "infographic" else "スライド資料"
    # Prefer exact text inside studio-panel
    try:
        page.locator("section.studio-panel").get_by_text(label, exact=True).first.click(
            timeout=4000, force=True
        )
        page.wait_for_timeout(2000)
        return
    except Exception:
        pass
    ok = page.evaluate(
        """(label) => {
          const panel = document.querySelector('section.studio-panel');
          if (!panel) return false;
          const el = [...panel.querySelectorAll('*')].find(
            e => (e.innerText || '').trim() === label
          );
          if (!el) return false;
          (el.closest('button') || el.closest('[role=button]') || el).click();
          return true;
        }""",
        label,
    )
    if not ok:
        raise RuntimeError(f"create_tile_not_found:{label}")
    page.wait_for_timeout(2000)


def _wait_studio_generating(page, timeout_sec: int, poll: float) -> bool:
    """Wait until '生成しています' appears then disappears."""
    deadline = time.time() + timeout_sec
    saw = False
    while time.time() < deadline:
        generating = page.evaluate(
            """() => /生成しています|Generating|Creating|生成中/.test(document.body.innerText)"""
        )
        if generating:
            saw = True
        elif saw:
            page.wait_for_timeout(2000)
            still = page.evaluate(
                """() => /生成しています|Generating|Creating|生成中/.test(document.body.innerText)"""
            )
            if not still:
                return True
        page.wait_for_timeout(int(poll * 1000))
    return saw  # if we saw it but never cleared, still timeout-ish


def _screenshot_artifact(page, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    handle = page.evaluate_handle(
        """() => {
          let best=null, bestA=0;
          for (const img of document.querySelectorAll('img')) {
            const r=img.getBoundingClientRect();
            const a=r.width*r.height;
            if (a>bestA && r.width>250) { best=img; bestA=a; }
          }
          return best;
        }"""
    )
    el = handle.as_element()
    if el:
        el.screenshot(path=str(dest))
    else:
        page.screenshot(path=str(dest))
    return str(dest)


def _open_existing_slide_deck(page, selectors: dict) -> None:
    open_sels = (selectors.get("open_existing") or {}).get("slide_deck") or []
    opened = False
    for sel in open_sels:
        if 'aria-description="スライド資料"' in sel:
            opened = _js_click_aria_description(page, "スライド資料")
            break
    if not opened:
        opened = _js_click_aria_description(page, "スライド資料")
    if not opened:
        raise RuntimeError("existing_slide_artifact_not_found")
    page.wait_for_timeout(3500)


def _screenshot_slide_pages(page, out_dir: Path, stem: str, pages: list[int]) -> list[str]:
    saved: list[str] = []
    thumb_tpl = '[aria-label^="スライド {n}"]'
    for n in pages:
        sel = thumb_tpl.format(n=n)
        try:
            page.locator(sel).first.click(timeout=4000)
        except Exception:
            page.get_by_label(f"スライド {n}", exact=False).first.click(timeout=4000)
        page.wait_for_timeout(900)
        dest = out_dir / f"{stem}_slide{n:02d}.png"
        page.screenshot(path=str(dest))
        saved.append(str(dest))
        print(f"# screenshot {dest}", file=sys.stderr)
    return saved


def _run_save_only(
    page,
    selectors: dict,
    out_dir: Path,
    stem: str,
    pages: list[int],
    state: dict,
) -> int:
    _open_existing_slide_deck(page, selectors)
    state["phase"] = "artifact_open"
    write_run_state(state)
    shots = []
    if pages:
        try:
            shots = _screenshot_slide_pages(page, out_dir, stem, pages)
        except Exception as e:
            print(f"# screenshot soft-fail: {e}", file=sys.stderr)
    try:
        files = _download_and_save(page, selectors, out_dir, stem)
    except Exception as e:
        print(f"# download soft-fail: {e}", file=sys.stderr)
        files = []
        state["error"] = f"download:{e}"
    state["files"] = files + shots
    state["ok"] = bool(files) or bool(shots)
    state["phase"] = "saved" if files else "generated_no_download"
    write_run_state(state)
    print(f"# done files={state.get('files')}")
    return 0 if state["ok"] else 1


def _run_create_or_recreate(
    page,
    selectors: dict,
    artifact: str,
    prompt: str,
    model: str,
    will_generate: bool,
    dry_run: bool,
    wait_and_save: bool,
    out_dir: Path,
    stem: str,
    cfg: dict,
    state: dict,
) -> int:
    _open_studio(page, selectors)
    _open_create_dialog(page, artifact)
    state["phase"] = "artifact_open"
    write_run_state(state)

    used = _fill_prompt(page, selectors.get("prompt_field") or [], prompt)
    print(f"# prompt filled via {used} chars={len(prompt)}", file=sys.stderr)
    _pick_model(page, selectors, model)
    state["phase"] = "prompt_ready"
    write_run_state(state)

    if dry_run or not will_generate:
        print("# dry-run / no generate — stopping before click", file=sys.stderr)
        state["ok"] = True
        state["phase"] = "dry_run_done"
        write_run_state(state)
        return 0

    # Prefer visible enabled 生成 / 作成 near dialog
    clicked = False
    for name in ("生成", "作成", "Generate"):
        btns = page.get_by_role("button", name=name)
        for j in range(btns.count()):
            b = btns.nth(j)
            try:
                if b.is_visible() and b.is_enabled():
                    box = b.bounding_box()
                    if box and box["y"] > 400:
                        b.click(timeout=3000)
                        clicked = True
                        print(f"# generate clicked ({name})", file=sys.stderr)
                        break
            except Exception:
                continue
        if clicked:
            break
    if not clicked:
        _click_first(page, selectors.get("generate") or [], "generate")
        print("# generate clicked (fallback)", file=sys.stderr)
    state["phase"] = "generating"
    write_run_state(state)

    if wait_and_save:
        ok_wait = _wait_studio_generating(
            page,
            int(cfg.get("generate_timeout_sec") or 900),
            float(cfg.get("poll_interval_sec") or 5),
        )
        if not ok_wait:
            # fallback to generic idle
            ok_wait = _wait_idle(
                page,
                selectors,
                60,
                float(cfg.get("poll_interval_sec") or 5),
            )
        if not ok_wait:
            state["error"] = "generate_timeout"
            write_run_state(state)
            print("# generate timeout", file=sys.stderr)
            return 1
        state["phase"] = "ready"
        write_run_state(state)
        files: list[str] = []
        try:
            files = _download_and_save(page, selectors, out_dir, stem)
        except Exception as e:
            print(f"# download soft-fail: {e}", file=sys.stderr)
            # open newest artifact of this type and screenshot
            desc = "インフォグラフィック" if artifact == "infographic" else "スライド資料"
            page.evaluate(
                """(desc) => {
                  const bs=[...document.querySelectorAll('button')].filter(
                    b => (b.getAttribute('aria-description')||'')===desc
                  );
                  const ranked=bs.map(b=>({b,y:b.getBoundingClientRect().y}))
                    .filter(x=>x.y>400).sort((a,c)=>a.y-c.y);
                  if(ranked.length) ranked[0].b.click();
                }""",
                desc,
            )
            page.wait_for_timeout(3500)
            shot = out_dir / f"{stem}.png"
            files = [_screenshot_artifact(page, shot)]
        state["files"] = files
        state["ok"] = True
        state["phase"] = "saved"
        write_run_state(state)
        print(f"# done files={files}")
        return 0

    state["ok"] = True
    state["phase"] = "generate_clicked"
    write_run_state(state)
    print("# generate started (no --wait-and-save)")
    return 0


def _run_revise(
    page,
    selectors: dict,
    artifact: str,
    page_prompts: dict[int, str],
    will_generate: bool,
    dry_run: bool,
    wait_and_save: bool,
    out_dir: Path,
    stem: str,
    cfg: dict,
    state: dict,
) -> int:
    if artifact != "slide_deck":
        raise RuntimeError("revise_mode_supports_slide_deck_only")

    # Open existing slide deck artifact (JS click avoids touch-target intercept)
    open_sels = (selectors.get("open_existing") or {}).get("slide_deck") or []
    opened = False
    for sel in open_sels:
        if 'aria-description="スライド資料"' in sel:
            opened = _js_click_aria_description(page, "スライド資料")
            break
    if not opened:
        # fallback: any stretched button with スライド資料
        opened = _js_click_aria_description(page, "スライド資料")
    if not opened:
        raise RuntimeError("existing_slide_artifact_not_found")
    page.wait_for_timeout(3500)
    state["phase"] = "artifact_open"
    write_run_state(state)

    rev = selectors.get("revise") or {}
    _click_first(page, rev.get("open_edit") or [], "revise_open_edit")
    page.wait_for_timeout(2000)
    state["phase"] = "revise_mode"
    write_run_state(state)

    thumb_tpl = rev.get("slide_thumb_template") or '[aria-label^="スライド {n}"]'
    for n, prompt in sorted(page_prompts.items()):
        sel = thumb_tpl.format(n=n)
        try:
            page.locator(sel).first.click(timeout=4000)
        except Exception:
            page.get_by_label(f"スライド {n}", exact=False).first.click(timeout=4000)
        page.wait_for_timeout(600)
        used = _fill_prompt(page, rev.get("prompt_field") or [], prompt)
        print(f"# slide {n} revision queued via {used} chars={len(prompt)}", file=sys.stderr)
        page.wait_for_timeout(700)
        try:
            pending = page.get_by_label("保留中の変更のポップアップを切り替え").inner_text()
            print(f"# pending: {pending.replace(chr(10), ' ')}", file=sys.stderr)
        except Exception:
            pass

    state["phase"] = "revise_queued"
    state["revise_pages"] = list(page_prompts.keys())
    write_run_state(state)

    if dry_run or not will_generate:
        print("# dry-run / no generate — cancel revise mode", file=sys.stderr)
        try:
            _click_first(page, rev.get("cancel") or [], "revise_cancel")
        except Exception:
            pass
        state["ok"] = True
        state["phase"] = "dry_run_done"
        write_run_state(state)
        return 0

    _click_first(page, rev.get("generate") or [], "revise_generate")
    print("# revise generate clicked", file=sys.stderr)
    state["phase"] = "generating"
    write_run_state(state)

    if wait_and_save:
        ok_wait = _wait_idle(
            page,
            selectors,
            int(cfg.get("generate_timeout_sec") or 900),
            float(cfg.get("poll_interval_sec") or 5),
        )
        if not ok_wait:
            # soft: wait a bit more if pending disappeared
            page.wait_for_timeout(15000)
        state["phase"] = "ready"
        write_run_state(state)
        try:
            files = _download_and_save(page, selectors, out_dir, stem)
            state["files"] = files
        except Exception as e:
            print(f"# download soft-fail: {e}", file=sys.stderr)
            state["files"] = []
            state["error"] = f"download:{e}"
        state["ok"] = True
        state["phase"] = "saved" if state.get("files") else "generated_no_download"
        write_run_state(state)
        print(f"# done files={state.get('files')}")
        return 0

    state["ok"] = True
    state["phase"] = "generate_clicked"
    write_run_state(state)
    print("# revise generate started (no --wait-and-save)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NotebookLM Studio run")
    ap.add_argument("--notebook-url", default=None)
    ap.add_argument("--notebook-key", default="hokkaido_gw2027")
    ap.add_argument(
        "--artifact",
        choices=("infographic", "slide_deck"),
        required=True,
    )
    ap.add_argument(
        "--mode",
        choices=("create", "recreate", "revise", "save"),
        default="create",
        help="create/recreate=新規作成UI / revise=既存スライドのページ別修正 / save=PDF保存のみ",
    )
    ap.add_argument(
        "--slide-pages",
        default=None,
        help="revise 時の対象ページ（例: 3,8）",
    )
    ap.add_argument("--prompt-file", default=None)
    ap.add_argument("--prompt-inline", default=None)
    ap.add_argument(
        "--prompt-section",
        default="full",
        help="info | slides | full（prompt-file 内の見出しから抽出）",
    )
    ap.add_argument("--model", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--confirm-generate",
        action="store_true",
        help="生成ボタンを押す明示許可（誤操作防止）",
    )
    ap.add_argument("--wait-and-save", action="store_true")
    ap.add_argument("--output-name", default=None, help="保存ファイル名 stem")
    ap.add_argument("--headed", action="store_true", default=True)
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args(argv)
    headed = not args.headless

    cfg = load_cfg()
    selectors = load_selectors()
    nb_meta = resolve_notebook_meta(cfg, args.notebook_key)
    if not args.prompt_file and nb_meta.get("revise_prompt") and args.mode == "revise":
        args.prompt_file = str(nb_meta["revise_prompt"])
    if not args.slide_pages and nb_meta.get("default_slide_pages") and args.mode == "revise":
        args.slide_pages = str(nb_meta["default_slide_pages"])

    url = resolve_notebook_url(cfg, args.notebook_url, args.notebook_key)
    if not url:
        print(
            "missing notebook url（--notebook-url か notebooks.<key>.url を設定）",
            file=sys.stderr,
        )
        return 2

    prompt_file_text = ""
    if args.prompt_file:
        p = Path(args.prompt_file).expanduser()
        if not p.is_absolute():
            p = REPO / p
        if not p.is_file():
            print(f"prompt_file_missing:{p}", file=sys.stderr)
            return 2
        prompt_file_text = p.read_text(encoding="utf-8")

    prompt = (args.prompt_inline or "").strip()
    page_prompts: dict[int, str] = {}
    save_pages: list[int] = []
    if args.mode == "save":
        if args.slide_pages:
            save_pages = [int(x.strip()) for x in args.slide_pages.split(",") if x.strip()]
        else:
            save_pages = [3, 6]
    elif args.mode == "revise":
        if not args.slide_pages:
            print("revise requires --slide-pages (e.g. 3,8)", file=sys.stderr)
            return 2
        pages = [int(x.strip()) for x in args.slide_pages.split(",") if x.strip()]
        if not pages:
            print("empty --slide-pages", file=sys.stderr)
            return 2
        if prompt and len(pages) == 1:
            page_prompts[pages[0]] = prompt
        else:
            src = prompt_file_text or prompt
            if not src:
                print("missing prompt for revise", file=sys.stderr)
                return 2
            for n in pages:
                page_prompts[n] = extract_slide_page_prompt(src, n)
    else:
        if args.prompt_file and not prompt:
            prompt = extract_prompt_section(prompt_file_text, args.prompt_section)
        if not prompt:
            print("missing prompt (--prompt-file or --prompt-inline)", file=sys.stderr)
            return 2

    model = args.model or cfg.get("preferred_model") or "Nano Banana Pro"
    drive_folder = nb_meta.get("drive_folder") or cfg.get("default_drive_folder")
    out_dir = resolve_drive_out(cfg, drive_folder)
    stem = args.output_name or (
        f"08_studio_{args.mode}_{args.artifact}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )

    require = bool(cfg.get("require_confirm_generate", True))
    will_generate = (not args.dry_run) and (args.confirm_generate or not require)
    if args.mode != "save" and not args.dry_run and require and not args.confirm_generate:
        print(
            "refusing generate: pass --confirm-generate (or --dry-run)",
            file=sys.stderr,
        )
        return 3

    state = {
        "ok": False,
        "phase": "start",
        "notebook_url": url,
        "artifact": args.artifact,
        "mode": args.mode,
        "slide_pages": list(page_prompts.keys()) if page_prompts else (save_pages or None),
        "dry_run": bool(args.dry_run),
        "confirm_generate": bool(args.confirm_generate),
        "will_generate": will_generate,
        "wait_and_save": bool(args.wait_and_save),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "files": [],
        "error": None,
    }
    write_run_state(state)

    downloads = out_dir if args.mode == "save" else expand(cfg.get("downloads_dir") or "~/Downloads")
    pw, context, page = _launch(headed, downloads)
    try:
        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=int(cfg.get("goto_timeout_sec") or 90) * 1000,
        )
        page.wait_for_timeout(3500)
        state["phase"] = "opened"
        write_run_state(state)

        if args.mode == "save":
            return _run_save_only(page, selectors, out_dir, stem, save_pages, state)
        if args.mode == "revise":
            return _run_revise(
                page,
                selectors,
                args.artifact,
                page_prompts,
                will_generate,
                bool(args.dry_run),
                bool(args.wait_and_save),
                out_dir,
                stem,
                cfg,
                state,
            )
        return _run_create_or_recreate(
            page,
            selectors,
            args.artifact,
            prompt,
            model,
            will_generate,
            bool(args.dry_run),
            bool(args.wait_and_save),
            out_dir,
            stem,
            cfg,
            state,
        )
    except Exception as e:
        state["error"] = str(e)
        state["ok"] = False
        write_run_state(state)
        print(f"# error: {e}", file=sys.stderr)
        return 1
    finally:
        try:
            context.close()
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
