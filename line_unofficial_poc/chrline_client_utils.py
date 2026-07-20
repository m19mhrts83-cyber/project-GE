"""
CHRLINE-PatchV2 用: .line_auth から保存トークンを読み、QR なしでクライアントを起動する。

トークン文字列はログに出さない。ファイルは LINE_UNOFFICIAL_AUTH_DIR/.tokens/ 配下。
CHRLINE は QR 初回ログイン時に .tokens を自動作成しないことがあるため、
chrline_qr_login_poc 成功後に persist_auth_token を呼ぶ。

環境変数:
  LINE_CHRLINE_AUTO_OPEN_QR … 1/true/yes のときだけ、再認証時に QR 画像を OS で自動表示する。
    未設定時は自動表示しない（ターミナルに IMG: パスが出るので、必要なら手動で開く）。

  LINE_CHRLINE_DEVICE … CHRLINE クライアント device（既定 DESKTOPWIN）。Phase0: CHROMEOS / ANDROIDSECONDARY 等。

  LINE_CHRLINE_APP_VERSION … CHRLINE クライアント版文字列（既定 9.0.0.3360）。

  LINE_CHRLINE_SQUARE_PROBE_MID / LINE_CHRLINE_SQUARE_PROBE_THREAD_MID … Square probe 用 mid。
    LINE 側がセッションを切ったときの QR 認証そのものは非公式 API の制約で省略できない。

  LINE_CHRLINE_CALL_INTERVAL_MS … Square API 連続呼び出しの最小間隔（既定 400ms）。バッチ401・LOGGED_OUT 対策。

  build_logged_in_client の allow_qr_login … 既定は False（バックグラウンド・ヘルスチェックで QR が頻発しないようにする）。
    取り込み確認など対話で再ログインしたいときは、各スクリプトの --allow-qr-login を付ける。

  LINE_UNOFFICIAL_AUTH_DIR … 未設定時は line_unofficial_poc 直下の .line_auth_local（ローカル固定・Git 対象外）。
    クラウド同期パスを明示指定した場合は警告を出す。
"""
from __future__ import annotations

import os
import re
import time
import subprocess
import sys
from contextlib import contextmanager
from hashlib import md5
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
_DEFAULT_LOCAL_AUTH_DIR = (ROOT / ".line_auth_local").resolve()
_CLOUD_PATH_HINTS = (
    "OneDrive",
    "Google Drive",
    "GoogleDrive",
    "Dropbox",
    "iCloud",
    "Box Sync",
)
load_dotenv(ROOT / ".env")

DEFAULT_CHRLINE_APP_VERSION = "9.0.0.3360"
DEFAULT_CHRLINE_DEVICE = "DESKTOPWIN"
DEFAULT_SQUARE_PROBE_MID = "m82a451eb96a535983d9cd8d172820c19"  # 34保険相談G
DEFAULT_SQUARE_PROBE_THREAD_MID = "t03c8f5bc4f5c1738d3fb5625db1ae6ee"


def chrline_device_from_env() -> str:
    """CHRLINE クライアント device（LINE_CHRLINE_DEVICE で上書き可）。"""
    return (os.environ.get("LINE_CHRLINE_DEVICE") or DEFAULT_CHRLINE_DEVICE).strip() or DEFAULT_CHRLINE_DEVICE


def chrline_app_version_from_env() -> str:
    return (os.environ.get("LINE_CHRLINE_APP_VERSION") or DEFAULT_CHRLINE_APP_VERSION).strip()


def chrline_constructor_kwargs() -> dict[str, Any]:
    """Square スレッド API（getSquareThreadMid 等）に必要な CHRLINE クライアント引数。"""
    version = chrline_app_version_from_env()
    device = chrline_device_from_env()
    kw: dict[str, Any] = {"device": device, "useThrift": True}
    if version:
        kw["version"] = version
    return kw


def client_cache_key(save_root: Path) -> str:
    """プロセス内 CHRLINE キャッシュキー（device + app version を含む）。"""
    return f"{save_root.resolve()}|{chrline_device_from_env()}|{chrline_app_version_from_env()}"


def cleanup_chrline_qr_images(save_root: Path) -> None:
    """
    CHRLINE が savePath/.images に保存する qr_*.png を整理する（容量用）。
    - 既定: 最新 1 枚だけ残し、古いものを削除
    - 画像が 0 枚ならディレクトリも削除
    """
    d = save_root / ".images"
    if not d.is_dir():
        return
    files = [f for f in d.glob("qr_*.png") if f.is_file()]
    if not files:
        try:
            next(d.iterdir())
        except StopIteration:
            try:
                d.rmdir()
            except OSError:
                pass
        except OSError:
            pass
        return

    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    keep = files[0]
    for f in files[1:]:
        try:
            f.unlink()
        except OSError:
            pass
    # keep があるため .images は消さない（ユーザーが後で開けるように）


def save_root_from_env() -> Path:
    raw = os.environ.get("LINE_UNOFFICIAL_AUTH_DIR", "").strip()
    if raw:
        p = Path(raw).expanduser().resolve()
    else:
        p = _DEFAULT_LOCAL_AUTH_DIR
        os.environ["LINE_UNOFFICIAL_AUTH_DIR"] = str(p)
    p.mkdir(parents=True, exist_ok=True)
    s = str(p)
    if any(h in s for h in _CLOUD_PATH_HINTS):
        print(
            "警告: LINE_UNOFFICIAL_AUTH_DIR がクラウド同期フォルダ付近です。"
            "セッション競合で QR が増えやすいため、"
            f"未設定時のローカル既定 {_DEFAULT_LOCAL_AUTH_DIR} への切り替え（.tokens 等をコピー）を推奨します。",
            file=sys.stderr,
        )
    return p


def persist_auth_token(save_root: Path, auth_token: str) -> None:
    """
    CHRLINE の checkNextToken / handleNextToken と同じ規則で 1 ファイル保存する。
    auth_token はログに出さない。
    加えて `.tokens/latest` に正本を1本だけ置く（md5 ファイル名の取りこぼし防止）。
    """
    t = (auth_token or "").strip()
    if len(t) < 8:
        return
    d = save_root / ".tokens"
    d.mkdir(parents=True, exist_ok=True)
    fn = md5(t.encode()).hexdigest()
    (d / fn).write_text(t, encoding="utf-8")
    (d / "latest").write_text(t, encoding="utf-8")


def _persist_client_session(save_root: Path, cl) -> None:
    """initAll 後の authToken（V3 ローテーション後）を .tokens に保存する。"""
    token = (getattr(cl, "authToken", None) or "").strip()
    if len(token) >= 30:
        persist_auth_token(save_root, token)


def _read_latest_saved_token(save_root: Path) -> str | None:
    latest = save_root / ".tokens" / "latest"
    if latest.is_file():
        t = latest.read_text(encoding="utf-8", errors="replace").strip()
        if len(t) >= 30:
            return t
    return None


def _iter_refresh_token_files_newest_first(save_root: Path) -> list[Path]:
    d = save_root / ".refreshToken"
    if not d.is_dir():
        return []
    files = [f for f in d.iterdir() if f.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def _is_refreshable_token_error(exc: BaseException) -> bool:
    """V3 accessToken 期限切れなど refresh で復旧できるエラー。"""
    if _is_invalid_saved_token_error(exc):
        return False
    code = getattr(exc, "code", None)
    if code == 119:
        return True
    msg = str(exc)
    if "Code: 119" in msg:
        return True
    if "access token expired" in msg.lower():
        return True
    if "x-line-access-refresh-required" in msg.lower():
        return True
    return False


def _try_refresh_access_token(cl, save_root: Path) -> bool:
    """保存済み refreshToken で accessToken を更新する（CHRLINE-Patch V3）。"""
    try:
        cl.tryRefreshToken()
    except Exception as exc:
        print(f"# refreshToken 失敗: {type(exc).__name__}: {str(exc)[:120]}", file=sys.stderr)
        return False
    _persist_client_session(save_root, cl)
    return True


def _init_client_all_with_v3_refresh(cl, save_root: Path) -> None:
    """initAll。V3 accessToken 期限切れ（code 119）なら refresh して再試行。"""
    from CHRLINE.exceptions import LineServiceException

    try:
        cl.initAll()
        _persist_client_session(save_root, cl)
        return
    except LineServiceException as exc:
        if not _is_refreshable_token_error(exc):
            raise
    except Exception as exc:
        if not _is_refreshable_token_error(exc):
            raise
    if not _try_refresh_access_token(cl, save_root):
        raise RuntimeError("accessToken 期限切れ（refreshToken で復旧できませんでした）")
    cl.initAll()
    _persist_client_session(save_root, cl)


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _open_qr_image_if_possible(img_path: str) -> None:
    """失効時の再認証で生成された QR 画像を開く（LINE_CHRLINE_AUTO_OPEN_QR があるときのみ）。"""
    if not _env_truthy("LINE_CHRLINE_AUTO_OPEN_QR"):
        return
    p = (img_path or "").strip()
    if not p:
        return
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", p], check=False)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", p], check=False)
        elif os.name == "nt":
            os.startfile(p)  # type: ignore[attr-defined]
    except Exception:
        # 開けない環境でも再認証自体は続行する。
        pass


_process_client_cache: dict[str, Any] = {}
_qr_logins_this_process = 0
_last_chrline_call_at: float = 0.0
_midrun_recoveries_this_process = 0


def _max_qr_logins_per_process() -> int:
    raw = (os.environ.get("LINE_CHRLINE_MAX_QR_PER_PROCESS") or "1").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 1


def load_latest_saved_token(save_root: Path) -> str | None:
    tokens = load_saved_tokens_newest_first(save_root)
    return tokens[0] if tokens else None


def _extract_login_url_from_chunk_text(text: str) -> str | None:
    m = re.search(
        r"(https://line\.me/R/au/lgn/sq/[A-Za-z0-9_-]+(?:\?[^\s\"')}>]+)?)",
        text,
    )
    return m.group(1) if m else None


def _ensure_latest_qr_png(save_root: Path, url: str) -> Path | None:
    try:
        import qrcode  # type: ignore
    except Exception:
        return None

    img_dir = save_root / ".images"
    img_dir.mkdir(parents=True, exist_ok=True)
    out_path = img_dir / f"qr_{time.time():.6f}.png"
    (img_dir / "qr_latest_url.txt").write_text(url + "\n", encoding="utf-8")
    qr = qrcode.QRCode(border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(out_path)
    return out_path


def chrline_call_interval_ms() -> int:
    """Square API 連続呼び出しの最小間隔（ms）。環境変数 LINE_CHRLINE_CALL_INTERVAL_MS（既定 400）。"""
    raw = (os.environ.get("LINE_CHRLINE_CALL_INTERVAL_MS") or "400").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 400


def chrline_throttle() -> None:
    """前回 Square/Talk API 呼び出しから最小間隔だけ待つ（バッチ401・セッション切断対策）。"""
    global _last_chrline_call_at
    interval_ms = chrline_call_interval_ms()
    if interval_ms <= 0:
        return
    now = time.monotonic()
    elapsed_ms = (now - _last_chrline_call_at) * 1000.0
    if _last_chrline_call_at > 0 and elapsed_ms < interval_ms:
        time.sleep((interval_ms - elapsed_ms) / 1000.0)
    _last_chrline_call_at = time.monotonic()


def _max_midrun_recoveries_per_process() -> int:
    raw = (os.environ.get("LINE_CHRLINE_MAX_MIDRUN_RECOVERIES") or "2").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 2


def _is_session_logged_out_error(exc: BaseException) -> bool:
    """バッチ途中の V3_TOKEN_CLIENT_LOGGED_OUT（code 8）等。"""
    if _is_invalid_saved_token_error(exc):
        return True
    msg = str(exc)
    return "LOGGED_OUT" in msg.upper()


def recover_session_midrun(
    save_root: Path,
    cl,
    *,
    allow_qr_login: bool = False,
):
    """
    バッチ同期途中のセッション切断を refreshToken / 保存トークンで1回復旧する。
    成功時は新しい client を返す。失敗時は None。
    """
    global _midrun_recoveries_this_process
    if _midrun_recoveries_this_process >= _max_midrun_recoveries_per_process():
        print(
            "# ミッドラン復旧: このプロセスでの上限に達しました",
            file=sys.stderr,
        )
        return None

    print("# ミッドラン復旧: refreshToken / 保存トークンで再接続を試行", file=sys.stderr)
    if cl is not None:
        try:
            if _try_refresh_access_token(cl, save_root):
                _init_client_all_with_v3_refresh(cl, save_root)
                if probe_square_session(cl) or probe_talk_session(cl):
                    _midrun_recoveries_this_process += 1
                    print("# ミッドラン復旧: refreshToken で成功", file=sys.stderr)
                    return cl
        except Exception as exc:
            print(
                f"# ミッドラン復旧: refresh 失敗 ({type(exc).__name__})",
                file=sys.stderr,
            )

    clear_process_client_cache(save_root)
    cl2 = try_client_from_saved_tokens_only(save_root)
    if cl2 is not None and (probe_square_session(cl2) or probe_talk_session(cl2)):
        _process_client_cache[client_cache_key(save_root)] = cl2
        _midrun_recoveries_this_process += 1
        print("# ミッドラン復旧: 保存トークンで成功", file=sys.stderr)
        return cl2

    if allow_qr_login:
        try:
            cl3 = build_logged_in_client(save_root, allow_qr_login=True)
            if cl3 is not None and probe_square_session(cl3):
                _midrun_recoveries_this_process += 1
                print("# ミッドラン復旧: QR 再認証で成功", file=sys.stderr)
                return cl3
        except SystemExit:
            pass

    print("# ミッドラン復旧: 失敗（バッチ同期を中断またはスキップ）", file=sys.stderr)
    return None


def _is_invalid_saved_token_error(exc: BaseException) -> bool:
    msg = str(exc)
    if "V3_TOKEN_CLIENT_LOGGED_OUT" in msg:
        return True
    if "Code: 8" in msg:
        return True
    if "Code: 1000" in msg and "'message': '3'" in msg:
        return True
    if "x-line-access-refresh-required" in msg.lower():
        return True
    code = getattr(exc, "code", None)
    if code in (8, 1000):
        return True
    return False


def _is_qr_expired_error(exc: BaseException) -> bool:
    msg = str(exc)
    return ("Code: 100" in msg) or ("行動條碼過期" in msg)


def _iter_token_files_newest_first(save_root: Path) -> list[Path]:
    d = save_root / ".tokens"
    if not d.is_dir():
        return []
    files = [f for f in d.iterdir() if f.is_file() and f.name != "latest"]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def _prune_token_files_except(save_root: Path, *, keep: Path) -> None:
    removed = 0
    for f in _iter_token_files_newest_first(save_root):
        if f == keep:
            continue
        try:
            f.unlink()
            removed += 1
        except OSError:
            pass
    if removed:
        print(
            f"# 失効済みトークンを {removed} 件整理しました（有効な1件のみ保持）。",
            file=sys.stderr,
        )


def _display_qr_once(save_root: Path, *, seen_urls: list[str], saw_native_img: bool) -> None:
    """QR は1回の認証につき URL/IMG を1セットだけ表示・自動オープンする。"""
    cleanup_chrline_qr_images(save_root)
    img_path: str | None = None
    if seen_urls:
        uniq = list(dict.fromkeys(seen_urls))
        best = next((u for u in uniq if "secret=" in u), uniq[-1])
        print(f"URL: {best}")
        if not saw_native_img:
            png = _ensure_latest_qr_png(save_root, best)
            if png is not None:
                img_path = str(png)
        else:
            files = sorted(
                (save_root / ".images").glob("qr_*.png"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if files:
                img_path = str(files[0])
    if img_path:
        print(f"IMG: {img_path}")
        _open_qr_image_if_possible(img_path)


def _perform_qr_relogin(save_root: Path):
    from CHRLINE import CHRLINE

    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        cleanup_chrline_qr_images(save_root)
        cl = CHRLINE(
            savePath=str(save_root),
            noLogin=True,
            **chrline_constructor_kwargs(),
        )
        saw_native_img = False
        seen_urls: list[str] = []
        saw_pin = False
        qr_displayed = False
        try:
            for chunk in cl.requestSQR3(isSelf=True):
                text = str(chunk)
                if text.startswith("請輸入pincode:"):
                    if not saw_pin:
                        print(text)
                        saw_pin = True
                if text.startswith("IMG:"):
                    saw_native_img = True
                url = _extract_login_url_from_chunk_text(text)
                if url:
                    seen_urls.append(url)
                if not qr_displayed and (seen_urls or saw_native_img):
                    _display_qr_once(save_root, seen_urls=seen_urls, saw_native_img=saw_native_img)
                    qr_displayed = True
            refreshed = (getattr(cl, "authToken", None) or "").strip()
            if not refreshed:
                raise RuntimeError("QR再認証でトークン取得に失敗しました。")
            persist_auth_token(save_root, refreshed)
            _init_client_all_with_v3_refresh(cl, save_root)
            for f in _iter_token_files_newest_first(save_root):
                if f.read_text(encoding="utf-8", errors="replace").strip() == (
                    getattr(cl, "authToken", None) or ""
                ).strip():
                    _prune_token_files_except(save_root, keep=f)
                    break
            cleanup_chrline_qr_images(save_root)
            return cl
        except Exception as exc:
            if _is_qr_expired_error(exc) and attempt < max_attempts:
                print(
                    "⚠ QR の有効期限が切れました。新しい QR を1回だけ再表示します。",
                    file=sys.stderr,
                )
                time.sleep(1.5)
                continue
            raise
        finally:
            cleanup_chrline_qr_images(save_root)

    raise RuntimeError("QR再認証に失敗しました。")


def try_client_from_saved_tokens_only(save_root: Path):
    """
    保存済みトークンだけで CHRLINE を初期化・initAll まで成功させる。
    失効トークンはその場で削除し、有効な1件だけ残す。QR は開始しない。
    accessToken 失効時は refreshToken（.refreshToken/）で復旧を試みる。
    """
    from CHRLINE import CHRLINE
    from CHRLINE.exceptions import LineServiceException

    cleanup_chrline_qr_images(save_root)
    for token in load_saved_tokens_newest_first(save_root):
        if len(token) < 30:
            continue
        try:
            cl = CHRLINE(
                token,
                savePath=str(save_root),
                **chrline_constructor_kwargs(),
            )
            _init_client_all_with_v3_refresh(cl, save_root)
            # latest 正本を更新（md5 ファイル名の取りこぼし防止）
            _persist_client_session(save_root, cl)
            for f in _iter_token_files_newest_first(save_root):
                if f.name == "latest":
                    continue
                if f.read_text(encoding="utf-8", errors="replace").strip() == (
                    getattr(cl, "authToken", None) or ""
                ).strip():
                    _prune_token_files_except(save_root, keep=f)
                    break
            return cl
        except LineServiceException as exc:
            if _is_invalid_saved_token_error(exc):
                # latest のみ削除（md5 ファイルは prune で整理）
                latest = save_root / ".tokens" / "latest"
                if latest.is_file() and latest.read_text(encoding="utf-8", errors="replace").strip() == token:
                    try:
                        latest.unlink()
                    except OSError:
                        pass
            continue
        except Exception:
            continue
    return _try_client_from_refresh_tokens_only(save_root)


def _try_client_from_refresh_tokens_only(save_root: Path):
    """
    .tokens が空または accessToken 失効時、.refreshToken/ の refreshToken から復旧する。
    CHRLINE-Patch V3 向け。
    """
    from CHRLINE import CHRLINE

    refresh_files = _iter_refresh_token_files_newest_first(save_root)
    if not refresh_files:
        return None
    max_try = 5
    cl = CHRLINE(
        savePath=str(save_root),
        noLogin=True,
        **chrline_constructor_kwargs(),
    )
    for rf in refresh_files[:max_try]:
        refresh_token = rf.read_text(encoding="utf-8", errors="replace").strip()
        if len(refresh_token) < 30:
            continue
        try:
            ratr = cl.refreshAccessToken(refresh_token)
            access = cl.checkAndGetValue(ratr, "accessToken", 1)
            if not access or len(str(access).strip()) < 30:
                continue
            cl.authToken = str(access).strip()
            persist_auth_token(save_root, cl.authToken)
            cl.saveCacheData(".refreshToken", cl.authToken, refresh_token)
            _init_client_all_with_v3_refresh(cl, save_root)
            print("# refreshToken から accessToken を復旧しました", file=sys.stderr)
            return cl
        except Exception as exc:
            print(
                f"# refreshToken 試行失敗 ({rf.name}): {type(exc).__name__}: {str(exc)[:80]}",
                file=sys.stderr,
            )
            continue
    return None


def chrline_session_ok(save_root: Path) -> bool:
    """保存トークンが有効であれば True。ネットワーク不可などは False 扱い。"""
    try:
        return try_client_from_saved_tokens_only(save_root) is not None
    except OSError:
        return False


def clear_process_client_cache(save_root: Path | None = None) -> None:
    """プロセス内 CHRLINE クライアントキャッシュを破棄（セッション失効後の再ログイン用）。"""
    if save_root is None:
        _process_client_cache.clear()
        return
    cache_key = client_cache_key(save_root)
    _process_client_cache.pop(cache_key, None)


def probe_square_session(cl, *, square_chat_mid: str | None = None) -> bool:
    """Square(オープンチャット) API が応答するか軽量確認（メイン+代表スレッド）。"""
    detail = probe_square_session_detail(cl, square_chat_mid=square_chat_mid)
    return bool(detail.get("ok"))


def probe_square_session_detail(cl, *, square_chat_mid: str | None = None) -> dict[str, Any]:
    """Square probe の詳細（Phase 0 診断・state 記録用）。メイン成功+スレッド成功で ok=True。"""
    mid = (
        square_chat_mid
        or os.environ.get("LINE_CHRLINE_SQUARE_PROBE_MID")
        or DEFAULT_SQUARE_PROBE_MID
        or ""
    ).strip()
    thread_mid = (
        os.environ.get("LINE_CHRLINE_SQUARE_PROBE_THREAD_MID") or DEFAULT_SQUARE_PROBE_THREAD_MID or ""
    ).strip()
    out: dict[str, Any] = {
        "ok": False,
        "main_ok": False,
        "thread_ok": False,
        "can_use_square": bool(getattr(cl, "can_use_square", False)) if cl else False,
        "talk_ok": probe_talk_session(cl) if cl else False,
        "square_chat_mid": mid,
        "thread_mid": thread_mid,
        "device": chrline_device_from_env(),
        "app_version": chrline_app_version_from_env(),
        "error": "",
    }
    if cl is None:
        out["error"] = "client is None"
        return out
    if not mid:
        out["error"] = "no square_chat_mid"
        return out
    # CHRLINE-Patch は can_use_square が遅延評価のため、直接 fetch して判定する
    try:
        chrline_throttle()
        cl.fetchSquareChatEvents(mid, limit=1)
        out["main_ok"] = True
    except Exception as exc:
        out["error"] = f"main: {type(exc).__name__}: {exc}"
        return out
    if thread_mid:
        try:
            chrline_throttle()
            cl.fetchSquareChatEvents(mid, limit=1, threadMid=thread_mid)
            out["thread_ok"] = True
        except Exception as exc:
            out["error"] = f"thread: {type(exc).__name__}: {exc}"
            return out
    else:
        out["thread_ok"] = True
    out["ok"] = out["main_ok"] and out["thread_ok"]
    if out["ok"]:
        out["can_use_square"] = True
    return out


def format_square_probe_report(detail: dict[str, Any]) -> str:
    """パートナー確認報告用 1 ブロック。"""
    status = "OK" if detail.get("ok") else "401/不可"
    lines = [
        "---",
        "📎 Square API プローブ（オープンチャット）",
        f"- 判定: {status}（device={detail.get('device')} version={detail.get('app_version')}）",
        f"- メイン: {'OK' if detail.get('main_ok') else 'NG'} / スレッド: {'OK' if detail.get('thread_ok') else 'NG'}",
    ]
    if not detail.get("ok"):
        err = (detail.get("error") or "").strip()
        if err:
            lines.append(f"- 詳細: {err[:120]}")
        lines.append("- オプチャ同期: スキップ（構造限界または Square 未復旧）")
        hint = _version_update_hint_for_probe_failure()
        if hint:
            lines.append(hint)
    lines.append("---")
    return "\n".join(lines)


def _version_update_hint_for_probe_failure() -> str:
    """Square probe NG 時: バージョン state を参照して更新提案1行（失敗時は空）。"""
    try:
        repo_root = Path(__file__).resolve().parent.parent
        scripts_dir = str(repo_root / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from jarvis_chrline_version_check import (  # noqa: WPS433
            run_version_check,
            version_update_hint_for_probe_failure,
        )

        run_version_check(force_upstream=False)
        return version_update_hint_for_probe_failure()
    except Exception:
        return ""


def probe_talk_session(cl) -> bool:
    """Talk API が応答するか軽量確認（Square 401 でもセッション再利用の判定に使う）。"""
    if cl is None:
        return False
    token = (getattr(cl, "authToken", None) or "").strip()
    if len(token) < 30:
        return False
    try:
        cl.getProfile()
        return True
    except Exception as exc:
        if _is_invalid_saved_token_error(exc):
            return False
        return False


def probe_client_session(cl) -> bool:
    """Talk または Square のいずれかが生きていればセッション有効とみなす。"""
    return probe_talk_session(cl) or probe_square_session(cl)


def _invalidate_client_auth_token(save_root: Path, cl) -> None:
    """initAll は通るが API が使えないトークンを .tokens から削除する。"""
    token = (getattr(cl, "authToken", None) or "").strip()
    if len(token) < 30:
        return
    latest = save_root / ".tokens" / "latest"
    if latest.is_file():
        saved = latest.read_text(encoding="utf-8", errors="replace").strip()
        if saved == token:
            try:
                latest.unlink()
            except OSError:
                pass
    for token_file in _iter_token_files_newest_first(save_root):
        saved = token_file.read_text(encoding="utf-8", errors="replace").strip()
        if saved == token:
            try:
                token_file.unlink()
            except OSError:
                pass
            print(
                "# 保存トークンを削除しました（Talk/Square セッション不一致）",
                file=sys.stderr,
            )
            break


def refresh_logged_in_client(save_root: Path, *, allow_qr_login: bool = False, cl=None):
    """
    セッション失効時にキャッシュを捨てて再構築。
    cl が有効ならそのまま返す。
    """
    if cl is not None and probe_client_session(cl):
        return cl
    clear_process_client_cache(save_root)
    return build_logged_in_client(save_root, allow_qr_login=allow_qr_login)


def refresh_square_logged_in_client(save_root: Path, *, allow_qr_login: bool = False, cl=None):
    """
    オープンチャット用: Square API が応答するセッションまで再構築する。
    sync 後に Talk のみ生きて Square が 401 になるケースを想定。

    重要: この関数内では **第2 QR を出さない**（allow_qr_login を無視して False 相当）。
    Talk も死んで復旧できない場合は None を返し、呼び出し側で open-chat をスキップする。
    """
    del allow_qr_login  # 第2 QR 禁止のため意図的に未使用
    if cl is not None and probe_square_session(cl):
        return cl
    # Square NG でも既存 Talk が生きていれば client を維持（cache 破棄・再QRしない）
    if cl is not None and probe_talk_session(cl):
        print(
            "# Square probe NG だが Talk 生存: 既存 client を維持（再QRしない）",
            file=sys.stderr,
        )
        return cl

    clear_process_client_cache(save_root)
    cl2 = try_client_from_saved_tokens_only(save_root)
    if cl2 is not None and probe_square_session(cl2):
        return cl2
    # Talk が生きていればトークンは有効（Square 401 は端末権限の問題。トークン削除しない）
    if cl2 is not None and probe_talk_session(cl2):
        return cl2
    if cl2 is not None and not probe_talk_session(cl2):
        _invalidate_client_auth_token(save_root, cl2)
        clear_process_client_cache(save_root)

    # 無 QR で再構築のみ試行
    cl3 = build_logged_in_client(save_root, allow_qr_login=False)
    if cl3 is not None and probe_square_session(cl3):
        return cl3
    if cl3 is not None and probe_talk_session(cl3):
        print(
            "# Square API 未利用（401 等）: スマホLINEで対象オープンチャットを開き、"
            "メインとスレッドを1件表示してから再実行してください",
            file=sys.stderr,
        )
        return cl3

    print(
        "# open-chat: セッション復旧不可（再QRしない）。"
        " --skip-sync で別プロセス再実行を検討してください",
        file=sys.stderr,
    )
    return None


def load_saved_tokens_newest_first(save_root: Path) -> list[str]:
    """`.tokens` 内の全ファイルを更新日時の新しい順に読み、有効な文字列のみ重複排除して返す。"""
    out: list[str] = []
    seen: set[str] = set()
    latest = _read_latest_saved_token(save_root)
    if latest and latest not in seen:
        seen.add(latest)
        out.append(latest)
    d = save_root / ".tokens"
    if not d.is_dir():
        return out
    files = [f for f in d.iterdir() if f.is_file() and f.name != "latest"]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files:
        t = f.read_text(encoding="utf-8", errors="replace").strip()
        if len(t) < 30 or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


SESSION_LOCK_FILENAME = ".open_chat_session.lock"


def session_lock_path(save_root: Path) -> Path:
    return Path(save_root) / SESSION_LOCK_FILENAME


@contextmanager
def _file_lock(lock_path: Path, *, poll_interval_s: float = 0.2, blocking: bool = True):
    """
    Cross-process flock.

    - blocking=True: QR 再認証や常駐監視の排他（取れるまで待つ）
    - blocking=False: 取れなければ BlockingIOError
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    f = lock_path.open("a+", encoding="utf-8")
    locked = False
    try:
        try:
            import fcntl  # POSIX

            while True:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                    break
                except BlockingIOError:
                    if not blocking:
                        raise
                    time.sleep(poll_interval_s)
        except BlockingIOError:
            raise
        except Exception:
            # Fallback: no real lock, but keep flow consistent.
            locked = True
        yield
    finally:
        if locked:
            try:
                import fcntl  # POSIX

                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
            except Exception:
                pass
        try:
            f.close()
        except Exception:
            pass


@contextmanager
def open_chat_session_lock(save_root: Path, *, blocking: bool = True):
    """
    リアルタイム監視とバッチ同期が同一セッションを同時利用しないための排他。
    """
    with _file_lock(session_lock_path(save_root), blocking=blocking):
        yield


def build_logged_in_client(save_root: Path, *, allow_qr_login: bool = False):
    """保存済み authToken で CHRLINE を初期化。失効時、allow_qr_login=True のときだけ QR 再認証に進む。"""
    global _qr_logins_this_process
    cache_key = client_cache_key(save_root)
    cached = _process_client_cache.get(cache_key)
    if cached is not None:
        return cached

    cl = try_client_from_saved_tokens_only(save_root)
    if cl is not None:
        _process_client_cache[cache_key] = cl
        return cl

    if not allow_qr_login:
        print(
            "保存トークンが無効です。QR再認証は許可されていないため終了します。"
            "（取り込み確認などで再ログインするときは、当該スクリプトに --allow-qr-login を付けて実行するか、"
            "chrline_qr_login_poc.py でトークンを保存してから再実行してください。）",
            file=sys.stderr,
        )
        sys.exit(2)

    lock_path = save_root / ".qr_login.lock"
    with _file_lock(lock_path):
        cached = _process_client_cache.get(cache_key)
        if cached is not None:
            return cached
        # Another process may have refreshed the token while we were waiting.
        cl = try_client_from_saved_tokens_only(save_root)
        if cl is not None:
            _process_client_cache[cache_key] = cl
            return cl

        if _qr_logins_this_process >= _max_qr_logins_per_process():
            print(
                "このプロセスでは QR 再認証を既に実施済みです。"
                "オプチャ処理後にセッションが切れた可能性があります。"
                "パートナー LINE だけ取り込む場合は "
                "`chrline_yoritoori_inbox_fetch.py --allow-qr-login --skip-open-chat` を再実行してください。",
                file=sys.stderr,
            )
            sys.exit(2)

        print(
            "保存トークンが無効なため、QR再認証を開始します（LINEアプリで1回承認してください）。",
            file=sys.stderr,
        )
        cl = _perform_qr_relogin(save_root)
        _qr_logins_this_process += 1
        _process_client_cache[cache_key] = cl
        return cl
