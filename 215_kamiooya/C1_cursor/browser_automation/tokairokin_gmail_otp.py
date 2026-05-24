#!/usr/bin/env python3
"""
東海労金インターネットバンキングのワンタイムパスワード通知メールを Gmail API で検索し、
指定時刻以降に届いたメールから OTP を抽出する。

手法は finance/prudential_gmail_otp.py（プルデンシャル生命の確認番号取得）と同じく、
215 の 1b_Cursorマニュアル 配下の Gmail トークン・スコープを利用する。

環境変数（主要）:
- TOKAIROKIN_FETCH_OTP_FROM_GMAIL … fetch_after_login が参照するオプトイン（1/true で Gmail 取得を試す）。
  **既定運用**: config の fetch_otp_from_gmail が false のときは無効。東海労金 OTP はワンタイムPW アプリ＋手入力が主経路。
- TOKAIROKIN_GMAIL_TOKEN_PATH … 省略時は GMAIL_TOKEN_PATH → token_m19m.json → token.json
- TOKAIROKIN_GMAIL_EXPECT_EMAIL … getProfile と期待アドレスの一致確認用
- TOKAIROKIN_OTP_GMAIL_QUERY … 指定時は検索式を全文上書き
- TOKAIROKIN_OTP_GMAIL_FROM … 送信元（カンマ区切り）。空なら件名・newer_than のみで検索
- TOKAIROKIN_OTP_GMAIL_SUBJECT_TERMS … 件名キーワード（カンマ区切り OR）
- TOKAIROKIN_OTP_GMAIL_MAX_WAIT_S / TOKAIROKIN_OTP_GMAIL_POLL_S
- TOKAIROKIN_OTP_GMAIL_CLOCK_SKEW_MS … internalDate しきい値を過去に広げる（時計ずれ対策）
- TOKAIROKIN_OTP_DIGITS … 抽出する桁数（既定 6）

失敗時の診断は stderr に出すが、OTP の値そのものは出力しない。
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
MANUAL_DIR = SCRIPT_DIR.parent / "1b_Cursorマニュアル"


def _ensure_mail_automation_path() -> None:
    mail_auto = MANUAL_DIR.parent / "mail_automation"
    if mail_auto.is_dir() and str(mail_auto) not in sys.path:
        sys.path.insert(0, str(mail_auto))


def _otp_digit_count() -> int:
    raw = os.environ.get("TOKAIROKIN_OTP_DIGITS", "6").strip()
    try:
        n = int(raw)
        return max(4, min(12, n))
    except ValueError:
        return 6


def build_gmail_service_tokairokin():
    """215 の Gmail トークンで Gmail API v1 の service を構築する。"""
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
    env_tok = os.environ.get("TOKAIROKIN_GMAIL_TOKEN_PATH", "").strip()
    env_gmail = os.environ.get("GMAIL_TOKEN_PATH", "").strip()
    if env_tok:
        token_candidate = Path(env_tok).expanduser()
        explicit = True
    elif env_gmail:
        token_candidate = Path(env_gmail).expanduser()
        explicit = True
    else:
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
            "TOKAIROKIN_GMAIL_EXPECT_EMAIL",
            "m19m.hrts83@gmail.com",
        ).strip().lower()
        if expect and em.lower() != expect:
            print(
                f"⚠ 東海労金 OTP の想定受信先 ({expect}) と API のメールアドレス ({em}) が一致しません。"
                " TOKAIROKIN_GMAIL_TOKEN_PATH で正しい token を明示してください。",
                file=sys.stderr,
            )
    except Exception as exc:
        print(f"🐞 Gmail getProfile 失敗（検索は続行）: {exc}", file=sys.stderr)
    return service


def _normalize_digits_jp(s: str) -> str:
    if not s:
        return ""
    return s.translate(str.maketrans("０１２３４５６７８９", "0123456789"))


def _strip_html_for_otp_scan(blob: str) -> str:
    if not blob:
        return ""
    t = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", blob, flags=re.I)
    t = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return t


def _extract_otp_from_subject(subject: str, digits: int) -> str | None:
    if not subject:
        return None
    s = _normalize_digits_jp(subject.strip())
    m = re.match(rf"^(\d{{{digits}}})\b", s)
    if m:
        return m.group(1)
    m = re.search(rf"(?:^|\s)(\d{{{digits}}})(?:\s|$)", s)
    if m:
        return m.group(1)
    return None


def _extract_otp_from_text_blob(blob: str, digits: int) -> str | None:
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
    pat = rf"(?<![0-9])(\d{{{digits}}})(?![0-9])"
    for candidate in variants:
        if not candidate:
            continue
        m = re.search(pat, candidate)
        if m:
            return m.group(1)
    return None


def _build_tokairokin_list_query(*, to_email: str) -> str:
    override = os.environ.get("TOKAIROKIN_OTP_GMAIL_QUERY", "").strip()
    if override:
        return override
    from_raw = os.environ.get("TOKAIROKIN_OTP_GMAIL_FROM", "").strip()
    from_list = [x.strip() for x in from_raw.replace(";", ",").split(",") if x.strip()]
    subj_raw = os.environ.get(
        "TOKAIROKIN_OTP_GMAIL_SUBJECT_TERMS",
        "ワンタイムパスワード,ワンタイム,認証番号,東海労働金庫,東海労金",
    ).strip()
    terms = [x.strip() for x in subj_raw.replace(";", ",").split(",") if x.strip()]
    if not terms:
        terms = ["ワンタイム", "認証番号"]
    if len(terms) == 1:
        subj_part = f"subject:{terms[0]}"
    else:
        subj_part = "(" + " OR ".join(f"subject:{t}" for t in terms) + ")"
    parts: list[str] = []
    if from_list:
        if len(from_list) == 1:
            parts.append(f"from:{from_list[0]}")
        else:
            parts.append("(" + " OR ".join(f"from:{a}" for a in from_list) + ")")
    parts.append(subj_part)
    parts.append("newer_than:2d")
    use_to = os.environ.get("TOKAIROKIN_OTP_GMAIL_USE_TO_FILTER", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    to_q = (to_email or "").strip()
    if use_to and to_q:
        parts.append(f"to:{to_q}")
    extra = os.environ.get("TOKAIROKIN_OTP_GMAIL_QUERY_EXTRA", "").strip()
    if extra:
        parts.append(extra)
    return " ".join(parts)


def _tokairokin_from_addresses() -> list[str]:
    raw = os.environ.get("TOKAIROKIN_OTP_GMAIL_FROM", "").strip()
    return [x.strip() for x in raw.replace(";", ",").split(",") if x.strip()]


def _build_tokairokin_query_variants(*, to_email: str) -> list[str]:
    primary = _build_tokairokin_list_query(to_email=to_email)
    seen: set[str] = set()
    out: list[str] = []
    if primary and primary not in seen:
        seen.add(primary)
        out.append(primary)
    if os.environ.get("TOKAIROKIN_OTP_GMAIL_QUERY", "").strip():
        return out
    if os.environ.get("TOKAIROKIN_OTP_GMAIL_FALLBACK_QUERIES", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return out
    for addr in _tokairokin_from_addresses()[:3]:
        fq = f"from:{addr} newer_than:2d"
        if fq not in seen:
            seen.add(fq)
            out.append(fq)
    fb = (
        "(subject:ワンタイム OR subject:認証 OR subject:OTP OR subject:労働金庫 OR subject:労金) "
        "newer_than:2d"
    )
    if fb not in seen:
        seen.add(fb)
        out.append(fb)
    return out


def _message_plain_text_snippet(payload: dict) -> str:
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


def _env_int_nonneg(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def poll_tokairokin_otp_from_gmail(
    *,
    to_email: str,
    min_internal_date_ms: int,
    max_wait_s: float | None = None,
    poll_s: float | None = None,
) -> str:
    """
    東海労金 OTP 通知メールを Gmail API で検索し、min_internal_date_ms 以降の最新 OTP を返す。
    """
    digits = _otp_digit_count()
    max_wait = (
        float(os.environ.get("TOKAIROKIN_OTP_GMAIL_MAX_WAIT_S", "180") or "180")
        if max_wait_s is None
        else max_wait_s
    )
    poll = (
        float(os.environ.get("TOKAIROKIN_OTP_GMAIL_POLL_S", "4") or "4")
        if poll_s is None
        else poll_s
    )
    skew_ms = _env_int_nonneg("TOKAIROKIN_OTP_GMAIL_CLOCK_SKEW_MS", 180000)
    raw_min_ms = max(0, int(min_internal_date_ms))
    effective_min_ms = max(0, raw_min_ms - skew_ms)
    queries = _build_tokairokin_query_variants(to_email=to_email)
    if len(queries) > 1:
        print(
            f"📧 [東海労金 OTP] Gmail 検索は最大 {len(queries)} パターンを順に試します。",
            file=sys.stderr,
        )

    service = build_gmail_service_tokairokin()
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
                code = _extract_otp_from_subject(subj, digits) or _extract_otp_from_text_blob(
                    f"{snippet}\n{body_text}", digits
                )
                if code:
                    cand = (internal, code)
                    if best is None or internal > best[0]:
                        best = cand
                elif (subj or snippet) and not warned_no_extract:
                    warned_no_extract = True
                    print(
                        "🐞 しきい値を満たすメールはあるが、"
                        f"件名・snippet・本文から {digits} 桁を抽出できませんでした。",
                        file=sys.stderr,
                    )
        if best is not None:
            print(
                "📧 Gmail から東海労金 OTP を取得しました（値はログに出しません）。",
                file=sys.stderr,
            )
            return best[1]
        nowp = time.monotonic()
        if nowp - last_progress >= 25.0:
            rem = max(0.0, deadline - nowp)
            print(
                f"📧 [東海労金 OTP] 検索継続中… 残り約 {rem:.0f}s "
                f"(effective_min_internalDate>={effective_min_ms})",
                file=sys.stderr,
            )
            last_progress = nowp
        time.sleep(max(1.0, poll))

    primary_q = queries[0] if queries else ""
    raise RuntimeError(
        f"Gmail から東海労金 OTP を {max_wait}s 以内に取得できませんでした。"
        f" primary_query={primary_q!r} effective_min_internalDate>={effective_min_ms} "
        f"(raw_min={raw_min_ms}, skew_ms={skew_ms}) "
        "送信元・件名が想定と違う場合は TOKAIROKIN_OTP_GMAIL_FROM / TOKAIROKIN_OTP_GMAIL_QUERY を設定してください。"
    )
