#!/usr/bin/env python3
"""
LINE 送信（クリップボード半自動）。

Mac で書いた本文を pbcopy → iPhoneミラーリングの LINE に Cmd+V で貼るだけにする。
Mac版LINEは起動しない（CHRLINE とデスクトップ認証が競合するため）。

下書きの優先順位（--partner 時）:
  1. パートナーフォルダの 4.LINE送信下書き.txt（非空）
  2. 26直下の LINE送信下書き.txt（宛先が一致するとき）
  3. --text / --text-file / stdin

専用ハブ（コンパクト・26直下）:
  26_パートナー社への相談/LINE送信下書き.txt
  先頭行「宛先: Tcell」など → 本文。route: も可。

使い方:
  python line_clip_send.py --hub
  python line_clip_send.py --partner Tcell
  python line_clip_send.py --route 30空室相談G --text "本文"
  python line_clip_send.py --partner LEAF --skip-confirm --no-wait   # Jarvis 用（コピー＋前面化のみ）
  python line_clip_send.py --partner LEAF --record-only              # 貼付送信後のやり取り追記のみ
  python line_clip_send.py --partner Tcell --dry-run

環境変数:
  YORITOORI_BASE_PATH / CONTACT_LIST_PATH / LINE_OPEN_CHAT_ROUTES_YAML
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

from yoritoori_utils import (
    YORITOORI_FILENAME,
    default_yoritoori_base_dir,
    make_summary,
)

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = default_yoritoori_base_dir()
CONTACT_YAML = BASE_DIR / "000_共通" / "連絡先一覧.yaml"
HUB_DRAFT_NAME = "LINE送信下書き.txt"
PARTNER_LINE_DRAFT_NAME = "4.LINE送信下書き.txt"
DEFAULT_OPEN_CHAT_ROUTES = (
    Path.home() / "git-repos" / "line_unofficial_poc" / "open_chat_routes.yaml"
)

CONTACT_PATH = Path(os.environ.get("CONTACT_LIST_PATH", CONTACT_YAML))
BASE_PATH = Path(os.environ.get("YORITOORI_BASE_PATH", BASE_DIR))


def hub_draft_path() -> Path:
    """26直下を正。旧 000_共通 にあればフォールバック。"""
    primary = BASE_PATH / HUB_DRAFT_NAME
    if primary.is_file():
        return primary
    legacy = BASE_PATH / "000_共通" / HUB_DRAFT_NAME
    if legacy.is_file():
        return legacy
    return primary


def trigger_editor_save_all() -> bool:
    """Cursor/VS Code の Save All（未保存下書きをディスクへ）。失敗しても続行可。"""
    if sys.platform != "darwin":
        return True
    script = r"""
    on trySaveAll(appName)
        tell application "System Events"
            if not (exists process appName) then return false
            tell process appName
                set frontmost to true
                delay 0.2
                try
                    click menu item "Save All" of menu "File" of menu bar 1
                    return true
                end try
                try
                    keystroke "s" using {command down, option down}
                    return true
                end try
            end tell
        end tell
        return false
    end trySaveAll
    if trySaveAll("Cursor") then return "ok"
    if trySaveAll("Code") then return "ok"
    return "ng"
    """
    try:
        r = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return (r.stdout or "").strip() == "ok"
    except (OSError, subprocess.TimeoutExpired):
        return False


def find_partner(partners: list, name_or_folder: str):
    needle = (name_or_folder or "").strip()
    if not needle:
        return None
    for p in partners:
        if p.get("name") == needle or p.get("folder") == needle:
            return p
    low = needle.lower()
    for p in partners:
        name = str(p.get("name") or "")
        folder = str(p.get("folder") or "")
        if low in name.lower() or low in folder.lower():
            return p
    return None


def open_chat_routes_path() -> Path:
    env = (os.environ.get("LINE_OPEN_CHAT_ROUTES_YAML") or "").strip()
    if env:
        return Path(env).expanduser()
    return DEFAULT_OPEN_CHAT_ROUTES


def load_open_chat_routes() -> list[dict]:
    path = open_chat_routes_path()
    if not path.is_file():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return []
    routes = data.get("routes") if isinstance(data, dict) else data
    return routes if isinstance(routes, list) else []


def find_route(routes: list[dict], needle: str) -> dict | None:
    n = (needle or "").strip()
    if not n:
        return None
    for r in routes:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("id") or "")
        org = str(r.get("org_label") or "")
        title = str(r.get("title_substring") or "")
        if n == rid or n == org or n == title:
            return r
    low = n.lower()
    for r in routes:
        if not isinstance(r, dict):
            continue
        blob = " ".join(
            str(r.get(k) or "") for k in ("id", "org_label", "title_substring")
        ).lower()
        if low in blob:
            return r
    return None


def _strip_hash_comment_lines(text: str) -> str:
    """行頭 # の説明コメントを除く（宛先メタは別処理）。"""
    out: list[str] = []
    for line in (text or "").splitlines():
        if re.match(r"^\s*#", line):
            continue
        out.append(line)
    return "\n".join(out).strip()


def parse_hub_draft(text: str) -> tuple[str, str, str]:
    """
    ハブ下書きをパース。
    Returns: (dest_kind, dest_value, body)
      dest_kind: partner | route | ""
    """
    lines = (text or "").splitlines()
    dest_kind = ""
    dest_value = ""
    body_lines: list[str] = []
    header_done = False
    for line in lines:
        s = line.strip()
        if not header_done:
            if not s or re.match(r"^\s*#", line):
                continue
            m = re.match(r"^(?:#\s*)?(宛先|パートナー|partner)\s*[：:]\s*(.*)$", s, re.I)
            if m and not dest_kind:
                dest_kind = "partner"
                dest_value = (m.group(2) or "").strip()
                continue
            m = re.match(r"^(?:#\s*)?(route|ルート|オプチャ)\s*[：:]\s*(.+)$", s, re.I)
            if m and not dest_kind:
                dest_kind = "route"
                dest_value = m.group(2).strip()
                continue
            header_done = True
            if re.match(r"^\s*#", line):
                continue
            body_lines.append(line)
            continue
        if re.match(r"^\s*#", line):
            continue
        body_lines.append(line)
    body = "\n".join(body_lines).strip()
    return dest_kind, dest_value, body


def parse_line_body(text: str) -> str:
    """パートナー用 LINE 下書き（件名行があれば捨てて本文のみ）。"""
    raw = text or ""
    lines = raw.splitlines()
    if lines and re.match(r"^件名[：:]", lines[0].strip()):
        return _strip_hash_comment_lines("\n".join(lines[1:]))
    # ハブ形式が混在していても本文だけ取る
    _k, _v, body = parse_hub_draft(raw)
    return body


def pbcopy(text: str) -> None:
    if sys.platform != "darwin":
        raise RuntimeError("pbcopy は macOS のみです")
    r = subprocess.run(["pbcopy"], input=text, text=True, capture_output=True, timeout=10)
    if r.returncode != 0:
        raise RuntimeError(f"pbcopy 失敗: {(r.stderr or '').strip()}")


def bring_iphone_mirroring_front() -> str:
    """iPhoneミラーリングを前面化。成功メッセージを返す。"""
    if sys.platform != "darwin":
        return "（macOS以外のため前面化スキップ）"
    candidates = [
        "iPhone Mirroring",
        "iPhoneミラーリング",
        "スクリーンミラーリング",
    ]
    for name in candidates:
        try:
            r = subprocess.run(
                ["open", "-a", name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if r.returncode == 0:
                return f"前面化: {name}"
        except (OSError, subprocess.TimeoutExpired):
            continue
    # bundle id フォールバック
    try:
        r = subprocess.run(
            ["open", "-b", "com.apple.ScreenContinuity"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode == 0:
            return "前面化: com.apple.ScreenContinuity"
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "警告: iPhoneミラーリングを開けませんでした（手動で前面にしてください）"


def insert_block_after_timeline_header(content: str, block: str) -> str:
    marker = "## やり取り（時系列）"
    if marker not in content:
        return content.rstrip() + "\n\n" + block.strip() + "\n"
    start = content.find(marker)
    after_marker = content[start:]
    m = re.search(r"\n\n### [12]\d{3}/\d{2}/\d{2}", after_marker)
    if m:
        pos = start + m.start() + 2
        return content[:pos] + block.strip() + "\n\n" + content[pos:]
    pos = start + len(marker)
    return content[:pos].rstrip() + "\n\n" + block.strip() + "\n\n" + content[pos:].lstrip()


def append_line_sent(md_path: Path, display_name: str, body: str) -> bool:
    if not md_path.is_file():
        print(f"エラー: {YORITOORI_FILENAME} がありません: {md_path}", file=sys.stderr)
        return False
    date_str = datetime.now().strftime("%Y/%m/%d %H:%M")
    summary = make_summary(body)
    block = f"""

### {date_str}｜{display_name}｜自分から送信（LINE）｜{summary}

{body}

---
"""
    content = md_path.read_text(encoding="utf-8")
    md_path.write_text(insert_block_after_timeline_header(content, block), encoding="utf-8")
    return True


def resolve_md_for_partner(partner: dict) -> Path:
    return BASE_PATH / partner["folder"] / YORITOORI_FILENAME


def resolve_md_for_route(route: dict) -> Path | None:
    raw = (route.get("output_md") or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def resolve_kanji_md() -> Path | None:
    """815 東海飲み会幹事のやり取り（フォルダ名ゆれ対応）。"""
    base = BASE_PATH / "815_神大家オプチャ"
    if not base.is_dir():
        # NFC/NFD ゆれ
        for p in BASE_PATH.iterdir():
            if p.is_dir() and "815" in p.name and "オプチャ" in p.name:
                base = p
                break
        else:
            return None
    for child in base.iterdir():
        if child.is_dir() and "幹事" in child.name:
            md = child / YORITOORI_FILENAME
            if md.is_file():
                return md
    return None


def load_partners() -> list:
    if not CONTACT_PATH.is_file():
        print(f"エラー: 連絡先一覧がありません: {CONTACT_PATH}", file=sys.stderr)
        sys.exit(1)
    data = yaml.safe_load(CONTACT_PATH.read_text(encoding="utf-8"))
    partners = data.get("partners") if isinstance(data, dict) else data
    return partners if isinstance(partners, list) else []


def read_text_arg(args) -> str | None:
    if args.text is not None:
        return args.text
    if args.text_file:
        return Path(args.text_file).expanduser().read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return None


def resolve_body_and_target(args, partners: list, routes: list[dict]):
    """
    Returns dict with keys:
      body, display_name, md_path, draft_path (optional), source_label
    """
    inline = read_text_arg(args)

    if args.record_only and not (args.partner or args.route or args.hub):
        print("エラー: --record-only には --partner / --route / --hub のいずれかが必要です。", file=sys.stderr)
        sys.exit(1)

    # --- hub ---
    if args.hub or (not args.partner and not args.route and inline is None):
        hub_path = hub_draft_path()
        if inline is None:
            if not hub_path.is_file():
                print(f"エラー: ハブ下書きがありません: {hub_path}", file=sys.stderr)
                sys.exit(1)
            trigger_editor_save_all()
            raw = hub_path.read_text(encoding="utf-8")
        else:
            raw = inline
            hub_path = None
        kind, value, body = parse_hub_draft(raw)
        if not body.strip():
            print("エラー: 本文が空です（ハブ下書き）。", file=sys.stderr)
            sys.exit(1)
        if args.partner:
            partner = find_partner(partners, args.partner)
            if not partner:
                print(f"エラー: パートナー '{args.partner}' が見つかりません。", file=sys.stderr)
                sys.exit(1)
            return {
                "body": body,
                "display_name": partner.get("name") or args.partner,
                "md_path": resolve_md_for_partner(partner),
                "draft_path": hub_path,
                "source_label": f"ハブ+--partner {args.partner}",
            }
        if args.route or kind == "route":
            needle = args.route or value
            route = find_route(routes, needle)
            if not route:
                # 幹事特例
                if "幹事" in needle:
                    md = resolve_kanji_md()
                    if md:
                        return {
                            "body": body,
                            "display_name": "815東海飲み会幹事",
                            "md_path": md,
                            "draft_path": hub_path,
                            "source_label": f"ハブ(幹事) {needle}",
                        }
                print(f"エラー: route '{needle}' が見つかりません。", file=sys.stderr)
                sys.exit(1)
            md = resolve_md_for_route(route)
            return {
                "body": body,
                "display_name": route.get("org_label") or route.get("id") or needle,
                "md_path": md,
                "draft_path": hub_path,
                "source_label": f"ハブ+route {needle}",
            }
        if kind == "partner" and value:
            if "幹事" in value:
                md = resolve_kanji_md()
                if md:
                    return {
                        "body": body,
                        "display_name": "815東海飲み会幹事",
                        "md_path": md,
                        "draft_path": hub_path,
                        "source_label": f"ハブ宛先 {value}",
                    }
            # オプチャ名っぽいとき route も試す
            route = find_route(routes, value)
            if route:
                return {
                    "body": body,
                    "display_name": route.get("org_label") or route.get("id") or value,
                    "md_path": resolve_md_for_route(route),
                    "draft_path": hub_path,
                    "source_label": f"ハブ宛先(route解釈) {value}",
                }
            partner = find_partner(partners, value)
            if not partner:
                print(f"エラー: 宛先 '{value}' が連絡先にも route にもありません。", file=sys.stderr)
                sys.exit(1)
            return {
                "body": body,
                "display_name": partner.get("name") or value,
                "md_path": resolve_md_for_partner(partner),
                "draft_path": hub_path,
                "source_label": f"ハブ宛先 {value}",
            }
        print(
            "エラー: ハブ下書きに「宛先: …」または「route: …」を書いてください"
            "（または --partner / --route を指定）。",
            file=sys.stderr,
        )
        sys.exit(1)

    # --- route ---
    if args.route:
        route = find_route(routes, args.route)
        if not route and "幹事" in args.route:
            md = resolve_kanji_md()
            if not md:
                print("エラー: 幹事フォルダのやり取り.md が見つかりません。", file=sys.stderr)
                sys.exit(1)
            body = (inline or "").strip()
            if not body:
                print("エラー: --route 幹事 には --text か stdin で本文が必要です。", file=sys.stderr)
                sys.exit(1)
            return {
                "body": parse_line_body(body),
                "display_name": "815東海飲み会幹事",
                "md_path": md,
                "draft_path": None,
                "source_label": f"--route {args.route}",
            }
        if not route:
            print(f"エラー: route '{args.route}' が見つかりません。", file=sys.stderr)
            sys.exit(1)
        body = (inline or "").strip()
        if not body:
            print("エラー: --route には --text / --text-file / stdin で本文を渡してください。", file=sys.stderr)
            sys.exit(1)
        return {
            "body": parse_line_body(body),
            "display_name": route.get("org_label") or route.get("id") or args.route,
            "md_path": resolve_md_for_route(route),
            "draft_path": None,
            "source_label": f"--route {args.route}",
        }

    # --- partner ---
    partner = find_partner(partners, args.partner)
    if not partner:
        print(f"エラー: パートナー '{args.partner}' が見つかりません。", file=sys.stderr)
        sys.exit(1)
    folder = BASE_PATH / partner["folder"]
    line_draft = folder / PARTNER_LINE_DRAFT_NAME
    hub_path = hub_draft_path()

    body = None
    draft_path = None
    source = ""

    if inline is not None and inline.strip():
        body = parse_line_body(inline)
        source = "--text"
    else:
        trigger_editor_save_all()
        if line_draft.is_file():
            raw = line_draft.read_text(encoding="utf-8")
            b = parse_line_body(raw)
            if b.strip():
                body = b
                draft_path = line_draft
                source = PARTNER_LINE_DRAFT_NAME
        if body is None and hub_path.is_file():
            kind, value, b = parse_hub_draft(hub_path.read_text(encoding="utf-8"))
            if b.strip() and (
                not value
                or find_partner(partners, value) == partner
                or (partner.get("name") or "") in value
                or (partner.get("folder") or "") in value
            ):
                # 宛先未記入でも --partner 指定時はハブ本文を使う（明示 partner 優先）
                if not value or find_partner(partners, value) == partner or (partner.get("name") or "") in value:
                    body = b
                    draft_path = hub_path
                    source = f"{HUB_DRAFT_NAME}（--partner {args.partner}）"
                elif kind == "partner" and find_partner(partners, value) == partner:
                    body = b
                    draft_path = hub_path
                    source = HUB_DRAFT_NAME

    if not body or not body.strip():
        print(
            f"エラー: 本文が空です。次のいずれかに書いてください:\n"
            f"  - {line_draft}\n"
            f"  - {hub_path}（宛先: {partner.get('name')}）\n"
            f"  - --text …",
            file=sys.stderr,
        )
        sys.exit(1)

    return {
        "body": body.strip(),
        "display_name": partner.get("name") or args.partner,
        "md_path": resolve_md_for_partner(partner),
        "draft_path": draft_path,
        "source_label": source or "--partner",
    }


def preview(target: dict) -> None:
    body = target["body"]
    print("─" * 40)
    print(f"宛先表示名: {target['display_name']}")
    print(f"記録先: {target['md_path']}")
    print(f"本文ソース: {target['source_label']}")
    print("─" * 40)
    print(body)
    print("─" * 40)
    print(f"（{len(body)} 文字）")


def confirm_yes(prompt: str) -> bool:
    if sys.stdin is None or not sys.stdin.isatty():
        print("エラー: 非対話のため確認できません。--skip-confirm を付けてください。", file=sys.stderr)
        sys.exit(1)
    ans = input(prompt).strip().lower()
    return ans in ("y", "yes", "ｙ")


def main() -> int:
    parser = argparse.ArgumentParser(description="LINE 送信（クリップボード半自動）")
    parser.add_argument("--partner", help="パートナー名またはフォルダ（例: Tcell, LEAF）")
    parser.add_argument("--route", help="815オプチャ route id / 表示名（例: 30空室相談G）")
    parser.add_argument("--hub", action="store_true", help="26直下の LINE送信下書き.txt を使う")
    parser.add_argument("--text", help="本文を直接指定")
    parser.add_argument("--text-file", help="本文ファイル")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-confirm", action="store_true", help="プレビュー後の y/N を省略")
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="貼付後の Enter 待ちをしない（Jarvis: コピー＋ミラーリング前面化のみ）",
    )
    parser.add_argument(
        "--record-only",
        action="store_true",
        help="クリップボード操作なし。やり取り.md へ送信記録のみ（貼付送信後）",
    )
    parser.add_argument(
        "--clear-draft",
        action="store_true",
        help="記録成功後、使った下書きファイルの本文をクリア（宛先行は残す）",
    )
    args = parser.parse_args()

    if not args.partner and not args.route and not args.hub and read_text_arg(args) is None:
        # 引数なし → ハブ既定
        args.hub = True

    partners = load_partners()
    routes = load_open_chat_routes()
    target = resolve_body_and_target(args, partners, routes)
    preview(target)

    if args.dry_run:
        print("dry-run: コピー・前面化・追記はしません。")
        return 0

    if args.record_only:
        if not args.skip_confirm and not confirm_yes("この内容をやり取り.md に送信記録しますか？ (y/N): "):
            print("中止しました。")
            return 1
        md = target["md_path"]
        if md is None:
            print("エラー: 記録先 MD がありません。", file=sys.stderr)
            return 1
        if append_line_sent(md, target["display_name"], target["body"]):
            print(f"やり取りに追記しました: {md}")
            _maybe_clear_draft(target, args)
            return 0
        return 1

    if not args.skip_confirm and not confirm_yes("クリップボードにコピーしてミラーリングを前面にしますか？ (y/N): "):
        print("中止しました。")
        return 1

    try:
        pbcopy(target["body"])
    except RuntimeError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1
    print("クリップボードにコピーしました。")
    msg = bring_iphone_mirroring_front()
    print(msg)
    print()
    print("次の操作:")
    print("  1) LINE で送りたいトークを開く")
    print("  2) 入力欄をタップ／クリック")
    print("  3) Cmd+V で貼り付け → 送信")
    print()

    if args.no_wait:
        print("（--no-wait）記録は後で --record-only を実行してください。")
        print("例: python line_clip_send.py --partner … --record-only --skip-confirm")
        return 0

    if sys.stdin is None or not sys.stdin.isatty():
        print("非対話のため Enter 待ちをスキップ。記録する場合は --record-only を実行してください。")
        return 0

    ans = input("LINE に貼り付けて送信したら Enter（記録しない場合は n）: ").strip().lower()
    if ans in ("n", "no", "ｎ"):
        print("記録せず終了しました。")
        return 0
    md = target["md_path"]
    if md is None:
        print("エラー: 記録先 MD がありません。", file=sys.stderr)
        return 1
    if append_line_sent(md, target["display_name"], target["body"]):
        print(f"やり取りに追記しました: {md}")
        _maybe_clear_draft(target, args)
        return 0
    return 1


def _maybe_clear_draft(target: dict, args) -> None:
    if not args.clear_draft:
        return
    path = target.get("draft_path")
    if not path or not Path(path).is_file():
        return
    path = Path(path)
    raw = path.read_text(encoding="utf-8")
    if path.name == HUB_DRAFT_NAME:
        kind, value, _body = parse_hub_draft(raw)
        if kind == "route":
            header = f"route: {value}\n\n"
        elif kind == "partner" or value:
            header = f"宛先: {value}\n\n"
        else:
            header = "宛先: \n\n"
        path.write_text(header, encoding="utf-8")
    else:
        path.write_text("", encoding="utf-8")
    print(f"下書きをクリアしました: {path}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n中断しました。", file=sys.stderr)
        raise SystemExit(130)
