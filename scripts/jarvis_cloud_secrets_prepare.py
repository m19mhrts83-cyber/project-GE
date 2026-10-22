#!/usr/bin/env python3
"""
Jarvis: Cloud Agents「My Secrets」へ載せる（値は表示しない）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  # 推奨: API で直接反映（CURSOR_API_KEY 必要。手貼り不要）
  python scripts/jarvis_cloud_secrets_prepare.py --slack-only --apply
  python scripts/jarvis_cloud_secrets_prepare.py --todoist-only --apply
  python scripts/jarvis_cloud_secrets_prepare.py --apply
  # 手貼り用 .env 断片だけ作るとき（--apply なし）:
  python scripts/jarvis_cloud_secrets_prepare.py --slack-only
  # → ~/.jarvis_state/cloud_agent_secrets.env → Dashboard My Secrets → Save
  # → rm ~/.jarvis_state/cloud_agent_secrets.env

API: PUT https://api.cursor.com/v1/me/secrets/{name}（Runtime Secret）
Git にコミットしないこと。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

OUT = Path.home() / ".jarvis_state" / "cloud_agent_secrets.env"
REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
CURSOR_ME_SECRETS = "https://api.cursor.com/v1/me/secrets"
REQUIRED = (
    "JARVIS_SUPABASE_URL",
    "JARVIS_SUPABASE_SERVICE_ROLE_KEY",
    "GEMINI_API_KEY",
)
# AIチーム Slack（Incoming Webhook）。Cloud 投稿の本線。URL は stdout に出さない。
SLACK_WEBHOOK_KEYS = (
    "SLACK_WEBHOOK_AI_TEAM_REPORT",
    "SLACK_WEBHOOK_AI_TEAM_CONSULT",
    "SLACK_WEBHOOK_AI_TEAM_OPS",
    "SLACK_WEBHOOK_AI_TEAM_HUB",
    "SLACK_WEBHOOK_AI_TEAM_DEAL_ACTIVE",
)


def _file_b64(path: Path) -> str | None:
    if not path.is_file():
        return None
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _append_todoist(lines: list[str], missing: list[str], *, required: bool) -> None:
    """Todoist（Jarvis 分身）。Cloud 起票に必須。値は stdout に出さない。"""
    tok = (os.environ.get("TODOIST_API_TOKEN") or "").strip()
    if tok:
        lines.append(f"TODOIST_API_TOKEN={tok}")
    elif required:
        missing.append("TODOIST_API_TOKEN")

    email = (os.environ.get("JARVIS_TODOIST_EMAIL") or "").strip()
    if email:
        lines.append(f"JARVIS_TODOIST_EMAIL={email}")

    backend = (os.environ.get("JARVIS_TASK_BACKEND") or "").strip() or "todoist"
    # トークンがある／必須のときは backend も揃える（ダッシュボード整合）
    if tok or required:
        lines.append(f"JARVIS_TASK_BACKEND={backend}")


def _append_slack_webhooks(
    lines: list[str], missing: list[str], *, required: bool
) -> int:
    """Slack Incoming Webhook。Cloud から Bot 投稿（プッシュ通知用）。値は出さない。"""
    n = 0
    for k in SLACK_WEBHOOK_KEYS:
        v = (os.environ.get(k) or "").strip()
        if v:
            lines.append(f"{k}={v}")
            n += 1
        elif required and k == "SLACK_WEBHOOK_AI_TEAM_REPORT":
            # REPORT だけ必須（他 ch は REPORT フォールバック可）
            missing.append(k)
    return n


def _lines_to_kv(lines: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for ln in lines:
        if not ln.strip() or ln.startswith("#") or "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        out[k] = v
    return out


def _apply_to_cursor_me(kv: dict[str, str]) -> int:
    """PUT /v1/me/secrets/{name}。値は stdout に出さない。失敗時は非0。"""
    api_key = (os.environ.get("CURSOR_API_KEY") or "").strip()
    if not api_key:
        print("missing: CURSOR_API_KEY（My Secrets API 反映に必要）", file=sys.stderr)
        return 2
    auth = "Basic " + base64.b64encode(f"{api_key}:".encode()).decode()
    ok = 0
    failed = 0
    for name, value in kv.items():
        if not value:
            print(f"skip {name}: empty", file=sys.stderr)
            failed += 1
            continue
        body = json.dumps(
            {"value": value, "type": "runtime_secret", "repos": []}
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{CURSOR_ME_SECRETS}/{name}",
            data=body,
            method="PUT",
            headers={
                "Authorization": auth,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                _ = res.read()
                status = res.status
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")[:160]
            print(f"❌ {name} HTTP {e.code}: {err}", file=sys.stderr)
            failed += 1
            continue
        except Exception as e:
            print(f"❌ {name}: {e}", file=sys.stderr)
            failed += 1
            continue
        print(f"✅ {name} http={status}")
        ok += 1
    print(f"applied {ok}/{ok + failed} secrets via Cursor My Secrets API")
    return 1 if failed else 0


def _finish(lines: list[str], *, label: str, apply: bool) -> int:
    if apply:
        return _apply_to_cursor_me(_lines_to_kv(lines))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    OUT.chmod(0o600)
    print(
        f"wrote {OUT} ({len(lines)} keys{', ' + label if label else ''}). "
        "Paste into Cloud Agents → My Secrets, then delete the file. "
        "Or re-run with --apply (CURSOR_API_KEY)."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--include-gmail-send",
        action="store_true",
        help="credentials + estate/m19m token を B64 で追加（Cloud 送信用）",
    )
    ap.add_argument(
        "--todoist-only",
        action="store_true",
        help="Todoist 関連だけ（手貼り or --apply）",
    )
    ap.add_argument(
        "--slack-only",
        action="store_true",
        help="Slack Incoming Webhook だけ（手貼り or --apply）",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="手貼りせず Cursor API（PUT /v1/me/secrets）で My Secrets に反映",
    )
    args = ap.parse_args(argv)

    lines: list[str] = []
    missing: list[str] = []

    if args.todoist_only and args.slack_only:
        print("use either --todoist-only or --slack-only, not both", file=sys.stderr)
        return 2

    if args.todoist_only:
        _append_todoist(lines, missing, required=True)
        if missing:
            print(f"missing: {', '.join(missing)}", file=sys.stderr)
            return 1
        return _finish(lines, label="todoist-only", apply=args.apply)

    if args.slack_only:
        n = _append_slack_webhooks(lines, missing, required=True)
        if missing:
            print(f"missing: {', '.join(missing)}", file=sys.stderr)
            return 1
        _ = n
        return _finish(lines, label="slack-only", apply=args.apply)

    for k in REQUIRED:
        v = (os.environ.get(k) or "").strip()
        if not v:
            missing.append(k)
            continue
        lines.append(f"{k}={v}")
    # 新形式キー名（SERVICE_ROLE と同値でよい）
    sr = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    secret = (os.environ.get("JARVIS_SUPABASE_SECRET_KEY") or "").strip() or sr
    if secret:
        lines.append(f"JARVIS_SUPABASE_SECRET_KEY={secret}")

    # Tavily（ローカル MCP と同キー。Cloud では env 経由で REST / 将来 MCP 配線）
    tavily = (os.environ.get("TAVILY_API_KEY") or "").strip()
    if tavily:
        lines.append(f"TAVILY_API_KEY={tavily}")

    # Todoist（スマホ→Cloud Agent 起票。Jarvis 分身トークン）
    _append_todoist(lines, missing, required=True)

    # Slack Incoming Webhook（Cloud から #report/#consult/#ops 等へ Bot 投稿＝通知が出る）
    _append_slack_webhooks(lines, missing, required=False)

    # 313／116／511 URL 署名（任意。無いと Cloud は TODOIST_API_TOKEN で署名）
    for gate_k in (
        "PROPERTY_GATE_ACTION_TOKEN",
        "TODOIST_313_ACTION_TOKEN",
        "MAIL_ACTION_TOKEN",
    ):
        gate_v = (os.environ.get(gate_k) or "").strip()
        if gate_v:
            lines.append(f"{gate_k}={gate_v}")

    if args.include_gmail_send:
        cred_b64 = (os.environ.get("GMAIL_CREDENTIALS_B64") or "").strip() or _file_b64(
            MANUAL / "credentials.json"
        )
        estate_b64 = (os.environ.get("GMAIL_ESTATE_TOKEN_B64") or "").strip() or _file_b64(
            MANUAL / "token_estate.json"
        )
        m19m_b64 = (os.environ.get("GMAIL_M19M_TOKEN_B64") or "").strip() or _file_b64(
            MANUAL / "token_m19m.json"
        )
        if cred_b64:
            lines.append(f"GMAIL_CREDENTIALS_B64={cred_b64}")
        else:
            missing.append("GMAIL_CREDENTIALS_B64|credentials.json")
        if estate_b64:
            lines.append(f"GMAIL_ESTATE_TOKEN_B64={estate_b64}")
        elif m19m_b64:
            lines.append(f"GMAIL_M19M_TOKEN_B64={m19m_b64}")
        else:
            missing.append("GMAIL_ESTATE_TOKEN_B64|token_estate.json")

    # OneDrive Graph（Cloud／GHA と同名）
    for gk in (
        "MS_GRAPH_CLIENT_ID",
        "MS_GRAPH_AUTHORITY",
        "MS_GRAPH_REFRESH_TOKEN",
        "MS_GRAPH_CLIENT_SECRET",
        "MS_GRAPH_TENANT_ID",
        "MS_GRAPH_USER_UPN",
        "MS_GRAPH_DRIVE_ID",
    ):
        gv = (os.environ.get(gk) or "").strip()
        if gv:
            lines.append(f"{gk}={gv}")
    if not (os.environ.get("MS_GRAPH_CLIENT_ID") or "").strip():
        # Graph は任意だが、レーン Cloud 実行には必要
        pass
    if not (os.environ.get("MS_GRAPH_AUTHORITY") or "").strip() and (
        os.environ.get("MS_GRAPH_CLIENT_ID") or ""
    ).strip():
        lines.append("MS_GRAPH_AUTHORITY=consumers")

    if missing:
        print(f"missing: {', '.join(missing)}", file=sys.stderr)
        return 1
    if not args.apply:
        print(
            "Note: jarvis-dashboard uses sb_secret_; legacy JWT service_role is disabled.",
            file=sys.stderr,
        )
    return _finish(lines, label="", apply=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
