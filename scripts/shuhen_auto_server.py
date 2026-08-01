#!/usr/bin/env python3
"""周辺MAP 単独Web ローカル／検証サーバ.

  cd ~/git-repos
  set -a && source .env.jarvis_private && set +a
  /Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/shuhen_auto_server.py
  # http://127.0.0.1:8770/shuhen-auto.html

既定ポートは 8770（8765 は Jarvis triage ダッシュボードと競合）。

環境変数:
  SHUHEN_AUTO_PORT=8770
  SHUHEN_AUTO_TOKEN=任意（設定時は ?token= または Header X-Shuhen-Token）
  SHUHEN_AUTO_RATE_PER_HOUR=20
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from collections import defaultdict
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from shuhen_auto_pipeline import rebuild_from_exclusions, run_c1, run_pipeline  # noqa: E402

PORT = int(os.environ.get("SHUHEN_AUTO_PORT") or "8770")
TOKEN = (os.environ.get("SHUHEN_AUTO_TOKEN") or "").strip()
RATE = int(os.environ.get("SHUHEN_AUTO_RATE_PER_HOUR") or "20")
MAPS_KEY_PLACEHOLDER = "__GOOGLE_MAPS_BROWSER_KEY__"

_rate_lock = threading.Lock()
_rate_hits: dict[str, list[float]] = defaultdict(list)


def _client_ip(handler: SimpleHTTPRequestHandler) -> str:
    return handler.client_address[0] if handler.client_address else "unknown"


def _rate_ok(ip: str) -> bool:
    now = time.time()
    with _rate_lock:
        hits = [t for t in _rate_hits[ip] if now - t < 3600]
        if len(hits) >= RATE:
            _rate_hits[ip] = hits
            return False
        hits.append(now)
        _rate_hits[ip] = hits
        return True


def _auth_ok(handler: SimpleHTTPRequestHandler) -> bool:
    if not TOKEN:
        return True
    header = (handler.headers.get("X-Shuhen-Token") or "").strip()
    if header == TOKEN:
        return True
    qs = parse_qs(urlparse(handler.path).query)
    return (qs.get("token") or [""])[0] == TOKEN


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Shuhen-Token")

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _serve_js_with_maps_key(self) -> bool:
        """ローカル検証用: shuhen-auto.js のプレースホルダへ Maps キーを注入する."""
        key = (os.environ.get("GOOGLE_MAPS_API_KEY") or "").strip()
        if not key:
            return False
        js_path = ROOT / "shuhen-auto.js"
        if not js_path.is_file():
            return False
        text = js_path.read_text(encoding="utf-8")
        if MAPS_KEY_PLACEHOLDER not in text:
            return False
        body = text.replace(MAPS_KEY_PLACEHOLDER, key, 1).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
        return True

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/shuhen-auto", "/shuhen-auto/"):
            self.path = "/shuhen-auto.html"
            path = "/shuhen-auto.html"
        if path == "/api/health":
            self._json(
                200,
                {
                    "ok": True,
                    "gemini": bool(os.environ.get("GEMINI_API_KEY")),
                    "maps": bool(os.environ.get("GOOGLE_MAPS_API_KEY")),
                    "token_required": bool(TOKEN),
                    "port": PORT,
                },
            )
            return
        if path == "/shuhen-auto.js" and self._serve_js_with_maps_key():
            return
        return super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path not in ("/api/run", "/api/c1", "/api/rebuild"):
            self._json(404, {"ok": False, "error": "not found"})
            return
        if not _auth_ok(self):
            self._json(401, {"ok": False, "error": "unauthorized"})
            return
        ip = _client_ip(self)
        if not _rate_ok(ip):
            self._json(429, {"ok": False, "error": f"rate limit ({RATE}/hour)"})
            return
        try:
            data = self._read_json()
        except Exception:
            self._json(400, {"ok": False, "error": "invalid json"})
            return

        if path == "/api/run":
            name = (data.get("property_name") or "").strip()
            address = (data.get("address") or "").strip()
            if not name or not address:
                self._json(400, {"ok": False, "error": "property_name と address は必須です"})
                return
            try:
                result = run_pipeline(
                    property_name=name,
                    address=address,
                    target=(data.get("target") or "").strip(),
                    facility_count=int(data.get("facility_count") or 15),
                )
                self._json(200, {"ok": True, "result": result})
            except Exception as e:
                self._json(500, {"ok": False, "error": str(e)})
            return

        if path == "/api/c1":
            job_id = (data.get("job_id") or "").strip()
            if not job_id:
                self._json(400, {"ok": False, "error": "job_id 必須"})
                return
            try:
                c1 = run_c1(job_id, timeout_sec=int(data.get("timeout_sec") or 120))
                self._json(200, {"ok": c1.get("status") == "ready", "c1": c1})
            except Exception as e:
                self._json(500, {"ok": False, "error": str(e)})
            return

        if path == "/api/rebuild":
            job_id = (data.get("job_id") or "").strip()
            if not job_id:
                self._json(400, {"ok": False, "error": "job_id 必須"})
                return
            exclude_ids = data.get("exclude_ids") or []
            if not isinstance(exclude_ids, list):
                self._json(400, {"ok": False, "error": "exclude_ids は配列です"})
                return
            try:
                result = rebuild_from_exclusions(
                    job_id, exclude_ids=[str(x) for x in exclude_ids]
                )
                self._json(200, {"ok": True, "result": result})
            except Exception as e:
                self._json(500, {"ok": False, "error": str(e)})
            return


def main() -> int:
    if not os.environ.get("GEMINI_API_KEY"):
        print("WARN: GEMINI_API_KEY 未設定", file=sys.stderr)
    if not os.environ.get("GOOGLE_MAPS_API_KEY"):
        print("WARN: GOOGLE_MAPS_API_KEY 未設定", file=sys.stderr)

    class ReuseHTTPServer(ThreadingHTTPServer):
        allow_reuse_address = True

    server = ReuseHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Shuhen Auto http://127.0.0.1:{PORT}/shuhen-auto.html")
    print(f"health http://127.0.0.1:{PORT}/api/health")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
