# やり取り.md 用の共通ユーティリティ

import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

# パートナー別フォルダ内のファイル名（全社統一）
YORITOORI_FILENAME = "5.やり取り.md"
DRAFT_FILENAME = "4.送信下書き.txt"


def default_yoritoori_base_dir() -> Path:
    """
    書き込みの正本は OneDrive 側（業務データ）を優先する。
    プログラム実行は git-repos 側で行うが、出力先（やり取り.md 等）は OneDrive を正とする運用。

    例外的に OneDrive パスが存在しない場合のみ git-repos 側へフォールバックする。
    """
    od = (
        Path.home()
        / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C2_ルーティン作業/26_パートナー社への相談"
    )
    gr = Path.home() / "git-repos/215_kamiooya/C2_ルーティン作業/26_パートナー社への相談"
    return od if od.is_dir() else gr


def _truthy_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def mirror_yoritoori_md_to_gitrepos(md_path: Path) -> None:
    """
    OneDrive 正本の `5.やり取り.md` を、git-repos 側へバックアップとしてミラーする（best-effort）。
    添付など容量が増えるものはミラーしない（md のみ）。
    """
    if not _truthy_env("YORITOORI_MIRROR_MD_TO_GITREPOS", default=True):
        return
    p = Path(md_path)
    if not p.is_file():
        return

    od_base = (
        Path.home()
        / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C2_ルーティン作業/26_パートナー社への相談"
    ).resolve()
    gr_base = (Path.home() / "git-repos/215_kamiooya/C2_ルーティン作業/26_パートナー社への相談").resolve()

    try:
        rp = p.resolve()
    except Exception:
        return
    if not str(rp).startswith(str(od_base) + os.sep):
        # OneDrive 配下以外は対象外（正本ではない）
        return

    rel = rp.relative_to(od_base)
    dest = gr_base / rel
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rp, dest)
    except OSError as e:
        print(f"警告: やり取り.md の git-repos ミラーに失敗: {dest}: {e}", file=sys.stderr)

def resolve_attach_dir(partner_folder):
    """
    送信添付フォルダのパスを解決。
    3.送信添付（番号付き）または 送信添付 のいずれかが存在すればそれを返す。
    なければ 送信添付 を返す（自動作成時に使用）。
    """
    partner_folder = Path(partner_folder)
    for name in ("送信添付", "3.送信添付"):
        p = partner_folder / name
        if p.exists() and p.is_dir():
            return p
    return partner_folder / "送信添付"


def resolve_past_attach_dir(partner_folder):
    """
    送信添付(過去)フォルダのパスを解決。
    2.送信添付(過去)（番号付き）または 送信添付(過去) のいずれかが存在すればそれを返す。
    なければ 送信添付(過去) を返す（自動作成時に使用）。
    """
    partner_folder = Path(partner_folder)
    for name in ("送信添付(過去)", "2.送信添付(過去)"):
        p = partner_folder / name
        if p.exists() and p.is_dir():
            return p
    return partner_folder / "送信添付(過去)"


def resolve_incoming_attach_dir(partner_folder):
    """
    受信添付フォルダのパスを解決（Gmail 受信メールの添付保存先）。
    1.受信添付(Stock)（番号付き）または 添付 のいずれかが存在すればそれを返す。
    なければ 添付 を返す（自動作成時に使用）。
    """
    partner_folder = Path(partner_folder)
    for name in ("1.受信添付(Stock)", "添付"):
        p = partner_folder / name
        if p.exists() and p.is_dir():
            return p
    return partner_folder / "添付"


def parse_received_date_folder(date_str: str) -> str:
    """受信日時文字列から日付フォルダ名 YYYY-MM-DD を返す。"""
    if not date_str:
        return datetime.now().strftime("%Y-%m-%d")
    m = re.match(r"(\d{4})[/-](\d{2})[/-](\d{2})", date_str.strip())
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"(\d{4})(\d{2})(\d{2})", date_str.strip())
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return datetime.now().strftime("%Y-%m-%d")


def resolve_incoming_attach_date_dir(partner_folder, date_str: str) -> Path:
    """
    受信添付の日付サブフォルダ（1.受信添付(Stock)/YYYY-MM-DD/）を返す。
    同一日に届いた添付をまとめて格納する。
    """
    base = resolve_incoming_attach_dir(partner_folder)
    day_dir = base / parse_received_date_folder(date_str)
    day_dir.mkdir(parents=True, exist_ok=True)
    return day_dir


def make_summary(body, max_len=50):
    """
    本文から要約を生成。（要約を記入）の代わりに使用。
    挨拶文を除き、最初の意味のある部分を max_len 文字まで抽出。
    """
    if not body or not body.strip():
        return "（要約を記入）"
    text = re.sub(r"\s+", " ", body.strip())
    # よくある挨拶を先頭から除去
    for prefix in [
        r"^松野\s*様\s*",
        r"^お世話になっております[.。]?\s*",
        r"^お世話になります[.。]?\s*",
        r"^[\s　]+",
    ]:
        text = re.sub(prefix, "", text)
    text = text.strip()
    if not text:
        return "（要約を記入）"
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "…"
