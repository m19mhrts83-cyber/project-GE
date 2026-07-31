#!/usr/bin/env python3
"""
Jarvis: 夜間トリアージ用ダッシュボード

  python scripts/jarvis_triage_dashboard.py --write
  python scripts/jarvis_triage_dashboard.py --serve   # http://127.0.0.1:8765/
  python scripts/jarvis_triage_dashboard.py --open
"""
from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_DIR = REPO / ".jarvis_state" / "night_triage"
QUEUE_PATH = STATE_DIR / "queue.json"
CONFIG_PATH = STATE_DIR / "config.json"
HTML_PATH = STATE_DIR / "dashboard.html"
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"
TRIAGE = REPO / "scripts" / "jarvis_night_triage.py"

# --serve で生成した HTML だけ操作リンクを有効にする
_SERVE_MODE = False


def load_queue() -> dict:
    if not QUEUE_PATH.is_file():
        return {"items": [], "updated_at": None}
    return json.loads(QUEUE_PATH.read_text(encoding="utf-8"))


def save_queue(data: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")
    QUEUE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_config() -> dict:
    if not CONFIG_PATH.is_file():
        return {"engine": "gemini", "gemini_model": "gemini-flash-lite-latest"}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"engine": "gemini"}


def save_config(cfg: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def set_engine(engine: str) -> bool:
    if engine not in ("gemini", "cursor"):
        return False
    cfg = load_config()
    cfg["engine"] = engine
    save_config(cfg)
    return True


def set_status(item_key: str, status: str) -> bool:
    q = load_queue()
    for it in q.get("items", []):
        if str(it.get("seq")) == item_key or str(it.get("id")) == item_key:
            it["status"] = status
            it["updated_at"] = datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")
            save_queue(q)
            return True
    return False


def prefer_engine(_q: dict | None = None) -> str:
    return (load_config().get("engine") or "gemini").strip() or "gemini"


def find_cursor_agent() -> str | None:
    for name in ("agent", "cursor-agent"):
        p = shutil.which(name)
        if p:
            return p
    local = Path.home() / ".local" / "bin"
    for name in ("agent", "cursor-agent"):
        p = local / name
        if p.is_file() and os_access_x(p):
            return str(p)
    return None


def os_access_x(p: Path) -> bool:
    import os

    return os.access(p, os.X_OK)


def cursor_login_status() -> tuple[bool, str]:
    """(logged_in, message)"""
    exe = find_cursor_agent()
    if not exe:
        return False, "Cursor Agent CLI 未インストール（~/.local/bin/agent）"
    try:
        r = subprocess.run(
            [exe, "status"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        low = out.lower()
        if "not logged in" in low or "authentication required" in low:
            return False, "Cursor Agent 未ログイン（ターミナルで agent login）"
        if r.returncode == 0 or "logged in" in low:
            return True, "Cursor Agent ログイン済み"
        # 不明だがインストールはある
        if "error" in low and "login" in low:
            return False, "Cursor Agent 未ログイン（agent login が必要）"
        return False, f"Cursor Agent 状態不明: {out[:120] or f'exit {r.returncode}'}"
    except Exception as e:
        return False, f"Cursor Agent 確認失敗: {e}"


def render_html(q: dict, *, serve_mode: bool | None = None) -> str:
    serve = _SERVE_MODE if serve_mode is None else serve_mode
    items = list(q.get("items") or [])
    pending = [i for i in items if i.get("status") == "pending"]
    pending.sort(key=lambda x: x.get("received_at") or "")
    others = [i for i in items if i.get("status") != "pending"]
    others.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    updated = html.escape(str(q.get("updated_at") or "—"))
    engine = prefer_engine(q)
    gemini_checked = "checked" if engine == "gemini" else ""
    cursor_checked = "checked" if engine == "cursor" else ""

    cursor_ok, cursor_msg = cursor_login_status() if serve else (True, "")
    warn_block = ""
    if serve and engine == "cursor" and not cursor_ok:
        warn_block = f"""
        <div class="warn">
          注意: {html.escape(cursor_msg)}。未ログインのままだと夜間バッチの下書き生成が失敗します。
          ターミナルで <code>agent login</code> を実行してください。
        </div>
        """

    if serve:
        engine_panel = f"""
        <div class="engine-panel">
          <span class="engine-label">下書きエンジン（次回バッチから反映）</span>
          <label class="engine-opt"><input type="radio" name="engine" value="gemini" {gemini_checked}
            onchange="location.href='/api/engine?engine=gemini'"/> Gemini（無料枠）</label>
          <label class="engine-opt"><input type="radio" name="engine" value="cursor" {cursor_checked}
            onchange="location.href='/api/engine?engine=cursor'"/> Cursor Agent</label>
          <span class="engine-hint">現在: <strong>{html.escape(engine)}</strong></span>
        </div>
        {warn_block}
        """
        howto = """
        <ol class="howto">
          <li>pending を上から確認（古い順）。不要なら「スキップ」「後で」</li>
          <li>送る件は「送信指示をコピー」→ Cursor に貼る（例: 夜間下書き #1 を送って）</li>
          <li>Jarvis が下書きをプレビュー → 承認後に送信（自動送信なし）</li>
        </ol>
        """
    else:
        engine_panel = f"""
        <div class="engine-panel static">
          <span class="engine-label">既定エンジン: <strong>{html.escape(engine)}</strong></span>
          <p class="engine-hint">エンジン切替・スキップ等の操作は
            <code>python scripts/jarvis_triage_dashboard.py --serve</code>
            → <a href="http://127.0.0.1:8765/">http://127.0.0.1:8765/</a> で開いてください（この静的 HTML では書き戻せません）。
          </p>
        </div>
        """
        howto = """
        <p class="sub">閲覧専用。操作する場合は <code>--serve</code> で開いてください。</p>
        """

    def card(it: dict, show_ab: bool) -> str:
        seq = it.get("seq") or "—"
        st = it.get("status") or ""
        pri = it.get("priority") or ""
        partner = html.escape(str(it.get("partner") or ""))
        folder = html.escape(str(it.get("folder") or ""))
        subject = html.escape(str(it.get("subject") or ""))
        received = html.escape(str(it.get("received_at") or ""))
        summary = html.escape(str(it.get("summary") or ""))
        reason = html.escape(str(it.get("reason") or ""))
        draft = html.escape(str(it.get("draft_text") or ""))
        dg = html.escape(str(it.get("draft_gemini") or ""))
        dc = html.escape(str(it.get("draft_cursor") or ""))
        iid = html.escape(str(it.get("id") or ""))
        ab = ""
        if show_ab and (dg or dc):
            ab = f"""
            <div class="ab">
              <div><h4>Gemini</h4><pre>{dg or '（なし）'}</pre></div>
              <div><h4>Cursor Agent</h4><pre>{dc or '（なし）'}</pre></div>
            </div>
            """
        actions = ""
        if st == "pending" and serve:
            actions = f"""
            <div class="actions">
              <button type="button" onclick="copyCmd({json.dumps(f'夜間下書き #{seq} を送って')})">送信指示をコピー</button>
              <a class="btn" href="/api/status?id={iid}&status=snoozed">後で</a>
              <a class="btn" href="/api/status?id={iid}&status=skipped">スキップ</a>
            </div>
            """
        elif st == "pending" and not serve:
            actions = f"""
            <div class="actions">
              <button type="button" onclick="copyCmd({json.dumps(f'夜間下書き #{seq} を送って')})">送信指示をコピー</button>
              <span class="meta">スキップ等は --serve で</span>
            </div>
            """
        return f"""
        <article class="card pri-{html.escape(pri)} status-{html.escape(st)}">
          <header>
            <span class="seq">#{seq}</span>
            <span class="pri">{html.escape(pri)}</span>
            <span class="st">{html.escape(st)}</span>
            <strong>{partner}</strong>
            <span class="meta">{folder} · {received}</span>
          </header>
          <h3>{subject}</h3>
          <p class="sum">{summary}</p>
          {f'<p class="reason">{reason}</p>' if reason else ''}
          <details>
            <summary>下書きを見る</summary>
            <pre>{draft or '（未生成）'}</pre>
            {ab}
          </details>
          {actions}
        </article>
        """

    cards_p = "\n".join(card(i, True) for i in pending) or "<p>pending なし</p>"
    cards_o = "\n".join(card(i, False) for i in others[:40])

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Jarvis 夜間トリアージ</title>
<style>
  :root {{
    --bg: #f6f3ee; --ink: #1c1917; --muted: #78716c; --line: #e7e5e4;
    --card: #fffdf9; --accent: #0f766e; --high: #b91c1c; --med: #b45309; --low: #57534e;
    --warn-bg: #fff7ed; --warn-ink: #9a3412;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: "Hiragino Sans", "Noto Sans JP", sans-serif;
    background: radial-gradient(1200px 600px at 10% -10%, #dbeafe55, transparent),
                radial-gradient(900px 500px at 100% 0%, #fde68a44, transparent), var(--bg);
    color: var(--ink); line-height: 1.5;
  }}
  main {{ max-width: 960px; margin: 0 auto; padding: 28px 18px 80px; }}
  h1 {{ font-size: 1.45rem; margin: 0 0 4px; letter-spacing: 0.02em; }}
  .sub {{ color: var(--muted); font-size: 0.9rem; margin-bottom: 12px; }}
  .howto {{ margin: 0 0 16px; padding-left: 1.2rem; font-size: 0.9rem; color: var(--muted); }}
  .howto li {{ margin: 2px 0; }}
  .engine-panel {{
    background: var(--card); border: 1px solid var(--line); border-radius: 10px;
    padding: 12px 14px; margin-bottom: 14px; display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
  }}
  .engine-label {{ font-size: 0.9rem; margin-right: 4px; }}
  .engine-opt {{ font-size: 0.9rem; cursor: pointer; }}
  .engine-hint {{ color: var(--muted); font-size: 0.85rem; }}
  .engine-panel.static {{ display: block; }}
  .warn {{
    background: var(--warn-bg); color: var(--warn-ink); border: 1px solid #fed7aa;
    border-radius: 8px; padding: 10px 12px; margin: -6px 0 14px; font-size: 0.88rem;
  }}
  .warn code {{ background: #ffedd5; padding: 1px 4px; border-radius: 3px; }}
  .stats {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 18px; }}
  .stat {{ background: var(--card); border: 1px solid var(--line); padding: 10px 14px; border-radius: 10px; }}
  .card {{
    background: var(--card); border: 1px solid var(--line); border-radius: 12px;
    padding: 14px 16px; margin: 12px 0; box-shadow: 0 1px 0 #00000008;
  }}
  .card header {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline; font-size: 0.85rem; }}
  .seq {{ font-weight: 700; color: var(--accent); }}
  .pri {{ text-transform: uppercase; font-size: 0.75rem; padding: 1px 6px; border-radius: 4px; background: #f5f5f4; }}
  .pri-high .pri {{ background: #fee2e2; color: var(--high); }}
  .pri-medium .pri {{ background: #ffedd5; color: var(--med); }}
  .pri-low .pri {{ background: #f5f5f4; color: var(--low); }}
  .st {{ color: var(--muted); }}
  .meta {{ color: var(--muted); }}
  h3 {{ font-size: 1.05rem; margin: 8px 0 6px; font-weight: 600; }}
  .sum {{ margin: 0 0 6px; }}
  .reason {{ color: var(--muted); font-size: 0.9rem; margin: 0 0 8px; }}
  pre {{
    white-space: pre-wrap; background: #fafaf9; border: 1px solid var(--line);
    padding: 12px; border-radius: 8px; font-size: 0.88rem; overflow-x: auto;
  }}
  .ab {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }}
  @media (max-width: 800px) {{ .ab {{ grid-template-columns: 1fr; }} }}
  .actions {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; align-items: center; }}
  button, .btn {{
    appearance: none; border: 1px solid var(--line); background: #fff; color: var(--ink);
    padding: 6px 12px; border-radius: 8px; cursor: pointer; text-decoration: none; font-size: 0.88rem;
  }}
  button:hover, .btn:hover {{ border-color: var(--accent); color: var(--accent); }}
  h2 {{ font-size: 1.1rem; margin: 28px 0 8px; }}
  .toast {{
    position: fixed; bottom: 18px; right: 18px; background: #134e4a; color: #ecfdf5;
    padding: 10px 14px; border-radius: 8px; display: none; max-width: 90vw;
  }}
  code {{ font-size: 0.85em; }}
</style>
</head>
<body>
<main>
  <h1>夜間メールトリアージ</h1>
  <p class="sub">更新: {updated} · 送信は Cursor で「夜間下書き #N を送って」（自動送信なし）</p>
  {engine_panel}
  {howto}
  <div class="stats">
    <div class="stat">pending <strong>{len(pending)}</strong></div>
    <div class="stat">その他表示 <strong>{min(len(others), 40)}</strong></div>
  </div>
  <h2>要対応（古い順）</h2>
  {cards_p}
  <h2>処理済み・スキップ（直近）</h2>
  {cards_o}
</main>
<div class="toast" id="toast"></div>
<script>
function copyCmd(t) {{
  navigator.clipboard.writeText(t).then(() => {{
    const el = document.getElementById('toast');
    el.textContent = 'コピーしました: ' + t;
    el.style.display = 'block';
    setTimeout(() => el.style.display = 'none', 2200);
  }});
}}
</script>
</body>
</html>
"""


def write_html(*, serve_mode: bool | None = None) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    html_text = render_html(load_queue(), serve_mode=serve_mode)
    HTML_PATH.write_text(html_text, encoding="utf-8")
    print(f"# wrote {HTML_PATH}")
    return HTML_PATH


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _redirect(self, loc: str = "/") -> None:
        self.send_response(302)
        self.send_header("Location", loc)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            qs = parse_qs(parsed.query)
            iid = (qs.get("id") or [""])[0]
            status = (qs.get("status") or [""])[0]
            if iid and status in ("skipped", "snoozed", "pending", "sent"):
                set_status(iid, status)
                write_html(serve_mode=True)
            self._redirect("/")
            return
        if parsed.path == "/api/engine":
            qs = parse_qs(parsed.query)
            engine = (qs.get("engine") or [""])[0]
            if set_engine(engine):
                write_html(serve_mode=True)
                print(f"# engine -> {engine}")
            self._redirect("/")
            return
        if parsed.path in ("/", "/index.html", "/dashboard.html"):
            write_html(serve_mode=True)
            data = HTML_PATH.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_error(404)


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    global _SERVE_MODE
    _SERVE_MODE = True
    write_html(serve_mode=True)
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"# serving http://{host}:{port}/  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n# stopped")
    finally:
        _SERVE_MODE = False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()

    if args.serve:
        serve(port=args.port)
        return 0

    path = write_html(serve_mode=False)
    if args.open or not args.write:
        subprocess.run(["open", str(path)], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
