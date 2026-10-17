#!/usr/bin/env python3
"""311 送信前品質ゲート — 下書き1件の機械点検（LLMなし）。

経路B: --draft PATH --source s9|211|hawk|s2|manual
経路A: --from-inbox [DIR]（input/*.md を処理して processed/ へ）
  README.md / example_* はスキップ。既定は未処理をすべて（--limit で上限）
上流キック: --enqueue --draft PATH --source …（input/ に依頼 MD を書く）

  ~/selenium_env/venv/bin/python scripts/jarvis_send_gate_311.py \\
    --draft '/path/to/4.送信下書き.txt' --source manual --dry-run
  … --post   # Slack #report(OK件数) / #consult(NG理由)
  … --from-inbox --post
  … --enqueue --draft PATH --source 211

秘密は .env.jarvis_private。チャットに出さない。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
AGENT_DIR = (
    REPO
    / "docs"
    / "AIエージェントチーム"
    / "300_品質・タスク運用管理室"
    / "311_送信前品質係"
)
DEFAULT_INBOX = AGENT_DIR / "input"
DEFAULT_CONFIG = AGENT_DIR / "config" / "banned_patterns.yaml"
CONTACT_YAML = Path(
    "/Users/matsunomasaharu2/Library/CloudStorage/OneDrive-個人用"
    "/215_神・大家さん倶楽部/C2_ルーティン作業/26_パートナー社への相談"
    "/000_共通/連絡先一覧.yaml"
)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
HEADER_TO = re.compile(
    r"(?im)^(?:To|Cc|Bcc|宛先|TO|CC|BCC)\s*[:：]\s*(.+)$"
)
HEADER_FROM = re.compile(
    r"(?im)^(?:From|Reply-To|送信者|返信先)\s*[:：]\s*(.+)$"
)
LINE_DEST = re.compile(r"(?im)^宛先\s*[:：]\s*(.+)$")
# パス区切り付き（215_神大家… 等の親フォルダ誤検出を防ぐ）
FOLDER_RE = re.compile(r"[/\\](?P<code>\d{3}_[^/\\]+)[/\\]")


@dataclass
class CheckResult:
    ok: bool
    code: str
    detail: str


@dataclass
class GateResult:
    draft_path: str
    source: str
    overall: str  # OK | NG
    reason: str
    checks: list[CheckResult] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


def _load_env() -> None:
    env_path = REPO / ".env.jarvis_private"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        print("⚠ PyYAML が必要です（selenium_env venv）", file=sys.stderr)
        return {}
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _partner_from_path(draft: Path) -> dict[str, Any] | None:
    data = _load_yaml(CONTACT_YAML)
    partners = [p for p in (data.get("partners") or []) if isinstance(p, dict)]
    known = {str(p.get("folder") or ""): p for p in partners if p.get("folder")}
    candidates = [m.group("code") for m in FOLDER_RE.finditer(str(draft))]
    for folder in candidates:
        if folder in known:
            return known[folder]
    # 連絡先未登録でも三桁フォルダらしきものがあればメモだけ返す
    for folder in candidates:
        if folder.startswith(("1", "2", "3", "5", "6", "7", "8", "9")):
            return {"folder": folder, "name": folder, "emails": [], "line": ""}
    return None


def _list_inbox_mds(inbox: Path) -> list[Path]:
    """未処理の依頼MD。README / example_* はサンプルなのでスキップ。"""
    out: list[Path] = []
    for p in sorted(inbox.glob("*.md"), key=lambda x: x.stat().st_mtime):
        name = p.name.lower()
        if name == "readme.md":
            continue
        if name.startswith("example"):
            continue
        out.append(p)
    return out


def _partner_hint_from_path(draft: Path) -> str:
    """パス中の三桁フォルダ。親の 215_神大家… より深い側（103_Tcell 等）を優先。"""
    codes = [m.group("code") for m in FOLDER_RE.finditer(str(draft))]
    if not codes:
        return draft.parent.name if draft.parent.name else ""
    # 末尾がパートナー本線（26_配下）であることが多い
    return codes[-1]


def enqueue_request(
    draft_path: Path | str,
    *,
    source: str = "manual",
    partner_or_thread: str = "",
    inbox: Path | None = None,
    note: str = "",
) -> Path:
    """経路A: input/ に短い依頼 MD を書く（poll が拾う）。

    無効化: JARVIS_SEND_GATE_311_ENQUEUE_DISABLE=1 → FileNotFoundError ではなく
    呼び出し側で env を見るか、ここでは Path を返さず例外。
    """
    if (os.environ.get("JARVIS_SEND_GATE_311_ENQUEUE_DISABLE") or "").strip() in (
        "1",
        "true",
        "yes",
    ):
        raise RuntimeError("JARVIS_SEND_GATE_311_ENQUEUE_DISABLE=1")
    draft = Path(draft_path).expanduser().resolve()
    if not draft.is_file():
        raise FileNotFoundError(f"下書きがありません: {draft}")
    dest_dir = Path(inbox).expanduser() if inbox else DEFAULT_INBOX
    dest_dir.mkdir(parents=True, exist_ok=True)
    src = (source or "manual").strip() or "manual"
    partner = (partner_or_thread or _partner_hint_from_path(draft)).strip()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_src = re.sub(r"[^\w\-]+", "_", src)[:24] or "manual"
    safe_partner = re.sub(r"[^\w\-一-龥]+", "_", partner)[:40] if partner else "draft"
    name = f"{stamp}_{safe_src}_{safe_partner}.md"
    out = dest_dir / name
    if out.exists():
        out = dest_dir / f"{stamp}_{safe_src}_{safe_partner}_{os.getpid()}.md"
    body_note = note.strip() or "（上流キック・本文は下書き正本を参照）"
    text = (
        "---\n"
        f"draft_path: {draft}\n"
        f"source: {src}\n"
        f"partner_or_thread: {partner}\n"
        "---\n\n"
        f"# 311 依頼（{src}）\n\n"
        f"{body_note}\n"
    )
    out.write_text(text, encoding="utf-8")
    return out


def _parse_inbox_md(path: Path) -> tuple[Path, str]:
    """YAML frontmatter or simple key: value → draft_path, source."""
    text = path.read_text(encoding="utf-8", errors="replace")
    draft = ""
    source = "manual"
    if text.lstrip().startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm = parts[1]
            for line in fm.splitlines():
                if ":" not in line:
                    continue
                k, _, v = line.partition(":")
                k, v = k.strip().lower(), v.strip().strip('"').strip("'")
                if k in ("draft_path", "draft"):
                    draft = v
                elif k == "source":
                    source = v or source
    if not draft:
        for line in text.splitlines():
            if ":" not in line:
                continue
            k, _, v = line.partition(":")
            k, v = k.strip().lower(), v.strip().strip('"').strip("'")
            if k in ("draft_path", "draft"):
                draft = v
            elif k == "source":
                source = v or source
    if not draft:
        raise ValueError(f"inbox MD に draft_path がありません: {path}")
    return Path(draft).expanduser(), source


def _read_draft(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"下書きがありません: {path}")
    return path.read_text(encoding="utf-8", errors="replace")


def _emails_in(text: str) -> list[str]:
    return [e.lower() for e in EMAIL_RE.findall(text or "")]


def run_checks(
    *,
    draft_path: Path,
    body: str,
    source: str,
    partner: dict[str, Any] | None,
    cfg: dict[str, Any],
) -> GateResult:
    checks: list[CheckResult] = []
    to_lines = [m.group(1).strip() for m in HEADER_TO.finditer(body)]
    from_lines = [m.group(1).strip() for m in HEADER_FROM.finditer(body)]
    line_dest = ""
    m_line = LINE_DEST.search(body)
    if m_line:
        line_dest = m_line.group(1).strip()

    to_blob = "\n".join(to_lines) if to_lines else ""
    # ヘッダが無いメール下書きは本文全体からアドレス抽出（誤爆防止のためヘッダ優先）
    to_emails = _emails_in(to_blob) if to_blob else []
    from_emails = _emails_in("\n".join(from_lines))
    all_emails = _emails_in(body)

    # --- 点検1: 宛先 ---
    partner_emails = [e.lower() for e in (partner or {}).get("emails") or [] if e]
    partner_name = str((partner or {}).get("name") or "")
    partner_folder = str((partner or {}).get("folder") or "")

    if line_dest:
        # LINE: Phase1は「宛先行がある＋三桁フォルダ紐づけ」まで（グループ名≠社名のことが多い）
        if not line_dest.strip():
            checks.append(CheckResult(False, "dest", "LINE宛先行が空"))
        else:
            note = f"LINE宛先あり: {line_dest}"
            if partner_folder:
                note += f"（folder={partner_folder}）"
            checks.append(CheckResult(True, "dest", note))
    elif to_emails and partner_emails:
        if any(e in partner_emails for e in to_emails):
            checks.append(CheckResult(True, "dest", "Toがパートナー登録メールと一致"))
        else:
            checks.append(
                CheckResult(
                    False,
                    "dest",
                    f"To {to_emails} が登録メール {partner_emails} と不一致",
                )
            )
    elif partner_emails and all_emails:
        # ヘッダ無し・本文にメールあり: パートナー以外が混ざっていないか
        foreign = [e for e in all_emails if e not in partner_emails]
        # 自分側アドレスは除外
        allowed_self = set()
        for k in cfg.get("allowed_from_env_keys") or []:
            v = (os.environ.get(k) or "").strip().lower()
            if v:
                allowed_self.add(v)
        for e in cfg.get("allowed_from_emails") or []:
            allowed_self.add(str(e).lower())
        foreign = [e for e in foreign if e not in allowed_self]
        if foreign:
            checks.append(
                CheckResult(
                    False,
                    "dest",
                    f"本文中の宛先候補がパートナー外: {foreign[:3]}",
                )
            )
        else:
            checks.append(CheckResult(True, "dest", "本文中アドレスはパートナー／本人範囲"))
    elif partner:
        # メール下書きで To 明示なし → Phase1は「要確認」ではなくパス（パートナー紐づけのみ）
        checks.append(
            CheckResult(
                True,
                "dest",
                f"パートナー紐づけのみ確認（{partner_folder or partner_name}）。To明示なし",
            )
        )
    else:
        checks.append(
            CheckResult(
                True,
                "dest",
                "パートナー未特定のため宛先照合はスキップ（パスに三桁フォルダ推奨）",
            )
        )

    # --- 点検2: 送信者名義 ---
    allowed = set()
    for k in cfg.get("allowed_from_env_keys") or []:
        v = (os.environ.get(k) or "").strip().lower()
        if v:
            allowed.add(v)
    for e in cfg.get("allowed_from_emails") or []:
        allowed.add(str(e).lower())

    if from_emails:
        bad = [e for e in from_emails if e not in allowed]
        if bad:
            checks.append(
                CheckResult(False, "sender", f"From/Reply-To が本人外: {bad}")
            )
        else:
            checks.append(CheckResult(True, "sender", "From/Reply-To が許容名義"))
    else:
        # 明示ヘッダなし → 下書きは社内正本前提でOK（送信時にyoritooriがFromを付ける）
        checks.append(
            CheckResult(True, "sender", "From明示なし（送信経路側で本人名義想定）")
        )

    # --- 点検3: 禁止宛先 ---
    ban_subs = [s.lower() for s in (cfg.get("email_substrings") or [])]
    ban_kw = list(cfg.get("text_keywords") or [])
    hit: list[str] = []
    scan_emails = to_emails or all_emails
    for e in scan_emails:
        for sub in ban_subs:
            if sub in e:
                hit.append(e)
                break
    for kw in ban_kw:
        if kw and kw in body:
            hit.append(f"keyword:{kw}")
    if hit:
        checks.append(CheckResult(False, "banned", f"禁止宛先／運営混入: {hit[:5]}"))
    else:
        checks.append(CheckResult(True, "banned", "禁止宛先なし"))

    ng = [c for c in checks if not c.ok]
    if ng:
        reason = "／".join(c.detail for c in ng)
        overall = "NG"
    else:
        reason = ""
        overall = "OK"

    return GateResult(
        draft_path=str(draft_path),
        source=source,
        overall=overall,
        reason=reason,
        checks=checks,
        meta={
            "partner_folder": partner_folder,
            "partner_name": partner_name,
            "line_dest": line_dest,
            "to_emails": to_emails,
        },
    )


def _ng_hint(res: GateResult) -> str:
    """人が読んで次の一手が分かる短いヒント。"""
    codes = {c.code for c in res.checks if not c.ok}
    partner = str(res.meta.get("partner_folder") or "")
    hints: list[str] = []
    if "dest" in codes:
        hints.append(
            "宛先点検NG: 下書きの宛先／To と、紐づけたパートナーフォルダが食い違っています。"
            "まずパス内の三桁フォルダ（例: 103_Tcell）が意図どおりか確認。"
            "partner が 215_ など親フォルダ名だけなら紐づけ誤り（ゲート側の取り違え）を疑う。"
        )
    if "sender" in codes:
        hints.append(
            "名義点検NG: From／Reply-To が本人許容アドレス外です。"
            "別アカウント・代理名義が混ざっていないか確認。"
        )
    if "banned" in codes:
        hints.append(
            "禁止宛先NG: noreply／運営宛などが含まれています。"
            "To/Cc/Bcc と本文中のメールを見直し（送らず修正）。"
        )
    if not hints:
        hints.append("上記理由を確認。下書きは書き換えず、修正してから再ゲート。")
    if partner.startswith("215_"):
        hints.append(
            "※partner が 215_ 始まり: OneDrive親フォルダの誤認の可能性大（実害のない誤報になりやすい）。"
        )
    return " ".join(hints)


def _format_slack(res: GateResult) -> tuple[str, str]:
    """Return (channel, text)."""
    name = Path(res.draft_path).name
    partner = res.meta.get("partner_folder") or "—"
    partner_name = res.meta.get("partner_name") or "—"
    if res.overall == "OK":
        text = (
            f"📎 311 送信前品質ゲート\n"
            f"- 判定: OK（この下書きはゲート通過。送信は別途・人が了承）\n"
            f"- 件数: 1\n"
            f"- source: {res.source}\n"
            f"- 紐づけ: {partner}（{partner_name}）\n"
            f"- file: {name}"
        )
        return "report", text
    ng_lines = [f"  · [{c.code}] {c.detail}" for c in res.checks if not c.ok]
    text = (
        f"📎 311 送信前品質ゲート\n"
        f"- 判定: NG（送らないで確認してほしい件）\n"
        f"- 要約: {res.reason}\n"
        f"- 内訳:\n"
        + "\n".join(ng_lines)
        + "\n"
        f"- 見方: {_ng_hint(res)}\n"
        f"- source: {res.source}\n"
        f"- 紐づけ: {partner}（{partner_name}）\n"
        f"- ファイル: {name}\n"
        f"- パス: {res.draft_path}\n"
        f"- 次: 下書きを直す → 同じCLIで再実行。誤報なら Jarvis に「誤報」と伝える"
    )
    return "consult", text


def _post_slack(channel: str, text: str) -> int:
    py = sys.executable
    cmd = [
        py,
        str(REPO / "scripts" / "jarvis_slack_webhook_post.py"),
        "--channel",
        channel,
        "--username",
        "311 送信前品質係",
        "--text",
        text,
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(p.stdout)
    sys.stderr.write(p.stderr)
    return p.returncode


def _write_output(res: GateResult) -> Path:
    out_dir = AGENT_DIR / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"gate_{ts}.json"
    payload = asdict(res)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _process_one(
    draft: Path,
    source: str,
    *,
    dry_run: bool,
    post: bool,
    cfg: dict[str, Any],
) -> int:
    body = _read_draft(draft)
    partner = _partner_from_path(draft)
    res = run_checks(
        draft_path=draft, body=body, source=source, partner=partner, cfg=cfg
    )
    out_path = _write_output(res)
    print(f"overall={res.overall}")
    if res.reason:
        print(f"reason={res.reason}")
    for c in res.checks:
        mark = "OK" if c.ok else "NG"
        print(f"  [{mark}] {c.code}: {c.detail}")
    print(f"output={out_path}")

    if dry_run and not post:
        print("dry-run: Slack投稿なし")
        return 0 if res.overall == "OK" else 10

    if post:
        ch, text = _format_slack(res)
        code = _post_slack(ch, text)
        if code != 0:
            return code
    return 0 if res.overall == "OK" else 10


def main() -> int:
    _load_env()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--draft", type=Path, help="下書きファイルパス（経路B）")
    ap.add_argument(
        "--source",
        default="manual",
        help="s9|211|hawk|s2|manual",
    )
    ap.add_argument(
        "--from-inbox",
        nargs="?",
        const=str(DEFAULT_INBOX),
        default=None,
        help="経路A: input/ の未処理 MD（省略時は既定 input/）",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="inbox 処理の上限件数（0=すべて）",
    )
    ap.add_argument(
        "--keep-inbox",
        action="store_true",
        help="処理後も input/ に残す（テスト用。定常pollでは使わない）",
    )
    ap.add_argument(
        "--enqueue",
        action="store_true",
        help="経路Aキック: input/ に依頼 MD を書いて終了（ゲートは走らない）",
    )
    ap.add_argument(
        "--partner",
        default="",
        help="--enqueue 時の partner_or_thread（省略時はパスから推定）",
    )
    ap.add_argument("--dry-run", action="store_true", help="Slackに投稿しない")
    ap.add_argument("--post", action="store_true", help="Slack #report/#consult へ投稿")
    ap.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="banned_patterns.yaml",
    )
    args = ap.parse_args()
    cfg = _load_yaml(args.config)

    if args.enqueue:
        if not args.draft:
            print("❌ --enqueue には --draft が必要です", file=sys.stderr)
            return 2
        try:
            written = enqueue_request(
                args.draft,
                source=args.source,
                partner_or_thread=args.partner,
            )
        except Exception as e:
            print(f"❌ enqueue 失敗: {e}", file=sys.stderr)
            return 2
        print(f"enqueued={written}")
        return 0

    if args.from_inbox is not None:
        inbox = Path(args.from_inbox).expanduser()
        if not inbox.is_dir():
            print(f"❌ inbox がありません: {inbox}", file=sys.stderr)
            return 2
        mds = _list_inbox_mds(inbox)
        if args.limit and args.limit > 0:
            mds = mds[: args.limit]
        if not mds:
            print(f"inbox に処理対象 MD がありません: {inbox}")
            return 0
        worst = 0
        processed_dir = inbox / "processed"
        processed_dir.mkdir(parents=True, exist_ok=True)
        for md in mds:
            print(f"--- inbox: {md.name}")
            try:
                draft, source = _parse_inbox_md(md)
            except ValueError as e:
                print(f"❌ {e}", file=sys.stderr)
                worst = max(worst, 2)
                if not args.keep_inbox:
                    bad = processed_dir / f"error_{md.name}"
                    if bad.exists():
                        bad = (
                            processed_dir
                            / f"error_{md.stem}_{datetime.now().strftime('%H%M%S')}{md.suffix}"
                        )
                    md.rename(bad)
                    print(f"inbox_error={bad}")
                continue
            code = _process_one(
                draft, source, dry_run=args.dry_run, post=args.post, cfg=cfg
            )
            worst = max(worst, code)
            if not args.keep_inbox:
                dest = processed_dir / md.name
                if dest.exists():
                    dest = (
                        processed_dir
                        / f"{md.stem}_{datetime.now().strftime('%H%M%S')}{md.suffix}"
                    )
                md.rename(dest)
                print(f"inbox_processed={dest}")
        print(f"inbox_done count={len(mds)} worst_exit={worst}")
        return worst

    if not args.draft:
        print("❌ --draft または --from-inbox を指定してください", file=sys.stderr)
        return 2
    return _process_one(
        args.draft.expanduser(),
        args.source,
        dry_run=args.dry_run,
        post=args.post,
        cfg=cfg,
    )


if __name__ == "__main__":
    raise SystemExit(main())
