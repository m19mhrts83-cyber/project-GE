# やり取り.md 用の共通ユーティリティ

import re
from pathlib import Path

# パートナー別フォルダ内のファイル名（全社統一）
YORITOORI_FILENAME = "5.やり取り.md"
DRAFT_FILENAME = "4.送信下書き.txt"


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
