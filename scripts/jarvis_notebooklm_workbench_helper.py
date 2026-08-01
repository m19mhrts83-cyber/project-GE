#!/usr/bin/env python3
"""
NotebookLM 作業セット用 localhost ヘルパー。

ダッシュボード /notebooklm が Mac 上で fetch すると Finder＋NotebookLM を開く。

  python scripts/jarvis_notebooklm_workbench_helper.py
  # 既定: http://127.0.0.1:8766/notebooklm-workbench
"""
from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from jarvis_notebooklm_workbench_open import open_workbench  # noqa: E402

CFG_PATH = REPO / "config" / "notebooklm_workbench.yaml"


def _cfg() -> dict:
    return yaml.safe_load(CFG_PATH.read_text(encoding="utf-8")) or {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _cors(self) -> None:
        origin = self.headers.get("Origin") or "*"
        # ローカル／Vercel ダッシュボードからの fetch を許可
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Vary", "Origin")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        cfg = _cfg()
        path = urlparse(self.path).path.rstrip("/") or "/"
        want = str(cfg.get("helper_path") or "/notebooklm-workbench").rstrip("/") or "/"

        if path in ("/health", "/"):
            body = json.dumps({"ok": True, "service": "notebooklm-workbench"}).encode()
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path != want:
            self.send_response(404)
            self._cors()
            self.end_headers()
            return

        rc = open_workbench(dry_run=False, skip_browser=False)
        body = json.dumps({"ok": rc == 0, "opened": rc == 0}).encode()
        self.send_response(200 if rc == 0 else 500)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    cfg = _cfg()
    host = str(cfg.get("helper_host") or "127.0.0.1")
    port = int(os.environ.get("NOTEBOOKLM_HELPER_PORT") or cfg.get("helper_port") or 8766)
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"# notebooklm workbench helper http://{host}:{port}/notebooklm-workbench", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
