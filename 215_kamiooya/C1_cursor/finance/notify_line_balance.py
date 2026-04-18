#!/usr/bin/env python3
"""
債券残高合計を LINE に通知する。

優先順:
1) LINE Messaging API（公式）
2) CHRLINE（既存 line_unofficial_poc の保存トークン）
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib import error, request


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = SCRIPT_DIR / ".env.akatsuki"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and value and key not in os.environ:
            os.environ[key] = value


def format_balance_message(total_jpy: int) -> str:
    return f"債券評価額: {total_jpy:,}円"


def format_balance_message_with_pl(*, eval_jpy: int, pl_jpy: int | None = None, category: str = "") -> str:
    """
    評価額 + 評価損益 を併記する通知文を作る。
    - category があれば先頭に付ける（例: 外国債券）
    - pl_jpy が None の場合は評価損益行を省略
    """
    cat = (category or "").strip()
    prefix = f"{cat} " if cat else ""
    lines = [f"{prefix}債券評価額: {eval_jpy:,}円"]
    if pl_jpy is not None:
        sign = "+" if pl_jpy > 0 else ""
        lines.append(f"{prefix}評価損益: {sign}{pl_jpy:,}円")
    return "\n".join(lines)


def _send_via_line_messaging_api_messages(messages: list[str]) -> bool:
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    to_id = os.environ.get("LINE_TO_USER_ID", "").strip() or os.environ.get("LINE_TO_GROUP_ID", "").strip()
    if not token or not to_id:
        return False

    texts = [m for m in (messages or []) if (m or "").strip()]
    if not texts:
        raise RuntimeError("送信本文が空です。")
    payload = json.dumps(
        {"to": to_id, "messages": [{"type": "text", "text": t} for t in texts]},
        ensure_ascii=False,
    ).encode("utf-8")
    req = request.Request(
        "https://api.line.me/v2/bot/message/push",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with request.urlopen(req, timeout=20) as resp:
            status = resp.getcode()
            body = resp.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LINE Messaging API 送信失敗: {exc.code} {detail}") from exc
    if status >= 300:
        raise RuntimeError(f"LINE Messaging API 送信失敗: {status} {body}")
    return True


def _send_via_chrline(message: str, allow_qr_login: bool) -> bool:
    to_mid = os.environ.get("LINE_NOTIFY_TO_MID", "").strip()
    if not to_mid:
        return False

    # finance/ から git-repos 直下まで辿り、line_unofficial_poc を探す
    p = SCRIPT_DIR.resolve()
    line_poc: Path | None = None
    for _ in range(10):
        cand = p / "line_unofficial_poc"
        if cand.is_dir():
            line_poc = cand
            break
        if p.parent == p:
            break
        p = p.parent
    if line_poc is None:
        # 最後の手段: カレントが git-repos 配下でない場合に備える
        home_cand = Path.home() / "git-repos" / "line_unofficial_poc"
        if home_cand.is_dir():
            line_poc = home_cand
    if not line_poc.is_dir():
        raise RuntimeError("line_unofficial_poc が見つかりません。")

    # CHRLINE は line_unofficial_poc 側の venv に依存がまとまっているため、
    # finance 側の venv から直接 import せず、サブプロセスで送信する。
    venv_py = line_poc / ".venv" / "bin" / "python"
    if not venv_py.is_file():
        raise RuntimeError(f"CHRLINE 用 venv が見つかりません: {venv_py}")

    code = r"""
import os, sys
from pathlib import Path

to_mid = os.environ.get("LINE_NOTIFY_TO_MID", "").strip()
msg = os.environ.get("LINE_NOTIFY_MESSAGE", "")
allow_qr = os.environ.get("LINE_NOTIFY_ALLOW_QR", "").strip() in ("1","true","yes","on")
if not to_mid:
    raise SystemExit("missing LINE_NOTIFY_TO_MID")

ROOT = Path.cwd().resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chrline_client_utils import build_logged_in_client, save_root_from_env  # type: ignore

save_root = save_root_from_env()
cl = build_logged_in_client(save_root, allow_qr_login=allow_qr)

errs = []
for method_name, args in [
    ("sendMessage", (to_mid, msg)),
    ("sendCompactMessage", (0, to_mid, msg)),
]:
    m = getattr(cl, method_name, None)
    if m is None:
        continue
    try:
        m(*args)
        print("OK")
        raise SystemExit(0)
    except TypeError:
        try:
            if method_name == "sendMessage":
                m(to_mid, msg, 0, {})
                print("OK")
                raise SystemExit(0)
        except Exception as e:
            errs.append(f"{method_name}: {e}")
    except Exception as e:
        errs.append(f"{method_name}: {e}")

raise SystemExit("CHRLINE send failed: " + ("; ".join(errs) if errs else "no method"))
"""
    env = dict(os.environ)
    env["LINE_NOTIFY_MESSAGE"] = message
    env["LINE_NOTIFY_ALLOW_QR"] = "1" if allow_qr_login else "0"

    def run_once(*, allow_qr: bool) -> subprocess.CompletedProcess[str]:
        env2 = dict(env)
        env2["LINE_NOTIFY_ALLOW_QR"] = "1" if allow_qr else "0"
        return subprocess.run(
            [str(venv_py), "-c", code],
            cwd=str(line_poc),
            env=env2,
            text=True,
            capture_output=True,
        )

    r = run_once(allow_qr=allow_qr_login)
    if r.returncode == 0:
        return True

    detail = (r.stderr or r.stdout or "").strip()
    needs_qr = "QR再認証は許可されていないため終了" in detail or "保存トークンが無効" in detail
    disable_auto_retry = os.environ.get("AKATSUKI_DISABLE_AUTO_QR_RETRY", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if (not allow_qr_login) and needs_qr and (not disable_auto_retry):
        # 既定で自動リトライ（定期実行などで止めたい場合は AKATSUKI_DISABLE_AUTO_QR_RETRY=1）
        r2 = run_once(allow_qr=True)
        if r2.returncode == 0:
            return True
        detail2 = (r2.stderr or r2.stdout or "").strip()
        raise RuntimeError(detail2 or "CHRLINE 送信に失敗しました。")

    raise RuntimeError(detail or "CHRLINE 送信に失敗しました。")


def send_text_to_line(message: str, *, allow_qr_login: bool = False) -> str:
    if _send_via_line_messaging_api_messages([message]):
        return "line-messaging-api"
    if _send_via_chrline(message, allow_qr_login=allow_qr_login):
        return "chrline"
    raise RuntimeError(
        "LINE送信先設定が不足しています。"
        "LINE_CHANNEL_ACCESS_TOKEN + LINE_TO_USER_ID(または LINE_TO_GROUP_ID) "
        "もしくは LINE_NOTIFY_TO_MID を設定してください。"
    )


def send_texts_to_line(messages: list[str], *, allow_qr_login: bool = False) -> str:
    if _send_via_line_messaging_api_messages(messages):
        return "line-messaging-api"
    # CHRLINE は1メッセージずつ送る
    ok_any = False
    for m in messages:
        if not (m or "").strip():
            continue
        if _send_via_chrline(m, allow_qr_login=allow_qr_login):
            ok_any = True
    if ok_any:
        return "chrline"
    raise RuntimeError(
        "LINE送信先設定が不足しています。"
        "LINE_CHANNEL_ACCESS_TOKEN + LINE_TO_USER_ID(または LINE_TO_GROUP_ID) "
        "もしくは LINE_NOTIFY_TO_MID を設定してください。"
    )


def send_balance_to_line(total_jpy: int, *, allow_qr_login: bool = False) -> str:
    message = format_balance_message(total_jpy)
    return send_text_to_line(message, allow_qr_login=allow_qr_login)


def send_balance_with_pl_to_line(
    *,
    eval_jpy: int,
    pl_jpy: int | None = None,
    category: str = "",
    allow_qr_login: bool = False,
) -> str:
    message1 = format_balance_message_with_pl(eval_jpy=eval_jpy, pl_jpy=pl_jpy, category=category)
    # 家計簿アプリ貼り付け用: 数字だけ（カンマなし、円なし）
    message2 = str(int(eval_jpy))
    return send_texts_to_line([message1, message2], allow_qr_login=allow_qr_login)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LINEへ債券残高合計を通知")
    parser.add_argument("--total-jpy", type=int, required=True, help="通知する合計残高（円）")
    parser.add_argument("--pl-jpy", type=int, default=None, help="評価損益（円）。指定時は併記する")
    parser.add_argument("--category", default="", help="商品分類名（例: 外国債券）。指定時は先頭に付ける")
    parser.add_argument("--allow-qr-login", action="store_true", help="CHRLINEでQR再ログインを許可")
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_PATH),
        help="環境変数ファイル（既定: finance/.env.akatsuki）",
    )
    parser.add_argument("--dry-run", action="store_true", help="送信せず本文だけ表示")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    _load_env_file(Path(args.env_file).expanduser())
    msg = format_balance_message_with_pl(
        eval_jpy=args.total_jpy,
        pl_jpy=args.pl_jpy,
        category=args.category,
    )
    if args.dry_run:
        print(msg)
        return 0
    try:
        backend = send_text_to_line(msg, allow_qr_login=args.allow_qr_login)
    except Exception as exc:
        print(f"LINE通知失敗: {exc}", file=sys.stderr)
        return 1
    print(f"LINE通知完了 ({backend}): {msg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
