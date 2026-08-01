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
from urllib.parse import parse_qs, quote, urlparse
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_DIR = REPO / ".jarvis_state" / "night_triage"
JARVIS_STATE = REPO / ".jarvis_state"
QUEUE_PATH = STATE_DIR / "queue.json"
CONFIG_PATH = STATE_DIR / "config.json"
HTML_PATH = STATE_DIR / "dashboard.html"
WATCH_OUT = JARVIS_STATE / "situation_watch.json"
WATCH_POPUP_DISMISS = JARVIS_STATE / "situation_watch_popup_dismiss.json"
WATCH_SCRIPT = REPO / "scripts" / "jarvis_situation_watch.py"
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"
TRIAGE = REPO / "scripts" / "jarvis_night_triage.py"

# --serve で生成した HTML だけ操作リンクを有効にする
_SERVE_MODE = False

MAIL_LANES = ("partner", "openchat", "general")
ALL_LANES = ("partner", "openchat", "general", "situation")
SIDEBAR_PLACEHOLDERS = (
    ("kamiooya", "神大家運営", "Phase 2"),
    ("properties", "3棟・物件", "Phase 2"),
    ("kodate", "戸建て", "Phase 2"),
    ("ai_raimo", "AI・Raimo", "Phase 2"),
    ("metrics", "数値", "Phase 2"),
)


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


def refresh_situation_watch() -> dict:
    """集約スクリプトを実行して最新 JSON を返す。失敗時は既存ファイルまたは空。"""
    py = str(PY) if PY.is_file() else sys.executable
    try:
        subprocess.run(
            [py, str(WATCH_SCRIPT)],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception as e:
        print(f"# situation watch refresh failed: {e}")
    if WATCH_OUT.is_file():
        try:
            return json.loads(WATCH_OUT.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"items": [], "counts": {}, "popup_item_ids": [], "updated_at": None}


def load_situation_watch(*, refresh: bool = False) -> dict:
    if refresh or not WATCH_OUT.is_file():
        return refresh_situation_watch()
    try:
        return json.loads(WATCH_OUT.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return refresh_situation_watch()


def archive_watch_item(item_id: str, *, unarchive: bool = False) -> bool:
    py = str(PY) if PY.is_file() else sys.executable
    flag = "--unarchive" if unarchive else "--archive"
    try:
        r = subprocess.run(
            [py, str(WATCH_SCRIPT), flag, item_id],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=60,
        )
        return r.returncode == 0
    except Exception as e:
        print(f"# watch archive failed: {e}")
        return False


def popup_dismissed_today() -> bool:
    if not WATCH_POPUP_DISMISS.is_file():
        return False
    try:
        data = json.loads(WATCH_POPUP_DISMISS.read_text(encoding="utf-8"))
        return data.get("date") == datetime.now(JST).strftime("%Y-%m-%d")
    except (json.JSONDecodeError, OSError):
        return False


def dismiss_popup_today() -> None:
    JARVIS_STATE.mkdir(parents=True, exist_ok=True)
    WATCH_POPUP_DISMISS.write_text(
        json.dumps(
            {"date": datetime.now(JST).strftime("%Y-%m-%d"), "at": datetime.now(JST).isoformat()},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def set_engine(engine: str) -> bool:
    if engine not in ("gemini", "cursor"):
        return False
    cfg = load_config()
    cfg["engine"] = engine
    save_config(cfg)
    return True


def _applescript_string(s: str) -> str:
    """AppleScript 用に二重引用符で囲む（内部の \" は \"\"）。"""
    return '"' + s.replace('"', '""') + '"'


def launch_agent_login_in_terminal() -> tuple[bool, str]:
    """未ログイン時に Terminal.app で agent login を起動。戻り値: (ok, message)"""
    exe = find_cursor_agent()
    if not exe:
        return False, "Cursor Agent CLI が見つかりません（~/.local/bin/agent）"
    # 複雑なシェルは AppleScript に埋め込まず、一時スクリプト経由（引用符エラー防止）
    # ログイン完了後は当該ウィンドウを自動クローズ（read 待ちで残さない）
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    sh_path = STATE_DIR / "_agent_login.sh"
    sh_body = f"""#!/bin/bash
export PATH="$HOME/.local/bin:$PATH"
cd "$HOME/git-repos" || true
echo "Cursor Agent ログインを開始します…"
"{exe}" login
status=$?
# このセッションの Terminal ウィンドウだけ閉じる
tty_name="$(basename "$(tty 2>/dev/null)" 2>/dev/null || true)"
if [[ -n "$tty_name" ]]; then
  osascript >/dev/null 2>&1 <<EOF || true
tell application "Terminal"
  repeat with w in windows
    repeat with t in tabs of w
      try
        if tty of t contains "$tty_name" then
          close w
          return
        end if
      end try
    end repeat
  end repeat
end tell
EOF
fi
exit "$status"
"""
    sh_path.write_text(sh_body, encoding="utf-8")
    sh_path.chmod(0o755)
    as_path = _applescript_string(str(sh_path))
    script = (
        'tell application "Terminal"\n'
        "  activate\n"
        f"  do script {as_path}\n"
        "end tell"
    )
    try:
        r = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            return False, f"Terminal 起動に失敗: {err[:200] or r.returncode}"
        return True, "ログイン画面を起動しました。ブラウザで完了してください"
    except Exception as e:
        return False, f"Terminal 起動に失敗: {e}"


def maybe_start_cursor_login() -> str | None:
    """cursor 未ログインなら login を起動し、ユーザー向けメッセージを返す。"""
    ok, msg = cursor_login_status()
    if ok:
        return None
    launched, launch_msg = launch_agent_login_in_terminal()
    if launched:
        return launch_msg
    return f"{msg}。自動起動失敗: {launch_msg}。手動で agent login を実行してください。"


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


def _load_night_triage():
    import importlib.util

    spec = importlib.util.spec_from_file_location("jarvis_night_triage", TRIAGE)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def lookup_partner_original_body(it: dict) -> str:
    """pending partner で original_body が空のとき、5.やり取り.md からベストエフォート再取得。"""
    folder = str(it.get("folder") or "").strip()
    received = str(it.get("received_at") or "").strip()
    subject = str(it.get("subject") or "").strip()
    if not folder or not received:
        return ""
    try:
        mod = _load_night_triage()
        if mod is None:
            return ""
        base = mod.partner_base()
        md = base / folder / "5.やり取り.md"
        if not md.is_file():
            return ""
        entries = mod.parse_yoritoori(md, folder, str(it.get("partner") or ""))
        # 日時一致を優先、なければ件名一致
        for e in entries:
            if e.get("received_at") == received:
                if not subject or e.get("subject") == subject:
                    return str(e.get("body") or "")[:8000]
        subj_norm = mod.normalize_subject(subject) if subject else ""
        for e in entries:
            if subj_norm and e.get("subject_norm") == subj_norm:
                if e.get("received_at") == received or not received:
                    return str(e.get("body") or "")[:8000]
        for e in entries:
            if e.get("received_at") == received:
                return str(e.get("body") or "")[:8000]
    except Exception as e:
        print(f"# original_body lookup failed folder={folder}: {e}")
    return ""


def resolve_original_body(it: dict) -> str:
    body = str(it.get("original_body") or "").strip()
    if body:
        return body
    if (it.get("lane") or "partner") != "partner":
        return ""
    return lookup_partner_original_body(it)


def backfill_original_bodies(q: dict) -> int:
    """queue 内の partner で original_body 空のものを埋め、変更数を返す。"""
    n = 0
    for it in q.get("items") or []:
        if it.get("kind") == "activity":
            continue
        if (it.get("lane") or "partner") != "partner":
            continue
        if str(it.get("original_body") or "").strip():
            continue
        body = lookup_partner_original_body(it)
        if body:
            it["original_body"] = body
            n += 1
    if n:
        save_queue(q)
    return n

def render_html(
    q: dict,
    *,
    serve_mode: bool | None = None,
    lane: str = "partner",
    flash_notice: str | None = None,
    watch: dict | None = None,
) -> str:
    serve = _SERVE_MODE if serve_mode is None else serve_mode
    if lane not in ALL_LANES:
        lane = "partner"
    watch = watch if watch is not None else load_situation_watch(refresh=False)
    watch_items = list(watch.get("items") or [])
    watch_counts = watch.get("counts") or {}
    watch_popup_n = int(watch_counts.get("popup") or 0)
    watch_attn = int(watch_counts.get("attention") or 0) + int(watch_counts.get("warn") or 0)

    items_all = list(q.get("items") or [])
    for it in items_all:
        if not it.get("lane"):
            it["lane"] = "partner"
        if not it.get("kind"):
            it["kind"] = (
                "mail"
                if it.get("status") in ("pending", "sent", "skipped", "snoozed")
                else (it.get("kind") or "mail")
            )

    def _is_mail_pending(i: dict) -> bool:
        return i.get("status") == "pending" and i.get("kind") != "activity"

    def _is_activity(i: dict, lane_name: str) -> bool:
        return i.get("kind") == "activity" and (i.get("lane") or "") == lane_name

    pending_partner = sum(
        1 for i in items_all if _is_mail_pending(i) and (i.get("lane") or "partner") == "partner"
    )
    pending_general = sum(1 for i in items_all if _is_mail_pending(i) and i.get("lane") == "general")
    openchat_n = sum(1 for i in items_all if _is_activity(i, "openchat"))
    partner_act_n = sum(1 for i in items_all if _is_activity(i, "partner"))
    mail_pending_total = pending_partner + pending_general

    if serve and lane in MAIL_LANES:
        items = [i for i in items_all if (i.get("lane") or "partner") == lane]
    elif lane in MAIL_LANES:
        items = items_all
    else:
        items = []

    pending = [
        i
        for i in items
        if _is_mail_pending(i) and (not serve or (i.get("lane") or "partner") == lane)
    ]
    pending.sort(key=lambda x: x.get("received_at") or "")

    if lane == "partner":
        activities = [i for i in items_all if _is_activity(i, "partner")]
    elif lane == "openchat":
        activities = [i for i in items_all if _is_activity(i, "openchat")]
    else:
        activities = []
    activities.sort(key=lambda x: x.get("received_at") or "", reverse=True)

    others = [
        i
        for i in items
        if i.get("status") in ("sent", "skipped", "snoozed") and i.get("kind") != "activity"
    ]
    if serve:
        others = [i for i in others if (i.get("lane") or "partner") == lane]
    others.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    updated = html.escape(str(q.get("updated_at") or "—"))
    engine = prefer_engine(q)
    gemini_checked = "checked" if engine == "gemini" else ""
    cursor_checked = "checked" if engine == "cursor" else ""

    cursor_ok, cursor_msg = cursor_login_status() if serve else (True, "")
    warn_block = ""
    if flash_notice:
        warn_block = f"""
        <div class="warn">
          {html.escape(flash_notice)}
        </div>
        """
    elif serve and engine == "cursor" and not cursor_ok and lane in MAIL_LANES:
        warn_block = f"""
        <div class="warn">
          注意: {html.escape(cursor_msg)}。未ログインのままだと夜間バッチの下書き生成が失敗します。
          Cursor Agent を選び直すと Terminal でログイン画面を起動します。
        </div>
        """

    def side_link(
        href_lane: str,
        label: str,
        badge: int | str | None = None,
        *,
        active: bool = False,
        disabled: bool = False,
        note: str = "",
    ) -> str:
        cls = "side-link"
        if active:
            cls += " active"
        if disabled:
            cls += " disabled"
        b = f'<span class="badge">{badge}</span>' if badge not in (None, "", 0) else ""
        n = f'<span class="side-note">{html.escape(note)}</span>' if note else ""
        if disabled:
            return f'<div class="{cls}"><span>{html.escape(label)}</span>{b}{n}</div>'
        if serve:
            return (
                f'<a class="{cls}" href="/?lane={href_lane}">'
                f"<span>{html.escape(label)}</span>{b}{n}</a>"
            )
        return (
            f'<a class="{cls}" href="#" onclick="showLane({json.dumps(href_lane)});return false;">'
            f"<span>{html.escape(label)}</span>{b}{n}</a>"
        )

    sidebar_links = [
        side_link("partner", "メール · パートナー", pending_partner, active=lane == "partner"),
        side_link("openchat", "メール · オプチャ", openchat_n, active=lane == "openchat"),
        side_link("general", "メール · それ以外", pending_general, active=lane == "general"),
        side_link("situation", "状況ウォッチ", watch_attn or None, active=lane == "situation"),
    ]
    for _pid, plabel, pnote in SIDEBAR_PLACEHOLDERS:
        sidebar_links.append(side_link(_pid, plabel, None, disabled=True, note=pnote))
    sidebar_html = "\n".join(sidebar_links)

    tab_partner_cls = "tab active" if lane == "partner" else "tab"
    tab_openchat_cls = "tab active" if lane == "openchat" else "tab"
    tab_general_cls = "tab active" if lane == "general" else "tab"
    tab_situation_cls = "tab active" if lane == "situation" else "tab"
    if serve:
        tabs = f"""
        <nav class="tabs">
          <a class="{tab_partner_cls}" href="/?lane=partner">パートナー <span class="badge">{pending_partner}</span></a>
          <a class="{tab_openchat_cls}" href="/?lane=openchat">神大家オプチャ <span class="badge">{openchat_n}</span></a>
          <a class="{tab_general_cls}" href="/?lane=general">それ以外 <span class="badge">{pending_general}</span></a>
          <a class="{tab_situation_cls}" href="/?lane=situation">状況 <span class="badge">{watch_attn}</span></a>
        </nav>
        """
        engine_panel = ""
        if lane in MAIL_LANES:
            engine_panel = f"""
        <div class="engine-panel">
          <span class="engine-label">下書きエンジン（次回バッチから反映・メールのみ）</span>
          <label class="engine-opt"><input type="radio" name="engine" value="gemini" {gemini_checked}
            onchange="location.href='/api/engine?engine=gemini&lane={lane}'"/> Gemini（無料枠）</label>
          <label class="engine-opt"><input type="radio" name="engine" value="cursor" {cursor_checked}
            onchange="location.href='/api/engine?engine=cursor&lane={lane}'"/> Cursor Agent</label>
          <span class="engine-hint">現在: <strong>{html.escape(engine)}</strong></span>
        </div>
        {warn_block}
        """
        elif warn_block:
            engine_panel = warn_block
        howto = """
        <ol class="howto">
          <li>パートナー: メール要返信（下書き）＋ Chatwork/LINE/メッセージの更新概要</li>
          <li>神大家オプチャ: 直近更新の概要のみ（返信提案・スキップなし）</li>
          <li>状況: 気にしている項目の判定。不要ならアーカイブ、「Cursorで調べる」で調査プロンプトをコピー</li>
          <li>メールを送る件は「送信指示をコピー」→ Cursor に貼る（自動送信なし）</li>
        </ol>
        """
    else:
        tabs = f"""
        <nav class="tabs">
          <a class="{tab_partner_cls}" href="#" onclick="showLane('partner');return false;">パートナー <span class="badge">{pending_partner}</span></a>
          <a class="{tab_openchat_cls}" href="#" onclick="showLane('openchat');return false;">神大家オプチャ <span class="badge">{openchat_n}</span></a>
          <a class="{tab_general_cls}" href="#" onclick="showLane('general');return false;">それ以外 <span class="badge">{pending_general}</span></a>
          <a class="{tab_situation_cls}" href="#" onclick="showLane('situation');return false;">状況 <span class="badge">{watch_attn}</span></a>
        </nav>
        <p class="sub">静的表示。操作は <a href="http://127.0.0.1:8765/">http://127.0.0.1:8765/</a>（常時起動）で。</p>
        """
        engine_panel = f"""
        <div class="engine-panel static">
          <span class="engine-label">既定エンジン: <strong>{html.escape(engine)}</strong></span>
        </div>
        """
        howto = ""

    def card(it: dict, show_ab: bool) -> str:
        kind = it.get("kind") or "mail"
        if kind == "activity":
            return activity_card(it)
        seq = it.get("seq") or "—"
        st = it.get("status") or ""
        pri = it.get("priority") or ""
        partner = html.escape(str(it.get("partner") or ""))
        folder = html.escape(str(it.get("folder") or it.get("from_email") or ""))
        subject = html.escape(str(it.get("subject") or ""))
        received = html.escape(str(it.get("received_at") or ""))
        summary = html.escape(str(it.get("summary") or ""))
        reason = html.escape(str(it.get("reason") or ""))
        draft = html.escape(str(it.get("draft_text") or ""))
        original = resolve_original_body(it)
        original_esc = html.escape(original) if original else ""
        item_lane_raw = str(it.get("lane") or "partner")
        if not original_esc:
            if item_lane_raw == "general":
                original_esc = "（原文未保存。次回夜間バッチ以降で保存されます）"
            else:
                original_esc = "（原文を取得できませんでした）"
        dg = html.escape(str(it.get("draft_gemini") or ""))
        dc = html.escape(str(it.get("draft_cursor") or ""))
        iid = html.escape(str(it.get("id") or ""))
        item_lane = html.escape(item_lane_raw)
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
              <a class="btn" href="/api/status?id={iid}&status=snoozed&lane={lane}">後で</a>
              <a class="btn" href="/api/status?id={iid}&status=skipped&lane={lane}">スキップ</a>
            </div>
            """
        elif st == "pending" and not serve:
            actions = f"""
            <div class="actions">
              <button type="button" onclick="copyCmd({json.dumps(f'夜間下書き #{seq} を送って')})">送信指示をコピー</button>
            </div>
            """
        show = "" if serve or item_lane_raw == "partner" else "display:none"
        return f"""
        <article class="card lane-{item_lane} pri-{html.escape(pri)} status-{html.escape(st)}" data-lane="{item_lane}" style="{show}">
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
            <h4>受信原文</h4>
            <pre class="original">{original_esc}</pre>
            <h4>返信下書き</h4>
            <pre>{draft or '（未生成）'}</pre>
            {ab}
          </details>
          {actions}
        </article>
        """

    def activity_card(it: dict) -> str:
        partner = html.escape(str(it.get("partner") or ""))
        folder = html.escape(str(it.get("folder") or ""))
        channel = html.escape(str(it.get("channel") or "更新"))
        received = html.escape(str(it.get("received_at") or ""))
        summary = html.escape(str(it.get("summary") or ""))
        subject = html.escape(str(it.get("subject") or ""))
        item_lane = html.escape(str(it.get("lane") or "partner"))
        body = html.escape(str(it.get("original_body") or it.get("body") or "")[:1500])
        show_style = "" if serve or item_lane == "partner" else "display:none"
        details = ""
        if body.strip():
            details = f"""
            <details>
              <summary>本文メモ</summary>
              <pre class="original">{body}</pre>
            </details>
            """
        return f"""
        <article class="card activity lane-{item_lane}" data-lane="{item_lane}" style="{show_style}">
          <header>
            <span class="ch">{channel}</span>
            <strong>{partner}</strong>
            <span class="meta">{folder} · {received}</span>
          </header>
          <p class="sum">{summary or subject}</p>
          {details}
        </article>
        """

    def watch_card(it: dict, *, archived_section: bool = False) -> str:
        iid = str(it.get("id") or "")
        level = str(it.get("level") or "info")
        title = html.escape(str(it.get("title") or ""))
        summary = html.escape(str(it.get("summary") or ""))
        detail = html.escape(str(it.get("detail") or ""))
        src = html.escape(str(it.get("source") or ""))
        prompt = str(it.get("cursor_prompt") or "").strip()
        prompt_js = json.dumps(prompt)
        if serve:
            if archived_section:
                actions = f"""
            <div class="actions">
              <button type="button" onclick='copyCmd({prompt_js})'>Cursorで調べる</button>
              <a class="btn" href="/api/watch?id={html.escape(iid)}&action=unarchive&lane=situation">再表示</a>
            </div>
            """
            else:
                actions = f"""
            <div class="actions">
              <button type="button" onclick='copyCmd({prompt_js})'>Cursorで調べる</button>
              <a class="btn" href="/api/watch?id={html.escape(iid)}&action=archive&lane=situation">アーカイブ</a>
            </div>
            """
        else:
            actions = f"""
            <div class="actions">
              <button type="button" onclick='copyCmd({prompt_js})'>Cursorで調べる</button>
            </div>
            """
        return f"""
        <article class="card watch level-{html.escape(level)}" data-lane="situation">
          <header>
            <span class="lvl">{html.escape(level)}</span>
            <strong>{title}</strong>
            <span class="meta">{src}</span>
          </header>
          <p class="sum">{summary}</p>
          {f'<p class="reason">{detail}</p>' if detail else ''}
          {actions}
        </article>
        """

    cards_p = "\n".join(card(i, True) for i in pending) or (
        "<p>メールの要返信なし</p>"
        if lane == "partner"
        else ("<p>pending なし</p>" if lane == "general" else "")
    )
    cards_act = "\n".join(activity_card(i) for i in activities) or "<p>直近の更新なし</p>"
    cards_o = "\n".join(card(i, False) for i in others[:40])

    if lane == "partner":
        lane_label = "パートナー"
        main_sections = f"""
  <div class="stats">
    <div class="stat">メール要返信 <strong>{len(pending)}</strong></div>
    <div class="stat">他チャネル更新 <strong>{partner_act_n}</strong></div>
    <div class="stat">状況要注意 <strong>{watch_attn}</strong></div>
  </div>
  <h2>メール要返信（古い順）</h2>
  {cards_p}
  <h2>他チャネルの更新（Chatwork / LINE / メッセージ）</h2>
  <p class="sec-note">概要のみ（スキップ・下書きなし）。取込はパートナー確認側の MD が正本。</p>
  {cards_act}
  <h2>処理済み・スキップ（直近）</h2>
  {cards_o}
"""
    elif lane == "openchat":
        lane_label = "神大家オプチャ"
        main_sections = f"""
  <div class="stats">
    <div class="stat">直近更新 <strong>{openchat_n}</strong></div>
  </div>
  <h2>直近の更新概要</h2>
  <p class="sec-note">情報収集枠。返信提案・スキップ操作はありません。</p>
  {cards_act}
"""
    elif lane == "situation":
        lane_label = "状況ウォッチ"
        active_w = [i for i in watch_items if i.get("status") != "archived"]
        arch_w = [i for i in watch_items if i.get("status") == "archived"]
        order = {"attention": 0, "warn": 1, "info": 2, "ok": 3}
        active_w.sort(key=lambda x: (order.get(str(x.get("level")), 9), str(x.get("title") or "")))
        cards_w = "\n".join(watch_card(i) for i in active_w) or "<p>ウォッチ項目なし</p>"
        cards_wa = "\n".join(watch_card(i, archived_section=True) for i in arch_w) or "<p>アーカイブなし</p>"
        wupd = html.escape(str(watch.get("updated_at") or "—"))
        refresh_btn = (
            "<a class='btn' href='/api/watch?action=refresh&lane=situation'>再集約</a>" if serve else ""
        )
        main_sections = f"""
  <div class="stats">
    <div class="stat">要注意 <strong>{watch_attn}</strong></div>
    <div class="stat">OK <strong>{int(watch_counts.get('ok') or 0)}</strong></div>
    <div class="stat">アーカイブ <strong>{int(watch_counts.get('archived') or 0)}</strong></div>
    <div class="stat">集約 {wupd}</div>
  </div>
  <p class="sec-note">既存 state から判定。不要な項目はアーカイブ。「Cursorで調べる」で調査プロンプトをコピー。</p>
  <div class="actions" style="margin-bottom:12px">{refresh_btn}</div>
  <h2>アクティブ</h2>
  {cards_w}
  <h2>アーカイブ</h2>
  {cards_wa}
"""
    else:
        lane_label = "それ以外（admin Gmail）"
        main_sections = f"""
  <div class="stats">
    <div class="stat">このタブ pending <strong>{len(pending)}</strong></div>
    <div class="stat">パートナー {pending_partner} / オプチャ {openchat_n} / それ以外 {pending_general}</div>
  </div>
  <h2>要対応（古い順）</h2>
  {cards_p}
  <h2>処理済み・スキップ（直近）</h2>
  {cards_o}
"""

    popup_html = ""
    popup_items = [
        i
        for i in watch_items
        if i.get("status") != "archived" and i.get("id") in (watch.get("popup_item_ids") or [])
    ]
    show_popup = bool(
        serve and lane != "situation" and watch_popup_n > 0 and not popup_dismissed_today() and popup_items
    )
    if show_popup:
        rows = []
        for i in popup_items[:8]:
            rows.append(
                f"<li><strong>{html.escape(str(i.get('title') or ''))}</strong>"
                f' <span class="lvl mini">{html.escape(str(i.get("level") or ""))}</span>'
                f'<br/><span class="muted">{html.escape(str(i.get("summary") or ""))}</span></li>'
            )
        popup_html = f"""
<div class="modal-backdrop" id="watchModal">
  <div class="modal" role="dialog" aria-labelledby="watchModalTitle">
    <h2 id="watchModalTitle">気にしている状況</h2>
    <p class="sec-note">要注意 {watch_popup_n} 件（今日1回表示）</p>
    <ul class="popup-list">
      {''.join(rows)}
    </ul>
    <div class="actions">
      <a class="btn primary" href="/?lane=situation">状況タブを開く</a>
      <a class="btn" href="/api/watch?action=dismiss_popup&lane={lane}">今日は閉じる</a>
    </div>
  </div>
</div>
"""

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Jarvis ダッシュボード</title>
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
  .layout {{ display: flex; min-height: 100vh; align-items: stretch; }}
  .sidebar {{
    width: 220px; flex-shrink: 0; background: #1c1917; color: #fafaf9;
    padding: 20px 12px; position: sticky; top: 0; height: 100vh; overflow-y: auto;
  }}
  .side-brand {{ font-size: 0.95rem; font-weight: 700; letter-spacing: 0.04em; margin: 0 8px 16px; }}
  .side-link {{
    display: flex; flex-wrap: wrap; gap: 6px; align-items: baseline;
    color: #e7e5e4; text-decoration: none; padding: 8px 10px; border-radius: 8px;
    font-size: 0.88rem; margin-bottom: 4px;
  }}
  .side-link:hover {{ background: #292524; }}
  .side-link.active {{ background: #0f766e; color: #ecfdf5; }}
  .side-link.disabled {{ opacity: 0.45; cursor: default; }}
  .side-note {{ font-size: 0.7rem; color: #a8a29e; width: 100%; }}
  .side-link .badge {{ background: #134e4a; color: #99f6e4; }}
  .side-link.active .badge {{ background: #ecfdf5; color: #0f766e; }}
  main {{ flex: 1; max-width: 960px; margin: 0 auto; padding: 28px 18px 80px; width: 100%; }}
  @media (max-width: 800px) {{
    .layout {{ flex-direction: column; }}
    .sidebar {{ width: 100%; height: auto; position: relative; display: flex; flex-wrap: wrap; gap: 4px; }}
    .side-brand {{ width: 100%; }}
  }}
  h1 {{ font-size: 1.45rem; margin: 0 0 4px; letter-spacing: 0.02em; }}
  .sub {{ color: var(--muted); font-size: 0.9rem; margin-bottom: 12px; }}
  .howto {{ margin: 0 0 16px; padding-left: 1.2rem; font-size: 0.9rem; color: var(--muted); }}
  .tabs {{ display: flex; gap: 8px; margin: 12px 0 16px; flex-wrap: wrap; }}
  .tab {{
    text-decoration: none; color: var(--ink); background: var(--card);
    border: 1px solid var(--line); padding: 8px 14px; border-radius: 999px; font-size: 0.9rem;
  }}
  .tab.active {{ border-color: var(--accent); color: var(--accent); font-weight: 600; }}
  .badge {{
    display: inline-block; min-width: 1.2em; text-align: center;
    background: #ecfdf5; color: var(--accent); border-radius: 6px; padding: 0 5px; font-size: 0.8rem;
  }}
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
  .ch {{
    font-size: 0.75rem; font-weight: 600; padding: 1px 8px; border-radius: 999px;
    background: #ecfeff; color: #0e7490;
  }}
  .lvl {{
    font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
    padding: 2px 8px; border-radius: 999px; background: #f5f5f4; color: var(--low);
  }}
  .lvl.mini {{ font-size: 0.65rem; }}
  .level-attention .lvl {{ background: #fee2e2; color: var(--high); }}
  .level-warn .lvl {{ background: #ffedd5; color: var(--med); }}
  .level-ok .lvl {{ background: #d1fae5; color: #065f46; }}
  .level-info .lvl {{ background: #e0e7ff; color: #3730a3; }}
  .card.watch {{ border-left: 3px solid var(--line); }}
  .level-attention.card.watch {{ border-left-color: var(--high); }}
  .level-warn.card.watch {{ border-left-color: var(--med); }}
  .card.activity {{ border-style: dashed; }}
  .sec-note {{ color: var(--muted); font-size: 0.85rem; margin: -4px 0 10px; }}
  .muted {{ color: var(--muted); font-size: 0.88rem; }}
  h3 {{ font-size: 1.05rem; margin: 8px 0 6px; font-weight: 600; }}
  .sum {{ margin: 0 0 6px; }}
  .reason {{ color: var(--muted); font-size: 0.9rem; margin: 0 0 8px; }}
  pre {{
    white-space: pre-wrap; background: #fafaf9; border: 1px solid var(--line);
    padding: 12px; border-radius: 8px; font-size: 0.88rem; overflow-x: auto;
  }}
  details h4 {{ font-size: 0.9rem; margin: 12px 0 6px; color: var(--muted); font-weight: 600; }}
  details h4:first-of-type {{ margin-top: 8px; }}
  pre.original {{ max-height: 28rem; overflow-y: auto; }}
  .ab {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }}
  @media (max-width: 800px) {{ .ab {{ grid-template-columns: 1fr; }} }}
  .actions {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; align-items: center; }}
  button, .btn {{
    appearance: none; border: 1px solid var(--line); background: #fff; color: var(--ink);
    padding: 6px 12px; border-radius: 8px; cursor: pointer; text-decoration: none; font-size: 0.88rem;
  }}
  button:hover, .btn:hover {{ border-color: var(--accent); color: var(--accent); }}
  .btn.primary {{ background: var(--accent); color: #ecfdf5; border-color: var(--accent); }}
  .btn.primary:hover {{ filter: brightness(1.05); color: #fff; }}
  h2 {{ font-size: 1.1rem; margin: 28px 0 8px; }}
  .toast {{
    position: fixed; bottom: 18px; right: 18px; background: #134e4a; color: #ecfdf5;
    padding: 10px 14px; border-radius: 8px; display: none; max-width: 90vw; z-index: 40;
  }}
  .modal-backdrop {{
    position: fixed; inset: 0; background: #00000066; display: flex; align-items: center;
    justify-content: center; z-index: 30; padding: 16px;
  }}
  .modal {{
    background: var(--card); border-radius: 14px; padding: 20px 22px; max-width: 520px; width: 100%;
    box-shadow: 0 20px 50px #00000033; max-height: 85vh; overflow-y: auto;
  }}
  .modal h2 {{ margin-top: 0; }}
  .popup-list {{ margin: 0 0 12px; padding-left: 1.1rem; }}
  .popup-list li {{ margin-bottom: 10px; }}
</style>
</head>
<body>
<div class="layout">
<aside class="sidebar">
  <div class="side-brand">Jarvis</div>
  {sidebar_html}
  <div class="side-note" style="margin:12px 10px 0;opacity:0.7">メール起点 · 状況ほかはサイドから</div>
</aside>
<main>
  <h1>Jarvis ダッシュボード</h1>
  <p class="sub">更新: {updated} · 表示中: {lane_label} · メールpending {mail_pending_total} · 送信は Cursor 経由（自動送信なし）</p>
  {tabs}
  {engine_panel}
  {howto}
  {main_sections}
</main>
</div>
{popup_html}
<div class="toast" id="toast"></div>
<script>
function copyCmd(t) {{
  navigator.clipboard.writeText(t).then(() => {{
    const el = document.getElementById('toast');
    el.textContent = 'コピーしました';
    el.style.display = 'block';
    setTimeout(() => el.style.display = 'none', 2200);
  }});
}}
function showLane(lane) {{
  document.querySelectorAll('.card').forEach(el => {{
    el.style.display = (el.dataset.lane === lane) ? '' : 'none';
  }});
  const order = ['partner', 'openchat', 'general', 'situation'];
  document.querySelectorAll('.tab').forEach((el, i) => {{
    el.classList.toggle('active', order[i] === lane);
  }});
}}
</script>
</body>
</html>
"""


def write_html(
    *,
    serve_mode: bool | None = None,
    lane: str = "partner",
    flash_notice: str | None = None,
    refresh_watch: bool = False,
) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    q = load_queue()
    n = backfill_original_bodies(q)
    if n:
        print(f"# backfilled original_body for {n} partner item(s)")
    watch = load_situation_watch(refresh=refresh_watch)
    html_text = render_html(
        q, serve_mode=serve_mode, lane=lane, flash_notice=flash_notice, watch=watch
    )
    HTML_PATH.write_text(html_text, encoding="utf-8")
    print(f"# wrote {HTML_PATH} lane={lane}")
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
        qs = parse_qs(parsed.query)
        lane = (qs.get("lane") or ["partner"])[0]
        if lane not in ALL_LANES:
            lane = "partner"
        if parsed.path == "/api/status":
            iid = (qs.get("id") or [""])[0]
            status = (qs.get("status") or [""])[0]
            if iid and status in ("skipped", "snoozed", "pending", "sent"):
                set_status(iid, status)
                write_html(serve_mode=True, lane=lane)
            self._redirect(f"/?lane={lane}")
            return
        if parsed.path == "/api/engine":
            engine = (qs.get("engine") or [""])[0]
            flash = None
            if set_engine(engine):
                if engine == "cursor":
                    flash = maybe_start_cursor_login()
                    if flash:
                        print(f"# cursor login: {flash}")
                print(f"# engine -> {engine}")
            if flash:
                self._redirect(f"/?lane={lane}&notice={quote(flash)}")
            else:
                self._redirect(f"/?lane={lane}")
            return
        if parsed.path == "/api/watch":
            action = (qs.get("action") or [""])[0]
            iid = (qs.get("id") or [""])[0]
            if action == "dismiss_popup":
                dismiss_popup_today()
                self._redirect(f"/?lane={lane}")
                return
            if action == "archive" and iid:
                archive_watch_item(iid, unarchive=False)
                write_html(serve_mode=True, lane="situation", refresh_watch=True)
                self._redirect("/?lane=situation")
                return
            if action == "unarchive" and iid:
                archive_watch_item(iid, unarchive=True)
                write_html(serve_mode=True, lane="situation", refresh_watch=True)
                self._redirect("/?lane=situation")
                return
            if action == "refresh":
                write_html(serve_mode=True, lane="situation", refresh_watch=True)
                self._redirect("/?lane=situation")
                return
            self._redirect(f"/?lane={lane}")
            return
        if parsed.path in ("/", "/index.html", "/dashboard.html"):
            notice = (qs.get("notice") or [None])[0]
            write_html(serve_mode=True, lane=lane, flash_notice=notice)
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
    write_html(serve_mode=True, refresh_watch=True)
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
    ap.add_argument("--lane", default="partner", choices=list(ALL_LANES))
    args = ap.parse_args()

    if args.serve:
        serve(port=args.port)
        return 0

    path = write_html(serve_mode=False, lane=args.lane, refresh_watch=True)
    if args.open or not args.write:
        subprocess.run(["open", str(path)], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
