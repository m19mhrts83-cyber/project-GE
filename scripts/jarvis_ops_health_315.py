#!/usr/bin/env python3
"""315 連携健全性点検係 — WeStudy/GHA ＋ オプチャ ＋ Gmail token をまとめ Slack #ops へ。

使い方:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_ops_health_315.py
  ~/selenium_env/venv/bin/python scripts/jarvis_ops_health_315.py --post
  ~/selenium_env/venv/bin/python scripts/jarvis_ops_health_315.py --cloud --post --mark-checked
  # Mac補完（日曜21:45）: 異常時に既知復旧を1回だけ試す
  ~/selenium_env/venv/bin/python scripts/jarvis_ops_health_315.py --remediate-once --post --mark-checked

秘密は .env.jarvis_private（SLACK_WEBHOOK_AI_TEAM_OPS / CONSULT）。フォルダに URL を書かない。
Gmail token 点検は Mac 上の token_*.json が正（--cloud ではスキップ→Mac 21:45）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
PYTHON_MAC = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")
LOG_DIR = (
    REPO
    / "docs"
    / "AIエージェントチーム"
    / "300_品質・タスク運用管理室"
    / "315_連携健全性点検係"
    / "logs"
)
WATCH_STATUS = (
    REPO / "line_unofficial_poc" / ".line_auth" / ".chrline_open_chat_watch_status.json"
)
OPENCHAT_BASE = Path(
    "~/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    "/C2_ルーティン作業/26_パートナー社への相談/815_神大家オプチャ"
).expanduser()
WATCH_ERR = Path.home() / "Library/Logs/line_open_chat/watch.err.log"
WATCH_RESUME = REPO / "line_unofficial_poc" / "launchd" / "open_chat_watch_resume.sh"
FLOW_URL = (
    "https://flowforge-259747770348.asia-northeast1.run.app"
    "/flows/flow_zYjp6A4HDURefJhSm0h_zUtX"
)


def _run(cmd: list[str], *, timeout: int = 120) -> tuple[int, str]:
    try:
        p = subprocess.run(
            cmd,
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=os.environ.copy(),
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
    out = ((p.stdout or "") + ("\n" + p.stderr if p.stderr else "")).strip()
    return p.returncode, out


def _python() -> str:
    if PYTHON_MAC.is_file():
        return str(PYTHON_MAC)
    return sys.executable


def westudy_block(*, mark_checked: bool) -> tuple[str, str]:
    """Return (summary_line, full_block)."""
    py = _python()
    cmd = [py, str(REPO / "scripts" / "jarvis_westudy_weekly_check.py"), "--force"]
    if mark_checked:
        cmd.append("--mark-checked")
    code, out = _run(cmd, timeout=90)
    block = out.strip() or "📎 WeStudy週次\n- 状態: 出力なし"
    # 1行要約
    line = "確認失敗" if code != 0 else "OK"
    for m in re.finditer(r"^- .+$", block, re.M):
        s = m.group(0).lstrip("- ").strip()
        if "success" in s.lower() or "失敗" in s or "Fail" in s or "状態" in s:
            line = s[:120]
            break
    if "failure" in block.lower() or "Fail" in block:
        line = "⚠️ Fail疑い — 詳細はブロック参照"
    return line, block


def gmail_token_snapshot(
    *,
    cloud: bool = False,
    mark_prompted: bool = False,
) -> tuple[str, list[str], list[str]]:
    """Gmail OAuth token スコープ・refresh 点検。

    Returns (level, detail_lines, issues).
    cloud=True: Mac の token JSON が無いのでスキップ（本線は Mac 21:45）。
    """
    if cloud:
        return (
            "スキップ(cloud)",
            [
                "Gmail token: スキップ（Mac専用・token_*.json）",
                "補完: Mac launchd 日曜21:45（--remediate-once）",
            ],
            [],
        )

    if os.environ.get("JARVIS_GMAIL_TOKEN_HEALTH_DISABLE", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return "スキップ(disabled)", ["Gmail token: JARVIS_GMAIL_TOKEN_HEALTH_DISABLE=1"], []

    py = _python()
    cmd = [
        py,
        str(REPO / "scripts" / "jarvis_gmail_token_health.py"),
        "--json",
        "--force",
    ]
    if mark_prompted:
        cmd.append("--mark-prompted")
    code, out = _run(cmd, timeout=60)
    # --json は stdout に JSON。混在時は最後の {…} を拾う
    payload: dict = {}
    raw = (out or "").strip()
    try:
        # 末尾から JSON オブジェクトを探す
        idx = raw.rfind("{")
        if idx >= 0:
            payload = json.loads(raw[idx:])
    except json.JSONDecodeError:
        payload = {}

    if not payload and code != 0:
        return "要フォロー", [f"Gmail token: 点検失敗 rc={code}"], ["health_fail"]

    issues = [str(x) for x in (payload.get("issues") or [])]
    estate_send = bool(payload.get("estate_send_missing"))
    detail: list[str] = []
    if not issues:
        detail.append("Gmail token: OK（admin/estate/m19m 等・send含む）")
        return "OK", detail, []

    detail.append(f"Gmail token: 要フォロー（issues={','.join(issues)}）")
    if estate_send or "estate_send" in issues:
        detail.append(
            "是正: cd ~/git-repos/215_kamiooya/C1_cursor/1b_Cursorマニュアル "
            "&& ~/selenium_env/venv/bin/python reauth_estate_gmail_send.py"
        )
    else:
        detail.append(
            "是正: ~/selenium_env/venv/bin/python scripts/jarvis_gmail_token_health.py"
            "（表示コマンドでブラウザ再同意）"
        )
    # ログ用に短い行も
    for ln in payload.get("lines") or []:
        s = str(ln).strip()
        if s.startswith("- ") and ("要再" in s or "read/modify" in s or "不足" in s):
            detail.append(s[:120])
            if len(detail) >= 6:
                break
    return "要フォロー", detail, issues


def openchat_snapshot(*, cloud: bool = False) -> tuple[str, list[str]]:
    """Light health: watch status + today's 【スレッド】 counts. No QR / no YAML writes.

    cloud=True（GHA）: Mac専用（launchd / OneDrive / watchログ）はスキップし、
    判定を「要フォロー」にしない（本線は WeStudy/GHA）。
    """
    lines: list[str] = []
    level = "OK"

    if cloud:
        lines.append("実行環境: GitHub Actions（--cloud）")
        lines.append("オプチャ詳細: スキップ（Mac専用・launchd/OneDrive）")
        lines.append("補完: Mac launchd 日曜21:45（--remediate-once）")
        return "スキップ(cloud)", lines

    # launchd
    uid = os.getuid()
    code, out = _run(
        ["launchctl", "print", f"gui/{uid}/com.matsunoma.line.openchat.watch"],
        timeout=15,
    )
    state_m = re.search(r"state = (\w+)", out or "")
    pid_m = re.search(r"pid = (\d+)", out or "")
    if code == 0 and state_m:
        st = state_m.group(1)
        pid = pid_m.group(1) if pid_m else "?"
        lines.append(f"launchd: {st} (pid={pid})")
        if st != "running":
            level = "要フォロー"
    else:
        lines.append("launchd: 取得失敗（未インストールの可能性）")
        level = "要フォロー"

    # watch status JSON
    hb = "—"
    if WATCH_STATUS.is_file():
        try:
            data = json.loads(WATCH_STATUS.read_text(encoding="utf-8"))
            hb = str(
                data.get("last_heartbeat")
                or data.get("heartbeat_at")
                or data.get("updated_at")
                or "—"
            )[:40]
            lines.append(f"watch heartbeat: {hb}")
        except (OSError, json.JSONDecodeError):
            lines.append("watch status: 読取失敗")
            level = "要フォロー"
    else:
        lines.append("watch status: ファイルなし")
        level = "要フォロー"

    # today's thread headings
    today = datetime.now(JST).strftime("%Y/%m/%d")
    total = 0
    if OPENCHAT_BASE.is_dir():
        for md in OPENCHAT_BASE.glob("*/5.やり取り.md"):
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            n = len(re.findall(rf"### {re.escape(today)}.*【スレッド】", text))
            if n:
                total += n
        lines.append(f"今日の【スレッド】見出し: {total}件")
    else:
        lines.append("815フォルダ: 未マウント")
        level = "要フォロー"

    # recent exceptions
    if WATCH_ERR.is_file():
        code, err_out = _run(
            ["tail", "-n", "30", str(WATCH_ERR)],
            timeout=10,
        )
        hits = [
            ln
            for ln in (err_out or "").splitlines()
            if re.search(r"TypeError|Exception in thread|LOGGED_OUT|PermissionError", ln)
        ]
        if hits:
            lines.append(f"直近例外: あり（{hits[-1][:80]}）")
            level = "要フォロー"
        else:
            lines.append("直近例外: なし（tail30）")
    else:
        lines.append("watch.err.log: なし")

    return level, lines


def _westudy_bad(westudy_line: str) -> bool:
    return "⚠️" in westudy_line or "Fail" in westudy_line or "失敗" in westudy_line


def _oc_bad(oc_level: str) -> bool:
    return oc_level not in ("OK", "スキップ(cloud)")


def _gmail_bad(gmail_level: str) -> bool:
    return gmail_level not in ("OK", "スキップ(cloud)", "スキップ(disabled)")


def overall_status(westudy_line: str, oc_level: str, gmail_level: str = "OK") -> str:
    if _westudy_bad(westudy_line) or _oc_bad(oc_level) or _gmail_bad(gmail_level):
        return "要フォロー"
    return "OK"


def try_remediate_once(
    *,
    westudy_line: str,
    oc_level: str,
    oc_lines: list[str],
    gmail_level: str = "OK",
    gmail_lines: list[str] | None = None,
    dry_run: bool,
) -> dict[str, str]:
    """既知の安全な復旧を最大1回。戻り値は報告用メタ。

    Gmail token NG はブラウザ再同意が必要なため自動復旧しない（#consult）。
    """
    meta = {
        "try": "スキップ",
        "detail": "異常なし（トライ不要）",
        "result": "n/a",
        "need_consult": "no",
    }
    w_bad = _westudy_bad(westudy_line)
    o_bad = _oc_bad(oc_level)
    g_bad = _gmail_bad(gmail_level)
    if not w_bad and not o_bad and not g_bad:
        return meta

    parts: list[str] = []
    need_consult = False

    if w_bad:
        parts.append("WeStudy Fail — 自動再実行なし（人が gh 判断）")
        need_consult = True

    if g_bad:
        # トークン破壊の自動復旧は禁止。是正コマンドを人が実行
        hint = next(
            (x for x in (gmail_lines or []) if x.startswith("是正:")),
            "是正: jarvis_gmail_token_health.py / reauth_estate_gmail_send.py",
        )
        parts.append(f"Gmail token NG — 自動再同意なし（人がブラウザ）。{hint[:160]}")
        need_consult = True

    if o_bad:
        launchd_line = next((x for x in oc_lines if x.startswith("launchd:")), "")
        launchd_not_running = "running" not in launchd_line or "取得失敗" in launchd_line

        if dry_run:
            parts.append(
                "オプチャ: dry-run（health --push → recover_worker / 必要なら watch resume）"
            )
            meta["try"] = "dry-run"
            meta["detail"] = "；".join(parts)
            meta["result"] = "未実施"
            meta["need_consult"] = "yes" if need_consult else "no"
            return meta

        meta["try"] = "実施"
        # 1) health push で silent_fail があれば mac_recipe を queue
        py = _python()
        h_code, h_out = _run(
            [py, str(REPO / "scripts" / "jarvis_openchat_thread_health.py"), "--push"],
            timeout=180,
        )
        parts.append(f"health --push rc={h_code}")

        # 2) recover_worker（queued 時のみ実作業）
        r_code, r_out = _run(
            [py, str(REPO / "scripts" / "jarvis_openchat_recover_worker.py")],
            timeout=1200,
        )
        r_tail = (r_out or "").replace("\n", " ")[-200:]
        if "no openchat_init_bootstrap" in (r_out or "") or "skip status=" in (r_out or ""):
            parts.append(f"recover: キューなし／スキップ（{r_tail[:80]}）")
            # 3) launchd が止まっているときだけ resume を1回
            if launchd_not_running and WATCH_RESUME.is_file():
                rs_code, rs_out = _run([str(WATCH_RESUME)], timeout=60)
                parts.append(f"watch resume rc={rs_code}")
                if rs_code != 0:
                    need_consult = True
                    parts.append((rs_out or "")[:80])
            else:
                # 復旧レシピが無い／対象外 → 人判断
                need_consult = True
        elif r_code == 0:
            parts.append(f"recover: ok（{r_tail[:100]}）")
        else:
            need_consult = True
            if re.search(r"QR|logged_out|LOGGED_OUT", r_out or "", re.I):
                parts.append("recover: QR要・打ち切り（人がスキャン）")
            else:
                parts.append(f"recover: 失敗 rc={r_code}（{r_tail[:100]}）")

    meta["detail"] = "；".join(parts) if parts else "—"
    meta["need_consult"] = "yes" if need_consult else "no"
    meta["result"] = "pending_recheck"
    return meta


def build_message(
    westudy_line: str,
    westudy_block: str,
    oc_level: str,
    oc_lines: list[str],
    *,
    gmail_level: str = "OK",
    gmail_lines: list[str] | None = None,
    cloud: bool = False,
    remediate_meta: dict[str, str] | None = None,
    overall_override: str | None = None,
) -> str:
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    overall = overall_override or overall_status(westudy_line, oc_level, gmail_level)

    if cloud:
        engine = "GHA ops-health-315（日曜21:00 JST）"
    elif remediate_meta is not None:
        engine = "Mac launchd 日曜21:45（--remediate-once）"
    else:
        engine = "Mac手動／launchd補完"

    body = [
        f"【315 連携健全性】点検1回",
        f"- 時刻: {now} JST",
        f"- 起動: {engine}",
        f"- 判定: {overall}",
        f"- 報告先: Slack #ops（要判断のみ #consult。#report には出さない）",
        f"- フロー: {FLOW_URL}",
        f"- WeStudy/GHA: {westudy_line}",
        f"- オプチャ: {oc_level}",
    ]
    for ln in oc_lines:
        body.append(f"  · {ln}")

    body.append(f"- Gmail token: {gmail_level}")
    for ln in gmail_lines or []:
        body.append(f"  · {ln}")

    if remediate_meta is not None:
        body.append(f"- トライ: {remediate_meta.get('try', '—')}")
        body.append(f"  · {remediate_meta.get('detail', '—')[:240]}")
        body.append(f"- トライ結果: {remediate_meta.get('result', '—')}")

    if overall in ("要フォロー", "未解決"):
        body.append(
            "- 見てほしい点: 未解決。QR/YAML大量／Gmail再同意は人が確かめる → #consult"
        )
    elif overall == "修正済":
        body.append("- 見てほしい点: なし（修正済）。異常時のみ対応")
    else:
        body.append("- 見てほしい点: なし（OK）。異常時のみ対応")
    # keep Slack message readable; full westudy block in log
    if westudy_block and len(westudy_block) < 900:
        body.append("")
        body.append(westudy_block)
    return "\n".join(body)


def post_slack(channel: str, text: str) -> int:
    py = _python()
    code, out = _run(
        [
            py,
            str(REPO / "scripts" / "jarvis_slack_webhook_post.py"),
            "--channel",
            channel,
            "--username",
            "315 連携健全性",
            "--text",
            text,
        ],
        timeout=60,
    )
    print(out)
    return code


def post_ops(text: str) -> int:
    return post_slack("ops", text)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--post", action="store_true", help="Slack #ops に投稿")
    ap.add_argument(
        "--mark-checked",
        action="store_true",
        help="WeStudy watch の --mark-checked を付ける",
    )
    ap.add_argument(
        "--cloud",
        action="store_true",
        help="GHA用。オプチャのMac専用点検をスキップ",
    )
    ap.add_argument(
        "--remediate-once",
        action="store_true",
        help="Mac用。異常時に既知復旧を1回だけ試し再点検して報告",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="投稿せず本文のみ。--remediate-once 時は復旧も実行しない",
    )
    args = ap.parse_args()

    if args.remediate_once and args.cloud:
        print("⚠ --remediate-once は --cloud と併用不可（Mac専用）。cloudのみで続行。", file=sys.stderr)
        args.remediate_once = False

    w_line, w_block = westudy_block(mark_checked=args.mark_checked)
    oc_level, oc_lines = openchat_snapshot(cloud=args.cloud)
    g_level, g_lines, _g_issues = gmail_token_snapshot(
        cloud=args.cloud,
        mark_prompted=bool(args.mark_checked),
    )

    remediate_meta: dict[str, str] | None = None
    overall_override: str | None = None

    if args.remediate_once:
        before = overall_status(w_line, oc_level, g_level)
        remediate_meta = try_remediate_once(
            westudy_line=w_line,
            oc_level=oc_level,
            oc_lines=oc_lines,
            gmail_level=g_level,
            gmail_lines=g_lines,
            dry_run=bool(args.dry_run),
        )
        if before == "OK":
            overall_override = "OK"
            remediate_meta["result"] = "不要"
        elif args.dry_run:
            overall_override = "要フォロー"
            remediate_meta["result"] = "dry-run（未実施）"
        else:
            # 再点検（WeStudy は mark 済みなので再取得。重くない）
            w_line2, w_block2 = westudy_block(mark_checked=False)
            oc_level2, oc_lines2 = openchat_snapshot(cloud=False)
            g_level2, g_lines2, _ = gmail_token_snapshot(
                cloud=False, mark_prompted=False
            )
            after = overall_status(w_line2, oc_level2, g_level2)
            w_line, w_block = w_line2, w_block2
            oc_level, oc_lines = oc_level2, oc_lines2
            g_level, g_lines = g_level2, g_lines2
            if after == "OK":
                overall_override = "修正済"
                remediate_meta["result"] = "修正済"
                remediate_meta["need_consult"] = "no"
            else:
                overall_override = "未解決"
                remediate_meta["result"] = "未解決（1回トライ済）"
                # Gmail NG は自動では直らない → consult 維持
                if _gmail_bad(g_level):
                    remediate_meta["need_consult"] = "yes"
                else:
                    remediate_meta["need_consult"] = "yes"

    msg = build_message(
        w_line,
        w_block,
        oc_level,
        oc_lines,
        gmail_level=g_level,
        gmail_lines=g_lines,
        cloud=args.cloud,
        remediate_meta=remediate_meta,
        overall_override=overall_override,
    )

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"{stamp}_ops_health.md"
    log_path.write_text(msg + "\n", encoding="utf-8")
    print(msg)
    print(f"\n📎 log: {log_path}")

    if args.dry_run or not args.post:
        if not args.post:
            print("\n（--post なし → Slack未投稿。投稿するときは --post）")
        return 0

    rc = post_ops(msg)
    if (
        remediate_meta
        and remediate_meta.get("need_consult") == "yes"
        and (overall_override or "") in ("未解決", "要フォロー")
    ):
        consult = (
            "【相談】315 連携健全性 — 1回トライ後も未解決\n"
            f"- 判定: {overall_override}\n"
            f"- トライ: {remediate_meta.get('detail', '')[:200]}\n"
            "- 見てほしい点: QR／YAML大量／WeStudy再実行／Gmail再同意の要否\n"
            f"- フロー: {FLOW_URL}"
        )
        crc = post_slack("consult", consult)
        if crc != 0 and rc == 0:
            rc = crc
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
