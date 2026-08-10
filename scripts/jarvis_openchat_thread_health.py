#!/usr/bin/env python3
"""
815 オプチャ・スレッド取得健全性 → sync_meta + watch_status

静かな失敗（登録0件で正常終了・追記0が続く等）と、
メイン鮮度（全ルートで直近N日【メイン】0＋常時監視は稼働）を検知し、
ダッシュボード /openchat/health 用の JSON を push する。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_openchat_thread_health.py
  python scripts/jarvis_openchat_thread_health.py --dry-run
  python scripts/jarvis_openchat_thread_health.py --push
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE = REPO / ".jarvis_state"
HEALTH_PATH = STATE / "openchat_thread_health.json"
ROUTES_YAML = REPO / "line_unofficial_poc" / "open_chat_routes.yaml"
WATCH_STATUS = (
    REPO / "line_unofficial_poc" / ".line_auth" / ".chrline_open_chat_watch_status.json"
)
OPENCHAT_BASE = Path(
    "~/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    "/C2_ルーティン作業/26_パートナー社への相談/815_神大家オプチャ"
).expanduser()

BOOTSTRAP_HINT = (
    "cd ~/git-repos/line_unofficial_poc && ./launchd/open_chat_watch_pause.sh && "
    "./run_patch.sh chrline_open_chat_to_md.py --allow-qr-login "
    "--discover-only --discover-thread-mids --init --auto-append-thread-mids "
    "--route-ids {route_id} --min-hit-count 1 --max-pages-per-stream 80 && "
    "./run_patch.sh chrline_open_chat_to_md.py --allow-qr-login --init --no-main "
    "--route-ids {route_id} --join-threads-yes --max-pages-per-stream 80 && "
    "./launchd/open_chat_watch_resume.sh"
)

MAC_RECIPE_ID = "openchat_init_bootstrap"
# 全ルート【メイン】0 が続く日数（既定3）。環境変数で上書き可。
MAIN_STALE_DAYS = max(1, int(os.environ.get("JARVIS_OPENCHAT_MAIN_STALE_DAYS") or "3"))
# 常時監視「稼働中」とみなす heartbeat 上限（秒）
WATCH_ALIVE_HB_SEC = max(60, int(os.environ.get("JARVIS_OPENCHAT_WATCH_ALIVE_HB_SEC") or "300"))


def now_iso() -> str:
    return datetime.now(tz=JST).isoformat(timespec="seconds")


def today() -> date:
    return datetime.now(tz=JST).date()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def load_routes() -> list[dict[str, Any]]:
    try:
        import yaml
    except Exception:
        print("エラー: PyYAML が必要です", file=sys.stderr)
        return []
    if not ROUTES_YAML.is_file():
        return []
    data = yaml.safe_load(ROUTES_YAML.read_text(encoding="utf-8")) or {}
    routes = data.get("routes") or []
    out = []
    for r in routes:
        if not isinstance(r, dict):
            continue
        out.append(
            {
                "id": str(r.get("id") or "").strip(),
                "org_label": str(r.get("org_label") or r.get("title_substring") or "").strip(),
                "include_threads": bool(r.get("include_threads", True)),
                "include_main": bool(r.get("include_main", True)),
                "thread_mids": [str(x) for x in (r.get("thread_mids") or []) if x],
                "output_md": Path(str(r.get("output_md") or "")).expanduser(),
            }
        )
    return [r for r in out if r["id"]]


def count_md_headings(md: Path, *, days: int = 14) -> dict[str, int]:
    """直近 N 日の 【スレッド】/【スレッド返信】 件数。"""
    result = {"thread": 0, "reply": 0, "main": 0}
    if not md.is_file():
        return result
    try:
        text = md.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return result
    start = today() - timedelta(days=max(0, days - 1))
    # ### YYYY/MM/DD HH:MM …【スレッド】
    for m in re.finditer(
        r"^### (\d{4}/\d{2}/\d{2}).*?(【スレッド返信】|【スレッド】|【メイン】)",
        text,
        re.M,
    ):
        try:
            d = datetime.strptime(m.group(1), "%Y/%m/%d").date()
        except ValueError:
            continue
        if d < start:
            continue
        kind = m.group(2)
        if kind == "【スレッド】":
            result["thread"] += 1
        elif kind == "【スレッド返信】":
            result["reply"] += 1
        else:
            result["main"] += 1
    return result


def daily_thread_series(routes: list[dict[str, Any]], *, days: int = 30) -> list[dict[str, Any]]:
    """日付ごとの【スレッド】追記件数（route内訳付き）。"""
    start = today() - timedelta(days=days - 1)
    by_day: dict[str, dict[str, int]] = {}
    for i in range(days):
        d = start + timedelta(days=i)
        by_day[d.isoformat()] = {}

    for route in routes:
        md = route["output_md"]
        if not md.is_file():
            continue
        try:
            text = md.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rid = route["id"]
        for m in re.finditer(r"^### (\d{4}/\d{2}/\d{2}).*?【スレッド】", text, re.M):
            try:
                d = datetime.strptime(m.group(1), "%Y/%m/%d").date()
            except ValueError:
                continue
            if d < start:
                continue
            key = d.isoformat()
            if key not in by_day:
                by_day[key] = {}
            by_day[key][rid] = by_day[key].get(rid, 0) + 1

    series = []
    for key in sorted(by_day.keys()):
        routes_counts = by_day[key]
        series.append(
            {
                "date": key,
                "total": sum(routes_counts.values()),
                "routes": routes_counts,
            }
        )
    return series


def heartbeat_age_sec(watch: dict[str, Any]) -> float | None:
    hb = watch.get("heartbeat_at") or watch.get("updated_at")
    if not hb:
        return None
    try:
        dt = datetime.fromisoformat(str(hb).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)
        return (datetime.now(tz=JST) - dt.astimezone(JST)).total_seconds()
    except Exception:
        return None


def evaluate_main_freshness(
    routes: list[dict[str, Any]],
    watch: dict[str, Any],
    hb_age: float | None,
    *,
    days: int = MAIN_STALE_DAYS,
) -> dict[str, Any]:
    """
    メイン鮮度: include_main な全ルートで直近 N 日【メイン】0、かつ常時監視が稼働中。
    → 取込自体が止まっている疑い（スレ bootstrap とは別レイヤー）。
    """
    targets = [r for r in routes if r.get("include_main", True)]
    per_route: list[dict[str, Any]] = []
    readable = 0
    for route in targets:
        md = route["output_md"]
        exists = md.is_file()
        counts = count_md_headings(md, days=days) if exists else {"main": 0, "thread": 0, "reply": 0}
        if exists:
            readable += 1
        per_route.append(
            {
                "route_id": route["id"],
                "org_label": route.get("org_label") or route["id"],
                "md_readable": exists,
                "md_main": int(counts.get("main") or 0),
            }
        )
    total_main = sum(int(x["md_main"]) for x in per_route)
    routes_with_main = sum(1 for x in per_route if int(x["md_main"]) > 0)
    state = str(watch.get("state") or "")
    watch_alive = (
        state == "running"
        and hb_age is not None
        and hb_age <= WATCH_ALIVE_HB_SEC
    )
    # MD が読めない／ルートが少なすぎると誤検知しやすい
    enough = readable >= 2 and readable >= max(2, int(len(targets) * 0.5))
    all_zero = enough and total_main == 0 and routes_with_main == 0
    stale = bool(all_zero and watch_alive)
    level = "attention" if stale else "ok"
    summary = (
        f"メイン鮮度: 直近{days}日 全{readable}ルート【メイン】0（常時監視は稼働）→要確認"
        if stale
        else (
            f"メイン鮮度: 直近{days}日 合計{total_main}件"
            f"（{routes_with_main}/{readable}ルート）"
            if enough
            else f"メイン鮮度: MD読取不足（readable={readable}/{len(targets)}）"
        )
    )
    return {
        "days": days,
        "level": level,
        "stale": stale,
        "symptom": "main_stale_all_routes" if stale else "ok",
        "summary": summary,
        "total_main": total_main,
        "routes_with_main": routes_with_main,
        "routes_checked": readable,
        "routes_total": len(targets),
        "watch_alive": watch_alive,
        "watch_state": state or None,
        "heartbeat_age_sec": int(hb_age) if hb_age is not None else None,
        "routes": per_route,
        "remediation_hint": (
            "パートナー確認の LINE／オプチャ取込、または朝バンドル --with-line。"
            " QR／トークン切れなら Mac で再認証。"
            if stale
            else ""
        ),
    }


def evaluate_route(
    route: dict[str, Any],
    latest_entry: dict[str, Any] | None,
    history: dict[str, Any],
    md_counts: dict[str, int],
) -> dict[str, Any]:
    rid = route["id"]
    registered = len(route["thread_mids"])
    include = bool(route["include_threads"])
    replies_14 = int(md_counts.get("reply") or 0)
    threads_14 = int(md_counts.get("thread") or 0)
    main_14 = int(md_counts.get("main") or 0)

    level = "ok"
    reasons: list[str] = []
    action = ""
    symptom = ""

    if include and registered == 0 and (replies_14 > 0 or main_14 > 0):
        level = "attention"
        symptom = "silent_fail_empty_mids"
        if replies_14 > 0:
            reasons.append(
                f"thread_mids 未登録なのに直近14日【スレッド返信】{replies_14}件"
                "（専用スレ取得できていない静かな失敗）"
            )
        else:
            # メインだけ取れていて relatedMessageId が MD に無い典型。
            # 差分 discover では候補0になりやすい → --init で履歴スキャンが必要。
            reasons.append(
                f"thread_mids 未登録なのに直近14日【メイン】{main_14}件"
                "（スレは立っていても差分discoverでは拾えない。--init 要）"
            )
        action = BOOTSTRAP_HINT.format(route_id=rid)

    # 登録あり・7日連続 appended_threads=0、かつ main 追記あり
    if include and registered > 0 and level == "ok":
        days_zero = 0
        main_recent = 0
        for day in sorted(history.keys())[-7:]:
            day_routes = (history.get(day) or {}).get("routes") or {}
            ent = day_routes.get(rid) or {}
            if int(ent.get("appended_threads") or 0) == 0:
                days_zero += 1
            main_recent += int(ent.get("appended_main") or 0)
        # MD 側の main も参考
        if days_zero >= 7 and (main_recent > 0 or main_14 > 0) and threads_14 == 0:
            level = "attention"
            symptom = "zero_append_with_main"
            reasons.append(
                f"登録{registered}件なのに7日連続スレ追記0（メインは動いている）"
            )
            action = action or BOOTSTRAP_HINT.format(route_id=rid)

    deleted = int((latest_entry or {}).get("deleted") or 0)
    closed = int((latest_entry or {}).get("closed") or 0)
    ok_n = int((latest_entry or {}).get("ok") or 0)
    if registered > 0 and (deleted + closed) >= max(registered * 0.8, 1) and ok_n == 0:
        if level == "ok":
            level = "info"
        if not symptom:
            symptom = "mostly_deleted"
        reasons.append(
            f"登録の大半が deleted/closed（構造限界: deleted={deleted} closed={closed}）"
        )

    if include and registered == 0 and replies_14 == 0 and threads_14 == 0 and main_14 == 0:
        if level == "ok":
            level = "info"
            reasons.append("thread_mids 0件・直近スレ／メイン活動なし（問題なしの可能性）")

    return {
        "route_id": rid,
        "org_label": route["org_label"],
        "include_threads": include,
        "thread_mids_registered": registered,
        "md_threads_14d": threads_14,
        "md_replies_14d": replies_14,
        "md_main_14d": main_14,
        "appended_threads": int((latest_entry or {}).get("appended_threads") or 0),
        "appended_main": int((latest_entry or {}).get("appended_main") or 0),
        "ok": ok_n,
        "deleted": deleted,
        "closed": closed,
        "last_ok_at": (latest_entry or {}).get("last_ok_at"),
        "run_at": (latest_entry or {}).get("run_at"),
        "level": level,
        "symptom": symptom or ("ok" if level == "ok" else "other"),
        "reasons": reasons,
        "action": action,
        "needs_bootstrap": bool(action),
        "cursor_prompt_short": (
            f"/trouble-shooting\n"
            f"【期待】{route['org_label'] or rid} のスレッドが 5.やり取り.md に【スレッド】で入る\n"
            f"【実際】{'; '.join(reasons) if reasons else level}\n"
            f"【対象】route_id={rid}\n"
            f"【一手】{action or 'ダッシュボード /openchat/health の解消パネルへ'}"
            if level == "attention"
            else ""
        ),
    }


def build_cursor_prompt(
    *,
    symptom: str,
    attention_routes: list[dict[str, Any]],
    infra_notes: list[str],
    summary: str,
    main_freshness: dict[str, Any] | None = None,
) -> str:
    route_lines = []
    for r in attention_routes[:8]:
        rid = r.get("route_id") or ""
        route_lines.append(
            f"- {r.get('org_label') or rid} ({rid}): "
            + " / ".join((r.get("reasons") or [])[:2])
        )
    cmds: list[str] = []
    mf = main_freshness if isinstance(main_freshness, dict) else {}
    if symptom == "main_stale_all_routes" or mf.get("stale"):
        days = mf.get("days") or MAIN_STALE_DAYS
        return "\n".join(
            [
                "/trouble-shooting",
                "【期待】815 オプチャの【メイン】が各ルートの 5.やり取り.md に追記される",
                f"【実際】{summary}",
                "【症状コード】main_stale_all_routes",
                f"【鮮度窓】直近{days}日・全ルート【メイン】0（常時監視は稼働中）",
                "【切り分け】スレ bootstrap（--init discover）ではなく、メイン取込経路",
                "【推奨一手】",
                "- パートナー確認の後半（chrline_yoritoori_inbox_fetch / run_patch.sh）",
                "- または朝バンドル: jarvis_morning_mac_refresh.py --force --with-line",
                "- QR／V3_TOKEN_CLIENT_LOGGED_OUT なら Mac で再認証（Mac版LINEは終了）",
                "- Square 401 構造限界なら square_probe を確認",
                "【基盤メモ】",
                *(f"- {n}" for n in (infra_notes or ["なし"])),
                "【注意】Cloud から CHRLINE／QR は回さない。Mac 専用。",
            ]
        )

    ids = [str(r.get("route_id")) for r in attention_routes if r.get("needs_bootstrap")]
    if ids:
        joined = " ".join(ids)
        cmds.append(
            "cd ~/git-repos/line_unofficial_poc && ./launchd/open_chat_watch_pause.sh && "
            "./run_patch.sh chrline_open_chat_to_md.py --allow-qr-login "
            "--discover-only --discover-thread-mids --init --auto-append-thread-mids "
            f"--route-ids {joined} --min-hit-count 1 --max-pages-per-stream 80 && "
            "./run_patch.sh chrline_open_chat_to_md.py --allow-qr-login --init --no-main "
            f"--route-ids {joined} --join-threads-yes --max-pages-per-stream 80 && "
            "./launchd/open_chat_watch_resume.sh"
        )
    return "\n".join(
        [
            "/trouble-shooting",
            "【期待】815 オプチャのスレッドが route 別に【スレッド】として MD に追記される",
            f"【実際】{summary}",
            f"【症状コード】{symptom}",
            "【対象ルート】",
            *(route_lines or ["- （ルート attention なし）"]),
            "【基盤メモ】",
            *(f"- {n}" for n in (infra_notes or ["なし"])),
            "【推奨】",
            "- 静かな失敗（登録0＋メイン／返信あり）→ --init discover → YAML追記 → backfill",
            "- メイン全体が止まっている → パートナー確認／朝 --with-line／QR（スレ bootstrap ではない）",
            "- CHRLINE／QR／pause は Mac 専用（Cloud では回さない）",
            "- 方針が複数ある・構造限界なら Plan モードで整理",
            "【コマンド例】",
            *(cmds or ["- （既知レシピ対象なし。/openchat/health で状況確認）"]),
        ]
    )


def build_remediation(
    route_evals: list[dict[str, Any]],
    *,
    watch_level: str,
    watch_notes: list[str],
    err: str | None,
    hb_age: float | None,
    summary: str,
    existing_mac_recipe: dict[str, Any] | None = None,
    main_freshness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    attention_routes = [r for r in route_evals if r.get("level") == "attention"]
    silent = [
        r
        for r in attention_routes
        if r.get("symptom") in {"silent_fail_empty_mids", "zero_append_with_main"}
    ]
    infra_symptoms: list[str] = []
    if err:
        infra_symptoms.append("watch_write_error")
    if hb_age is not None and hb_age > 180:
        infra_symptoms.append("heartbeat_stale")
    if watch_level == "attention" and not infra_symptoms and watch_notes:
        infra_symptoms.append("watch_not_running")

    mf = main_freshness if isinstance(main_freshness, dict) else {}
    main_stale = bool(mf.get("stale"))

    # 優先: メイン取込停止 > スレ静かな失敗 > 基盤 > その他
    if main_stale:
        primary = "main_stale_all_routes"
    elif silent:
        primary = "silent_fail_empty_mids"
    elif any(r.get("symptom") == "zero_append_with_main" for r in attention_routes):
        primary = "zero_append_with_main"
    elif infra_symptoms:
        primary = infra_symptoms[0]
    elif attention_routes:
        primary = str(attention_routes[0].get("symptom") or "other")
    else:
        primary = "ok"

    cursor_prompt = build_cursor_prompt(
        symptom=primary,
        attention_routes=attention_routes,
        infra_notes=watch_notes,
        summary=summary,
        main_freshness=mf,
    )

    mac_recipe: dict[str, Any] | None = None
    # メイン鮮度問題のときはスレ bootstrap を主役にしない
    if silent and not main_stale:
        route_ids = [str(r["route_id"]) for r in silent if r.get("route_id")]
        # 進行中キューは上書きしない
        prev = existing_mac_recipe if isinstance(existing_mac_recipe, dict) else {}
        prev_status = str(prev.get("status") or "")
        if prev_status in {"queued", "running"} and prev.get("id") == MAC_RECIPE_ID:
            mac_recipe = prev
        else:
            mac_recipe = {
                "id": MAC_RECIPE_ID,
                "route_ids": route_ids,
                "label": "静かな失敗の --init discover＋バックフィル",
                "status": "idle",
            }
    elif isinstance(existing_mac_recipe, dict):
        prev_status = str(existing_mac_recipe.get("status") or "")
        if prev_status in {"queued", "running"} and existing_mac_recipe.get("id") == MAC_RECIPE_ID:
            mac_recipe = existing_mac_recipe

    if main_stale:
        hint = str(mf.get("remediation_hint") or "") or (
            "メイン全体が止まっている予兆。パートナー確認／朝 --with-line／QR。"
            " スレ bootstrap は後回し。"
        )
    elif silent:
        hint = "棒が細い＋メインはある → 静かな失敗の予兆。下の解消パネルへ。"
    elif infra_symptoms and not attention_routes:
        hint = "基盤（常時監視・書込）を先に確認。スレ bootstrap は主役ではない。"
    else:
        hint = ""

    return {
        "symptom": primary,
        "route_attention_count": len(attention_routes),
        "infra_attention": bool(infra_symptoms),
        "infra_symptoms": infra_symptoms,
        "main_stale": main_stale,
        "cursor_prompt": cursor_prompt,
        "mac_recipe": mac_recipe,
        "hint": hint,
    }


def build_report() -> dict[str, Any]:
    routes = load_routes()
    health = load_json(HEALTH_PATH)
    watch = load_json(WATCH_STATUS)
    history = health.get("history") if isinstance(health.get("history"), dict) else {}
    latest = health.get("latest") if isinstance(health.get("latest"), dict) else {}
    latest_routes = latest.get("routes") if isinstance(latest.get("routes"), dict) else {}

    route_evals: list[dict[str, Any]] = []
    for route in routes:
        md_counts = count_md_headings(route["output_md"], days=14)
        route_evals.append(
            evaluate_route(
                route,
                latest_routes.get(route["id"]),
                history,
                md_counts,
            )
        )

    level_rank = {"attention": 0, "warn": 1, "info": 2, "ok": 3}
    worst = "ok"
    for ev in route_evals:
        if level_rank.get(ev["level"], 9) < level_rank.get(worst, 9):
            worst = ev["level"]

    hb_age = heartbeat_age_sec(watch)
    watch_level = "ok"
    watch_notes: list[str] = []
    state = str(watch.get("state") or "")
    if not watch:
        watch_level = "attention"
        watch_notes.append("常時監視 status なし")
    elif state and state != "running":
        watch_level = "attention"
        watch_notes.append(f"launchd state={state}")
    if hb_age is not None and hb_age > 180:
        watch_level = "attention"
        watch_notes.append(f"heartbeat 停止（{int(hb_age)}秒前）")
    err = str(watch.get("last_write_error") or "").strip()
    if err:
        watch_level = "attention"
        watch_notes.append(f"書込エラー: {err[:120]}")

    if level_rank.get(watch_level, 9) < level_rank.get(worst, 9):
        worst = watch_level

    main_freshness = evaluate_main_freshness(routes, watch, hb_age)
    if level_rank.get(main_freshness.get("level") or "ok", 9) < level_rank.get(worst, 9):
        worst = str(main_freshness.get("level") or worst)

    attention_routes = [r for r in route_evals if r["level"] == "attention"]
    series = daily_thread_series(routes, days=30)
    threads_today = next(
        (s["total"] for s in series if s["date"] == today().isoformat()),
        0,
    )

    route_summary = f"ルート要確認 {len(attention_routes)}/{len(route_evals)}"
    infra_summary = (
        "基盤: " + " / ".join(watch_notes[:2]) if watch_notes else "基盤: 問題なし"
    )
    main_summary = str(main_freshness.get("summary") or "メイン鮮度: —")
    summary_parts = [
        route_summary,
        infra_summary,
        main_summary,
        f"今日【スレッド】{threads_today}件",
    ]
    if watch.get("state"):
        summary_parts.insert(0, f"launchd {watch.get('state')}")
    if hb_age is not None and hb_age < 120:
        summary_parts.append("heartbeat 直近")
    elif hb_age is not None:
        summary_parts.append(f"heartbeat {int(hb_age)}秒前")
    if attention_routes:
        summary_parts.append(
            "ルート問題: "
            + ", ".join(r["org_label"] or r["route_id"] for r in attention_routes[:3])
        )
    if main_freshness.get("stale"):
        summary_parts.append("メイン取込停止疑い")

    summary = " · ".join(summary_parts)

    # 既存 mac_recipe（queued/running）を維持するため、ローカル snapshot から読む
    existing_recipe = None
    last_report = health.get("last_report") if isinstance(health.get("last_report"), dict) else {}
    rem_prev = last_report.get("remediation") if isinstance(last_report.get("remediation"), dict) else {}
    if isinstance(rem_prev.get("mac_recipe"), dict):
        existing_recipe = rem_prev.get("mac_recipe")

    remediation = build_remediation(
        route_evals,
        watch_level=watch_level,
        watch_notes=watch_notes,
        err=err or None,
        hb_age=hb_age,
        summary=summary,
        existing_mac_recipe=existing_recipe,
        main_freshness=main_freshness,
    )

    return {
        "generated_at": now_iso(),
        "worst_level": worst,
        "summary": summary,
        "summary_split": {
            "route": route_summary,
            "infra": infra_summary,
            "main": main_summary,
            "route_attention_count": len(attention_routes),
            "infra_attention": remediation.get("infra_attention"),
            "main_stale": bool(main_freshness.get("stale")),
        },
        "main_freshness": main_freshness,
        "watch": {
            "state": watch.get("state"),
            "heartbeat_at": watch.get("heartbeat_at"),
            "heartbeat_age_sec": int(hb_age) if hb_age is not None else None,
            "last_append_at": watch.get("last_append_at"),
            "last_append_route": watch.get("last_append_route"),
            "last_write_error": err or None,
            "level": watch_level,
            "notes": watch_notes,
        },
        "batch": {
            "latest_day": health.get("latest_day"),
            "run_at": latest.get("run_at") or health.get("updated_at"),
        },
        "threads_today": threads_today,
        "attention_count": len(attention_routes),
        "routes": route_evals,
        "daily_series": series,
        "remediation": remediation,
        "source": "jarvis_openchat_thread_health",
    }


def sb_client():
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要")
    from supabase import create_client

    return create_client(url, key)


def push_report(report: dict[str, Any]) -> None:
    sb = sb_client()
    now = now_iso()

    # Supabase 上の進行中 mac_recipe を優先維持
    try:
        prev = (
            sb.table("watch_status")
            .select("payload")
            .eq("id", "openchat_threads")
            .limit(1)
            .execute()
        )
        rows = prev.data or []
        pl = rows[0].get("payload") if rows else None
        if isinstance(pl, dict):
            rem = pl.get("remediation") if isinstance(pl.get("remediation"), dict) else {}
            mr = rem.get("mac_recipe") if isinstance(rem.get("mac_recipe"), dict) else pl.get("mac_recipe")
            if isinstance(mr, dict) and str(mr.get("status") or "") in {"queued", "running"}:
                rem_out = report.get("remediation") if isinstance(report.get("remediation"), dict) else {}
                rem_out = dict(rem_out)
                rem_out["mac_recipe"] = mr
                report["remediation"] = rem_out
    except Exception as e:
        print(f"# preserve mac_recipe skip: {e}", file=sys.stderr)

    sb.table("sync_meta").upsert(
        {
            "key": "openchat_thread_health",
            "value": json.dumps(report, ensure_ascii=False),
            "updated_at": now,
        },
        on_conflict="key",
    ).execute()

    level = report.get("worst_level") or "info"
    remediation = report.get("remediation") if isinstance(report.get("remediation"), dict) else {}
    cursor_prompt = str(remediation.get("cursor_prompt") or "").strip() or (
        "ダッシュボード /openchat/health を確認。"
    )
    payload = {
        "origin": "openchat_thread_health",
        "show_banner": level in ("attention", "warn"),
        "worst_level": level,
        "heartbeat_at": (report.get("watch") or {}).get("heartbeat_at"),
        "threads_today": report.get("threads_today"),
        "attention_count": report.get("attention_count"),
        "routes": report.get("routes") or [],
        "batch_run_at": (report.get("batch") or {}).get("run_at"),
        "href": "/openchat/health",
        "summary_split": report.get("summary_split") or {},
        "main_freshness": report.get("main_freshness") or {},
        "remediation": remediation,
        "mac_recipe": remediation.get("mac_recipe"),
    }
    sb.table("watch_status").upsert(
        {
            "id": "openchat_threads",
            "title": "オプチャ・スレッド取得",
            "category": "ops",
            "level": level,
            "summary": report.get("summary") or "",
            "detail": "/openchat/health",
            "source": "openchat_thread_health",
            "cursor_prompt": cursor_prompt,
            "status": "active",
            "archived_at": None,
            "payload": payload,
            "checked_at": now,
            "updated_at": now,
        },
        on_conflict="id",
    ).execute()
    print("# pushed sync_meta.openchat_thread_health + watch_status.openchat_threads")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--push", action="store_true")
    args = ap.parse_args(argv)
    if not args.dry_run and not args.push:
        args.dry_run = True

    report = build_report()
    # ローカルにも保存（バッチ未実行でも MD 判定結果を残す）
    STATE.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "updated_at": report["generated_at"],
        "latest_day": today().isoformat(),
        "latest": {
            "run_at": report["generated_at"],
            "routes": {
                r["route_id"]: {
                    "route_id": r["route_id"],
                    "org_label": r["org_label"],
                    "include_threads": r["include_threads"],
                    "thread_mids_registered": r["thread_mids_registered"],
                    "appended_threads": r["appended_threads"],
                    "appended_main": r["appended_main"],
                    "ok": r["ok"],
                    "deleted": r["deleted"],
                    "closed": r["closed"],
                    "last_ok_at": r.get("last_ok_at"),
                    "run_at": r.get("run_at") or report["generated_at"],
                    "level": r["level"],
                }
                for r in (report.get("routes") or [])
            },
        },
        "history": load_json(HEALTH_PATH).get("history") or {},
        "last_report": {
            "worst_level": report.get("worst_level"),
            "summary": report.get("summary"),
            "attention_count": report.get("attention_count"),
            "summary_split": report.get("summary_split"),
            "main_freshness": report.get("main_freshness"),
            "remediation": report.get("remediation"),
        },
    }
    # history に今日の判定サマリを軽く載せる（バッチ統計が無ければ MD ベース）
    hist = snapshot["history"] if isinstance(snapshot["history"], dict) else {}
    day = today().isoformat()
    day_bucket = hist.get(day) if isinstance(hist.get(day), dict) else {}
    if not day_bucket.get("routes"):
        day_bucket["routes"] = snapshot["latest"]["routes"]
        day_bucket["run_at"] = report["generated_at"]
        hist[day] = day_bucket
        keep = sorted(hist.keys())[-30:]
        snapshot["history"] = {k: hist[k] for k in keep}
    HEALTH_PATH.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"# wrote {HEALTH_PATH} worst={report.get('worst_level')} "
        f"attention={report.get('attention_count')}",
        file=sys.stderr,
    )

    print(
        json.dumps(
            {
                "worst_level": report.get("worst_level"),
                "attention_count": report.get("attention_count"),
                "routes": len(report.get("routes") or []),
                "summary": report.get("summary"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if args.dry_run:
        return 0
    try:
        push_report(report)
    except Exception as e:
        print(f"# push failed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
