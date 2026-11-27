#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""313 週の整理（金曜の夜・週1回）— A「済みました」を先に閉じ、B「やめてもいいのでは」を本人に選んでもらう.

松野さん了承 2026-11-24（Orca 項目50）。毎晩の期日ずらし（片付け 3択）はやめ、期日は「今週の9件」で決める。
313 の仕事はこの2つだけ:

- A 済みました … 説明・コメントに貼られた PR・Issue・別タスクが**すべて**済んでいて、その完了がタスクを作った後なら、
  313 が先に閉じる（完了。削除しない）。根拠1行＋リンクを Todoist コメントに残し、閉じた件を記録する。
  7日間は `--undo` で戻せる。根拠が弱い件・後追いの確認やお金の件は閉じずに B で「済み？」と聞く。
- B やめてもいいのでは … 3週間以上 題・説明・コメントが動いていない件（今週の9件・318 の待ち・「残す」4週内は除く）。
  動いていない理由を1行付けて /313/bulk に載せる（sync_meta.todoist_313_weekly_queue → cleanup_bulk が画面の材料に混ぜる）。
  本人が 済み／やめる／残す を選ぶと cleanup_bulk の reflect が閉じる（やめるも完了扱い。削除しない）。

閉じない: 繰り返しタスク・318 が聞いている件・基準（config）が読めない時。Slack は #consult に1通だけ。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_313_weekly.py              # 下見（何も書かない）
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_313_weekly.py --apply      # 本番（金曜 20:00 の runner）
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_313_weekly.py --undo list  # 戻せる件
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_313_weekly.py --undo 2     # 一覧の #2 を戻す（all で全部）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

import jarvis_todoist_313_http as http313  # noqa: E402

JST = timezone(timedelta(hours=9))
CONFIG_PATH = REPO / "config" / "todoist_313_weekly.yaml"
STATE_PATH = REPO / ".jarvis_state" / "todoist_313_weekly.json"  # 非公開（題は書かない）
QUEUE_KEY = "todoist_313_weekly_queue"
QUEUE_318_KEY = "todoist_318_bulk_queue"
SURFACE = "todoist_313"
BULK_PATH = "/313/bulk"
HISTORY_DAYS = 30  # 閉じた記録を state に残す日数

PR_RE = re.compile(r"https://github\.com/([\w.-]+)/([\w.-]+)/pull/(\d+)")
ISSUE_RE = re.compile(r"https://github\.com/([\w.-]+)/([\w.-]+)/issues/(\d+)")
TASK_RE = re.compile(r"https://(?:app\.)?todoist\.com/(?:app/task/(?:[\w-]*-)?([0-9A-Za-z]+)|showTask\?id=([0-9A-Za-z]+))")
KIND_TEXT = {"pr_merged": "PR がマージ済み", "issue_closed": "Issue が完了で閉じている", "task_done": "関係タスクが完了"}


class ConfigError(ValueError):
    pass


class ReadError(RuntimeError):
    """必要な材料が読めない（基準なし・0件とは扱わない）。"""


# ---------------------------------------------------------------------------
# 基準
# ---------------------------------------------------------------------------


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    try:
        import yaml  # type: ignore  # noqa: PLC0415
    except ImportError as e:
        raise ConfigError("PyYAML が無い") from e
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ConfigError(f"{path.name} が無い") from e
    except Exception as e:  # noqa: BLE001
        raise ConfigError(f"{path.name} が壊れている（{type(e).__name__}）") from e
    if not isinstance(data, dict) or not isinstance(data.get("done"), dict) or not isinstance(data.get("stale"), dict):
        raise ConfigError("done / stale が無い")
    d, s = data["done"], data["stale"]
    try:
        cfg = {
            "strong_kinds": {str(x) for x in (d.get("strong_kinds") or [])},
            "require_after_added": bool(d.get("require_after_added", True)),
            "no_comment_after": bool(d.get("no_comment_after", True)),
            "hold_words": [str(x) for x in (d.get("hold_words") or [])],
            "hold_labels": {str(x) for x in (d.get("hold_labels") or [])},
            "agent_comment_re": re.compile(str(d.get("agent_comment_re") or r"^【")),
            "agent_done_re": re.compile(str(d.get("agent_done_re") or r"(完了しました)")),
            "max_close": int(d.get("max_close", 15)),
            "undo_days": int(d.get("undo_days", 7)),
            "idle_days": int(s.get("idle_days", 21)),
            "skip_future_due": bool(s.get("skip_future_due", True)),
            "keep_days": int(s.get("keep_days", 28)),
            "max_cards": int(s.get("max_cards", 20)),
            "weekly_pick_lookback_days": int(data.get("weekly_pick_lookback_days", 14)),
            "queue_318_stale_days": int(data.get("queue_318_stale_days", 3)),
        }
    except (TypeError, ValueError, re.error) as e:
        raise ConfigError(f"値の形が想定外（{e}）") from e
    unknown = cfg["strong_kinds"] - set(KIND_TEXT)
    if unknown:
        raise ConfigError(f"strong_kinds に知らない種類: {sorted(unknown)}")
    if cfg["idle_days"] < 7 or cfg["undo_days"] < 1:
        raise ConfigError("idle_days は7以上・undo_days は1以上")
    return cfg


# ---------------------------------------------------------------------------
# 純粋な判定（テスト対象）
# ---------------------------------------------------------------------------


def _dt(s: Any) -> datetime | None:
    if not s:
        return None
    try:
        v = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        try:
            v = datetime.combine(date.fromisoformat(str(s)[:10]), datetime.min.time())
        except ValueError:
            return None
    return v if v.tzinfo else v.replace(tzinfo=JST)


def extract_links(text: str) -> list[tuple[str, str, str]]:
    """本文から (種類, キー, URL)。種類は pr / issue / task。重複は1つ。"""
    out: dict[tuple[str, str], str] = {}
    for m in PR_RE.finditer(text or ""):
        out[("pr", f"{m.group(1)}/{m.group(2)}#{m.group(3)}")] = m.group(0)
    for m in ISSUE_RE.finditer(text or ""):
        out[("issue", f"{m.group(1)}/{m.group(2)}#{m.group(3)}")] = m.group(0)
    for m in TASK_RE.finditer(text or ""):
        tid = m.group(1) or m.group(2)
        out[("task", tid)] = m.group(0)
    return [(k, key, url) for (k, key), url in out.items()]


def is_recurring(task: dict[str, Any]) -> bool:
    due = task.get("due") or {}
    return bool(isinstance(due, dict) and due.get("is_recurring"))


def last_activity(task: dict[str, Any], comments: list[dict[str, Any]]) -> datetime | None:
    cands = [_dt(task.get("updated_at")), _dt(task.get("added_at"))]
    cands += [_dt(c.get("posted_at")) for c in comments]
    cands = [c for c in cands if c]
    return max(cands) if cands else None


def judge_done(
    task: dict[str, Any],
    comments: list[dict[str, Any]],
    status: dict[tuple[str, str], dict[str, Any]],
    cfg: dict[str, Any],
) -> dict[str, Any] | None:
    """済みの判定。強い根拠なら level=strong（A）、弱い・保留語があれば level=weak（B で「済み？」）、無ければ None。

    status は (種類, キー) → {"done": True/False/None, "at": ISO, "url": …}（None は読めなかった）。
    """
    blob = "\n".join([str(task.get("description") or "")] + [str(c.get("content") or "") for c in comments])
    links = extract_links(blob)
    ordered = sorted(comments, key=lambda c: str(c.get("posted_at") or ""))
    last_text = str(ordered[-1].get("content") or "") if ordered else ""
    title_blob = f"{task.get('content') or ''}\n{task.get('description') or ''}\n{last_text}"
    added = _dt(task.get("added_at"))
    kind_of = {"pr": "pr_merged", "issue": "issue_closed", "task": "task_done"}
    # PR・Issue があればそれだけで見る（元タスク・関連タスクのリンクは背景として貼られることが多い）
    gh_links = [x for x in links if x[0] in ("pr", "issue")]
    links = gh_links or links
    if links:
        rows = [(kind_of[k], status.get((k, key)) or {"done": None}, url) for k, key, url in links]
        all_done = all(r[1].get("done") is True for r in rows)
        if all_done:
            last = max(rows, key=lambda r: str(r[1].get("at") or ""))
            kind, st, url = last
            reasons: list[str] = []
            if not all(r[0] in cfg["strong_kinds"] for r in rows):
                reasons.append("根拠の種類が弱い")
            at = _dt(st.get("at"))
            if cfg["require_after_added"] and added and (not at or at < added):
                reasons.append("タスクより前に済んだ根拠")
            if cfg["no_comment_after"] and at:
                later = [c for c in ordered if (_dt(c.get("posted_at")) or at) > at]
                if any(not cfg["agent_done_re"].search(str(c.get("content") or "")) for c in later):
                    reasons.append("根拠の後にコメントあり")
            hold = next((w for w in cfg["hold_words"] if w and w in title_blob), "")
            if hold:
                reasons.append(f"「{hold}」があるので本人に")
            if set(str(x) for x in (task.get("labels") or [])) & cfg["hold_labels"]:
                reasons.append("保留ラベル")
            n = len(rows)
            line = KIND_TEXT[kind] + (f"（{n}件すべて）" if n > 1 else "")
            return {
                "level": "weak" if reasons else "strong",
                "kind": kind,
                "line": line,
                "url": url,
                "at": st.get("at"),
                "hold": reasons,
            }
    # エージェントの「済み」コメント（最後のコメントがそれで、その後に人が書いていない）
    if ordered:
        last_c = ordered[-1]
        text = last_text
        if cfg["agent_comment_re"].search(text) and cfg["agent_done_re"].search(text):
            return {"level": "weak", "kind": "agent_comment", "line": "エージェントのコメントに「済み」とある",
                    "url": f"https://app.todoist.com/app/task/{task.get('id')}", "at": last_c.get("posted_at"), "hold": []}
    return None


def stale_reason(task: dict[str, Any], last: datetime | None, now: datetime, cfg: dict[str, Any]) -> str | None:
    """B に出す理由1行。出さないなら None。"""
    if not last:
        return None
    idle = (now - last).days
    if idle < cfg["idle_days"]:
        return None
    due_s = ((task.get("due") or {}).get("date") or "") if isinstance(task.get("due"), dict) else ""
    today = now.astimezone(JST).date()
    try:
        due = date.fromisoformat(due_s[:10]) if due_s else None
    except ValueError:
        due = None
    if due and due >= today and cfg["skip_future_due"]:
        return None
    if due:
        return f"{idle}日 動きなし・期日を{(today - due).days}日過ぎ"
    return f"{idle}日 動きなし・期日なし"


def plan(
    tasks: list[dict[str, Any]],
    comments_by_id: dict[str, list[dict[str, Any]]],
    status: dict[tuple[str, str], dict[str, Any]],
    *,
    cfg: dict[str, Any],
    now: datetime,
    exclude_ids: set[str],
    week9_ids: set[str],
    kept_ids: set[str],
) -> dict[str, Any]:
    """A（閉じる）と B（選んでもらう）の案。副作用なし。"""
    a: list[dict[str, Any]] = []
    b: list[dict[str, Any]] = []
    skipped = {"recurring": 0, "by_318": 0, "week9": 0, "kept": 0, "subtask": 0}
    # 親を閉じると未完了のサブタスクも閉じてしまうので、子が残る件は A にしない
    parents = {str(t.get("parent_id")) for t in tasks if t.get("parent_id") and not t.get("checked")}
    for t in tasks:
        tid = str(t.get("id") or "")
        if not tid or t.get("checked") or t.get("is_deleted"):
            continue
        if is_recurring(t):
            skipped["recurring"] += 1
            continue
        if tid in exclude_ids:
            skipped["by_318"] += 1
            continue
        comments = comments_by_id.get(tid) or []
        done = judge_done(t, comments, status, cfg)
        if done and done["level"] == "strong" and tid in parents:
            done = {**done, "level": "weak", "hold": [*done["hold"], "サブタスクが残っている"]}
        if done and done["level"] == "strong":
            a.append({"task": t, "done": done})
            continue
        if tid in week9_ids:
            skipped["week9"] += 1
            continue
        if tid in kept_ids:
            skipped["kept"] += 1
            continue
        last = last_activity(t, comments)
        reason = stale_reason(t, last, now, cfg)
        if done:  # 弱い根拠 → 「済み？」として聞く（動きの日数に関係なく）
            why = f"済み？ {done['line']}" + (f"（{'・'.join(done['hold'][:2])}）" if done["hold"] else "")
            b.append({"task": t, "suggest": "close", "why": why, "evidence_url": done["url"], "idle": (now - last).days if last else 0})
        elif reason:
            if t.get("parent_id"):
                skipped["subtask"] += 1  # 親で聞く
                continue
            b.append({"task": t, "suggest": "drop", "why": reason, "evidence_url": None, "idle": (now - last).days if last else 0})
    a.sort(key=lambda x: str(x["done"].get("at") or ""))
    carried_a = max(0, len(a) - cfg["max_close"])
    a = a[: cfg["max_close"]]
    b.sort(key=lambda x: (x["suggest"] != "close", -x["idle"]))
    carried_b = max(0, len(b) - cfg["max_cards"])
    b = b[: cfg["max_cards"]]
    return {"a": a, "b": b, "carried_a": carried_a, "carried_b": carried_b, "skipped": skipped}


def b_card(row: dict[str, Any], now: datetime) -> dict[str, Any]:
    """/313/bulk の CleanupCard と同じ形（origin=313）。"""
    t = row["task"]
    due = ((t.get("due") or {}).get("date") or None) if isinstance(t.get("due"), dict) else None
    added = str(t.get("added_at") or "")[:10]
    try:
        age = (now.date() - date.fromisoformat(added)).days if added else None
    except ValueError:
        age = None
    return {
        "id": str(t["id"]),
        "title": str(t.get("content") or ""),
        "sender": "",
        "subject": "",
        "mail_date": "",
        "summary": "",
        "gmail_url": "",
        "due": (due or None) and str(due)[:10],
        "added_at": added,
        "age_days": age,
        "suggest": row["suggest"],
        "why": row["why"],
        "priority": t.get("priority"),
        "origin": "313",
        "evidence_url": row.get("evidence_url"),
    }


def close_comment(done: dict[str, Any], author: str, undo_days: int) -> str:
    return (
        f"【{author}】タスク完了したよ（313 週の整理・済みました）\n"
        f"根拠: {done['line']}\n"
        f"アウトプット:\n- [根拠]({done['url']})\n"
        f"違ったら {undo_days} 日以内に戻せます（Todoist の完了済みから戻す／"
        f"`jarvis_todoist_313_weekly.py --undo list`）"
    )


def slack_text(run: dict[str, Any], a_rows: list[dict[str, Any]], b_cards: list[dict[str, Any]], url: str) -> str:
    c = run["counts"]
    lines = [
        "【相談】313 週の整理",
        f"✅ 済みました {c['closed']}件（閉じました・{run['undo_days']}日は戻せます）",
        f"🗑 やめる提案 {c['b_published']}件",
        "",
    ]
    for r in a_rows[:5]:
        t, d = r["task"], r["done"]
        lines.append(f"・{str(t.get('content') or '')[:36]}")
        lines.append(f"　{d['line']}｜<{d['url']}|根拠>")
    if len(a_rows) > 5:
        lines.append(f"ほか {len(a_rows) - 5}件")
    if c.get("close_failed"):
        lines.append(f"⚠ 閉じられなかった {c['close_failed']}件（次の金曜にもう一度）")
    if run.get("b_error"):
        lines.append(f"⚠ やめる提案は載せていません（{run['b_error']}）")
    lines += [
        "",
        f"<{url}|済み・やめる・残すを選ぶ（/313/bulk）>" if c["b_published"] else "選ぶものはありません",
        "",
        "次: 人判断のみ（やめる提案）",
        "担当メモ: やめる＝完了扱い（削除しない）。残すは4週出しません",
        "橋渡し: 戻すときは Todoist の完了済みから戻す／`--undo list`",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 外部 API
# ---------------------------------------------------------------------------


def _todoist_token() -> str:
    return (os.environ.get("TODOIST_API_TOKEN_OWNER") or os.environ.get("TODOIST_API_TOKEN") or "").strip()


def todoist(method: str, path: str, body: dict | None = None) -> Any:
    return http313.request(method, path, _todoist_token(), body)


def active_tasks() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor = ""
    for _ in range(20):
        d = todoist("GET", "/tasks?limit=200" + (f"&cursor={urllib.parse.quote(cursor)}" if cursor else ""))
        if isinstance(d, list):
            return out + d
        out.extend(d.get("results") or [])
        cursor = str(d.get("next_cursor") or "")
        if not cursor:
            return out
    raise ReadError("Todoist の一覧が 20 ページを超えた")


def task_comments(tid: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor = ""
    for _ in range(5):
        d = todoist("GET", f"/comments?task_id={tid}&limit=100" + (f"&cursor={urllib.parse.quote(cursor)}" if cursor else ""))
        if isinstance(d, list):
            return out + d
        out.extend(d.get("results") or [])
        cursor = str(d.get("next_cursor") or "")
        if not cursor:
            break
    return out


def _github_token() -> str:
    tok = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if tok:
        return tok
    try:
        r = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


def github(path: str, token: str) -> dict[str, Any]:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "jarvis-313-weekly"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request("https://api.github.com" + path, headers=h)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def resolve_links(keys: set[tuple[str, str]], *, gh_token: str, fetch_task: Callable[[str], Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """各リンクの済み状況。読めないものは done=None（強い根拠にしない）。"""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for kind, key in sorted(keys):
        try:
            if kind in ("pr", "issue"):
                repo, num = key.split("#")
                if kind == "pr":
                    d = github(f"/repos/{repo}/pulls/{num}", gh_token)
                    out[(kind, key)] = {"done": bool(d.get("merged_at")), "at": d.get("merged_at")}
                else:
                    d = github(f"/repos/{repo}/issues/{num}", gh_token)
                    ok = d.get("state") == "closed" and d.get("state_reason") in (None, "completed") and not d.get("pull_request")
                    out[(kind, key)] = {"done": ok, "at": d.get("closed_at")}
            else:
                d = fetch_task(key) or {}
                out[(kind, key)] = {"done": bool(d.get("checked")), "at": d.get("completed_at")}
        except urllib.error.HTTPError as e:
            out[(kind, key)] = {"done": None, "error": f"HTTP {e.code}"}
        except Exception as e:  # noqa: BLE001
            out[(kind, key)] = {"done": None, "error": type(e).__name__}
    return out


def _sb():
    import jarvis_todoist_312_collect as c  # noqa: PLC0415

    return c.sb


def week9_ids(sb, now: datetime, days: int) -> set[str]:
    """今週の9件（weekly_pick の確定 set_due）。読めなければ ReadError。"""
    since = (now - timedelta(days=days)).isoformat()
    try:
        rows = sb("owner_decisions", params={
            "select": "decided_at,payload", "surface": "eq.weekly_pick", "action": "eq.commit",
            "decided_at": f"gte.{since}", "order": "decided_at.desc", "limit": "5",
        }) or []
    except Exception as e:  # noqa: BLE001
        raise ReadError(f"今週の9件が読めない（{type(e).__name__}）") from e
    ids: set[str] = set()
    for r in rows:
        for x in ((r.get("payload") or {}).get("plan") or {}).get("set_due") or []:
            if isinstance(x, dict) and x.get("id"):
                ids.add(str(x["id"]))
    return ids


def kept_from_rows(rows: list[dict[str, Any]]) -> set[str]:
    """「残す／先送り」を選んだ件。どの画面から選んでも数える（313 の origin 問わず・ふるい分けの keep も）。"""
    out: set[str] = set()
    for r in rows:
        surface, action = str(r.get("surface") or ""), str(r.get("action") or "")
        if (surface == SURFACE and action == "defer") or (surface == "todoist_triage" and action == "keep"):
            out.add(str(r.get("target_id") or ""))
    out.discard("")
    return out


def kept_ids(sb, now: datetime, days: int) -> set[str]:
    """「残す／先送り」を選んだ件（keep_days 以内・どの画面からでも）。読めなければ ReadError。"""
    since = (now - timedelta(days=days)).isoformat()
    try:
        rows = sb("owner_decisions", params={
            "select": "target_id,surface,action", "target_type": "eq.todoist_task", "decided_at": f"gte.{since}",
            "or": f"(and(surface.eq.{SURFACE},action.eq.defer),and(surface.eq.todoist_triage,action.eq.keep))",
            "limit": "2000",
        }) or []
    except Exception as e:  # noqa: BLE001
        raise ReadError(f"「残す」の記録が読めない（{type(e).__name__}）") from e
    return kept_from_rows(rows)


def queue_318_ids(sb, now: datetime, stale_days: int) -> set[str]:
    """318 が /313/bulk に載せている件。読めなければ ReadError（無い・古いは空）。"""
    try:
        rows = sb("sync_meta", params={"select": "value", "key": f"eq.{QUEUE_318_KEY}", "limit": "1"}) or []
    except Exception as e:  # noqa: BLE001
        raise ReadError(f"318 の待ちが読めない（{type(e).__name__}）") from e
    if not rows:
        return set()
    v = rows[0].get("value")
    try:
        doc = json.loads(v) if isinstance(v, str) else (v or {})
    except ValueError as e:
        raise ReadError("318 の待ちが壊れている") from e
    at = _dt(doc.get("generated_at"))
    if not doc.get("published") or not at or now - at > timedelta(days=stale_days):
        return set()
    return {str(c.get("id")) for c in (doc.get("cards") or []) if isinstance(c, dict) and c.get("id")}


def publish_queue(sb, doc: dict[str, Any]) -> None:
    sb("sync_meta", params={"on_conflict": "key"}, method="POST", prefer="resolution=merge-duplicates,return=minimal", body={
        "key": QUEUE_KEY, "value": json.dumps(doc, ensure_ascii=False), "updated_at": datetime.now(JST).isoformat(),
    })


def log_decision(sb, *, action: str, tid: str, subject: str, payload: dict[str, Any], idem: str) -> None:
    from jarvis_owner_decision_log import contract_row  # noqa: PLC0415

    try:
        sb("owner_decisions", method="POST", prefer="return=minimal", body=contract_row(
            surface=SURFACE, action=action, source="script_todoist_313_weekly", target_type="todoist_task",
            target_id=tid, employee="313", subject=subject[:500], payload=payload, idem_key=idem,
        ))
    except Exception as e:  # noqa: BLE001
        print(f"  owner_decisions soft-fail: {type(e).__name__}", file=sys.stderr)


def post_slack(text: str, *, signal: str) -> bool:
    r = subprocess.run(
        [sys.executable, str(HERE / "jarvis_slack_webhook_post.py"), "--channel", "consult", "--text", text,
         "--no-fb-footer", "--signal", signal, "--username", "313 タスク処置"],
        capture_output=True, text=True,
    )
    print(r.stdout.strip() or r.stderr.strip())
    return r.returncode == 0


# ---------------------------------------------------------------------------
# 状態（非公開・題は書かない）
# ---------------------------------------------------------------------------


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            d.setdefault("closed", [])
            return d
    except Exception:  # noqa: BLE001
        pass
    return {"closed": []}


def save_state(d: dict[str, Any], path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def undoable(state: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    out = []
    for r in state.get("closed") or []:
        until = _dt(r.get("undo_until"))
        if r.get("undone_at") or not until or until < now:
            continue
        out.append(r)
    return out


# ---------------------------------------------------------------------------
# 実行
# ---------------------------------------------------------------------------


def run(*, apply: bool, author: str, now: datetime, notify: bool = True) -> int:
    try:
        cfg = load_config()
    except ConfigError as e:
        print(f"❌ 313 週の整理: 基準が読めないので止めます（{e}）", file=sys.stderr)
        return 2
    run_id = f"t313w-{now:%Y%m%d-%H%M}"
    counts = {"tasks": 0, "a": 0, "closed": 0, "close_failed": 0, "b": 0, "b_published": 0, "carried_a": 0, "carried_b": 0}
    result: dict[str, Any] = {"run_id": run_id, "at": now.isoformat(timespec="seconds"), "apply": apply,
                              "undo_days": cfg["undo_days"], "counts": counts, "errors": []}
    try:
        tasks = active_tasks()
    except Exception as e:  # noqa: BLE001
        print(f"❌ Todoist が読めない（{type(e).__name__}）", file=sys.stderr)
        return 1
    counts["tasks"] = len(tasks)

    # B に要る材料（読めなければ B は載せない。A は進める）
    sb = None
    exclude: set[str] = set()
    w9: set[str] = set()
    kept: set[str] = set()
    b_error = ""
    if os.environ.get("JARVIS_SUPABASE_URL") and os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY"):
        sb = _sb()
        try:
            exclude = queue_318_ids(sb, now, cfg["queue_318_stale_days"])
            w9 = week9_ids(sb, now, cfg["weekly_pick_lookback_days"])
            kept = kept_ids(sb, now, cfg["keep_days"])
        except ReadError as e:
            b_error = str(e)
    else:
        b_error = "Supabase の鍵が無い"
    if b_error:
        result["errors"].append({"where": "b_inputs", "error": b_error})
        result["b_error"] = b_error

    # コメントを読む（API v1 の一覧の note_count は 0 のままなので当てにしない。318 が聞いている件・繰り返しは読まない）
    comments_by_id: dict[str, list[dict[str, Any]]] = {}
    for t in tasks:
        if not is_recurring(t) and str(t.get("id")) not in exclude:
            try:
                comments_by_id[str(t["id"])] = task_comments(str(t["id"]))
            except Exception as e:  # noqa: BLE001
                result["errors"].append({"where": "comments", "task_id": str(t["id"]), "error": type(e).__name__})
                comments_by_id[str(t["id"])] = []
    keys: set[tuple[str, str]] = set()
    for t in tasks:
        blob = "\n".join([str(t.get("description") or "")] + [str(c.get("content") or "") for c in comments_by_id.get(str(t["id"])) or []])
        keys |= {(k, key) for k, key, _ in extract_links(blob)}
    status = resolve_links(keys, gh_token=_github_token(), fetch_task=lambda i: todoist("GET", f"/tasks/{i}"))

    p = plan(tasks, comments_by_id, status, cfg=cfg, now=now, exclude_ids=exclude, week9_ids=w9, kept_ids=kept)
    counts.update(a=len(p["a"]), b=len(p["b"]), carried_a=p["carried_a"], carried_b=p["carried_b"])
    result["skipped"] = p["skipped"]
    cards = [b_card(r, now) for r in p["b"]]

    print(f"📎 313 週の整理（{'本番' if apply else '下見'}）: タスク {len(tasks)}件 → A 済みました {len(p['a'])}件／B やめる提案 {len(cards)}件"
          f"（上限で次週へ A {p['carried_a']}／B {p['carried_b']}・除外 {p['skipped']}）")
    if b_error:
        print(f"⚠ B は載せません: {b_error}")
    if not apply:
        for r in p["a"]:
            print(f"  A {r['done']['line']}｜{r['done']['url']}")
        for c in cards[:10]:
            print(f"  B [{c['suggest']}] {c['why']}")
        return 0

    state = load_state()
    closed_rows: list[dict[str, Any]] = []
    for r in p["a"]:
        t, d = r["task"], r["done"]
        tid = str(t["id"])
        try:
            todoist("POST", "/comments", {"task_id": tid, "content": close_comment(d, author, cfg["undo_days"])})
            todoist("POST", f"/tasks/{tid}/close", {})
        except Exception as e:  # noqa: BLE001
            counts["close_failed"] += 1
            result["errors"].append({"where": "close", "task_id": tid, "error": type(e).__name__})
            continue
        counts["closed"] += 1
        closed_rows.append(r)
        state["closed"].append({
            "task_id": tid, "closed_at": now.isoformat(timespec="seconds"), "run_id": run_id,
            "kind": d["kind"], "evidence_url": d["url"], "evidence_at": d.get("at"),
            "undo_until": (now + timedelta(days=cfg["undo_days"])).isoformat(timespec="seconds"),
        })
        if sb:
            log_decision(sb, action="close", tid=tid, subject=str(t.get("content") or ""), idem=f"t313w:close:{tid}:{run_id}",
                         payload={"kind": "weekly_done", "origin": "313", "evidence": {"kind": d["kind"], "url": d["url"], "at": d.get("at")},
                                  "run_id": run_id, "undo_until": state["closed"][-1]["undo_until"]})

    if cards and sb and not b_error:
        try:
            publish_queue(sb, {"v": 1, "run_id": run_id, "generated_at": now.isoformat(timespec="seconds"), "published": True, "cards": cards})
            counts["b_published"] = len(cards)
        except Exception as e:  # noqa: BLE001
            result["errors"].append({"where": "publish", "error": type(e).__name__})
            result["b_error"] = "画面に載せられなかった"
    elif not cards and sb and not b_error:
        try:  # 前の週の残りを画面から下げる
            publish_queue(sb, {"v": 1, "run_id": run_id, "generated_at": now.isoformat(timespec="seconds"), "published": True, "cards": []})
        except Exception as e:  # noqa: BLE001
            result["errors"].append({"where": "publish", "error": type(e).__name__})

    cutoff = now - timedelta(days=HISTORY_DAYS)
    state["closed"] = [x for x in state["closed"] if (_dt(x.get("closed_at")) or now) >= cutoff]
    state["last_run"] = result
    state["b_ids"] = [c["id"] for c in cards] if counts["b_published"] else []
    state["at"] = result["at"]

    if notify:
        try:
            from jarvis_nody_link import nody_link  # noqa: PLC0415

            url = nody_link(BULK_PATH, now)
        except Exception:  # noqa: BLE001
            url = BULK_PATH
        bad = counts["close_failed"] or result.get("b_error")
        ok = post_slack(slack_text(result, closed_rows, cards if counts["b_published"] else [], url), signal="yellow" if bad else "green")
        result["slack"] = "sent" if ok else "failed"
    result["result"] = "partial" if (counts["close_failed"] or result.get("b_error") or result.get("slack") == "failed") else "success"
    save_state(state)
    print(f"結果: {result['result']}（閉じた {counts['closed']}・載せた {counts['b_published']}）")
    return 0


def undo(select: str, *, author: str, now: datetime, dry: bool) -> int:
    state = load_state()
    rows = undoable(state, now)
    if select in ("", "list"):
        if not rows:
            print("戻せる件はありません（閉じてから7日以内のものだけ）")
        for i, r in enumerate(rows, 1):
            print(f"  #{i} {r['task_id']} {r['closed_at'][:16]}（{r['kind']}）→ {r['evidence_url']}｜戻せる期限 {r['undo_until'][:16]}")
        return 0
    if select == "all":
        targets = rows
    else:
        nums = {int(x) for x in re.findall(r"\d+", select) if len(x) <= 3}
        ids = set(re.findall(r"[0-9A-Za-z]{6,}", select))
        targets = [r for i, r in enumerate(rows, 1) if i in nums or r["task_id"] in ids]
    if not targets:
        print("❌ 戻す件が見つかりません（--undo list で番号を確認）", file=sys.stderr)
        return 1
    sb = _sb() if (os.environ.get("JARVIS_SUPABASE_URL") and os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")) else None
    rc = 0
    for r in targets:
        tid = r["task_id"]
        if dry:
            print(f"  dry: reopen {tid}")
            continue
        try:
            todoist("POST", f"/tasks/{tid}/reopen", {})
            todoist("POST", "/comments", {"task_id": tid, "content": f"【{author}】313 週の整理で閉じたのを戻しました（済んでいなかった）"})
        except Exception as e:  # noqa: BLE001
            print(f"❌ {tid} を戻せませんでした（{type(e).__name__}）", file=sys.stderr)
            rc = 1
            continue
        r["undone_at"] = now.isoformat(timespec="seconds")
        print(f"  戻しました {tid}")
        if sb:
            log_decision(sb, action="reopen", tid=tid, subject="", idem=f"t313w:reopen:{tid}:{r['closed_at']}",
                         payload={"kind": "weekly_undo", "origin": "313", "closed_at": r["closed_at"], "evidence_kind": r["kind"]})
    if not dry:
        save_state(state)
    return rc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="閉じる・載せる・Slack に1通（無ければ下見だけ）")
    ap.add_argument("--dry-run", action="store_true", help="下見（既定。Todoist・Supabase・Slack に書かない）")
    ap.add_argument("--no-notify", action="store_true", help="--apply でも Slack に出さない")
    ap.add_argument("--undo", default=None, help="戻す: list／番号（1,3）／task_id／all")
    ap.add_argument("--author", default=os.environ.get("TODOIST_313_AUTHOR") or "313")
    a = ap.parse_args(argv)
    if not _todoist_token():
        print("❌ TODOIST_API_TOKEN 未設定", file=sys.stderr)
        return 2
    now = datetime.now(JST)
    if a.undo is None and a.apply and (os.environ.get("JARVIS_TODOIST_313_WEEKLY_DISABLE") == "1"
                                      or os.environ.get("JARVIS_TODOIST_313_DIGEST_DISABLE") == "1"):
        print("313 週の整理: 停止中（JARVIS_TODOIST_313_WEEKLY_DISABLE／_DIGEST_DISABLE）。何もしません")
        return 0
    if a.undo is not None:
        return undo(a.undo, author=a.author, now=now, dry=a.dry_run)
    return run(apply=a.apply and not a.dry_run, author=a.author, now=now, notify=not a.no_notify)


if __name__ == "__main__":
    raise SystemExit(main())
