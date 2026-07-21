#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WeStudy フォーラム板タイトル / URL → 短縮カテゴリ名（forum_category）。

番号付きラベルは使わない。正本の短縮名はユーザー合意の Phase 9 一覧。
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

# 完全一致（スクレイプ title）
TITLE_EXACT: dict[str, str] = {
    "成果報告【実践し、成果が出た内容を記載】": "成果報告",
    "月次活動報告 ＆ 来月への宣言【グルコン10日前まで】": "月次活動報告",
    "【不動産】その他役立つ情報 (プロパン業者,wifi設置もこちら)": "その他 (プロパン業者,wifi設置など)",
    "【不動産】最新融資情報１　※通常の金融機関融資情報シェアはこちら※": "融資情報1",
    "【不動産】最新融資情報１ ※通常の金融機関融資情報シェアはこちら※": "融資情報1",
    "【不動産】最新融資情報２ ※不動産会社提携ローン専用※": "融資情報2(不動産会社提携ローン)",
    "【不動産】修繕・トラブル対応関連": "修繕・トラブル対応",
    "【その他テーマ】運気UP情報": "運気UP",
    "【不動産】 オススメ/苦戦エリア、賃貸需要の共有": "オススメ/苦戦エリア、賃貸需要共有",
    "【不動産】オススメ/苦戦エリア、賃貸需要の共有": "オススメ/苦戦エリア、賃貸需要共有",
    "【不動産】ＤＩＹ部": "DIY部",
    "【不動産】DIY部": "DIY部",
    "神ホテル会員情報（ベイコート倶楽部・エクシブ）": "神ホテル会員情報",
    "【その他テーマ】超健康情報": "超健康情報",
    "【不動産】リフォーム業者情報": "リフォーム業者情報",
    "【不動産】保険会社・管理会社など": "保険会社・管理会社",
    "この業者には要注意": "この業者に要注意",
    "【全国】おススメのホテル・施設": "全国おすすめホテル・施設",
    "【相互連絡用】LINE繋がり、現地会当日連絡板": "LINE繋がり、現地会当日連絡板",
    "【不動産】購入・売却関連、不動産業者情報等": "購入・売却、不動産会社情報",
    "【不動産】補助金・助成金・特殊な融資などその他資金調達関連": "資金調達（補助金・助成金・特殊な融資）",
    "【不動産】空室対策 情報共有": "空室対策 情報共有",
    "塾生相互支援板　【仕事依頼】【仕事手伝います！】（事業やお店の宣伝もOK）": "塾生相互支援板",
    "【その他テーマ】AI活用で業務改善": "AI活用で業務改善",
    "【不動産】公庫融資を見込む創業セミナー系情報、士業紹介など": "公庫融資を見込む創業セミナー、士業紹介",
    "【自由投稿】会員同士の質問などなんでもOK": "会員同士の質問など何でもOK",
    "【その他テーマ】育児教育情報": "育児教育情報",
    "会計ソフト 使用感の共有": "会計ソフト使用感の共有",
    "【神物件名】オリジナル物件名アイディア・キーワード集": "オリジナル物件名アイデア集",
}

# URL path 末尾（forum slug）— title 欠落時の保険
URL_PATH_EXACT: dict[str, str] = {
    "results": "成果報告",
    "monthly_output": "月次活動報告",
    "work-2": "塾生相互支援板",
}

# 部分一致（長い title のゆれ吸収）。先に長いパターンを置く
TITLE_CONTAINS: list[tuple[str, str]] = [
    ("成果報告", "成果報告"),
    ("月次活動報告", "月次活動報告"),
    ("プロパン", "その他 (プロパン業者,wifi設置など)"),
    ("wifi設置", "その他 (プロパン業者,wifi設置など)"),
    ("最新融資情報１", "融資情報1"),
    ("最新融資情報1", "融資情報1"),
    ("通常の金融機関融資", "融資情報1"),
    ("最新融資情報２", "融資情報2(不動産会社提携ローン)"),
    ("最新融資情報2", "融資情報2(不動産会社提携ローン)"),
    ("提携ローン", "融資情報2(不動産会社提携ローン)"),
    ("融資情報３", "融資情報3(宅建業者）"),
    ("融資情報3", "融資情報3(宅建業者）"),
    ("宅建業者", "融資情報3(宅建業者）"),
    ("修繕・トラブル", "修繕・トラブル対応"),
    ("運気UP", "運気UP"),
    ("運気up", "運気UP"),
    ("苦戦エリア", "オススメ/苦戦エリア、賃貸需要共有"),
    ("賃貸需要", "オススメ/苦戦エリア、賃貸需要共有"),
    ("ＤＩＹ", "DIY部"),
    ("DIY部", "DIY部"),
    ("神ホテル会員", "神ホテル会員情報"),
    ("超健康", "超健康情報"),
    ("リフォーム業者", "リフォーム業者情報"),
    ("保険会社", "保険会社・管理会社"),
    ("管理会社", "保険会社・管理会社"),
    ("要注意", "この業者に要注意"),
    ("おススメのホテル", "全国おすすめホテル・施設"),
    ("おすすめのホテル", "全国おすすめホテル・施設"),
    ("育児教育", "育児教育情報"),
    ("LINE繋がり", "LINE繋がり、現地会当日連絡板"),
    ("現地会", "LINE繋がり、現地会当日連絡板"),
    ("購入・売却", "購入・売却、不動産会社情報"),
    ("補助金", "資金調達（補助金・助成金・特殊な融資）"),
    ("助成金", "資金調達（補助金・助成金・特殊な融資）"),
    ("空室対策", "空室対策 情報共有"),
    ("塾生相互支援", "塾生相互支援板"),
    ("AI活用", "AI活用で業務改善"),
    ("公庫融資", "公庫融資を見込む創業セミナー、士業紹介"),
    ("士業紹介", "公庫融資を見込む創業セミナー、士業紹介"),
    ("なんでもOK", "会員同士の質問など何でもOK"),
    ("何でもOK", "会員同士の質問など何でもOK"),
    ("育児教育", "育児教育情報"),
    ("会計ソフト", "会計ソフト使用感の共有"),
    ("オリジナル物件名", "オリジナル物件名アイデア集"),
    ("建築業者", "建築業者情報"),
    ("情報お持ちの方", "情報お持ちの方いませんか？"),
    ("息抜き", "息抜きに遊びませんか？"),
    ("事例集", "事例集（リフォーム・ステージング）"),
    ("ステージング", "事例集（リフォーム・ステージング）"),
]

SOURCE_SYSTEM_WESTUDY = "WeStudy"
SOURCE_KIND_COMMUNITY = "コミュニティ情報"
UNCLASSIFIED = "未分類"


def forum_path_slug(url: str) -> str:
    if not url:
        return ""
    path = unquote(urlparse(str(url)).path or "")
    parts = [p for p in path.split("/") if p]
    if not parts:
        return ""
    # .../forum/<slug>
    if "forum" in parts:
        i = parts.index("forum")
        if i + 1 < len(parts):
            return parts[i + 1]
    return parts[-1]


def resolve_forum_category(topic_title: str = "", topic_url: str = "") -> str:
    title = (topic_title or "").strip()
    url = (topic_url or "").strip()
    if title in TITLE_EXACT:
        return TITLE_EXACT[title]
    slug = forum_path_slug(url)
    if slug in URL_PATH_EXACT:
        return URL_PATH_EXACT[slug]
    for needle, label in TITLE_CONTAINS:
        if needle and needle in title:
            return label
    # 全角スペースゆれ
    compact = re.sub(r"\s+", " ", title)
    if compact in TITLE_EXACT:
        return TITLE_EXACT[compact]
    for needle, label in TITLE_CONTAINS:
        if needle and needle in compact:
            return label
    return UNCLASSIFIED if title or url else UNCLASSIFIED


def enrich_comment_meta(
    topic_title: str = "",
    topic_url: str = "",
    *,
    source_system: str = SOURCE_SYSTEM_WESTUDY,
    source_kind: str = SOURCE_KIND_COMMUNITY,
) -> dict[str, str]:
    title = (topic_title or "").strip()
    return {
        "source_system": source_system or SOURCE_SYSTEM_WESTUDY,
        "source_kind": source_kind or SOURCE_KIND_COMMUNITY,
        "topic_title": title,
        "forum_category": resolve_forum_category(title, topic_url),
    }
