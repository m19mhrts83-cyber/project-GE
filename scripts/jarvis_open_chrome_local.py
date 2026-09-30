#!/usr/bin/env python3
"""KURASHIFT 用: URL を Google Chrome で開くローカルヘルパー（Cursor 中央ブラウザ回避）。

  起動: python scripts/jarvis_open_chrome_local.py
  または: launchd/install_open_chrome_local_launchd.sh

  GET http://127.0.0.1:18765/open-chrome?url=https://...
"""

from __future__ import annotations

import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

HOST = "127.0.0.1"
PORT = 18765


class Handler(BaseHTTPRequestHandler):
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return
        if parsed.path != "/open-chrome":
            self.send_response(404)
            self._cors()
            self.end_headers()
            return
        qs = parse_qs(parsed.query)
        url = (qs.get("url") or [""])[0].strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            self.send_response(400)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":false,"error":"bad_url"}')
            return
        subprocess.run(
            ["open", "-a", "Google Chrome", url],
            check=False,
            capture_output=True,
        )
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "url": url}).encode("utf-8"))

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        sys.stderr.write(f"[open-chrome] {fmt % args}\n")


def main() -> int:
    httpd = HTTPServer((HOST, PORT), Handler)
    print(f"jarvis_open_chrome_local listening on http://{HOST}:{PORT}/open-chrome", flush=True)
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
