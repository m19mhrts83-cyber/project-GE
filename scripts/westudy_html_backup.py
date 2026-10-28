#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WeStudy（神大家 会員サイト）の HTML と再構築用アセットをまるごとバックアップする。

週次取込（westudy_forum_all.py / westudy_lesson_pages.py）と同じ方法でログインし、
コースタブ → 目次 → レッスン → フォーラムを巡回して、各ページを次の形で 1 つの zip に固める。

  raw/pages/...html        ログイン後に表示された HTML（加工なし）
  raw/assets/<host>/...    CSS の原本（site 側は参照先を書き換えるため）
  site/pages/...html       オフラインで開けるよう参照先を相対パスへ書き換えた HTML
  site/assets/<host>/...   CSS / JS / 画像 / フォント等
  site/assets/.../*.pdf 等 レッスンからリンクされた配布資料（westudy.co.jp 内のもの）
  screenshots/...          ページ全体の画面キャプチャ（見た目の答え合わせ用）
  api/wp-json/...          WordPress REST API で取れた本文データ（別 WordPress への流し込み素材）
  api/extra/...            robots.txt・サイトマップ
  structure.json           コースタブ → 目次セクション → レッスンの構成
  manifest.json            全ページ・全アセットの URL / 保存先 / sha256 / 取得結果
  index.html               バックアップの目次（ブラウザで開く入口）

動画本体（Vimeo 等）は取らず、埋め込み URL だけ manifest に記録する。
保存先は config/westudy_html_backup.yaml の destination で切り替える。

実行例（Mac。WeStudy 認証は既存 .env、Chrome は selenium_env）:
  cd ~/git-repos && set -a && source "<Q&Aチャットボット>/scripts/.env" && set +a
  ~/selenium_env/venv/bin/python scripts/westudy_html_backup.py --max-pages 5   # お試し
  ~/selenium_env/venv/bin/python scripts/westudy_html_backup.py                 # 本番
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import posixpath
import re
import shutil
import sys
import time
import zipfile
from collections import deque
from datetime import datetime, timezone
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import parse_qsl, unquote, urldefrag, urlencode, urljoin, urlsplit, urlunsplit

REPO = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO / "config" / "westudy_html_backup.yaml"
LESSON_SCRAPER_DIR = REPO / "ProgramCode" / "alfred_python"
DEFAULT_WORK_ROOT = REPO / ".jarvis_state" / "westudy_html_backup"
SITE_HOST = "westudy.co.jp"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------- 設定


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def resolve_destination(cfg: dict[str, Any], env: dict[str, str] | None = None) -> dict[str, Any]:
    """config の destination に環境変数の上書きを当て、~ を展開して返す。"""
    env = os.environ if env is None else env
    dest = dict(cfg.get("destination") or {})
    for key, env_key in (
        ("type", "WESTUDY_BACKUP_DEST_TYPE"),
        ("path", "WESTUDY_BACKUP_DEST_PATH"),
        ("folder_id", "WESTUDY_BACKUP_DEST_FOLDER_ID"),
        ("token_path", "WESTUDY_BACKUP_GDRIVE_TOKEN"),
    ):
        v = (env.get(env_key) or "").strip()
        if v:
            dest[key] = v
    dest["type"] = (dest.get("type") or "local").strip()
    if dest["type"] not in ("local", "gdrive_api"):
        raise ValueError(f"destination.type は local / gdrive_api のどちらか: {dest['type']}")
    for key in ("path", "token_path"):
        if dest.get(key):
            dest[key] = str(Path(str(dest[key])).expanduser())
    if dest["type"] == "local" and not dest.get("path"):
        raise ValueError("destination.type=local には destination.path が必要です")
    if dest["type"] == "gdrive_api" and not (dest.get("folder_id") and dest.get("token_path")):
        raise ValueError("destination.type=gdrive_api には folder_id と token_path が必要です")
    return dest


# ---------------------------------------------------------------- URL


def normalize_page_url(url: str, base: str = "", keep_query_keys: Iterable[str] = ()) -> str | None:
    """ページ URL を正規化（# を落とし、指定キー以外のクエリを落とし、末尾 / を揃える）。"""
    if not url:
        return None
    url = url.strip()
    if url.startswith(("javascript:", "mailto:", "tel:", "data:", "#")):
        return None
    absu, _ = urldefrag(urljoin(base, url) if base else url)
    parts = urlsplit(absu)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    keep = set(keep_query_keys)
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query) if k in keep))
    path = parts.path or "/"
    if len(path) > 1:
        path = path.rstrip("/")
    return urlunsplit(("https", parts.netloc.lower(), path, query, ""))


def should_follow(url: str, include: Iterable[str], exclude: Iterable[str]) -> bool:
    if urlsplit(url).netloc != SITE_HOST:
        return False
    if any(re.search(p, url) for p in exclude):
        return False
    return any(re.search(p, url) for p in include)


_UNSAFE = re.compile(r'[\\:*?"<>|\x00-\x1f]')


def _safe_segment(seg: str) -> str:
    seg = _UNSAFE.sub("_", unquote(seg)).strip(". ") or "_"
    # 長すぎるスラッグは途中を hash にする（zip / Drive のパス長対策）
    if len(seg.encode("utf-8")) > 120:
        seg = seg[:40] + "_" + hashlib.sha1(seg.encode("utf-8")).hexdigest()[:10]
    return seg


def page_local_path(url: str) -> str:
    """https://westudy.co.jp/lesson/abc?t=x → pages/lesson/abc__t-x.html"""
    parts = urlsplit(url)
    segs = [_safe_segment(s) for s in parts.path.split("/") if s]
    name = segs.pop() if segs else "index"
    if parts.query:
        name += "__" + _safe_segment(parts.query.replace("=", "-").replace("&", "_"))
    return posixpath.join("pages", *segs, name + ".html")


def asset_local_path(url: str) -> str:
    """アセット URL → assets/<host>/<path>（クエリ付きは拡張子の前に短い hash）。"""
    parts = urlsplit(url)
    segs = [_safe_segment(s) for s in parts.path.split("/") if s]
    if not segs or parts.path.endswith("/"):
        segs.append("index")
    name = segs.pop()
    if parts.query:
        q = hashlib.sha1(parts.query.encode("utf-8")).hexdigest()[:8]
        stem, dot, ext = name.rpartition(".")
        name = f"{stem}__q{q}.{ext}" if dot and stem else f"{name}__q{q}"
    return posixpath.join("assets", _safe_segment(parts.netloc.lower()), *segs, name)


def url_extension(url: str) -> str:
    name = urlsplit(url).path.rsplit("/", 1)[-1]
    return name.rpartition(".")[2].lower() if "." in name else ""


def is_site_host(url: str) -> bool:
    host = urlsplit(url).netloc.lower()
    return host == SITE_HOST or host.endswith("." + SITE_HOST)


_NONCE_RES = (
    re.compile(r"wpApiSettings\s*=\s*\{[^}]*?[\"']nonce[\"']\s*:\s*[\"']([0-9a-f]{8,12})[\"']"),
    re.compile(r"[\"']rest_?nonce[\"']\s*:\s*[\"']([0-9a-f]{8,12})[\"']", re.I),
)


def find_rest_nonce(html: str) -> str | None:
    """ページ内の wpApiSettings.nonce 等から REST API 用 nonce を拾う（cookie 認証に必要）。"""
    for rx in _NONCE_RES:
        m = rx.search(html)
        if m:
            return m.group(1)
    return None


_DEAD_BROWSER_ERRORS = ("InvalidSessionIdException", "NoSuchWindowException", "WebDriverException",
                        "MaxRetryError", "ConnectionRefusedError", "RemoteDisconnected")


def is_browser_dead(e: BaseException) -> bool:
    """Chrome / ChromeDriver が落ちた例外か（selenium を import せず型名で判定）。"""
    names = {c.__name__ for c in type(e).__mro__}
    if "TimeoutException" in names:
        return False
    return bool(names & set(_DEAD_BROWSER_ERRORS)) or "invalid session id" in str(e).lower()


def rel_from(from_file: str, to_file: str) -> str:
    return posixpath.relpath(to_file, posixpath.dirname(from_file) or ".")


# ---------------------------------------------------------------- HTML / CSS 解析

_CSS_URL = re.compile(r"""url\(\s*(['"]?)([^'")]+?)\1\s*\)""", re.I)
_CSS_IMPORT = re.compile(r"""@import\s+(['"])([^'"]+)\1""", re.I)
_ASSET_ATTRS = {
    "img": ("src", "srcset", "data-src", "data-srcset", "data-lazy-src"),
    "source": ("src", "srcset", "data-srcset"),
    "script": ("src",),
    "video": ("poster",),
    "input": ("src",),
}
_LINK_ASSET_RELS = {"stylesheet", "icon", "shortcut", "apple-touch-icon", "preload", "manifest", "mask-icon"}


def split_srcset(value: str) -> list[str]:
    out = []
    for part in value.split(","):
        u = part.strip().split(" ")[0].strip()
        if u:
            out.append(u)
    return out


def extract_css_refs(css: str) -> list[str]:
    refs = [m.group(2).strip() for m in _CSS_URL.finditer(css)]
    refs += [m.group(2).strip() for m in _CSS_IMPORT.finditer(css)]
    return [r for r in refs if r and not r.startswith(("data:", "#"))]


class _RefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.assets: list[str] = []
        self.iframes: list[str] = []
        self.title = ""
        self._in_title = False
        self._in_style = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        elif tag == "link" and a.get("href"):
            rels = set(a.get("rel", "").lower().split())
            if rels & _LINK_ASSET_RELS:
                self.assets.append(a["href"])
        elif tag == "iframe" and a.get("src"):
            self.iframes.append(a["src"])
        for attr in _ASSET_ATTRS.get(tag, ()):
            v = a.get(attr)
            if not v:
                continue
            if attr.endswith("srcset"):
                self.assets.extend(split_srcset(v))
            else:
                self.assets.append(v)
        if a.get("style"):
            self.assets.extend(extract_css_refs(a["style"]))
        if tag == "title":
            self._in_title = True
        if tag == "style":
            self._in_style = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag == "style":
            self._in_style = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._in_style:
            self.assets.extend(extract_css_refs(data))


def extract_refs(html: str, base_url: str) -> dict[str, Any]:
    p = _RefParser()
    p.feed(html)
    p.close()

    def absolutize(items: list[str]) -> list[str]:
        out: list[str] = []
        for raw in items:
            raw = raw.strip()
            if not raw or raw.startswith(("data:", "javascript:", "mailto:", "tel:", "#", "blob:")):
                continue
            u, _ = urldefrag(urljoin(base_url, raw))
            if urlsplit(u).scheme in ("http", "https") and u not in out:
                out.append(u)
        return out

    return {
        "title": " ".join(p.title.split()),
        "links": absolutize(p.links),
        "assets": absolutize(p.assets),
        "iframes": absolutize(p.iframes),
    }


_ATTR_RE = re.compile(
    r"""(\s(?:src|href|srcset|data-src|data-srcset|data-lazy-src|poster)\s*=\s*)(["'])(.*?)\2""",
    re.I | re.S,
)


def rewrite_refs(text: str, resolve: Callable[[str], str | None], *, css_only: bool = False) -> str:
    """属性値と CSS url() を resolve(raw) の結果で置き換える（None は元のまま）。"""

    def one(raw: str) -> str:
        # 属性値は HTML エスケープのまま（?a=1&amp;b=2）。抽出側は 1 回戻した値なので揃える
        new = resolve(unescape(raw.strip()))
        return raw if new is None else new

    def css_sub(m: re.Match[str]) -> str:
        q, raw = m.group(1), m.group(2)
        return f"url({q}{one(raw)}{q})"

    def import_sub(m: re.Match[str]) -> str:
        q, raw = m.group(1), m.group(2)
        return f"@import {q}{one(raw)}{q}"

    if not css_only:

        def attr_sub(m: re.Match[str]) -> str:
            prefix, q, val = m.group(1), m.group(2), m.group(3)
            if "srcset" in prefix.lower():
                pieces = []
                for part in val.split(","):
                    bits = part.strip().split(" ", 1)
                    if bits[0]:
                        bits[0] = one(bits[0])
                    pieces.append(" ".join(bits))
                val = ", ".join(pieces)
            else:
                val = one(val)
            return f"{prefix}{q}{val}{q}"

        text = _ATTR_RE.sub(attr_sub, text)
    text = _CSS_IMPORT.sub(import_sub, text)
    return _CSS_URL.sub(css_sub, text)


# ---------------------------------------------------------------- 本体


class SiteBackup:
    def __init__(self, cfg: dict[str, Any], work_dir: Path, *, headless: bool = True) -> None:
        self.cfg = cfg
        self.crawl = cfg.get("crawl") or {}
        self.acfg = cfg.get("assets") or {}
        self.work = work_dir
        self.headless = headless
        self.keep_q = list(self.crawl.get("keep_query_keys") or [])
        self.pages: dict[str, dict[str, Any]] = {}
        self.assets: dict[str, dict[str, Any]] = {}
        self.embeds: set[str] = set()
        self.structure: list[dict[str, Any]] = []
        self.external_docs: set[str] = set()
        self.api: list[dict[str, Any]] = []
        self.screenshots = 0
        self.rest_nonce: str | None = None
        self.session = None
        self.wlp = None
        self.pages_since_restart = 0
        self.queue: deque[str] = deque()
        self.seen: set[str] = set()

    # --- ブラウザ（既存 lesson スクレイパーのログイン処理をそのまま使う）
    def _start_browser(self) -> None:
        sys.path.insert(0, str(LESSON_SCRAPER_DIR))
        import westudy_lesson_pages as wlp

        self.wlp = wlp
        wlp._HEADLESS = self.headless
        wlp.driver = wlp.create_driver(headless=self.headless)
        wlp.login_westudy()
        self._sync_cookies()

    def _sync_cookies(self) -> None:
        import requests

        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({"User-Agent": UA, "Accept-Language": "ja-JP"})
        for c in self.wlp.driver.get_cookies():
            self.session.cookies.set(c["name"], c["value"], domain=c.get("domain"), path=c.get("path", "/"))

    def _looks_logged_out(self) -> bool:
        cur = (self.wlp.driver.current_url or "").lower()
        if "wp-login.php" in cur or cur.rstrip("/").endswith("/login"):
            return True
        try:
            return bool(self.wlp.driver.execute_script("return !!document.querySelector('#user_login');"))
        except Exception:
            return False

    def _restart_browser(self, reason: str) -> None:
        """Chrome を作り直して再ログインする（セッション切れ・長時間運転のメモリ肥大対策）。"""
        log(f"  🔄 ブラウザ再起動: {reason}")
        try:
            self.wlp.driver.quit()
        except Exception:
            pass
        self.wlp.driver = self.wlp.create_driver(headless=self.headless)
        self.wlp.login_westudy()
        self._sync_cookies()
        self.pages_since_restart = 0

    def _apply_page_timeout(self) -> None:
        try:
            self.wlp.driver.set_page_load_timeout(int(self.crawl.get("page_load_timeout_sec", 30)))
        except Exception:
            pass

    def _get_html(self, url: str) -> tuple[str, str]:
        wlp = self.wlp
        every = int(self.crawl.get("restart_browser_every", 40) or 0)
        if every and self.pages_since_restart >= every:
            self._restart_browser(f"{every} ページごとの定期再起動")
        for attempt in (1, 2):
            self._apply_page_timeout()
            try:
                wlp._safe_get(url, retries=2)
            except Exception as e:
                # InvalidSessionIdException 等。死んだ Chrome のまま続けると 1 ページ十数分止まる
                if attempt == 2 or not is_browser_dead(e):
                    raise
                self._restart_browser(e.__class__.__name__)
                continue
            time.sleep(float(self.crawl.get("page_delay_sec", 1.0)))
            if not self._looks_logged_out():
                self.pages_since_restart += 1
                return wlp.driver.page_source, wlp.driver.current_url
            log(f"  ログイン切れ → 再ログイン ({attempt}/2)")
            wlp.login_westudy()
            self._sync_cookies()
        raise RuntimeError(f"再ログイン後もログイン画面のまま: {url}")

    # --- 構成
    def collect_structure(self) -> list[str]:
        seeds: list[str] = []
        for tab in self.wlp.COURSE_TABS:
            try:
                lessons = self.wlp.collect_sections_and_lessons(tab)
            except Exception as e:  # 構成が取れなくても巡回は続ける
                log(f"  構成取得失敗 {tab['label']}: {e}")
                lessons = []
            sections: dict[str, list[dict[str, str]]] = {}
            for item in lessons:
                u = normalize_page_url(item["url"], keep_query_keys=self.keep_q)
                if not u:
                    continue
                sections.setdefault(item.get("section") or "", []).append(
                    {"title": item.get("title") or "", "url": u, "local": page_local_path(u)}
                )
                seeds.append(u)
            self.structure.append(
                {
                    "tab": tab["label"],
                    "url": tab["url"],
                    "sections": [{"section": k, "lessons": v} for k, v in sections.items()],
                }
            )
        return seeds

    # --- アセット
    def _skip_asset(self, url: str) -> str | None:
        host = urlsplit(url).netloc.lower()
        if host in set(self.acfg.get("skip_hosts") or []):
            return "skip_host"
        return None

    def fetch_asset(self, url: str, depth: int = 0, *, kind: str = "asset") -> dict[str, Any]:
        if url in self.assets:
            return self.assets[url]
        rec: dict[str, Any] = {"url": url, "local": asset_local_path(url), "kind": kind}
        self.assets[url] = rec
        reason = self._skip_asset(url)
        if reason:
            rec["status"] = reason
            return rec
        mb = (self.cfg.get("attachments") or {}).get("max_mb", 100) if kind == "attachment" else self.acfg.get("max_asset_mb", 25)
        max_bytes = int(float(mb) * 1024 * 1024)
        try:
            r = self.session.get(url, timeout=60, stream=True)
            ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            rec["content_type"] = ctype
            rec["http_status"] = r.status_code
            if r.status_code != 200:
                rec["status"] = "http_error"
                r.close()
                return rec
            if kind == "asset" and any(ctype.startswith(p) for p in self.acfg.get("skip_content_types") or []):
                rec["status"] = "skip_content_type"
                r.close()
                return rec
            buf = bytearray()
            for chunk in r.iter_content(65536):
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    rec["status"] = "too_large"
                    r.close()
                    return rec
        except Exception as e:
            rec["status"] = "error"
            rec["error"] = f"{e.__class__.__name__}: {e}"[:300]
            return rec
        time.sleep(float(self.acfg.get("asset_delay_sec", 0.1)))
        data = bytes(buf)
        rec.update(status="ok", bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        is_css = ctype == "text/css" or urlsplit(url).path.lower().endswith(".css")
        if is_css and depth < 4:
            css = data.decode("utf-8", errors="replace")
            self._write("raw/" + rec["local"], data)
            for ref in extract_css_refs(css):
                child, _ = urldefrag(urljoin(url, ref))
                if urlsplit(child).scheme in ("http", "https"):
                    self.fetch_asset(child, depth + 1)
            css = rewrite_refs(css, self._resolver(url, "site/" + rec["local"]), css_only=True)
            data = css.encode("utf-8")
        self._write("site/" + rec["local"], data)
        return rec

    def _resolver(self, base_url: str, from_file: str) -> Callable[[str], str | None]:
        def resolve(raw: str) -> str | None:
            if not raw or raw.startswith(("data:", "#", "javascript:", "mailto:", "tel:")):
                return None
            absu, frag = urldefrag(urljoin(base_url, raw))
            a = self.assets.get(absu)
            if a and a.get("status") == "ok":
                return rel_from(from_file, "site/" + a["local"])
            pu = normalize_page_url(absu, keep_query_keys=self.keep_q)
            if pu and pu in self.pages and self.pages[pu].get("status") == "ok":
                target = rel_from(from_file, "site/" + self.pages[pu]["local"])
                return target + (f"#{frag}" if frag else "")
            return None

        return resolve

    def _write(self, rel: str, data: bytes | str) -> None:
        p = self.work / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, str):
            p.write_text(data, encoding="utf-8")
        else:
            p.write_bytes(data)

    # --- 巡回
    def crawl_pages(self, extra_seeds: list[str], max_pages: int) -> None:
        include = self.crawl.get("include") or []
        exclude = self.crawl.get("exclude") or []
        doc_exts = set((self.cfg.get("attachments") or {}).get("extensions") or [])
        doc_hosts = {h.lower() for h in (self.cfg.get("attachments") or {}).get("extra_hosts") or []}
        queue, seen = self.queue, self.seen
        for s in list(self.crawl.get("seeds") or []) + extra_seeds:
            u = normalize_page_url(s, keep_query_keys=self.keep_q)
            if u and u not in seen:
                seen.add(u)
                queue.append(u)
        while queue and len(self.pages) < max_pages:
            url = queue.popleft()
            n = len(self.pages) + 1
            rec: dict[str, Any] = {"url": url, "local": page_local_path(url)}
            self.pages[url] = rec
            log(f"[{n}/{min(max_pages, n + len(queue))}] {url}")
            t0 = time.monotonic()
            try:
                html, final_url = self._get_html(url)
            except Exception as e:
                rec.update(status="error", error=f"{e.__class__.__name__}: {e}"[:300])
                log(f"  ⚠️ 取得失敗: {rec['error']}")
                self.save_checkpoint()
                continue
            refs = extract_refs(html, final_url)
            body = html.encode("utf-8")
            rec.update(
                status="ok",
                final_url=final_url,
                title=refs["title"],
                bytes=len(body),
                sha256=hashlib.sha256(body).hexdigest(),
                assets=refs["assets"],
                iframes=refs["iframes"],
                fetched_at=datetime.now(timezone.utc).isoformat(),
            )
            self._write("raw/" + rec["local"], body)
            if not self.rest_nonce:
                self.rest_nonce = find_rest_nonce(html)
            self._maybe_screenshot(rec)
            self.embeds.update(i for i in refs["iframes"] if urlsplit(i).netloc != SITE_HOST)
            for a in refs["assets"]:
                self.fetch_asset(a)
            links: list[str] = []
            for link in refs["links"]:
                if doc_exts and url_extension(link) in doc_exts:
                    if is_site_host(link) or urlsplit(link).netloc.lower() in doc_hosts:
                        self.fetch_asset(link, kind="attachment")
                    else:
                        self.external_docs.add(link)
                    continue
                u = normalize_page_url(link, keep_query_keys=self.keep_q)
                if not u:
                    continue
                links.append(u)
                if u not in seen and should_follow(u, include, exclude):
                    seen.add(u)
                    queue.append(u)
            rec["links"] = sorted(set(links))
            rec["elapsed_sec"] = round(time.monotonic() - t0, 1)
            if rec["elapsed_sec"] > 60:
                log(f"  ⏱ {rec['elapsed_sec']} 秒かかった")
            if n % 10 == 0:
                self.save_checkpoint()
            if n % 200 == 0:
                self._sync_cookies()
        if queue:
            log(f"⚠️ max_pages={max_pages} に達したため未巡回 {len(queue)} 件（manifest.unvisited に記録）")
        self.unvisited = list(queue)

    def _maybe_screenshot(self, rec: dict[str, Any]) -> None:
        sc = self.cfg.get("screenshots") or {}
        if not sc.get("enabled") or not any(re.search(p, rec["url"]) for p in sc.get("include") or []):
            return
        d = self.wlp.driver
        try:
            metrics = d.execute_cdp_cmd("Page.getLayoutMetrics", {})
            size = metrics.get("cssContentSize") or metrics.get("contentSize") or {}
            w = int(min(max(size.get("width", 1280), 320), 1920))
            # 縦長すぎるページを丸ごと撮ると Chrome がメモリで落ちる（InvalidSessionId の一因）
            h = int(min(max(size.get("height", 1024), 200), int(sc.get("max_height_px", 8000))))
            res = d.execute_cdp_cmd(
                "Page.captureScreenshot",
                {"format": "jpeg", "quality": 80, "captureBeyondViewport": True,
                 "clip": {"x": 0, "y": 0, "width": w, "height": h, "scale": 1}},
            )
            data, ext = base64.b64decode(res["data"]), "jpg"
        except Exception:
            try:
                data, ext = d.get_screenshot_as_png(), "png"
            except Exception as e:
                rec["screenshot_error"] = f"{e.__class__.__name__}: {e}"[:200]
                return
        local = "screenshots/" + rec["local"][len("pages/"):].rsplit(".", 1)[0] + "." + ext
        self._write(local, data)
        rec["screenshot"] = local
        self.screenshots += 1

    def _api_get(self, path_or_url: str):
        url = path_or_url if path_or_url.startswith("http") else f"https://{SITE_HOST}{path_or_url}"
        headers = {"X-WP-Nonce": self.rest_nonce} if self.rest_nonce else {}
        return self.session.get(url, timeout=60, headers=headers)

    def _save_api(self, local: str, url: str, r) -> dict[str, Any]:
        rec: dict[str, Any] = {"url": url, "local": local, "http_status": getattr(r, "status_code", None)}
        if r is not None and r.status_code == 200:
            self._write(local, r.content)
            rec.update(status="ok", bytes=len(r.content))
        else:
            rec["status"] = "http_error"
        self.api.append(rec)
        return rec

    def dump_wp_json(self) -> None:
        """WordPress REST API の本文データと、robots.txt・サイトマップを保存する（取れた分だけ）。"""
        wcfg = self.cfg.get("wp_json") or {}
        if not wcfg.get("enabled"):
            return
        self._sync_cookies()
        if not self.rest_nonce:
            # ログイン中なら admin-ajax が REST 用 nonce を返す（WordPress 5.3+）
            try:
                r = self.session.get(f"https://{SITE_HOST}/wp-admin/admin-ajax.php?action=rest-nonce", timeout=30)
                if r.status_code == 200 and re.fullmatch(r"[0-9a-f]{8,12}", r.text.strip()):
                    self.rest_nonce = r.text.strip()
            except Exception:
                pass
        log(f"WordPress API 取得（nonce={'あり' if self.rest_nonce else 'なし'}）")
        for path in wcfg.get("extra_paths") or []:
            try:
                r = self.session.get(f"https://{SITE_HOST}{path}", timeout=30)
            except Exception:
                r = None
            self._save_api("api/extra/" + _safe_segment(path.strip("/")), path, r)
        try:
            r = self._api_get("/wp-json/wp/v2/types?context=view")
        except Exception as e:
            self.api.append({"url": "/wp-json/wp/v2/types", "status": "error", "error": str(e)[:200]})
            return
        rec = self._save_api("api/wp-json/types.json", "/wp-json/wp/v2/types", r)
        if rec["status"] != "ok":
            log(f"  wp-json は使えませんでした（HTTP {rec['http_status']}）")
            return
        try:
            types = r.json()
        except ValueError:
            return
        skip = set(wcfg.get("skip_types") or [])
        limit = int(wcfg.get("max_pages_per_type", 50))
        for name, t in sorted(types.items()):
            base = (t or {}).get("rest_base")
            ns = (t or {}).get("rest_namespace") or "wp/v2"
            if name in skip or not base:
                continue
            total = 0
            for page in range(1, limit + 1):
                path = f"/wp-json/{ns}/{base}?per_page=100&page={page}&context=view"
                try:
                    r = self._api_get(path)
                except Exception:
                    break
                if r.status_code != 200:
                    if page == 1:
                        self._save_api(f"api/wp-json/{_safe_segment(base)}/page-001.json", path, r)
                    break
                try:
                    items = r.json()
                except ValueError:
                    break
                if not isinstance(items, list) or not items:
                    break
                self._save_api(f"api/wp-json/{_safe_segment(base)}/page-{page:03d}.json", path, r)
                total += len(items)
                try:
                    if page >= int(r.headers.get("X-WP-TotalPages") or 0):
                        break
                except ValueError:
                    pass
                time.sleep(float(self.acfg.get("asset_delay_sec", 0.1)))
            if total:
                log(f"  {name}: {total} 件")

    CHECKPOINT = "_checkpoint.json"

    def save_checkpoint(self) -> None:
        """途中経過を保存する（Mac のスリープ・回線断で止まっても --resume で続きから）。"""
        data = {
            "pages": self.pages, "assets": self.assets, "structure": self.structure,
            "embeds": sorted(self.embeds), "external_docs": sorted(self.external_docs),
            "screenshots": self.screenshots, "rest_nonce": self.rest_nonce,
            "queue": list(self.queue), "seen": sorted(self.seen),
        }
        tmp = self.work / (self.CHECKPOINT + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.work / self.CHECKPOINT)

    def load_checkpoint(self) -> bool:
        p = self.work / self.CHECKPOINT
        if not p.is_file():
            return False
        d = json.loads(p.read_text(encoding="utf-8"))
        # 取得失敗だったページは取り直す
        retry = [u for u, r in d["pages"].items() if r.get("status") != "ok"]
        self.pages = {u: r for u, r in d["pages"].items() if r.get("status") == "ok"}
        self.assets = d["assets"]
        self.structure = d["structure"]
        self.embeds = set(d["embeds"])
        self.external_docs = set(d["external_docs"])
        self.screenshots = d["screenshots"]
        self.rest_nonce = d.get("rest_nonce")
        self.queue = deque(retry + [u for u in d["queue"] if u not in retry])
        self.seen = set(d["seen"])
        log(f"途中から再開: 取得済み {len(self.pages)} ページ / 残り {len(self.queue)} ページ")
        return True

    def write_offline_pages(self) -> None:
        """全ページ取得後に、ページ間リンクとアセット参照を相対パスへ書き換えた site/ 版を作る。"""
        for url, rec in self.pages.items():
            if rec.get("status") != "ok":
                continue
            raw = (self.work / "raw" / rec["local"]).read_text(encoding="utf-8")
            site_file = "site/" + rec["local"]
            out = rewrite_refs(raw, self._resolver(rec.get("final_url") or url, site_file))
            self._write(site_file, out)

    def write_index(self, run_id: str) -> None:
        rows = []
        for tab in self.structure:
            rows.append(f"<h2>{escape(tab['tab'])}</h2>")
            for sec in tab["sections"]:
                if sec["section"]:
                    rows.append(f"<h3>{escape(sec['section'])}</h3>")
                rows.append("<ul>")
                for les in sec["lessons"]:
                    rows.append(
                        f'<li><a href="site/{escape(les["local"])}">{escape(les["title"] or les["url"])}</a></li>'
                    )
                rows.append("</ul>")
        rows.append("<h2>すべてのページ</h2><ul>")
        for url, rec in sorted(self.pages.items()):
            if rec.get("status") == "ok":
                rows.append(
                    f'<li><a href="site/{escape(rec["local"])}">{escape(rec.get("title") or url)}</a>'
                    + (f' <a href="{escape(rec["screenshot"])}">[画面]</a>' if rec.get("screenshot") else "")
                    + f' <small>{escape(url)}</small></li>'
                )
        rows.append("</ul>")
        html = (
            '<!doctype html><meta charset="utf-8"><title>WeStudy バックアップ '
            f"{escape(run_id)}</title><body style=\"font-family:sans-serif;max-width:960px;margin:2em auto\">"
            f"<h1>WeStudy バックアップ {escape(run_id)}</h1>" + "\n".join(rows)
        )
        self._write("index.html", html)

    def manifest(self, run_id: str, started: str) -> dict[str, Any]:
        def count(d: dict[str, dict[str, Any]]) -> dict[str, int]:
            out: dict[str, int] = {}
            for r in d.values():
                out[r.get("status", "?")] = out.get(r.get("status", "?"), 0) + 1
            return out

        return {
            "run_id": run_id,
            "started_at": started,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "site": f"https://{SITE_HOST}/",
            "pages_by_status": count(self.pages),
            "assets_by_status": count(self.assets),
            "asset_bytes": sum(a.get("bytes", 0) for a in self.assets.values() if a.get("status") == "ok"),
            "external_embeds": sorted(self.embeds),
            "external_documents": sorted(self.external_docs),
            "attachments_ok": sum(1 for a in self.assets.values() if a.get("kind") == "attachment" and a.get("status") == "ok"),
            "screenshots": self.screenshots,
            "pages_by_kind": pages_by_kind(self.pages),
            "assets_by_kind": assets_by_kind(self.assets),
            "lessons_by_tab": {t["tab"]: sum(len(s["lessons"]) for s in t["sections"]) for t in self.structure},
            "rest_nonce_found": bool(self.rest_nonce),
            "api_by_status": count({str(i): a for i, a in enumerate(self.api)}),
            "unvisited": getattr(self, "unvisited", []),
            "pages": list(self.pages.values()),
            "assets": list(self.assets.values()),
            "api": self.api,
        }

    def run(self, run_id: str, max_pages: int, *, resume: bool = False) -> dict[str, Any]:
        started = datetime.now(timezone.utc).isoformat()
        resumed = resume and self.load_checkpoint()
        self._start_browser()
        try:
            seeds = [] if resumed else self.collect_structure()
            self.crawl_pages(seeds, max_pages)
            self.save_checkpoint()
            try:
                self.dump_wp_json()
            except Exception as e:  # API が取れなくても HTML のバックアップは残す
                log(f"⚠️ WordPress API 取得で例外: {e}")
        finally:
            try:
                self.wlp.driver.quit()
            except Exception:
                pass
        self.write_offline_pages()
        self.write_index(run_id)
        self._write("structure.json", json.dumps(self.structure, ensure_ascii=False, indent=2))
        m = self.manifest(run_id, started)
        self._write("manifest.json", json.dumps(m, ensure_ascii=False, indent=2))
        (self.work / self.CHECKPOINT).unlink(missing_ok=True)
        self._write(
            "README.txt",
            "WeStudy（神大家 会員サイト）バックアップ\n"
            f"取得: {started}\n\n"
            "index.html をブラウザで開くと目次から各ページを見られます。\n"
            "raw/ はログイン後に表示された HTML の原本、site/ はオフライン閲覧用に参照先を書き換えた版です。\n"
            "screenshots/ は各ページの画面キャプチャ、api/ は WordPress API で取れた本文データです。\n"
            "動画本体は含みません（埋め込み URL は manifest.json の external_embeds）。\n"
            "外部（Google ドライブ等）の配布資料は URL のみ（manifest.json の external_documents）。\n"
            "会員限定の内容と会員名が含まれるため、共有範囲に注意してください。\n",
        )
        return m


# ---------------------------------------------------------------- 保存先


_ASSET_KINDS = (
    ("css", ("css",)),
    ("js", ("js", "mjs")),
    ("image", ("png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "avif", "bmp")),
    ("font", ("woff", "woff2", "ttf", "otf", "eot")),
)


def pages_by_kind(pages: dict[str, dict[str, Any]]) -> dict[str, int]:
    """取得できたページを /course/・/lesson/・/forum/ ごとに数える（資料の数字用）。"""
    out: dict[str, int] = {}
    for url, r in pages.items():
        if r.get("status") != "ok":
            continue
        seg = (urlsplit(url).path.strip("/").split("/") or [""])[0] or "top"
        out[seg] = out.get(seg, 0) + 1
    return dict(sorted(out.items()))


def assets_by_kind(assets: dict[str, dict[str, Any]]) -> dict[str, dict[str, int]]:
    """取得できたアセットを CSS / JS / 画像 / フォント / 配布資料 / その他 に分けて件数とバイト数を出す。"""
    out: dict[str, dict[str, int]] = {}
    for a in assets.values():
        if a.get("status") != "ok":
            continue
        ext = url_extension(a["url"])
        ctype = a.get("content_type") or ""
        kind = "attachment" if a.get("kind") == "attachment" else "other"
        if kind == "other":
            for name, exts in _ASSET_KINDS:
                if ext in exts or (name == "image" and ctype.startswith("image/")) or (name == "css" and ctype == "text/css"):
                    kind = name
                    break
        slot = out.setdefault(kind, {"count": 0, "bytes": 0})
        slot["count"] += 1
        slot["bytes"] += int(a.get("bytes") or 0)
    return dict(sorted(out.items()))


def export_source(cfg: dict[str, Any], dest: Path | None = None) -> Path:
    """引き渡し用のソースコード一式を、リポジトリと同じ相対パスで dest に写す（毎週上書き）。"""
    hcfg = cfg.get("handover") or {}
    dest = dest or Path(str(hcfg.get("source_dest") or "")).expanduser()
    if not str(dest).strip() or str(dest) == ".":
        raise ValueError("handover.source_dest が未設定です")
    dest.mkdir(parents=True, exist_ok=True)
    copied = []
    for rel in hcfg.get("files") or []:
        src = REPO / rel
        if not src.is_file():
            raise FileNotFoundError(f"引き渡し対象がありません: {rel}")
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
        copied.append(rel)
    try:
        import subprocess

        commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                                capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        commit = ""
    (dest / "VERSION.txt").write_text(
        f"書き出し: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"元リポジトリのコミット: {commit or '不明'}\n"
        "ファイル:\n" + "".join(f"  {c}\n" for c in copied),
        encoding="utf-8",
    )
    log(f"ソースコード {len(copied)} ファイルを書き出し: {dest}")
    return dest


def summary_of(m: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in m.items() if k not in ("pages", "assets", "api")}


def make_zip(work: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in sorted(work.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(work).as_posix())


def deliver_local(dest: dict[str, Any], zip_path: Path, summary: dict[str, Any]) -> str:
    out_dir = Path(dest["path"])
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / (zip_path.name + ".partial")
    shutil.copyfile(zip_path, tmp)
    final = out_dir / zip_path.name
    tmp.replace(final)
    run_id = summary["run_id"]
    (out_dir / f"westudy_html_backup_{run_id}.summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "latest.json").write_text(
        json.dumps({"run_id": run_id, "zip": final.name, **{k: summary[k] for k in ("pages_by_status", "assets_by_status")}},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    prune_old_backups(out_dir, int(dest.get("keep_last") or 0))
    return str(final)


def prune_old_backups(out_dir: Path, keep_last: int) -> list[str]:
    """新しい順に keep_last 回分だけ残し、それより古い zip と summary.json を消す（0 なら何もしない）。"""
    if keep_last <= 0:
        return []
    zips = sorted(out_dir.glob("westudy_html_backup_*.zip"), reverse=True)  # 名前が日時なので名前順＝新しい順
    removed = []
    for z in zips[keep_last:]:
        run_id = z.stem.replace("westudy_html_backup_", "")
        for p in (z, out_dir / f"westudy_html_backup_{run_id}.summary.json"):
            if p.exists():
                p.unlink()
                removed.append(p.name)
    if removed:
        log(f"古いバックアップを整理（直近 {keep_last} 回を残す）: {', '.join(removed)}")
    return removed


def deliver_gdrive(dest: dict[str, Any], zip_path: Path, summary: dict[str, Any]) -> str:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload, MediaInMemoryUpload

    token = Path(dest["token_path"])
    creds = Credentials.from_authorized_user_file(str(token))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token.write_text(creds.to_json(), encoding="utf-8")
    svc = build("drive", "v3", credentials=creds, cache_discovery=False)
    parent = dest["folder_id"]
    sub = (dest.get("subfolder") or "").strip()
    if sub:
        q = (
            f"'{parent}' in parents and name = '{sub}' and "
            "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        )
        found = svc.files().list(q=q, fields="files(id)", supportsAllDrives=True,
                                 includeItemsFromAllDrives=True).execute().get("files", [])
        if found:
            parent = found[0]["id"]
        else:
            parent = svc.files().create(
                body={"name": sub, "mimeType": "application/vnd.google-apps.folder", "parents": [parent]},
                fields="id", supportsAllDrives=True,
            ).execute()["id"]
    media = MediaFileUpload(str(zip_path), mimetype="application/zip", resumable=True, chunksize=16 * 1024 * 1024)
    f = svc.files().create(body={"name": zip_path.name, "parents": [parent]}, media_body=media,
                           fields="id,webViewLink", supportsAllDrives=True).execute()
    svc.files().create(
        body={"name": f"westudy_html_backup_{summary['run_id']}.summary.json", "parents": [parent]},
        media_body=MediaInMemoryUpload(json.dumps(summary, ensure_ascii=False, indent=2).encode("utf-8"),
                                       mimetype="application/json"),
        supportsAllDrives=True,
    ).execute()
    return f.get("webViewLink") or f["id"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="WeStudy HTML・アセットのバックアップ")
    ap.add_argument("--config", type=Path, default=CONFIG_PATH)
    ap.add_argument("--max-pages", type=int, default=None, help="巡回ページ数の上限（お試しは 5 など）")
    ap.add_argument("--show", action="store_true", help="ブラウザを表示する")
    ap.add_argument("--work-root", type=Path, default=DEFAULT_WORK_ROOT)
    ap.add_argument("--no-upload", action="store_true", help="zip を作るだけで保存先へ置かない")
    ap.add_argument("--keep-work", action="store_true", help="展開済みの作業フォルダを残す")
    ap.add_argument("--export-source", action="store_true",
                    help="終了後、引き渡し用ソースコード一式を handover.source_dest に写す")
    ap.add_argument("--export-source-only", action="store_true", help="巡回せずソースコードの書き出しだけ行う")
    ap.add_argument("--resume", metavar="RUN_ID",
                    help="止まった回の続きから（作業フォルダ <work-root>/<RUN_ID> の _checkpoint.json を使う）")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    if args.export_source_only:
        export_source(cfg)
        return 0
    dest = resolve_destination(cfg)  # 先に検証して、長い巡回の後で失敗しないようにする
    if dest["type"] == "local" and not args.no_upload:
        parent = Path(dest["path"]).parent
        if not parent.is_dir():
            raise SystemExit(f"保存先の親フォルダがありません（同期されていない？）: {parent}")
    max_pages = args.max_pages or int((cfg.get("crawl") or {}).get("max_pages", 2000))

    run_id = args.resume or datetime.now().strftime("%Y%m%d-%H%M%S")
    work = args.work_root / run_id
    if args.resume and not (work / SiteBackup.CHECKPOINT).is_file():
        raise SystemExit(f"再開用の _checkpoint.json がありません: {work}")
    work.mkdir(parents=True, exist_ok=True)
    log(f"作業フォルダ: {work}")

    m = SiteBackup(cfg, work, headless=not args.show).run(run_id, max_pages, resume=bool(args.resume))
    summary = summary_of(m)
    log(f"ページ: {summary['pages_by_status']} / アセット: {summary['assets_by_status']}")
    ok_pages = summary["pages_by_status"].get("ok", 0)

    zip_path = args.work_root / f"westudy_html_backup_{run_id}.zip"
    make_zip(work, zip_path)
    log(f"zip: {zip_path} ({zip_path.stat().st_size / 1024 / 1024:.1f} MB)")
    if not args.keep_work:
        shutil.rmtree(work, ignore_errors=True)

    if ok_pages == 0:
        log("❌ 取得できたページが 0 件。保存先へは置きません。")
        return 1
    if args.no_upload:
        return 0
    where = deliver_local(dest, zip_path, summary) if dest["type"] == "local" else deliver_gdrive(dest, zip_path, summary)
    log(f"✅ 保存先へ配置: {where}")
    zip_path.unlink(missing_ok=True)
    if args.export_source:
        export_source(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
