#!/usr/bin/env python3
"""
Zaim 連携設定ページ（口座一覧）から、各口座の「最終更新」とエラー表示を読む（読み取り専用）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_zaim_online_accounts.py --fetch --headless
  ~/selenium_env/venv/bin/python scripts/jarvis_zaim_online_accounts.py --from-html <保存したHTML>
  ~/selenium_env/venv/bin/python scripts/jarvis_zaim_online_accounts.py --status

守ること:
- 画面を開いて読むだけ。「連携データを更新」など、押す操作は一切しない。
- ログインは既存の仕組み（zaim_budget_apply.ensure_logged_in・storage_state）。認証情報は出力しない。
- OTP・画像認証・追加認証の画面が出たら止める（status=auth_blocked）。
- 取った HTML は .jarvis_state/zaim_online_accounts/（非公開・gitignore 済み）にだけ置く。
- 結果は .jarvis_state/zaim_online_accounts.json。jarvis_zaim_bank_sync_check.py が読む。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
ZAIM_DIR = REPO / "215_kamiooya" / "C1_cursor" / "finance" / "zaim_budget_sync"
STATE_DIR = REPO / ".jarvis_state"
SNAPSHOT_PATH = STATE_DIR / "zaim_online_accounts.json"
HTML_DIR = STATE_DIR / "zaim_online_accounts"
ONLINE_URL = "https://zaim.net/online_accounts"
LOG_DIR = Path.home() / "Library" / "Logs" / "jarvis_zaim"
# CSV 週次・銀行更新と共有（同時 Playwright でセッション破壊しない）
PLAYWRIGHT_LOCK = LOG_DIR / "zaim_playwright.lock"

# 認証の壁（出たら止める。値は読まない）
AUTH_MARKERS = (
    "ワンタイム",
    "認証コード",
    "確認コード",
    "セキュリティコード",
    "画像認証",
    "追加認証",
    "本人確認",
)

# 注意文のうち「ログインし直しが要る」類
REAUTH_WORDS = ("ログイン", "再認証", "有効期限", "パスワード", "認証")

_UPDATED_RE = re.compile(
    r"最終更新[:：]\s*(\d{4})年(\d{1,2})月(\d{1,2})日\s+(\d{1,2}):(\d{2})(?::(\d{2}))?"
)
_CLASS_KEY_RE = re.compile(r"OnlineAccount(Summary|StatusBar)-module__([A-Za-z]+)___")
_VOID_TAGS = {"br", "img", "input", "meta", "link", "hr", "source", "wbr", "area", "base", "col"}


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def parse_updated(text: str) -> tuple[str | None, bool]:
    """『最終更新：2026年11月25日 09:51:49（自動取得非対応）』→ (JST の ISO, 自動取得非対応か)。"""
    m = _UPDATED_RE.search(text or "")
    if not m:
        return None, "自動取得非対応" in (text or "")
    y, mo, d, h, mi, s = m.groups()
    dt = datetime(int(y), int(mo), int(d), int(h), int(mi), int(s or 0), tzinfo=JST)
    return dt.strftime("%Y-%m-%dT%H:%M:%S%z"), "自動取得非対応" in (text or "")


class _Parser(HTMLParser):
    """口座行（td.name）ごとに、クラス名ごとの文字列を集める。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, str | None]] = []  # (tag, capture key)
        self.group: str | None = None
        self.cur: dict[str, str] | None = None
        self.cur_group: str | None = None
        self.rows: list[dict[str, Any]] = []
        self._buf: dict[int, list[str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _VOID_TAGS:
            return
        cls = dict(attrs).get("class") or ""
        key = None
        m = _CLASS_KEY_RE.search(cls)
        if m:
            kind, name = m.groups()
            if kind == "Summary" and name == "name":
                self.cur = {}
                self.cur_group = self.group
            key = f"{kind}.{name}"
        self.stack.append((tag, key))
        if key:
            self._buf[len(self.stack)] = []

    def handle_data(self, data: str) -> None:
        for depth in self._buf:
            self._buf[depth].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID_TAGS or not self.stack:
            return
        while self.stack and self.stack[-1][0] != tag:
            self._close_top()
        if self.stack:
            self._close_top()

    def _close_top(self) -> None:
        depth = len(self.stack)
        _tag, key = self.stack.pop()
        if not key:
            return
        text = re.sub(r"\s+", " ", "".join(self._buf.pop(depth, []))).strip()
        if key == "StatusBar.title":
            self.group = text or None
        elif key == "Summary.name":
            if self.cur is not None:
                self.rows.append({"_f": self.cur, "group": self.cur_group})
            self.cur = None
        elif key.startswith("Summary.") and self.cur is not None and text:
            name = key.split(".", 1)[1]
            # 同じ名前が複数回出るもの（faqLink 等）は先勝ち
            self.cur.setdefault(name, text)


def parse_online_accounts_html(html: str) -> list[dict[str, Any]]:
    """口座一覧の HTML → 口座ごとの dict。ページ構造が読めなければ空リスト。

    返す値: website（サービス名）, account（口座名）, last_updated（JST の ISO か None）,
    auto_unsupported, notice（エラー・注意の文言か None）, group（Zaim の更新区分）,
    periodic_only（『定期更新のみ』表示）, link_broken（『連携できない』表示）。
    """
    p = _Parser()
    p.feed(html or "")
    p.close()
    out: list[dict[str, Any]] = []
    for r in p.rows:
        f = r["_f"]
        website = f.get("websiteName") or ""
        account = f.get("accountName") or ""
        if not website and not account:
            continue
        last_updated, auto_unsupported = parse_updated(f.get("textMuted") or "")
        out.append(
            {
                "website": website,
                "account": account,
                "last_updated": last_updated,
                "auto_unsupported": auto_unsupported,
                "notice": f.get("textNotice") or None,
                "group": r.get("group"),
                "periodic_only": "定期更新のみ" in (f.get("caution") or ""),
                "link_broken": "連携できない" in (f.get("faqLink") or ""),
            }
        )
    return out


def _norm_name(s: str) -> str:
    """★・空白（全角含む）を除く。CSV 側の口座名と Zaim 画面の口座名の表記ゆれを吸収する。"""
    return re.sub(r"[★☆\s]+", "", s or "")


def match_online_account(
    needles: str | list[str], accounts: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """YAML の match / online_match に合う口座を一覧から探す。複数なら最終更新が新しいもの。

    口座名・サービス名のどちらかに、★と空白を除いた形で部分一致すれば採る。
    """
    if isinstance(needles, str):
        needles = [needles]
    keys = [_norm_name(n) for n in needles if n and _norm_name(n)]
    if not keys:
        return None
    hits = [
        a
        for a in accounts
        if any(k in _norm_name(a.get("account") or "") or k in _norm_name(a.get("website") or "") for k in keys)
    ]
    if not hits:
        return None
    hits.sort(key=lambda a: a.get("last_updated") or "", reverse=True)
    return hits[0]


def has_zaim_error(row: dict[str, Any]) -> bool:
    """Zaim 画面がエラー・要対応を示しているか（注意文・『連携できない』・『更新再開の操作待ち』）。"""
    return bool(row.get("notice")) or bool(row.get("link_broken")) or row.get("group") == "更新再開の操作待ち"


def is_reauth_notice(notice: str | None) -> bool:
    return bool(notice) and any(w in str(notice) for w in REAUTH_WORDS)


# ---- 保存・読み込み ----------------------------------------------------------------


def build_snapshot(accounts: list[dict[str, Any]], *, fetched_at: str | None = None) -> dict[str, Any]:
    if not accounts:
        return {
            "status": "parse_empty",
            "fetched_at": fetched_at or now_iso(),
            "reason": "口座一覧を読めなかった（画面の作りが変わった可能性）",
            "accounts": [],
        }
    return {
        "status": "ok",
        "fetched_at": fetched_at or now_iso(),
        "accounts": accounts,
    }


def load_snapshot(path: Path = SNAPSHOT_PATH) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_snapshot(snap: dict[str, Any], path: Path = SNAPSHOT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def snapshot_usable(
    snap: dict[str, Any], *, max_age_days: float, now: datetime | None = None
) -> tuple[bool, str]:
    """スナップショットを判定に使ってよいか。使えない理由は短い語で返す。"""
    if not snap:
        return False, "未取得"
    if snap.get("status") != "ok":
        return False, str(snap.get("status") or "不明")
    fetched = snap.get("fetched_at")
    try:
        dt = datetime.fromisoformat(str(fetched).replace("+0900", "+09:00"))
    except ValueError:
        return False, "取得時刻が読めない"
    now = now or datetime.now(JST)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    age = (now - dt).total_seconds() / 86400
    if age > max_age_days:
        return False, f"{int(age)}日前の取得（古い）"
    return True, "ok"


# ---- 実画面（読み取り専用）-----------------------------------------------------------


def acquire_playwright_lock(*, wait_sec: int = 0) -> bool:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + max(0, wait_sec)
    while True:
        try:
            os.mkdir(PLAYWRIGHT_LOCK)
            (PLAYWRIGHT_LOCK / "owner.txt").write_text(
                f"online_accounts pid={os.getpid()} at={now_iso()}\n", encoding="utf-8"
            )
            return True
        except FileExistsError:
            if time.time() >= deadline:
                return False
            time.sleep(2)


def release_playwright_lock() -> None:
    try:
        for p in PLAYWRIGHT_LOCK.iterdir():
            p.unlink(missing_ok=True)
    except Exception:
        pass
    try:
        PLAYWRIGHT_LOCK.rmdir()
    except Exception:
        pass


def fetch_html(*, headless: bool) -> tuple[str | None, dict[str, Any]]:
    """口座一覧を開いて HTML を返す。押す操作はしない。失敗時は (None, {status, reason})。"""
    sys.path.insert(0, str(ZAIM_DIR))
    import zaim_budget_apply as zaim  # noqa: E402
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        try:
            kwargs: dict[str, Any] = {}
            if zaim.STORAGE_STATE.is_file():
                kwargs["storage_state"] = str(zaim.STORAGE_STATE)
            ctx = browser.new_context(**kwargs)
            page = ctx.new_page()
            try:
                zaim.ensure_logged_in(
                    page,
                    email=zaim.DEFAULT_LOGIN_EMAIL,
                    password=zaim.DEFAULT_LOGIN_PASSWORD,
                    google_email=zaim.DEFAULT_GOOGLE_EMAIL,
                    login_method="email",
                    manual=False,
                )
            except Exception as exc:
                body = ""
                try:
                    body = page.inner_text("body", timeout=3000)
                except Exception:
                    pass
                if any(m in body for m in AUTH_MARKERS):
                    return None, {"status": "auth_blocked", "reason": "追加認証の画面が出た（ここで止めた）"}
                return None, {"status": "login_failed", "reason": type(exc).__name__}
            zaim.save_storage_state(ctx)
            page.goto(ONLINE_URL, wait_until="networkidle", timeout=90_000)
            page.wait_for_timeout(3000)
            if zaim.is_login_page(page):
                return None, {"status": "login_failed", "reason": "口座一覧でログイン画面に戻された"}
            return page.content(), {"status": "ok"}
        finally:
            browser.close()


def cmd_fetch(args: argparse.Namespace) -> int:
    if not acquire_playwright_lock(wait_sec=args.lock_wait):
        snap = {
            "status": "lock_busy",
            "fetched_at": now_iso(),
            "reason": "別の Zaim 画面作業が実行中",
            "accounts": [],
        }
        # 前回の成功分は残す（ロック待ちで落ちただけで、前の結果を消さない）
        prev = load_snapshot()
        if prev.get("status") == "ok":
            print("# lock busy: 前回のスナップショットを残す", file=sys.stderr)
            print(json.dumps({"ok": False, "status": "lock_busy"}, ensure_ascii=False))
            return 4
        save_snapshot(snap)
        print(json.dumps({"ok": False, "status": "lock_busy"}, ensure_ascii=False))
        return 4
    try:
        html, info = fetch_html(headless=args.headless)
    except Exception as exc:  # Playwright の起動失敗など
        html, info = None, {"status": "fetch_error", "reason": type(exc).__name__}
    finally:
        release_playwright_lock()

    if html is None:
        # 取れなかった。前回の成功分は残し、失敗の事実だけ別に残す
        prev = load_snapshot()
        record = {**info, "fetched_at": now_iso(), "accounts": []}
        if prev.get("status") == "ok":
            prev["last_failed"] = {"at": record["fetched_at"], **info}
            save_snapshot(prev)
        else:
            save_snapshot(record)
        print(json.dumps({"ok": False, **info}, ensure_ascii=False))
        return 3 if info.get("status") == "auth_blocked" else 1

    HTML_DIR.mkdir(parents=True, exist_ok=True)
    (HTML_DIR / "online_accounts_latest.html").write_text(html, encoding="utf-8")
    accounts = parse_online_accounts_html(html)
    snap = build_snapshot(accounts)
    save_snapshot(snap)
    print(
        json.dumps(
            {"ok": snap["status"] == "ok", "status": snap["status"], "accounts": len(accounts)},
            ensure_ascii=False,
        )
    )
    return 0 if snap["status"] == "ok" else 1


def cmd_from_html(args: argparse.Namespace) -> int:
    html = Path(args.from_html).read_text(encoding="utf-8")
    accounts = parse_online_accounts_html(html)
    snap = build_snapshot(accounts)
    if args.write:
        save_snapshot(snap)
    print(
        json.dumps(
            {"ok": snap["status"] == "ok", "status": snap["status"], "accounts": len(accounts)},
            ensure_ascii=False,
        )
    )
    return 0 if snap["status"] == "ok" else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Zaim 口座一覧の最終更新・エラー表示を読む（読み取り専用）")
    ap.add_argument("--fetch", action="store_true", help="実画面を開いて読む（押す操作なし）")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--lock-wait", type=int, default=0, help="Playwright 共有ロック待ち秒")
    ap.add_argument("--from-html", default="", help="保存済み HTML を読む（画面を開かない）")
    ap.add_argument("--write", action="store_true", help="--from-html の結果を state に書く")
    ap.add_argument("--status", action="store_true", help="保存済みの要約だけ表示（口座名は出さない）")
    args = ap.parse_args(argv)

    if args.status:
        snap = load_snapshot()
        print(
            json.dumps(
                {
                    "status": snap.get("status"),
                    "fetched_at": snap.get("fetched_at"),
                    "accounts": len(snap.get("accounts") or []),
                    "last_failed": snap.get("last_failed"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.from_html:
        return cmd_from_html(args)
    if args.fetch:
        return cmd_fetch(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())


def is_automation_off(acc: dict[str, Any] | None) -> bool:
    """automation: off の判定。YAML では off が False として読まれるので、それも「オフ」とみなす。
    キー自体が無い（None）ときはオフではない。"""
    if not acc:
        return False
    v = acc.get("automation")
    if v is None:
        return False
    return v is False or str(v).strip().lower() in ("off", "false", "0", "no")
