#!/usr/bin/env python3
"""
Jarvis: Vercel / GitHub Actions の Fail を検知し watch_status へ反映。

夜間トリアージ・GHA Gmail triage・situation watch から呼ぶ。
修正完了時は ops_fix_notice（ホームお知らせ）を立てる。

  python scripts/jarvis_ops_fail_watch.py --dry-run
  python scripts/jarvis_ops_fail_watch.py --push
  python scripts/jarvis_ops_fail_watch.py --push --note "直した内容"

環境: JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY
任意: gh 認証（GITHUB_TOKEN）
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

# main 直近コミットの Vercel context を見る
VERCEL_CONTEXTS = (
    "Vercel – jarvis-dashboard",
    "Vercel – project-ge",
    "Vercel",
)

# 監視する workflow ファイル名（失敗したら注意）
WATCH_WORKFLOWS = (
    "jarvis-dashboard-gmail-triage.yml",
    "jarvis-dashboard-situation-watch.yml",
    "jarvis-dashboard-lanes.yml",
    "jarvis-dashboard-heartbeat.yml",
    "westudy-raimo-weekly.yml",
    "pages-docs.yml",
)


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def _gh_json(args: list[str], timeout: int = 60) -> Any:
    cmd = ["gh", *args]
    out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT, timeout=timeout)
    return json.loads(out or "null")


def check_vercel_main() -> dict[str, Any]:
    """origin/main の commit status から Vercel 失敗を拾う。"""
    try:
        st = _gh_json(["api", "repos/{owner}/{repo}/commits/main/status"])
    except FileNotFoundError:
        return {
            "id": "vercel_deploy",
            "title": "Vercelデプロイ",
            "category": "ops",
            "level": "attention",
            "summary": "gh 未インストールのため Vercel 状態を取得できない",
            "detail": None,
            "source": "ops_fail_watch",
            "cursor_prompt": "Vercel の Production デプロイ失敗を確認し、ビルドエラーを直して。",
            "status": "active",
            "checked_at": now_iso(),
            "payload": {"show_banner": True, "origin": "ops_fail_watch"},
        }
    except (subprocess.CalledProcessError, json.JSONDecodeError, subprocess.TimeoutExpired) as e:
        return {
            "id": "vercel_deploy",
            "title": "Vercelデプロイ",
            "category": "ops",
            "level": "attention",
            "summary": f"gh 取得失敗: {e}",
            "detail": None,
            "source": "ops_fail_watch",
            "cursor_prompt": "Vercel の Production デプロイ失敗を確認し、ビルドエラーを直して。",
            "status": "active",
            "checked_at": now_iso(),
            "payload": {"show_banner": True, "origin": "ops_fail_watch"},
        }

    statuses = st.get("statuses") or []
    vercel = [
        s
        for s in statuses
        if any(c in (s.get("context") or "") for c in ("Vercel", "vercel"))
    ]
    bad = [s for s in vercel if (s.get("state") or "") in ("failure", "error")]
    pending = [s for s in vercel if (s.get("state") or "") == "pending"]

    if bad:
        bits = []
        for s in bad:
            bits.append(
                f"{s.get('context')}: {s.get('description') or s.get('state')}"
            )
        url = bad[0].get("target_url")
        return {
            "id": "vercel_deploy",
            "title": "Vercelデプロイ失敗",
            "category": "ops",
            "level": "attention",
            "summary": " / ".join(bits)[:400],
            "detail": url,
            "source": "ops_fail_watch",
            "cursor_prompt": (
                "Vercel Production/Development のデプロイ失敗を直して。"
                " gh の commit status と対象アプリ（jarvis-dashboard / project-ge）の"
                " `npm run build` を確認し、修正→push。直したら"
                " `python scripts/jarvis_ops_fail_watch.py --push --note '…直した内容…'` で"
                " ホームお知らせを出して。"
            ),
            "status": "active",
            "checked_at": now_iso(),
            "payload": {
                "show_banner": True,
                "origin": "ops_fail_watch",
                "statuses": bad,
            },
        }

    if pending:
        return {
            "id": "vercel_deploy",
            "title": "Vercelデプロイ",
            "category": "ops",
            "level": "info",
            "summary": f"デプロイ進行中（{len(pending)}）",
            "detail": (pending[0].get("target_url") if pending else None),
            "source": "ops_fail_watch",
            "cursor_prompt": "Vercel デプロイの完了を確認して。",
            "status": "active",
            "checked_at": now_iso(),
            "payload": {"show_banner": False, "origin": "ops_fail_watch"},
        }

    ok_n = len([s for s in vercel if s.get("state") == "success"])
    return {
        "id": "vercel_deploy",
        "title": "Vercelデプロイ",
        "category": "ops",
        "level": "ok",
        "summary": f"main の Vercel は成功（{ok_n} contexts）" if ok_n else "Vercel status なし（スキップ可）",
        "detail": (vercel[0].get("target_url") if vercel else None),
        "source": "ops_fail_watch",
        "cursor_prompt": "Vercel デプロイ状態を確認して。",
        "status": "active",
        "checked_at": now_iso(),
        "payload": {"show_banner": False, "origin": "ops_fail_watch", "statuses": vercel},
    }


def check_gha_workflows() -> dict[str, Any]:
    """監視対象 workflow の直近失敗を列挙。"""
    fails: list[dict[str, Any]] = []
    try:
        for wf in WATCH_WORKFLOWS:
            try:
                runs = _gh_json(
                    [
                        "run",
                        "list",
                        f"--workflow={wf}",
                        "--limit",
                        "2",
                        "--json",
                        "databaseId,conclusion,status,createdAt,url,displayTitle,headBranch",
                    ]
                )
            except subprocess.CalledProcessError:
                continue
            if not runs:
                continue
            latest = runs[0]
            if latest.get("conclusion") == "failure":
                # 古い失敗を永続ピンしない（直近 4 日）
                created = latest.get("createdAt") or ""
                try:
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    age_h = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
                except ValueError:
                    age_h = 0.0
                if age_h <= 96:
                    fails.append({"workflow": wf, **latest})
    except FileNotFoundError:
        return {
            "id": "gha_workflow_fail",
            "title": "GitHub Actions失敗",
            "category": "ops",
            "level": "attention",
            "summary": "gh 未インストール",
            "detail": None,
            "source": "ops_fail_watch",
            "cursor_prompt": "失敗した GitHub Actions を直して。",
            "status": "active",
            "checked_at": now_iso(),
            "payload": {"show_banner": True, "origin": "ops_fail_watch"},
        }
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        return {
            "id": "gha_workflow_fail",
            "title": "GitHub Actions失敗",
            "category": "ops",
            "level": "attention",
            "summary": f"取得失敗: {e}",
            "detail": None,
            "source": "ops_fail_watch",
            "cursor_prompt": "失敗した GitHub Actions を直して。",
            "status": "active",
            "checked_at": now_iso(),
            "payload": {"show_banner": True, "origin": "ops_fail_watch"},
        }

    if fails:
        bits = [
            f"{f.get('workflow')}: {f.get('displayTitle') or f.get('conclusion')}"
            for f in fails
        ]
        return {
            "id": "gha_workflow_fail",
            "title": "GitHub Actions失敗",
            "category": "ops",
            "level": "attention",
            "summary": " / ".join(bits)[:400],
            "detail": fails[0].get("url"),
            "source": "ops_fail_watch",
            "cursor_prompt": (
                "失敗した GitHub Actions のログを見て直して。"
                " 直したら `python scripts/jarvis_ops_fail_watch.py --push --note '…'` でお知らせ。"
            ),
            "status": "active",
            "checked_at": now_iso(),
            "payload": {
                "show_banner": True,
                "origin": "ops_fail_watch",
                "fails": fails,
            },
        }

    return {
        "id": "gha_workflow_fail",
        "title": "GitHub Actions",
        "category": "ops",
        "level": "ok",
        "summary": "監視対象 workflow の直近は失敗なし",
        "detail": None,
        "source": "ops_fail_watch",
        "cursor_prompt": "GitHub Actions の失敗有無を確認して。",
        "status": "active",
        "checked_at": now_iso(),
        "payload": {"show_banner": False, "origin": "ops_fail_watch"},
    }


def make_fix_notice(note: str, *, level: str = "info") -> dict[str, Any]:
    note = (note or "").strip() or "運用監視の修正を反映しました"
    return {
        "id": "ops_fix_notice",
        "title": "Jarvisが直したよ",
        "category": "ops",
        "level": level,
        "summary": note[:500],
        "detail": None,
        "source": "ops_fail_watch",
        "cursor_prompt": "ホームのお知らせ（ops_fix_notice）を確認して、必要ならアーカイブして。",
        "status": "active",
        "checked_at": now_iso(),
        "payload": {
            "show_banner": True,
            "origin": "ops_fail_watch",
            "note": note,
            "fixed_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def to_row(it: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": it["id"],
        "title": it.get("title") or it["id"],
        "category": it.get("category"),
        "level": it.get("level") or "info",
        "summary": it.get("summary"),
        "detail": it.get("detail"),
        "source": it.get("source"),
        "cursor_prompt": it.get("cursor_prompt"),
        "status": it.get("status") or "active",
        "archived_at": None,
        "checked_at": it.get("checked_at") or now_iso(),
        "payload": it.get("payload") or {"origin": "ops_fail_watch"},
        "updated_at": now_iso(),
    }


def collect_items(*, note: str | None = None) -> list[dict[str, Any]]:
    items = [check_vercel_main(), check_gha_workflows()]
    if note:
        items.append(make_fix_notice(note))
    return items


def push_items(items: list[dict[str, Any]]) -> int:
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        print("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要", file=sys.stderr)
        return 1
    from supabase import create_client

    sb = create_client(url, key)
    remote_arch: set[str] = set()
    try:
        r = sb.table("watch_status").select("id").eq("status", "archived").execute()
        remote_arch = {str(x["id"]) for x in (r.data or [])}
    except Exception as e:
        print(f"# archive merge skip: {e}", file=sys.stderr)

    rows = []
    for it in items:
        # ops_fix_notice は archived でも note 指定時は復活させたい
        if it["id"] in remote_arch and it["id"] != "ops_fix_notice":
            continue
        if it["id"] == "ops_fix_notice" and it["id"] in remote_arch:
            # 再掲
            pass
        rows.append(to_row(it))
    if rows:
        sb.table("watch_status").upsert(rows, on_conflict="id").execute()
    meta_now = now_iso()
    meta_rows = [
        {"key": "ops_fail_watch_at", "value": meta_now, "updated_at": meta_now},
        {"key": "gha_watch_pushed_at", "value": meta_now, "updated_at": meta_now},
    ]
    note_item = next((i for i in items if i["id"] == "ops_fix_notice"), None)
    if note_item:
        meta_rows.append(
            {
                "key": "ops_fix_notice",
                "value": note_item.get("summary") or "",
                "updated_at": meta_now,
            }
        )
    sb.table("sync_meta").upsert(meta_rows, on_conflict="key").execute()
    print(f"# ops_fail_watch upserted {len(rows)}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--push", action="store_true")
    ap.add_argument(
        "--note",
        default="",
        help="修正内容をホームお知らせ（ops_fix_notice）に載せる",
    )
    args = ap.parse_args(argv)
    if not args.dry_run and not args.push:
        args.dry_run = True

    items = collect_items(note=args.note or None)
    print(json.dumps({"count": len(items), "items": items}, ensure_ascii=False, indent=2))
    if args.dry_run:
        return 0
    return push_items(items)


if __name__ == "__main__":
    raise SystemExit(main())
