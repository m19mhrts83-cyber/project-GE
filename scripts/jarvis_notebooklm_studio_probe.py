#!/usr/bin/env python3
"""
NotebookLM Studio UI 探査（生成は押さない）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_notebooklm_studio_probe.py
  python scripts/jarvis_notebooklm_studio_probe.py --notebook-url 'https://notebooklm.google.com/notebook/…'
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_notebooklm_studio_lib import (  # noqa: E402
    expand,
    first_match,
    load_cfg,
    load_selectors,
    resolve_notebook_url,
    save_selectors,
)


def _launch(headed: bool):
    from playwright.sync_api import sync_playwright

    cfg = load_cfg()
    profile = expand(cfg.get("profile_dir") or "~/Library/Application Support/notebooklm-studio/chrome_profile")
    profile.mkdir(parents=True, exist_ok=True)
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


def _dump_labels(page) -> list[str]:
    return page.evaluate(
        """() => {
          const els = [...document.querySelectorAll('button,[role=tab],[role=button],a,span')];
          const out = [];
          for (const el of els) {
            const t = (el.getAttribute('aria-label') || el.innerText || '').trim().replace(/\\s+/g, ' ');
            if (t && t.length < 60) out.push(t);
          }
          return [...new Set(out)].slice(0, 200);
        }"""
    )


def _try_click_studio(page, selectors: dict) -> str | None:
    loc, sel = first_match(page, selectors.get("studio_tab") or [], timeout_ms=1500)
    if loc:
        try:
            loc.click(timeout=3000)
            page.wait_for_timeout(2000)
            return sel
        except Exception as e:
            print(f"# studio_tab click fail: {e}", file=sys.stderr)
    # fallback by text
    for label in ("Studio", "スタジオ"):
        try:
            page.get_by_text(label, exact=True).first.click(timeout=2000)
            page.wait_for_timeout(2000)
            return f"get_by_text({label})"
        except Exception:
            continue
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NotebookLM Studio UI probe")
    ap.add_argument("--notebook-url", default=None)
    ap.add_argument("--notebook-key", default=None, help="config notebooks.* key")
    ap.add_argument("--headed", action="store_true", default=True)
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--update-selectors", action="store_true", help="write probe hits into selectors yaml")
    args = ap.parse_args(argv)
    headed = not args.headless

    cfg = load_cfg()
    selectors = load_selectors()
    url = resolve_notebook_url(cfg, args.notebook_url, args.notebook_key)
    if not url:
        print("missing notebook url", file=sys.stderr)
        return 2

    out_dir = expand(cfg.get("probe_out_dir") or "/tmp/notebooklm_studio_probe")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = out_dir / stamp
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"# notebook={url}", file=sys.stderr)
    print(f"# out={run_dir}", file=sys.stderr)

    pw, context, page = _launch(headed)
    report: dict = {
        "notebook_url": url,
        "started_at": stamp,
        "studio_tab_hit": None,
        "artifact_hits": {},
        "prompt_hits": [],
        "generate_hits": [],
        "labels_before": [],
        "labels_after_studio": [],
        "ok": False,
    }
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=int(cfg.get("goto_timeout_sec") or 90) * 1000)
        page.wait_for_timeout(4000)
        page.screenshot(path=str(run_dir / "01_notebook.png"))
        report["labels_before"] = _dump_labels(page)
        (run_dir / "labels_before.json").write_text(
            json.dumps(report["labels_before"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        hit = _try_click_studio(page, selectors)
        report["studio_tab_hit"] = hit
        page.screenshot(path=str(run_dir / "02_studio.png"))
        report["labels_after_studio"] = _dump_labels(page)
        (run_dir / "labels_after_studio.json").write_text(
            json.dumps(report["labels_after_studio"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        arts = selectors.get("artifacts") or {}
        for key, sels in arts.items():
            loc, sel = first_match(page, sels, timeout_ms=1500)
            report["artifact_hits"][key] = {"found": bool(loc), "selector": sel}
            if loc:
                try:
                    loc.click(timeout=3000)
                    page.wait_for_timeout(1500)
                    page.screenshot(path=str(run_dir / f"03_artifact_{key}.png"))
                except Exception as e:
                    report["artifact_hits"][key]["click_error"] = str(e)

        for sel in selectors.get("prompt_field") or []:
            try:
                loc = page.locator(sel)
                if loc.count() and loc.first.is_visible(timeout=800):
                    report["prompt_hits"].append(sel)
            except Exception:
                continue

        for sel in selectors.get("generate") or []:
            try:
                loc = page.locator(sel)
                if loc.count() and loc.first.is_visible(timeout=800):
                    report["generate_hits"].append(sel)
            except Exception:
                continue

        report["ok"] = bool(
            report["studio_tab_hit"]
            or report["artifact_hits"].get("infographic", {}).get("found")
            or report["artifact_hits"].get("slide_deck", {}).get("found")
            or any("Studio" in x or "スタジオ" in x for x in report["labels_after_studio"])
        )
        (run_dir / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        if args.update_selectors:
            # prepend successful selectors
            if report["studio_tab_hit"] and report["studio_tab_hit"] not in (
                selectors.get("studio_tab") or []
            ):
                selectors.setdefault("studio_tab", [])
                if not str(report["studio_tab_hit"]).startswith("get_by_text"):
                    selectors["studio_tab"] = [report["studio_tab_hit"]] + list(
                        selectors["studio_tab"]
                    )
            for key, info in report["artifact_hits"].items():
                if info.get("found") and info.get("selector"):
                    lst = (selectors.get("artifacts") or {}).setdefault(key, [])
                    if info["selector"] not in lst:
                        selectors.setdefault("artifacts", {}).setdefault(key, [])
                        selectors["artifacts"][key] = [info["selector"]] + list(lst)
            if report["prompt_hits"]:
                selectors["prompt_field"] = list(
                    dict.fromkeys(report["prompt_hits"] + list(selectors.get("prompt_field") or []))
                )
            if report["generate_hits"]:
                selectors["generate"] = list(
                    dict.fromkeys(report["generate_hits"] + list(selectors.get("generate") or []))
                )
            selectors["updated_at"] = datetime.now(timezone.utc).isoformat()
            selectors["notes"] = f"probe {stamp} notebook={url}"
            save_selectors(selectors)
            print(f"# updated {REPO / 'config/notebooklm_studio_selectors.yaml'}", file=sys.stderr)

        print(json.dumps({"ok": report["ok"], "out": str(run_dir), "report": report}, ensure_ascii=False))
        return 0 if report["ok"] else 1
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
