#!/usr/bin/env python3
"""
Jarvis: 夜間メールトリアージ（パートナー + admin Gmail 全般）

1. gmail_to_yoritoori.py で取込（パートナー）
2. 5.やり取り.md / admin INBOX から未返信候補を抽出
3. Gemini / Cursor Agent で要返信判定・下書き生成（メールのみ）
4. Chatwork／LINE／iMessage・815神大家オプチャの直近更新概要を queue に載せる
5. .jarvis_state/night_triage/queue.json を更新（lane=partner|general|openchat）

使い方:
  python scripts/jarvis_night_triage.py --dry-run
  python scripts/jarvis_night_triage.py --skip-fetch --lane all
  python scripts/jarvis_night_triage.py --lane general --skip-fetch --limit 5
  python scripts/jarvis_night_triage.py --apply-draft 12
  python scripts/jarvis_night_triage.py --send-gmail 12   # general のみ・承認後
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_DIR = REPO / ".jarvis_state" / "night_triage"
QUEUE_PATH = STATE_DIR / "queue.json"
CONFIG_PATH = STATE_DIR / "config.json"
LOG_DIR = Path.home() / "Library" / "Logs" / "jarvis_night_triage"
MANUAL_DIR = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"

ONEDRIVE_PARTNER = (
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    / "C2_ルーティン作業/26_パートナー社への相談"
)

HEADING_RE = re.compile(
    r"^###\s+(\d{4}/\d{2}/\d{2}(?:\s+\d{2}:\d{2})?)\s*｜\s*([^｜]+)\s*｜\s*([^｜]+)\s*｜\s*(.*)$"
)
SUBJECT_RE = re.compile(r"^\*\*件名\*\*\s*[:：]\s*(.+)$", re.MULTILINE)
RE_PREFIX_RE = re.compile(r"^((re|fw|fwd|返信|転送)\s*[:：]\s*)+", re.I)

# 自動スキップ（要返信判定を呼ばない）
NOISE_SUBJECT_RE = re.compile(
    r"(password|パスワード|MailGates|mgc-filelink|配信漏れ|"
    r"アーカイブ動画|プレゼントのご案内|\[toall\])",
    re.I,
)
NOISE_BODY_RE = re.compile(
    r"(添付リンクのパスワード|以下のURLをクリックすることにより|"
    r"This is password notification|添付ファイルダウンロードページへ遷移)",
    re.I,
)

SKIP_FOLDERS = {
    "000_共通",
    "815_神大家オプチャ",
    "809_神大家運営回答",  # 一斉配信中心・返信義務なし
}

OPENCHAT_ROOT_NAME = "815_神大家オプチャ"
PLACEHOLDER_BODY_RE = re.compile(r"(\[本文なし|E2EE|復号でき|プレースホルダ)", re.I)
ACTIVITY_LOOKBACK_DEFAULT = 7
ACTIVITY_PER_PARTNER = 3
ACTIVITY_PARTNER_MAX = 30
ACTIVITY_OPENCHAT_MAX = 40

DEFAULT_GEMINI_MODEL = "gemini-flash-lite-latest"
DEFAULT_ENGINE = "gemini"


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def partner_base() -> Path:
    env = (os.environ.get("YORITOORI_BASE_PATH") or "").strip()
    if env:
        p = Path(env).expanduser()
        if p.is_dir():
            return p.resolve()
    if ONEDRIVE_PARTNER.is_dir():
        return ONEDRIVE_PARTNER.resolve()
    return (REPO / "215_kamiooya" / "C2_ルーティン作業" / "26_パートナー社への相談").resolve()


def load_dotenv_private() -> None:
    env_path = REPO / ".env.jarvis_private"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip("'").strip('"')
        if k and k not in os.environ:
            os.environ[k] = v


def load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_config() -> dict[str, Any]:
    cfg = load_json(
        CONFIG_PATH,
        {
            "engine": DEFAULT_ENGINE,
            "gemini_model": DEFAULT_GEMINI_MODEL,
            "disabled": False,
            "max_drafts_per_run": 15,
            "lookback_days": 90,
        },
    )
    return cfg


def normalize_subject(subject: str) -> str:
    s = (subject or "").strip()
    s = RE_PREFIX_RE.sub("", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def is_gmail_channel(channel: str) -> bool:
    ch = (channel or "").strip()
    if ch in ("相手から返信", "自分から送信"):
        return True
    # Gmail 明示付き（将来拡張）
    if "Gmail" in ch and ("相手から返信" in ch or "自分から送信" in ch):
        if any(x in ch for x in ("Chatwork", "LINE", "SMS", "iMessage", "オープンチャット")):
            return False
        return True
    return False


def is_inbound(channel: str) -> bool:
    return "相手から返信" in (channel or "") and "自分から送信" not in (channel or "")


def chat_channel_kind(channel: str) -> str | None:
    """Chatwork / LINE / iMessage ならラベル、メール等なら None。"""
    ch = channel or ""
    if "Chatwork" in ch:
        return "Chatwork"
    if "iMessage" in ch or "/SMS" in ch or "（SMS" in ch or "SMS/" in ch:
        return "iMessage"
    if "LINE" in ch or "CHRLINE" in ch or "公式エクスポート" in ch:
        return "LINE"
    return None


def is_chat_inbound(channel: str) -> bool:
    ch = channel or ""
    if "自分から送信" in ch:
        return False
    if "相手から返信" in ch:
        return True
    # LINE グループ見出し: …（…受信）
    if "受信" in ch and "送信" not in ch:
        return True
    if "公式エクスポート" in ch:
        return True
    return False


def parse_received_at(s: str) -> datetime | None:
    s = (s or "").strip()
    for fmt, n in (("%Y/%m/%d %H:%M", 16), ("%Y/%m/%d", 10)):
        try:
            return datetime.strptime(s[:n], fmt).replace(tzinfo=JST)
        except ValueError:
            continue
    return None


def activity_id(lane: str, folder: str, received_at: str, channel: str, summary: str) -> str:
    raw = f"{lane}|{folder}|{received_at}|{channel}|{(summary or '')[:80]}"
    return "a" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:11]


def summarize_activity_text(summary: str, body: str) -> str:
    text = (summary or "").strip() or (body or "").strip().replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if PLACEHOLDER_BODY_RE.search(text) or PLACEHOLDER_BODY_RE.search(body or ""):
        base = text[:120] if text and not PLACEHOLDER_BODY_RE.search(text[:40]) else ""
        return (base + " （本文未取得）").strip() if base else "（本文未取得）"
    return text[:180] if text else "（要約なし）"


def find_recent_chat_activity(
    entries: list[dict[str, Any]],
    lookback_days: int,
    *,
    per_partner: int = ACTIVITY_PER_PARTNER,
) -> list[dict[str, Any]]:
    """パートナー MD から Chatwork/LINE/iMessage の直近受信を抽出。"""
    cutoff = None
    if lookback_days > 0:
        from datetime import timedelta

        cutoff = datetime.now(JST) - timedelta(days=lookback_days)
    picked: list[dict[str, Any]] = []
    # 新しい順に走査し、フォルダごとに上限
    ordered = sorted(entries, key=lambda x: x.get("received_at") or "", reverse=True)
    per_folder: dict[str, int] = {}
    for e in ordered:
        kind = chat_channel_kind(e.get("channel") or "")
        if not kind:
            continue
        if not is_chat_inbound(e.get("channel") or ""):
            continue
        if NOISE_SUBJECT_RE.search(e.get("summary") or "") or NOISE_SUBJECT_RE.search(e.get("subject") or ""):
            continue
        if cutoff:
            dt = parse_received_at(e.get("received_at") or "")
            if dt and dt < cutoff:
                continue
        folder = e.get("folder") or ""
        if per_folder.get(folder, 0) >= per_partner:
            continue
        per_folder[folder] = per_folder.get(folder, 0) + 1
        summary = summarize_activity_text(e.get("summary") or "", e.get("body") or "")
        subject = e.get("subject") or summary
        if subject == e.get("summary") or not e.get("subject"):
            subject = f"[{kind}] {summary[:80]}"
        picked.append(
            {
                "id": activity_id("partner", folder, e.get("received_at") or "", e.get("channel") or "", summary),
                "lane": "partner",
                "kind": "activity",
                "status": "info",
                "channel": kind,
                "channel_raw": e.get("channel") or "",
                "partner_name": e.get("partner_name") or "",
                "folder": folder,
                "received_at": e.get("received_at") or "",
                "subject": subject[:120],
                "summary": summary,
                "body": (e.get("body") or "")[:2000],
                "priority": "",
                "draft_text": "",
            }
        )
    return picked


def list_openchat_mds(base: Path) -> list[tuple[str, Path]]:
    root = base / OPENCHAT_ROOT_NAME
    out: list[tuple[str, Path]] = []
    if not root.is_dir():
        return out
    for p in sorted(root.iterdir()):
        if not p.is_dir() or p.name.startswith(".") or p.name.startswith("000_"):
            continue
        md = p / "5.やり取り.md"
        if md.is_file():
            out.append((p.name, md))
    return out


def parse_openchat_md(md_path: Path, group_folder: str) -> list[dict[str, Any]]:
    """815 オプチャの見出しをパース（欄数が可変）。"""
    text = md_path.read_text(encoding="utf-8", errors="replace")
    entries: list[dict[str, Any]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith("### "):
            i += 1
            continue
        parts = [p.strip() for p in line[4:].split("｜")]
        if len(parts) < 5:
            i += 1
            continue
        received_at = parts[0]
        stream = parts[1] if len(parts) > 1 else ""
        group = parts[2] if len(parts) > 2 else group_folder
        # スレッドタイトル有無で位置がずれる
        direction = ""
        sender = ""
        summary = ""
        if len(parts) >= 6 and parts[3] in ("受信", "送信"):
            direction, sender, summary = parts[3], parts[4], "｜".join(parts[5:])
        elif len(parts) >= 7 and parts[4] in ("受信", "送信"):
            direction, sender, summary = parts[4], parts[5], "｜".join(parts[6:])
        else:
            # 末尾付近から 受信/送信 を探す
            for j, p in enumerate(parts):
                if p in ("受信", "送信"):
                    direction = p
                    sender = parts[j + 1] if j + 1 < len(parts) else ""
                    summary = "｜".join(parts[j + 2 :]) if j + 2 < len(parts) else ""
                    break
        body_lines: list[str] = []
        i += 1
        while i < len(lines) and not lines[i].startswith("### "):
            body_lines.append(lines[i])
            i += 1
        body = "\n".join(body_lines).strip()
        entries.append(
            {
                "folder": group_folder,
                "partner_name": group or group_folder,
                "received_at": received_at,
                "stream": stream,
                "direction": direction,
                "sender": sender,
                "summary": (summary or "")[:200],
                "body": body[:4000],
                "inbound": direction == "受信",
            }
        )
    return entries


def find_recent_openchat_activity(
    entries: list[dict[str, Any]],
    lookback_days: int,
) -> list[dict[str, Any]]:
    cutoff = None
    if lookback_days > 0:
        from datetime import timedelta

        cutoff = datetime.now(JST) - timedelta(days=lookback_days)
    picked: list[dict[str, Any]] = []
    ordered = sorted(entries, key=lambda x: x.get("received_at") or "", reverse=True)
    for e in ordered:
        if not e.get("inbound"):
            continue
        if cutoff:
            dt = parse_received_at(e.get("received_at") or "")
            if dt and dt < cutoff:
                continue
        summary = summarize_activity_text(e.get("summary") or "", e.get("body") or "")
        stream = e.get("stream") or "【メイン】"
        sender = e.get("sender") or ""
        subject = f"{stream} {sender}".strip()
        ch_label = stream.replace("【", "").replace("】", "") or "オープンチャット"
        folder = e.get("folder") or ""
        picked.append(
            {
                "id": activity_id(
                    "openchat",
                    folder,
                    e.get("received_at") or "",
                    f"{stream}|{sender}",
                    summary,
                ),
                "lane": "openchat",
                "kind": "activity",
                "status": "info",
                "channel": ch_label,
                "partner_name": e.get("partner_name") or folder,
                "folder": folder,
                "received_at": e.get("received_at") or "",
                "subject": subject[:120],
                "summary": summary,
                "body": (e.get("body") or "")[:2000],
                "priority": "",
                "draft_text": "",
            }
        )
    return picked


def replace_activity_items(queue: dict[str, Any], activities: list[dict[str, Any]]) -> int:
    """kind=activity を一括差し替え。"""
    kept = [it for it in queue.get("items") or [] if it.get("kind") != "activity"]
    stamped = []
    for a in activities:
        item = queue_item_fields(
            {
                "id": a["id"],
                "lane": a.get("lane") or "partner",
                "partner_name": a.get("partner_name") or "",
                "folder": a.get("folder") or "",
                "subject": a.get("subject") or "",
                "received_at": a.get("received_at") or "",
                "body": a.get("body") or "",
            },
            {
                "kind": "activity",
                "status": "info",
                "channel": a.get("channel") or "",
                "summary": a.get("summary") or "",
                "priority": "",
                "draft_text": "",
                "reason": "",
            },
        )
        stamped.append(item)
    queue["items"] = kept + stamped
    queue["updated_at"] = now_iso()
    return len(stamped)


def entry_id(folder: str, received_at: str, subject: str) -> str:
    raw = f"{folder}|{received_at}|{normalize_subject(subject)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def parse_yoritoori(md_path: Path, partner_folder: str, partner_name: str) -> list[dict[str, Any]]:
    text = md_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    entries: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        m = HEADING_RE.match(lines[i])
        if not m:
            i += 1
            continue
        received_at, name, channel, summary = m.group(1), m.group(2).strip(), m.group(3).strip(), m.group(4).strip()
        body_lines: list[str] = []
        i += 1
        while i < len(lines) and not HEADING_RE.match(lines[i]):
            body_lines.append(lines[i])
            i += 1
        body = "\n".join(body_lines).strip()
        sm = SUBJECT_RE.search(body)
        subject = (sm.group(1).strip() if sm else summary) or "(件名なし)"
        # 件名行以降の本文（引用込みだが上限で切る）
        body_main = body
        if sm:
            body_main = body[sm.end() :].strip()
        entries.append(
            {
                "folder": partner_folder,
                "partner_name": name or partner_name,
                "received_at": received_at,
                "channel": channel,
                "summary": summary[:200],
                "subject": subject,
                "subject_norm": normalize_subject(subject),
                "body": body_main[:8000],
                "inbound": is_inbound(channel),
                "gmail": is_gmail_channel(channel),
            }
        )
    return entries


def find_unreplied(entries: list[dict[str, Any]], lookback_days: int) -> list[dict[str, Any]]:
    """同一 subject_norm の時系列で、最後が受信のものを未返信候補にする。"""
    gmail = [e for e in entries if e["gmail"]]
    # ファイルは新しい順 → スレッド内では古い順に並べ替えて判定
    by_subj: dict[str, list[dict[str, Any]]] = {}
    for e in gmail:
        by_subj.setdefault(e["subject_norm"] or e["summary"][:80], []).append(e)

    cutoff = None
    if lookback_days > 0:
        from datetime import timedelta

        cutoff = datetime.now(JST) - timedelta(days=lookback_days)

    candidates: list[dict[str, Any]] = []
    for _subj, items in by_subj.items():
        # received_at 昇順
        def _key(x: dict[str, Any]) -> str:
            return x["received_at"]

        ordered = sorted(items, key=_key)
        last = ordered[-1]
        if not last["inbound"]:
            continue
        if cutoff:
            try:
                dt = datetime.strptime(last["received_at"][:16], "%Y/%m/%d %H:%M").replace(tzinfo=JST)
            except ValueError:
                try:
                    dt = datetime.strptime(last["received_at"][:10], "%Y/%m/%d").replace(tzinfo=JST)
                except ValueError:
                    dt = None
            if dt and dt < cutoff:
                continue
        subj = last["subject"]
        body = last["body"]
        if NOISE_SUBJECT_RE.search(subj) or NOISE_BODY_RE.search(body) or NOISE_BODY_RE.search(last["summary"]):
            continue
        # 文脈: 直近最大4通
        ctx = ordered[-4:]
        candidates.append(
            {
                **last,
                "lane": "partner",
                "context": ctx,
                "id": entry_id(last["folder"], last["received_at"], last["subject"]),
            }
        )
    # 新しい順
    candidates.sort(key=lambda x: x["received_at"], reverse=True)
    return candidates


def list_partner_mds(base: Path) -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    if not base.is_dir():
        return out
    for p in sorted(base.iterdir()):
        if not p.is_dir() or p.name.startswith(".") or p.name in SKIP_FOLDERS:
            continue
        if p.name.startswith("815_"):
            continue
        md = p / "5.やり取り.md"
        if md.is_file():
            out.append((p.name, md))
    return out


def run_gmail_fetch(dry_run: bool) -> int:
    script = MANUAL_DIR / "gmail_to_yoritoori.py"
    if not script.is_file():
        print(f"# fetch: script missing: {script}", file=sys.stderr)
        return 1
    if dry_run:
        print(f"# dry-run: would run {script}")
        return 0
    env = os.environ.copy()
    env.setdefault("YORITOORI_BASE_PATH", str(partner_base()))
    cmd = [str(PY), str(script)]
    print(f"# fetch: {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=str(MANUAL_DIR), env=env)
    return r.returncode


def gemini_generate(prompt: str, model: str, api_key: str) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 2048},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini HTTP {e.code}: {err[:500]}") from e
    cands = data.get("candidates") or []
    if not cands:
        raise RuntimeError(f"Gemini empty response: {json.dumps(data, ensure_ascii=False)[:400]}")
    parts = (((cands[0] or {}).get("content") or {}).get("parts")) or []
    texts = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("text")]
    return "\n".join(texts).strip()


def find_cursor_agent() -> str | None:
    for name in ("agent", "cursor-agent"):
        p = shutil.which(name)
        if p:
            return p
    local = Path.home() / ".local" / "bin"
    for name in ("agent", "cursor-agent"):
        p = local / name
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return None


def cursor_generate(prompt: str) -> str:
    exe = find_cursor_agent()
    if not exe:
        raise RuntimeError("cursor-agent / agent が見つかりません（未インストール）")
    # 非対話・読取専用（下書き生成のみ。ファイル書込させない）
    cmd = [exe, "-p", "--mode", "ask", "--output-format", "text", prompt]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        raise RuntimeError(f"cursor-agent failed ({r.returncode}): {r.stderr[:500] or r.stdout[:500]}")
    return (r.stdout or "").strip()


def build_judge_prompt(c: dict[str, Any]) -> str:
    ctx_lines = []
    for e in c.get("context") or []:
        role = "相手" if e["inbound"] else "自分"
        ctx_lines.append(f"[{e['received_at']}|{role}] {e['subject']}\n{(e['body'] or '')[:1200]}")
    return f"""あなたは不動産オーナー（松野）の秘書です。メールについて返信が必要か判定してください。

相手: {c['partner_name']}（{c.get('folder') or c.get('from_email') or c.get('lane') or ''}）
最新件名: {c['subject']}
最新受信: {c['received_at']}

直近のやり取り:
---
{chr(10).join(ctx_lines)}
---

次の JSON のみを返してください（Markdown不可）:
{{"needs_reply": true/false, "priority": "high"|"medium"|"low", "summary": "1行要約", "reason": "短い理由"}}

返信不要の例: 単なる承知の連絡、自動通知、パスワード通知、既に完結している御礼のみ、配信メール、広告。
返信要の例: 質問・依頼・署名依頼・確認待ち・期限あり・意思決定が必要。
"""


def build_draft_prompt(c: dict[str, Any], judge: dict[str, Any]) -> str:
    ctx_lines = []
    for e in c.get("context") or []:
        role = "相手" if e["inbound"] else "自分"
        ctx_lines.append(f"[{e['received_at']}|{role}]\n{(e['body'] or '')[:1500]}")
    return f"""あなたは株式会社リビングサポート松の代表・松野真治です。パートナーへの返信メール下書きを書いてください。

ルール:
- 日本語。丁寧だが冗長にしない。
- 冒頭は相手の呼び方に合わせる（〇〇様）。不明なら「ご担当者様」。
- 末尾署名は「松野」のみ（会社名の長い署名ブロックは付けない）。
- 勝手な約束・金額・日付を捏造しない。文脈にないことは書かない。不明点は確認の一文にする。
- 件名行は書かない。本文のみ。
- 「Re:」や引用は付けない。

パートナー: {c['partner_name']}
件名（参考）: {c['subject']}
判定要約: {judge.get('summary', '')}

直近やり取り:
---
{chr(10).join(ctx_lines)}
---

返信本文のみを出力してください。
"""


def extract_json_obj(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            raise
        return json.loads(m.group(0))


def generate_with_engine(engine: str, prompt: str, model: str, api_key: str) -> str:
    if engine == "gemini":
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY が未設定です")
        return gemini_generate(prompt, model, api_key)
    if engine == "cursor":
        return cursor_generate(prompt)
    raise RuntimeError(f"unknown engine: {engine}")


def macos_notify(title: str, body: str) -> None:
    script = f'display notification {json.dumps(body)} with title {json.dumps(title)}'
    try:
        subprocess.run(["osascript", "-e", script], check=False, capture_output=True)
    except Exception:
        pass


LOCAL_DASHBOARD_URL = "http://127.0.0.1:8765/"
LAST_AUTO_OPEN_PATH = STATE_DIR / "last_auto_open_date"
DASHBOARD_LABEL = "com.matsunoma.jarvis.triage-dashboard"


def resolve_dashboard_url() -> str:
    """本番 Vercel URL（JARVIS_DASHBOARD_URL）があれば優先。なければローカル 8765。"""
    cloud = (os.environ.get("JARVIS_DASHBOARD_URL") or "").strip().rstrip("/")
    if cloud:
        return cloud + "/"
    return LOCAL_DASHBOARD_URL


# 後方互換
DASHBOARD_URL = LOCAL_DASHBOARD_URL


def pending_items(queue: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    q = queue if queue is not None else load_queue()
    return [it for it in (q.get("items") or []) if it.get("status") == "pending"]


def pending_partner_hint(items: list[dict[str, Any]], *, limit: int = 3) -> str:
    names: list[str] = []
    seen: set[str] = set()
    for it in items:
        name = str(it.get("partner") or it.get("folder") or it.get("from_email") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
        if len(names) >= limit:
            break
    return "・".join(names)


def today_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def already_auto_opened_today() -> bool:
    if not LAST_AUTO_OPEN_PATH.is_file():
        return False
    try:
        return LAST_AUTO_OPEN_PATH.read_text(encoding="utf-8").strip() == today_jst()
    except OSError:
        return False


def mark_auto_opened_today() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LAST_AUTO_OPEN_PATH.write_text(today_jst() + "\n", encoding="utf-8")


def wait_dashboard_ready(*, timeout_s: float = 25.0) -> bool:
    """localhost:8765 が応答するまで待つ。必要なら launchd kickstart。"""
    deadline = time.time() + timeout_s
    kicked = False
    while time.time() < deadline:
        try:
            urllib.request.urlopen(DASHBOARD_URL, timeout=2)
            return True
        except Exception:
            if not kicked and time.time() + 10 < deadline:
                try:
                    uid = os.getuid()
                    subprocess.run(
                        ["launchctl", "kickstart", "-k", f"gui/{uid}/{DASHBOARD_LABEL}"],
                        capture_output=True,
                        timeout=10,
                    )
                except Exception:
                    pass
                kicked = True
            time.sleep(1.0)
    return False


def open_dashboard_browser(
    *,
    force: bool = False,
    dry_run: bool = False,
    require_daytime: bool = True,
) -> tuple[bool, str]:
    """
    pending≥1 のときダッシュボードをブラウザで開く。
    force=False なら同一日の再オープンをスキップ。
    require_daytime=True なら 5:00–22:59 のみ（夜間の無人オープン防止）。
    戻り値: (opened_or_would_open, message)
    """
    items = pending_items()
    n = len(items)
    if n < 1:
        return False, "pending=0（オープン不要）"
    if not force and already_auto_opened_today():
        return False, f"pending={n} だが本日は既に自動オープン済み"
    hour = datetime.now(JST).hour
    if require_daytime and not (5 <= hour <= 22):
        return False, f"pending={n} だが表示時間外（hour={hour}）"
    url = resolve_dashboard_url()
    if dry_run:
        return True, f"dry-run: pending={n} なら open する ({url})"
    # ローカル 8765 のときだけ起動待ち。クラウドは常に到達可想定。
    if url.startswith("http://127.0.0.1") or url.startswith("http://localhost"):
        if not wait_dashboard_ready():
            return False, "ダッシュボード未応答（8765）"
    try:
        subprocess.run(["open", url], check=False, capture_output=True)
    except Exception as e:
        return False, f"open 失敗: {e}"
    mark_auto_opened_today()
    return True, f"opened pending={n} url={url}"


def load_queue() -> dict[str, Any]:
    data = load_json(QUEUE_PATH, {"version": 1, "items": [], "updated_at": None})
    if "items" not in data:
        data["items"] = []
    changed = False
    for it in data["items"]:
        if not it.get("lane"):
            it["lane"] = "partner"
            changed = True
    if changed:
        save_json(QUEUE_PATH, data)
    return data


def queue_item_fields(c: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """候補 dict から queue 保存用フィールドを組み立てる。"""
    body = str(c.get("body") or "")
    base = {
        "id": c["id"],
        "lane": c.get("lane") or "partner",
        "partner": c.get("partner_name") or c.get("partner") or "",
        "folder": c.get("folder") or "",
        "subject": c.get("subject") or "",
        "received_at": c.get("received_at") or "",
        "account": c.get("account") or "",
        "gmail_thread_id": c.get("gmail_thread_id") or "",
        "gmail_message_id": c.get("gmail_message_id") or "",
        "from_email": c.get("from_email") or "",
        "message_id_header": c.get("message_id_header") or "",
        "original_body": body[:8000],
        "updated_at": now_iso(),
    }
    base.update(extra)
    return base


def upsert_item(queue: dict[str, Any], item: dict[str, Any]) -> None:
    items: list[dict[str, Any]] = queue["items"]
    for i, old in enumerate(items):
        if old.get("id") == item["id"]:
            # sent/skipped は上書きしない（新着で再オープンする場合のみ）
            if old.get("status") in ("sent", "skipped") and item.get("status") == "pending":
                if old.get("received_at") == item.get("received_at"):
                    return
            merged = {**old, **item}
            items[i] = merged
            return
    items.append(item)


def mark_status(item_id: str, status: str) -> None:
    queue = load_queue()
    found = False
    for it in queue["items"]:
        if str(it.get("id")) == str(item_id) or str(it.get("seq")) == str(item_id):
            it["status"] = status
            it["updated_at"] = now_iso()
            found = True
            break
    if not found:
        raise SystemExit(f"item not found: {item_id}")
    queue["updated_at"] = now_iso()
    save_json(QUEUE_PATH, queue)
    print(f"# marked {item_id} -> {status}")


def assign_seqs(queue: dict[str, Any]) -> None:
    """pending に通番を振る（ダッシュボード用）。既存 seq は維持。"""
    used = {it.get("seq") for it in queue["items"] if it.get("seq") is not None}
    n = 1
    for it in queue["items"]:
        if it.get("status") != "pending":
            continue
        if it.get("seq") is not None:
            continue
        while n in used:
            n += 1
        it["seq"] = n
        used.add(n)
        n += 1


def regenerate_dashboard() -> None:
    dash = REPO / "scripts" / "jarvis_triage_dashboard.py"
    if dash.is_file():
        subprocess.run([str(PY), str(dash), "--write"], check=False)


def process_candidates(
    candidates: list[dict[str, Any]],
    *,
    engine: str,
    compare: bool,
    model: str,
    api_key: str,
    dry_run: bool,
    limit: int,
    judge_only: bool,
) -> tuple[int, int]:
    queue = load_queue()
    drafted = 0
    judged_need = 0
    sleep_s = 4.5 if engine == "gemini" else 1.0

    for c in candidates[:limit]:
        lane = c.get("lane") or "partner"
        label = c.get("folder") or c.get("from_email") or lane
        print(f"# candidate [{lane}/{label}] {c['received_at']} {c['subject'][:60]}")
        judge_prompt = build_judge_prompt(c)
        if dry_run:
            print("  (dry-run) skip LLM")
            continue
        try:
            judge_raw = generate_with_engine(engine if not compare else "gemini", judge_prompt, model, api_key)
            judge = extract_json_obj(judge_raw)
        except Exception as e:
            print(f"  ! judge failed: {e}", file=sys.stderr)
            continue
        needs = bool(judge.get("needs_reply"))
        print(f"  needs_reply={needs} priority={judge.get('priority')} summary={judge.get('summary')}")
        if not needs:
            upsert_item(
                queue,
                queue_item_fields(
                    c,
                    {
                        "seq": None,
                        "priority": judge.get("priority") or "low",
                        "summary": judge.get("summary") or c.get("summary") or "",
                        "reason": judge.get("reason") or "",
                        "draft_text": "",
                        "draft_gemini": "",
                        "draft_cursor": "",
                        "status": "skipped",
                        "engine": engine,
                    },
                ),
            )
            time.sleep(sleep_s)
            continue

        judged_need += 1
        if judge_only:
            upsert_item(
                queue,
                queue_item_fields(
                    c,
                    {
                        "priority": judge.get("priority") or "medium",
                        "summary": judge.get("summary") or "",
                        "reason": judge.get("reason") or "",
                        "draft_text": "",
                        "status": "pending",
                        "engine": engine,
                    },
                ),
            )
            time.sleep(sleep_s)
            continue

        draft_prompt = build_draft_prompt(c, judge)
        draft_gemini = ""
        draft_cursor = ""
        draft_text = ""
        try:
            if compare:
                time.sleep(sleep_s)
                draft_gemini = generate_with_engine("gemini", draft_prompt, model, api_key)
                try:
                    draft_cursor = generate_with_engine("cursor", draft_prompt, model, api_key)
                except Exception as e:
                    draft_cursor = f"（Cursor Agent 失敗: {e}）"
                draft_text = draft_gemini
            else:
                time.sleep(sleep_s)
                draft_text = generate_with_engine(engine, draft_prompt, model, api_key)
                if engine == "gemini":
                    draft_gemini = draft_text
                else:
                    draft_cursor = draft_text
        except Exception as e:
            print(f"  ! draft failed: {e}", file=sys.stderr)
            continue

        upsert_item(
            queue,
            queue_item_fields(
                c,
                {
                    "priority": judge.get("priority") or "medium",
                    "summary": judge.get("summary") or "",
                    "reason": judge.get("reason") or "",
                    "draft_text": draft_text,
                    "draft_gemini": draft_gemini,
                    "draft_cursor": draft_cursor,
                    "status": "pending",
                    "engine": "compare" if compare else engine,
                },
            ),
        )
        drafted += 1
        time.sleep(sleep_s)

    assign_seqs(queue)
    queue["updated_at"] = now_iso()
    if not dry_run:
        save_json(QUEUE_PATH, queue)
        regenerate_dashboard()
    return judged_need, drafted


def apply_draft_to_partner(seq_or_id: str) -> Path | None:
    queue = load_queue()
    item = None
    for it in queue["items"]:
        if str(it.get("seq")) == str(seq_or_id) or str(it.get("id")) == str(seq_or_id):
            item = it
            break
    if not item:
        raise SystemExit(f"item not found: {seq_or_id}")
    draft = (item.get("draft_text") or "").strip()
    if not draft:
        raise SystemExit("draft_text empty")
    lane = item.get("lane") or "partner"
    subject = item.get("subject") or ""
    if lane == "general":
        print(f"# lane=general (Gmail Reply)")
        print(f"# to: {item.get('from_email')}")
        print(f"# thread: {item.get('gmail_thread_id')}")
        print(f"# subject: {subject}")
        print("---DRAFT---")
        print(draft)
        print("---")
        print("# 承認後: python scripts/jarvis_night_triage.py --send-gmail " + str(seq_or_id))
        return None
    folder = item["folder"]
    partner_dir = partner_base() / folder
    draft_path = partner_dir / "4.送信下書き.txt"
    if not subject.lower().startswith("re:"):
        subject_line = f"件名：Re: {subject}"
    else:
        subject_line = f"件名：{subject}"
    content = f"{subject_line}\n\n{draft}\n"
    draft_path.write_text(content, encoding="utf-8")
    print(f"# wrote draft -> {draft_path}")
    print(f"# partner folder: {folder}")
    print(f"# subject: {subject}")
    return draft_path


def send_general_gmail(seq_or_id: str) -> None:
    from jarvis_night_triage_general import send_general_reply

    queue = load_queue()
    item = None
    for it in queue["items"]:
        if str(it.get("seq")) == str(seq_or_id) or str(it.get("id")) == str(seq_or_id):
            item = it
            break
    if not item:
        raise SystemExit(f"item not found: {seq_or_id}")
    if (item.get("lane") or "partner") != "general":
        raise SystemExit("lane is not general — use yoritoori_send for partners")
    draft = (item.get("draft_text") or "").strip()
    if not draft:
        raise SystemExit("draft_text empty")
    result = send_general_reply(item, draft)
    print(f"# sent gmail id={result.get('id')} to={result.get('to')}")
    mark_status(str(item.get("seq") or item.get("id")), "sent")
    regenerate_dashboard()


def contact_yaml_path() -> Path:
    return partner_base() / "000_共通" / "連絡先一覧.yaml"


def main() -> int:
    load_dotenv_private()
    ap = argparse.ArgumentParser(description="Jarvis night email triage")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--engine", choices=("gemini", "cursor"), default=None)
    ap.add_argument("--compare-engines", action="store_true")
    ap.add_argument("--judge-only", action="store_true")
    ap.add_argument("--lane", choices=("partner", "general", "all"), default="all")
    ap.add_argument("--limit", type=int, default=0, help="処理する候補の上限（0=config）")
    ap.add_argument("--lookback-days", type=int, default=0)
    ap.add_argument("--mark-sent", metavar="ID")
    ap.add_argument("--mark-skipped", metavar="ID")
    ap.add_argument("--mark-snoozed", metavar="ID")
    ap.add_argument("--apply-draft", metavar="ID", help="partner: 4.送信下書きへ / general: プレビュー表示")
    ap.add_argument("--send-gmail", metavar="ID", help="general のみ・承認後に Gmail Reply 送信")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    if args.mark_sent:
        mark_status(args.mark_sent, "sent")
        regenerate_dashboard()
        return 0
    if args.mark_skipped:
        mark_status(args.mark_skipped, "skipped")
        regenerate_dashboard()
        return 0
    if args.mark_snoozed:
        mark_status(args.mark_snoozed, "snoozed")
        regenerate_dashboard()
        return 0
    if args.apply_draft:
        apply_draft_to_partner(args.apply_draft)
        return 0
    if args.send_gmail:
        send_general_gmail(args.send_gmail)
        return 0
    if args.list:
        q = load_queue()
        for it in q.get("items", []):
            if it.get("status") != "pending":
                continue
            print(
                f"#{it.get('seq')} [{it.get('lane') or 'partner'}][{it.get('priority')}] "
                f"{it.get('folder') or it.get('from_email')} | "
                f"{it.get('received_at')} | {it.get('subject', '')[:50]}"
            )
        return 0

    cfg = load_config()
    if cfg.get("disabled") and not args.dry_run:
        print("# night triage disabled in config.json")
        return 0

    engine = args.engine or cfg.get("engine") or DEFAULT_ENGINE
    model = cfg.get("gemini_model") or DEFAULT_GEMINI_MODEL
    api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    limit = args.limit or int(cfg.get("max_drafts_per_run") or 15)
    lookback = args.lookback_days or int(cfg.get("lookback_days") or 90)
    general_lookback = int(cfg.get("general_lookback_days") or 14)

    do_partner = args.lane in ("partner", "all")
    do_general = args.lane in ("general", "all")

    if do_partner and not args.skip_fetch:
        rc = run_gmail_fetch(args.dry_run)
        if rc != 0:
            print(f"# fetch failed rc={rc}", file=sys.stderr)

    base = partner_base()
    print(f"# partner base: {base}")
    print(f"# engine: {'compare' if args.compare_engines else engine} model={model} lane={args.lane}")

    all_cands: list[dict[str, Any]] = []
    activities: list[dict[str, Any]] = []
    activity_lookback = int(cfg.get("activity_lookback_days") or ACTIVITY_LOOKBACK_DEFAULT)
    if do_partner:
        for folder, md in list_partner_mds(base):
            name = folder.split("_", 1)[-1] if "_" in folder else folder
            entries = parse_yoritoori(md, folder, name)
            cands = find_unreplied(entries, lookback)
            all_cands.extend(cands)
            activities.extend(find_recent_chat_activity(entries, activity_lookback))
        # パートナー活動: 全体上限
        activities.sort(key=lambda x: x.get("received_at") or "", reverse=True)
        activities = activities[:ACTIVITY_PARTNER_MAX]
        print(f"# partner unreplied candidates: {sum(1 for c in all_cands if c.get('lane')=='partner')}")
        print(f"# partner chat activity: {len(activities)}")

        oc_acts: list[dict[str, Any]] = []
        for group, md in list_openchat_mds(base):
            entries = parse_openchat_md(md, group)
            oc_acts.extend(find_recent_openchat_activity(entries, activity_lookback))
        oc_acts.sort(key=lambda x: x.get("received_at") or "", reverse=True)
        oc_acts = oc_acts[:ACTIVITY_OPENCHAT_MAX]
        print(f"# openchat activity: {len(oc_acts)}")
        activities.extend(oc_acts)

    if do_general:
        try:
            from jarvis_night_triage_general import find_general_unreplied

            g_cands = find_general_unreplied(
                contact_yaml=contact_yaml_path(),
                lookback_days=general_lookback,
                max_threads=int(cfg.get("general_max_threads") or 40),
            )
            print(f"# general unreplied candidates: {len(g_cands)}")
            all_cands.extend(g_cands)
        except Exception as e:
            print(f"# general fetch failed: {e}", file=sys.stderr)

    all_cands.sort(key=lambda x: x.get("received_at") or "", reverse=True)
    print(f"# unreplied candidates total: {len(all_cands)}")

    queue = load_queue()
    existing = {it["id"]: it for it in queue.get("items", []) if it.get("id")}
    todo = []
    for c in all_cands:
        old = existing.get(c["id"])
        if old and old.get("status") in ("sent", "skipped") and not args.compare_engines:
            continue
        if old and old.get("status") == "pending" and old.get("draft_text") and not args.compare_engines:
            continue
        todo.append(c)

    print(f"# to process: {len(todo)} (limit {limit})")
    need, drafted = process_candidates(
        todo,
        engine=engine,
        compare=args.compare_engines,
        model=model,
        api_key=api_key,
        dry_run=args.dry_run,
        limit=limit,
        judge_only=args.judge_only,
    )

    if do_partner and not args.dry_run:
        queue = load_queue()
        n_act = replace_activity_items(queue, activities)
        assign_seqs(queue)
        save_json(QUEUE_PATH, queue)
        print(f"# activity items saved: {n_act}")
    elif do_partner and args.dry_run:
        print(f"# dry-run: would save {len(activities)} activity items")

    msg = f"要返信 {need} / 下書き {drafted} / 候補 {len(all_cands)}"
    print(f"# done: {msg}")
    if not args.dry_run:
        queue_after = load_queue()
        pending = pending_items(queue_after)
        hint = pending_partner_hint(pending)
        notify_body = msg
        if pending:
            notify_body = f"{msg}"
            if hint:
                notify_body = f"要返信 {len(pending)} 件 — {hint}"
            elif need:
                notify_body = f"要返信 {need} / 下書き {drafted} — pending {len(pending)}"
        macos_notify("Jarvis 夜間トリアージ", notify_body)
        # ブラウザは夜間に開かない（ユーザーが開いた最初のタイミングは morning-open 側）
        print("# dashboard open: skipped at batch (morning-open handles first open of day)")
        # 自分用 Supabase（jarvis-dashboard）へ push（SERVICE_ROLE 未設定ならスキップ）
        try:
            push = REPO / "scripts" / "jarvis_dashboard_push.py"
            if push.is_file() and (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip():
                r = subprocess.run(
                    [sys.executable, str(push)],
                    cwd=str(REPO),
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                print(f"# supabase push: exit={r.returncode} {(r.stderr or r.stdout or '')[-200:]}")
            else:
                print("# supabase push: skipped (JARVIS_SUPABASE_SERVICE_ROLE_KEY unset)")
        except Exception as e:
            print(f"# supabase push failed: {e}")
        logf = LOG_DIR / f"run_{datetime.now(JST).strftime('%Y%m%d_%H%M%S')}.log"
        logf.write_text(
            json.dumps(
                {
                    "at": now_iso(),
                    "engine": "compare" if args.compare_engines else engine,
                    "lane": args.lane,
                    "candidates": len(all_cands),
                    "need": need,
                    "drafted": drafted,
                    "pending": len(pending),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
