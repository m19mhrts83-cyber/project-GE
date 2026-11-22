#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""318 Todoist消化係 — Phase 1（読むだけ）: 開始チェック → 基準・履歴の読込 → 抽出 → 変化なし除外 → 3分類 → 内部ログ.

設計の正本: FlowForge flow_HMy15MUxWiSpw5QgAPYa_8e4（承認済み 15 ノード）。
社員フォルダ: docs/AIエージェントチーム/300_品質・タスク運用管理室/318_Todoist消化係/

Phase 1 で守ること（コードで縛る）:
- Todoist は GET だけ（TodoistReader に書き込みの口が無い）。コメント・完了・削除・期限変更をしない
- Slack に送らない。報告は「案」を内部ログに置くだけ
- 起動は手動だけ（定期起動の登録はしない）
- 1 回 最大 60 分・処理 5 件

使い方（Mac）:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_318_triage.py run --dry-run   # 履歴は更新しない
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_318_triage.py run             # 履歴も更新（読むだけ）
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_318_triage.py status
  # AI（この実行の Claude Code）で分類を見直す時:
  #   run --dry-run --emit-packet → .jarvis_state/todoist_318/packet.json を読んで answers.json を書く
  #   run --ai-answers .jarvis_state/todoist_318/answers.json

置き場（git 管理外・private_paths の .jarvis_state/**）: .jarvis_state/todoist_318/
  history.json … task_id ごとの前回の状態（ハッシュだけ・題は書かない）
  runs/<run_id>.json … 1 回分の内部ログ（分類根拠・採用基準・判断案・停止理由・次回再評価条件・報告案）
  packet.json … AI 分類用の材料（題・説明を含む。非公開の置き場だけ）
  run.lock … 排他 ／ STOP … 置けば停止スイッチ
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Protocol
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_todoist_313_judgment as jd313  # noqa: E402  （指紋照合を再利用）
import jarvis_todoist_318_handoff as ho  # noqa: E402  （Phase 2: /313/bulk・週次・通知の部品）
from jarvis_todoist_mark import AI_MARK, REQUESTED_MARK, strip_mark  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
AGENT_ID = "318"
AGENT_ROLE = "Todoist消化"
PHASE = "phase2"
HOLD_AFTER_DEFER_DAYS = 14  # /313/bulk で「残す」を選んだら、この日数たってから再評価（cleanup_bulk の HOLD_DAYS と同じ）
MAX_TASKS = 5
MAX_MINUTES = 60
COMMENT_FETCH_CAP = 30  # 変化確認でコメントを読む上限（API の呼びすぎ防止。残りは繰越）
DEADLINE_SOON_DAYS = 3
OWN_COMMENT_PREFIX = "【318】"  # 自分のコメントは変化に数えない（Phase 3 の循環防止）
# 317 の受領の返し（元のコメントを引用するだけで新しい情報が無い）も変化に数えない。
# これを数えると、コメントが付くたびに 317 の返しでもう一度「変化あり」になる（2026-11-23 実データで確認）
ACK_COMMENT_PREFIXES = ("【AIチーム】見たよ",)
WINDOW_313 = ((10, 15), (11, 30))  # 313 0.5（毎朝 10:30 ごろ）と重ねない時間帯
API_BASE = "https://api.todoist.com/api/v1"

CATEGORY_TEXT = {"1": "①AIのみ", "2": "②松野さんの判断", "3": "③本人操作"}
PROPOSAL_TEXT = {
    "1": "Phase 2 で自律実行の対象（Phase 1 は実行しない。Todoist は閉じない）",
    "2": "松野さんに一言判断を依頼（/313/bulk の待ちに入れる。載るのは --publish の時だけ）",
    "3": "312 の週次計画（今週の9件）へ既存タスクのまま渡す（載るのは --publish の時だけ）",
}
NEXT_RECHECK = "題・説明・期限・締切・優先度・ラベル・コメント（【318】以外）・本人回答・親子の依存のどれかが変わったら再評価"

# 重要度は「部分文字列」ではなく、ラベル完全一致・題の【】[] タグ・Todoist の優先度で見る（313 の誤判定の修正）
IMPORTANT_LABELS = {"要ボス", "緊急", "優先1", "重要"}
IMPORTANT_TAGS = {"要ボス", "緊急", "優先1", "至急", "重要"}
# 外との約束・行事・支払いの期日（312 weekly_pick.HARD_RE と同じ語。重大な期限を先に）
HARD_WORDS = ("期限", "締切", "〆切", "振込", "支払", "引落", "説明会", "入試", "行事", "参加証", "更新前")
FAMILY_LABELS = {"kazoku", "family"}
URL_RE = re.compile(r"https?://\S+")
TAG_RE = re.compile(r"[【\[]([^】\]]{1,20})[】\]]")


def now_jst() -> datetime:
    return datetime.now(JST)


def _h(*parts: Any) -> str:
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# 失敗の型
# ---------------------------------------------------------------------------


class SafeStop(Exception):
    """処理せずに止める。result は failed（停止スイッチだけ stopped）。"""

    def __init__(self, code: str, reason: str, result: str = "failed"):
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.result = result


# ---------------------------------------------------------------------------
# Todoist（GET だけ）
# ---------------------------------------------------------------------------


class Reader(Protocol):
    def get(self, path: str) -> Any: ...


class TodoistReader:
    """GET だけの読み口。書き込みのメソッドは作らない（Phase 1 の約束）。"""

    def __init__(self, token: str, timeout: int = 40):
        self._token = token
        self._timeout = timeout
        self.calls = 0

    def get(self, path: str) -> Any:
        self.calls += 1
        req = urllib.request.Request(
            API_BASE + path,
            headers={"Authorization": f"Bearer {self._token}"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as r:
            raw = r.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}


def paginate(reader: Reader, path: str, *, limit: int = 200, max_pages: int = 30) -> list[dict]:
    """v1 の next_cursor を最後まで辿る。上限に当たったら途中までを返さず止める（読取不完全＝失敗）。"""
    out: list[dict] = []
    cursor = ""
    sep = "&" if "?" in path else "?"
    for _ in range(max_pages):
        q = f"{path}{sep}limit={limit}" + (f"&cursor={urllib.parse.quote(cursor)}" if cursor else "")
        d = reader.get(q)
        if isinstance(d, list):
            out.extend(d)
            return out
        if not isinstance(d, dict) or "results" not in d:
            raise SafeStop("read_shape", f"Todoist の応答の形が想定外（{path.split('?')[0]}）")
        out.extend(d.get("results") or [])
        cursor = str(d.get("next_cursor") or "")
        if not cursor:
            return out
    raise SafeStop("read_truncated", f"ページ上限（{max_pages}）に達した。途中までの件数では判断しない")


# ---------------------------------------------------------------------------
# 置き場
# ---------------------------------------------------------------------------


@dataclass
class Paths:
    state_dir: Path

    @property
    def root(self) -> Path:
        return self.state_dir / "todoist_318"

    @property
    def history(self) -> Path:
        return self.root / "history.json"

    @property
    def runs(self) -> Path:
        return self.root / "runs"

    @property
    def lock(self) -> Path:
        return self.root / "run.lock"

    @property
    def stop(self) -> Path:
        return self.root / "STOP"

    @property
    def packet(self) -> Path:
        return self.root / "packet.json"

    @property
    def bulk_queue(self) -> Path:
        return self.root / "bulk_queue.json"

    @property
    def weekly_handoff(self) -> Path:
        return self.root / "weekly_handoff.json"

    @property
    def drafts(self) -> Path:
        return self.root / "drafts"

    @property
    def cleanup_313(self) -> Path:
        return self.state_dir / "todoist_313_cleanup.json"

    @property
    def judgments_313(self) -> Path:
        return self.state_dir / "todoist_313_judgments.json"

    @property
    def agent_locks(self) -> Path:
        return self.state_dir / "agent_run_locks.json"


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_json_strict(path: Path, what: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except Exception as e:  # noqa: BLE001
        raise SafeStop("basis_unreadable", f"{what} が読めない（{type(e).__name__}）") from e


# ---------------------------------------------------------------------------
# 開始チェック
# ---------------------------------------------------------------------------


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def acquire_lock(paths: Paths, run_id: str) -> None:
    paths.root.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"run_id": run_id, "pid": os.getpid(), "started_at": now_jst().isoformat(timespec="seconds")})
    try:
        fd = os.open(paths.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        info: dict[str, Any] = {}
        try:
            info = json.loads(paths.lock.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
        pid = int(info.get("pid") or 0)
        state = "実行中" if pid and _pid_alive(pid) else "前回が異常終了した可能性"
        raise SafeStop(
            "lock_busy",
            f"排他: ロックあり（{state}・run={info.get('run_id', '?')}）。確かめてから `unlock --force`",
        )
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(body)


def release_lock(paths: Paths, run_id: str) -> None:
    try:
        info = json.loads(paths.lock.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return
    if info.get("run_id") == run_id:
        paths.lock.unlink(missing_ok=True)


def stop_switch_on(paths: Paths, env: dict[str, str]) -> str:
    if (env.get("TODOIST_318_STOP") or "").strip().lower() in ("1", "true", "on", "yes"):
        return "環境変数 TODOIST_318_STOP"
    if paths.stop.exists():
        return f"停止ファイル {paths.stop.name}"
    return ""


def check_313_overlap(paths: Paths, now: datetime, allow_window: bool) -> None:
    """313 0.5 との二重起動を防ぐ。313 のロックが running、または 10:15–11:30 の枠内なら止める。"""
    if paths.agent_locks.is_file():
        try:
            data = json.loads(paths.agent_locks.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            raise SafeStop("lock_313_unreadable", f"作業ロック表が読めない（{type(e).__name__}）") from e
        for k, row in ((data or {}).get("locks") or {}).items():
            if isinstance(row, dict) and str(row.get("agent_id")) == "313" and row.get("status") == "running":
                raise SafeStop("overlap_313", "313 が実行中（作業ロック表）。二重起動しない")
    if not allow_window:
        (h1, m1), (h2, m2) = WINDOW_313
        t = (now.hour, now.minute)
        if (h1, m1) <= t <= (h2, m2):
            raise SafeStop("overlap_313_window", "313 0.5（10:30 ごろ）の時間帯。重ねない（--allow-313-window で外す）")


def preflight(
    paths: Paths,
    env: dict[str, str],
    reader_factory: Callable[[str], Reader],
    *,
    now: datetime,
    allow_313_window: bool,
) -> tuple[Reader, dict[str, Any], dict[str, Any]]:
    """停止スイッチ・313との重なり・Todoist 接続・本人権限。ロックは呼び出し側で先に取る。"""
    checks: dict[str, Any] = {}
    why = stop_switch_on(paths, env)
    if why:
        raise SafeStop("stop_switch", f"停止スイッチが有効（{why}）", result="stopped")
    checks["stop_switch"] = "off"
    check_313_overlap(paths, now, allow_313_window)
    checks["overlap_313"] = "none"
    tok = (env.get("TODOIST_API_TOKEN_OWNER") or "").strip()
    if not tok:
        raise SafeStop("no_owner_token", "本人権限のトークン（TODOIST_API_TOKEN_OWNER）が無い。分身トークンでは読まない")
    reader = reader_factory(tok)
    try:
        user = reader.get("/user")
    except urllib.error.HTTPError as e:
        code = "permission" if e.code in (401, 403) else "todoist_http"
        raise SafeStop(code, f"Todoist 接続・権限の確認に失敗（HTTP {e.code}）") from e
    except Exception as e:  # noqa: BLE001
        raise SafeStop("todoist_connect", f"Todoist に接続できない（{type(e).__name__}）") from e
    if not isinstance(user, dict) or not user.get("id"):
        raise SafeStop("permission", "Todoist のユーザー情報が取れない（本人権限を確かめられない）")
    checks["todoist"] = "ok"
    checks["owner_permission"] = "ok"
    return reader, checks, user


# ---------------------------------------------------------------------------
# 1-1 採用済み基準・判断履歴
# ---------------------------------------------------------------------------


@dataclass
class Rule:
    id: str
    status: str
    category: str
    decision_id: str
    source: str
    title_any: list[str] = field(default_factory=list)
    labels_any: list[str] = field(default_factory=list)
    marks_any: list[str] = field(default_factory=list)
    tags_any: list[str] = field(default_factory=list)


@dataclass
class Basis:
    rules: list[Rule]
    ignored_rules: int
    judgments_313: dict[str, Any]
    history: dict[str, Any]
    first_run: bool
    owner_answers: dict[str, dict[str, str]] = field(default_factory=dict)

    @property
    def adopted_ids(self) -> list[str]:
        return [r.decision_id for r in self.rules if r.status == "adopted"]


def load_criteria(path: Path) -> tuple[list[Rule], int]:
    try:
        import yaml  # type: ignore
    except ImportError as e:
        raise SafeStop("basis_unreadable", "PyYAML が無いので基準を読めない") from e
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise SafeStop("basis_missing", f"基準ファイルが無い（{path.name}）") from e
    except Exception as e:  # noqa: BLE001
        raise SafeStop("basis_unreadable", f"基準ファイルが壊れている（{type(e).__name__}）") from e
    rows = (data or {}).get("rules") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        raise SafeStop("basis_unreadable", "基準ファイルに rules が無い")
    rules: list[Rule] = []
    ignored = 0
    for r in rows:
        if not isinstance(r, dict):
            raise SafeStop("basis_unreadable", "基準の行の形が想定外")
        status = str(r.get("status") or "")
        cat = str(r.get("category") or "")
        if status not in ("adopted", "proposed"):
            ignored += 1  # 未判断・見送り・取消は使わない
            continue
        if cat not in ("1", "2", "3", "large"):
            raise SafeStop("basis_unreadable", f"基準 {r.get('id')} の category が想定外")
        if status == "adopted" and not r.get("decision_id"):
            raise SafeStop("basis_unreadable", f"採用済み基準 {r.get('id')} に decision_id が無い")
        m = r.get("match") or {}
        words = [str(x) for x in (m.get("title_any") or [])]
        if any(len(w) < 2 for w in words):
            raise SafeStop("basis_unreadable", f"基準 {r.get('id')} に1文字の語（誤判定のもと）")
        rules.append(
            Rule(
                id=str(r.get("id")),
                status=status,
                category=cat,
                decision_id=str(r.get("decision_id") or ""),
                source=str(r.get("source") or ""),
                title_any=words,
                labels_any=[str(x) for x in (m.get("labels_any") or [])],
                marks_any=[str(x) for x in (m.get("marks_any") or [])],
                tags_any=[str(x) for x in (m.get("tags_any") or [])],
            )
        )
    return rules, ignored


def load_basis(paths: Paths, criteria_path: Path) -> Basis:
    rules, ignored = load_criteria(criteria_path)
    # 313 の判断履歴（「残す」＝本人の確定判断）。無い・壊れているは安全停止
    try:
        j313 = read_json_strict(paths.judgments_313, "313 の判断履歴")
    except FileNotFoundError as e:
        raise SafeStop("basis_missing", "313 の判断履歴（todoist_313_judgments.json）が無い") from e
    if not isinstance(j313, dict):
        raise SafeStop("basis_unreadable", "313 の判断履歴の形が想定外")
    j313.setdefault("keep", {})
    # 318 自身の履歴。初回だけ無くてよい（runs が既にあるのに無いのは異常）
    first_run = False
    try:
        hist = read_json_strict(paths.history, "318 の判断履歴")
    except FileNotFoundError:
        if paths.runs.is_dir() and any(paths.runs.glob("*.json")):
            live_runs = [p for p in paths.runs.glob("*.json") if '"mode": "live"' in p.read_text(encoding="utf-8")]
            if live_runs:
                raise SafeStop("basis_missing", "318 の判断履歴が無い（過去の本実行はある）。消えた可能性")
        hist = {"tasks": {}}
        first_run = True
    if not isinstance(hist, dict) or not isinstance(hist.get("tasks", {}), dict):
        raise SafeStop("basis_unreadable", "318 の判断履歴の形が想定外")
    hist.setdefault("tasks", {})
    return Basis(rules=rules, ignored_rules=ignored, judgments_313=j313, history=hist, first_run=first_run)


# ---------------------------------------------------------------------------
# 1-2 対象タスクの抽出（313 の順位付けを直したもの）
# ---------------------------------------------------------------------------


def _d(s: Any) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def due_of(t: dict) -> date | None:
    return _d((t.get("due") or {}).get("date"))


def deadline_of(t: dict) -> date | None:
    return _d((t.get("deadline") or {}).get("date"))


def clean_title(t: dict) -> str:
    return URL_RE.sub(" ", strip_mark(str(t.get("content") or "")))


def title_tags(t: dict) -> set[str]:
    return {m.strip() for m in TAG_RE.findall(str(t.get("content") or ""))}


def is_important(t: dict) -> bool:
    labels = {str(x) for x in (t.get("labels") or [])}
    return bool(labels & IMPORTANT_LABELS or title_tags(t) & IMPORTANT_TAGS)


def is_hard(t: dict) -> bool:
    """外との約束・行事・支払いの期日。312 weekly_pick.is_hard と同じ考え（URL を除いてから語を見る）。"""
    if deadline_of(t):
        return True
    labels = {str(x) for x in (t.get("labels") or [])}
    title = clean_title(t)
    return bool(due_of(t) and (labels & FAMILY_LABELS or any(w in title for w in HARD_WORDS)))


def candidate_filter(tasks: list[dict], user_id: str, today: date) -> list[dict]:
    """今日まで（今日＋期限切れ）か、締切（deadline）が近い未完了。担当は自分か未割当。"""
    out = []
    for t in tasks:
        if t.get("checked") or t.get("is_deleted") or t.get("completed_at"):
            continue
        resp = t.get("responsible_uid")
        if resp not in (None, "", user_id):
            continue
        du, dl = due_of(t), deadline_of(t)
        if (du and du <= today) or (dl and dl <= today + timedelta(days=DEADLINE_SOON_DAYS)):
            out.append(t)
    return out


def rank_key(t: dict, today: date, history: dict[str, Any]) -> tuple:
    """並べ順。313 の点数（min(超過日,60)＋部分一致の加点）を、段のある並べ方に置き換えた。

    1. 段: 締切が過ぎた／3日以内・外との約束の期日 → 今日の割り振り（週次予定） → ほかの期限切れ
    2. Todoist の優先度（p1 が先）
    3. 重要の印（ラベル完全一致・題の【】タグだけ。「高い」の「高」のような部分一致はしない）
    4. 最後に見た日が古い（まだ見ていない）ものを先に … 同点が毎日同じ5件に集中するのを防ぐ
    5. 超過日数（深い方が先・上限なし） 6. task_id（並びを毎回同じにする）
    """
    du, dl = due_of(t), deadline_of(t)
    if (dl and dl <= today + timedelta(days=DEADLINE_SOON_DAYS)) or (is_hard(t) and du and du <= today):
        tier = 0
    elif du == today:
        tier = 1
    else:
        tier = 2
    prio = int(t.get("priority") or 1)
    row = history.get(str(t.get("id"))) or {}
    last_seen = str(row.get("last_examined") or "")  # 空＝見ていない＝先
    over = (today - du).days if du else 0
    return (tier, -prio, 0 if is_important(t) else 1, last_seen, -over, str(t.get("id")))


def rank(tasks: list[dict], today: date, history: dict[str, Any]) -> list[dict]:
    return sorted(tasks, key=lambda t: rank_key(t, today, history))


# ---------------------------------------------------------------------------
# 1-3 前回から変化なしの除外
# ---------------------------------------------------------------------------


def dependency_sig(t: dict, children: dict[str, list[str]]) -> str:
    kids = sorted(children.get(str(t.get("id")), []))
    return _h(t.get("parent_id") or "", ",".join(kids))


def _ignored_comment(c: dict) -> bool:
    body = str(c.get("content") or "").lstrip()
    return body.startswith(OWN_COMMENT_PREFIX) or body.startswith(ACK_COMMENT_PREFIXES)


def note_count_of(t: dict) -> str:
    v = t.get("note_count")
    return "" if v is None else str(v)


def snapshot(
    t: dict,
    comments: list[dict] | None,
    children: dict[str, list[str]],
    owner_answer: str,
    *,
    comments_hash: str = "",
) -> dict[str, str]:
    """比べる項目ごとのハッシュ。題そのものは残さない。

    comments=None は「コメント数が前回と同じなので読まなかった」時。前回のハッシュ（comments_hash）を引き継ぐ。
    """
    du = (t.get("due") or {}) if isinstance(t.get("due"), dict) else {}
    if comments is None:
        c_hash = comments_hash
    else:
        others = [c for c in comments if not _ignored_comment(c)]
        c_hash = _h(len(others), ",".join(f"{c.get('id')}:{c.get('posted_at') or ''}" for c in others))
    return {
        "content": _h(t.get("content") or "", t.get("description") or ""),
        "due": _h(du.get("date") or "", du.get("is_recurring") or "", (t.get("deadline") or {}).get("date") or ""),
        "priority": str(t.get("priority") or ""),
        "labels": _h(",".join(sorted(str(x) for x in (t.get("labels") or [])))),
        "comments": c_hash,
        "note_count": note_count_of(t),
        "owner_answer": _h(owner_answer),
        "dependency": dependency_sig(t, children),
    }


def owner_answer_sig(task_id: str, basis: Basis) -> str:
    """本人回答: 313 の「残す」記録 ＋ owner_decisions（/313/bulk・20:00 ボタン）の最新の判断。"""
    keep = (basis.judgments_313.get("keep") or {}).get(task_id) or {}
    own = basis.owner_answers.get(task_id) or {}
    return json.dumps({"keep313": keep.get("fp") or "", "own": own}, sort_keys=True, ensure_ascii=False)


def recheck_on_for(answer: dict[str, str], t: dict, today: date) -> str:
    """本人回答の後、いつ再評価するか。日を変えた → その日。残す → 14日後。完了・削除 → タスクが消える。"""
    act = (answer or {}).get("action") or ""
    if act == "reschedule":
        du = due_of(t)
        return du.isoformat() if du else (today + timedelta(days=HOLD_AFTER_DEFER_DAYS)).isoformat()
    if act in ("defer", "keep"):
        return (today + timedelta(days=HOLD_AFTER_DEFER_DAYS)).isoformat()
    return ""


HINT_KEYS = {"note_count"}  # 読み方の手がかり。変化の判定には使わない（317 の受領の返しでも増えるため）


def detect_change(task_id: str, snap: dict[str, str], basis: Basis) -> tuple[str, list[str]]:
    prev = ((basis.history.get("tasks") or {}).get(task_id) or {}).get("snapshot")
    if not prev:
        return "new", []
    if not isinstance(prev, dict):
        return "hold", ["前回の記録の形が想定外"]
    keys = [k for k in snap if k not in HINT_KEYS]
    changed = [k for k in keys if prev.get(k) != snap[k]]
    missing = [k for k in keys if k not in prev]
    if missing and len(missing) == len(keys):
        return "hold", ["前回の記録に比べる項目が無い"]
    return ("changed", changed) if changed else ("unchanged", [])


# ---------------------------------------------------------------------------
# 1-4 3分類
# ---------------------------------------------------------------------------


def rule_hits(rule: Rule, t: dict) -> bool:
    raw = str(t.get("content") or "").lstrip()
    labels = {str(x) for x in (t.get("labels") or [])}
    tags = title_tags(t)
    text = clean_title(t) + " " + URL_RE.sub(" ", str(t.get("description") or ""))
    if rule.marks_any and any(raw.startswith(m) for m in rule.marks_any):
        return True
    if rule.labels_any and labels & set(rule.labels_any):
        return True
    if rule.tags_any and tags & set(rule.tags_any):
        return True
    if rule.title_any and any(w in text for w in rule.title_any):
        return True
    return False


def classify(t: dict, rules: list[Rule]) -> dict[str, Any]:
    """①は adopted の①だけに当たり、②③の印が一つも無い時だけ。迷ったら②。"""
    hits = [r for r in rules if rule_hits(r, t)]
    by = lambda cat, st=None: [r for r in hits if r.category == cat and (st is None or r.status == st)]  # noqa: E731
    large = bool(by("large"))
    blockers2 = by("2")
    blockers3 = by("3")
    ok1 = by("1", "adopted")
    if blockers3 and not blockers2:
        cat, basis_rules, why = "3", blockers3, "本人の操作が要る手がかり"
    elif blockers2:
        cat, basis_rules, why = "2", blockers2 + blockers3, "松野さんの判断が要る（採用済み基準）"
    elif ok1:
        cat, basis_rules, why = "1", ok1, "AIが進めてよい印・確認のみ（採用済み基準）・止める印なし"
    else:
        cat, basis_rules, why = "2", [], "迷ったら②（AIだけで進めてよい根拠が無い）"
    if cat == "2" and blockers3 and blockers2:
        why += "・本人操作の手がかりもあり"
    return {
        "category": cat,
        "reason": why,
        "rule_ids": [r.id for r in basis_rules],
        "applied_decision_ids": sorted({r.decision_id for r in basis_rules if r.status == "adopted"}),
        "hint_rule_ids": [r.id for r in basis_rules if r.status != "adopted"] + [r.id for r in by("large")],
        "large": large,
        "classified_by": "rule",
        "blocked_by_adopted_2": bool([r for r in blockers2 if r.status == "adopted"]),
    }


def apply_ai_answer(cls: dict[str, Any], ans: dict[str, Any] | None, snap_id: str) -> dict[str, Any]:
    """この実行の Claude Code が書いた分類で見直す。安全側（②③）へはいつでも、①へは採用済み②が無い時だけ。"""
    if not ans:
        return cls
    if str(ans.get("snapshot_id") or "") != snap_id:
        return {**cls, "ai_note": "AIの回答は前の内容に対するもの（無視）"}
    cat = str(ans.get("category") or "")
    reason = str(ans.get("reason") or "").strip()
    if cat not in ("1", "2", "3") or not reason:
        return {**cls, "ai_note": "AIの回答の形が想定外（無視）"}
    if cat == "1" and cls.get("blocked_by_adopted_2"):
        return {**cls, "ai_note": "AIは①案だが採用済み②基準に当たるので②のまま"}
    return {
        **cls,
        "rule_category": cls["category"],
        "category": cat,
        "reason": f"AI: {reason[:200]}",
        "classified_by": "ai(claude_code)",
        "large": bool(ans.get("large", cls.get("large"))),
    }


# ---------------------------------------------------------------------------
# 実行
# ---------------------------------------------------------------------------


@dataclass
class RunOptions:
    dry_run: bool = True
    max_tasks: int = MAX_TASKS
    max_minutes: int = MAX_MINUTES
    comment_cap: int = COMMENT_FETCH_CAP
    emit_packet: bool = False
    ai_answers: dict[str, Any] | None = None
    allow_313_window: bool = False
    owner_answers: str = "supabase"  # supabase（読めなければ安全停止）／skip（明示した時だけ）
    publish: bool = False  # ② を /313/bulk、③ を週次へ載せる（Supabase sync_meta への書き込み）
    send_slack: bool = False  # #consult 通知と #ai-hub 報告を実際に送る
    sb: Callable[..., Any] | None = None  # Supabase（テストで差し替え）
    poster: Callable[[str, str], bool] | None = None  # (channel, text) -> 送れたか


def new_run_id(now: datetime) -> str:
    return f"r318-{now.strftime('%Y%m%dT%H%M%S')}-{secrets.token_hex(2)}"


def build_report_draft(run: dict[str, Any]) -> str:
    c = run["counts"]
    sig = {"success": "🟢", "partial": "🟡", "failed": "🔴", "stopped": "⏸"}.get(run["result"], "")
    lines = [
        f"【報告案】{AGENT_ID} {AGENT_ROLE}・手動",
        f"{sig} 判定: {run['result']}" + (f"（{run['stop_reason']}）" if run.get("stop_reason") else ""),
        f"候補 {c['candidates']}件 ／ 確認 {c['examined']}件 ／ 繰越 {c['carried_over']}件",
        f"変化なし {c['skipped_unchanged']}件 ／ 313で残す済 {c['skipped_kept_313']}件 ／ 保留 {c['held']}件",
        f"仕分け ①{c['cat1']} ②{c['cat2']} ③{c['cat3']}（大規模 {c['large']}）／回答取込 {c['answered']}件",
        f"/313/bulk 待ち {c['queued']}件（313で質問中 {c['asked_313']}）／週次へ {c['handoff']}件",
    ]
    if run.get("errors"):
        lines.append(f"要確認 {len(run['errors'])}件（内部ログ参照）")
    return "\n".join(lines)


def _empty_counts() -> dict[str, int]:
    return {
        "active_tasks": 0,
        "candidates": 0,
        "examined": 0,
        "processed": 0,
        "skipped_unchanged": 0,
        "skipped_kept_313": 0,
        "held": 0,
        "carried_over": 0,
        "cat1": 0,
        "cat2": 0,
        "cat3": 0,
        "large": 0,
        "answered": 0,
        "rechecked": 0,
        "queued": 0,
        "asked_313": 0,
        "handoff": 0,
    }


def execute(
    paths: Paths,
    criteria_path: Path,
    env: dict[str, str],
    reader_factory: Callable[[str], Reader],
    opts: RunOptions,
    *,
    now_fn: Callable[[], datetime] = now_jst,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    started = now_fn()
    t0 = clock()
    run_id = new_run_id(started)
    run: dict[str, Any] = {
        "run_id": run_id,
        "agent_id": AGENT_ID,
        "phase": PHASE,
        "mode": "dry" if opts.dry_run else "live",
        "trigger": "manual",
        "started_at": started.isoformat(timespec="seconds"),
        "limits": {"max_tasks": opts.max_tasks, "max_minutes": opts.max_minutes, "comment_cap": opts.comment_cap},
        "checks": {},
        "basis": {},
        "counts": _empty_counts(),
        "tasks": [],
        "errors": [],
        "result": "failed",
        "stop_reason": "",
        "writes": {"todoist": 0, "slack": 0, "supabase": 0},  # Todoist は常に 0（Phase 3 まで書かない）
        "flags": {"publish": opts.publish and not opts.dry_run, "send_slack": opts.send_slack and not opts.dry_run},
    }
    lock_taken = False
    packet: list[dict[str, Any]] = []
    try:
        why = stop_switch_on(paths, env)  # 停止スイッチはロックより先に見る（ロックを残さない）
        if why:
            raise SafeStop("stop_switch", f"停止スイッチが有効（{why}）", result="stopped")
        acquire_lock(paths, run_id)
        lock_taken = True
        run["checks"]["lock"] = "acquired"
        reader, checks, user = preflight(
            paths, env, reader_factory, now=started, allow_313_window=opts.allow_313_window
        )
        run["checks"].update(checks)
        user_id = str(user.get("id"))

        basis = load_basis(paths, criteria_path)
        run["basis"] = {
            "criteria_file": criteria_path.name,
            "adopted_decision_ids": basis.adopted_ids,
            "proposed_rule_ids": [r.id for r in basis.rules if r.status != "adopted"],
            "ignored_rules": basis.ignored_rules,
            "keep_313": len(basis.judgments_313.get("keep") or {}),
            "history_tasks": len(basis.history.get("tasks") or {}),
            "first_run": basis.first_run,
        }
        if opts.owner_answers == "skip":
            run["basis"]["owner_answers"] = "skipped（明示）"
        else:
            if opts.sb is None:
                raise SafeStop("owner_answers_unavailable", "本人回答（owner_decisions）の読み口が無い。--owner-answers skip を明示しない限り止める")
            try:
                basis.owner_answers = ho.fetch_owner_answers(opts.sb, started)
            except Exception as e:  # noqa: BLE001
                raise SafeStop("owner_answers_unreadable", f"本人回答が読めない（{type(e).__name__}）。回答なしとは扱わない") from e
            run["basis"]["owner_answers"] = len(basis.owner_answers)

        today = started.date()
        try:
            active = paginate(reader, "/tasks")
        except SafeStop:
            raise
        except urllib.error.HTTPError as e:  # noqa: PERF203
            raise SafeStop("read_failed", f"タスク一覧の読取に失敗（HTTP {e.code}）。0件扱いにしない") from e
        except Exception as e:  # noqa: BLE001
            raise SafeStop("read_failed", f"タスク一覧の読取に失敗（{type(e).__name__}）。0件扱いにしない") from e
        run["counts"]["active_tasks"] = len(active)
        children: dict[str, list[str]] = {}
        for t in active:
            if t.get("parent_id"):
                children.setdefault(str(t["parent_id"]), []).append(str(t.get("id")))
        hist_tasks: dict[str, Any] = basis.history["tasks"]
        ranked = rank(candidate_filter(active, user_id, today), today, hist_tasks)
        run["counts"]["candidates"] = len(ranked)

        comment_reads = 0
        for pos, t in enumerate(ranked, 1):
            tid = str(t.get("id"))
            elapsed_min = (clock() - t0) / 60.0
            if run["counts"]["processed"] >= opts.max_tasks or comment_reads >= opts.comment_cap:
                run["counts"]["carried_over"] = len(ranked) - pos + 1
                break
            if elapsed_min >= opts.max_minutes:
                run["counts"]["carried_over"] = len(ranked) - pos + 1
                run["stop_reason"] = f"時間上限 {opts.max_minutes} 分（安全な区切りで止めた）"
                break
            entry: dict[str, Any] = {
                "task_id": tid,
                "rank": pos,
                "rank_key": list(rank_key(t, today, hist_tasks)[:3]),
                "processed_at": now_fn().isoformat(timespec="seconds"),
            }
            run["counts"]["examined"] += 1
            # 313 で本人が「残す」と答え、内容が変わっていない → 本人の確定判断を尊重して触らない
            if jd313.is_kept(basis.judgments_313, tid, jd313.fingerprint(t)):
                entry.update(status="skip_kept_313", skip_reason="313で本人が「残す」と回答・内容の変化なし")
                entry["next_recheck"] = NEXT_RECHECK
                run["counts"]["skipped_kept_313"] += 1
                run["tasks"].append(entry)
                _touch_history(hist_tasks, tid, run_id, started, None)
                continue
            prev = (hist_tasks.get(tid) or {}).get("snapshot")
            nc = note_count_of(t)
            comments: list[dict] | None = None
            if isinstance(prev, dict) and nc and prev.get("note_count") == nc and prev.get("comments"):
                # コメント数が前回と同じ → コメントは読まない（API を減らし、上限で下の段が後回しになるのを防ぐ）
                entry["comments_checked"] = "count_only"
            try:
                if "comments_checked" not in entry:
                    comment_reads += 1
                    comments = paginate(reader, f"/comments?task_id={urllib.parse.quote(tid)}", limit=100)
                    entry["comments_checked"] = "read"
            except Exception as e:  # noqa: BLE001
                code = f"HTTP {e.code}" if isinstance(e, urllib.error.HTTPError) else type(e).__name__
                entry.update(status="hold", skip_reason=f"コメントが読めず判断不能（{code}）。推測で処理済みにしない")
                entry["next_recheck"] = "次回の実行で読み直す"
                run["counts"]["held"] += 1
                run["errors"].append({"task_id": tid, "where": "comments", "error": code})
                run["tasks"].append(entry)
                continue
            snap = snapshot(
                t, comments, children, owner_answer_sig(tid, basis),
                comments_hash=str((prev or {}).get("comments") or "") if comments is None else "",
            )
            snap_id = _h(*[snap[k] for k in sorted(snap) if k not in HINT_KEYS])
            status, changed = detect_change(tid, snap, basis)
            row = hist_tasks.get(tid) or {}
            if status == "changed" and "owner_answer" in changed and basis.owner_answers.get(tid):
                status = "answered"  # 新しい本人回答。一緒に変わった期限などは回答の反映とみなし、すぐ聞き直さない
            elif status == "new" and basis.owner_answers.get(tid):
                rc0 = recheck_on_for(basis.owner_answers[tid], t, today)
                if rc0 and rc0 > today.isoformat():
                    status = "answered"  # 初めて見る件でも、最近の本人回答の待ち期間中なら聞かない
            elif status == "unchanged" and row.get("recheck_on") and today.isoformat() >= str(row["recheck_on"]):
                status, changed = "recheck", ["recheck_on"]
            entry["status"] = status
            entry["snapshot_id"] = snap_id
            if status == "answered":
                ans = basis.owner_answers[tid]
                rc = recheck_on_for(ans, t, today)
                entry.update(
                    answer={"action": ans.get("action"), "decided_at": ans.get("decided_at"), "decision_id": ans.get("decision_id")},
                    skip_reason="本人回答を判断履歴へ取り込み（今回は聞き直さない）",
                    next_recheck=(f"{rc} に再評価" if rc else "") + ("・" if rc else "") + NEXT_RECHECK,
                )
                run["counts"]["answered"] += 1
                run["tasks"].append(entry)
                _touch_history(hist_tasks, tid, run_id, started, {"snapshot": snap})
                hist_tasks[tid].update(queue_state="answered", owner_answer=ans, recheck_on=rc)
                continue
            if status == "recheck":
                run["counts"]["rechecked"] += 1
            if status == "unchanged":
                entry["skip_reason"] = "前回から変化なし（分類・実行・再質問・コメントを省略）"
                entry["next_recheck"] = NEXT_RECHECK
                run["counts"]["skipped_unchanged"] += 1
                run["tasks"].append(entry)
                _touch_history(hist_tasks, tid, run_id, started, {"snapshot": snap})
                continue
            if status == "hold":
                entry["skip_reason"] = "変化の有無を判断できない: " + "・".join(changed)
                entry["next_recheck"] = "記録を確かめてから再評価"
                run["counts"]["held"] += 1
                run["tasks"].append(entry)
                continue
            entry["changed_fields"] = changed
            cls = classify(t, basis.rules)
            cls = apply_ai_answer(cls, (opts.ai_answers or {}).get(tid), snap_id)
            cls.pop("blocked_by_adopted_2", None)
            entry.update(cls)
            entry["proposal"] = PROPOSAL_TEXT[cls["category"]]
            if cls.get("large"):
                entry["proposal"] += "／大規模: 既存タスクのまま週次へ（区分だけ記録）"
            entry["next_recheck"] = NEXT_RECHECK
            run["counts"]["processed"] += 1
            run["counts"][f"cat{cls['category']}"] += 1
            run["counts"]["large"] += int(bool(cls.get("large")))
            run["tasks"].append(entry)
            _touch_history(hist_tasks, tid, run_id, started, {"snapshot": snap, "category": cls["category"]})
            hist_tasks[tid].update(
                queue_state="pending" if cls["category"] == "2" else None,
                last_reason=str(cls.get("reason") or "")[:200],
                last_large=bool(cls.get("large")),
                recheck_on="",
            )
            if opts.emit_packet:
                if comments is None:
                    try:
                        comments = paginate(reader, f"/comments?task_id={urllib.parse.quote(tid)}", limit=100)
                    except Exception:  # noqa: BLE001
                        comments = []
                packet.append(_packet_row(t, comments, snap_id, cls))

        active_by_id = {str(t.get("id")): t for t in active}
        _route_and_notify(run, paths, opts, hist_tasks, active_by_id, started)
        run["result"] = "partial" if run["errors"] else "success"
    except SafeStop as s:
        run["result"] = s.result
        run["stop_reason"] = s.reason
        run["stop_code"] = s.code  # 失敗・停止の回は履歴を書かない（下の保存で result を見る）
    finally:
        run["finished_at"] = now_fn().isoformat(timespec="seconds")
        run["report_draft"] = build_report_draft(run)
        # 保存（失敗は正常完了にしない）
        try:
            if run["result"] in ("success", "partial") and not opts.dry_run:
                hist_doc = {"version": 1, "updated_at": run["finished_at"], "last_run_id": run_id, "tasks": hist_tasks}
                atomic_write_json(paths.history, hist_doc)
            if opts.emit_packet and packet:
                atomic_write_json(paths.packet, {"run_id": run_id, "note": _PACKET_NOTE, "tasks": packet})
            run["hub_report_draft"] = ho.hub_report_text(run)
            _save_draft(paths, run_id, "hub", run["hub_report_draft"])
            atomic_write_json(paths.runs / f"{run_id}.json", run)
            run["saved"] = True
        except Exception as e:  # noqa: BLE001
            run["saved"] = False
            run["result"] = "failed"
            run["stop_reason"] = (run.get("stop_reason") or "") + f"／内部ログの保存に失敗（{type(e).__name__}）"
        # 終了報告（#ai-hub）は内部ログを保存できた後だけ。313 は #report なので重ならない
        if opts.send_slack and not opts.dry_run and run.get("saved") and run["result"] != "stopped":
            poster = opts.poster or _post_default
            try:
                ok = poster("hub", run["hub_report_draft"])
            except Exception:  # noqa: BLE001
                ok = False
            run.setdefault("notify", {})["hub_sent"] = ok
            if ok:
                run["writes"]["slack"] += 1
            try:
                atomic_write_json(paths.runs / f"{run_id}.json", run)
            except Exception:  # noqa: BLE001
                pass
        if lock_taken:
            release_lock(paths, run_id)
    return run


def _post_default(channel: str, text: str) -> bool:
    """既存の Webhook 投稿（jarvis_slack_webhook_post.py）。--send-slack の時だけ呼ばれる。"""
    import subprocess  # noqa: PLC0415

    r = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "jarvis_slack_webhook_post.py"), "--channel", channel, "--text", text, "--no-fb-footer"],
        capture_output=True, text=True, timeout=60,
    )
    return r.returncode == 0


def _route_and_notify(
    run: dict[str, Any], paths: Paths, opts: RunOptions, hist_tasks: dict[str, Any],
    active_by_id: dict[str, dict], started: datetime,
) -> None:
    """② → /313/bulk の待ち、③ → 週次の受け渡し、通知・報告の案。外へ出すのはフラグの時だけ。"""
    live = not opts.dry_run
    asked = ho.asked_by_313(paths.cleanup_313, started)
    if asked is None:
        # 313 の質問状況が分からない時は二重質問を避けて ② を載せない
        run["errors"].append({"where": "cleanup_313", "error": "313 片付けの状態が読めないので②を /313/bulk に載せない"})
        cards, gone = [], {"gone": 0, "asked_313": 0}
    else:
        cards, gone = ho.build_bulk_cards(hist_tasks, active_by_id, asked)
    handoff = ho.build_weekly_handoff(hist_tasks, active_by_id)
    run["counts"]["queued"] = len(cards)
    run["counts"]["asked_313"] = gone["asked_313"]
    run["counts"]["handoff"] = len(handoff)
    published = False
    if opts.publish and live:
        if opts.sb is None:
            run["errors"].append({"where": "publish", "error": "Supabase の読み口が無いので載せなかった"})
        else:
            try:
                ho.publish(opts.sb, ho.QUEUE_KEY, ho.queue_doc(run["run_id"], started, cards, published=True), started)
                ho.publish(opts.sb, ho.HANDOFF_KEY, ho.handoff_doc(run["run_id"], started, handoff, published=True), started)
                run["writes"]["supabase"] += 2
                published = True
            except Exception as e:  # noqa: BLE001
                run["errors"].append({"where": "publish", "error": type(e).__name__})
    run["published"] = published
    # 手元の写し（題を含むので非公開の置き場だけ）。preview は毎回、本体は sync_meta に載せた回だけ書く
    # → 313 片付けは本体（= 画面に出ている件）だけを外す
    atomic_write_json(paths.root / "bulk_queue.preview.json", ho.queue_doc(run["run_id"], started, cards, published=False))
    atomic_write_json(paths.root / "weekly_handoff.preview.json", ho.handoff_doc(run["run_id"], started, handoff, published=False))
    if published:
        atomic_write_json(paths.bulk_queue, ho.queue_doc(run["run_id"], started, cards, published=True))
        atomic_write_json(paths.weekly_handoff, ho.handoff_doc(run["run_id"], started, handoff, published=True))
    # 通知の案: 新しく待ちに入った件だけ（前に知らせた件は出さない）。313 の質問中は cards に入っていない
    new_cards = [c for c in cards if not (hist_tasks.get(c["id"]) or {}).get("notified_at")]
    url = _bulk_url(started)
    consult = ho.consult_text(new_cards, len(cards), url) if new_cards else ""
    run["notify"] = {"consult_new": len(new_cards), "consult_sent": False, "hub_sent": False}
    if consult:
        _save_draft(paths, run["run_id"], "consult", consult)
    if opts.send_slack and live:
        poster = opts.poster or _post_default
        if consult and published:  # 画面に載っていないのに「開いて」と送らない
            if poster("consult", consult):
                run["writes"]["slack"] += 1
                run["notify"]["consult_sent"] = True
                for c in new_cards:
                    hist_tasks[c["id"]]["notified_at"] = started.isoformat(timespec="seconds")
            else:
                run["errors"].append({"where": "slack_consult", "error": "送信失敗"})
        elif consult:
            run["notify"]["consult_skip"] = "/313/bulk に載っていないので通知しない（--publish が要る）"


def _bulk_url(now: datetime) -> str:
    try:
        from jarvis_todoist_312_collect import nody_url  # noqa: PLC0415

        return nody_url(ho.BULK_PATH, now)
    except Exception:  # noqa: BLE001
        return "https://jarvis-loopware.vercel.app" + ho.BULK_PATH


def _save_draft(paths: Paths, run_id: str, kind: str, text: str) -> None:
    paths.drafts.mkdir(parents=True, exist_ok=True)
    (paths.drafts / f"{run_id}_{kind}.txt").write_text(text + "\n", encoding="utf-8")


_PACKET_NOTE = (
    "AI分類用。tasks[].task_id ごとに {category: '1'|'2'|'3', reason: '…', snapshot_id: そのまま, large: bool} を"
    " answers.json（{task_id: {...}}）に書き、run --ai-answers で渡す。迷ったら '2'。この材料は非公開の置き場だけに置く"
)


def _packet_row(t: dict, comments: list[dict], snap_id: str, cls: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": str(t.get("id")),
        "snapshot_id": snap_id,
        "title": str(t.get("content") or ""),
        "description": str(t.get("description") or "")[:1500],
        "labels": [str(x) for x in (t.get("labels") or [])],
        "due": (t.get("due") or {}).get("date"),
        "deadline": (t.get("deadline") or {}).get("date"),
        "priority": t.get("priority"),
        "recent_comments": [str(c.get("content") or "")[:400] for c in comments[-5:]],
        "rule_result": {k: cls.get(k) for k in ("category", "reason", "rule_ids", "large")},
    }


def _touch_history(
    hist_tasks: dict[str, Any], tid: str, run_id: str, started: datetime, upd: dict[str, Any] | None
) -> None:
    row = hist_tasks.setdefault(tid, {})
    row["last_examined"] = started.date().isoformat()
    row["last_run_id"] = run_id
    if upd:
        row["snapshot"] = upd["snapshot"]
        if "category" in upd:  # 分類した回だけ。変化なしの回は手がかり（コメント数）だけ更新する
            row["last_category"] = upd["category"]
            row["last_evaluated"] = started.isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _paths_from(args: argparse.Namespace) -> Paths:
    return Paths(Path(args.state_dir).expanduser() if args.state_dir else REPO / ".jarvis_state")


def cmd_run(args: argparse.Namespace) -> int:
    paths = _paths_from(args)
    answers = None
    if args.ai_answers:
        try:
            answers = json.loads(Path(args.ai_answers).read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"❌ AI回答ファイルが読めない（{type(e).__name__}）", file=sys.stderr)
            return 2
    opts = RunOptions(
        dry_run=args.dry_run,
        max_tasks=max(1, min(args.max_tasks, MAX_TASKS)),
        max_minutes=max(1, min(args.max_minutes, MAX_MINUTES)),
        emit_packet=args.emit_packet,
        ai_answers=answers if isinstance(answers, dict) else None,
        allow_313_window=args.allow_313_window,
        owner_answers=args.owner_answers,
        publish=args.publish,
        send_slack=args.send_slack,
        sb=_default_sb(),
    )
    run = execute(paths, Path(args.criteria), dict(os.environ), TodoistReader, opts)
    print(run["report_draft"])
    print(f"📎 run_id={run['run_id']} mode={run['mode']} saved={run.get('saved')} log=todoist_318/runs/{run['run_id']}.json")
    return {"success": 0, "stopped": 0, "partial": 1}.get(run["result"], 2)


def _default_sb() -> Callable[..., Any] | None:
    """Supabase の読み書き口（312 の部品を再利用）。鍵が無ければ None（本人回答が要る時は安全停止になる）。"""
    if not (os.environ.get("JARVIS_SUPABASE_URL") and os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")):
        return None
    from jarvis_todoist_312_collect import sb  # noqa: PLC0415

    return sb


def cmd_status(args: argparse.Namespace) -> int:
    paths = _paths_from(args)
    runs = sorted(paths.runs.glob("*.json")) if paths.runs.is_dir() else []
    print(f"lock={'あり' if paths.lock.exists() else 'なし'} stop={'ON' if paths.stop.exists() else 'off'} runs={len(runs)}")
    if runs:
        last = json.loads(runs[-1].read_text(encoding="utf-8"))
        print(last.get("report_draft", ""))
    return 0


def cmd_unlock(args: argparse.Namespace) -> int:
    paths = _paths_from(args)
    if not args.force:
        print("--force を付けて実行（実行中でないことを確かめてから）", file=sys.stderr)
        return 2
    paths.lock.unlink(missing_ok=True)
    print("ロックを外した")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--state-dir", default=None, help="既定 <repo>/.jarvis_state（worktree から本番 state を読む時に指定）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--dry-run", action="store_true", help="履歴を更新しない（内部ログは残す）")
    r.add_argument("--max-tasks", type=int, default=MAX_TASKS)
    r.add_argument("--max-minutes", type=int, default=MAX_MINUTES)
    r.add_argument("--criteria", default=str(REPO / "config" / "todoist_318_criteria.yaml"))
    r.add_argument("--emit-packet", action="store_true", help="AI分類用の材料を packet.json に書く")
    r.add_argument("--ai-answers", default=None, help="Claude Code が書いた分類（answers.json）")
    r.add_argument("--allow-313-window", action="store_true", help="10:15–11:30 でも動かす（313 と重ならないと確かめた時だけ）")
    r.add_argument("--owner-answers", choices=["supabase", "skip"], default="supabase",
                   help="本人回答（owner_decisions）を読む。skip は明示した時だけ（読めない時に黙って skip しない）")
    r.add_argument("--publish", action="store_true", help="②を /313/bulk、③を週次へ載せる（Supabase sync_meta に書く。既定オフ）")
    r.add_argument("--send-slack", action="store_true", help="#consult 通知と #ai-hub 報告を送る（既定オフ。--publish が無いと #consult は送らない）")
    r.set_defaults(func=cmd_run)
    s = sub.add_parser("status")
    s.set_defaults(func=cmd_status)
    u = sub.add_parser("unlock")
    u.add_argument("--force", action="store_true")
    u.set_defaults(func=cmd_unlock)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
