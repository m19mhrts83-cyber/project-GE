#!/usr/bin/env python3
"""WeStudy HTML バックアップの単体テスト（ブラウザ・ネットワーク不要）。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import westudy_html_backup as b  # noqa: E402

KEEP = ["t", "paged"]


class TestUrls(unittest.TestCase):
    def test_normalize_drops_fragment_and_unknown_query(self):
        self.assertEqual(
            b.normalize_page_url("/lesson/abc/?utm=1#top", "https://westudy.co.jp/course/x", KEEP),
            "https://westudy.co.jp/lesson/abc",
        )

    def test_normalize_keeps_tab_query(self):
        self.assertEqual(
            b.normalize_page_url("https://westudy.co.jp/course/kami-ooyasan-club?t=forums", keep_query_keys=KEEP),
            "https://westudy.co.jp/course/kami-ooyasan-club?t=forums",
        )

    def test_normalize_rejects_non_http(self):
        for u in ("javascript:void(0)", "mailto:a@b", "#x", ""):
            self.assertIsNone(b.normalize_page_url(u, "https://westudy.co.jp/"))

    def test_should_follow(self):
        inc = [r"^https://westudy\.co\.jp/lesson/"]
        exc = ["logout"]
        self.assertTrue(b.should_follow("https://westudy.co.jp/lesson/a", inc, exc))
        self.assertFalse(b.should_follow("https://westudy.co.jp/lesson/logout", inc, exc))
        self.assertFalse(b.should_follow("https://example.com/lesson/a", inc, exc))
        self.assertFalse(b.should_follow("https://westudy.co.jp/mypage", inc, exc))

    def test_page_local_path(self):
        self.assertEqual(b.page_local_path("https://westudy.co.jp/lesson/abc"), "pages/lesson/abc.html")
        self.assertEqual(b.page_local_path("https://westudy.co.jp/"), "pages/index.html")
        self.assertEqual(
            b.page_local_path("https://westudy.co.jp/course/x?t=forums"), "pages/course/x__t-forums.html"
        )

    def test_page_local_path_decodes_japanese_slug(self):
        self.assertEqual(
            b.page_local_path("https://westudy.co.jp/forum/%E4%BF%AE%E7%B9%95"), "pages/forum/修繕.html"
        )

    def test_asset_local_path_query_hash_keeps_extension(self):
        p = b.asset_local_path("https://westudy.co.jp/wp-content/themes/a/style.css?ver=6.1")
        self.assertTrue(p.startswith("assets/westudy.co.jp/wp-content/themes/a/style__q"))
        self.assertTrue(p.endswith(".css"))

    def test_rel_from(self):
        self.assertEqual(
            b.rel_from("site/pages/lesson/a.html", "site/assets/westudy.co.jp/x.css"),
            "../../assets/westudy.co.jp/x.css",
        )


class TestParsing(unittest.TestCase):
    HTML = """<html><head><title> レッスン 1 </title>
      <link rel="stylesheet" href="/wp-content/a.css?ver=1">
      <link rel="canonical" href="https://westudy.co.jp/lesson/a">
      <script src="https://westudy.co.jp/wp-includes/b.js"></script>
      <style>.x{background:url('/img/bg.png')}</style></head>
      <body><a href="/lesson/b">次</a><a href="mailto:x@y">m</a>
      <img src="/img/1.jpg" srcset="/img/1.jpg 1x, /img/1@2x.jpg 2x">
      <div style="background-image:url(/img/d.png)"></div>
      <iframe src="https://player.vimeo.com/video/123"></iframe></body></html>"""

    def test_extract_refs(self):
        r = b.extract_refs(self.HTML, "https://westudy.co.jp/lesson/a")
        self.assertEqual(r["title"], "レッスン 1")
        self.assertEqual(r["links"], ["https://westudy.co.jp/lesson/b"])
        self.assertIn("https://westudy.co.jp/wp-content/a.css?ver=1", r["assets"])
        self.assertIn("https://westudy.co.jp/wp-includes/b.js", r["assets"])
        self.assertIn("https://westudy.co.jp/img/bg.png", r["assets"])
        self.assertIn("https://westudy.co.jp/img/1@2x.jpg", r["assets"])
        self.assertIn("https://westudy.co.jp/img/d.png", r["assets"])
        self.assertNotIn("https://westudy.co.jp/lesson/a", r["assets"])  # canonical は資産でない
        self.assertEqual(r["iframes"], ["https://player.vimeo.com/video/123"])

    def test_extract_css_refs(self):
        css = "@import 'base.css'; a{background:url(\"i.png\")} b{src:url(data:font/woff2;base64,AA)}"
        self.assertEqual(sorted(b.extract_css_refs(css)), ["base.css", "i.png"])

    def test_rewrite_refs(self):
        mapping = {"/img/1.jpg": "a.jpg", "/img/1@2x.jpg": "b.jpg", "/img/bg.png": "bg.png", "/lesson/b": "b.html"}
        out = b.rewrite_refs(self.HTML, mapping.get)
        self.assertIn('src="a.jpg"', out)
        self.assertIn('srcset="a.jpg 1x, b.jpg 2x"', out)
        self.assertIn("url('bg.png')", out)
        self.assertIn('href="b.html"', out)
        self.assertIn('href="mailto:x@y"', out)  # 解決できないものはそのまま


class TestHelpers(unittest.TestCase):
    def test_find_rest_nonce(self):
        html = '<script>var wpApiSettings = {"root":"https://westudy.co.jp/wp-json/","nonce":"a1b2c3d4e5"};</script>'
        self.assertEqual(b.find_rest_nonce(html), "a1b2c3d4e5")
        self.assertIsNone(b.find_rest_nonce("<html></html>"))

    def test_url_extension_and_host(self):
        self.assertEqual(b.url_extension("https://westudy.co.jp/wp-content/uploads/a.PDF?x=1"), "pdf")
        self.assertEqual(b.url_extension("https://westudy.co.jp/lesson/a"), "")
        self.assertTrue(b.is_site_host("https://cdn.westudy.co.jp/x"))
        self.assertFalse(b.is_site_host("https://drive.google.com/x.pdf"))


class TestEscapedQuery(unittest.TestCase):
    def test_rewrite_matches_entity_encoded_query(self):
        # 実サイト: href="...style.css?v=1&amp;amp;ver=2"。抽出値は 1 回戻した "&amp;ver" になる
        html = '<link rel="stylesheet" href="/t/style.css?v=1&amp;amp;ver=2">'
        r = b.extract_refs(html, "https://westudy.co.jp/course/x")
        self.assertEqual(r["assets"], ["https://westudy.co.jp/t/style.css?v=1&amp;ver=2"])
        out = b.rewrite_refs(html, {"/t/style.css?v=1&amp;ver=2": "local.css"}.get)
        self.assertIn('href="local.css"', out)


class TestDestination(unittest.TestCase):
    def test_env_override_and_expand(self):
        cfg = {"destination": {"type": "local", "path": "/a"}}
        d = b.resolve_destination(cfg, {"WESTUDY_BACKUP_DEST_PATH": "~/x"})
        self.assertEqual(d["path"], str(Path("~/x").expanduser()))

    def test_gdrive_requires_token(self):
        cfg = {"destination": {"type": "gdrive_api", "folder_id": "F"}}
        with self.assertRaises(ValueError):
            b.resolve_destination(cfg, {})

    def test_unknown_type(self):
        with self.assertRaises(ValueError):
            b.resolve_destination({"destination": {"type": "s3"}}, {})

    def test_repo_config_is_valid(self):
        cfg = b.load_config()
        d = b.resolve_destination(cfg, {})
        self.assertEqual(d["type"], "local")
        self.assertIn("217_westudyソースコードバックアップ", d["path"])


# ---- ブラウザとネットワークを差し替えて、巡回 → zip → 保存先 までを通す


class FakeDriver:
    def __init__(self, site: dict[str, str]) -> None:
        self.site = site
        self.current_url = ""
        self.page_source = ""

    def get(self, url: str) -> None:
        self.current_url = url
        self.page_source = self.site.get(url, "<html><title>404</title></html>")

    def execute_script(self, *_a):
        return False

    def execute_cdp_cmd(self, cmd, _params):
        if cmd == "Page.getLayoutMetrics":
            return {"cssContentSize": {"width": 1280, "height": 2000}}
        return {"data": "SlBH"}  # base64("JPG")

    def get_cookies(self):
        return [{"name": "wordpress_logged_in_x", "value": "v", "domain": "westudy.co.jp"}]

    def quit(self):
        pass


class FakeResp:
    def __init__(self, body: bytes, ctype: str, status: int = 200, headers: dict | None = None) -> None:
        self.body, self.status_code = body, status
        self.content, self.text = body, body.decode("utf-8", "replace")
        self.headers = {"Content-Type": ctype, **(headers or {})}

    def json(self):
        return json.loads(self.body)

    def iter_content(self, _n):
        yield self.body

    def close(self):
        pass


class FakeSession:
    def __init__(self, files: dict[str, tuple[bytes, str]]) -> None:
        self.files = files
        self.cookies = SimpleNamespace(set=lambda *a, **k: None)
        self.headers: dict[str, str] = {}
        self.calls: list[tuple[str, str | None]] = []

    def get(self, url, **k):
        self.calls.append((url, (k.get("headers") or {}).get("X-WP-Nonce")))
        if url in self.files:
            return FakeResp(*self.files[url])
        return FakeResp(b"", "text/html", 404)


class TestEndToEnd(unittest.TestCase):
    def test_backup_roundtrip(self):
        site = {
            "https://westudy.co.jp/course/c1": (
                '<html><head><title>コース</title><link rel="stylesheet" href="/s.css"></head>'
                '<body><a href="/lesson/l1">L1</a><a href="https://westudy.co.jp/wp-login.php?action=logout">out</a></body></html>'
            ),
            "https://westudy.co.jp/lesson/l1": (
                '<html><head><title>L1</title><link rel="stylesheet" href="/s.css"></head>'
                '<script>var wpApiSettings = {"nonce":"abcdef1234"};</script>'
                '<body><img src="/i.png"><a href="/course/c1">戻る</a>'
                '<a href="/wp-content/uploads/資料.pdf">資料</a>'
                '<a href="https://drive.google.com/file/d/X/view.pdf">外部</a>'
                '<iframe src="https://player.vimeo.com/video/9"></iframe>'
                '<video poster="https://player.vimeo.com/p.jpg"></video></body></html>'
            ),
        }
        files = {
            "https://westudy.co.jp/s.css": (b"body{background:url(bg.png)}", "text/css"),
            "https://westudy.co.jp/bg.png": (b"PNG1", "image/png"),
            "https://westudy.co.jp/i.png": (b"PNG2", "image/png"),
            "https://westudy.co.jp/wp-content/uploads/資料.pdf": (b"%PDF", "application/pdf"),
            "https://westudy.co.jp/robots.txt": (b"User-agent: *", "text/plain"),
            "https://westudy.co.jp/wp-json/wp/v2/types?context=view": (
                json.dumps({"page": {"rest_base": "pages"}, "attachment": {"rest_base": "media"}}).encode(),
                "application/json",
            ),
            "https://westudy.co.jp/wp-json/wp/v2/pages?per_page=100&page=1&context=view": (
                json.dumps([{"id": 1, "content": {"rendered": "<p>本文</p>"}}]).encode(),
                "application/json",
                200,
                {"X-WP-TotalPages": "1"},
            ),
        }
        drv = FakeDriver(site)
        wlp = SimpleNamespace(
            driver=drv,
            COURSE_TABS=[{"label": "神大家1.基礎", "url": "https://westudy.co.jp/course/c1"}],
            collect_sections_and_lessons=lambda tab: [
                {"section": "第1章", "title": "L1", "url": "https://westudy.co.jp/lesson/l1"}
            ],
            _safe_get=lambda url, retries=3: drv.get(url),
            login_westudy=lambda: None,
        )
        cfg = {
            "crawl": {
                "seeds": ["https://westudy.co.jp/course/c1"],
                "include": [r"^https://westudy\.co\.jp/(course|lesson)/"],
                "exclude": ["logout", r"/wp-login\.php"],
                "keep_query_keys": ["t"],
                "page_delay_sec": 0,
            },
            "assets": {"skip_hosts": ["player.vimeo.com"], "asset_delay_sec": 0},
            "attachments": {"extensions": ["pdf"], "max_mb": 1},
            "wp_json": {"enabled": True, "max_pages_per_type": 3, "skip_types": ["attachment"],
                        "extra_paths": ["/robots.txt", "/sitemap.xml"]},
            "screenshots": {"enabled": True, "include": [r"/lesson/"]},
        }
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = td / "work"
            sb = b.SiteBackup(cfg, work)
            sb.wlp = wlp
            sb.session = FakeSession(files)
            sb._start_browser = lambda: None
            sb._sync_cookies = lambda: None
            m = sb.run("RUN", max_pages=10)

            self.assertEqual(m["pages_by_status"], {"ok": 2})
            self.assertEqual(m["assets_by_status"], {"ok": 4, "skip_host": 1})
            self.assertEqual(m["attachments_ok"], 1)
            self.assertEqual(m["external_documents"], ["https://drive.google.com/file/d/X/view.pdf"])
            self.assertEqual(m["screenshots"], 1)
            self.assertTrue((work / "screenshots/lesson/l1.jpg").is_file())
            self.assertTrue(m["rest_nonce_found"])
            self.assertTrue((work / "api/wp-json/pages/page-001.json").is_file())
            self.assertFalse((work / "api/wp-json/media").exists())  # skip_types
            self.assertTrue((work / "api/extra/robots.txt").is_file())
            api_calls = [c for c in sb.session.calls if "/wp-json/" in c[0]]
            self.assertTrue(all(n == "abcdef1234" for _, n in api_calls))
            self.assertEqual(m["external_embeds"], ["https://player.vimeo.com/video/9"])

            lesson = (work / "site/pages/lesson/l1.html").read_text(encoding="utf-8")
            self.assertIn('href="../../assets/westudy.co.jp/s.css"', lesson)
            self.assertIn('src="../../assets/westudy.co.jp/i.png"', lesson)
            self.assertIn('href="../course/c1.html"', lesson)
            self.assertIn('href="../../assets/westudy.co.jp/wp-content/uploads/資料.pdf"', lesson)
            raw = (work / "raw/pages/lesson/l1.html").read_text(encoding="utf-8")
            self.assertIn('href="/s.css"', raw)  # 原本は書き換えない
            css = (work / "site/assets/westudy.co.jp/s.css").read_text(encoding="utf-8")
            self.assertEqual(css, "body{background:url(bg.png)}")
            self.assertTrue((work / "raw/assets/westudy.co.jp/s.css").is_file())
            structure = json.loads((work / "structure.json").read_text(encoding="utf-8"))
            self.assertEqual(structure[0]["sections"][0]["lessons"][0]["local"], "pages/lesson/l1.html")
            self.assertIn('href="site/pages/lesson/l1.html"', (work / "index.html").read_text(encoding="utf-8"))

            zip_path = td / "out.zip"
            b.make_zip(work, zip_path)
            with zipfile.ZipFile(zip_path) as zf:
                self.assertIn("site/pages/lesson/l1.html", zf.namelist())
            dest = td / "dest"
            final = b.deliver_local({"path": str(dest)}, zip_path, b.summary_of(m))
            self.assertTrue(Path(final).is_file())
            latest = json.loads((dest / "latest.json").read_text(encoding="utf-8"))
            self.assertEqual(latest["zip"], "out.zip")
            self.assertFalse(list(dest.glob("*.partial")))


class InvalidSessionIdException(Exception):
    pass


class TimeoutException(Exception):
    pass


class TestRecovery(unittest.TestCase):
    def _backup(self, td: Path, site: dict[str, str], *, fail_first: str | None = None):
        drivers: list[FakeDriver] = []
        logins: list[int] = []

        def create_driver(headless=True):
            d = FakeDriver(site)
            drivers.append(d)
            return d

        wlp = SimpleNamespace(
            driver=create_driver(),
            COURSE_TABS=[],
            collect_sections_and_lessons=lambda tab: [],
            create_driver=create_driver,
            login_westudy=lambda: logins.append(1),
        )
        state = {"failed": False}

        def safe_get(url, retries=3):
            if url == fail_first and not state["failed"]:
                state["failed"] = True
                raise InvalidSessionIdException("invalid session id")
            wlp.driver.get(url)

        wlp._safe_get = safe_get
        cfg = {
            "crawl": {"seeds": list(site), "include": [r"/lesson/"], "exclude": [],
                      "page_delay_sec": 0, "restart_browser_every": 0},
            "assets": {"asset_delay_sec": 0},
        }
        sb = b.SiteBackup(cfg, td)
        sb.wlp = wlp
        sb.session = FakeSession({})
        sb._start_browser = lambda: None
        sb._sync_cookies = lambda: None
        return sb, drivers, logins

    def test_is_browser_dead(self):
        self.assertTrue(b.is_browser_dead(InvalidSessionIdException("x")))
        self.assertTrue(b.is_browser_dead(RuntimeError("Message: invalid session id")))
        self.assertFalse(b.is_browser_dead(TimeoutException("slow")))
        self.assertFalse(b.is_browser_dead(ValueError("x")))

    def test_dead_session_restarts_browser_and_relogs_in(self):
        site = {f"https://westudy.co.jp/lesson/{i}": f"<html><title>{i}</title></html>" for i in range(3)}
        with tempfile.TemporaryDirectory() as td:
            sb, drivers, logins = self._backup(Path(td), site, fail_first="https://westudy.co.jp/lesson/1")
            m = sb.run("R", max_pages=10)
            self.assertEqual(m["pages_by_status"], {"ok": 3})
            self.assertEqual(len(drivers), 2)  # 初期 + 再起動 1 回
            self.assertEqual(len(logins), 1)

    def test_resume_from_checkpoint(self):
        site = {f"https://westudy.co.jp/lesson/{i}": f"<html><title>{i}</title></html>" for i in range(4)}
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            sb, _, _ = self._backup(td, site)
            sb.crawl_pages([], max_pages=2)  # 2 ページで止まった想定
            sb.save_checkpoint()
            self.assertTrue((td / b.SiteBackup.CHECKPOINT).is_file())

            sb2, drivers, _ = self._backup(td, site)
            fetched: list[str] = []
            orig = sb2.wlp._safe_get
            sb2.wlp._safe_get = lambda url, retries=3: (fetched.append(url), orig(url))
            m = sb2.run("R", max_pages=10, resume=True)
            self.assertEqual(m["pages_by_status"], {"ok": 4})
            self.assertEqual(fetched, ["https://westudy.co.jp/lesson/2", "https://westudy.co.jp/lesson/3"])
            self.assertFalse((td / b.SiteBackup.CHECKPOINT).exists())  # 完走したら消す


class TestStatsAndHandover(unittest.TestCase):
    def test_pages_by_kind(self):
        pages = {
            "https://westudy.co.jp/course/a": {"status": "ok"},
            "https://westudy.co.jp/lesson/b": {"status": "ok"},
            "https://westudy.co.jp/lesson/c": {"status": "error"},
            "https://westudy.co.jp/forum/d": {"status": "ok"},
        }
        self.assertEqual(b.pages_by_kind(pages), {"course": 1, "forum": 1, "lesson": 1})

    def test_assets_by_kind(self):
        assets = {
            "1": {"url": "https://x/a.css?v=1", "status": "ok", "bytes": 10},
            "2": {"url": "https://x/b.js", "status": "ok", "bytes": 5},
            "3": {"url": "https://x/c.png", "status": "ok", "bytes": 7},
            "4": {"url": "https://x/f.woff2", "status": "ok", "bytes": 3},
            "5": {"url": "https://x/d.pdf", "status": "ok", "bytes": 9, "kind": "attachment"},
            "6": {"url": "https://x/img", "status": "ok", "bytes": 2, "content_type": "image/jpeg"},
            "7": {"url": "https://x/e.png", "status": "http_error"},
        }
        self.assertEqual(
            b.assets_by_kind(assets),
            {"attachment": {"count": 1, "bytes": 9}, "css": {"count": 1, "bytes": 10},
             "font": {"count": 1, "bytes": 3}, "image": {"count": 2, "bytes": 9},
             "js": {"count": 1, "bytes": 5}},
        )

    def test_export_source_copies_listed_files(self):
        cfg = b.load_config()
        with tempfile.TemporaryDirectory() as td:
            out = b.export_source(cfg, Path(td) / "src")
            for rel in cfg["handover"]["files"]:
                self.assertTrue((out / rel).is_file(), rel)
            self.assertIn("scripts/westudy_html_backup.py", (out / "VERSION.txt").read_text(encoding="utf-8"))

    def test_config_folders_are_separated(self):
        cfg = b.load_config()
        dest = b.resolve_destination(cfg, {})
        self.assertTrue(dest["path"].endswith("02_バックアップデータ"))
        self.assertTrue(cfg["handover"]["source_dest"].endswith("01_ソースコード"))

    def test_extra_host_attachment_is_downloaded(self):
        site = {
            "https://westudy.co.jp/lesson/a": (
                '<html><a href="https://kamiooyasan.jp/wp-content/uploads/x.pdf">x</a>'
                '<a href="https://www.city.example.jp/y.pdf">y</a></html>'
            )
        }
        drv = FakeDriver(site)
        wlp = SimpleNamespace(driver=drv, COURSE_TABS=[], collect_sections_and_lessons=lambda t: [],
                              _safe_get=lambda url, retries=3: drv.get(url), login_westudy=lambda: None)
        cfg = {"crawl": {"seeds": list(site), "include": [], "exclude": [], "page_delay_sec": 0},
               "assets": {"asset_delay_sec": 0},
               "attachments": {"extensions": ["pdf"], "extra_hosts": ["kamiooyasan.jp"]}}
        with tempfile.TemporaryDirectory() as td:
            sb = b.SiteBackup(cfg, Path(td))
            sb.wlp = wlp
            sb.session = FakeSession({"https://kamiooyasan.jp/wp-content/uploads/x.pdf": (b"%PDF", "application/pdf")})
            sb._start_browser = lambda: None
            sb._sync_cookies = lambda: None
            m = sb.run("R", max_pages=5)
            self.assertEqual(m["attachments_ok"], 1)
            self.assertEqual(m["external_documents"], ["https://www.city.example.jp/y.pdf"])
            self.assertEqual(m["assets_by_kind"], {"attachment": {"count": 1, "bytes": 4}})


class TestPrune(unittest.TestCase):
    def test_keep_last(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            for rid in ("20261028-130011", "20261101-120000", "20261108-120000"):
                (d / f"westudy_html_backup_{rid}.zip").write_bytes(b"z")
                (d / f"westudy_html_backup_{rid}.summary.json").write_text("{}")
            self.assertEqual(b.prune_old_backups(d, 0), [])
            removed = b.prune_old_backups(d, 2)
            self.assertEqual(sorted(removed), ["westudy_html_backup_20261028-130011.summary.json",
                                               "westudy_html_backup_20261028-130011.zip"])
            self.assertEqual(len(list(d.glob("*.zip"))), 2)


if __name__ == "__main__":
    unittest.main()
