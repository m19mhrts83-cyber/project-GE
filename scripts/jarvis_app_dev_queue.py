#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""アプリ開発カード → GitHub キュー（第1段）。

Grok は PR を切らない。Jarvis が朝バンドルで:
  · リスク低（実装）→ Cursor Cloud Agent（autoCreatePR）
  · リスク高（実装）→ gh issue（label: app-dev, risk-high）
  · 材料 → Issue（label: app-dev, material）※Cloud は起動しない
  · 表確認 → Issue（label: app-dev, ui-check）※ログインして画面確認。Cloud は起動しない

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_app_dev_queue.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_app_dev_queue.py
  ~/selenium_env/venv/bin/python scripts/jarvis_app_dev_queue.py --list-only
  ~/selenium_env/venv/bin/python scripts/jarvis_app_dev_queue.py --merge-pr 123

無効化: JARVIS_APP_DEV_QUEUE_DISABLE=1
朝バンドル: jarvis_morning_mac_refresh.py から呼ばれる。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

import jarvis_app_dev_cards_morning as cards  # noqa: E402
from jarvis_cloud_agent_launch import launch_cloud_agent  # noqa: E402

STATE_PATH = cards.STATE_PATH
DIGEST_PATH = REPO / ".jarvis_state" / "app_dev_queue_digest.md"
DEFAULT_REPO = "https://github.com/m19mhrts83-cyber/project-GE"
MAX_LOW_CLOUD_PER_RUN = 3
LABEL_APP = "app-dev"
LABEL_HIGH = "risk-high"
LABEL_LOW = "risk-low"
LABEL_MAT = "material"
LABEL_UI = "ui-check"


def env_disabled() -> bool:
    return (os.environ.get("JARVIS_APP_DEV_QUEUE_DISABLE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def repo_url() -> str:
    return (
        (os.environ.get("CURSOR_CLOUD_REPO_URL") or "").strip()
        or DEFAULT_REPO
    )


def repo_slug(url: str) -> str:
    """https://github.com/owner/repo(.git) → owner/repo"""
    m = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", url)
    if not m:
        return "m19mhrts83-cyber/project-GE"
    return f"{m.group(1)}/{m.group(2)}"


def load_state() -> dict[str, Any]:
    state = cards.load_state()
    state.setdefault("queue", {})
    if not isinstance(state["queue"], dict):
        state["queue"] = {}
    return state


def save_state(state: dict[str, Any]) -> None:
    cards.save_state(state)


def run_gh(args: list[str], *, timeout: int = 60) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(REPO),
    )
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def ensure_labels(slug: str, dry_run: bool) -> None:
    wanted = [
        (LABEL_APP, "app development queue"),
        (LABEL_HIGH, "needs Matsuno OK"),
        (LABEL_LOW, "low risk auto-PR"),
        (LABEL_MAT, "materials request"),
        (LABEL_UI, "UI check after backend review"),
    ]
    for name, desc in wanted:
        if dry_run:
            print(f"# dry-run: ensure label {name}")
            continue
        rc, _, err = run_gh(
            [
                "label",
                "create",
                name,
                "--repo",
                slug,
                "--description",
                desc,
                "--force",
            ]
        )
        if rc != 0 and "already exists" not in (err or "").lower():
            # --force で更新可。失敗は警告のみ
            print(f"# label {name}: {err or 'ok?'}", file=sys.stderr)


def build_cloud_prompt(card: dict[str, Any]) -> str:
    return f"""あなたは Jarvis（Mac 運用の代わりに Cloud Agent）です。
リポジトリ project-GE（モノレポ）で、アプリ開発統括からの **低リスク** 小修正を実装し、PR を作成してください。

## 制約
- 対象は次の3アプリのみ: apps/kamiooya-qa-web / apps/jarvis-dashboard / apps/trade-desk
- .env・秘密・パスワード・API鍵は読まない・書かない・コミットしない
- main に直接 push しない。作業ブランチ＋ PR のみ
- Free Supabase に3つ目プロジェクトを作らない
- kamiooya-qa に Jarvis 個人用テーブルを足さない
- 大きい挙動・DB・認証・対外送信は触らない（このカードはリスク低のはず）

## カード（card_id={card["id"]}）
- アプリ: {card.get("app")}
- やりたいこと: {card.get("want")}
- 触りそうな場所: {card.get("where") or "（未記入）"}
- リスク: 低
- 完了条件: {card.get("done") or "変更が意図どおり・ビルドが通る"}

## PR
- タイトル先頭: `[app-dev][low][{card["id"]}]`
- 本文に card_id={card["id"]} と上記カード全文を含める
- ラベル相当の説明に app-dev / risk-low と書く

最小差分で完了条件を満たすこと。
"""


def build_issue_body(card: dict[str, Any]) -> str:
    lines = [
        f"card_id: `{card['id']}`",
        f"kind: {card.get('kind')}",
        f"risk: {card.get('risk')}",
        f"source: {card.get('source')}",
        "",
        "```",
        card.get("raw") or "",
        "```",
        "",
        "### Jarvis",
        "- 高リスク: 松野 OK 後に Cloud／対話で PR を作成",
        "- 材料: 週次パックを用意してチャンネル or メールへ",
        "- 表確認: Jarvis がログインして該当画面を確認し、結果を Issue／チャットへ",
    ]
    return "\n".join(lines)


def create_issue(
    slug: str,
    card: dict[str, Any],
    *,
    labels: list[str],
    dry_run: bool,
) -> dict[str, Any]:
    title = f"[app-dev][{card.get('risk') or card.get('kind')}][{card['id']}] {card.get('app')}: {card.get('want')}"
    title = title[:200]
    body = build_issue_body(card)
    if dry_run:
        print(f"# dry-run issue: {title}")
        print(f"# labels: {','.join(labels)}")
        return {"ok": True, "dry_run": True, "title": title}
    args = [
        "issue",
        "create",
        "--repo",
        slug,
        "--title",
        title,
        "--body",
        body,
    ]
    for lb in labels:
        args.extend(["--label", lb])
    rc, out, err = run_gh(args, timeout=90)
    if rc != 0:
        return {"ok": False, "error": err or out or f"rc={rc}"}
    return {"ok": True, "url": out.strip()}


def list_open_queue(slug: str) -> dict[str, list[str]]:
    prs: list[str] = []
    issues: list[str] = []
    rc, out, err = run_gh(
        [
            "pr",
            "list",
            "--repo",
            slug,
            "--state",
            "open",
            "--limit",
            "30",
            "--json",
            "number,title,url,labels",
        ]
    )
    if rc == 0 and out:
        try:
            for p in json.loads(out):
                title = p.get("title") or ""
                labels = [x.get("name") for x in (p.get("labels") or [])]
                if LABEL_APP in labels or "[app-dev]" in title:
                    prs.append(f"#{p.get('number')} {title} — {p.get('url')}")
        except json.JSONDecodeError:
            prs.append(f"(parse error) {out[:120]}")
    else:
        prs.append(f"(gh pr list failed) {err or out}")

    rc, out, err = run_gh(
        [
            "issue",
            "list",
            "--repo",
            slug,
            "--state",
            "open",
            "--label",
            LABEL_APP,
            "--limit",
            "30",
            "--json",
            "number,title,url,labels",
        ]
    )
    if rc == 0 and out:
        try:
            for it in json.loads(out):
                issues.append(
                    f"#{it.get('number')} {it.get('title')} — {it.get('url')}"
                )
        except json.JSONDecodeError:
            issues.append(f"(parse error) {out[:120]}")
    else:
        issues.append(f"(gh issue list failed) {err or out}")

    return {"prs": prs, "issues": issues}


def merge_pr(slug: str, number: int, *, dry_run: bool) -> int:
    """低リスク相当の PR のみマージ（タイトルまたはラベルで判定）。"""
    rc, out, err = run_gh(
        [
            "pr",
            "view",
            str(number),
            "--repo",
            slug,
            "--json",
            "title,labels,url,state",
        ]
    )
    if rc != 0:
        print(f"# merge-pr failed: {err or out}", file=sys.stderr)
        return 1
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        print(f"# merge-pr bad json: {out[:200]}", file=sys.stderr)
        return 1
    title = data.get("title") or ""
    labels = [x.get("name") for x in (data.get("labels") or [])]
    high = LABEL_HIGH in labels or "[high]" in title.lower() or "risk-high" in title
    if high:
        print("# refuse: 高リスク／risk-high の PR は自動マージしません", file=sys.stderr)
        return 2
    if LABEL_APP not in labels and "[app-dev]" not in title:
        print("# refuse: app-dev 以外の PR はマージしません", file=sys.stderr)
        return 2
    if dry_run:
        print(f"# dry-run merge: #{number} {title}")
        return 0
    rc, out, err = run_gh(
        [
            "pr",
            "merge",
            str(number),
            "--repo",
            slug,
            "--squash",
            "--delete-branch",
        ],
        timeout=120,
    )
    if rc != 0:
        print(f"# merge failed: {err or out}", file=sys.stderr)
        return 1
    print(f"# merged #{number} {data.get('url')}")
    return 0


def render_digest(
    *,
    actions: list[str],
    open_q: dict[str, list[str]],
    notes: list[str],
) -> str:
    lines = [
        "📎 アプリ開発キュー（PR／Issue）",
        f"- 取得: {' / '.join(notes)}",
        f"- 今回の処置: {len(actions)}",
    ]
    for a in actions[:12]:
        lines.append(f"  · {a}")
    lines.append(f"- Open PR (app-dev): {len([x for x in open_q['prs'] if not x.startswith('(')])}")
    for p in open_q["prs"][:10]:
        lines.append(f"  · {p}")
    lines.append(f"- Open Issue (app-dev): {len([x for x in open_q['issues'] if not x.startswith('(')])}")
    for it in open_q["issues"][:10]:
        lines.append(f"  · {it}")
    lines.append(
        "- 次: 低PRは目視マージ or「委任して #N」。高IssueはOK後に PR 作成依頼。"
    )
    return "\n".join(lines) + "\n"


def pending_cards(state: dict[str, Any], *, days: int, skip_gmail: bool) -> list[dict[str, Any]]:
    all_cards, _notes = cards.collect_cards(
        days=days, skip_gmail=skip_gmail, state=state
    )
    queue = state.get("queue") or {}
    out: list[dict[str, Any]] = []
    for c in all_cards:
        cid = c["id"]
        prev = queue.get(cid) or {}
        status = (prev.get("status") or "").strip()
        if status in ("queued", "cloud_launched", "issue_created", "merged", "skipped"):
            continue
        out.append(c)
    return out


def process_card(
    card: dict[str, Any],
    *,
    slug: str,
    dry_run: bool,
    skip_cloud: bool,
    issues_only: bool,
    low_budget: list[int],
) -> tuple[dict[str, Any], str]:
    """Returns (queue_entry, action_line)."""
    kind = card.get("kind")
    risk = card.get("risk")

    if kind == "材料":
        r = create_issue(
            slug,
            card,
            labels=[LABEL_APP, LABEL_MAT],
            dry_run=dry_run,
        )
        if not r.get("ok"):
            return (
                {"status": "error", "error": r.get("error"), "kind": kind, "risk": risk},
                f"材料Issue失敗 [{card['id']}]: {r.get('error')}",
            )
        entry = {
            "status": "issue_created",
            "kind": kind,
            "risk": risk,
            "issue_url": r.get("url"),
            "at": cards.now_iso(),
        }
        return entry, f"材料Issue [{card['id']}] {r.get('url') or '(dry-run)'}"

    if kind == "表確認":
        r = create_issue(
            slug,
            card,
            labels=[LABEL_APP, LABEL_UI],
            dry_run=dry_run,
        )
        if not r.get("ok"):
            return (
                {"status": "error", "error": r.get("error"), "kind": kind, "risk": risk},
                f"表確認Issue失敗 [{card['id']}]: {r.get('error')}",
            )
        entry = {
            "status": "issue_created",
            "kind": kind,
            "risk": risk,
            "issue_url": r.get("url"),
            "at": cards.now_iso(),
        }
        return entry, f"表確認Issue [{card['id']}] {r.get('url') or '(dry-run)'}"

    if risk == "高" or (risk not in ("低",) and kind == "実装"):
        # 不明も高扱い
        r = create_issue(
            slug,
            card,
            labels=[LABEL_APP, LABEL_HIGH],
            dry_run=dry_run,
        )
        if not r.get("ok"):
            return (
                {"status": "error", "error": r.get("error"), "kind": kind, "risk": "高"},
                f"高Issue失敗 [{card['id']}]: {r.get('error')}",
            )
        entry = {
            "status": "issue_created",
            "kind": kind,
            "risk": "高",
            "issue_url": r.get("url"),
            "at": cards.now_iso(),
        }
        return entry, f"高Issue [{card['id']}] {r.get('url') or '(dry-run)'}"

    # 低
    if issues_only or skip_cloud:
        r = create_issue(
            slug,
            card,
            labels=[LABEL_APP, LABEL_LOW],
            dry_run=dry_run,
        )
        if not r.get("ok"):
            return (
                {"status": "error", "error": r.get("error"), "kind": kind, "risk": "低"},
                f"低Issue失敗 [{card['id']}]: {r.get('error')}",
            )
        entry = {
            "status": "issue_created",
            "kind": kind,
            "risk": "低",
            "issue_url": r.get("url"),
            "note": "cloud skipped",
            "at": cards.now_iso(),
        }
        return entry, f"低Issue(Cloud skip) [{card['id']}] {r.get('url') or '(dry-run)'}"

    if low_budget[0] >= MAX_LOW_CLOUD_PER_RUN:
        return (
            {"status": "deferred", "kind": kind, "risk": "低", "at": cards.now_iso()},
            f"低Cloud見送り(上限{MAX_LOW_CLOUD_PER_RUN}) [{card['id']}]",
        )

    prompt = build_cloud_prompt(card)
    if dry_run:
        print(f"# dry-run Cloud Agent card={card['id']}")
        print(prompt[:500] + ("…" if len(prompt) > 500 else ""))
        low_budget[0] += 1
        return (
            {
                "status": "cloud_launched",
                "kind": kind,
                "risk": "低",
                "dry_run": True,
                "at": cards.now_iso(),
            },
            f"低Cloud(dry-run) [{card['id']}]",
        )

    launched = launch_cloud_agent(
        prompt=prompt,
        name=f"app-dev-{card['id']}"[:80],
        repo_url=repo_url(),
        starting_ref="main",
        auto_create_pr=True,
    )
    low_budget[0] += 1
    if not launched.get("ok"):
        return (
            {
                "status": "error",
                "kind": kind,
                "risk": "低",
                "error": launched.get("error"),
                "limit": launched.get("limit"),
                "at": cards.now_iso(),
            },
            f"低Cloud失敗 [{card['id']}]: {launched.get('error')}",
        )
    entry = {
        "status": "cloud_launched",
        "kind": kind,
        "risk": "低",
        "agent_id": launched.get("agent_id"),
        "agent_url": launched.get("url"),
        "run_id": launched.get("run_id"),
        "at": cards.now_iso(),
    }
    return entry, f"低Cloud起動 [{card['id']}] {launched.get('url')}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-gmail", action="store_true")
    ap.add_argument("--skip-cloud", action="store_true")
    ap.add_argument("--issues-only", action="store_true")
    ap.add_argument("--list-only", action="store_true")
    ap.add_argument("--merge-pr", type=int, default=0)
    args = ap.parse_args()

    if env_disabled():
        print("# skip: JARVIS_APP_DEV_QUEUE_DISABLE=1")
        return 0

    slug = repo_slug(repo_url())
    notes = [f"repo={slug}"]

    if args.merge_pr:
        return merge_pr(slug, args.merge_pr, dry_run=args.dry_run)

    open_q = list_open_queue(slug)
    if args.list_only:
        digest = render_digest(actions=["(list-only)"], open_q=open_q, notes=notes)
        print(digest, end="")
        DIGEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        DIGEST_PATH.write_text(digest, encoding="utf-8")
        return 0

    state = load_state()
    pending = pending_cards(state, days=args.days, skip_gmail=args.skip_gmail)
    notes.append(f"pending_cards={len(pending)}")

    ensure_labels(slug, args.dry_run)

    actions: list[str] = []
    low_budget = [0]
    queue = state.setdefault("queue", {})

    for card in pending:
        entry, line = process_card(
            card,
            slug=slug,
            dry_run=args.dry_run,
            skip_cloud=args.skip_cloud,
            issues_only=args.issues_only,
            low_budget=low_budget,
        )
        actions.append(line)
        # deferred は次回再試行のため queue に確定しない
        if entry.get("status") == "deferred":
            continue
        queue[card["id"]] = entry

    # 最新の open 一覧
    open_q = list_open_queue(slug)
    digest = render_digest(actions=actions, open_q=open_q, notes=notes)
    print(digest, end="")
    DIGEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    DIGEST_PATH.write_text(digest, encoding="utf-8")

    # カード朝 digest にも追記（あれば）
    if cards.DIGEST_PATH.is_file():
        prev = cards.DIGEST_PATH.read_text(encoding="utf-8", errors="replace")
        if "📎 アプリ開発キュー" not in prev:
            cards.DIGEST_PATH.write_text(prev.rstrip() + "\n\n" + digest, encoding="utf-8")

    if not args.dry_run:
        state["queue"] = queue
        state["last_queue_at"] = cards.now_iso()
        save_state(state)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
