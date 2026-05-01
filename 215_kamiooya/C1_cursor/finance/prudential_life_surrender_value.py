#!/usr/bin/env python3
"""
ライフプラン自動化 Step5:
プルデンシャル生命の契約者向けWebから解約返戻金を抽出する。

複数利用者は PRUDENTIAL_USERNAME_1/2/… と PRUDENTIAL_PASSWORD_1/2/… で指定。
1人目でログイン→取得→セッション解除→2人目で再ログイン…を順に行う。

ログイン後の導線（優先順）:
1) PRUDENTIAL_TARGET_URL があれば直接遷移
2) PRUDENTIAL_AFTER_LOGIN_CLICK_* があれば1クリック
3) PRUDENTIAL_NAV_STEP1_* … PRUDENTIAL_NAV_STEP20_* を順に実行（各ステップで SELECTOR または TEXT）
4) 上記がすべて空なら **既定ナビ（マイページ想定）**:
   「契約内容」→ 契約一覧の先頭相当のタイトルリンク → 「解約返戻金」タブ
   （タブは `c-mypg-contr-cont-inq-basic-detail` 内の `a.m-tab-btn` であることが多く、
   `PRUDENTIAL_SURRENDER_TAB_SELECTOR` または `PRUDENTIAL_SURRENDER_TAB_HOST_SELECTOR` で上書き可）

画面の待ち時間（ms・任意で調整）:
- PRUDENTIAL_LOGIN_MAIN_PROBE_MS … **メイン document** で ID 欄を探す最大待ち（既定 45000）。
  Salesforce 系で入力が **iframe 内**にあると、メインでは永遠に出ないため、ここで諦めて別フレームへ回す。
  旧実装はメインに --timeout-ms 全額を使い切り、iframe に残り時間が無くなる不具合があった。
- PRUDENTIAL_LOGIN_PAGE_READY_MS … ログイン**前**の追加待機（既定 0）。ID／PW 画面にアニメーション前提は置かず、
  要素の wait_for で待つ。LWC で入力が遅れて見えるときは 5000〜10000 程度を試す。
- PRUDENTIAL_LOGIN_FORM_HOST_SELECTOR … **任意**。ログイン枠のカスタム要素が DOM に載るまで待つ（既定:
  `c-mypg-login-info-input-detail`）。空にするとこの待機をスキップ。
- PRUDENTIAL_POST_LOGIN_ANIMATION_MS … 従来どおり読み込むが、**主な待ち**は
  `PRUDENTIAL_POST_LOGIN_SETTLE_MS` による「マイページ or 確認番号画面の安定待ち」に置き換え。
  安定後は `PRUDENTIAL_POST_LOGIN_EXTRA_ANIM_MS`（既定 2000ms）だけ追加待ち。
- PRUDENTIAL_POST_LOGIN_SETTLE_MS … ログイン直後、**マイページ or 確認番号ステップ**が判別できるまでの最大待ち（既定 90000）。
  確認番号画面が一瞬で消えてログインに戻る SPA 対策。
- PRUDENTIAL_POST_LOGIN_SETTLE_POLL_MS … 上記のポーリング間隔 ms（既定 400）。
- PRUDENTIAL_OTP_STEP_STABLE_MS … 確認番号欄・文言が**連続して**見えているとみなす最短 ms（既定 2000）。チラ見え除外。
- PRUDENTIAL_POST_LOGIN_EXTRA_ANIM_MS … 安定検出後の追加待ち ms（既定 2000）。
- PRUDENTIAL_AFTER_OTP_ANIMATION_MS … 確認番号送信後、マイページ本体まで
- PRUDENTIAL_POST_LOGIN_WAIT_MS … 解約返戻金ナビ開始前の追加待ち（既定 10000）

Gmail 連携（確認番号）:
- PRUDENTIAL_FETCH_OTP_FROM_GMAIL … **未設定時はオン（1 と同じ）**。Gmail API で
  cyberadmin@prudential.co.jp の通知から6桁をポーリング（件名・snippet・本文のいずれかから抽出）。
  `0` / `false` でオフ。215 の 1b token（readonly 等）要。
- PRUDENTIAL_PAUSE_BEFORE_GMAIL_OTP_MS … 確認番号画面のあと **Gmail 取得を始めるまで**待つ ms（画面・受信確認用）。
- PRUDENTIAL_OTP_GMAIL_LOOKBACK_MS … ベースの過去幅（ms）。実際は **settle 後の経過時間 + PRUDENTIAL_OTP_GMAIL_POST_LOGIN_SLACK_MS** と比べて広い方を採用し、遅延着信を拾う。
- PRUDENTIAL_OTP_GMAIL_POST_LOGIN_SLACK_MS … 上記の余裕（既定 120000）。
- PRUDENTIAL_OTP_GMAIL_STRICT_AFTER_LOGIN … **1 のとき** Gmail のしきい値を
  `ログイン送信時刻 - PRUDENTIAL_OTP_GMAIL_STRICT_LOOKBACK_MS` のみに固定し、
  **今回のログインより前に届いている通知を採用しない**（過去実行の確認番号メールを除外しやすい）。
  既定 0（従来どおり経過時間でしきい値を広げる）。
- PRUDENTIAL_OTP_GMAIL_STRICT_LOOKBACK_MS … 上記の「ログインよりどれだけ手前まで許容するか」ms（既定 120000）。
- PRUDENTIAL_OTP_GMAIL_MAX_WAIT_S … `prudential_gmail_otp` の検索ポーリング最大秒。
- PRUDENTIAL_OTP_GMAIL_CLOCK_SKEW_MS … **internalDate しきい値をさらに過去に広げる ms**（PC 時計と Gmail のずれ対策。既定 180000）。
- PRUDENTIAL_OTP_GMAIL_FROM … 送信元（カンマ区切りで複数可。既定 cyberadmin@prudential.co.jp）。
- PRUDENTIAL_OTP_GMAIL_SUBJECT_TERMS … 件名検索語（カンマ区切りで OR。既定 確認番号）。
- PRUDENTIAL_OTP_GMAIL_QUERY … 上記を無視して Gmail 検索式を **全文指定**。
- 取得失敗時 … stderr に 🐞 診断（件名・From・時刻比較。番号は出さない）。
- `--fetch-otp-gmail` / `--no-fetch-otp-gmail` でコマンドラインから上書き可。

信頼できる端末:
- PRUDENTIAL_TRUST_DEVICE_CHECK … **未設定時はオン**。確認番号画面で「信頼できる端末に登録する」に
  チェックを入れてから入力・送信する（次回以降 OTP が省略されやすくなる想定）。`0` でスキップ。

デバッグ（ログイン送信直後）:
- PRUDENTIAL_DEBUG_LOGIN_SUBMIT=1 または `--login-submit-debug` …
  ログインボタンクリック後（POST_LOGIN_ANIMATION 待ちのあと）に URL・タイトル・HTML・PNG を
  `finance/debug/prudential_login_submit_after_anim_accountN.*` に保存し stderr にパスを出す。
  ステップ1（確認番号画面か／エラーか）の切り分け用。
- PRUDENTIAL_DEBUG_LOGIN_FORM_FAIL=1 または `--dump-login-form-fail` …
  **ID／パスワード欄が見つからない**とき（fill より前で失敗するとき）に
  `finance/debug/prudential_login_form_fail_accountN.*` を保存。
  未設定時は `--login-submit-debug` と同じオン／オフに追従（どちらも無効なら保存しない）。
- PRUDENTIAL_DEBUG_PAUSE_BEFORE_LOGIN_MS または `--pause-before-login-sec` …
  **ログイン欄を探す直前**に追加待機（ms）。Chromium を開いたまま DevTools でセレクタ確認する用。
- PRUDENTIAL_DEBUG_PAUSE_ON_LOGIN_FORM_FAIL_MS または `--pause-on-login-fail-sec` …
  **入力欄未検出で失敗した直後**（ダンプ後）、ブラウザを閉じる前に待機（ms）。

ログイン欄（動的 ID 対策）:
- PRUDENTIAL_LOGIN_HEURISTIC_FALLBACK=1（既定）… `.env` の固定セレクタで見つからないとき、
  ログイン枠（PRUDENTIAL_LOGIN_FORM_HOST_SELECTOR・既定 `c-mypg-login-info-input-detail`）内で
  `input[id^="input-"]` / `input[type="password"]` / 「ログイン」ボタンをヒューリスティックに解決する。

確認番号入力（Lightning）:
- ログイン ID は `input[id^="input-"]`、確認番号は `input[id^="confirmNumber"]` など **別 id**。
  `PRUDENTIAL_OTP_SELECTOR` にログイン用と同系の広いセレクタ（例: 単なる lightning-input）を
  指定すると **ログイン ID 欄に確認番号が入る**ことがある。必ず確認番号専用（`confirmNumber` 系）を指定。
- 任意で確認番号ブロックだけに絞る: `PRUDENTIAL_OTP_HOST_SELECTOR`（未設定時はフレーム全体から探索）。
- fill だけで検証エラーが消えない場合は `_fill_otp_field_lightning_compat` が補う。

セッション継続（確認番号のやり直し）:
- ログインから再実行すると **新しい確認番号** が要るため、確認番号画面に達した時点で
  Playwright の `storage_state` を `DEFAULT_OTP_STORAGE_STATE` に保存する。
- `--resume-otp`（または `PRUDENTIAL_RESUME_OTP_ONLY=1`）で **ログインをスキップ**し、
  保存 URL へ遷移してから Gmail／`--otp-code`／対話入力で番号を入れる。
- 保存先: `PRUDENTIAL_OTP_STORAGE_STATE_PATH` / `PRUDENTIAL_OTP_RESUME_META_PATH`（未設定時は
  `finance/.prudential_otp_storage_state.json` と `.prudential_otp_resume_meta.json`）。
  クッキーを含むため取り扱いに注意。

金額抽出:
- PRUDENTIAL_SURRENDER_VALUE_SELECTOR が最優先
- 次に「解約した場合のお支払い予定額」等の見出し近傍（プルデンシャル画面向け）
- 表の th に PRUDENTIAL_SURRENDER_ROW_TH_CONTAINS（既定: 解約返戻金）を含む行
- PRUDENTIAL_SURRENDER_VALUE_LABEL でラベル近傍探索
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = SCRIPT_DIR / ".env.lifeplan"
DEFAULT_DEBUG_DIR = SCRIPT_DIR / "debug"
# ログイン後・確認番号画面で保存（再実行時は --resume-otp でログインし直さず続行）
DEFAULT_OTP_STORAGE_STATE = SCRIPT_DIR / ".prudential_otp_storage_state.json"
DEFAULT_OTP_RESUME_META = SCRIPT_DIR / ".prudential_otp_resume_meta.json"

_MAX_NAV_STEPS = 20


@dataclass
class PrudentialSurrenderAccountResult:
    """1利用者IDあたりの解約返戻金。"""

    account_index: int
    username: str
    value_jpy: int
    value_text: str
    source_url: str
    parser_mode: str


@dataclass
class PrudentialSurrenderValueResult:
    """items に各アカウントの結果。value_jpy は合計。"""

    items: list[PrudentialSurrenderAccountResult]
    value_jpy: int
    value_text: str
    source_url: str
    parser_mode: str


class PrudentialOtpPausedBeforeSubmit(Exception):
    """確認番号入力後・「次へ」送信前で意図的に停止したとき（失敗ではない）。"""


class PrudentialOtpPausedAtScreen(Exception):
    """確認番号入力画面到達直後（Gmail・番号入力の前）で意図的に停止したとき（失敗ではない）。"""


class PrudentialPausedAtContractList(Exception):
    """契約一覧画面で、契約リンククリック前に意図的に停止したとき（失敗ではない）。"""


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


def prudential_step_configured(env_file: Path) -> bool:
    """PRUDENTIAL_LOGIN_URL が設定されていれば Step5 を実行対象とする。"""
    _load_env_file(env_file)
    return bool(os.environ.get("PRUDENTIAL_LOGIN_URL", "").strip())


def _parse_first_jpy(text: str) -> tuple[int | None, str]:
    normalized = (text or "").replace("\u3000", " ")
    m = re.search(r"([+-]?\d[\d,]{0,})(?:\s*円)?", normalized)
    if not m:
        return None, ""
    raw = m.group(1).replace(",", "")
    if not raw:
        return None, ""
    try:
        value = int(raw)
    except ValueError:
        return None, ""
    return value, m.group(0).strip()


def _wait_page_ready(page, timeout_ms: int) -> None:
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    try:
        page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 10000))
    except Exception:
        pass


def _wait_login_shell_ready(page, timeout_ms: int) -> None:
    """ログイン URL 直後: domcontentloaded のみ。networkidle は計測・広告で長引きやすく、ID 欄待ちを遅らせる。"""
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)


def _login_probe_frames(page):
    """ログイン用: メインフレームを最優先（フォームは通常ここ。誤 iframe を先に長待ちしない）。"""
    main = page.main_frame
    out: list = []
    seen: set[int] = set()
    for fr in [main] + list(getattr(page, "frames", []) or []):
        fid = id(fr)
        if fid in seen:
            continue
        seen.add(fid)
        out.append(fr)
    return out if out else [main]


def _sleep_ms(page, ms: int) -> None:
    if ms <= 0:
        return
    try:
        page.wait_for_timeout(ms)
    except Exception:
        pass


def _dump_prudential_page_debug(
    page,
    account_no: int,
    *,
    file_stem: str,
    log_prefix: str,
) -> None:
    """URL・タイトル・HTML・PNG を finance/debug に保存（汎用）。"""
    DEFAULT_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    html_path = DEFAULT_DEBUG_DIR / f"{file_stem}.html"
    png_path = DEFAULT_DEBUG_DIR / f"{file_stem}.png"
    try:
        url = page.url or ""
        title = page.title() or ""
    except Exception:
        url, title = "", ""
    try:
        html_path.write_text(page.content(), encoding="utf-8")
    except Exception:
        pass
    try:
        page.screenshot(path=str(png_path), full_page=True)
    except Exception:
        pass
    print(
        f"🐞 {log_prefix} account{account_no} "
        f"url={url!r} title={title!r} → {html_path.name} / {png_path.name}",
        file=sys.stderr,
    )


def _dump_login_submit_debug(page, account_no: int, phase: str) -> None:
    """ログイン送信〜待機後の画面を HTML/PNG で残す（確認番号画面の切り分け用）。"""
    stem = f"prudential_login_submit_{phase}_account{account_no}"
    _dump_prudential_page_debug(
        page,
        account_no,
        file_stem=stem,
        log_prefix=f"ログイン送信デバッグ [{phase}]",
    )


def _dump_login_form_fail_debug(page, account_no: int) -> None:
    """ログイン欄が解決できないときの画面（ID/PW の fill より前で失敗した場合の切り分け用）。"""
    stem = f"prudential_login_form_fail_account{account_no}"
    _dump_prudential_page_debug(
        page,
        account_no,
        file_stem=stem,
        log_prefix="ログイン入力欄未検出デバッグ",
    )


def _resolve_login_form_locators(
    page,
    username_selector: str,
    password_selector: str,
    submit_selector: str,
    timeout_ms: int,
):
    """
    ログインID／パスワード／送信を同一フレーム内で解決する。

    - **メインフレームを先に**試すが、待ちには **上限**を設ける。入力が iframe 内のみにあるサイトでは、
      メインで「残りタイムアウト全額」を使うと **iframe に回る前に期限切れ**になり失敗する。
    - **サブフレーム**は広告等の誤マッチが多いので、短い上限だけ試す。
    """
    budget_ms = max(int(timeout_ms), 60_000)
    deadline = time.monotonic() + budget_ms / 1000.0
    main_probe = int(os.environ.get("PRUDENTIAL_LOGIN_MAIN_PROBE_MS", "45000") or "45000")
    main_probe = max(5000, min(main_probe, 180_000))
    iframe_probe = int(os.environ.get("PRUDENTIAL_LOGIN_IFRAME_PROBE_MS", "0") or "0")
    if iframe_probe <= 0:
        iframe_probe = int(os.environ.get("PRUDENTIAL_LOGIN_FRAME_PROBE_MS", "6000") or "6000")
    iframe_probe = max(2000, min(iframe_probe, 30_000))
    last_exc: BaseException | None = None
    frames = _login_probe_frames(page)

    for i, fr in enumerate(frames):
        remaining_ms = int(max(500, (deadline - time.monotonic()) * 1000))
        if remaining_ms < 2000:
            break
        # _login_probe_frames は常にメインを先頭に入れる（Frame オブジェクト同一性に依存しない）
        is_main = i == 0
        u_cap = min(remaining_ms, main_probe) if is_main else min(remaining_ms, iframe_probe)
        try:
            u = fr.locator(username_selector).first
            u.wait_for(state="visible", timeout=u_cap)
            rem2 = int(max(500, (deadline - time.monotonic()) * 1000))
            p = fr.locator(password_selector).first
            try:
                p.wait_for(state="visible", timeout=min(rem2, 120_000))
            except Exception:
                p.wait_for(state="attached", timeout=min(rem2, 60_000))
            rem3 = int(max(500, (deadline - time.monotonic()) * 1000))
            s = fr.locator(submit_selector).first
            s.wait_for(state="attached", timeout=min(rem3, 60_000))
            return u, p, s
        except Exception as e:
            last_exc = e
            continue

    raise RuntimeError(
        "ログイン画面の入力欄が表示されませんでした（"
        f"USER={username_selector!r} / PASS={password_selector!r} / SUBMIT={submit_selector!r}）。"
        "メイン→iframe の順で探索しています。入力が iframe 内だけの場合、"
        "PRUDENTIAL_LOGIN_MAIN_PROBE_MS（メイン側の諦め時間・既定 45000）を短くし、"
        "PRUDENTIAL_LOGIN_IFRAME_PROBE_MS を伸ばして再試行してください。"
        " セレクタ・ログイン URL・--timeout-ms・ヘッドレス外しも確認してください。"
    ) from last_exc


def _resolve_login_form_locators_prudential_heuristic(
    page,
    host_selector: str,
    timeout_ms: int,
):
    """
    プルデンシャル契約者サイト想定: Lightning の動的 id に依存せず、ログイン枠内で解決する。

    - ユーザー名: input[id^="input-"]（ログイン ID 欄の命名パターン）
    - パスワード: input[type="password"]（先頭の1つ）
    - 送信: ロール button・名前「ログイン」、ダメなら lightning-button 内 button で文言一致
    """
    host_sel = (host_selector or "").strip() or "c-mypg-login-info-input-detail"
    budget_ms = max(int(timeout_ms), 60_000)
    deadline = time.monotonic() + budget_ms / 1000.0
    main_probe = int(os.environ.get("PRUDENTIAL_LOGIN_MAIN_PROBE_MS", "45000") or "45000")
    main_probe = max(5000, min(main_probe, 180_000))
    iframe_probe = int(os.environ.get("PRUDENTIAL_LOGIN_IFRAME_PROBE_MS", "0") or "0")
    if iframe_probe <= 0:
        iframe_probe = int(os.environ.get("PRUDENTIAL_LOGIN_FRAME_PROBE_MS", "6000") or "6000")
    iframe_probe = max(2000, min(iframe_probe, 30_000))
    last_exc: BaseException | None = None
    frames = _login_probe_frames(page)

    for i, fr in enumerate(frames):
        remaining_ms = int(max(500, (deadline - time.monotonic()) * 1000))
        if remaining_ms < 2000:
            break
        is_main = i == 0
        u_cap = min(remaining_ms, main_probe) if is_main else min(remaining_ms, iframe_probe)
        try:
            host = fr.locator(host_sel).first
            host.wait_for(state="visible", timeout=min(u_cap, 35_000))
            root = host
            u = root.locator('input[id^="input-"]').first
            u.wait_for(state="visible", timeout=min(u_cap, 25_000))
            rem2 = int(max(500, (deadline - time.monotonic()) * 1000))
            p = root.locator('input[type="password"]').first
            try:
                p.wait_for(state="visible", timeout=min(rem2, 60_000))
            except Exception:
                p = root.locator('input[id^="registerPassword"]').first
                p.wait_for(state="attached", timeout=min(rem2, 45_000))
            rem3 = int(max(500, (deadline - time.monotonic()) * 1000))
            s = None
            try:
                s = root.get_by_role("button", name="ログイン")
                s.wait_for(state="visible", timeout=min(rem3, 20_000))
            except Exception:
                s = root.locator("lightning-button button, form button.slds-button").filter(
                    has_text=re.compile(r"^\s*ログイン\s*$")
                ).first
                s.wait_for(state="visible", timeout=min(rem3, 25_000))
            return u, p, s
        except Exception as e:
            last_exc = e
            continue

    raise RuntimeError(
        "ヒューリスティックでもログイン画面の入力欄を解決できませんでした（"
        f"HOST={host_sel!r}）。PRUDENTIAL_LOGIN_FORM_HOST_SELECTOR を確認するか、"
        "固定セレクタ（PRUDENTIAL_USERNAME_SELECTOR 等）を DevTools で更新してください。"
    ) from last_exc


def _frames_in_order(page) -> list:
    seen: set[int] = set()
    out: list = []
    for fr in getattr(page, "frames", []) or []:
        fid = id(fr)
        if fid not in seen:
            seen.add(fid)
            out.append(fr)
    return out


def _click_by_selector_or_text_in_frame(
    frame,
    *,
    selector: str,
    text: str,
    timeout_ms: int,
) -> bool:
    if selector:
        try:
            loc = frame.locator(selector).first
            loc.wait_for(state="visible", timeout=min(25_000, max(3000, timeout_ms)))
            try:
                loc.scroll_into_view_if_needed(timeout=min(8000, timeout_ms))
            except Exception:
                pass
            try:
                loc.click(timeout=timeout_ms)
            except Exception:
                loc.click(timeout=timeout_ms, force=True)
            return True
        except Exception:
            pass
    if text:
        for pat in (
            re.compile(re.escape(text)),
            re.compile(text.replace(" ", r"\s*")),
        ):
            try:
                for role in ("link", "button", "menuitem", "tab"):
                    loc = frame.get_by_role(role, name=pat)
                    if loc.count() > 0:
                        loc.first.click(timeout=timeout_ms)
                        return True
            except Exception:
                continue
        for q in (
            f"a:has-text('{text}')",
            f"button:has-text('{text}')",
            f"[role='button']:has-text('{text}')",
            f"text={text}",
        ):
            try:
                loc = frame.locator(q)
                if loc.count() > 0 and loc.first.is_visible():
                    loc.first.click(timeout=timeout_ms)
                    return True
            except Exception:
                continue
    return False


def _click_by_selector_or_text_any_frame(
    page,
    *,
    selector: str,
    text: str,
    timeout_ms: int,
) -> bool:
    for fr in _login_probe_frames(page):
        if _click_by_selector_or_text_in_frame(
            fr, selector=selector, text=text, timeout_ms=timeout_ms
        ):
            return True
    return False


def _collect_prudential_accounts() -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for i in range(1, 11):
        u = os.environ.get(f"PRUDENTIAL_USERNAME_{i}", "").strip()
        p = os.environ.get(f"PRUDENTIAL_PASSWORD_{i}", "").strip()
        if i == 1:
            if not u:
                u = os.environ.get("PRUDENTIAL_USERNAME", "").strip()
            if not p:
                p = os.environ.get("PRUDENTIAL_PASSWORD", "").strip()
        if not u and not p:
            if i == 1:
                raise RuntimeError(
                    "PRUDENTIAL_USERNAME_1 / PRUDENTIAL_PASSWORD_1（または "
                    "PRUDENTIAL_USERNAME / PRUDENTIAL_PASSWORD）を設定してください。"
                )
            break
        if not u or not p:
            raise RuntimeError(
                f"PRUDENTIAL_USERNAME_{i} と PRUDENTIAL_PASSWORD_{i} は両方必要です。"
            )
        pairs.append((u, p))
    return pairs


def _otp_env_for_account(account_1based: int) -> str:
    if account_1based <= 1:
        return os.environ.get("PRUDENTIAL_OTP_CODE", "").strip()
    key = f"PRUDENTIAL_OTP_CODE_{account_1based}"
    return os.environ.get(key, "").strip() or os.environ.get("PRUDENTIAL_OTP_CODE", "").strip()


def _resolve_otp_code(
    otp_code_from_env: str,
    otp_code_override: str | None,
    *,
    account_index: int,
) -> str:
    code = (otp_code_override or otp_code_from_env or "").strip()
    if code:
        return code
    if not sys.stdin.isatty():
        return ""
    suffix = f"（アカウント{account_index}）" if account_index > 1 else ""
    return input(
        f"メール等に届いたプルデンシャル生命の確認番号を入力してください{suffix}。"
        "（Cursor でチャットに番号を送った場合は、その番号をここに貼り付けても構いません）\n"
        "確認番号: "
    ).strip()


def _reset_session_before_relogin(
    page,
    context,
    *,
    login_url: str,
    logout_url: str,
    logout_selector: str,
    logout_text: str,
    timeout_ms: int,
) -> None:
    if logout_selector:
        try:
            loc = page.locator(logout_selector)
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click()
                _wait_page_ready(page, timeout_ms)
        except Exception:
            pass
    elif logout_text:
        _click_by_selector_or_text_any_frame(
            page, selector="", text=logout_text, timeout_ms=timeout_ms
        )
    if logout_url:
        try:
            page.goto(logout_url, wait_until="domcontentloaded")
            _wait_page_ready(page, timeout_ms)
        except Exception:
            pass
    try:
        context.clear_cookies()
    except Exception:
        pass
    page.goto(login_url, wait_until="domcontentloaded")
    _wait_login_shell_ready(page, timeout_ms)


def _has_manual_prudential_nav_config() -> bool:
    """TARGET / AFTER_LOGIN / NAV_STEP1 のいずれかがあれば手動ナビのみ。"""
    if os.environ.get("PRUDENTIAL_TARGET_URL", "").strip():
        return True
    if os.environ.get("PRUDENTIAL_AFTER_LOGIN_CLICK_SELECTOR", "").strip():
        return True
    if os.environ.get("PRUDENTIAL_AFTER_LOGIN_CLICK_TEXT", "").strip():
        return True
    s1 = os.environ.get("PRUDENTIAL_NAV_STEP1_SELECTOR", "").strip()
    t1 = os.environ.get("PRUDENTIAL_NAV_STEP1_TEXT", "").strip()
    return bool(s1 or t1)


def _prudential_already_on_contract_list(page) -> bool:
    """OTP 直後などでマイページトップを経由せず契約一覧 URL にいる場合がある。"""
    try:
        title = (page.title() or "").replace(" ", "")
        url = (page.url or "").lower()
        return "契約一覧" in title or "contractlist" in url or "contract-list" in url
    except Exception:
        return False


def _click_contract_content_mypage(page, timeout_ms: int) -> bool:
    """トップメニュー等の「契約内容」をクリック。"""
    sel = os.environ.get("PRUDENTIAL_NAV_CONTRACT_MENU_SELECTOR", "").strip()
    if sel and _click_by_selector_or_text_any_frame(
        page, selector=sel, text="", timeout_ms=timeout_ms
    ):
        return True
    menu_text = os.environ.get("PRUDENTIAL_NAV_CONTRACT_MENU_TEXT", "契約内容").strip() or "契約内容"
    return _click_by_selector_or_text_any_frame(
        page, selector="", text=menu_text, timeout_ms=timeout_ms
    )


def _click_first_contract_title_mypage(page, timeout_ms: int) -> bool:
    """契約一覧から1件目（または環境で指定）の契約タイトルリンクをクリック。"""
    try:
        page.locator("c-mypg-view").first.wait_for(state="attached", timeout=min(20000, timeout_ms))
        page.wait_for_timeout(1500)
    except Exception:
        pass
    sel = os.environ.get("PRUDENTIAL_CONTRACT_LINK_SELECTOR", "").strip()
    if sel:
        try:
            for fr in _frames_in_order(page):
                loc = fr.locator(sel)
                if loc.count() > 0:
                    loc.first.scroll_into_view_if_needed(timeout=min(8000, timeout_ms))
                    try:
                        loc.first.click(timeout=timeout_ms)
                    except Exception:
                        loc.first.click(timeout=timeout_ms, force=True)

                    # 契約詳細へ遷移するまで待つ（遷移せず一覧のままのことがある）
                    try:
                        page.wait_for_function(
                            """() => {
  const t = (document.title || "");
  if (t.includes("契約内容詳細")) return true;
  const hasCash = !!document.querySelector("c-mypg-contr-cont-inq-cash-val-detail");
  const hasBasic = !!document.querySelector("c-mypg-contr-cont-inq-basic-detail");
  return hasCash || hasBasic;
}""",
                            timeout=min(45_000, max(12_000, timeout_ms)),
                        )
                        return True
                    except Exception:
                        # もう一度だけ強制クリックして待つ
                        try:
                            loc.first.click(timeout=timeout_ms, force=True)
                        except Exception:
                            pass
                        try:
                            page.wait_for_function(
                                """() => {
  const t = (document.title || "");
  if (t.includes("契約内容詳細")) return true;
  const hasCash = !!document.querySelector("c-mypg-contr-cont-inq-cash-val-detail");
  const hasBasic = !!document.querySelector("c-mypg-contr-cont-inq-basic-detail");
  return hasCash || hasBasic;
}""",
                                timeout=min(45_000, max(12_000, timeout_ms)),
                            )
                            return True
                        except Exception:
                            return True  # クリック自体はできた扱いで、後段のタブで失敗HTMLを残す
        except Exception:
            pass

    sub = os.environ.get("PRUDENTIAL_CONTRACT_LINK_TEXT", "").strip()
    if sub:
        try:
            pat = re.compile(re.escape(sub))
            for fr in _frames_in_order(page):
                loc = fr.get_by_role("link", name=pat)
                if loc.count() > 0:
                    loc.first.click(timeout=timeout_ms)
                    return True
                loc2 = fr.locator("a").filter(has_text=sub)
                if loc2.count() > 0:
                    loc2.first.click(timeout=timeout_ms)
                    return True
        except Exception:
            pass

    for table_sel in (
        "c-mypg-view table tbody tr td a",
        "c-mypg-view main table a",
        "table.m-table tbody tr a",
    ):
        try:
            loc = page.locator(table_sel)
            if loc.count() > 0:
                loc.first.wait_for(state="visible", timeout=12000)
                loc.first.click(timeout=timeout_ms)
                return True
        except Exception:
            continue

    clicked = page.evaluate(
        r"""
() => {
  const bad = (t) => {
    const n = (t || "").replace(/\s/g, "");
    return /契約内容|ログアウト|ログイン|マイページトップ|お知らせ|ヘルプ|初めて|利用登録|よくある/.test(n);
  };
  const good = (t) => {
    const n = (t || "").replace(/\s/g, "");
    return n.length >= 6 && /保険|年金|終身|一時払|変額|養老|定期/.test(n);
  };
  const links = Array.from(document.querySelectorAll('a[href]'));
  const scored = [];
  for (const a of links) {
    const t = (a.innerText || "").trim();
    if (!t || bad(t)) continue;
    const st = window.getComputedStyle(a);
    if (st.display === "none" || st.visibility === "hidden") continue;
    const r = a.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    let score = t.length;
    if (good(t)) score += 100;
    scored.push({ a, score, t });
  }
  scored.sort((x, y) => y.score - x.score);
  const pick = scored[0];
  if (!pick) return false;
  pick.a.scrollIntoView({ block: "center", inline: "center" });
  pick.a.click();
  return true;
}
"""
    )
    return bool(clicked)


def _click_surrender_value_tab_mypage(page, timeout_ms: int) -> bool:
    """詳細画面の「解約返戻金」タブをクリック。"""
    tab_text = (
        os.environ.get("PRUDENTIAL_SURRENDER_TAB_TEXT", "解約返戻金").strip() or "解約返戻金"
    )
    pat = re.compile(re.escape(tab_text))
    pat_loose = re.compile(r"解約\s*返戻金")

    def _tab_is_active() -> bool:
        # LWC のタブは class で active になることが多い
        try:
            active = page.locator("a.m-tab-btn.m-tab-btn-active").filter(has_text=pat)
            if active.count() > 0 and active.first.is_visible(timeout=1200):
                return True
        except Exception:
            pass
        # 参考値ブロックが見えていれば解約返戻金側とみなす
        try:
            key = page.locator("text=/解約した場合のお支払い予定額|お支払い予定額（参考値）|お支払い予定額/")
            if key.count() > 0 and key.first.is_visible(timeout=1200):
                return True
        except Exception:
            pass
        return False

    if _tab_is_active():
        return True

    # タブ一覧が描画されるまで少し待つ（SPA のロード中にクリックしても反応しないことがある）
    try:
        page.locator("a.m-tab-btn, button.m-tab-btn").first.wait_for(
            state="attached",
            timeout=min(25_000, max(5000, timeout_ms // 2)),
        )
    except Exception:
        pass

    debug_tab = _env_yesno_or_default("PRUDENTIAL_DEBUG_SURRENDER_TAB", default=False)
    if debug_tab:
        try:
            DEFAULT_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            dbg = DEFAULT_DEBUG_DIR / "prudential_surrender_tab_debug.html"
            dbg.write_text(page.content(), encoding="utf-8")
            print(f"🐞 [tab] クリック失敗切り分け用HTMLを保存: {dbg.name}", file=sys.stderr)
        except Exception:
            pass
        try:
            n_all = page.locator("a.m-tab-btn, button.m-tab-btn").count()
            print(f"🐞 [tab] a.m-tab-btn total: {n_all}", file=sys.stderr)
        except Exception:
            pass

    # まずは「ページ上に見えているタブ一覧」を直接走査して、文言一致する index をクリックする
    try:
        tabs = page.locator("a.m-tab-btn, button.m-tab-btn")
        tab_texts = [t.strip() for t in tabs.all_inner_texts()[:20]]
        if debug_tab:
            print(f"🐞 [tab] tab_texts={tab_texts!r}", file=sys.stderr)
        hit_idx = None
        for i, t in enumerate(tab_texts):
            if pat_loose.search(t):
                hit_idx = i
                break
        if hit_idx is not None:
            tgt = tabs.nth(hit_idx)
            try:
                tgt.scroll_into_view_if_needed(timeout=min(8000, timeout_ms))
            except Exception:
                pass
            for _ in range(3):
                try:
                    tgt.click(timeout=timeout_ms)
                except Exception:
                    tgt.click(timeout=timeout_ms, force=True)
                try:
                    page.wait_for_timeout(1200)
                except Exception:
                    pass
                if _tab_is_active():
                    return True
    except Exception:
        pass

    sel = os.environ.get("PRUDENTIAL_SURRENDER_TAB_SELECTOR", "").strip()
    if sel:
        try:
            for _ in range(3):
                # クリック対象が他の LWC にある場合に備えて、全体からも探す（frame を跨ぐ locator が効かないケース対策）
                try:
                    loc0 = page.locator(sel)
                    if loc0.count() > 0:
                        tgt0 = loc0.first
                        try:
                            tgt0.scroll_into_view_if_needed(timeout=min(8000, timeout_ms))
                        except Exception:
                            pass
                        try:
                            tgt0.click(timeout=timeout_ms)
                        except Exception:
                            tgt0.click(timeout=timeout_ms, force=True)
                        try:
                            page.wait_for_timeout(1200)
                        except Exception:
                            pass
                        if _tab_is_active():
                            return True
                except Exception:
                    pass
                for fr in _frames_in_order(page):
                    loc = fr.locator(sel)
                    if loc.count() <= 0:
                        continue
                    tgt = loc.first
                    try:
                        tgt.wait_for(
                            state="visible",
                            timeout=min(25_000, max(3000, timeout_ms)),
                        )
                    except Exception:
                        pass
                    try:
                        tgt.scroll_into_view_if_needed(timeout=min(8000, timeout_ms))
                    except Exception:
                        pass
                    try:
                        tgt.click(timeout=timeout_ms)
                    except Exception:
                        tgt.click(timeout=timeout_ms, force=True)
                    # SPA のタブはクリック後に少し待たないと active 判定が反映されないことがある
                    try:
                        page.wait_for_timeout(1200)
                    except Exception:
                        pass
                    if _tab_is_active():
                        return True
        except Exception:
            pass

    for fr in _frames_in_order(page):
        for role in ("tab", "link", "button"):
            try:
                loc = fr.get_by_role(role, name=pat)
                if loc.count() > 0:
                    for _ in range(2):
                        try:
                            loc.first.click(timeout=timeout_ms)
                        except Exception:
                            loc.first.click(timeout=timeout_ms, force=True)
                        try:
                            page.wait_for_timeout(1200)
                        except Exception:
                            pass
                        if _tab_is_active():
                            return True
            except Exception:
                continue
        try:
            loc = fr.locator(
                "[role='tab'], a, button, span"
            ).filter(has_text=pat_loose)
            if loc.count() > 0:
                for _ in range(2):
                    try:
                        loc.first.click(timeout=timeout_ms)
                    except Exception:
                        loc.first.click(timeout=timeout_ms, force=True)
                    try:
                        page.wait_for_timeout(1200)
                    except Exception:
                        pass
                    if _tab_is_active():
                        return True
        except Exception:
            pass

    # LWC 契約詳細: タブは <a class="m-tab-btn"> で Shadow 内のため role=link が付かず上記が失敗することがある
    host_sel = (
        os.environ.get("PRUDENTIAL_SURRENDER_TAB_HOST_SELECTOR", "").strip()
        or "c-mypg-contr-cont-inq-basic-detail"
    )
    for fr in _frames_in_order(page):
        try:
            host = fr.locator(host_sel)
            if debug_tab:
                try:
                    print(
                        f"🐞 [tab] host_sel={host_sel!r} count={host.count()}",
                        file=sys.stderr,
                    )
                except Exception:
                    pass
            if host.count() <= 0:
                continue
            inner = host.locator("a.m-tab-btn, button.m-tab-btn").filter(has_text=pat_loose)
            if debug_tab:
                try:
                    print(
                        f"🐞 [tab] inner (m-tab-btn + has_text) count={inner.count()}",
                        file=sys.stderr,
                    )
                except Exception:
                    pass
            if inner.count() <= 0:
                continue
            tgt = inner.first
            try:
                tgt.wait_for(
                    state="visible",
                    timeout=min(25_000, max(3000, timeout_ms)),
                )
            except Exception:
                pass
            try:
                tgt.scroll_into_view_if_needed(timeout=min(8000, timeout_ms))
            except Exception:
                pass
            for _ in range(3):
                try:
                    tgt.click(timeout=timeout_ms)
                except Exception:
                    tgt.click(timeout=timeout_ms, force=True)
                try:
                    page.wait_for_timeout(1200)
                except Exception:
                    pass
                if _tab_is_active():
                    return True
        except Exception:
            continue
    return False


def _prudential_default_nav_mypage(page, timeout_ms: int) -> None:
    """ログイン直後〜解約返戻金タブまで（マイページ標準導線）。"""
    if _prudential_already_on_contract_list(page):
        print(
            "↪ すでに契約一覧画面のため、「契約内容」メニューのクリックをスキップします。",
            file=sys.stderr,
        )
        _wait_page_ready(page, timeout_ms)
    elif not _click_contract_content_mypage(page, timeout_ms):
        raise RuntimeError(
            "「契約内容」をクリックできませんでした（ログイン〜マイページ表示後の最初のナビ）。"
            "セレクタ／TEXT は設定済みでも、トップの描画待ち不足・別フレーム・オーバーレイで失敗することがあります。"
            " PRUDENTIAL_POST_LOGIN_WAIT_MS を大きくする、"
            "PRUDENTIAL_NAV_CONTRACT_MENU_SELECTOR を `h2.l-section-top-panel-tit` や親の `a` に変えて試す、"
            "ヘッドレスを外して要素が見えるか確認してください。"
        )
    else:
        _wait_page_ready(page, timeout_ms)
    try:
        page.wait_for_timeout(800)
    except Exception:
        pass

    if _env_yesno_or_default("PRUDENTIAL_PAUSE_AT_CONTRACT_LIST", default=False):
        DEFAULT_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        html_path = DEFAULT_DEBUG_DIR / "prudential_contract_list_inspect.html"
        png_path = DEFAULT_DEBUG_DIR / "prudential_contract_list_inspect.png"
        try:
            html_path.write_text(page.content(), encoding="utf-8")
            page.screenshot(path=str(png_path), full_page=True)
        except Exception:
            pass
        print(
            f"⏸ 契約一覧に到達しました。契約リンククリック前で停止します。保存: {html_path.name} / {png_path.name}",
            file=sys.stderr,
        )
        try:
            page.pause()
        except Exception:
            pass
        raise PrudentialPausedAtContractList(
            "契約一覧で停止しました（PRUDENTIAL_PAUSE_AT_CONTRACT_LIST）。"
            " PRUDENTIAL_CONTRACT_LINK_SELECTOR / PRUDENTIAL_CONTRACT_LINK_TEXT を設定して再実行してください。"
        )

    if not _click_first_contract_title_mypage(page, timeout_ms):
        raise RuntimeError(
            "契約タイトル（一覧のリンク）をクリックできませんでした。"
            "PRUDENTIAL_CONTRACT_LINK_SELECTOR または PRUDENTIAL_CONTRACT_LINK_TEXT（タイトルの一部）を設定してください。"
        )
    _wait_page_ready(page, timeout_ms)
    # 契約詳細のタブUIが描画されるまで待つ（描画前にクリックすると失敗しやすい）
    try:
        page.locator("a.m-tab-btn, button.m-tab-btn").first.wait_for(
            state="visible",
            timeout=min(45_000, max(12_000, timeout_ms)),
        )
    except Exception:
        pass
    try:
        page.wait_for_timeout(800)
    except Exception:
        pass

    if not _click_surrender_value_tab_mypage(page, timeout_ms):
        # タブが取れないケースがあるため、ヘッダー/メニュー側の「解約返戻金一覧」も試す（遷移できれば抽出は可能）
        if not _click_by_selector_or_text_any_frame(
            page,
            selector="",
            text=os.environ.get("PRUDENTIAL_SURRENDER_MENU_TEXT", "解約返戻金一覧").strip()
            or "解約返戻金一覧",
            timeout_ms=timeout_ms,
        ):
            raise RuntimeError(
                "「解約返戻金」タブをクリックできませんでした。"
                "PRUDENTIAL_SURRENDER_TAB_SELECTOR を設定するか、画面を確認してください。"
            )
    _wait_page_ready(page, timeout_ms)


def _extract_prudential_reference_payment(page) -> tuple[int | None, str]:
    """
    「解約した場合のお支払い予定額（参考値）」付近の金額（プルデンシャル想定DOM）。
    """
    raw = page.evaluate(
        r"""
() => {
  const norm = (s) => (s || "").replace(/\s/g, "").replace(/\u3000/g, "");
  const wantRefs = [
    "解約した場合のお支払い予定額",
    "お支払い予定額（参考値）",
    "お支払い予定額",
  ];
  const candidates = Array.from(
    document.querySelectorAll("p, h1, h2, h3, h4, span, div, dt, legend, label")
  );
  for (const el of candidates) {
    const raw = (el.innerText || "").replace(/\s+/g, " ").trim();
    const n = norm(raw);
    let hit = false;
    for (const w of wantRefs) {
      if (n.includes(norm(w))) { hit = true; break; }
    }
    if (!hit) continue;
    let root = el.closest("section, article, [class*='l-'], [class*='block'], div") || el.parentElement;
    for (let depth = 0; depth < 8 && root; depth++) {
      const block = (root.innerText || "").replace(/\s+/g, " ");
      const m = block.match(/([0-9][0-9,]*)\s*円/);
      if (m && m[1]) {
        const num = m[1].replace(/,/g, "");
        if (num.length >= 1) return m[0].trim();
      }
      root = root.parentElement;
    }
  }
  return "";
}
"""
    )
    return _parse_first_jpy((raw or "").strip())


def _extract_max_yen_by_visible_text(
    page,
    *,
    root_selector: str = "",
    min_value: int = 1000,
    max_candidates: int = 200,
) -> tuple[int | None, str]:
    """
    Playwright の text engine を使って「xxx円」を列挙し、最大値を返す。
    Shadow DOM をまたいで拾えるため、page.evaluate(querySelectorAll) より堅牢。
    """
    try:
        root = page.locator(root_selector) if root_selector else page.locator("body")
        loc = root.locator(r"text=/[0-9][0-9,]*\\s*円/")
        # 取りすぎ防止（内部的には逐次評価だが、all_inner_texts が重くなるため制限）
        texts = loc.all_inner_texts()[:max_candidates]
    except Exception:
        return None, ""

    best_val: int | None = None
    best_txt = ""
    for t in texts:
        v, vt = _parse_first_jpy((t or "").strip())
        if v is None:
            continue
        if v < min_value:
            continue
        if best_val is None or v > best_val:
            best_val = v
            best_txt = vt or f"{v:,}円"
    return best_val, best_txt


def _extract_prudential_surrender_by_section_text(page) -> tuple[int | None, str]:
    """
    「解約した場合のお支払い予定額（参考値）」等のブロック内で金額を拾う（Shadow 対応）。
    """
    try:
        # まずは「お支払い予定額」ブロックを優先
        key = re.compile(r"解約した場合のお支払い予定額|お支払い予定額（参考値）|お支払い予定額")
        sec = page.locator("section, article, div").filter(has_text=key).first
        if sec.count() > 0:
            try:
                loc = sec.locator(r"text=/[0-9][0-9,]*\\s*円/")  # shadow 対応
                texts = loc.all_inner_texts()[:200]
            except Exception:
                texts = []
            best_val: int | None = None
            best_txt = ""
            for t in texts:
                v, vt = _parse_first_jpy((t or "").strip())
                if v is None or v < 1000:
                    continue
                if best_val is None or v > best_val:
                    best_val = v
                    best_txt = vt or f"{v:,}円"
            if best_val is not None:
                return best_val, best_txt
    except Exception:
        pass

    # 契約詳細 LWC のホスト（解約返戻金タブ配下）に絞って拾う
    v2, vt2 = _extract_max_yen_by_visible_text(
        page,
        root_selector="c-mypg-contr-cont-inq-basic-detail",
        min_value=1000,
    )
    return v2, vt2


def _page_looks_like_prudential_otp_challenge(page) -> bool:
    """ログイン直後の「確認番号」入力画面か（タイトル・本文の簡易判定）。"""
    try:
        title = page.title() or ""
    except Exception:
        title = ""
    if any(
        x in title
        for x in ("確認番号", "ワンタイムパスワード", "認証コード", "確認コード")
    ):
        return True
    try:
        body = (page.inner_text("body") or "")[:2500]
    except Exception:
        body = ""
    if "確認番号" in body and ("入力" in body or "お送り" in body or "SMS" in body):
        return True
    return False


def _prudential_otp_input_visible(page, otp_selector: str) -> bool:
    """確認番号用 input が表示されているか（ページ種別の判定用）。"""
    try:
        if otp_selector and page.locator(otp_selector).count() > 0:
            if page.locator(otp_selector).first.is_visible(timeout=1200):
                return True
    except Exception:
        pass
    try:
        loc = page.locator('input[id^="confirmNumber"]').first
        if loc.count() > 0 and loc.is_visible(timeout=1200):
            return True
    except Exception:
        pass
    return False


def _prudential_looks_like_login_form_again(page) -> bool:
    """
    ログイン送信後に、再びログイン ID + パスワードが目立つ画面に戻ったか（簡易）。
    確認番号画面が消えてログインに戻る事象の検知用。
    """
    try:
        if not _prudential_guest_shell_visible(page):
            return False
    except Exception:
        return False
    try:
        pw = page.locator('input[type="password"]').first
        if pw.count() == 0 or not pw.is_visible(timeout=1500):
            return False
    except Exception:
        return False
    try:
        id_like = page.locator('input[id^="input-"]').first
        if id_like.count() > 0 and id_like.is_visible(timeout=800):
            return True
    except Exception:
        pass
    return False


def _wait_prudential_post_login_settle(
    page,
    *,
    otp_selector: str,
    timeout_ms: int,
) -> tuple[str, str]:
    """
    ログインクリック直後: LWC が **確認番号画面** か **マイページ** に落ち着くまで待つ。

    固定の PRUDENTIAL_POST_LOGIN_ANIMATION_MS だけ sleep すると、
    確認番号 UI が一瞬表示されたあと SPA がログイン画面に戻る場合に、
    その後の処理が「どのページか分からない」まま進んでしまう。

    - マイページ（c-mypg-top-detail）が先に出たら確認番号不要として終了。
    - 確認番号欄が **一定時間連続で見える** まで待ってから otp とする（チラ見えを除外）。
    - ログイン画面に戻ったと判断したら login_reset。
    """
    max_ms = _env_int_nonneg("PRUDENTIAL_POST_LOGIN_SETTLE_MS", 90000)
    poll_ms = max(200, _env_int_nonneg("PRUDENTIAL_POST_LOGIN_SETTLE_POLL_MS", 400))
    stable_ms = max(500, _env_int_nonneg("PRUDENTIAL_OTP_STEP_STABLE_MS", 2000))
    deadline = time.monotonic() + max_ms / 1000.0
    first_otp_mono: float | None = None
    login_reset_streak = 0

    while time.monotonic() < deadline:
        try:
            if _prudential_authenticated_top_ready(page, timeout_ms=2500):
                return "mypage", "マイページ（認証後トップ）を検出しました。"
        except Exception:
            pass

        otp_ok = _prudential_otp_input_visible(page, otp_selector) or _page_looks_like_prudential_otp_challenge(
            page
        )
        now = time.monotonic()

        if otp_ok:
            if first_otp_mono is None:
                first_otp_mono = now
                print(
                    "⏳ 確認番号まわりの画面を検出しました。表示が安定するまで待ちます…",
                    file=sys.stderr,
                )
            elif (now - first_otp_mono) * 1000.0 >= stable_ms:
                return "otp", "確認番号ステップが安定して表示されています。"
        else:
            first_otp_mono = None

        if _prudential_looks_like_login_form_again(page) and not otp_ok:
            login_reset_streak += 1
            if login_reset_streak >= max(3, int(5000 / poll_ms)):
                return (
                    "login_reset",
                    "ログイン画面（ID・パスワード）に戻ったように見えます。"
                    "確認番号画面が消えた・セッションが切れた可能性があります。",
                )
        else:
            login_reset_streak = 0

        try:
            page.wait_for_timeout(poll_ms)
        except Exception:
            time.sleep(poll_ms / 1000.0)

    return (
        "timeout",
        f"{max_ms} ms 以内にマイページまたは安定した確認番号画面を確認できませんでした。",
    )


def _prudential_try_check_trusted_device(page, timeout_ms: int) -> bool:
    """確認番号画面で「信頼できる端末として登録する」等のチェックをオンにする。"""
    if not _env_yesno_or_default("PRUDENTIAL_TRUST_DEVICE_CHECK", default=True):
        return False
    cap = min(15000, max(3000, timeout_ms))
    pat = re.compile(r"信頼できる端末")
    for fr in _login_probe_frames(page):
        try:
            loc = fr.get_by_role("checkbox", name=pat)
            if loc.count() > 0:
                box = loc.first
                box.wait_for(state="visible", timeout=min(8000, cap))
                if not box.is_checked():
                    box.check(timeout=cap)
                print(
                    "✓ 信頼できる端末として（に）登録するチェックをオンにしました。",
                    file=sys.stderr,
                )
                return True
        except Exception:
            pass
    try:
        clicked = page.evaluate(
            r"""
() => {
  const want = /信頼できる端末/;
  const roots = Array.from(
    document.querySelectorAll("main, section, form, c-mypg-guest-view, [class*='l-login']")
  );
  for (const root of roots) {
    const cbs = root.querySelectorAll('input[type="checkbox"]');
    for (const cb of cbs) {
      let lab = "";
      if (cb.labels && cb.labels.length) lab = (cb.labels[0].innerText || "").trim();
      if (!lab) lab = (cb.getAttribute("aria-label") || "").trim();
      if (want.test(lab) && !cb.checked) {
        cb.click();
        return true;
      }
    }
  }
  const all = Array.from(document.querySelectorAll('input[type="checkbox"]'));
  for (const cb of all) {
    let lab = "";
    if (cb.labels && cb.labels.length) lab = (cb.labels[0].innerText || "").trim();
    if (!lab) lab = (cb.getAttribute("aria-label") || "").trim();
    if (want.test(lab) && !cb.checked) {
      cb.click();
      return true;
    }
  }
  return false;
}
"""
        )
        if clicked:
            print(
                "✓ 信頼できる端末として（に）登録するチェックをオンにしました（DOM フォールバック）。",
                file=sys.stderr,
            )
            return True
    except Exception:
        pass
    return False


def _fill_otp_field_lightning_compat(locator, code: str, timeout_ms: int) -> bool:
    """
    Lightning / LWC の確認番号欄は Playwright の fill だけでは LWC 内部状態が更新されず、
    aria-invalid のまま・「必ず入力」のエラーが残ることがある。
    input/change イベントと press_sequentially で補う。
    """
    if not (code or "").strip():
        return False
    t = min(12_000, max(3000, timeout_ms))
    v_lit = json.dumps(str(code).strip(), ensure_ascii=False)
    patch_fn = (
        "(el) => {\n"
        "  const v = "
        + v_lit
        + ";\n"
        "  try { el.focus(); } catch (e) {}\n"
        "  const cur = String(el.value || '').replace(/\\s/g, '');\n"
        "  const want = String(v || '').replace(/\\s/g, '');\n"
        "  if (cur !== want) {\n"
        "    try {\n"
        "      el.value = v;\n"
        "      el.dispatchEvent(new Event('input', { bubbles: true }));\n"
        "      el.dispatchEvent(new Event('change', { bubbles: true }));\n"
        "      try {\n"
        "        el.dispatchEvent(new InputEvent('input', { bubbles: true, data: v, "
        "inputType: 'insertText' }));\n"
        "      } catch (e2) {}\n"
        "    } catch (e3) {}\n"
        "  }\n"
        "  return String(el.value || '').replace(/\\s/g, '') === want;\n"
        "}"
    )
    try:
        locator.wait_for(state="visible", timeout=t)
    except Exception:
        return False
    try:
        locator.click(timeout=t)
        locator.fill("", timeout=t)
        locator.fill(str(code).strip(), timeout=t)
    except Exception:
        pass
    try:
        if locator.evaluate(patch_fn):
            try:
                locator.evaluate(
                    "(el) => { try { el.dispatchEvent(new FocusEvent('blur', { bubbles: true })); } catch (e) {} }"
                )
            except Exception:
                pass
            return True
    except Exception:
        pass
    try:
        locator.press_sequentially(str(code).strip(), delay=50, timeout=t)
        ok = bool(locator.evaluate(patch_fn))
        if ok:
            try:
                locator.evaluate(
                    "(el) => { try { el.dispatchEvent(new FocusEvent('blur', { bubbles: true })); } catch (e) {} }"
                )
            except Exception:
                pass
        return ok
    except Exception:
        pass
    try:
        return bool(locator.evaluate(patch_fn))
    except Exception:
        return False


def _is_probable_prudential_login_id_input(locator) -> bool:
    """
    ログインID欄と確認番号欄の誤認識を防ぐ。
    プルデンシャルではログイン ID が input[id^=\"input-\"]、確認番号が confirmNumber 系のことが多い。
    """
    try:
        return bool(
            locator.evaluate(
                """
(el) => {
  if (!el || el.tagName !== 'INPUT') return false;
  const id = String(el.id || '');
  const name = String(el.name || '').toLowerCase();
  const ac = String(el.getAttribute('autocomplete') || '').toLowerCase();
  const ph = String(el.getAttribute('placeholder') || '');
  const al = String(el.getAttribute('aria-label') || '');
  const type = String(el.type || '').toLowerCase();
  // 確認番号・OTP 専用と分かるものはログイン ID とみなさない
  if (/confirm|otp|番号|認証/i.test(id)) return false;
  if (/confirm|otp/i.test(name)) return false;
  if (ac === 'one-time-code') return false;
  if (/確認番号|ワンタイム|認証番号/i.test(ph + al)) return false;
  // ログイン ID 列（動的 id が input- で始まるのが一般的）
  if (/^input-/i.test(id) && !/confirm/i.test(id)) return true;
  if (ac === 'username' || ac === 'email') return true;
  if (/user|login|contract|mail|email/i.test(name) && !/confirm|otp/i.test(name)) return true;
  if (/ログイン\\s*id|契約者番号|ユーザ\\s*id/i.test(ph + al) && !/確認/.test(ph + al)) return true;
  let p = el;
  for (let i = 0; i < 8 && p; i++, p = p.parentElement) {
    const t = (p.innerText || '').replace(/\\s+/g, ' ').slice(0, 400);
    if (/ログイン\\s*id|契約者番号/.test(t) && !/確認番号/.test(t)) return true;
  }
  return false;
}
"""
            )
        )
    except Exception:
        return False


def _try_press_enter_on_otp_field(page, otp_selector: str, timeout_ms: int) -> None:
    """確認番号欄で Enter（フォーム送信の補助）。失敗しても無視。"""
    t = min(12_000, max(3000, timeout_ms))
    try:
        if otp_selector and page.locator(otp_selector).count() > 0:
            page.locator(otp_selector).first.press("Enter", timeout=t)
            return
    except Exception:
        pass
    try:
        loc = page.locator('input[id^="confirmNumber"]').first
        if loc.is_visible(timeout=3000):
            loc.press("Enter", timeout=t)
    except Exception:
        pass


def _fill_prudential_otp_generic(page, code: str, timeout_ms: int) -> bool:
    """PRUDENTIAL_OTP_SELECTOR 未設定時、確認番号入力欄を推定して入力する。

    **ログイン ID 欄（lightning-input / input[id^=\"input-\"] 等）と誤認識しないよう、
    広すぎるセレクタは使わず、ログイン ID 疑いの要素はスキップする。**
    """
    # ログイン ID と共通しやすいセレクタは含めない（旧: lightning-input input.slds-input 等は削除）
    selectors = [
        'input[id^="confirmNumber"]',
        'input[data-name="otpValue"]',
        'input[name="confirmNumber"]',
        'input[autocomplete="one-time-code"]',
        'input[inputmode="numeric"]',
        'input[type="tel"]',
        'input[placeholder*="確認番号"]',
        'input[aria-label*="確認番号"]',
        'input[placeholder*="確認"]',
        'input[aria-label*="確認"]',
        'input[maxlength="6"]',
    ]
    host = os.environ.get("PRUDENTIAL_OTP_HOST_SELECTOR", "").strip()
    for fr in _frames_in_order(page):
        root = fr.locator(host).first if host else fr
        try:
            if host:
                root.wait_for(state="attached", timeout=min(8000, timeout_ms))
        except Exception:
            continue
        for sel in selectors:
            try:
                loc = root.locator(sel)
                n = loc.count()
                for i in range(min(n, 8)):
                    el = loc.nth(i)
                    try:
                        if not el.is_visible():
                            continue
                    except Exception:
                        continue
                    if _is_probable_prudential_login_id_input(el):
                        continue
                    if _fill_otp_field_lightning_compat(el, code, timeout_ms):
                        return True
            except Exception:
                continue
    return False


def _click_last_role_button_by_text_in_frame(frame, text: str, timeout_ms: int) -> bool:
    """同一文言のボタンが複数あるとき、手前のステップの「次へ」を誤クリックしないよう最後の表示中を優先。"""
    if not text:
        return False
    for pat in (
        re.compile(re.escape(text)),
        re.compile(text.replace(" ", r"\s*")),
    ):
        try:
            loc = frame.get_by_role("button", name=pat)
            n = loc.count()
            if n <= 0:
                continue
            for i in range(n - 1, -1, -1):
                btn = loc.nth(i)
                try:
                    if not btn.is_visible():
                        continue
                    btn.click(timeout=timeout_ms)
                    return True
                except Exception:
                    continue
        except Exception:
            continue
    return False


def _click_last_visible_text_button_any_frame(page, text: str, timeout_ms: int) -> bool:
    for fr in _login_probe_frames(page):
        if _click_last_role_button_by_text_in_frame(fr, text, timeout_ms):
            return True
    return False


def _click_prudential_otp_next_scoped(page, timeout_ms: int) -> bool:
    """OTP 入力欄に紐づく「次へ」を優先してクリックする。

    画面内に同じ primary ボタンが複数あることがあり、広いセレクタだと誤クリックでゲストに戻るため、
    confirmNumber 入力欄（または OTP detail コンポーネント）にスコープして「次へ」を探す。
    """
    # 1) OTP detail コンポーネント内の「次へ」
    try:
        detail = page.locator("c-mypg-otp-customer-info-detail").first
        if detail.count() > 0 and detail.is_visible(timeout=2000):
            btns = detail.get_by_role("button", name=re.compile(r"^\s*次へ\s*$"))
            n = btns.count()
            for i in range(n - 1, -1, -1):
                b = btns.nth(i)
                try:
                    if not b.is_visible():
                        continue
                    b.scroll_into_view_if_needed(timeout=8000)
                    b.click(timeout=timeout_ms)
                    return True
                except Exception:
                    continue
    except Exception:
        pass

    # 2) confirmNumber 入力欄の近傍（祖先）にスコープして「次へ」
    for sel in (
        'input[name="confirmNumber"]',
        "input.confirm-number",
        "[data-id='confirmNumber']",
    ):
        try:
            inp = page.locator(sel).first
            if inp.count() <= 0 or not inp.is_visible(timeout=2000):
                continue
            # 近傍のコンテナ（フォーム/セクション）から「次へ」を探す
            for ancestor in (
                inp.locator("xpath=ancestor-or-self::*[self::form][1]"),
                inp.locator("xpath=ancestor-or-self::*[self::section][1]"),
                inp.locator("xpath=ancestor-or-self::*[self::div][1]"),
            ):
                try:
                    if ancestor.count() <= 0:
                        continue
                    btns = ancestor.get_by_role("button", name=re.compile(r"^\s*次へ\s*$"))
                    n = btns.count()
                    for i in range(n - 1, -1, -1):
                        b = btns.nth(i)
                        try:
                            if not b.is_visible():
                                continue
                            b.scroll_into_view_if_needed(timeout=8000)
                            b.click(timeout=timeout_ms)
                            return True
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception:
            continue

    return False


def _click_prudential_otp_submit_host_scoped(page, timeout_ms: int) -> bool:
    """ログイン枠と同じ LWC ホスト内の lightning-button を優先（Shadow 内ボタンで文言取得が空になりやすい対策）。"""
    for env_key in ("PRUDENTIAL_OTP_HOST_SELECTOR", "PRUDENTIAL_LOGIN_FORM_HOST_SELECTOR"):
        host_sel = os.environ.get(env_key, "").strip()
        if not host_sel:
            continue
        for fr in _login_probe_frames(page):
            try:
                host = fr.locator(host_sel).first
                host.wait_for(state="attached", timeout=min(8000, timeout_ms))
                if not host.is_visible(timeout=2000):
                    continue
            except Exception:
                continue
            for inner in (
                "c-alfa-button lightning-button button",
                "lightning-button button.slds-button_brand",
                "lightning-button button",
            ):
                try:
                    loc = host.locator(inner)
                    n = loc.count()
                    if n <= 0:
                        continue
                    for i in range(n - 1, -1, -1):
                        btn = loc.nth(i)
                        try:
                            if not btn.is_visible():
                                continue
                            btn.click(timeout=timeout_ms)
                            return True
                        except Exception:
                            continue
                except Exception:
                    continue
    return False


def _click_prudential_otp_submit_generic(page, timeout_ms: int) -> bool:
    """確認番号送信ボタン（ホスト内 LWC → 文言 → 広いセレクタ）。

    本関数は OTP 入力後の送信専用。OTP 用 LWC が表示されているのに
    ``PRUDENTIAL_LOGIN_FORM_HOST_SELECTOR`` 側の lightning-button を先に押すと、
    ログイン送信扱いになりゲスト画面に戻ることがあるため、その場合はホストスコープを試さない。
    """
    otp_detail_visible = False
    try:
        det = page.locator("c-mypg-otp-customer-info-detail").first
        otp_detail_visible = bool(det.is_visible(timeout=2000))
    except Exception:
        otp_detail_visible = False
    otp_field_visible = False
    if not otp_detail_visible:
        try:
            for sel in (
                'input[name="confirmNumber"]',
                "input.confirm-number",
                "[data-id='confirmNumber']",
            ):
                root = page.locator(sel)
                if root.count() <= 0:
                    continue
                if root.first.is_visible(timeout=1500):
                    otp_field_visible = True
                    break
        except Exception:
            otp_field_visible = False
    if not otp_detail_visible and not otp_field_visible:
        if _click_prudential_otp_submit_host_scoped(page, timeout_ms):
            return True
    for txt in (
        "次へ進む",
        "次へ",
        "送信",
        "確認",
        "ログイン",
        "続行",
        "進む",
        "Next",
        "Submit",
    ):
        if _click_last_visible_text_button_any_frame(page, txt, timeout_ms):
            return True
        if _click_by_selector_or_text_any_frame(
            page, selector="", text=txt, timeout_ms=timeout_ms
        ):
            return True
    for fr in _login_probe_frames(page):
        for sel in (
            'lightning-button button[type="button"]',
            "button.slds-button_brand",
            'button[type="submit"]',
        ):
            try:
                loc = fr.locator(sel)
                if loc.count() > 0 and loc.last.is_visible():
                    loc.last.click(timeout=timeout_ms)
                    return True
            except Exception:
                try:
                    loc = fr.locator(sel)
                    if loc.count() > 0 and loc.first.is_visible():
                        loc.first.click(timeout=timeout_ms)
                        return True
                except Exception:
                    continue
    return False


def _page_still_matches_login_hint(page) -> bool:
    """PRUDENTIAL_LOGIN_STILL_URL_SUBSTR が URL に含まれるときログイン失敗とみなす。"""
    needle = os.environ.get("PRUDENTIAL_LOGIN_STILL_URL_SUBSTR", "").strip()
    if not needle:
        return False
    try:
        url = page.url or ""
    except Exception:
        return False
    return needle in url


def _prudential_guest_shell_visible(page) -> bool:
    """ログイン前のゲスト画面（c-mypg-guest-view）がまだ手前に出ているか。"""
    try:
        g = page.locator("c-mypg-guest-view").first
        return bool(g.is_visible(timeout=2500))
    except Exception:
        return False


def _prudential_authenticated_top_ready(page, *, timeout_ms: int) -> bool:
    """認証後の本体 UI が表示されたか。

    マイページトップは ``c-mypg-top-detail`` だが、OTP 直後に **契約一覧など別 URL** へ遷移する場合は
    ``c-mypg-top-detail`` が出ず ``c-mypg-view`` のみになることがある。
    """
    slot = max(4000, int(timeout_ms) // 2)
    for sel in (
        "c-mypg-top-detail",
        "c-mypg-view",
    ):
        try:
            page.locator(sel).first.wait_for(state="visible", timeout=slot)
            return True
        except Exception:
            continue
    return False


def _extract_by_selector(page, selector: str) -> tuple[int | None, str]:
    if not selector:
        return None, ""
    loc = page.locator(selector)
    if loc.count() <= 0:
        return None, ""
    txt = (loc.first.inner_text() or "").strip()
    return _parse_first_jpy(txt)


def _extract_table_row_by_th_contains(page, header_substring: str) -> tuple[int | None, str]:
    if not header_substring:
        return None, ""
    raw = page.evaluate(
        """
(sub) => {
  const norm = (s) => (s || "").replace(/\\s/g, "").replace(/\\u3000/g, "");
  const want = norm(sub);
  for (const tr of document.querySelectorAll("table tr")) {
    const th = tr.querySelector("th");
    if (!th) continue;
    const t = norm(th.innerText || "");
    if (!t.includes(want)) continue;
    const td = tr.querySelector("td:last-of-type") || tr.querySelector("td");
    if (!td) continue;
    return (td.innerText || "").replace(/\\s+/g, " ").trim();
  }
  return "";
}
""",
        header_substring,
    )
    return _parse_first_jpy((raw or "").strip())


def _extract_by_label_dom(page, label: str) -> tuple[int | None, str]:
    if not label:
        return None, ""
    raw = page.evaluate(
        """
(label) => {
  const nodes = Array.from(document.querySelectorAll("p,dt,th,span,div,td,li"));
  for (const n of nodes) {
    const txt = (n.innerText || "").replace(/\\s+/g, " ").trim();
    if (!txt || !txt.includes(label)) continue;
    const container = n.closest("div,li,section,article,tr,dl,table") || n.parentElement;
    if (!container) continue;
    const num = container.querySelector(".c-text-number-num, .amount, .money, .yen");
    if (num) {
      const t = (num.textContent || "").replace(/\\s+/g, " ").trim();
      if (t) return t;
    }
    const around = (container.innerText || "").replace(/\\s+/g, " ").trim();
    const m = around.match(/([+-]?\\d[\\d,]{0,})(?:\\s*円)?/);
    if (m && m[1]) return m[1];
  }
  return "";
}
""",
        label,
    )
    return _parse_first_jpy(raw or "")


def _extract_by_label_fallback(page, label: str) -> tuple[int | None, str]:
    body = (page.inner_text("body") or "").replace("\u3000", " ")
    if not body or not label:
        return None, ""
    pattern = rf"{re.escape(label)}[^\n\r]{{0,40}}?([+-]?\d[\d,]{{0,}}(?:\s*円)?)"
    m = re.search(pattern, body)
    if not m:
        return None, ""
    return _parse_first_jpy(m.group(1))


def _navigate_after_login_prudential(page, timeout_ms: int) -> None:
    target_url = os.environ.get("PRUDENTIAL_TARGET_URL", "").strip()
    after_sel = os.environ.get("PRUDENTIAL_AFTER_LOGIN_CLICK_SELECTOR", "").strip()
    after_txt = os.environ.get("PRUDENTIAL_AFTER_LOGIN_CLICK_TEXT", "").strip()
    post_ms = int(os.environ.get("PRUDENTIAL_POST_LOGIN_WAIT_MS", "10000") or "10000")
    try:
        page.wait_for_timeout(post_ms)
    except Exception:
        pass

    if target_url:
        page.goto(target_url, wait_until="domcontentloaded")
        _wait_page_ready(page, timeout_ms)
        return

    if after_sel or after_txt:
        if not _click_by_selector_or_text_any_frame(
            page, selector=after_sel, text=after_txt, timeout_ms=timeout_ms
        ):
            raise RuntimeError(
                "ログイン後のクリックに失敗しました。"
                "PRUDENTIAL_AFTER_LOGIN_CLICK_SELECTOR / TEXT を確認するか、"
                "PRUDENTIAL_TARGET_URL を指定してください。"
            )
        _wait_page_ready(page, timeout_ms)
        return

    if _has_manual_prudential_nav_config():
        for step in range(1, _MAX_NAV_STEPS + 1):
            sel = os.environ.get(f"PRUDENTIAL_NAV_STEP{step}_SELECTOR", "").strip()
            txt = os.environ.get(f"PRUDENTIAL_NAV_STEP{step}_TEXT", "").strip()
            if not sel and not txt:
                if step == 1:
                    raise RuntimeError(
                        "PRUDENTIAL_NAV_STEP1_* が空です。"
                        "PRUDENTIAL_NAV_STEP1_SELECTOR または TEXT を設定してください。"
                    )
                break
            if not _click_by_selector_or_text_any_frame(
                page, selector=sel, text=txt, timeout_ms=timeout_ms
            ):
                raise RuntimeError(
                    f"ナビ ステップ{step}（SELECTOR={sel!r} TEXT={txt!r}）をクリックできませんでした。"
                )
            _wait_page_ready(page, timeout_ms)
        return

    use_default = os.environ.get("PRUDENTIAL_USE_DEFAULT_NAV", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
    if use_default:
        _prudential_default_nav_mypage(page, timeout_ms)
        return

    raise RuntimeError(
        "ログイン後の導線がありません。PRUDENTIAL_TARGET_URL / AFTER_LOGIN_CLICK_* / "
        "NAV_STEP* のいずれかを設定するか、PRUDENTIAL_USE_DEFAULT_NAV=1（既定）で自動ナビを使ってください。"
    )


def _extract_surrender_from_page(
    page,
    *,
    value_selector: str,
    value_label: str,
    row_th_contains: str,
    reference_label: str,
) -> tuple[int | None, str, str]:
    value: int | None = None
    value_text = ""
    mode = "none"
    if value_selector:
        value, value_text = _extract_by_selector(page, value_selector)
        if value is not None:
            mode = "selector"
    if value is None:
        # Shadow DOM 配下でも拾えるよう、Playwright の text engine で最大の「xxx円」を優先して取得する
        value, value_text = _extract_prudential_surrender_by_section_text(page)
        if value is not None:
            mode = "prudential:text-max-yen"
    if value is None:
        value, value_text = _extract_prudential_reference_payment(page)
        if value is not None:
            mode = "prudential:お支払い予定額(参考)"
    if value is None and reference_label:
        value, value_text = _extract_by_label_dom(page, reference_label)
        if value is not None:
            mode = f"label-dom:{reference_label}"
    if value is None and row_th_contains:
        value, value_text = _extract_table_row_by_th_contains(page, row_th_contains)
        if value is not None:
            mode = f"table-th:{row_th_contains}"
    if value is None:
        value, value_text = _extract_by_label_dom(page, value_label)
        if value is not None:
            mode = f"label-dom:{value_label}"
    if value is None:
        value, value_text = _extract_by_label_fallback(page, value_label)
        if value is not None:
            mode = f"label:{value_label}"
    # 明らかに小さい値（例: 1円）を誤取得した場合は失敗扱いにして、誤通知を防ぐ
    if value is not None:
        min_ok = _env_int_nonneg("PRUDENTIAL_SURRENDER_MIN_JPY", 1000)
        if min_ok > 0 and value < min_ok:
            try:
                print(
                    f"🐞 解約返戻金が小さすぎるため無効扱い: {value}円 < {min_ok}円"
                    f"（現在URL: {page.url}）",
                    file=sys.stderr,
                )
            except Exception:
                pass
            value, value_text, mode = None, "", "too-small"
    return value, value_text, mode


def _env_yesno_or_default(name: str, *, default: bool) -> bool:
    """環境変数が明示されていれば 1/0 で解釈、未設定なら default。"""
    raw = os.environ.get(name, "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


def _env_int_nonneg(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def _otp_storage_state_path() -> Path:
    raw = os.environ.get("PRUDENTIAL_OTP_STORAGE_STATE_PATH", "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_OTP_STORAGE_STATE


def _otp_resume_meta_path() -> Path:
    raw = os.environ.get("PRUDENTIAL_OTP_RESUME_META_PATH", "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_OTP_RESUME_META


def _load_otp_resume_meta() -> dict | None:
    p = _otp_resume_meta_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_prudential_otp_checkpoint(
    context,
    page,
    *,
    username: str,
    account_no: int,
    login_submit_ms: int,
) -> None:
    """確認番号画面の Playwright storage_state を保存（--resume-otp でログインを繰り返さない）。"""
    state_path = _otp_storage_state_path()
    meta_path = _otp_resume_meta_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(state_path))
    meta = {
        "username": (username or "").strip(),
        "account_no": int(account_no),
        "login_submit_ms": int(login_submit_ms),
        "otp_page_url": page.url,
        "saved_at_ms": int(time.time() * 1000),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"📎 確認番号画面のセッションを保存しました: {state_path.name} / {meta_path.name}",
        file=sys.stderr,
    )


def fetch_prudential_surrender_value(
    *,
    headless: bool,
    timeout_ms: int,
    save_debug: bool,
    env_file: Path,
    otp_code_override: str | None = None,
    fetch_otp_from_gmail: bool | None = None,
    debug_login_submit: bool | None = None,
    debug_login_form_fail: bool | None = None,
    pause_before_login_ms: int | None = None,
    pause_on_login_form_fail_ms: int | None = None,
    resume_otp_only: bool | None = None,
    otp_pause_before_submit: bool | None = None,
    otp_pause_at_screen: bool | None = None,
) -> PrudentialSurrenderValueResult:
    _load_env_file(env_file)

    pause_before_otp_submit_eff = (
        bool(otp_pause_before_submit)
        if otp_pause_before_submit is not None
        else _env_yesno_or_default("PRUDENTIAL_OTP_PAUSE_BEFORE_SUBMIT", default=False)
    )
    pause_at_otp_screen_eff = (
        bool(otp_pause_at_screen)
        if otp_pause_at_screen is not None
        else _env_yesno_or_default("PRUDENTIAL_OTP_PAUSE_AT_SCREEN", default=False)
    )

    debug_login_submit_effective = (
        debug_login_submit
        if debug_login_submit is not None
        else os.environ.get("PRUDENTIAL_DEBUG_LOGIN_SUBMIT", "").strip().lower()
        in ("1", "true", "yes", "on")
    )

    debug_login_form_fail_effective = (
        debug_login_form_fail
        if debug_login_form_fail is not None
        else _env_yesno_or_default(
            "PRUDENTIAL_DEBUG_LOGIN_FORM_FAIL",
            default=debug_login_submit_effective,
        )
    )

    fetch_otp_gmail_effective = (
        fetch_otp_from_gmail
        if fetch_otp_from_gmail is not None
        else _env_yesno_or_default("PRUDENTIAL_FETCH_OTP_FROM_GMAIL", default=True)
    )

    login_url = os.environ.get("PRUDENTIAL_LOGIN_URL", "").strip()
    if not login_url:
        raise RuntimeError("PRUDENTIAL_LOGIN_URL が未設定です。")

    accounts = _collect_prudential_accounts()

    resume_otp_effective = (
        resume_otp_only
        if resume_otp_only is not None
        else _env_yesno_or_default("PRUDENTIAL_RESUME_OTP_ONLY", default=False)
    )
    if resume_otp_effective and len(accounts) > 1:
        print(
            "注意: --resume-otp は保存セッションが 1人目の確認番号画面のため、"
            f"2人目以降（{len(accounts) - 1} 件）はこの実行ではスキップします。",
            file=sys.stderr,
        )
        accounts = accounts[:1]

    username_selector = os.environ.get("PRUDENTIAL_USERNAME_SELECTOR", "").strip()
    password_selector = os.environ.get("PRUDENTIAL_PASSWORD_SELECTOR", "").strip()
    submit_selector = os.environ.get("PRUDENTIAL_SUBMIT_SELECTOR", "").strip()
    if not username_selector or not password_selector or not submit_selector:
        raise RuntimeError(
            "プルデンシャル生命のログイン用に "
            "PRUDENTIAL_USERNAME_SELECTOR / PRUDENTIAL_PASSWORD_SELECTOR / "
            "PRUDENTIAL_SUBMIT_SELECTOR を設定してください（契約者サイトの画面に合わせる）。"
        )

    logout_url = os.environ.get("PRUDENTIAL_LOGOUT_URL", "").strip()
    logout_selector = os.environ.get("PRUDENTIAL_LOGOUT_SELECTOR", "").strip()
    logout_text = os.environ.get("PRUDENTIAL_LOGOUT_TEXT", "").strip()

    otp_selector = os.environ.get("PRUDENTIAL_OTP_SELECTOR", "").strip()
    otp_submit_selector = os.environ.get("PRUDENTIAL_OTP_SUBMIT_SELECTOR", "").strip()

    value_selector = os.environ.get("PRUDENTIAL_SURRENDER_VALUE_SELECTOR", "").strip()
    value_label = os.environ.get("PRUDENTIAL_SURRENDER_VALUE_LABEL", "解約返戻金").strip()
    row_th_contains = os.environ.get("PRUDENTIAL_SURRENDER_ROW_TH_CONTAINS", "解約返戻金").strip()
    reference_label = os.environ.get("PRUDENTIAL_SURRENDER_REFERENCE_LABEL", "").strip()

    login_page_ready_ms = int(os.environ.get("PRUDENTIAL_LOGIN_PAGE_READY_MS", "0") or "0")
    login_form_host_selector = os.environ.get(
        "PRUDENTIAL_LOGIN_FORM_HOST_SELECTOR",
        "c-mypg-login-info-input-detail",
    ).strip()
    post_login_anim_ms = int(os.environ.get("PRUDENTIAL_POST_LOGIN_ANIMATION_MS", "12000") or "12000")
    after_otp_anim_ms = int(os.environ.get("PRUDENTIAL_AFTER_OTP_ANIMATION_MS", "12000") or "12000")

    pause_before_login_eff_ms = (
        max(0, int(pause_before_login_ms))
        if pause_before_login_ms is not None
        else _env_int_nonneg("PRUDENTIAL_DEBUG_PAUSE_BEFORE_LOGIN_MS", 0)
    )
    pause_on_login_fail_eff_ms = (
        max(0, int(pause_on_login_form_fail_ms))
        if pause_on_login_form_fail_ms is not None
        else _env_int_nonneg("PRUDENTIAL_DEBUG_PAUSE_ON_LOGIN_FORM_FAIL_MS", 0)
    )
    login_heuristic_fallback_effective = _env_yesno_or_default(
        "PRUDENTIAL_LOGIN_HEURISTIC_FALLBACK",
        default=True,
    )
    heuristic_host = login_form_host_selector or "c-mypg-login-info-input-detail"
    pause_before_gmail_otp_ms = _env_int_nonneg("PRUDENTIAL_PAUSE_BEFORE_GMAIL_OTP_MS", 0)
    otp_gmail_lookback_ms = _env_int_nonneg("PRUDENTIAL_OTP_GMAIL_LOOKBACK_MS", 60000)

    items: list[PrudentialSurrenderAccountResult] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        # 重要: 同一タブ/同一セッションを使い回すと、ログインがループしてゲストに戻ることがある。
        # そのため、原則として「アカウントごとに新しい browser context（=新セッション）」を使う。
        context = None
        page = None

        for idx, (username, password) in enumerate(accounts):
            account_no = idx + 1
            login_submit_ms = 0
            resume_here = bool(resume_otp_effective and idx == 0)
            # 1アカウント分を新しいセッションで開始
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
            if resume_here:
                meta_pre = _load_otp_resume_meta()
                state_path = _otp_storage_state_path()
                if not meta_pre or not (meta_pre.get("otp_page_url") or "").strip():
                    raise RuntimeError(
                        "確認番号画面からの再開用データがありません。"
                        f"先に通常実行でログイン〜確認番号画面まで進むと {DEFAULT_OTP_RESUME_META.name} が作成されます。"
                    )
                if not state_path.exists():
                    raise RuntimeError(
                        f"セッションファイルがありません: {state_path}\n"
                        "通常実行で確認番号画面に到達すると自動保存されます。"
                    )
                context = browser.new_context(
                    locale="ja-JP",
                    storage_state=str(state_path),
                )
            else:
                context = browser.new_context(locale="ja-JP")
            page = context.new_page()
            page.set_default_timeout(timeout_ms)

            if resume_here:
                meta = _load_otp_resume_meta() or {}
                otp_url = (meta.get("otp_page_url") or "").strip()
                if not otp_url:
                    raise RuntimeError("再開用メタに otp_page_url がありません。")
                page.goto(otp_url, wait_until="load")
                _wait_login_shell_ready(page, timeout_ms)
                _wait_page_ready(page, timeout_ms)
                _sleep_ms(page, min(3000, login_page_ready_ms))
                login_submit_ms = int(meta.get("login_submit_ms") or 0)
                if login_submit_ms <= 0:
                    saved_at = int(meta.get("saved_at_ms") or 0)
                    login_submit_ms = (
                        max(0, saved_at - 180_000) if saved_at else int(time.time() * 1000 - 180_000)
                    )
                print(
                    "↩ 保存済みセッションで確認番号画面から再開します（ログインはスキップ）。",
                    file=sys.stderr,
                )
            else:
                page.goto(login_url, wait_until="load")
                _wait_login_shell_ready(page, timeout_ms)

            if not resume_here:
                # ログイン ID 画面はトップのアニメ対象外。必要ならのみ追加待機（既定 0）
                _sleep_ms(page, login_page_ready_ms)
                if login_form_host_selector:
                    try:
                        page.locator(login_form_host_selector).first.wait_for(
                            state="visible",
                            timeout=min(timeout_ms, 60_000),
                        )
                    except Exception:
                        pass
                if pause_before_login_eff_ms:
                    print(
                        f"⏳ ログイン欄探索まで {pause_before_login_eff_ms} ms 待機します"
                        "（Chromium でログイン画面を Inspect してセレクタを確認できます）。",
                        file=sys.stderr,
                    )
                    _sleep_ms(page, pause_before_login_eff_ms)

                def _dump_pause_on_login_fail() -> None:
                    if debug_login_form_fail_effective:
                        _dump_login_form_fail_debug(page, account_no)
                    if pause_on_login_fail_eff_ms:
                        print(
                            f"⏳ ログイン入力欄未検出のため、あと {pause_on_login_fail_eff_ms} ms "
                            "ブラウザを開いたままにします（画面・DevTools を確認してください）。",
                            file=sys.stderr,
                        )
                        _sleep_ms(page, pause_on_login_fail_eff_ms)

                try:
                    u_loc, p_loc, s_loc = _resolve_login_form_locators(
                        page,
                        username_selector,
                        password_selector,
                        submit_selector,
                        timeout_ms,
                    )
                except RuntimeError:
                    if login_heuristic_fallback_effective:
                        print(
                            "ヒント: .env の固定セレクタではログイン欄を解決できませんでした。"
                            "動的 ID 向けヒューリスティックを試します。",
                            file=sys.stderr,
                        )
                        try:
                            u_loc, p_loc, s_loc = _resolve_login_form_locators_prudential_heuristic(
                                page,
                                heuristic_host,
                                timeout_ms,
                            )
                        except RuntimeError:
                            _dump_pause_on_login_fail()
                            raise
                        print(
                            "✓ ログイン欄はヒューリスティックで解決しました。"
                            f"（ログイン枠: {heuristic_host!r}）",
                            file=sys.stderr,
                        )
                    else:
                        _dump_pause_on_login_fail()
                        raise

                if username:
                    u_loc.fill(username)
                if password:
                    p_loc.fill(password)
                if username and password:
                    s_loc.click()
                    login_submit_ms = int(time.time() * 1000)
                    _wait_page_ready(page, timeout_ms)
                    # 固定 sleep だけだと、確認番号画面が一瞬で消えてログインに戻る SPA では
                    # 「今どのページか」が不定のまま Gmail 待ち等に進んでしまうため、
                    # マイページ or 確認番号ステップが安定するまでポーリングする。
                    settle_kind, settle_msg = _wait_prudential_post_login_settle(
                        page,
                        otp_selector=otp_selector,
                        timeout_ms=timeout_ms,
                    )
                    print(f"📌 {settle_msg} （判定: {settle_kind}）", file=sys.stderr)
                    if settle_kind == "login_reset":
                        DEFAULT_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                        dbg_lr = DEFAULT_DEBUG_DIR / (
                            f"prudential_login_reset_after_submit_account{account_no}.html"
                        )
                        try:
                            dbg_lr.write_text(page.content(), encoding="utf-8")
                        except Exception:
                            pass
                        raise RuntimeError(
                            f"{settle_msg} "
                            f"HTML を {dbg_lr.name} に保存しました。"
                            " セッション切れ・サイト側タイムアウト・確認番号画面の一時表示のあとに"
                            "ログインへ戻る場合があります。表示ありブラウザで再現を確認するか、"
                            "時間帯を変えて試してください。"
                        )
                    if settle_kind == "timeout":
                        DEFAULT_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                        dbg_to = DEFAULT_DEBUG_DIR / (
                            f"prudential_post_login_settle_timeout_account{account_no}.html"
                        )
                        try:
                            dbg_to.write_text(page.content(), encoding="utf-8")
                        except Exception:
                            pass
                        raise RuntimeError(
                            f"{settle_msg} {dbg_to.name} を保存しました。"
                            " PRUDENTIAL_POST_LOGIN_SETTLE_MS（最大待ち）や"
                            " PRUDENTIAL_OTP_STEP_STABLE_MS（確認番号 UI が連続で見える時間）を"
                            "伸ばして試してください。"
                        )
                    extra_anim = _env_int_nonneg(
                        "PRUDENTIAL_POST_LOGIN_EXTRA_ANIM_MS",
                        2000,
                    )
                    _sleep_ms(page, extra_anim)
                    if debug_login_submit_effective:
                        _dump_login_submit_debug(page, account_no, "after_post_login_anim")

            otp_override = otp_code_override if account_no == 1 else None
            otp_env = _otp_env_for_account(account_no)
            has_otp_from_user = bool((otp_override or "").strip() or (otp_env or "").strip())
            if resume_here:
                needs_otp = True
            else:
                needs_otp = bool(otp_selector and page.locator(otp_selector).count() > 0) or (
                    _page_looks_like_prudential_otp_challenge(page)
                )
                # 確認番号画面を Heuristic で取りこぼすと、--otp-code を付けても OTP ブロックに入らない
                if has_otp_from_user and not needs_otp:
                    _sleep_ms(page, 2000)
                    needs_otp = bool(otp_selector and page.locator(otp_selector).count() > 0) or (
                        _page_looks_like_prudential_otp_challenge(page)
                    )
                if has_otp_from_user and not needs_otp and _prudential_guest_shell_visible(page):
                    needs_otp = True
                if fetch_otp_gmail_effective and not has_otp_from_user:
                    if not needs_otp:
                        _sleep_ms(page, 2000)
                        if not _prudential_authenticated_top_ready(page, timeout_ms=8000):
                            if _prudential_guest_shell_visible(page) or _page_looks_like_prudential_otp_challenge(
                                page
                            ):
                                needs_otp = True
            if needs_otp:
                _save_prudential_otp_checkpoint(
                    context,
                    page,
                    username=username,
                    account_no=account_no,
                    login_submit_ms=login_submit_ms,
                )
                # OTP 画面のデバッグダンプ（アカウント指定）
                dbg_accts_raw = os.environ.get("PRUDENTIAL_DEBUG_OTP_SCREEN_ACCOUNTS", "").strip()
                if dbg_accts_raw:
                    want = {x.strip() for x in dbg_accts_raw.split(",") if x.strip()}
                    if str(account_no) in want:
                        try:
                            DEFAULT_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                            dbg_html = DEFAULT_DEBUG_DIR / f"prudential_otp_screen_before_fill_account{account_no}.html"
                            dbg_png = DEFAULT_DEBUG_DIR / f"prudential_otp_screen_before_fill_account{account_no}.png"
                            dbg_html.write_text(page.content(), encoding="utf-8")
                            page.screenshot(path=str(dbg_png), full_page=True)
                            print(
                                f"🐞 OTP 画面（入力前）を保存しました: {dbg_html.name} / {dbg_png.name}",
                                file=sys.stderr,
                            )
                        except Exception:
                            pass
                if pause_at_otp_screen_eff:
                    DEFAULT_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                    dbg_html = (
                        DEFAULT_DEBUG_DIR
                        / f"prudential_otp_screen_inspect_account{account_no}.html"
                    )
                    dbg_png = (
                        DEFAULT_DEBUG_DIR
                        / f"prudential_otp_screen_inspect_account{account_no}.png"
                    )
                    try:
                        dbg_html.write_text(page.content(), encoding="utf-8")
                        page.screenshot(path=str(dbg_png), full_page=True)
                    except Exception:
                        pass
                    print(
                        "⏸ 確認番号入力画面に到達しました。Gmail 取得・番号入力の前で停止しています。"
                        f" 保存: {dbg_html.name} / {dbg_png.name}",
                        file=sys.stderr,
                    )
                    if not headless:
                        print(
                            "   ブラウザで DevTools を開き「次へ」ボタンのセレクタを確認してください。"
                            " Playwright Inspector が出ていれば Resume で終了します。",
                            file=sys.stderr,
                        )
                        try:
                            page.pause()
                        except Exception as exc:
                            print(f"🐞 page.pause 不可: {exc}", file=sys.stderr)
                    elif sys.stdin.isatty():
                        try:
                            input("セレクタ確認後、Enter で終了… ")
                        except EOFError:
                            pass
                    else:
                        wait_ms = _env_int_nonneg(
                            "PRUDENTIAL_OTP_PAUSE_AT_SCREEN_WAIT_MS", 600000
                        )
                        print(
                            f"⚠ ヘッドレス・非TTYのため {wait_ms // 1000}s 待機後に終了します。",
                            file=sys.stderr,
                        )
                        _sleep_ms(page, wait_ms)
                    browser.close()
                    raise PrudentialOtpPausedAtScreen(
                        "確認番号画面で停止しました（PRUDENTIAL_OTP_PAUSE_AT_SCREEN）。"
                        " PRUDENTIAL_OTP_SUBMIT_SELECTOR に「次へ」を設定し、このフラグを 0 にして再実行してください。"
                    )
                otp_code = _resolve_otp_code(
                    otp_env,
                    otp_override,
                    account_index=account_no,
                )
                if not otp_code and fetch_otp_gmail_effective:
                    prev_token = os.environ.get("PRUDENTIAL_GMAIL_TOKEN_PATH", "")
                    prev_expect = os.environ.get("PRUDENTIAL_GMAIL_EXPECT_EMAIL", "")
                    try:
                        tok_key = (
                            "PRUDENTIAL_GMAIL_TOKEN_PATH"
                            if account_no <= 1
                            else f"PRUDENTIAL_GMAIL_TOKEN_PATH_{account_no}"
                        )
                        exp_key = (
                            "PRUDENTIAL_GMAIL_EXPECT_EMAIL"
                            if account_no <= 1
                            else f"PRUDENTIAL_GMAIL_EXPECT_EMAIL_{account_no}"
                        )
                        tok = os.environ.get(tok_key, "").strip()
                        exp = os.environ.get(exp_key, "").strip()
                        if tok:
                            os.environ["PRUDENTIAL_GMAIL_TOKEN_PATH"] = tok
                        if exp:
                            os.environ["PRUDENTIAL_GMAIL_EXPECT_EMAIL"] = exp

                        if pause_before_gmail_otp_ms:
                            print(
                                f"⏳ 確認番号入力画面のあと、Gmail API で取得するまで {pause_before_gmail_otp_ms} ms "
                                "待機します（ブラウザで画面・受信の確認用）。",
                                file=sys.stderr,
                            )
                            _sleep_ms(page, pause_before_gmail_otp_ms)
                        skew_dbg = _env_int_nonneg("PRUDENTIAL_OTP_GMAIL_CLOCK_SKEW_MS", 180000)
                        now_ms_anchor = int(time.time() * 1000)
                        elapsed_since_click_ms = max(0, now_ms_anchor - login_submit_ms)
                        post_login_slack_ms = _env_int_nonneg(
                            "PRUDENTIAL_OTP_GMAIL_POST_LOGIN_SLACK_MS",
                            120000,
                        )
                        strict_after_login = _env_yesno_or_default(
                            "PRUDENTIAL_OTP_GMAIL_STRICT_AFTER_LOGIN",
                            default=False,
                        )
                        if strict_after_login and login_submit_ms <= 0:
                            print(
                                "⚠ PRUDENTIAL_OTP_GMAIL_STRICT_AFTER_LOGIN=1 ですが login_submit_ms が無効のため、"
                                "従来のしきい値計算にフォールバックします（フルログインでログインボタン送信が記録されているか確認）。",
                                file=sys.stderr,
                            )
                            strict_after_login = False
                        if strict_after_login:
                            strict_lb = _env_int_nonneg(
                                "PRUDENTIAL_OTP_GMAIL_STRICT_LOOKBACK_MS",
                                120_000,
                            )
                            effective_lookback_ms = strict_lb
                            gmail_min_internal_ms = max(0, login_submit_ms - effective_lookback_ms)
                            print(
                                "📧 Gmail API で確認番号メールを検索します（"
                                "PRUDENTIAL_OTP_GMAIL_STRICT_AFTER_LOGIN=1: 今回のログイン送信より前の通知は除外）。"
                                f" internalDate しきい値の基準: ログイン送信より最大約 {effective_lookback_ms // 1000}s 手前まで。"
                                f" 時計ずれ対策でさらに {skew_dbg} ms 緩めます（PRUDENTIAL_OTP_GMAIL_CLOCK_SKEW_MS）。",
                                file=sys.stderr,
                            )
                        else:
                            effective_lookback_ms = max(
                                otp_gmail_lookback_ms,
                                elapsed_since_click_ms + post_login_slack_ms,
                            )
                            gmail_min_internal_ms = max(0, login_submit_ms - effective_lookback_ms)
                            print(
                                "📧 Gmail API で確認番号メールを検索します。"
                                f" 着信時刻しきい値はログイン送信より最大約 {effective_lookback_ms // 1000}s 手前まで許容 "
                                f"（settle・待機後の遅延着信向け・PRUDENTIAL_OTP_GMAIL_POST_LOGIN_SLACK_MS）。"
                                f" 時計ずれ対策でさらに {skew_dbg} ms 緩めます（PRUDENTIAL_OTP_GMAIL_CLOCK_SKEW_MS）。",
                                file=sys.stderr,
                            )
                        try:
                            from prudential_gmail_otp import poll_prudential_otp_from_gmail
                        except ImportError as exc:
                            raise RuntimeError(
                                "Gmail から確認番号を取得するには google-api-python-client / google-auth 等が必要です。"
                                f" finance の venv にインストールしてください。（{exc}）"
                            ) from exc
                        otp_code = poll_prudential_otp_from_gmail(
                            to_email=username,
                            min_internal_date_ms=gmail_min_internal_ms,
                        )
                    finally:
                        if prev_token:
                            os.environ["PRUDENTIAL_GMAIL_TOKEN_PATH"] = prev_token
                        else:
                            os.environ.pop("PRUDENTIAL_GMAIL_TOKEN_PATH", None)
                        if prev_expect:
                            os.environ["PRUDENTIAL_GMAIL_EXPECT_EMAIL"] = prev_expect
                        else:
                            os.environ.pop("PRUDENTIAL_GMAIL_EXPECT_EMAIL", None)
                if not otp_code:
                    _save_prudential_otp_checkpoint(
                        context,
                        page,
                        username=username,
                        account_no=account_no,
                        login_submit_ms=login_submit_ms,
                    )
                    if sys.stdin.isatty():
                        print(
                            "Gmail から確認番号を取得できませんでした。"
                            "ブラウザは確認番号入力画面のままです（ログインからやり直していません）。",
                            file=sys.stderr,
                        )
                        try:
                            otp_code = input("確認番号（6桁）を入力して Enter: ").strip()
                        except EOFError:
                            otp_code = ""
                    if not otp_code:
                        acct = f"（このときはアカウント{account_no}用の番号）" if account_no > 1 else ""
                        raise RuntimeError(
                            "プルデンシャル生命のログインに確認番号が必要です。"
                            f"{acct}\n"
                            "セッションは確認番号画面のまま保存済みです。"
                            "【重要】ログインからやり直さず、同じ確認番号で続行するには:\n"
                            "  `run_prudential_life_step5.py --resume-otp --otp-code 6桁`\n"
                            "  または `run_lifeplan_checks.py --prudential-resume-otp --prudential-otp-code 6桁`\n"
                            "（`--otp-code` だけで再実行するとログインが最初からになり、別の確認番号が必要になります。）\n"
                            "【Cursor 経由】メールで番号を確認したら、上記の `--resume-otp` 付きで再実行してください。\n"
                            "【Gmail 自動取得】既定でオン（`PRUDENTIAL_FETCH_OTP_FROM_GMAIL=0` でオフ）。"
                            "215 の Gmail token・readonly スコープが必要。\n"
                            "【代替】一時的に `PRUDENTIAL_OTP_CODE`"
                            + (f" / `PRUDENTIAL_OTP_CODE_{account_no}`" if account_no > 1 else "")
                            + " を .env に入れても構いません。"
                            " 入力欄が見つからないときは `PRUDENTIAL_OTP_SELECTOR` / "
                            "`PRUDENTIAL_OTP_SUBMIT_SELECTOR` の設定も確認してください。"
                        )
                filled = False
                if otp_selector and page.locator(otp_selector).count() > 0:
                    n_otp = page.locator(otp_selector).count()
                    for ii in range(min(n_otp, 15)):
                        cand = page.locator(otp_selector).nth(ii)
                        try:
                            if not cand.is_visible():
                                continue
                        except Exception:
                            continue
                        if _is_probable_prudential_login_id_input(cand):
                            continue
                        if _fill_otp_field_lightning_compat(cand, otp_code, timeout_ms):
                            filled = True
                            break
                else:
                    filled = _fill_prudential_otp_generic(page, otp_code, timeout_ms)
                if not filled:
                    raise RuntimeError(
                        "確認番号を入力できませんでした。"
                        "ログイン ID 欄（input[id^='input-'] 等）と誤認識しないよう、"
                        "PRUDENTIAL_OTP_SELECTOR には確認番号専用（例: input[id^='confirmNumber']）だけを指定してください。"
                        "PRUDENTIAL_USERNAME_SELECTOR と同じセレクタにしないでください。"
                    )
                _prudential_try_check_trusted_device(page, timeout_ms)
                if pause_before_otp_submit_eff:
                    DEFAULT_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                    dbg_html = (
                        DEFAULT_DEBUG_DIR / f"prudential_otp_pause_before_submit_account{account_no}.html"
                    )
                    dbg_png = (
                        DEFAULT_DEBUG_DIR / f"prudential_otp_pause_before_submit_account{account_no}.png"
                    )
                    try:
                        dbg_html.write_text(page.content(), encoding="utf-8")
                        page.screenshot(path=str(dbg_png), full_page=True)
                    except Exception:
                        pass
                    print(
                        "⏸ 確認番号を入力しました。「次へ」は自動では押しません。"
                        f" 保存: {dbg_html.name} / {dbg_png.name}",
                        file=sys.stderr,
                    )
                    if not headless:
                        print(
                            "   ブラウザで「次へ」周りを確認してください。"
                            " Playwright Inspector が開いたら Resume で終了します。",
                            file=sys.stderr,
                        )
                        try:
                            page.pause()
                        except Exception as exc:
                            print(f"🐞 page.pause 不可: {exc}", file=sys.stderr)
                    elif sys.stdin.isatty():
                        try:
                            input("確認が終わったら Enter で終了… ")
                        except EOFError:
                            pass
                    else:
                        wait_ms = _env_int_nonneg(
                            "PRUDENTIAL_OTP_PAUSE_WAIT_MS", 30 * 60 * 1000
                        )
                        print(
                            f"⚠ ヘッドレス・非TTYのため {wait_ms // 1000}s 待機後に終了します。",
                            file=sys.stderr,
                        )
                        _sleep_ms(page, wait_ms)
                    browser.close()
                    raise PrudentialOtpPausedBeforeSubmit(
                        "確認番号まで入力し、「次へ」送信前で停止しました（PRUDENTIAL_OTP_PAUSE_BEFORE_SUBMIT）。"
                        " 解約返戻金は未取得です。"
                    )
                if _env_yesno_or_default("PRUDENTIAL_OTP_PRESS_ENTER_AFTER_FILL", default=True):
                    _try_press_enter_on_otp_field(page, otp_selector, timeout_ms)
                    _sleep_ms(page, min(2000, max(500, after_otp_anim_ms // 6)))
                clicked_submit = False
                if otp_submit_selector:
                    try:
                        loc = page.locator(otp_submit_selector)
                        n = loc.count()
                        if n > 0:
                            # ページ内に m-btn-primary が複数あると first がヘッダ等を掴むことがあるため、
                            # 末尾から可視要素を探してクリックする。
                            for i in range(n - 1, -1, -1):
                                cand = loc.nth(i)
                                try:
                                    cand.wait_for(state="visible", timeout=min(20000, max(5000, timeout_ms)))
                                    cand.scroll_into_view_if_needed(timeout=8000)
                                    cand.click(timeout=timeout_ms)
                                    clicked_submit = True
                                    break
                                except Exception:
                                    continue
                    except Exception:
                        print(
                            "🐞 PRUDENTIAL_OTP_SUBMIT_SELECTOR のクリックに失敗。OTP 画面用フォールバックを試します。",
                            file=sys.stderr,
                        )
                if not clicked_submit:
                    try:
                        detail = page.locator("c-mypg-otp-customer-info-detail").first
                        detail.wait_for(state="visible", timeout=12000)
                        nxt = detail.get_by_role("button", name=re.compile(r"^\s*次へ\s*$"))
                        if nxt.count() > 0:
                            nn = nxt.count()
                            for i in range(nn - 1, -1, -1):
                                btn = nxt.nth(i)
                                try:
                                    if not btn.is_visible():
                                        continue
                                    btn.scroll_into_view_if_needed(timeout=8000)
                                    btn.click(timeout=timeout_ms)
                                    clicked_submit = True
                                    break
                                except Exception:
                                    continue
                    except Exception:
                        pass
                if not clicked_submit:
                    # さらに厳密に OTP 入力欄へスコープした「次へ」を試す
                    try:
                        if _click_prudential_otp_next_scoped(page, timeout_ms=min(timeout_ms, 25000)):
                            clicked_submit = True
                    except Exception:
                        pass
                if not clicked_submit:
                    for alt in (
                        "c-mypg-otp-customer-info-detail button.m-btn.m-btn-primary",
                        "c-mypg-otp-customer-info-detail button.m-btn",
                        "c-mypg-guest-view c-mypg-otp-customer-info-detail button.m-btn.m-btn-primary",
                    ):
                        try:
                            al = page.locator(alt)
                            if al.count() <= 0:
                                continue
                            nn = al.count()
                            for i in range(nn - 1, -1, -1):
                                btn = al.nth(i)
                                try:
                                    if not btn.is_visible():
                                        continue
                                    btn.scroll_into_view_if_needed(timeout=8000)
                                    btn.click(timeout=timeout_ms)
                                    clicked_submit = True
                                    break
                                except Exception:
                                    continue
                            if clicked_submit:
                                break
                        except Exception:
                            continue
                if not clicked_submit:
                    # ログイン枠（PRUDENTIAL_LOGIN_FORM_HOST_SELECTOR）内の lightning-button を誤って押すと
                    # OTP 送信ではなくログイン送信扱いになり、ゲスト画面に戻ることがあるため、
                    # まずはゲストビュー内の「次へ」を優先する。
                    try:
                        gv = page.locator("c-mypg-guest-view").first
                        gv.wait_for(state="visible", timeout=8000)
                        if _click_last_role_button_by_text_in_frame(
                            gv, "次へ", timeout_ms=min(timeout_ms, 25000)
                        ):
                            clicked_submit = True
                    except Exception:
                        pass
                if not clicked_submit:
                    if not _click_prudential_otp_submit_generic(page, timeout_ms):
                        raise RuntimeError(
                            "確認番号の送信ボタンが見つかりません。"
                            "PRUDENTIAL_OTP_SUBMIT_SELECTOR を設定するか、画面のボタン文言を確認してください。"
                        )
                _wait_page_ready(page, timeout_ms)
                # OTP 送信直後の画面を残す（「ログインに戻る」「エラー表示のまま」等の切り分け用）
                if save_debug:
                    try:
                        DEFAULT_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                        html = DEFAULT_DEBUG_DIR / f"prudential_otp_after_submit_account{account_no}.html"
                        png = DEFAULT_DEBUG_DIR / f"prudential_otp_after_submit_account{account_no}.png"
                        html.write_text(page.content(), encoding="utf-8")
                        page.screenshot(path=str(png), full_page=True)
                    except Exception:
                        pass
                # OTP 通過後の「マイページ」アニメーション・本体描画待ち
                _sleep_ms(page, after_otp_anim_ms)

            if _page_still_matches_login_hint(page):
                raise RuntimeError(
                    "ログイン後もログインURL相当のままです。"
                    "ID・パスワードを確認するか、PRUDENTIAL_LOGIN_STILL_URL_SUBSTR を見直し、"
                    "追加認証が必要なら PRUDENTIAL_OTP_* を設定してください。"
                )

            top_wait = int(
                os.environ.get(
                    "PRUDENTIAL_MYPAGE_TOP_WAIT_MS",
                    str(min(25000, max(8000, timeout_ms // 2))),
                )
                or str(min(25000, max(8000, timeout_ms // 2)))
            )
            if not _prudential_authenticated_top_ready(page, timeout_ms=top_wait):
                if _prudential_guest_shell_visible(page):
                    try:
                        dbg = DEFAULT_DEBUG_DIR / f"prudential_otp_guest_fail_account{account_no}.html"
                        DEFAULT_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                        dbg.write_text(page.content(), encoding="utf-8")
                        try:
                            png = DEFAULT_DEBUG_DIR / f"prudential_otp_guest_fail_account{account_no}.png"
                            page.screenshot(path=str(png), full_page=True)
                        except Exception:
                            pass
                        print(
                            f"🐞 ゲスト画面のまま終了: {dbg.name} を保存しました（送信ボタン・入力欄の切り分け用）。",
                            file=sys.stderr,
                        )
                    except Exception:
                        pass
                    raise RuntimeError(
                        "ログイン送信後もゲスト（ログイン）画面のままです。"
                        "マイページに入れていない状態で「契約内容」を探していると、このエラーに見えます。\n"
                        "【よくある原因】"
                        " (1) `--resume-otp` で復元したセッションと、別のログインで届いた確認番号を組み合わせている。"
                        " 確認番号は「そのログイン操作の直後」に届いたものだけ有効です。"
                        " いったん通常実行でログインし直し、同じ実行内で Gmail／--otp-code を使うか、"
                        " 保存直後に --resume-otp で続行してください。\n"
                        " (2) 画面に「次へ」が複数あり、誤ってクリックしている → コード側で最後のボタンを優先するよう修正済み。\n"
                        " (3) 確認番号の入力・送信失敗・期限切れ・誤り → PRUDENTIAL_OTP_SELECTOR / "
                        "PRUDENTIAL_OTP_SUBMIT_SELECTOR を確認するか、"
                        " PRUDENTIAL_OTP_PRESS_ENTER_AFTER_FILL=0 で Enter 補助をオフにして試す。"
                    )
                try:
                    dbg_top = DEFAULT_DEBUG_DIR / f"prudential_mypage_top_timeout_account{account_no}.html"
                    DEFAULT_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                    dbg_top.write_text(page.content(), encoding="utf-8")
                    print(
                        f"🐞 認証後トップが未表示: {dbg_top.name} を保存しました（OTP 後の画面確認用）。",
                        file=sys.stderr,
                    )
                except Exception:
                    pass
                raise RuntimeError(
                    "認証後トップ（c-mypg-top-detail）が表示されませんでした。"
                    " PRUDENTIAL_POST_LOGIN_ANIMATION_MS / PRUDENTIAL_AFTER_OTP_ANIMATION_MS を伸ばす、"
                    "またはヘッドレスを外して表示を確認してください。"
                )

            try:
                _navigate_after_login_prudential(page, timeout_ms)
            except Exception:
                DEFAULT_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                fail_html = DEFAULT_DEBUG_DIR / f"prudential_life_nav_fail_account{account_no}.html"
                try:
                    fail_html.write_text(page.content(), encoding="utf-8")
                except Exception:
                    pass
                raise

            value, value_text, mode = _extract_surrender_from_page(
                page,
                value_selector=value_selector,
                value_label=value_label,
                row_th_contains=row_th_contains,
                reference_label=reference_label,
            )

            if save_debug:
                DEFAULT_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                html_path = DEFAULT_DEBUG_DIR / f"prudential_life_last_page_account{account_no}.html"
                png_path = DEFAULT_DEBUG_DIR / f"prudential_life_last_page_account{account_no}.png"
                html_path.write_text(page.content(), encoding="utf-8")
                page.screenshot(path=str(png_path), full_page=True)

            source_url = page.url

            if value is None:
                try:
                    context.close()
                except Exception:
                    pass
                raise RuntimeError(
                    f"アカウント{account_no}（{username}）で解約返戻金を抽出できませんでした。"
                    "PRUDENTIAL_SURRENDER_VALUE_SELECTOR / PRUDENTIAL_SURRENDER_ROW_TH_CONTAINS / "
                    f"LABEL を見直し、debug/prudential_life_last_page_account{account_no}.html を確認してください。"
                )

            items.append(
                PrudentialSurrenderAccountResult(
                    account_index=account_no,
                    username=username,
                    value_jpy=value,
                    value_text=value_text or f"{value:,}円",
                    source_url=source_url,
                    parser_mode=mode,
                )
            )
            try:
                context.close()
            except Exception:
                pass

        browser.close()

    total = sum(x.value_jpy for x in items)
    lines = [f"アカウント{x.account_index}（{x.username}）: {x.value_text}" for x in items]
    combined_text = "\n".join(lines) + f"\n合計: {total:,}円"
    parser_mode = f"multi:{len(items)}accounts"
    last_url = items[-1].source_url if items else ""

    return PrudentialSurrenderValueResult(
        items=items,
        value_jpy=total,
        value_text=combined_text,
        source_url=last_url,
        parser_mode=parser_mode,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="プルデンシャル生命の解約返戻金を取得")
    parser.add_argument("--headless", action="store_true", help="ヘッドレスで実行する")
    parser.add_argument("--timeout-ms", type=int, default=45000, help="Playwright タイムアウト（ms）")
    parser.add_argument("--save-debug", action="store_true", help="最終ページのHTML/PNGを保存")
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_PATH),
        help="環境変数ファイル（既定: finance/.env.lifeplan）",
    )
    parser.add_argument(
        "--otp-code",
        default="",
        help="確認番号（1人目）。メール確認後にチャットで受け取った番号を渡すか、対話プロンプトで入力。2人目は PRUDENTIAL_OTP_CODE_2 等",
    )
    parser.add_argument(
        "--fetch-otp-gmail",
        action="store_true",
        help="Gmail から確認番号を取得（既定でオン・明示的に有効化する用途）",
    )
    parser.add_argument(
        "--no-fetch-otp-gmail",
        action="store_true",
        help="Gmail から確認番号を取得しない（PRUDENTIAL_FETCH_OTP_FROM_GMAIL=0 と同効）",
    )
    parser.add_argument(
        "--login-submit-debug",
        action="store_true",
        help="ログイン送信直後に debug/ に HTML・PNG を保存（PRUDENTIAL_DEBUG_LOGIN_SUBMIT と同効）",
    )
    parser.add_argument(
        "--dump-login-form-fail",
        action="store_true",
        help="ログイン入力欄が見つからないとき（ID/PW の fill より前）に debug/ へ HTML・PNG を保存",
    )
    parser.add_argument(
        "--pause-before-login-sec",
        type=int,
        default=None,
        metavar="SEC",
        help="ログイン欄探索の直前に SEC 秒待つ（セレクタ確認用・PRUDENTIAL_DEBUG_PAUSE_BEFORE_LOGIN_MS より優先）",
    )
    parser.add_argument(
        "--pause-on-login-fail-sec",
        type=int,
        default=None,
        metavar="SEC",
        help="入力欄未検出で失敗した直後に SEC 秒待つ（ダンプ後・ブラウザが閉じる前）",
    )
    parser.add_argument(
        "--resume-otp",
        action="store_true",
        help="保存済みセッションで確認番号画面から再開（ログインを繰り返さない。--otp-code と併用可）",
    )
    parser.add_argument(
        "--pause-before-otp-submit",
        action="store_true",
        help="確認番号入力後に「次へ」を押さず停止（目視・セレクタ確認。PRUDENTIAL_OTP_PAUSE_BEFORE_SUBMIT と同効）",
    )
    parser.add_argument(
        "--pause-at-otp-screen",
        action="store_true",
        help="確認番号入力画面到達直後に停止（Gmail・入力の前。PRUDENTIAL_OTP_PAUSE_AT_SCREEN と同効）",
    )
    parser.add_argument("--json", action="store_true", help="JSONで結果を出力する")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.fetch_otp_gmail and args.no_fetch_otp_gmail:
        print("--fetch-otp-gmail と --no-fetch-otp-gmail は同時に指定できません。", file=sys.stderr)
        return 2
    if args.no_fetch_otp_gmail:
        fetch_otp_arg: bool | None = False
    elif args.fetch_otp_gmail:
        fetch_otp_arg = True
    else:
        fetch_otp_arg = None
    try:
        result = fetch_prudential_surrender_value(
            headless=args.headless,
            timeout_ms=args.timeout_ms,
            save_debug=args.save_debug,
            env_file=Path(args.env_file).expanduser(),
            otp_code_override=(args.otp_code or "").strip() or None,
            fetch_otp_from_gmail=fetch_otp_arg,
            debug_login_submit=True if args.login_submit_debug else None,
            debug_login_form_fail=True if args.dump_login_form_fail else None,
            pause_before_login_ms=args.pause_before_login_sec * 1000
            if args.pause_before_login_sec is not None
            else None,
            pause_on_login_form_fail_ms=args.pause_on_login_fail_sec * 1000
            if args.pause_on_login_fail_sec is not None
            else None,
            resume_otp_only=True if args.resume_otp else None,
            otp_pause_before_submit=True if args.pause_before_otp_submit else None,
            otp_pause_at_screen=True if args.pause_at_otp_screen else None,
        )
    except PlaywrightTimeoutError as exc:
        print(f"タイムアウト: {exc}", file=sys.stderr)
        return 1
    except PrudentialOtpPausedAtScreen as exc:
        print(str(exc), file=sys.stderr)
        return 0
    except PrudentialOtpPausedBeforeSubmit as exc:
        print(str(exc), file=sys.stderr)
        return 0
    except PrudentialPausedAtContractList as exc:
        print(str(exc), file=sys.stderr)
        return 0
    except Exception as exc:
        print(f"取得失敗: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "value_jpy": result.value_jpy,
                    "value_text": result.value_text,
                    "source_url": result.source_url,
                    "parser_mode": result.parser_mode,
                    "items": [asdict(x) for x in result.items],
                },
                ensure_ascii=False,
            )
        )
    else:
        print(f"解約返戻金 合計: {result.value_jpy:,}円")
        for x in result.items:
            print(f"  - アカウント{x.account_index}（{x.username}）: {x.value_jpy:,}円")
        print(result.value_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
