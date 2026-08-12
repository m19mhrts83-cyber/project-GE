#!/usr/bin/env python3
"""
NotebookLM Studio 生成ランナー（Infographic / Slide Deck）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  # dry-run（生成クリックなし）
  python scripts/jarvis_notebooklm_studio_run.py --artifact infographic \\
    --prompt-file PATH.md --prompt-section info --dry-run
  # 生成＋保存
  python scripts/jarvis_notebooklm_studio_run.py --artifact infographic \\
    --prompt-file PATH.md --prompt-section info --confirm-generate --wait-and-save
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
    first_match,
    load_cfg,
    load_selectors,
    resolve_drive_out,
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
        viewport={"width": 1400, "height": 900},
        ignore_default_args=["--enable-automation"],
        accept_downloads=True,
    )
    page = context.pages[0] if context.pages else context.new_page()
    return pw, context, page


def _click_first(page, selectors: list[str], what: str):
    loc, sel = first_match(page, selectors, timeout_ms=2000)
    if not loc:
        # text fallbacks embedded in selector list already; try get_by_text for short labels
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


def _fill_prompt(page, selectors: list[str], prompt: str) -> str:
    loc, sel = first_match(page, selectors, timeout_ms=2500)
    if not loc:
        # last resort: first textarea / contenteditable
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
        # clear
        page.keyboard.press("Meta+A")
        page.keyboard.press("Backspace")
        loc.fill(prompt)
    except Exception:
        # contenteditable may not support fill
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
        # try get_by_text
        try:
            page.get_by_text(model_name or "Nano Banana Pro", exact=False).first.click(timeout=2000)
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
        if saw_busy and not busy:
            return True
        # download button as completion signal
        dl_sels = selectors.get("download") or []
        loc, _ = first_match(page, dl_sels, timeout_ms=400)
        if loc and saw_busy:
            return True
        if loc and not saw_busy and time.time() + 30 > deadline - timeout_sec + 60:
            # download visible without busy — treat as ready after short wait
            page.wait_for_timeout(2000)
            return True
        page.wait_for_timeout(int(poll * 1000))
    return False


def _download_and_save(page, selectors: dict, dest_dir: Path, stem: str) -> list[str]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    dl_sels = selectors.get("download") or []
    loc, sel = first_match(page, dl_sels, timeout_ms=3000)
    if not loc:
        # try menu
        for label in ("Download", "ダウンロード", "Export", "エクスポート"):
            try:
                page.get_by_text(label, exact=False).first.click(timeout=2000)
                page.wait_for_timeout(800)
                loc, sel = first_match(page, dl_sels, timeout_ms=2000)
                if loc:
                    break
            except Exception:
                continue
    if not loc:
        raise RuntimeError("download_button_not_found")

    with page.expect_download(timeout=120000) as di:
        loc.click()
    download = di.value
    suggested = download.suggested_filename or f"{stem}.bin"
    ext = Path(suggested).suffix or ".pdf"
    out = dest_dir / f"{stem}{ext}"
    download.save_as(str(out))
    saved.append(str(out))
    print(f"# saved {out}", file=sys.stderr)
    return saved


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NotebookLM Studio run")
    ap.add_argument("--notebook-url", default=None)
    ap.add_argument("--notebook-key", default="hokkaido_gw2027")
    ap.add_argument(
        "--artifact",
        choices=("infographic", "slide_deck"),
        required=True,
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
    url = resolve_notebook_url(cfg, args.notebook_url, args.notebook_key)
    if not url:
        print("missing notebook url", file=sys.stderr)
        return 2

    prompt = (args.prompt_inline or "").strip()
    if args.prompt_file:
        p = Path(args.prompt_file).expanduser()
        if not p.is_file():
            print(f"prompt_file_missing:{p}", file=sys.stderr)
            return 2
        prompt = extract_prompt_section(p.read_text(encoding="utf-8"), args.prompt_section)
    if not prompt:
        print("missing prompt (--prompt-file or --prompt-inline)", file=sys.stderr)
        return 2

    model = args.model or cfg.get("preferred_model") or "Nano Banana Pro"
    nb_cfg = (cfg.get("notebooks") or {}).get(args.notebook_key or "") or {}
    drive_folder = nb_cfg.get("drive_folder") or cfg.get("default_drive_folder")
    out_dir = resolve_drive_out(cfg, drive_folder)
    stem = args.output_name or (
        f"08_studio_{args.artifact}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )

    require = bool(cfg.get("require_confirm_generate", True))
    will_generate = (not args.dry_run) and (
        args.confirm_generate or not require
    )
    if not args.dry_run and require and not args.confirm_generate:
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
        "dry_run": bool(args.dry_run),
        "confirm_generate": bool(args.confirm_generate),
        "will_generate": will_generate,
        "wait_and_save": bool(args.wait_and_save),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "files": [],
        "error": None,
    }
    write_run_state(state)

    downloads = expand(cfg.get("downloads_dir") or "~/Downloads")
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

        # Studio tab
        try:
            _click_first(page, selectors.get("studio_tab") or [], "studio_tab")
            page.wait_for_timeout(1500)
        except Exception:
            for label in ("Studio", "スタジオ"):
                try:
                    page.get_by_text(label, exact=True).first.click(timeout=2000)
                    page.wait_for_timeout(1500)
                    break
                except Exception:
                    continue

        arts = (selectors.get("artifacts") or {}).get(args.artifact) or []
        _click_first(page, arts, f"artifact:{args.artifact}")
        page.wait_for_timeout(1500)
        state["phase"] = "artifact_open"
        write_run_state(state)

        used_prompt_sel = _fill_prompt(page, selectors.get("prompt_field") or [], prompt)
        print(f"# prompt filled via {used_prompt_sel} chars={len(prompt)}", file=sys.stderr)
        _pick_model(page, selectors, model)
        state["phase"] = "prompt_ready"
        write_run_state(state)

        if args.dry_run or not will_generate:
            print("# dry-run / no generate — stopping before click", file=sys.stderr)
            state["ok"] = True
            state["phase"] = "dry_run_done"
            write_run_state(state)
            return 0

        _click_first(page, selectors.get("generate") or [], "generate")
        print("# generate clicked", file=sys.stderr)
        state["phase"] = "generating"
        write_run_state(state)

        if args.wait_and_save:
            ok_wait = _wait_idle(
                page,
                selectors,
                int(cfg.get("generate_timeout_sec") or 900),
                float(cfg.get("poll_interval_sec") or 5),
            )
            if not ok_wait:
                state["error"] = "generate_timeout"
                write_run_state(state)
                print("# generate timeout", file=sys.stderr)
                return 1
            state["phase"] = "ready"
            write_run_state(state)
            files = _download_and_save(page, selectors, out_dir, stem)
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
