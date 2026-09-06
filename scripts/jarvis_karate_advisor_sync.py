#!/usr/bin/env python3
"""Sync Karate Advisor research & diagrams from Grok Bot to Obsidian & OGD.

Workflow:
1. Connects to Grok Bot desktop app via CDP.
2. Reads messages in "空手アドバイザー" (Karate Advisor).
3. Detects "## Obsidian追記案" blocks and generated anatomical diagrams (images).
4. Saves notes to ~/Documents/500_Obsidian_r1/01_Journaling/☆Karate/{subfolder}/.
5. Saves images to ~/Documents/500_Obsidian_r1/01_Journaling/☆Karate/assets/.
6. Updates 00_このフォルダ.md index.
7. Calls jarvis_obsidian_ogd_retag.py so iPhone Obsidian pulls them cleanly.
8. Records state in ~/.jarvis_state/karate_advisor_sync.json.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
VAULT_DIR = Path.home() / "Documents/500_Obsidian_r1"
KARATE_DIR = VAULT_DIR / "01_Journaling/☆Karate"
ASSETS_DIR = KARATE_DIR / "assets"
INDEX_FILE = KARATE_DIR / "00_このフォルダ.md"
STATE_FILE = REPO_ROOT / ".jarvis_state/karate_advisor_sync.json"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import jarvis_grok_bot_cdp  # noqa: E402


def load_state() -> dict:
    if STATE_FILE.is_file():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"last_sync_at": None, "saved_notes": [], "saved_images": []}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_obsidian_draft(text: str) -> dict | None:
    """Parse title, date, category, and markdown body from Obsidian追記案."""
    marker = "## Obsidian追記案"
    if marker in text:
        content = text.split(marker, 1)[1].strip()
    else:
        # Fallback if the whole message is the note
        content = text.strip()

    # Extract code fences if present
    fence_m = re.search(r"```markdown\s*(.*?)\s*```", content, re.DOTALL)
    if fence_m:
        md_text = fence_m.group(1).strip()
    else:
        # If there's a title header #
        idx = content.find("# ")
        if idx != -1:
            md_text = content[idx:].strip()
        else:
            return None

    # Title
    first_line = md_text.splitlines()[0].strip()
    title = re.sub(r"^#+\s*", "", first_line)

    # Date
    date_m = re.search(r"調査日[:：]\s*(\d{4}[-/]\d{2}[-/]\d{2})", md_text)
    date_str = date_m.group(1).replace("/", "-") if date_m else datetime.now().strftime("%Y-%m-%d")

    # Category
    cat_m = re.search(r"カテゴリ[:：]\s*([^\n]+)", md_text)
    if cat_m and "骨" in cat_m.group(1):
        category = "骨と筋肉"
    elif cat_m and "和道" in cat_m.group(1):
        category = "和道流"
    elif "ピンアン" in title or "クーシャンクー" in title or "セイシャン" in title:
        category = "和道流"
    else:
        category = "骨と筋肉"

    # Generate filename
    # Extract main topic words from title
    main_title = title.split("（")[0].split("(")[0].strip()
    if not main_title:
        main_title = title.replace("（", "_").replace("）", "")
    safe_title = re.sub(r'[\\/*?:"<>|()（）,\s]+', "_", main_title).strip("_")
    date_compact = date_str.replace("-", "")
    filename = f"{safe_title}_{date_compact}.md"

    return {
        "title": title,
        "date": date_str,
        "category": category,
        "filename": filename,
        "md_text": md_text,
    }


def update_index_file(category: str, note_stem: str) -> None:
    if not INDEX_FILE.is_file():
        return
    text = INDEX_FILE.read_text(encoding="utf-8")
    link = f"[[{note_stem}]]"
    if link in text:
        return

    # Find category section
    cat_header = f"### {category}" if f"### {category}" in text else f"## {category}"
    if cat_header in text:
        parts = text.split(cat_header, 1)
        sub = parts[1]
        next_sec = re.search(r"\n##+\s+", sub)
        if next_sec:
            insert_pos = next_sec.start()
            new_sub = sub[:insert_pos].rstrip() + f"\n- {link}\n\n" + sub[insert_pos:]
            text = parts[0] + cat_header + new_sub
        else:
            text = text.rstrip() + f"\n- {link}\n"
    else:
        text = text.rstrip() + f"\n\n### {category}\n- {link}\n"

    INDEX_FILE.write_text(text, encoding="utf-8")
    print(f"Updated index {INDEX_FILE.name} with {link}")


async def fetch_karate_messages(g) -> list[dict]:
    """Retrieve messages and images from 空手アドバイザー."""
    await g.open_bot("空手アドバイザー")
    await asyncio.sleep(1.0)

    raw_items = await g.ev("""(() => {
        // Collect messages
        const articles = Array.from(document.querySelectorAll('article, [data-testid*="message"], .prose, div[class*="message"]'));
        const results = [];
        
        for (const el of articles) {
            const text = (el.innerText || '').trim();
            if (text.length < 30) continue;
            
            const imgs = Array.from(el.querySelectorAll('img')).map(img => ({
                alt: img.alt || '',
                src: img.src || '',
                isData: (img.src || '').startsWith('data:image')
            })).filter(i => i.isData || i.src.startsWith('http'));
            
            results.push({
                text: text,
                imgs: imgs
            });
        }
        return results;
    })()""")

    return raw_items or []


async def sync_karate_advisor(dry_run: bool = False, force: bool = False) -> int:
    state = load_state()
    saved_notes = set(state.get("saved_notes", []))
    saved_images = set(state.get("saved_images", []))

    print(f"Connecting to Grok Bot CDP...")
    try:
        ws, g = await jarvis_grok_bot_cdp.connect()
    except Exception as e:
        print(f"Cannot connect to Grok Bot CDP ({e}). Skipping Karate sync.")
        return 0

    try:
        items = await fetch_karate_messages(g)
    finally:
        await ws.close()

    if not items:
        print("No messages found in 空手アドバイザー.")
        return 0

    print(f"Retrieved {len(items)} messages from 空手アドバイザー.")

    synced_notes = []
    synced_files_for_ogd = []

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    for item in items:
        text = item["text"]
        imgs = item.get("imgs", [])

        # Check for Obsidian追記案
        parsed = parse_obsidian_draft(text)
        if not parsed:
            continue

        filename = parsed["filename"]
        cat_dir = KARATE_DIR / parsed["category"]
        cat_dir.mkdir(parents=True, exist_ok=True)
        target_path = cat_dir / filename
        rel_path = f"01_Journaling/☆Karate/{parsed['category']}/{filename}"

        if target_path.exists() and not force and rel_path in saved_notes:
            continue

        md_text = parsed["md_text"]

        # Handle associated images
        attached_images = []
        for img in imgs:
            alt = img["alt"] or "図解"
            src = img["src"]
            if src.startswith("data:image"):
                header, b64_data = src.split(",", 1)
                ext = "png" if "png" in header else "jpg"
                safe_alt = re.sub(r'[\\/*?:"<>|()（）]', "_", alt).strip("_")
                img_name = f"{parsed['filename'].replace('.md', '')}_{safe_alt}.{ext}"
                img_path = ASSETS_DIR / img_name
                rel_img_path = f"01_Journaling/☆Karate/assets/{img_name}"

                if not dry_run:
                    try:
                        img_path.write_bytes(base64.b64decode(b64_data))
                        print(f"Saved diagram image: {rel_img_path} ({img_path.stat().st_size} bytes)")
                        saved_images.add(rel_img_path)
                        synced_files_for_ogd.append(rel_img_path)
                        attached_images.append((img_name, alt))
                    except Exception as e:
                        print(f"Failed to decode image {img_name}: {e}")

        # Insert image link into markdown if images were found and not already present
        for img_name, alt in attached_images:
            link_md = f"\n\n### 視覚図解\n![{alt}](../assets/{img_name})\n"
            if img_name not in md_text:
                if "## 図解・参照" in md_text:
                    md_text = md_text.replace("## 図解・参照", f"## 図解・参照\n{link_md}")
                elif "## 3. 構造図解" in md_text:
                    md_text = md_text.replace("## 3. 構造図解", f"## 3. 構造図解\n{link_md}")
                else:
                    md_text = md_text.rstrip() + link_md

        print(f"{'[DRY-RUN] Would save' if dry_run else 'Saving'} note: {rel_path}")
        if not dry_run:
            target_path.write_text(md_text, encoding="utf-8")
            update_index_file(parsed["category"], target_path.stem)
            saved_notes.add(rel_path)
            synced_notes.append(rel_path)
            synced_files_for_ogd.append(rel_path)

    # Sync to OGD if new files were created
    if synced_files_for_ogd and not dry_run:
        print(f"\nTriggering jarvis_obsidian_ogd_retag.py for {len(synced_files_for_ogd)} files...")
        retag_script = REPO_ROOT / "scripts/jarvis_obsidian_ogd_retag.py"
        cmd = [
            "/Users/matsunomasaharu2/selenium_env/venv/bin/python",
            str(retag_script),
        ] + synced_files_for_ogd + ["01_Journaling/☆Karate/00_このフォルダ.md"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            print("OGD Retag output:\n" + res.stdout)
            if res.stderr:
                print("OGD Retag stderr:\n" + res.stderr)
        except Exception as e:
            print(f"Error calling OGD retag: {e}")

    # Update state
    if not dry_run:
        state["last_sync_at"] = datetime.now().isoformat()
        state["saved_notes"] = sorted(list(saved_notes))
        state["saved_images"] = sorted(list(saved_images))
        save_state(state)

    print(f"\nKarate Advisor Sync finished. New notes synced: {len(synced_notes)}")
    return len(synced_notes)


def main():
    parser = argparse.ArgumentParser(description="Sync Karate Advisor from Grok Bot to Obsidian & OGD")
    parser.add_argument("--dry-run", action="store_true", help="Preview sync without saving")
    parser.add_argument("--force", action="store_true", help="Force overwrite existing notes")
    args = parser.parse_args()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    res = loop.run_until_complete(sync_karate_advisor(dry_run=args.dry_run, force=args.force))
    sys.exit(0 if res >= 0 else 1)


if __name__ == "__main__":
    main()
