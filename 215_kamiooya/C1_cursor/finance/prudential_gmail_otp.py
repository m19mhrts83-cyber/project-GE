#!/usr/bin/env python3
"""
プルデンシャル生命「Myページ確認番号」メールを Gmail API で検索し、
ログイン送信後に届いた新着メールから 6 桁を取得する（件名・snippet・本文テキストのいずれか）。

215 の 1b_Cursorマニュアル の Gmail トークン（readonly/modify/send スコープ）を使用。
既定では token_m19m.json があればそれを優先し、確認番号の想定受信先は m19m.hrts83@gmail.com。
PRUDENTIAL_GMAIL_TOKEN_PATH で明示すると GMAIL_TOKEN_PATH より優先される。

取得失敗の典型原因と環境変数:
- 検索にヒットしない: 実際の From/件名が既定と違う → PRUDENTIAL_OTP_GMAIL_FROM（カンマ区切り）
  または PRUDENTIAL_OTP_GMAIL_QUERY で全文上書き。
- internalDate しきい値より古いと除外: PC 時計と Gmail のずれ → PRUDENTIAL_OTP_GMAIL_CLOCK_SKEW_MS（既定 180000）。
- ログインクリック後に settle 等で時間が空くと、元の lookback だけでは足りない → 呼び出し側で
  PRUDENTIAL_OTP_GMAIL_POST_LOGIN_SLACK_MS を足して min_internal を広げる。
- 主検索が 0 件のとき `from:… newer_than:2d` 等のフォールバック検索（PRUDENTIAL_OTP_GMAIL_FALLBACK_QUERIES）。
- PRUDENTIAL_OTP_GMAIL_MAX_WAIT_S 既定 180（長い settle 後もポーリングし切れるように）。
- 本文が HTML/全角数字: タグ除去・全角→半角・空白除去を試行済み。

失敗時は stderr に 🐞 診断（件名・From・時刻比較、番号は出さない）。
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
from pathlib import Path

FINANCE_DIR = Path(__file__).resolve().parent
MANUAL_DIR = FINANCE_DIR.parent / "1b_Cursorマニュアル"


def _ensure_mail_automation_path() -> None:
    mail_auto = MANUAL_DIR.parent / "mail_automation"
    if mail_auto.is_dir() and str(mail_auto) not in sys.path:
        sys.path.insert(0, str(mail_auto))


def _build_gmail_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    if not MANUAL_DIR.is_dir():
        raise RuntimeError(f"1b_Cursorマニュアル が見つかりません: {MANUAL_DIR}")

    sys.path.insert(0, str(MANUAL_DIR))
    from gmail_api_scopes import (  # noqa: E402
        GMAIL_SCOPES_215,
        resolve_single_token_path_215,
        token_satisfies_215_scopes,
    )

    _ensure_mail_automation_path()
    try:
        from gmail_token_sync import save_token_json_and_sync
    except ImportError:

        def save_token_json_and_sync(token_path, creds_json, *, log_prefix: str = "") -> None:
            Path(token_path).write_text(creds_json, encoding="utf-8")

    credentials_path = Path(os.environ.get("GMAIL_CREDENTIALS_PATH", MANUAL_DIR / "credentials.json"))
    # このモジュールではプルデンシャル専用パスを GMAIL_TOKEN_PATH より優先（別用途の token を避ける）
    env_pru = os.environ.get("PRUDENTIAL_GMAIL_TOKEN_PATH", "").strip()
    env_gmail = os.environ.get("GMAIL_TOKEN_PATH", "").strip()
    if env_pru:
        token_candidate = Path(env_pru).expanduser()
        explicit = True
    elif env_gmail:
        token_candidate = Path(env_gmail).expanduser()
        explicit = True
    else:
        # プルデンシャル確認番号は m19m.hrts83@gmail.com 宛が一般的。token.json が別アカウントだと
        # 検索 0 件になるため、存在すれば token_m19m.json を既定の候補にする。
        m19m_tok = MANUAL_DIR / "token_m19m.json"
        token_candidate = m19m_tok if m19m_tok.is_file() else (MANUAL_DIR / "token.json")
        explicit = False
    token_path = resolve_single_token_path_215(
        MANUAL_DIR, token_candidate, explicit_via_env=explicit
    )
    if not token_path.exists():
        raise RuntimeError(f"Gmail token がありません: {token_path}")

    raw = json.loads(token_path.read_text(encoding="utf-8"))
    if not token_satisfies_215_scopes(raw):
        raise RuntimeError(
            "Gmail token のスコープが不足しています（gmail.readonly / modify / send が必要）。"
            f" token: {token_path}"
        )

    creds_data = dict(raw)
    if "client_id" not in creds_data and credentials_path.exists():
        cred_json = json.loads(credentials_path.read_text(encoding="utf-8"))
        client = cred_json.get("installed") or cred_json.get("web", {})
        creds_data["client_id"] = client.get("client_id")
        creds_data["client_secret"] = client.get("client_secret")
        creds_data["token_uri"] = "https://oauth2.googleapis.com/token"
        if "access_token" in creds_data and "token" not in creds_data:
            creds_data["token"] = creds_data["access_token"]

    creds = Credentials.from_authorized_user_info(creds_data, GMAIL_SCOPES_215)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_token_json_and_sync(token_path, creds.to_json())

    service = build("gmail", "v1", credentials=creds)
    try:
        prof = service.users().getProfile(userId="me").execute()
        em = (prof.get("emailAddress") or "").strip()
        print(f"📧 Gmail API 利用アカウント: {em}（token: {token_path.name}）", file=sys.stderr)
        expect = os.environ.get(
            "PRUDENTIAL_GMAIL_EXPECT_EMAIL",
            "m19m.hrts83@gmail.com",
        ).strip().lower()
        if expect and em.lower() != expect:
            print(
                f"⚠ プルデンシャル確認番号の想定受信先 ({expect}) と API のメールアドレス ({em}) が一致しません。"
                " 別アカウントの受信箱を見ていると検索 0 件になります。"
                " PRUDENTIAL_GMAIL_TOKEN_PATH で token_m19m.json を明示するか、"
                " 1b_Cursorマニュアル/token_m19m.json を用意してください。",
                file=sys.stderr,
            )
    except Exception as exc:
        print(f"🐞 Gmail getProfile 失敗（検索は続行）: {exc}", file=sys.stderr)
    return service


def _extract_otp_from_subject(subject: str) -> str | None:
    if not subject:
        return None
    s = _normalize_digits_jp(subject.strip())
    m = re.match(r"^(\d{6})\b", s)
    if m:
        return m.group(1)
    m = re.search(r"(?:^|\s)(\d{6})(?:\s|$)", s)
    if m:
        return m.group(1)
    return None


def _normalize_digits_jp(s: str) -> str:
    """全角数字を半角に（メール本文が全角のみの場合の救済）。"""
    if not s:
        return ""
    return s.translate(str.maketrans("０１２３４５６７８９", "0123456789"))


def _strip_html_for_otp_scan(blob: str) -> str:
    """HTML タグを除いた文字列（タグに埋もれた 6 桁を拾う）。"""
    if not blob:
        return ""
    t = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", blob, flags=re.I)
    t = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return t


def _extract_otp_from_text_blob(blob: str) -> str | None:
    """件名・snippet・本文から最初の6桁（確認番号想定）を取る。"""
    if not blob:
        return None
    nospace = re.sub(r"\s+", "", blob)
    variants = (
        blob,
        nospace,
        _normalize_digits_jp(blob),
        _normalize_digits_jp(nospace),
        _strip_html_for_otp_scan(blob),
        _normalize_digits_jp(_strip_html_for_otp_scan(blob)),
    )
    for candidate in variants:
        if not candidate:
            continue
        m = re.search(r"(?<![0-9])(\d{6})(?![0-9])", candidate)
        if m:
            return m.group(1)
    return None


def _build_prudential_list_query(*, to_email: str) -> str:
    """Gmail search query（環境変数で上書き・拡張可能）。"""
    override = os.environ.get("PRUDENTIAL_OTP_GMAIL_QUERY", "").strip()
    if override:
        return override
    from_raw = os.environ.get(
        "PRUDENTIAL_OTP_GMAIL_FROM",
        "cyberadmin@prudential.co.jp",
    ).strip()
    from_list = [x.strip() for x in from_raw.replace(";", ",").split(",") if x.strip()]
    if not from_list:
        from_list = ["cyberadmin@prudential.co.jp"]
    if len(from_list) == 1:
        from_part = f"from:{from_list[0]}"
    else:
        from_part = "(" + " OR ".join(f"from:{a}" for a in from_list) + ")"
    subj_raw = os.environ.get("PRUDENTIAL_OTP_GMAIL_SUBJECT_TERMS", "確認番号").strip()
    terms = [x.strip() for x in subj_raw.replace(";", ",").split(",") if x.strip()]
    if not terms:
        terms = ["確認番号"]
    if len(terms) == 1:
        subj_part = f"subject:{terms[0]}"
    else:
        subj_part = "(" + " OR ".join(f"subject:{t}" for t in terms) + ")"
    parts = [from_part, subj_part]
    use_to = os.environ.get("PRUDENTIAL_OTP_GMAIL_USE_TO_FILTER", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    to_q = (to_email or "").strip()
    if use_to and to_q:
        parts.append(f"to:{to_q}")
    extra = os.environ.get("PRUDENTIAL_OTP_GMAIL_QUERY_EXTRA", "").strip()
    if extra:
        parts.append(extra)
    return " ".join(parts)


def _prudential_gmail_from_addresses() -> list[str]:
    raw = os.environ.get(
        "PRUDENTIAL_OTP_GMAIL_FROM",
        "cyberadmin@prudential.co.jp",
    ).strip()
    lst = [x.strip() for x in raw.replace(";", ",").split(",") if x.strip()]
    return lst or ["cyberadmin@prudential.co.jp"]


def _build_prudential_gmail_query_variants(*, to_email: str) -> list[str]:
    """主検索 + フォールバック（件名・送信元のゆれ・遅延着信で主検索が 0 件のとき）。"""
    primary = _build_prudential_list_query(to_email=to_email)
    seen: set[str] = set()
    out: list[str] = []
    if primary and primary not in seen:
        seen.add(primary)
        out.append(primary)
    if os.environ.get("PRUDENTIAL_OTP_GMAIL_QUERY", "").strip():
        return out
    if os.environ.get("PRUDENTIAL_OTP_GMAIL_FALLBACK_QUERIES", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return out
    for addr in _prudential_gmail_from_addresses()[:3]:
        fq = f"from:{addr} newer_than:2d"
        if fq not in seen:
            seen.add(fq)
            out.append(fq)
    subj_line = "(subject:確認 OR subject:マイページ OR subject:Myページ) newer_than:2d"
    if subj_line not in seen:
        seen.add(subj_line)
        out.append(subj_line)
    return out


def _message_plain_text_snippet(payload: dict) -> str:
    """Gmail API payload からプレーンテキストを再帰収集（長すぎる場合は先頭のみ）。"""
    out: list[str] = []

    def walk(part: dict) -> None:
        if not part:
            return
        mime = (part.get("mimeType") or "").lower()
        body = part.get("body") or {}
        data = body.get("data")
        if data and mime.startswith("text/"):
            try:
                raw = base64.urlsafe_b64decode(data.encode("ascii")).decode("utf-8", errors="ignore")
                out.append(raw[:8000])
            except Exception:
                pass
        for sub in part.get("parts") or []:
            walk(sub)

    walk(payload)
    return "\n".join(out)[:12000]


def _env_int_nonneg_gmail(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def _diagnose_prudential_otp_miss(
    service,
    *,
    primary_q: str,
    effective_min_ms: int,
    raw_min_ms: int,
    skew_ms: int,
) -> None:
    """失敗時: 検索ヒット・時刻フィルタ・送信元を stderr に出す（本文・番号は出さない）。"""
    try:
        resp = service.users().messages().list(userId="me", q=primary_q, maxResults=20).execute()
        n_pri = len(resp.get("messages") or [])
        print(
            f"🐞 [Prudential Gmail] 主検索の list 件数: {n_pri} query={primary_q!r}",
            file=sys.stderr,
        )
    except Exception as exc:
        print(f"🐞 [Prudential Gmail] 主検索 list 失敗: {exc}", file=sys.stderr)
        n_pri = -1
    relaxed = os.environ.get(
        "PRUDENTIAL_OTP_GMAIL_DIAG_RELAXED_QUERY",
        "subject:確認番号 newer_than:3d",
    ).strip()
    try:
        resp2 = service.users().messages().list(userId="me", q=relaxed, maxResults=8).execute()
        mids = [m["id"] for m in resp2.get("messages", [])][:5]
        print(
            f"🐞 [Prudential Gmail] 緩い検索（診断用）件数: {len(resp2.get('messages') or [])} "
            f"query={relaxed!r}",
            file=sys.stderr,
        )
        for mid in mids:
            full = (
                service.users().messages().get(userId="me", id=mid, format="full").execute()
            )
            internal = int(full.get("internalDate", "0"))
            headers = {h["name"]: h["value"] for h in full.get("payload", {}).get("headers", [])}
            subj = (headers.get("Subject") or "")[:120]
            frm = (headers.get("From") or "")[:160]
            passes = internal >= effective_min_ms
            print(
                f"🐞   id={mid[:12]}… internalDate={internal} "
                f">= effective_min({effective_min_ms})? {passes} | From: {frm!r} | Subj: {subj!r}",
                file=sys.stderr,
            )
    except Exception as exc:
        print(f"🐞 [Prudential Gmail] 緩い検索の取得失敗: {exc}", file=sys.stderr)
    print(
        f"🐞 [Prudential Gmail] 時刻しきい値: raw_min={raw_min_ms} skew_ms={skew_ms} "
        f"→ effective_min={effective_min_ms}（PC と Gmail の時刻差でメールが除外されないよう skew を足す）",
        file=sys.stderr,
    )
    if n_pri == 0:
        print(
            "🐞 [Prudential Gmail] 主検索が 0 件のときは "
            "送信元・件名が想定と違う可能性があります。PRUDENTIAL_OTP_GMAIL_FROM や "
            "PRUDENTIAL_OTP_GMAIL_QUERY（全文上書き）を確認してください。",
            file=sys.stderr,
        )


def poll_prudential_otp_from_gmail(
    *,
    to_email: str,
    min_internal_date_ms: int,
    max_wait_s: float | None = None,
    poll_s: float | None = None,
) -> str:
    """
    プルデンシャル生命の確認番号通知を Gmail API で検索し、ログイン送信後に届いた最新の 6 桁を返す。

    min_internal_date_ms は呼び出し側の「ログイン送信時刻 - lookback」。さらに
    PRUDENTIAL_OTP_GMAIL_CLOCK_SKEW_MS 分だけ過去に広げ、PC 時計と Gmail internalDate のずれで
    取りこぼさないようにする。
    呼び出し側で PRUDENTIAL_OTP_GMAIL_STRICT_AFTER_LOGIN=1 のときは lookback が狭くなり、
    過去のログインで届いた確認番号メールを除外しやすい。
    """
    max_wait = (
        float(os.environ.get("PRUDENTIAL_OTP_GMAIL_MAX_WAIT_S", "180") or "180")
        if max_wait_s is None
        else max_wait_s
    )
    poll = (
        float(os.environ.get("PRUDENTIAL_OTP_GMAIL_POLL_S", "4") or "4")
        if poll_s is None
        else poll_s
    )
    skew_ms = _env_int_nonneg_gmail("PRUDENTIAL_OTP_GMAIL_CLOCK_SKEW_MS", 180000)
    raw_min_ms = max(0, int(min_internal_date_ms))
    effective_min_ms = max(0, raw_min_ms - skew_ms)
    queries = _build_prudential_gmail_query_variants(to_email=to_email)
    if len(queries) > 1:
        print(
            f"📧 Gmail 検索は最大 {len(queries)} パターンを順に試します（フォールバックあり）。",
            file=sys.stderr,
        )

    service = _build_gmail_service()
    deadline = time.monotonic() + max(5.0, max_wait)
    best: tuple[int, str] | None = None
    last_progress = time.monotonic()
    warned_no_extract = False

    while time.monotonic() < deadline:
        for qi, q in enumerate(queries):
            try:
                resp = service.users().messages().list(userId="me", q=q, maxResults=15).execute()
            except Exception as exc:
                print(f"🐞 Gmail list エラー (query#{qi + 1}): {exc}", file=sys.stderr)
                continue
            mids = [m["id"] for m in resp.get("messages", [])]
            for mid in mids:
                full = (
                    service.users()
                    .messages()
                    .get(userId="me", id=mid, format="full")
                    .execute()
                )
                internal = int(full.get("internalDate", "0"))
                if internal < effective_min_ms:
                    continue
                headers = {h["name"]: h["value"] for h in full.get("payload", {}).get("headers", [])}
                subj = headers.get("Subject", "")
                snippet = full.get("snippet") or ""
                body_text = _message_plain_text_snippet(full.get("payload") or {})
                code = _extract_otp_from_subject(subj) or _extract_otp_from_text_blob(
                    f"{snippet}\n{body_text}"
                )
                if code:
                    cand = (internal, code)
                    if best is None or internal > best[0]:
                        best = cand
                elif (subj or snippet) and not warned_no_extract:
                    warned_no_extract = True
                    print(
                        "🐞 しきい値を満たすメールはあるが、件名・snippet・本文から 6 桁を抽出できませんでした。"
                        " 画像のみ・桁が分割されている等の可能性があります。",
                        file=sys.stderr,
                    )
        if best is not None:
            print(
                "📧 Gmail からプルデンシャル確認番号を取得しました（チャットには番号を出しません）。",
                file=sys.stderr,
            )
            return best[1]
        nowp = time.monotonic()
        if nowp - last_progress >= 25.0:
            rem = max(0.0, deadline - nowp)
            print(
                f"📧 Gmail 検索継続中… 残り約 {rem:.0f}s（effective_min_internalDate>={effective_min_ms}）",
                file=sys.stderr,
            )
            last_progress = nowp
        time.sleep(max(1.0, poll))

    primary_q = queries[0] if queries else ""
    _diagnose_prudential_otp_miss(
        service,
        primary_q=primary_q,
        effective_min_ms=effective_min_ms,
        raw_min_ms=raw_min_ms,
        skew_ms=skew_ms,
    )
    raise RuntimeError(
        f"Gmail から確認番号を {max_wait}s 以内に取得できませんでした。"
        f" primary_query={primary_q!r} effective_min_internalDate>={effective_min_ms} "
        f"(raw_min={raw_min_ms}, skew_ms={skew_ms})"
    )
