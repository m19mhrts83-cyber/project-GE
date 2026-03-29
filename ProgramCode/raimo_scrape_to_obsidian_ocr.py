#!/usr/bin/env python3
"""
raiMO（raimo.buzz）の lessonPage を開いて、
 - 折りたたみ（accordion/collapsible）をクリックで展開
 - 展開後の画面をスクショ（full page）
 - tesseract で OCR（--psm 11）
 - Obsidian向け Markdown と画像（<img>）をローカル保存

用途:
  まず 1-1-1 / 1-1-2 だけデバッグして、本文の欠け具合と画像リンクが問題ないか確認する。

注意:
  - 本スクリプトは「文字が画像として表示される」前提で OCR します。
  - 画像のダウンロードは認証が必要な場合があるため、Playwrightの同一セッション（ログイン済み）
    で取得する想定です。
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
import time
import os
import urllib.parse
from dataclasses import dataclass
from pathlib import Path


def slugify_filename(name: str) -> str:
    # Obsidianのファイル名として安全な文字に寄せる
    name = name.strip()
    name = re.sub(r"[\/\\:\*\?\"<>\|]", "_", name)
    # 連続空白を圧縮
    name = re.sub(r"\s+", " ", name)
    return name


def lesson_slug_from_title(title: str) -> str | None:
    # 例: "【1-1-3】本講座で修得する具体的デジタルスキル一覧 2:59"
    m = re.search(r"【\s*(\d+-\d+-\d+)\s*】", title)
    return m.group(1) if m else None


def tesseract_ocr(image_path: Path, *, lang: str, psm: int) -> str:
    """
    tesseract CLI を使って OCR する。
    依存を増やさない（pytesseract を入れない）ため subprocess に寄せる。
    """
    cmd = [
        "tesseract",
        str(image_path),
        "stdout",
        "-l",
        lang,
        "--psm",
        str(psm),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        # OCR失敗時も落とさず、エラー文を本文に残す（デバッグ用）
        err = res.stderr.strip() or res.stdout.strip()
        return f"[OCR エラー]\n{err}\n"
    return (res.stdout or "").strip()


def safe_relpath(from_path: Path, to_path: Path) -> str:
    # Obsidian で相対リンクが効くようにする
    try:
        rel = os.path.relpath(str(to_path), start=str(from_path.parent))
        return rel.replace("\\", "/")
    except Exception:
        return to_path.as_posix()


@dataclass(frozen=True)
class LessonIds:
    category_id: str
    lesson_page_id: str


def build_lesson_url(ids: LessonIds) -> str:
    return f"https://raimo.buzz/lessons?categoryId={ids.category_id}&lessonPageId={ids.lesson_page_id}"


def expand_collapsibles(page) -> list[str]:
    """
    展開クリック候補を当てに行く（完全固定ではなく「候補探索」）。
    戻り値: クリックできた要素の説明（デバッグ用）
    """
    # まず定番候補（今回のページで出てきた系統）
    candidates = [
        "解説",
        "CHECK",
        "SUMMARY",
        "講座のまとめ",
        "振り返り",
        "理解度チェック",
        "この講座でできるようになること",
        "このレッスンの目的",
        "このレッスンで学ぶこと",
        "この講座で理解したこと",
        "覚えておくべきキーワード",
    ]

    clicked: list[str] = []

    # aria-expanded が false のものを優先
    # （これがDOMに埋まってない場合もあるので、次の候補探索へ続ける）
    try:
        items = page.locator("[aria-expanded='false']").all()
        for el in items:
            try:
                el.click(timeout=1500)
                txt = (el.inner_text(timeout=1500) or "").strip().replace("\n", " ")
                clicked.append(f"aria-expanded false: {txt[:60]}")
            except Exception:
                pass
    except Exception:
        pass

    # 次に、ボタン/summary/role=button を列挙して候補文字列を含むものをクリック
    selectors = "button, summary, [role='button']"
    try:
        els = page.locator(selectors).all()
        for el in els:
            try:
                txt = (el.inner_text(timeout=1500) or "").strip()
                if not txt:
                    continue
                if any(c in txt for c in candidates):
                    el.click(timeout=1500)
                    clicked.append(f"text match: {txt[:60]}")
            except Exception:
                continue
    except Exception:
        pass

    return clicked


def is_likely_login_page(page) -> bool:
    url = page.url or ""
    if "/login" in url:
        return True
    # タイトルや見出しでも雑に判定（ログインページでよく出る語）
    try:
        t = page.title() or ""
        if "ログイン" in t:
            return True
    except Exception:
        pass
    return False


def fill_login_form(page, *, email: str, password: str) -> bool:
    """
    ログインページで email/password 入力欄を探して入力し、ログインボタンを押す。
    セレクタは固定にせず、input[type=password] とその他の input を使って推定する。
    """
    # まず placeholder で直接当てる（ログインUIが固定なら最短）
    email_loc = None
    pass_loc = None
    try:
        loc = page.locator("input[placeholder*='メール']").first
        if loc.count() > 0:
            email_loc = loc
    except Exception:
        pass
    try:
        loc = page.locator("input[placeholder*='パスワード']").first
        if loc.count() > 0:
            pass_loc = loc
    except Exception:
        pass

    # placeholder で取れない場合は visible input から推定
    if email_loc is None or pass_loc is None:
        try:
            inputs = page.locator("input").all()
        except Exception:
            return False

        for loc in inputs:
            try:
                if not loc.is_visible():
                    continue
                itype = (loc.get_attribute("type") or "").lower()
                placeholder = (loc.get_attribute("placeholder") or "").strip()
                aria_label = (loc.get_attribute("aria-label") or "").strip()
                name_attr = (loc.get_attribute("name") or "").strip()

                text_hint = placeholder or aria_label or name_attr

                if itype == "password" or "パスワード" in text_hint:
                    if pass_loc is None:
                        pass_loc = loc
                elif itype in ("email", "text") or "メール" in text_hint:
                    if email_loc is None:
                        email_loc = loc
            except Exception:
                continue

    # fallback: visible inputsの先頭/パスワード
    if pass_loc is None:
        try:
            pass_loc = page.locator("input[type='password']").first
        except Exception:
            pass_loc = None
    if email_loc is None:
        try:
            email_loc = page.locator("input[type='email']").first
        except Exception:
            email_loc = None
    # 最終fallback: visible input のうちパスワード以外をメール扱い
    if email_loc is None:
        try:
            visible_inputs = page.locator("input").filter(has_text="").all()
        except Exception:
            visible_inputs = []
        if visible_inputs:
            for loc in visible_inputs:
                try:
                    if loc.is_visible():
                        email_loc = loc
                        break
                except Exception:
                    continue

    if email_loc is None or pass_loc is None:
        return False

    try:
        email_loc.click(timeout=3000)
        email_loc.fill(email)
        pass_loc.click(timeout=3000)
        pass_loc.fill(password)
    except Exception:
        return False

    # デバッグ: 本当に値が入っているか確認
    try:
        email_val = (email_loc.input_value() or "").strip()
        pass_val = (pass_loc.input_value() or "").strip()
        print(
            f"[DEBUG] auto-login fill: email_len={len(email_val)} pass_len={len(pass_val)}",
            flush=True,
        )
        if not email_val or not pass_val:
            return False
    except Exception:
        # input_value が読めないケースでも、入力だけは試したので継続
        pass

    # submitボタン（複数候補で確実に押す）
    submitted = False
    try:
        btn = page.locator("button[type='submit']").first
        if btn.count() == 0:
            btn = page.locator("button:has-text('ログイン')").first
        if btn.count() == 0:
            btn = page.locator("button:has-text('Login')").first
        if btn.count() > 0:
            btn.click(timeout=5000)
            submitted = True
    except Exception:
        submitted = False

    if not submitted:
        try:
            pass_loc.press("Enter")
            submitted = True
        except Exception:
            submitted = False

    # 送信後の遷移待ち（ログイン完了が反映されるまで）
    try:
        page.wait_for_timeout(2000)
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass

    return submitted


def load_env_file(path: Path) -> None:
    """
    ローカルの .env から環境変数を読み込む（Git共有しない前提）。

    形式:
      RAIMO_LOGIN_EMAIL=xxx
      RAIMO_LOGIN_PASSWORD=yyy
      # コメント
      export RAIMO_LOGIN_EMAIL=xxx
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        key = k.strip()
        val = v.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, val)


def wait_until_lesson_loaded(
    page,
    *,
    target_url: str,
    timeout_seconds: int,
    expected_lesson_page_id: str,
    skip_goto_when_login: bool = False,
) -> bool:
    """
    ログインが完了して lessonPageId のページへ戻っているかを一定時間待つ。
    """
    start = time.time()
    expected_fragment = f"lessonPageId={expected_lesson_page_id}"
    next_retry_goto_at = start + 15  # auto-loginで遷移しない場合に備えた再goto

    while time.time() - start < timeout_seconds:
        try:
            if ("raimo.buzz/lessons" in page.url) and (expected_fragment in page.url):
                return True
            if is_likely_login_page(page):
                if not skip_goto_when_login:
                    # 同一sessionでログイン状態になったタイミングで遷移するように再goto
                    page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_load_state("networkidle", timeout=25000)
                else:
                    # ログインページのまま goto を繰り返すと、押下/遷移の反映を邪魔する可能性があるため
                    # 直近では抑制しつつ、一定間隔でリトライする。
                    now = time.time()
                    if now >= next_retry_goto_at:
                        try:
                            page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                            page.wait_for_load_state("networkidle", timeout=25000)
                        except Exception:
                            pass
                        next_retry_goto_at = now + 15
                    time.sleep(3)
                    continue
            else:
                # それ以外（Myプロンプト等）に飛んだ場合は戻す
                page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_load_state("networkidle", timeout=25000)
        except Exception:
            # 失敗しても待機を継続（再試行）
            pass

        time.sleep(3)

    return False


def collect_page_images_and_download(page, *, assets_lesson_dir: Path) -> tuple[list[Path], dict[str, Path]]:
    """
    ページ内の <img src="..."> を回収し、ローカル保存する。
    """
    assets_lesson_dir.mkdir(parents=True, exist_ok=True)

    img_srcs = []
    try:
        # src属性をまとめて回収
        for i in range(page.locator("img").count()):
            img = page.locator("img").nth(i)
            src = (img.get_attribute("src") or "").strip()
            if src:
                img_srcs.append(src)
    except Exception:
        # 最悪ケース（画像保存はデバッグ対象なので継続）
        img_srcs = []

    # 重複排除（順序保持）
    seen = set()
    uniq_srcs = []
    for s in img_srcs:
        if s in seen:
            continue
        seen.add(s)
        uniq_srcs.append(s)

    saved: list[Path] = []
    src_to_path: dict[str, Path] = {}
    for idx, src in enumerate(uniq_srcs, start=1):
        if src.startswith("data:"):
            continue
        # 相対URL対策
        abs_url = urllib.parse.urljoin(page.url, src)

        # 拡張子推定
        parsed = urllib.parse.urlparse(abs_url)
        ext = Path(parsed.path).suffix.lower()
        if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            ext = ".jpg"

        out_path = assets_lesson_dir / f"img_{idx:03d}{ext}"

        try:
            # Playwrightのリクエストで認証Cookie込みにする
            resp = page.request.get(abs_url, timeout=15000)
            if not resp.ok:
                continue
            out_path.write_bytes(resp.body())
            saved.append(out_path)
            src_to_path[abs_url] = out_path
        except Exception:
            continue

    return saved, src_to_path


def extract_dom_sequence(page) -> list[dict]:
    """
    main/article内を DOM順に `h1-h6/p/li/img` で列挙し、
    テキストはtype=text、画像はtype=img で返す。
    """
    js = r"""
    () => {
      const container =
        document.querySelector('main') ||
        document.querySelector('article') ||
        document.body;
      const els = Array.from(container.querySelectorAll('h1,h2,h3,h4,h5,h6,p,li,div,section,article,img'));
      return els.map(el => {
        if (el.tagName === 'IMG') {
          const src = el.getAttribute('src') || '';
          const currentSrc = el.currentSrc || '';
          return {
            type: 'img',
            src: (currentSrc || src || '').trim(),
            alt: (el.getAttribute('alt') || '').trim(),
          };
        }
        const text = (el.innerText || '').trim();
        return { type: 'text', text };
      }).filter(x => x.type === 'img' || (x.text && x.text.length > 0));
    }
    """
    seq = page.evaluate(js)
    if not isinstance(seq, list):
        return []
    return seq


def filter_ui_noise(text: str) -> str | None:
    """
    プレイヤーUI/メニューなど本文ではない文字列を簡易除去。
    """
    t = text.strip()
    if not t:
        return None
    noise_exact = {
        "Play",
        "Mute",
        "Settings",
        "Quality",
        "Speed",
        "Normal >",
        "PIP",
        "Enter fullscreen",
        "前の講座",
        "次の講座",
        "目次",
        "学習済み",
        "共有プロンプト",
        "Myプロンプト",
        "共有ミニアプリ",
        "Myミニアプリ",
        "便利ツール",
        "代理店マニュアル",
        "管理者メニュー",
        "ヘルプ",
        "松",
        "学習",
    }
    if t in noise_exact:
        return None
    if re.fullmatch(r"\d{1,3}%", t):
        return None
    if re.fullmatch(r"\d{1,2}:\d{2}", t):
        return None
    if len(t) <= 6 and t.isascii():
        return None
    return t


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--category-id", required=True)
    ap.add_argument("--lesson-page-id", required=True)

    ap.add_argument(
        "--out-md-dir",
        required=True,
        help="1ページ=1Markdownの出力先ディレクトリ（例: .../01_講義ノート/第01章_導入）",
    )
    ap.add_argument(
        "--assets-images-root",
        required=True,
        help="99_assets/images のルート（例: .../RAIMO講座/99_assets/images）",
    )

    ap.add_argument(
        "--debug-dir",
        default=None,
        help="スクショや中間出力を保存するデバッグディレクトリ（省略時は out-md-dir 配下に作成）",
    )
    ap.add_argument(
        "--ocr-lang",
        default="jpn",
        help="tesseract -l の指定（例: jpn, jpn+eng など）",
    )
    ap.add_argument("--ocr-psm", type=int, default=11)
    ap.add_argument("--overwrite", action="store_true", help="既存 md を上書きする（デバッグ時は通常OFF推奨）")

    ap.add_argument(
        "--prefer-dom",
        action="store_true",
        help="展開後に DOM の innerText を優先取得し、一定以上取れたら OCR をスキップする",
    )
    ap.add_argument(
        "--dom-min-length",
        type=int,
        default=800,
        help="DOM本文として採用する最低文字数（--prefer-dom 時）",
    )

    ap.add_argument(
        "--inline-images",
        action="store_true",
        help="画像を本文中の出現位置に差し込み（DOM順）。コードブロックを画像境界で分割してレンダリングする。",
    )

    ap.add_argument(
        "--manual-login",
        action="store_true",
        help="headfulで開いて、ユーザーがログイン完了したらEnterで続行（storage_state不要）",
    )
    ap.add_argument(
        "--manual-login-wait-seconds",
        type=int,
        default=180,
        help="--manual-login 時にログイン完了まで待つ秒数（Enter入力不要の自動待機）。",
    )

    ap.add_argument(
        "--auto-login",
        action="store_true",
        help="環境変数のメール/パスワードを使ってログインフォームへ自動入力する（ログイン完了後にlessonへ戻るまで待つ）",
    )
    ap.add_argument(
        "--login-email-env",
        default="RAIMO_LOGIN_EMAIL",
        help="メールアドレスの環境変数名",
    )
    ap.add_argument(
        "--login-password-env",
        default="RAIMO_LOGIN_PASSWORD",
        help="パスワードの環境変数名",
    )
    ap.add_argument(
        "--login-timeout-seconds",
        type=int,
        default=300,
        help="ログイン完了/lessonへ戻るまでの最大待機秒数",
    )
    ap.add_argument(
        "--login-env-file",
        default=str(
            Path.home()
            / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/browser_automation/.env"
        ),
        help="--auto-login 時に秘密情報を読み込むローカル .env ファイル（Git管理外推奨）",
    )
    args = ap.parse_args()

    ids = LessonIds(category_id=args.category_id, lesson_page_id=args.lesson_page_id)
    url = build_lesson_url(ids)

    out_md_dir = Path(args.out_md_dir).expanduser().resolve()
    assets_images_root = Path(args.assets_images_root).expanduser().resolve()
    out_md_dir.mkdir(parents=True, exist_ok=True)

    debug_dir = Path(args.debug_dir).expanduser().resolve() if args.debug_dir else (out_md_dir / "_raimo_debug")
    debug_dir.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print("エラー: playwright がインストールされていません。", file=sys.stderr)
        print("  例: pip install playwright && playwright install chromium", file=sys.stderr)
        raise SystemExit(1) from e

    # 1) ブラウザ起動
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.manual_login)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()

        print(f"[INFO] open: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=25000)

        if args.manual_login:
            print(
                f"[INFO] ログインが必要です。ブラウザでログイン完了後、このまま {args.manual_login_wait_seconds} 秒待機して続行します。"
            )
            time.sleep(args.manual_login_wait_seconds)

        # どのケースでも、ログイン後/遷移後に必ず指定 lesson へ戻る（待ちを含む）
        try:
            if is_likely_login_page(page) and args.auto_login:
                # env が未設定ならローカル env ファイルから補完
                env_file = Path(args.login_env_file).expanduser().resolve()
                email = os.environ.get(args.login_email_env, "")
                password = os.environ.get(args.login_password_env, "")
                if (not email or not password) and env_file.exists():
                    load_env_file(env_file)
                    email = os.environ.get(args.login_email_env, "")
                    password = os.environ.get(args.login_password_env, "")
                if not email or not password:
                    print("[ERROR] --auto-login だが環境変数が未設定です。", file=sys.stderr)
                else:
                    print("[INFO] auto-login: filling form ...")
                    ok = fill_login_form(page, email=email, password=password)
                    print(f"[INFO] auto-login: fill status={ok}")
            # lessonへ戻るまで待つ
            skip_goto_when_login = bool(args.auto_login)
            ok = wait_until_lesson_loaded(
                page,
                target_url=url,
                timeout_seconds=args.login_timeout_seconds,
                expected_lesson_page_id=ids.lesson_page_id,
                skip_goto_when_login=skip_goto_when_login,
            )
            if not ok:
                print(f"[WARN] lessonPageId={ids.lesson_page_id} へ戻るまで待機しましたが到達できませんでした。URL={page.url}")
        except Exception:
            pass

        # 2) タイトル取得（ファイル名）
        title = page.title()
        # サイド目次/ナビの現在レッスンリンクから拾える場合、ここを優先（ファイル名要件に合わせる）
        try:
            nav = page.locator(f"a[href*='lessonPageId={ids.lesson_page_id}']").first
            if nav.count() > 0:
                nt = nav.inner_text(timeout=5000).strip()
                if nt:
                    title = nt
        except Exception:
            pass
        # ページ上の見出しがある場合は次点で優先
        try:
            h1 = page.locator("h1").first
            if h1.count() > 0:
                t = h1.inner_text(timeout=5000).strip()
                if t:
                    title = t
        except Exception:
            pass

        if not title:
            title = f"lesson_{ids.lesson_page_id}"

        lesson_slug = lesson_slug_from_title(title) or slugify_filename(title)[:30]
        assets_lesson_dir = assets_images_root / lesson_slug

        # 3) 展開（候補探索→クリック）
        debug_expand_path = debug_dir / f"expand_clicked_{ids.lesson_page_id}.txt"
        clicked = expand_collapsibles(page)
        debug_expand_path.write_text("\n".join(clicked) if clicked else "(no clicks)", encoding="utf-8")

        # 4) DOM優先（取得できなければ OCR）
        dom_text = ""
        if args.prefer_dom:
            for sel in ["main", "article", "[role='main']", "body"]:
                try:
                    loc = page.locator(sel).first
                    txt = (loc.inner_text(timeout=5000) or "").strip()
                    if len(txt) >= args.dom_min_length:
                        dom_text = txt
                        break
                except Exception:
                    continue
            (debug_dir / f"{ids.lesson_page_id}_dom_text_preview.txt").write_text(
                dom_text[:4000] if dom_text else "(dom text not adopted)",
                encoding="utf-8",
            )

        # スクショはデバッグ用に残す（OCR を回さない場合でも、状態確認に使える）
        shot_full = debug_dir / f"{ids.lesson_page_id}_full_expanded.png"
        print(f"[INFO] screenshot: {shot_full}")
        page.wait_for_timeout(1000)
        page.screenshot(path=str(shot_full), full_page=True)

        if dom_text:
            print("[INFO] DOM text adopted (skip OCR).")
            ocr_text = dom_text
        else:
            # OCR
            print("[INFO] OCR start ...")
            ocr_text = tesseract_ocr(shot_full, lang=args.ocr_lang, psm=args.ocr_psm)

        # 6) 画像保存（ページ内 <img>）
        print("[INFO] save images ...")
        saved_images, src_to_path = collect_page_images_and_download(page, assets_lesson_dir=assets_lesson_dir)

        # 7) Markdown生成
        safe_title = slugify_filename(title)
        md_base = f"{safe_title}.md"
        out_md_path = out_md_dir / md_base
        if not args.overwrite:
            out_md_path = out_md_dir / f"{safe_title}_draft.md"

        # 画像リンク（存在するものだけ）
        img_lines = []
        for pth in saved_images:
            rel = safe_relpath(out_md_path, pth)
            img_lines.append(f"![図]({rel})")

        now = dt.datetime.now().strftime("%Y-%m-%d")
        md = []
        md.append(f"# {title}")
        md.append("")
        md.append("## メタ情報")
        md.append("- 企業AI研修ライモBiz（カテゴリ）")
        md.append(f"- `lessonPageId`: `{ids.lesson_page_id}`")
        md.append(f"- `categoryId`: `{ids.category_id}`")
        md.append(f"- `source_url`: {url}")
        md.append(f"- `取得日時`: {now}")
        md.append("")

        if args.inline_images:
            md.append("## OCR本文（コードブロック表示：本文＋図版）")
            md.append("")

            seq = extract_dom_sequence(page)
            # 画像の「差し込み位置」は DOM から推定するが、本文テキストは ocr_text（/DOM innerText）を丸ごと使う。
            # これにより、DOMシーケンス側のテキスト欠け（見出ししか取れない等）を避ける。

            def norm_abs(src: str) -> str:
                return urllib.parse.urljoin(page.url, src) if src else src

            # ocr_text を（多少ノイズ除去しつつ）行単位にしてコードブロックへ出す
            raw_lines = (ocr_text or "").splitlines()
            lines: list[str] = []
            for l in raw_lines:
                if not l.strip():
                    # 空行は保持
                    lines.append("")
                    continue
                cleaned = filter_ui_noise(l)
                if cleaned is None:
                    continue
                lines.append(cleaned)

            # 画像差し込みは基本的に「本文中のプレースホルダ '画像' 」をアンカーにする。
            # （lessonの本文テキストには '画像' という1語行が出てくるため、順序ズレを減らせる）
            placeholder_positions = [i for i, l in enumerate(lines) if l.strip() == "画像"]

            # DOM順で画像ローカルパスを列挙（src_to_path に存在するものだけ）
            img_locals_in_order: list[Path] = []
            for tok in seq:
                if tok.get("type") != "img":
                    continue
                src = str(tok.get("src") or "").strip()
                if not src:
                    continue
                abs_src = norm_abs(src)
                local = src_to_path.get(abs_src)
                if local and local not in img_locals_in_order:
                    img_locals_in_order.append(local)

            # DOM順が取れない場合でも、保存済み画像は最低限末尾へ差し込めるようにする
            if not img_locals_in_order and saved_images:
                img_locals_in_order = [p for p in saved_images if p.exists()]

            insert_map: dict[int, list[Path]] = {}
            if placeholder_positions and img_locals_in_order:
                for pos, local in zip(placeholder_positions, img_locals_in_order):
                    insert_map.setdefault(pos, []).append(local)
            else:
                # プレースホルダが取れない場合は、従来の「直前テキストアンカー」方式でフォールバックする
                anchor_keywords = [
                    "冒頭あいさつ",
                    "このレッスンの目的",
                    "このレッスンで学ぶこと",
                    "解説",
                    "生成AIの正体",
                    "なぜ「2026年の今",
                    "本教材の信頼性",
                    "比喩・例え話",
                    "CHECK",
                    "SUMMARY",
                    "講座のまとめ",
                ]
                prev_text = ""
                img_entries: list[dict] = []
                for tok in seq:
                    if tok.get("type") == "text":
                        prev_text = str(tok.get("text") or "").strip()
                        continue
                    if tok.get("type") == "img":
                        src = str(tok.get("src") or "").strip()
                        if not src:
                            continue
                        anchor = prev_text
                        if anchor and not any(k in anchor for k in anchor_keywords):
                            anchor = ""
                        img_entries.append({"src": src, "anchor": anchor})

                last_pos = -1
                for ent in img_entries:
                    abs_src = norm_abs(ent["src"])
                    local = src_to_path.get(abs_src)
                    if not local:
                        continue

                    anchor = ent.get("anchor") or ""
                    anchor_short = anchor.splitlines()[0].strip() if anchor else ""
                    if not anchor_short:
                        continue

                    pos = None
                    for i in range(last_pos + 1, len(lines)):
                        if anchor_short in lines[i]:
                            pos = i
                            break
                    if pos is None:
                        continue

                    insert_map.setdefault(pos, []).append(local)
                    last_pos = pos

            # 1つのコードブロックを基本にして、差し込み地点だけ分割する
            # フォールバックでも差し込めなかった画像がある場合、最後尾にまとめて入れて
            # 「画像が消える」状態だけは避ける。
            if img_locals_in_order and lines:
                inserted: set[Path] = set()
                for ps in insert_map.values():
                    inserted.update(ps)
                remaining = [p for p in img_locals_in_order if p not in inserted]
                if remaining:
                    insert_map.setdefault(len(lines) - 1, []).extend(remaining)

            md.append("```text")
            for i, line in enumerate(lines):
                md.append(line)
                if i in insert_map:
                    md.append("```")
                    md.append("")
                    for pth in insert_map[i]:
                        rel = safe_relpath(out_md_path, pth)
                        md.append(f"![図]({rel})")
                        md.append("")
                    md.append("```text")

            md.append("```")
            md.append("")
        else:
            if img_lines:
                md.append("## 図版（ページ内画像：オフライン用）")
                md.extend(img_lines)
                md.append("")

            md.append("## OCR本文（コードブロック表示）")
            md.append("```text")
            md.append(ocr_text)
            md.append("```")
            md.append("")

        md.append("## 内部リンク（要追加）")
        md.append("- （今回のデバッグ段階では未実装。目次との突合は別工程で行う）")
        md.append("")

        out_md_path.write_text("\n".join(md), encoding="utf-8")

        print(f"[DONE] md: {out_md_path}")
        print(f"[DONE] images: {len(saved_images)} saved to {assets_lesson_dir}")

        browser.close()


if __name__ == "__main__":
    main()

