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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Vary", "Origin")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        cfg = _cfg()
        path = urlparse(self.path).path.rstrip("/") or "/"
        want = str(cfg.get("helper_path") or "/notebooklm-workbench").rstrip("/") or "/"

        if path in ("/health", "/"):
            self._json(200, {"ok": True, "service": "notebooklm-workbench"})
            return

        if path == "/notebooklm-studio":
            self._json(
                200,
                {
                    "ok": True,
                    "hint": "POST with JSON {artifact, prompt_file?, dry_run?} to start Studio runner",
                    "docs": "docs/N1_NotebookLM/Jarvis_NotebookLM_Studio自動化.md",
                },
            )
            return

        if path != want:
            self.send_response(404)
            self._cors()
            self.end_headers()
            return

        rc = open_workbench(dry_run=False, skip_browser=False)
        self._json(200 if rc == 0 else 500, {"ok": rc == 0, "opened": rc == 0})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/notebooklm-studio":
            self.send_response(404)
            self._cors()
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            self._json(400, {"ok": False, "error": "invalid_json"})
            return

        artifact = str(payload.get("artifact") or "infographic").strip()
        if artifact not in ("infographic", "slide_deck"):
            self._json(400, {"ok": False, "error": "artifact must be infographic|slide_deck"})
            return

        dry_run = bool(payload.get("dry_run", True))
        confirm = bool(payload.get("confirm_generate", False))
        wait_save = bool(payload.get("wait_and_save", False))
        prompt_file = payload.get("prompt_file")
        prompt_inline = payload.get("prompt_inline")
        prompt_section = str(payload.get("prompt_section") or "info")
        notebook_url = payload.get("notebook_url")
        notebook_key = payload.get("notebook_key") or "hokkaido_gw2027"

        if not prompt_file and not prompt_inline:
            self._json(
                400,
                {
                    "ok": False,
                    "error": "prompt_file or prompt_inline required",
                    "docs": "docs/N1_NotebookLM/Jarvis_NotebookLM_Studio自動化.md",
                },
            )
            return

        py = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")
        script = REPO / "scripts" / "jarvis_notebooklm_studio_run.py"
        cmd = [
            str(py),
            str(script),
            "--artifact",
            artifact,
            f"--prompt-section={prompt_section}",
            f"--notebook-key={notebook_key}",
        ]
        if notebook_url:
            cmd += ["--notebook-url", str(notebook_url)]
        if prompt_file:
            cmd += ["--prompt-file", str(prompt_file)]
        if prompt_inline:
            cmd += ["--prompt-inline", str(prompt_inline)]
        if dry_run:
            cmd.append("--dry-run")
        if confirm:
            cmd.append("--confirm-generate")
        if wait_save:
            cmd.append("--wait-and-save")

        # 非同期起動（長時間生成で HTTP をブロックしない）
        import subprocess

        log = Path("/tmp/notebooklm_studio_helper.log")
        with log.open("a", encoding="utf-8") as fh:
            fh.write(f"\n# start {cmd}\n")
            fh.flush()
            subprocess.Popen(
                cmd,
                cwd=str(REPO),
                stdout=fh,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        self._json(
            202,
            {
                "ok": True,
                "started": True,
                "dry_run": dry_run,
                "confirm_generate": confirm,
                "log": str(log),
                "cmd": cmd,
            },
        )


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
