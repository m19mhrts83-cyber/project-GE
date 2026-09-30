#!/usr/bin/env python3
"""
Jarvis: Cloud Agents「My Secrets」貼り付け用の .env 断片を作る（値は表示しない）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_cloud_secrets_prepare.py
  python scripts/jarvis_cloud_secrets_prepare.py --include-gmail-send
  # スマホ→Cloud で Todoist 起票だけ足すとき:
  python scripts/jarvis_cloud_secrets_prepare.py --todoist-only
  # → ~/.jarvis_state/cloud_agent_secrets.env
  # Dashboard → Cloud Agents → My Secrets → Add Secrets に中身を貼って Save
  # 終わったら: rm ~/.jarvis_state/cloud_agent_secrets.env

Git にコミットしないこと。
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
from pathlib import Path

OUT = Path.home() / ".jarvis_state" / "cloud_agent_secrets.env"
REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
REQUIRED = (
    "JARVIS_SUPABASE_URL",
    "JARVIS_SUPABASE_SERVICE_ROLE_KEY",
    "GEMINI_API_KEY",
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
        help="Todoist 関連だけ出力（My Secrets に差分追加するとき）",
    )
    args = ap.parse_args(argv)

    lines: list[str] = []
    missing: list[str] = []

    if args.todoist_only:
        _append_todoist(lines, missing, required=True)
        if missing:
            print(f"missing: {', '.join(missing)}", file=sys.stderr)
            return 1
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        OUT.chmod(0o600)
        print(
            f"wrote {OUT} ({len(lines)} keys, todoist-only). "
            "Paste into Cloud Agents → My Secrets, then delete the file."
        )
        return 0

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
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    OUT.chmod(0o600)
    print(f"wrote {OUT} ({len(lines)} keys). Paste into Cloud Agents → My Secrets, then delete the file.")
    print(
        "Note: jarvis-dashboard uses sb_secret_; legacy JWT service_role is disabled.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
