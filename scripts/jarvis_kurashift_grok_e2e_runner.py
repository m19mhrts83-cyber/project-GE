#!/usr/bin/env python3
"""Grok × estate × KURASHIFT パイプライン通しテスト（Phase 5）。

内部パイプラインのみ実送信（estate 宛 Grok レポート）。対外第一問合せは --dry-run。
fixture 返信を seed して ops パックまで検証。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_grok_e2e_runner.py
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_grok_e2e_runner.py --cleanup
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")
E2E_MARKER = "E2E-GROK-KURASHIFT"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sb_client():
    import os

    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です")
    from supabase import create_client

    return create_client(url, key)


def fixture_body(report_id: str) -> str:
    return f"""---
source: grok_bot
bot: 物件調査
report_id: {report_id}
e2e: {E2E_MARKER}
---

## 物件
- 所在: 愛知県岡崎市羽根町（{E2E_MARKER}・対外送信禁止）
- 価格_万: 1200
- 土地面積: 150㎡
- 建物: 戸建 築40年
- 駐車場: あり
- URL: https://example.com/e2e-test-only

## 土地評価
- 方式: 倍率
- 路線価_万円_坪: 12
- 倍率: 1.2
- 土地積算_万円: 1300
- 土地値100%_比率: 108%
- 土地値100%判定: 聞く
- 根拠URL: https://www.chikamap.jp/chikamap/Map

## ハザード（重ねるハザードマップ）
- 調査URL: https://disaportal.gsi.go.jp/maps/
- 洪水: なし
- 土砂: なし
- 高潮: なし
- 内水: なし
- 評価: OK
- 根拠URL: https://disaportal.gsi.go.jp/maps/

## 人口（チャプロ軸）
- 評価: 安全
- 表: 人口横ばい・世帯数微増

## 総合
- 聞く価値: 聞く
- 理由1行: E2E通しテスト用（倍率・土地値108%・HZ OK）
"""


def run_cmd(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    cmd = [str(PY), *args]
    print(f"# run: {' '.join(cmd)}", file=sys.stderr)
    cp = subprocess.run(
        cmd,
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=None,
    )
    if cp.stdout:
        print(cp.stdout, end="")
    if cp.stderr:
        print(cp.stderr, end="", file=sys.stderr)
    if check and cp.returncode != 0:
        raise RuntimeError(f"command failed rc={cp.returncode}: {' '.join(args)}")
    return cp


def find_deal_by_report_id(sb, report_id: str) -> dict | None:
    rows = (
        sb.table("kurashift_re_deals")
        .select("*")
        .eq("source", "mail_grok")
        .order("created_at", desc=True)
        .limit(50)
        .execute()
        .data
        or []
    )
    for r in rows:
        grok = (r.get("summary_json") or {}).get("grok") or {}
        if grok.get("report_id") == report_id:
            return r
        if E2E_MARKER in str(r.get("title") or ""):
            return r
    return None


def seed_fixture_thread(sb, deal: dict) -> None:
    """ops パック用に fixture 問合せ＋返信を DB に載せる（Gmail 送信なし）。"""
    deal_id = deal["id"]
    now = now_iso()
    thread_id = f"e2e-thread-{deal_id[:8]}"
    out_gid = f"e2e-out-{deal_id[:8]}"
    in_gid = f"e2e-in-{deal_id[:8]}"
    rows = [
        {
            "deal_id": deal_id,
            "kind": "first_inquiry",
            "direction": "outbound",
            "gmail_id": out_gid,
            "thread_id": thread_id,
            "subject": "物件資料のご依頼（E2Eテスト）",
            "body_text": "E2E fixture outbound（送信なし）",
            "from_email": "matsuno.estate@gmail.com",
            "to_email": "e2e-agent@example.com",
            "occurred_at": now,
            "payload": {"account": "mail_estate", "e2e": True},
        },
        {
            "deal_id": deal_id,
            "kind": "reply",
            "direction": "inbound",
            "gmail_id": in_gid,
            "thread_id": thread_id,
            "subject": "Re: 物件資料のご依頼（E2Eテスト）",
            "body_text": "E2E fixture inbound — 資料送付可否の返信サンプル",
            "from_email": "e2e-agent@example.com",
            "to_email": "matsuno.estate@gmail.com",
            "occurred_at": now,
            "payload": {"e2e": True},
        },
    ]
    for row in rows:
        try:
            sb.table("kurashift_re_deal_messages").insert(row).execute()
        except Exception as e:
            if "duplicate" not in str(e).lower() and "23505" not in str(e):
                raise
    sb.table("kurashift_re_deals").update(
        {
            "inquiry_status": "has_reply",
            "inquiry_thread_id": thread_id,
            "updated_at": now,
        }
    ).eq("id", deal_id).execute()


def cleanup_e2e(sb) -> int:
    rows = (
        sb.table("kurashift_re_deals")
        .select("id, title")
        .eq("source", "mail_grok")
        .limit(100)
        .execute()
        .data
        or []
    )
    n = 0
    for r in rows:
        if E2E_MARKER not in str(r.get("title") or ""):
            grok = (
                sb.table("kurashift_re_deals")
                .select("summary_json")
                .eq("id", r["id"])
                .single()
                .execute()
                .data
                or {}
            )
            sj = grok.get("summary_json") or {}
            if sj.get("e2e") != E2E_MARKER and E2E_MARKER not in str(
                (sj.get("grok") or {}).get("location") or ""
            ):
                continue
        did = r["id"]
        sb.table("kurashift_re_deal_messages").delete().eq("deal_id", did).execute()
        cons = (
            sb.table("kurashift_consultations")
            .select("id")
            .contains("metadata", {"deal_id": did})
            .execute()
            .data
            or []
        )
        for c in cons:
            sb.table("kurashift_consultations").delete().eq("id", c["id"]).execute()
        sb.table("kurashift_re_deals").delete().eq("id", did).execute()
        n += 1
        print(f"  cleaned deal {did[:8]} …")
    print(f"📎 e2e cleanup: removed {n} deal(s)")
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-send", action="store_true", help="Grok レポート送信をスキップ（再取込のみ）")
    ap.add_argument("--report-id", default="", help="既存 report_id で再検証")
    ap.add_argument("--cleanup", action="store_true", help="E2E fixture 案件を削除")
    args = ap.parse_args()
    sb = sb_client()

    if args.cleanup:
        cleanup_e2e(sb)
        return 0

    report_id = args.report_id or datetime.now().strftime("E2E-%Y%m%d-%H%M%S")
    steps: list[dict] = []

    if not args.skip_send:
        body = fixture_body(report_id)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as tf:
            tf.write(body)
            tf_path = tf.name
        try:
            run_cmd(
                [
                    "scripts/jarvis_grok_report_mail.py",
                    "--file",
                    tf_path,
                    "--subject",
                    f"[Grok調査] 岡崎 {E2E_MARKER}",
                    "--send",
                ]
            )
            steps.append({"step": "grok_report_send", "ok": True, "report_id": report_id})
        finally:
            Path(tf_path).unlink(missing_ok=True)
    else:
        steps.append({"step": "grok_report_send", "ok": True, "skipped": True})

    ingest_ok = False
    for attempt in range(5):
        run_cmd(
            [
                "scripts/jarvis_kurashift_property_mail_match.py",
                "--grok-only",
                "--apply",
                "--days",
                "3",
            ]
        )
        deal = find_deal_by_report_id(sb, report_id)
        if deal:
            ingest_ok = True
            break
        if attempt < 4:
            time.sleep(4)
    steps.append({"step": "mail_grok_ingest", "ok": ingest_ok})
    if not ingest_ok:
        deal = None
    if not deal:
        print(
            f"KURASHIFT_RESULT:{json.dumps({'ok': False, 'error': 'deal not found', 'report_id': report_id}, ensure_ascii=False)}"
        )
        return 1

    deal_id = deal["id"]
    grok = (deal.get("summary_json") or {}).get("grok") or {}
    checks = {
        "status_viewing": deal.get("status") == "viewing",
        "listen_聞く": grok.get("listen_value") == "聞く",
        "land_bairitsu": "倍率" in str(grok.get("land_method") or ""),
        "hazard_ok": grok.get("hazard_eval") == "OK",
    }
    steps.append({"step": "deal_assertions", "ok": all(checks.values()), "checks": checks, "deal_id": deal_id})
    if not all(checks.values()):
        print(json.dumps(steps, ensure_ascii=False, indent=2))
        return 1

    prev_cp = run_cmd(
        ["scripts/jarvis_kurashift_re_inquiry.py", "--preview-deal-id", deal_id]
    )
    prev_ok = "from_account" in prev_cp.stdout and "estate" in prev_cp.stdout
    bairitsu_ok = "倍率地域" in prev_cp.stdout or "固定資産" in prev_cp.stdout
    steps.append(
        {
            "step": "inquiry_preview",
            "ok": prev_ok and bairitsu_ok,
            "from_estate": prev_ok,
            "bairitsu_block": bairitsu_ok,
        }
    )

    dry_cp = run_cmd(
        [
            "scripts/jarvis_kurashift_re_inquiry.py",
            "--send-deal-id",
            deal_id,
            "--to",
            "e2e-agent@example.com",
            "--dry-run",
        ]
    )
    steps.append({"step": "inquiry_send_dry_run", "ok": "dry_run" in dry_cp.stdout})

    run_cmd(["scripts/jarvis_kurashift_re_inquiry.py", "--poll-replies", "--deal-id", deal_id])
    steps.append({"step": "poll_replies", "ok": True, "note": "real poll; 0 new is OK"})

    seed_fixture_thread(sb, deal)
    steps.append({"step": "seed_fixture_messages", "ok": True})

    pack_cp = run_cmd(
        [
            "scripts/jarvis_kurashift_re_inquiry.py",
            "--build-ops-pack",
            "--deal-id",
            deal_id,
        ]
    )
    cid = ""
    for line in pack_cp.stdout.splitlines():
        if line.startswith("KURASHIFT_RESULT:"):
            payload = json.loads(line.split(":", 1)[1])
            cid = str(payload.get("consultation_id") or "")
    steps.append({"step": "ops_pack", "ok": bool(cid), "consultation_id": cid})

    all_ok = all(s.get("ok") for s in steps)
    result = {
        "ok": all_ok,
        "report_id": report_id,
        "deal_id": deal_id,
        "consultation_id": cid,
        "steps": steps,
        "cleanup": f"{PY} scripts/jarvis_kurashift_grok_e2e_runner.py --cleanup",
    }
    print(f"\n📎 Grok E2E {'PASS' if all_ok else 'FAIL'}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"KURASHIFT_RESULT:{json.dumps(result, ensure_ascii=False)}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
