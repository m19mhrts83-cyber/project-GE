#!/usr/bin/env python3
"""
LINE からコピーしたテキスト（または標準入力・ファイル）を、パートナー別フォルダの
5.やり取り.md に追記する。個人LINEに公式APIがない前提の半自動用。

前提:
  - 連絡先一覧.yaml（デフォルトは 26_パートナー社への相談/000_共通）
  - Mac: クリップボードは pbpaste（--text-file / パイプで代替可）
  - pip install PyYAML（他スクリプトと同様。既存なら `./.venv_gmail/bin/python line_to_yoritoori_clip.py`）

使い方:
  # LINE でコピーしたあと（受信・貼り付け）
  python line_to_yoritoori_clip.py --partner Newtus

  # フォルダ直指定（YAML に無いグループ用フォルダなど）
  python line_to_yoritoori_clip.py --folder 950_LINE_案件名 --display-name "火災保険協議"

  # グループ見出し（--group-label ありで「LINE（グループ・貼り付け）」）
  python line_to_yoritoori_clip.py --partner Newtus --group-label "○○案件"

  # 送信した文面をコピーしたあと
  python line_to_yoritoori_clip.py --partner 806_神大家AI推進 --direction send

  # 4.送信下書き.txt をそのまま履歴に残す（LINE 送信前のメモ）
  python line_to_yoritoori_clip.py --partner ミニテック --direction draft

  python line_to_yoritoori_clip.py --partner LEAF --text-file ~/Desktop/line_export.txt
  echo "貼り付け本文" | python line_to_yoritoori_clip.py --folder 312_Newtus

環境変数（任意）:
  CONTACT_LIST_PATH, YORITOORI_BASE_PATH（yoritoori_send.py と同様）
  LINE_CLIP_PROCESSED_PATH（重複検知 JSON の保存先。未設定時は ~/.cursor/line_clip_processed.json）
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from yoritoori_utils import DRAFT_FILENAME, YORITOORI_FILENAME, make_summary

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent.parent / "C2_ルーティン作業" / "26_パートナー社への相談"
CONTACT_YAML = BASE_DIR / "000_共通" / "連絡先一覧.yaml"
DEFAULT_PROCESSED_JSON = Path.home() / ".cursor" / "line_clip_processed.json"

JST = ZoneInfo("Asia/Tokyo")


def load_env():
    env_path = SCRIPT_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*([^#=]+)\s*=\s*(.+?)\s*$", line)
        if m:
            key = m.group(1).strip()
            val = m.group(2).strip().strip("'\"")
            if val:
                os.environ[key] = val


load_env()

CONTACT_PATH = Path(os.environ.get("CONTACT_LIST_PATH", CONTACT_YAML))
BASE_PATH = Path(os.environ.get("YORITOORI_BASE_PATH", BASE_DIR))
PROCESSED_JSON = Path(os.environ.get("LINE_CLIP_PROCESSED_PATH", DEFAULT_PROCESSED_JSON))


def find_partner(partners: list, name_or_folder: str):
    """name または folder でパートナーを検索（yoritoori_send と同じ）。"""
    name_or_folder = (name_or_folder or "").strip()
    for p in partners:
        if p.get("name") == name_or_folder or p.get("folder") == name_or_folder:
            return p
    return None


def _flatten_notion_headings(body: str) -> str:
    if not body:
        return ""
    lines = body.split("\n")
    out = []
    for line in lines:
        if re.match(r"^### \d{4}/\d{2}/\d{2}", line):
            out.append(line)
        elif re.match(r"^### +", line):
            rest = re.sub(r"^### +\s*", "", line)
            out.append(f"**{rest}**" if rest else line)
        elif re.match(r"^## +", line):
            rest = re.sub(r"^## +\s*", "", line)
            out.append(f"**{rest}**" if rest else line)
        elif re.match(r"^# +", line):
            rest = re.sub(r"^# +\s*", "", line)
            out.append(f"**{rest}**" if rest else line)
        else:
            out.append(line)
    return "\n".join(out)


def _wrap_in_toggle(body: str) -> str:
    flattened = _flatten_notion_headings(body)
    return f"<details>\n<summary>本文を開く</summary>\n\n{flattened}\n\n</details>"


def insert_block_after_timeline_header(content: str, block: str) -> str:
    """yoritoori_send.append_sent_to_yoritoori と同様、時系列セクション先頭（新しい順）に挿入。"""
    marker = "## やり取り（時系列）"
    if marker not in content:
        return content + block

    start = content.find(marker)
    after_marker = content[start:]
    m = re.search(r"\n\n### [12]\d{3}/\d{2}/\d{2}", after_marker)
    if m:
        pos = start + m.start() + 2
        return content[:pos] + block.strip() + "\n\n" + content[pos:]
    pos = start + len(marker)
    return content[:pos].rstrip() + "\n\n" + block.strip() + "\n\n" + content[pos:].lstrip()


def parse_draft(draft_path: Path) -> tuple[str, str]:
    """4.送信下書き.txt を (subject, body) に。"""
    content = draft_path.read_text(encoding="utf-8")
    lines = content.strip().split("\n")
    subject = ""
    body_lines = []
    for i, line in enumerate(lines):
        if i == 0 and re.match(r"^件名[：:]\s*(.*)$", line):
            m = re.match(r"^件名[：:]\s*(.*)$", line)
            subject = (m.group(1) or "").strip()
        else:
            body_lines.append(line)
    body = "\n".join(body_lines).strip()
    return subject, body


def read_clipboard() -> str:
    if sys.platform != "darwin":
        print("エラー: クリップボード読み取りは macOS のみです。--text-file かパイプを使ってください。", file=sys.stderr)
        sys.exit(1)
    try:
        r = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"エラー: pbpaste に失敗しました: {e}", file=sys.stderr)
        sys.exit(1)
    return r.stdout or ""


def load_processed() -> dict:
    if not PROCESSED_JSON.exists():
        return {"entries": []}
    try:
        data = json.loads(PROCESSED_JSON.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("entries"), list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"entries": []}


def save_processed(data: dict) -> None:
    PROCESSED_JSON.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def is_duplicate(data: dict, folder: str, direction: str, body_hash: str) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    entries = data.get("entries", [])
    for e in entries:
        if not isinstance(e, dict):
            continue
        if e.get("folder") != folder or e.get("direction") != direction or e.get("hash") != body_hash:
            continue
        try:
            t = datetime.fromisoformat(e.get("ts", "").replace("Z", "+00:00"))
            if t >= cutoff:
                return True
        except (TypeError, ValueError):
            continue
    return False


def record_processed(data: dict, folder: str, direction: str, body_hash: str) -> None:
    entries = data.setdefault("entries", [])
    entries.append(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "folder": folder,
            "direction": direction,
            "hash": body_hash,
        }
    )
    entries = entries[-500:]
    data["entries"] = entries


def build_heading_line(
    date_str: str,
    display_name: str,
    direction: str,
    is_group: bool,
    group_label: str | None,
    body: str,
) -> str:
    summary = make_summary(body)
    if group_label:
        summary = f"{group_label} — {summary}"

    if direction == "draft":
        tag = "LINE（送信予定・下書き）"
    elif direction == "send":
        tag = "LINE（グループ・貼り付け・送信）" if is_group else "LINE（貼り付け・送信）"
    elif is_group:
        tag = "LINE（グループ・貼り付け）"
    else:
        tag = "LINE（貼り付け・受信）"

    return f"### {date_str}｜{display_name}｜{tag}｜{summary}"


def append_line_block(
    md_path: Path,
    heading_line: str,
    body: str,
    direction: str,
    draft_subject: str | None,
) -> None:
    subject_block = ""
    if direction == "draft" and draft_subject:
        subject_block = f"**件名**: {draft_subject}\n\n"

    body_display = _wrap_in_toggle(body)
    block = f"""

{heading_line}

{subject_block}{body_display}

---
"""
    content = md_path.read_text(encoding="utf-8")
    new_content = insert_block_after_timeline_header(content, block)
    md_path.write_text(new_content, encoding="utf-8")


def resolve_target(args) -> tuple[str, str]:
    """(folder, display_name_for_heading) を返す。"""
    if not CONTACT_PATH.exists():
        print(f"エラー: 連絡先一覧が見つかりません: {CONTACT_PATH}", file=sys.stderr)
        sys.exit(1)

    config = yaml.safe_load(CONTACT_PATH.read_text(encoding="utf-8")) or {}
    partners = config.get("partners", [])

    if args.folder:
        folder = args.folder.strip()
        name = (args.display_name or folder).strip()
        return folder, name

    partner = find_partner(partners, args.partner)
    if not partner:
        print(f"エラー: パートナー '{args.partner}' が見つかりません。", file=sys.stderr)
        sys.exit(1)
    return partner["folder"], partner.get("name") or partner["folder"]


def load_body_text(args, folder_path_str: str) -> tuple[str, str | None]:
    """
    追記する本文と、draft 時の件名（あれば）を返す。
    """
    draft_subject: str | None = None

    if args.direction == "draft":
        draft_path = BASE_PATH / folder_path_str / DRAFT_FILENAME
        if not draft_path.exists():
            print(f"エラー: {DRAFT_FILENAME} が見つかりません: {draft_path}", file=sys.stderr)
            sys.exit(1)
        subj, body = parse_draft(draft_path)
        draft_subject = subj or None
        if not body.strip():
            print("エラー: 送信下書きの本文が空です。", file=sys.stderr)
            sys.exit(1)
        return body, draft_subject

    if args.text_file:
        p = Path(args.text_file).expanduser()
        if not p.is_file():
            print(f"エラー: ファイルがありません: {p}", file=sys.stderr)
            sys.exit(1)
        return p.read_text(encoding="utf-8"), None

    if not sys.stdin.isatty():
        piped = sys.stdin.read()
        if piped.strip():
            return piped, None

    text = read_clipboard()
    return text, None


def main() -> None:
    parser = argparse.ArgumentParser(description="LINE 貼り付けテキストを 5.やり取り.md に追記")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--partner", help="連絡先一覧の name または folder")
    g.add_argument("--folder", help="追記先フォルダ名（例: 312_Newtus / 950_LINE_○○）")
    parser.add_argument("--display-name", help="--folder 指定時の見出し名（省略時は folder 名）")
    parser.add_argument(
        "--direction",
        choices=("receive", "send", "draft"),
        default="receive",
        help="receive=貼り付け受信, send=貼り付け送信, draft=4.送信下書き.txt を追記",
    )
    parser.add_argument("--group", action="store_true", help="グループトーク用見出し（LINE（グループ・貼り付け）等）")
    parser.add_argument("--group-label", help="グループ名・案件名（要約の先頭に付与。--group と併用可）")
    parser.add_argument("--text-file", help="本文ファイル（クリップボードの代わり）")
    parser.add_argument("--no-dedup", action="store_true", help="直近重複検知を無効化")
    args = parser.parse_args()

    folder, display_name = resolve_target(args)
    body, draft_subject = load_body_text(args, folder)

    if not body or not str(body).strip():
        print("エラー: 本文が空です。LINE でコピーするか --text-file / パイプで渡してください。", file=sys.stderr)
        sys.exit(1)

    gl = (args.group_label or "").strip()
    is_group = bool(args.group) or bool(gl)

    md_path = BASE_PATH / folder / YORITOORI_FILENAME
    if not md_path.exists():
        print(f"エラー: {YORITOORI_FILENAME} が見つかりません: {md_path}", file=sys.stderr)
        sys.exit(1)

    body_hash = sha256(body.encode("utf-8")).hexdigest()
    if not args.no_dedup:
        pdata = load_processed()
        if is_duplicate(pdata, folder, args.direction, body_hash):
            print("同一内容を直近ですでに追記済みのためスキップしました（--no-dedup で再追記可）。")
            return
    else:
        pdata = load_processed()

    date_str = datetime.now(JST).strftime("%Y/%m/%d %H:%M")
    heading = build_heading_line(
        date_str,
        display_name,
        args.direction,
        is_group,
        gl if gl else None,
        body,
    )

    append_line_block(md_path, heading, body, args.direction, draft_subject)
    record_processed(pdata, folder, args.direction, body_hash)
    save_processed(pdata)

    print(f"追記しました: {md_path}")
    print(f"  {heading[:80]}{'…' if len(heading) > 80 else ''}")


if __name__ == "__main__":
    main()
