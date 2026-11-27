#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""318 Todoist消化係 — 済み検出（件119の5）.

Gmail・Slack・GitHub・各ボットの報告（Slack ハブ）に「終わった」根拠がある Todoist タスクを見つけ、
「済みらしい」印（【318】済みらしい コメント・根拠リンクつき）を付けるための材料を作る。

- 318 自身は Todoist を close しない（close は 62_ の了承事項）。閉じるのは ★000 大佐（水・土 8:30）で、
  この一覧（`done_likely.md`／`done_likely.json`）を見て閉じて事後報告する
- AI API は使わない（スクリプトだけ）。根拠の合致は「題の特徴語が2つ以上＋完了の手がかり」の機械判定で、
  あくまで「らしい」。確定ではない
- 読み口（Gmail・Slack・GitHub）が使えない時は「根拠なし」ではなく「その読み口は使えなかった」と記録する
- 読むだけ。外へ送らない・書かない
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Protocol

DONE_CHECK_DAYS = 7  # ② で回答がなく止まっている物へ済み検出だけ当て直す間隔（日）
EVIDENCE_WINDOW_DAYS = 30  # 根拠を探す期間
MAX_EVIDENCE = 3  # 1件に付ける根拠リンクの上限
MIN_TERMS = 2  # 合致に要る特徴語の数（題が特徴語1つだけの時は長い語1つ＋完了の手がかり）
DONE_LABEL = "済みらしい"
REPO_SLUG = "m19mhrts83-cyber/project-GE"
SLACK_CHANNELS = ("hub", "report", "consult", "ops")  # config/slack_ai_team_hub.yaml のキー。各ボットの報告が出る所
SLACK_LIMIT = 200

DONE_HINT_RE = re.compile(r"済み|済んだ|済ませ|送信しました|送りました|返信しました|対応しました|提出しました|支払いました|払いました|完了しました|完了済|が完了|マージ|merged|✅|解決しました")
HINT_WINDOW = 80  # 完了の手がかりの前後この文字数の中に、題の特徴語が要る（長い報告文に語が散らばっているだけでは当てない）
# 318 自身の報告・コメントと、「これから判断してほしい物を並べた」まとめ・報告は根拠にしない（自分で自分を済みにしない・待ちの一覧は済みではない）
OWN_POST_RE = re.compile(r"318 Todoist消化|【318】|判断待ち|ブリーフィング|週1レビュー|本日のタスク処置|要判断")
TERM_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]*|[ァ-ヶー]+|[一-龥々]+")
URL_RE = re.compile(r"https?://\S+")
REF_RE = re.compile(r"(?:#|PR\s*|pull/)(\d{2,5})")
# 特徴語にしない語（どのタスクにも出る・題だけでは何も分からない語）
STOP_TERMS = {
    "確認", "連絡", "対応", "検討", "手続", "手続き", "準備", "作成", "更新", "設定", "依頼", "報告", "資料", "提出", "今日", "明日",
    "今週", "来週", "今月", "来月", "以内", "以降", "関連", "について", "ください", "お願い", "必要", "完了", "予定", "調査", "整理",
    "状況", "内容", "全体", "一覧", "作業", "実施", "開始", "終了", "チェック", "メール", "タスク", "Slack", "slack", "AI",
}


class DocSource(Protocol):
    name: str

    def fetch(self, now: datetime) -> list[dict[str, Any]]:
        """[{source, url, text, when, strong_done(bool)}]。使えない時は例外（呼び出し側が「使えなかった」と記録する）。"""
        ...


def terms_of(title: str) -> list[str]:
    """題から特徴語を取り出す（印・URL・括弧のタグ・一般語を除く）。"""
    s = URL_RE.sub(" ", str(title or ""))
    s = re.sub(r"[【\[][^】\]]{0,20}[】\]]", " ", s)
    s = re.sub(r"^[^\w一-龥ぁ-んァ-ヶ]+", "", s)
    out: list[str] = []
    for m in TERM_RE.findall(s):
        if m in STOP_TERMS or len(m) < 2:
            continue
        if m not in out:
            out.append(m)
    return out


def refs_of(title: str) -> set[str]:
    return set(REF_RE.findall(str(title or "")))


def match_doc(title: str, doc: dict[str, Any]) -> bool:
    """題の特徴語の半分以上（最低2つ）が、完了の手がかりの近く（または短い完了文書の中）にある。"""
    text = str(doc.get("text") or "")
    if OWN_POST_RE.search(text):
        return False
    if doc.get("source") == "github" and doc.get("number") and str(doc["number"]) in refs_of(title):
        return True  # 題に PR 番号があり、その PR がマージ済み
    ts = terms_of(title)
    if not ts:
        return False
    # 題の特徴語の半分以上（最低2つ。特徴語が1つだけの題は4文字以上の語1つ）が同じ文脈に出ていること
    need = max(MIN_TERMS, (len(ts) + 1) // 2) if len(ts) >= MIN_TERMS else 1
    if doc.get("strong_done"):
        windows = [text]  # マージ済み PR・自分が送ったメールは、それ自体が完了の手がかり（短い文）
    else:
        windows = [text[max(0, m.start() - HINT_WINDOW): m.end() + HINT_WINDOW] for m in DONE_HINT_RE.finditer(text)]
    for w in windows:
        hit = [t for t in ts if t in w]
        if len(hit) >= need and not (need == 1 and len(hit[0]) < 4):
            return True
    return False


def find_evidence(title: str, docs: list[dict[str, Any]], *, cap: int = MAX_EVIDENCE) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for d in docs:
        if match_doc(title, d):
            out.append({"source": str(d["source"]), "url": str(d["url"]), "when": str(d.get("when") or "")[:10]})
            if len(out) >= cap:
                break
    return out


# ---------------------------------------------------------------------------
# 読み口（読むだけ）
# ---------------------------------------------------------------------------


class GitHubSource:
    """マージ済みの PR（gh CLI。追加の API 契約なし）。"""

    name = "github"

    def __init__(self, runner: Callable[[list[str]], str] | None = None, repo: str = REPO_SLUG):
        self._run = runner or self._default
        self._repo = repo

    @staticmethod
    def _default(argv: list[str]) -> str:
        return subprocess.run(argv, capture_output=True, text=True, timeout=60, check=True).stdout

    def fetch(self, now: datetime) -> list[dict[str, Any]]:
        since = (now - timedelta(days=EVIDENCE_WINDOW_DAYS)).date().isoformat()
        raw = self._run([
            "gh", "pr", "list", "--repo", self._repo, "--state", "merged", "--limit", "200",
            "--search", f"merged:>={since}", "--json", "number,title,url,mergedAt",
        ])
        return [
            {"source": "github", "url": p["url"], "text": str(p.get("title") or ""), "when": p.get("mergedAt") or "",
             "number": p.get("number"), "strong_done": True}
            for p in json.loads(raw or "[]")
        ]


class SlackSource:
    """Slack ハブ（各ボットの報告・やり取り）の直近。SLACK_BOT_TOKEN の読み取りだけ。"""

    name = "slack"

    def __init__(self, token: str, channels: dict[str, str], workspace: str, getter: Callable[[str, dict[str, str]], dict] | None = None):
        self._token = token
        self._channels = channels
        self._ws = workspace
        self._get = getter or self._default

    def _default(self, method: str, params: dict[str, str]) -> dict:
        req = urllib.request.Request(
            f"https://slack.com/api/{method}?" + urllib.parse.urlencode(params),
            headers={"Authorization": f"Bearer {self._token}"}, method="GET",
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))

    def fetch(self, now: datetime) -> list[dict[str, Any]]:
        if not self._token:
            raise RuntimeError("SLACK_BOT_TOKEN が無い")
        oldest = str((now - timedelta(days=EVIDENCE_WINDOW_DAYS)).timestamp())
        docs: list[dict[str, Any]] = []
        failed: list[str] = []
        for key, cid in self._channels.items():
            data = self._get("conversations.history", {"channel": cid, "limit": str(SLACK_LIMIT), "oldest": oldest})
            if not data.get("ok"):
                failed.append(f"{key}:{data.get('error') or 'error'}")  # 1チャンネルが読めなくても他は続ける
                continue
            for m in data.get("messages") or []:
                ts = str(m.get("ts") or "")
                if not ts or not m.get("text"):
                    continue
                docs.append({
                    "source": "slack", "text": str(m["text"]), "when": datetime.fromtimestamp(float(ts)).isoformat(),
                    "url": f"https://{self._ws}/archives/{cid}/p{ts.replace('.', '')}",
                })
        if failed and len(failed) == len(self._channels):
            raise RuntimeError("slack 全チャンネル読めない " + "・".join(failed))
        return docs


class GmailSource:
    """自分が送ったメール（件名・冒頭）の直近。送った事実そのものが「済み」の手がかり。"""

    name = "gmail"

    def __init__(self, token_path: str, service_factory: Callable[[str], Any] | None = None, limit: int = 80):
        self._path = token_path
        self._factory = service_factory or self._default
        self._limit = limit

    @staticmethod
    def _default(path: str) -> Any:
        from google.oauth2.credentials import Credentials  # noqa: PLC0415
        from googleapiclient.discovery import build  # noqa: PLC0415

        return build("gmail", "v1", credentials=Credentials.from_authorized_user_file(path), cache_discovery=False)

    def fetch(self, now: datetime) -> list[dict[str, Any]]:
        paths = [p for p in self._path.split(",") if p and Path(p).is_file()]
        if not paths:
            raise RuntimeError("Gmail の token が無い")
        docs: list[dict[str, Any]] = []
        errs: list[str] = []
        for pth in paths:
            try:
                docs += self._fetch_one(pth)
            except Exception as e:  # noqa: BLE001
                errs.append(type(e).__name__)
        if errs and len(errs) == len(paths):
            raise RuntimeError("Gmail の読取に全部失敗 " + "・".join(errs))
        return docs

    def _fetch_one(self, path: str) -> list[dict[str, Any]]:
        svc = self._factory(path)
        ids = svc.users().messages().list(userId="me", q=f"in:sent newer_than:{EVIDENCE_WINDOW_DAYS}d", maxResults=self._limit).execute()
        docs: list[dict[str, Any]] = []
        for m in ids.get("messages") or []:
            g = svc.users().messages().get(userId="me", id=m["id"], format="metadata", metadataHeaders=["Subject", "Date"]).execute()
            hdr = {h["name"]: h["value"] for h in (g.get("payload") or {}).get("headers") or []}
            docs.append({
                "source": "gmail", "text": f"{hdr.get('Subject', '')} {g.get('snippet', '')}", "when": hdr.get("Date", ""),
                "url": f"https://mail.google.com/mail/u/0/#sent/{g.get('threadId') or m['id']}", "strong_done": True,
            })
        return docs


def _gmail_tokens(env: dict[str, str]) -> str:
    """Jarvis の token と、同じ置き場の本人のメールの token（あれば）。パスをカンマでつなぐ。"""
    j = (env.get("GMAIL_TOKEN_JARVIS") or "").strip()
    out = [j] if j else []
    if j:
        for name in ("token_m19m.json", "token_estate.json", "token_livingsupport.json"):
            q = Path(j).parent / name
            if q.is_file():
                out.append(str(q))
    return ",".join(out)


def default_sources(env: dict[str, str], repo: Path) -> list[DocSource]:
    ch: dict[str, str] = {}
    ws = "aiwsnetwork.slack.com"
    try:
        import yaml  # type: ignore  # noqa: PLC0415

        cfg = yaml.safe_load((repo / "config" / "slack_ai_team_hub.yaml").read_text(encoding="utf-8")) or {}
        ws = str(cfg.get("workspace_hint") or ws)
        ch = {k: v["id"] for k, v in (cfg.get("channels") or {}).items() if k in SLACK_CHANNELS and isinstance(v, dict) and v.get("id")}
    except Exception:  # noqa: BLE001
        ch = {}
    return [
        GitHubSource(),
        SlackSource((env.get("SLACK_BOT_TOKEN") or "").strip(), ch, ws),
        GmailSource(_gmail_tokens(env)),
    ]


def load_docs(sources: list[DocSource], now: datetime) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """全読み口の文書と、使えなかった読み口（名前→理由）。1つが使えなくても他は続ける。"""
    docs: list[dict[str, Any]] = []
    unavailable: dict[str, str] = {}
    for s in sources:
        try:
            docs.extend(s.fetch(now))
        except Exception as e:  # noqa: BLE001
            unavailable[s.name] = f"{type(e).__name__}:{str(e)[:60]}"
    return docs, unavailable


# ---------------------------------------------------------------------------
# 対象の選び方・印の本文・大佐向けの一覧
# ---------------------------------------------------------------------------


def due_for_check(row: dict[str, Any], today: str, *, changed: bool) -> bool:
    """変化した件・まだ当てていない件・前回から DONE_CHECK_DAYS 日たった件。"""
    last = str((row.get("done_check") or {}).get("checked_on") or "")
    if changed or not last:
        return True
    try:
        return (datetime.fromisoformat(today) - datetime.fromisoformat(last)).days >= DONE_CHECK_DAYS
    except ValueError:
        return True


def stuck_owner_ids(hist_tasks: dict[str, Any], active_ids: set[str]) -> list[str]:
    """② で回答がなく止まっている物（判断待ちのまま残っている件）。"""
    return sorted(t for t, r in hist_tasks.items() if t in active_ids and r.get("queue_state") == "pending")


def format_done_comment(evidence: list[dict[str, str]], run_id: str, id_label: str, prefix: str) -> str:
    lines = [f"{prefix}{DONE_LABEL}", "要約: Gmail・Slack・GitHub に終わった跡がある（318 は閉じない。大佐が確かめて閉じる）", "根拠:"]
    for e in evidence:
        lines.append(f"- {e['source']} {e.get('when', '')} {e['url']}".rstrip())
    lines.append(f"{id_label}{run_id}")
    return "\n".join(lines)


def write_list(root: Path, hist_tasks: dict[str, Any], active_by_id: dict[str, dict], now: datetime) -> dict[str, Any]:
    """大佐が水・土 8:30 に閉じて事後報告できる一覧。題を含むので非公開の置き場（.jarvis_state）だけ。"""
    rows = []
    for tid, row in sorted(hist_tasks.items()):
        dc = row.get("done_check") or {}
        t = active_by_id.get(tid)
        if not (dc.get("likely") and t):
            continue
        rows.append({
            "task_id": tid, "title": str(t.get("content") or "")[:120], "url": f"https://app.todoist.com/app/task/{tid}",
            "evidence": dc.get("evidence") or [], "found_on": dc.get("found_on") or dc.get("checked_on"),
            "queue_state": row.get("queue_state"),
        })
    doc = {
        "version": 1, "updated_at": now.isoformat(timespec="seconds"),
        "note": "318 は閉じない。大佐（000・水土 8:30）が根拠リンクを見て、明らかに終わった物だけ完了にして事後報告する。迷う物は松野さん",
        "items": rows,
    }
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / "done_likely.json.tmp"
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, root / "done_likely.json")
    md = [f"# 済みらしい一覧（{now.date().isoformat()}・318）", "", doc["note"], ""]
    for r in rows:
        md.append(f"- [{r['title']}]({r['url']}) — 根拠: " + " ／ ".join(f"{e['source']} {e['url']}" for e in r["evidence"]))
    if not rows:
        md.append("（今は無し）")
    (root / "done_likely.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return doc
