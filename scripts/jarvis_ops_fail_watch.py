#!/usr/bin/env python3
"""
Jarvis: Vercel / GitHub Actions の Fail を検知し watch_status へ反映。

定例は朝1回のみ（Gmail トリアージ 05:00 JST の末尾）。昼・夜は回さない。
手動・修正お知らせは workflow_dispatch / --note で。
--autofix で Cloud Agent 自動起動（上限時はローカル queued）。
修正完了時は ops_fix_notice（ホームお知らせ）を立て、失敗ピンは対応済みにして消す。
ダッシュボードでは「確認しました」でお知らせを消す（アーカイブしない）。

  python scripts/jarvis_ops_fail_watch.py --dry-run
  python scripts/jarvis_ops_fail_watch.py --push
  python scripts/jarvis_ops_fail_watch.py --push --autofix
  python scripts/jarvis_ops_fail_watch.py --push --note "直した内容"

環境: JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY
任意: gh 認証（GITHUB_TOKEN）/ CURSOR_API_KEY（--autofix）/ CURSOR_CLOUD_REPO_URL
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

AUTOFIX_IDS = ("vercel_deploy", "gha_workflow_fail")
OPS_EPHEMERAL_IDS = (*AUTOFIX_IDS, "ops_fix_notice")
BUSY_STATUSES = ("queued", "running", "launched")


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def _ephemeral_payload(**extra: Any) -> dict[str, Any]:
    pl: dict[str, Any] = {
        "origin": "ops_fail_watch",
        "never_archive": True,
        "ephemeral": True,
    }
    pl.update(extra)
    return pl


def _as_id_set(raw: Any) -> set[str]:
    out: set[str] = set()
    if not isinstance(raw, (list, tuple, set)):
        return out
    for x in raw:
        if x is None:
            continue
        s = str(x).strip()
        if s:
            out.add(s)
    return out


def _vercel_status_key(s: dict[str, Any]) -> str:
    ctx = str(s.get("context") or "")
    sha = str(s.get("sha") or s.get("target_url") or s.get("description") or "")
    return f"{ctx}|{sha}"[:240]


def _gh_json(args: list[str], timeout: int = 60) -> Any:
    cmd = ["gh", *args]
    out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT, timeout=timeout)
    return json.loads(out or "null")


def check_vercel_main(*, resolved_keys: set[str] | None = None) -> dict[str, Any]:
    """origin/main の commit status から Vercel 失敗を拾う。"""
    resolved_keys = resolved_keys or set()
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
            "payload": _ephemeral_payload(show_banner=True),
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
            "payload": _ephemeral_payload(show_banner=True),
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
        unresolved = [s for s in bad if _vercel_status_key(s) not in resolved_keys]
        if not unresolved:
            return {
                "id": "vercel_deploy",
                "title": "Vercelデプロイ",
                "category": "ops",
                "level": "ok",
                "summary": "直近の失敗は対応済み（新しい失敗なし）",
                "detail": bad[0].get("target_url"),
                "source": "ops_fail_watch",
                "cursor_prompt": "Vercel デプロイ状態を確認して。",
                "status": "active",
                "checked_at": now_iso(),
                "payload": _ephemeral_payload(
                    show_banner=False,
                    statuses=bad,
                    resolved_keys=sorted(resolved_keys),
                ),
            }
        bits = []
        for s in unresolved:
            bits.append(
                f"{s.get('context')}: {s.get('description') or s.get('state')}"
            )
        url = unresolved[0].get("target_url")
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
            "payload": _ephemeral_payload(
                show_banner=True,
                statuses=unresolved,
                fail_keys=[_vercel_status_key(s) for s in unresolved],
            ),
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
            "payload": _ephemeral_payload(show_banner=False),
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
        "payload": _ephemeral_payload(show_banner=False, statuses=vercel),
    }


def check_gha_workflows(*, resolved_run_ids: set[str] | None = None) -> dict[str, Any]:
    """監視対象 workflow の直近失敗を列挙。"""
    resolved_run_ids = resolved_run_ids or set()
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
            "payload": _ephemeral_payload(show_banner=True),
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
            "payload": _ephemeral_payload(show_banner=True),
        }

    if fails:
        unresolved = [
            f
            for f in fails
            if str(f.get("databaseId") or "") not in resolved_run_ids
        ]
        if not unresolved:
            return {
                "id": "gha_workflow_fail",
                "title": "GitHub Actions",
                "category": "ops",
                "level": "ok",
                "summary": "直近の失敗は対応済み（新しい失敗なし）",
                "detail": fails[0].get("url"),
                "source": "ops_fail_watch",
                "cursor_prompt": "GitHub Actions の失敗有無を確認して。",
                "status": "active",
                "checked_at": now_iso(),
                "payload": _ephemeral_payload(
                    show_banner=False,
                    fails=fails,
                    resolved_run_ids=sorted(resolved_run_ids),
                ),
            }
        bits = [
            f"{f.get('workflow')}: {f.get('displayTitle') or f.get('conclusion')}"
            for f in unresolved
        ]
        return {
            "id": "gha_workflow_fail",
            "title": "GitHub Actions失敗",
            "category": "ops",
            "level": "attention",
            "summary": " / ".join(bits)[:400],
            "detail": unresolved[0].get("url"),
            "source": "ops_fail_watch",
            "cursor_prompt": (
                "失敗した GitHub Actions のログを見て直して。"
                " 直したら `python scripts/jarvis_ops_fail_watch.py --push --note '…'` でお知らせ。"
            ),
            "status": "active",
            "checked_at": now_iso(),
            "payload": _ephemeral_payload(
                show_banner=True,
                fails=unresolved,
                fail_run_ids=[
                    str(f.get("databaseId"))
                    for f in unresolved
                    if f.get("databaseId") is not None
                ],
            ),
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
        "payload": _ephemeral_payload(show_banner=False),
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
        "cursor_prompt": (
            "ホーム／状況ウォッチの「Jarvisが直したよ」を確認し、"
            "「確認しました」で消してよい（アーカイブしない）。"
        ),
        "status": "active",
        "checked_at": now_iso(),
        "payload": _ephemeral_payload(
            show_banner=True,
            note=note,
            fixed_at=datetime.now(timezone.utc).isoformat(),
        ),
    }


def _resolve_fail_item(it: dict[str, Any], *, note: str) -> dict[str, Any]:
    """--note 時: 失敗バナーを消し、当該失敗を対応済みとして記録する。"""
    wid = str(it.get("id") or "")
    pl = dict(it.get("payload") or {}) if isinstance(it.get("payload"), dict) else {}
    out = dict(it)
    if wid == "gha_workflow_fail":
        fail_ids = _as_id_set(pl.get("fail_run_ids")) | {
            str(f.get("databaseId"))
            for f in (pl.get("fails") or [])
            if isinstance(f, dict) and f.get("databaseId") is not None
        }
        out["title"] = "GitHub Actions"
        out["level"] = "ok"
        out["summary"] = "修正済み（Jarvisが直したよを確認）"
        out["payload"] = _ephemeral_payload(
            show_banner=False,
            fails=pl.get("fails") or [],
            resolved_run_ids=sorted(fail_ids),
            resolved_at=datetime.now(timezone.utc).isoformat(),
            resolved_note=note[:300],
        )
        return out
    if wid == "vercel_deploy":
        keys = _as_id_set(pl.get("fail_keys")) | {
            _vercel_status_key(s)
            for s in (pl.get("statuses") or [])
            if isinstance(s, dict)
        }
        out["title"] = "Vercelデプロイ"
        out["level"] = "ok"
        out["summary"] = "修正済み（Jarvisが直したよを確認）"
        out["payload"] = _ephemeral_payload(
            show_banner=False,
            statuses=pl.get("statuses") or [],
            resolved_keys=sorted(keys),
            resolved_at=datetime.now(timezone.utc).isoformat(),
            resolved_note=note[:300],
        )
        return out
    return out


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
        "status": "active",
        "archived_at": None,
        "checked_at": it.get("checked_at") or now_iso(),
        "payload": it.get("payload") or _ephemeral_payload(show_banner=False),
        "updated_at": now_iso(),
    }


def _load_resolved_maps(sb: Any | None) -> tuple[set[str], set[str]]:
    """既存 payload から対応済み run / Vercel key を読む。"""
    run_ids: set[str] = set()
    keys: set[str] = set()
    if sb is None:
        return run_ids, keys
    try:
        er = (
            sb.table("watch_status")
            .select("id,payload")
            .in_("id", list(AUTOFIX_IDS))
            .execute()
        )
        for row in er.data or []:
            pl = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            wid = str(row.get("id") or "")
            if wid == "gha_workflow_fail":
                run_ids |= _as_id_set(pl.get("resolved_run_ids"))
            elif wid == "vercel_deploy":
                keys |= _as_id_set(pl.get("resolved_keys"))
    except Exception as e:
        print(f"# resolved map skip: {e}", file=sys.stderr)
    return run_ids, keys


def collect_items(
    *,
    note: str | None = None,
    resolved_run_ids: set[str] | None = None,
    resolved_keys: set[str] | None = None,
) -> list[dict[str, Any]]:
    items = [
        check_vercel_main(resolved_keys=resolved_keys),
        check_gha_workflows(resolved_run_ids=resolved_run_ids),
    ]
    if note:
        # 失敗ピンは「要確認」のまま残さず、「直したよ」へ切り替える
        fixed: list[dict[str, Any]] = []
        for it in items:
            if it.get("id") in AUTOFIX_IDS:
                if (it.get("level") or "") in ("attention", "warn"):
                    it = _resolve_fail_item(it, note=note)
                else:
                    pl = dict(it.get("payload") or {})
                    pl["show_banner"] = False
                    pl["never_archive"] = True
                    pl["ephemeral"] = True
                    it = {**it, "payload": pl}
            fixed.append(it)
        items = fixed
        items.append(make_fix_notice(note))
    return items


def _sb_client():
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要")
    from supabase import create_client

    return create_client(url, key)


def _build_autofix_prompt(it: dict[str, Any]) -> str:
    return "\n".join(
        [
            "あなたは Jarvis（運用修復 Cloud Agent）です。",
            "リポジトリ m19mhrts83-cyber/project-GE の失敗を直してください。",
            "秘密（APIキー等）は出力しない。対外メール送信はしない。",
            "手順:",
            "1. 失敗内容を確認（下記 summary / detail。必要なら gh / npm run build）",
            "2. 最小修正をコミットして push（無関係ファイルは触らない）",
            "3. autoCreatePR で draft PR を作る（BugBot が PR 上の残バグを拾える）",
            "4. 直したら可能なら `python scripts/jarvis_ops_fail_watch.py --push --note '直した内容'`",
            "対外メール送信はしない。無関係なリファクタはしない。",
            "",
            f"watch_id: {it.get('id')}",
            f"title: {it.get('title')}",
            f"level: {it.get('level')}",
            f"summary: {it.get('summary')}",
            f"detail: {it.get('detail')}",
            "",
            "cursor_prompt:",
            str(it.get("cursor_prompt") or ""),
        ]
    )


def _existing_ops_status(sb, watch_id: str) -> str:
    try:
        r = (
            sb.table("watch_status")
            .select("payload")
            .eq("id", watch_id)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        row = rows[0] if rows else {}
        pl = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        ops = pl.get("cursor_ops_fix") if isinstance(pl.get("cursor_ops_fix"), dict) else {}
        return str(ops.get("status") or "")
    except Exception:
        return ""


def _patch_ops_payload(sb, watch_id: str, ops_patch: dict[str, Any], *, keep_banner: bool = True) -> None:
    r = (
        sb.table("watch_status")
        .select("payload")
        .eq("id", watch_id)
        .limit(1)
        .execute()
    )
    rows = r.data or []
    row = rows[0] if rows else {}
    pl = dict(row.get("payload") or {}) if isinstance(row.get("payload"), dict) else {}
    ops = dict(pl.get("cursor_ops_fix") or {}) if isinstance(pl.get("cursor_ops_fix"), dict) else {}
    ops.update(ops_patch)
    pl["cursor_ops_fix"] = ops
    if keep_banner:
        pl["show_banner"] = True
    pl["origin"] = pl.get("origin") or "ops_fail_watch"
    pl["never_archive"] = True
    pl["ephemeral"] = True
    sb.table("watch_status").update(
        {"payload": pl, "updated_at": now_iso()}
    ).eq("id", watch_id).execute()


def run_autofix(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """要対応の Fail に対し Cloud 起動。失敗・上限ならローカル queued。"""
    from jarvis_cloud_agent_launch import launch_cloud_agent

    sb = _sb_client()
    notices: list[str] = []
    for it in items:
        wid = str(it.get("id") or "")
        if wid not in AUTOFIX_IDS:
            continue
        if (it.get("level") or "") not in ("attention", "warn"):
            continue
        existing = _existing_ops_status(sb, wid)
        if existing in BUSY_STATUSES:
            print(f"# autofix skip {wid}: already {existing}", file=sys.stderr)
            continue

        prompt = _build_autofix_prompt(it)
        launched = launch_cloud_agent(
            prompt=prompt,
            name=f"jarvis-ops-{wid}"[:80],
            auto_create_pr=True,
        )
        if launched.get("ok"):
            _patch_ops_payload(
                sb,
                wid,
                {
                    "status": "launched",
                    "via": "cloud",
                    "agent_id": launched.get("agent_id"),
                    "run_id": launched.get("run_id"),
                    "url": launched.get("url"),
                    "launched_at": datetime.now(timezone.utc).isoformat(),
                    "prompt": prompt[:1500],
                },
            )
            notices.append(
                f"Cloud Agent で {wid} の修復を起動した → {launched.get('url')}"
            )
            print(f"# autofix cloud ok {wid} {launched.get('url')}", file=sys.stderr)
            continue

        # Cloud 失敗 → ローカル待ち
        reason = str(launched.get("error") or "cloud failed")
        limit = bool(launched.get("limit"))
        _patch_ops_payload(
            sb,
            wid,
            {
                "status": "queued",
                "via": "local_fallback",
                "queued_at": datetime.now(timezone.utc).isoformat(),
                "cloud_error": reason[:400],
                "cloud_limit": limit,
                "prompt": prompt[:1500],
            },
        )
        if limit:
            notices.append(
                f"Cloud 上限／枠のため {wid} はローカル待ちにした（Mac Worker／朝起動で処理）"
            )
        else:
            notices.append(
                f"Cloud 起動できず {wid} をローカル待ちにした: {reason[:120]}"
            )
        print(f"# autofix local queue {wid}: {reason}", file=sys.stderr)

    extra: list[dict[str, Any]] = []
    for n in notices:
        # 起動お知らせだけ（失敗ピンはまだ消さない）
        extra.append(make_fix_notice(n, level="info"))
    return extra


def push_items(items: list[dict[str, Any]]) -> int:
    try:
        sb = _sb_client()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1

    # 既存の cursor_ops_fix / 確認済みフラグを潰さないよう merge
    existing_payload: dict[str, dict[str, Any]] = {}
    try:
        er = (
            sb.table("watch_status")
            .select("id,payload")
            .in_("id", list(OPS_EPHEMERAL_IDS))
            .execute()
        )
        for row in er.data or []:
            pl = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            existing_payload[str(row["id"])] = pl
    except Exception as e:
        print(f"# payload merge skip: {e}", file=sys.stderr)

    rows = []
    for it in items:
        row = to_row(it)
        prev = existing_payload.get(str(it["id"])) or {}
        merged = dict(row["payload"] or {})
        # 対応済み ID は今回分と既存を合算（新しい失敗は fail_* 側）
        if it["id"] == "gha_workflow_fail":
            merged["resolved_run_ids"] = sorted(
                _as_id_set(prev.get("resolved_run_ids"))
                | _as_id_set(merged.get("resolved_run_ids"))
            )
        if it["id"] == "vercel_deploy":
            merged["resolved_keys"] = sorted(
                _as_id_set(prev.get("resolved_keys"))
                | _as_id_set(merged.get("resolved_keys"))
            )
        if prev.get("cursor_ops_fix"):
            # 失敗が再発（attention）したら修復ステータスは残しつつバナーは今回優先
            if (it.get("level") or "") in ("attention", "warn"):
                ops = dict(prev["cursor_ops_fix"])
                if str(ops.get("status") or "") in ("done", "resolved"):
                    ops["status"] = "reopened"
                merged["cursor_ops_fix"] = ops
            else:
                merged["cursor_ops_fix"] = prev["cursor_ops_fix"]
        # ops_fix_notice: 新しい note があるときだけ上書き。無ければ既存の確認状態を維持
        if it["id"] == "ops_fix_notice":
            if merged.get("show_banner") is True:
                # 新しいお知らせ
                pass
            elif prev.get("acknowledged_at") and prev.get("show_banner") is False:
                merged["show_banner"] = False
                merged["acknowledged_at"] = prev.get("acknowledged_at")
        row["payload"] = merged
        # ephemeral は常に active（アーカイブ積み上げしない）
        row["status"] = "active"
        row["archived_at"] = None
        rows.append(row)
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
        "--autofix",
        action="store_true",
        help="要対応 Fail を Cloud Agent 起動（失敗時はローカル queued）",
    )
    ap.add_argument(
        "--note",
        default="",
        help="修正内容をホームお知らせ（ops_fix_notice）に載せる",
    )
    args = ap.parse_args(argv)
    if not args.dry_run and not args.push:
        args.dry_run = True

    resolved_run_ids: set[str] = set()
    resolved_keys: set[str] = set()
    if args.push or args.note:
        try:
            sb = _sb_client()
            resolved_run_ids, resolved_keys = _load_resolved_maps(sb)
        except Exception as e:
            print(f"# resolved preload skip: {e}", file=sys.stderr)

    items = collect_items(
        note=args.note or None,
        resolved_run_ids=resolved_run_ids,
        resolved_keys=resolved_keys,
    )
    print(json.dumps({"count": len(items), "items": items}, ensure_ascii=False, indent=2))
    if args.dry_run:
        return 0
    rc = push_items(items)
    if rc != 0:
        return rc
    if args.autofix:
        try:
            extra = run_autofix(items)
        except Exception as e:
            print(f"# autofix error: {e}", file=sys.stderr)
            extra = [
                make_fix_notice(
                    f"自動修復の起動に失敗: {e}",
                    level="warn",
                )
            ]
        if extra:
            push_items(extra)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
