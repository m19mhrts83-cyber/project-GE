#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""317 コメント起動 — Slack FB＋Todoist Webhook を拾い Ack／分類／任意 L2。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_comment_dispatch.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_comment_dispatch.py --apply
  ~/selenium_env/venv/bin/python scripts/jarvis_comment_dispatch.py --apply --phase-b
  ~/selenium_env/venv/bin/python scripts/jarvis_comment_dispatch.py --apply --failover-only

入口: todoist_webhook_events／Slack FB スレ
確認: L1 Ack 自動。L2 は許可リスト＋--phase-b。対外・金は人
履歴: .jarvis_state/comment_dispatch.json／sync_meta heartbeat／Slack
停止: JARVIS_COMMENT_DISPATCH_DISABLE=1
冗長だけ止める: JARVIS_COMMENT_DISPATCH_FAILOVER=0
stale 閾値分: JARVIS_COMMENT_DISPATCH_STALE_MIN（既定10）
夜間除外（JST）: 既定 0:00〜6:00。JARVIS_COMMENT_DISPATCH_QUIET_START/END（時 0-23）
  除外をやめる: JARVIS_COMMENT_DISPATCH_QUIET_DISABLE=1

正本: docs/AIエージェントチーム/44_コメント常駐起動_317_20261022.md
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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
STATE = REPO / ".jarvis_state" / "comment_dispatch.json"
EXAMPLE = REPO / ".jarvis_state" / "comment_dispatch.example.json"
PY = Path(
    os.environ.get("JARVIS_PYTHON")
    or "/Users/matsunomasaharu2/selenium_env/venv/bin/python"
)
JST = timezone(timedelta(hours=9))
LOG = "📎 317 コメント起動"
HEARTBEAT_KEY = "comment_dispatch_heartbeat_at"
META_KEY = "comment_dispatch_last"
# 就寝帯（JST）: [start, end) — 既定 0:00 以上 6:00 未満
QUIET_START_DEFAULT = 0
QUIET_END_DEFAULT = 6

# Phase B 許可リスト（コメント本文の部分一致・小文字化後）
ALLOWLIST_PATTERNS = (
    r"表確認",
    r"確認だけ",
    r"確認のみ",
    r"launchd.*resume",
    r"resume.*launchd",
    r"オーナー確認",
    r"状態教えて",
    r"内容教えて",
    r"heartbeat",
    r"docs/.*\.md",
)

PHASE_B_HOOK = (os.environ.get("JARVIS_COMMENT_DISPATCH_PHASE_B_CMD") or "").strip()


def _now() -> datetime:
    return datetime.now(JST)


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


def _disabled() -> bool:
    return (os.environ.get("JARVIS_COMMENT_DISPATCH_DISABLE") or "").strip() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _failover_allowed() -> bool:
    return (os.environ.get("JARVIS_COMMENT_DISPATCH_FAILOVER") or "1").strip() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _stale_minutes() -> int:
    try:
        return max(1, int(os.environ.get("JARVIS_COMMENT_DISPATCH_STALE_MIN") or "10"))
    except ValueError:
        return 10


def _quiet_hours_disabled() -> bool:
    return (os.environ.get("JARVIS_COMMENT_DISPATCH_QUIET_DISABLE") or "").strip() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _quiet_hour_bounds() -> tuple[int, int]:
    """Return (start, end) hours in JST; window is [start, end) with wrap support."""
    try:
        start = int(os.environ.get("JARVIS_COMMENT_DISPATCH_QUIET_START") or QUIET_START_DEFAULT)
    except ValueError:
        start = QUIET_START_DEFAULT
    try:
        end = int(os.environ.get("JARVIS_COMMENT_DISPATCH_QUIET_END") or QUIET_END_DEFAULT)
    except ValueError:
        end = QUIET_END_DEFAULT
    start = max(0, min(23, start))
    end = max(0, min(24, end))
    return start, end


def in_quiet_hours(now: datetime | None = None) -> bool:
    """True while JST local time is in the sleeping window (default 00:00–06:00)."""
    if _quiet_hours_disabled():
        return False
    dt = now or _now()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    else:
        dt = dt.astimezone(JST)
    hour = dt.hour
    start, end = _quiet_hour_bounds()
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    # wrap past midnight e.g. 22–6
    return hour >= start or hour < end


def load_state() -> dict[str, Any]:
    if STATE.is_file():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    if EXAMPLE.is_file():
        try:
            return json.loads(EXAMPLE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "disabled": False,
        "last_run_at": None,
        "last_path": None,
        "processed_phase_b": {},
        "last_summary": None,
    }


def save_state(st: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(
        json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _sb_creds() -> tuple[str, str] | None:
    url = (
        os.environ.get("JARVIS_SUPABASE_URL")
        or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        or ""
    ).rstrip("/")
    key = (
        os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("JARVIS_SUPABASE_SECRET_KEY")
        or ""
    ).strip()
    if not url or not key:
        return None
    return url, key


def _sb_req(
    method: str,
    path_qs: str,
    *,
    body: dict[str, Any] | list[Any] | None = None,
) -> Any:
    creds = _sb_creds()
    if not creds:
        raise RuntimeError("JARVIS_SUPABASE_* missing")
    url, key = creds
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/rest/v1/{path_qs}",
        data=data,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        raw = r.read()
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))


def push_heartbeat(*, dry_run: bool, path: str, summary: dict[str, Any]) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if dry_run:
        print(f"# dry-run heartbeat {ts} path={path}")
        return
    if not _sb_creds():
        print(f"{LOG}: heartbeat skip (no supabase)", file=sys.stderr)
        return
    try:
        _sb_req(
            "POST",
            "sync_meta?on_conflict=key",
            body=[
                {"key": HEARTBEAT_KEY, "value": ts, "updated_at": ts},
                {
                    "key": META_KEY,
                    "value": json.dumps(
                        {"at": ts, "path": path, **summary}, ensure_ascii=False
                    ),
                    "updated_at": ts,
                },
            ],
        )
        print(f"{LOG}: heartbeat ok at {ts} path={path}")
    except Exception as exc:
        print(f"{LOG}: heartbeat FAIL: {exc}", file=sys.stderr)


def read_heartbeat_age_minutes() -> float | None:
    if not _sb_creds():
        return None
    try:
        rows = _sb_req(
            "GET",
            f"sync_meta?key=eq.{urllib.parse.quote(HEARTBEAT_KEY)}&select=value,updated_at",
        )
        if not rows:
            return 1e9
        row = rows[0] if isinstance(rows, list) else rows
        raw = str(row.get("value") or row.get("updated_at") or "").strip()
        if not raw:
            return 1e9
        # tolerate Z / +00:00
        raw = raw.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return 1e9
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 60.0
    except Exception as exc:
        print(f"{LOG}: heartbeat read FAIL: {exc}", file=sys.stderr)
        return None


def run_py(script: str, args: list[str], *, dry_run: bool, timeout: int = 180) -> int:
    cmd = [str(PY), str(SCRIPTS / script), *args]
    if dry_run:
        print("# dry-run:", " ".join(cmd))
        return 0
    try:
        r = subprocess.run(cmd, cwd=str(REPO), timeout=timeout)
        return int(r.returncode)
    except Exception as exc:
        print(f"{LOG}: {script} FAIL: {exc}", file=sys.stderr)
        return 1


def classify_todoist_comment(text: str) -> str:
    t = (text or "").strip()
    low = t.lower()
    if not t:
        return "無関係"
    if re.search(r"確認のみ|確認だけ|表確認|クローズして|完了して", t):
        return "確認のみ"
    if re.search(r"方針|どうする|判断|相談|見送り\?", t):
        return "要判断"
    if any(re.search(p, t, re.I) for p in ALLOWLIST_PATTERNS) or re.search(
        r"直して|実装|直してくれ|やって", t
    ):
        return "要実装"
    if len(t) < 4:
        return "無関係"
    if "？" in t or "?" in t or "教えて" in t or "どう" in low:
        return "要判断"
    return "要判断"


def allowlisted(text: str) -> bool:
    t = text or ""
    return any(re.search(p, t, re.I) for p in ALLOWLIST_PATTERNS)


def fetch_unprocessed_notes(limit: int = 15) -> list[dict[str, Any]]:
    if not _sb_creds():
        return []
    qs = (
        "todoist_webhook_events"
        "?select=id,delivery_id,event_name,event_data,initiator,created_at,processed_at"
        "&event_name=eq.note%3Aadded"
        "&processed_at=is.null"
        "&order=created_at.asc"
        f"&limit={limit}"
    )
    try:
        rows = _sb_req("GET", qs) or []
        return list(rows) if isinstance(rows, list) else []
    except Exception as exc:
        print(f"{LOG}: fetch notes FAIL: {exc}", file=sys.stderr)
        return []


def summarize_note(row: dict[str, Any]) -> dict[str, Any]:
    ed = row.get("event_data") or {}
    if not isinstance(ed, dict):
        ed = {}
    item = ed.get("item") if isinstance(ed.get("item"), dict) else {}
    initiator = row.get("initiator") if isinstance(row.get("initiator"), dict) else {}
    return {
        "row_id": row.get("id"),
        "task_id": str(ed.get("item_id") or item.get("id") or ""),
        "task_title": str(item.get("content") or "")[:80],
        "comment": str(ed.get("content") or "").strip(),
        "from_name": str(initiator.get("full_name") or ""),
        "kind": classify_todoist_comment(str(ed.get("content") or "")),
    }


def post_slack_report(text: str, *, dry_run: bool) -> int:
    post = SCRIPTS / "jarvis_slack_webhook_post.py"
    if not post.is_file():
        print(text)
        return 0
    if dry_run:
        print("# dry-run slack report:\n", text)
        return 0
    r = subprocess.run(
        [
            str(PY),
            str(post),
            "--channel",
            "report",
            "--username",
            "317 コメント起動",
            "--text",
            text,
        ],
        cwd=str(REPO),
        timeout=60,
    )
    return int(r.returncode)


def _todoist_phase_b_comment(task_id: str, body: str) -> str:
    if not task_id:
        return "no_task_id"
    try:
        sys.path.insert(0, str(SCRIPTS))
        from jarvis_todoist_webhook_handle import _todoist_comment  # type: ignore

        _todoist_comment(task_id, body)
        return "ok"
    except Exception as exc:
        return f"fail:{exc}"


def _build_phase_b_prompt(item: dict[str, Any]) -> str:
    return (
        "あなたは Jarvis（317 コメント起動）。許可リスト内の安全な処置だけ行う。\n"
        "禁止: 対外送信・振込・解約・無確認 apply・秘密再掲・815返信。\n"
        f"task_id: {item.get('task_id')}\n"
        f"title: {item.get('task_title')}\n"
        f"kind: {item.get('kind')}\n"
        f"comment: {item.get('comment')}\n"
        "完了したら Todoist に【Jarvis】コメントと、可能なら Slack #report に"
        "『やりましたよ（317）』を残す。"
    )


def _run_local_agent(prompt: str) -> str:
    sys.path.insert(0, str(SCRIPTS))
    try:
        from jarvis_night_triage import find_cursor_agent  # type: ignore
    except Exception as exc:
        return f"local_import_fail:{exc}"
    exe = find_cursor_agent()
    if not exe:
        return "local_agent_missing"
    cmd = [
        exe,
        "-p",
        "--trust",
        "--force",
        "--workspace",
        str(REPO),
        "--output-format",
        "text",
        prompt,
    ]
    try:
        r = subprocess.run(
            cmd, cwd=str(REPO), capture_output=True, text=True, timeout=900
        )
        if r.returncode != 0:
            return f"local_rc={r.returncode}:{(r.stderr or r.stdout or '')[:200]}"
        return "local_ok"
    except Exception as exc:
        return f"local_fail:{exc}"


def _run_cloud_agent(prompt: str) -> str:
    """枠あり時のみ。limit なら consult 向け印を返す。"""
    if (os.environ.get("JARVIS_COMMENT_DISPATCH_CLOUD_L2") or "1").strip() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return "cloud_l2_disabled"
    sys.path.insert(0, str(SCRIPTS))
    try:
        from jarvis_cloud_agent_launch import launch_cloud_agent  # type: ignore
    except Exception as exc:
        return f"cloud_import_fail:{exc}"
    res = launch_cloud_agent(
        prompt=prompt,
        name="jarvis-317-comment-dispatch",
        auto_create_pr=False,
    )
    if res.get("ok"):
        return f"cloud_ok:{res.get('url') or res.get('agent_id') or 'started'}"
    if res.get("limit"):
        return "cloud_limit"
    return f"cloud_fail:{res.get('error')}"


def post_slack_consult(text: str, *, dry_run: bool) -> int:
    post = SCRIPTS / "jarvis_slack_webhook_post.py"
    if not post.is_file():
        print(text)
        return 0
    if dry_run:
        print("# dry-run slack consult:\n", text)
        return 0
    r = subprocess.run(
        [
            str(PY),
            str(post),
            "--channel",
            "consult",
            "--username",
            "317 コメント起動",
            "--text",
            text,
        ],
        cwd=str(REPO),
        timeout=60,
    )
    return int(r.returncode)


def run_phase_b_hook(item: dict[str, Any], *, dry_run: bool, path: str) -> str:
    """許可リスト命中時。Mac=Local Agent 本線／failover=Cloud L2。"""
    comment = item.get("comment") or ""
    if not allowlisted(comment):
        return "skip_not_allowlisted"
    key = f"{item.get('task_id')}:{item.get('row_id')}"
    if dry_run:
        return f"dry-run phase-b {key} path={path}"
    if PHASE_B_HOOK:
        env = os.environ.copy()
        env["JARVIS_COMMENT_DISPATCH_ITEM"] = json.dumps(item, ensure_ascii=False)
        try:
            r = subprocess.run(
                PHASE_B_HOOK,
                shell=True,
                cwd=str(REPO),
                env=env,
                timeout=600,
            )
            return f"hook_rc={r.returncode}"
        except Exception as exc:
            return f"hook_fail:{exc}"

    prompt = _build_phase_b_prompt(item)
    tid = str(item.get("task_id") or "")

    if path == "mac":
        local_res = _run_local_agent(prompt)
        if local_res == "local_ok":
            _todoist_phase_b_comment(
                tid,
                "【Jarvis】\nサマリ: 317 Phase B（Local Agent）処置しました。"
                f" kind={item.get('kind')}\nアウトプット:\n- 317 Local Agent",
            )
            post_slack_report(
                f"【報告】317 コメント起動｜やりましたよ（Local）\n"
                f"- task: {item.get('task_title') or tid}\n"
                f"- comment: {(comment or '')[:80]}",
                dry_run=False,
            )
            return local_res
        # Local 不可 → コメントキュー＋相談
        _todoist_phase_b_comment(
            tid,
            "【Jarvis】\nサマリ: 317 Phase B 許可リスト該当。Local Agent 未実行"
            f"（{local_res}）。次セッション／人確認。\nアウトプット:\n- 317 dispatch",
        )
        return f"queued_after_local:{local_res}"

    # failover path → Cloud L2
    cloud_res = _run_cloud_agent(prompt)
    if cloud_res.startswith("cloud_ok"):
        _todoist_phase_b_comment(
            tid,
            "【Jarvis】\nサマリ: 317 Phase B（Cloud Agent・failover）起動しました。"
            f" {cloud_res}\nアウトプット:\n- 317 Cloud Agent",
        )
        post_slack_report(
            f"【報告】317 コメント起動｜やりましたよ（failover/Cloud）\n"
            f"- task: {item.get('task_title') or tid}\n"
            f"- {cloud_res}",
            dry_run=False,
        )
        return cloud_res
    if cloud_res == "cloud_limit":
        post_slack_consult(
            "【相談】317 コメント起動｜Mac復帰待ち／Cloud枠なし\n"
            f"- task: {item.get('task_title') or tid}\n"
            f"- comment: {(comment or '')[:80]}\n"
            "次: Jarvisに依頼\n担当メモ: 枠回復または Mac 復帰後に --phase-b",
            dry_run=False,
        )
        _todoist_phase_b_comment(
            tid,
            "【Jarvis】\nサマリ: 317 Phase B — Cloud 枠なし。キュー残留（failover）。\n"
            "アウトプット:\n- 317 queue",
        )
        return cloud_res
    _todoist_phase_b_comment(
        tid,
        f"【Jarvis】\nサマリ: 317 Phase B Cloud 未起動（{cloud_res}）。\n"
        "アウトプット:\n- 317 queue",
    )
    return cloud_res


def build_report(
    *,
    path: str,
    fb_rc: int,
    wh_rc: int,
    notes: list[dict[str, Any]],
    phase_b: list[str],
) -> str:
    lines = [
        f"【報告】317 コメント起動｜path={path}",
        f"- FB poll rc={fb_rc}／webhook_handle rc={wh_rc}",
        f"- Todoist未処理メモ分類: {len(notes)}件",
    ]
    for n in notes[:8]:
        lines.append(
            f"  · [{n.get('kind')}] {n.get('task_title') or n.get('task_id')}: "
            f"{(n.get('comment') or '')[:60]}"
        )
    if phase_b:
        lines.append("- Phase B: " + "; ".join(phase_b[:5]))
    if path == "failover":
        lines.append("- 経路: (failover) L1 冗長")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true", help="副次スクリプトを実行し heartbeat")
    ap.add_argument("--phase-b", action="store_true", help="許可リスト L2 フック")
    ap.add_argument(
        "--failover-only",
        action="store_true",
        help="Mac heartbeat が stale のときだけ L1（GHA 用）",
    )
    ap.add_argument("--no-slack", action="store_true")
    ap.add_argument("--force", action="store_true", help="stale 判定を無視して failover 実行")
    args = ap.parse_args()

    if _disabled():
        print(f"{LOG}: disabled")
        return 0

    st = load_state()
    if st.get("disabled"):
        print(f"{LOG}: state disabled")
        return 0

    if in_quiet_hours():
        start, end = _quiet_hour_bounds()
        print(
            f"{LOG}: quiet hours JST {start:02d}:00–{end:02d}:00 — skip "
            f"(now {_now().strftime('%H:%M')})"
        )
        # Mac が生きている印だけ残し、夜間の GHA stale 発火を防ぐ
        if args.apply and not args.failover_only:
            push_heartbeat(
                dry_run=False,
                path="mac_quiet",
                summary={"quiet": True, "skip": True},
            )
        return 0

    path = "mac"
    if args.failover_only:
        if not _failover_allowed() and not args.force:
            print(f"{LOG}: failover disabled")
            return 0
        age = read_heartbeat_age_minutes()
        stale_m = _stale_minutes()
        if age is None:
            print(f"{LOG}: failover skip (no heartbeat read)")
            return 0
        if age < stale_m and not args.force:
            print(f"{LOG}: mac alive age_min={age:.1f} < {stale_m} → noop")
            return 0
        path = "failover"
        print(f"{LOG}: failover L1 (age_min={age:.1f})")

    do_run = args.apply or args.dry_run
    if not do_run:
        ap.print_help()
        return 2

    # L1: existing tools
    fb_args = ["--apply"] if args.apply else ["--dry-run"]
    wh_args = ["--reply"] if args.apply else []
    # dry-run for webhook_handle: just list via our fetch; still call without --reply
    fb_rc = run_py("jarvis_slack_report_fb_poll.py", fb_args, dry_run=args.dry_run)
    if args.dry_run:
        wh_rc = 0
        print("# dry-run: skip webhook_handle --reply")
    else:
        wh_rc = run_py(
            "jarvis_todoist_webhook_handle.py",
            wh_args or ["--limit", "10"],
            dry_run=False,
            timeout=180,
        )

    notes_raw = fetch_unprocessed_notes(limit=15)
    notes = [summarize_note(r) for r in notes_raw]
    # Also re-classify already-fetched for report even if handle marked some
    phase_b_results: list[str] = []
    if args.phase_b:
        for n in notes:
            if n.get("kind") == "要実装" or allowlisted(str(n.get("comment") or "")):
                res = run_phase_b_hook(n, dry_run=args.dry_run, path=path)
                phase_b_results.append(f"{n.get('row_id')}:{res}")
                pb = dict(st.get("processed_phase_b") or {})
                pb[str(n.get("row_id"))] = {"at": _now_iso(), "res": res, "path": path}
                st["processed_phase_b"] = pb

    summary = {
        "fb_rc": fb_rc,
        "wh_rc": wh_rc,
        "notes": len(notes),
        "phase_b": len(phase_b_results),
        "kinds": {n.get("kind"): 0 for n in notes},
    }
    for n in notes:
        k = str(n.get("kind") or "")
        summary["kinds"][k] = int(summary["kinds"].get(k) or 0) + 1

    # heartbeat: mac path always; failover also updates so we know failover ran
    if args.apply or args.dry_run:
        push_heartbeat(dry_run=args.dry_run, path=path, summary=summary)

    report = build_report(
        path=path,
        fb_rc=fb_rc,
        wh_rc=wh_rc,
        notes=notes,
        phase_b=phase_b_results,
    )
    print(report)

    # Slack: 何かあったとき／failover のときだけ
    should_post = (len(notes) > 0 or phase_b_results or path == "failover") and (
        fb_rc == 0 or wh_rc == 0 or len(notes) > 0
    )
    if should_post and not args.no_slack:
        post_slack_report(report, dry_run=args.dry_run)

    st["last_run_at"] = _now_iso()
    st["last_path"] = path
    st["last_summary"] = summary
    if args.apply and not args.dry_run:
        save_state(st)
    elif args.dry_run:
        print("# dry-run: state not saved")

    # 副次の非0は summary に残す。heartbeat まで到達したら launchd は成功扱い（soft-fail）
    if fb_rc != 0 or wh_rc != 0:
        print(
            f"{LOG}: soft-fail fb_rc={fb_rc} wh_rc={wh_rc} (heartbeat/state は更新済)",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
