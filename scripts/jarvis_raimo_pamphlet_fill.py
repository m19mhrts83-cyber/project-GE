#!/usr/bin/env python3
"""Fill Raimo AI Studio pamphlet workflow (周辺MAP) steps 1–4.

Stops BEFORE clicking 「ワークフローを完了」 (needs user approval).
Answers are prepared offline (Jarvis as external AI).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path.home() / "git-repos"
ENV = ROOT / ".env.jarvis_private"
OUT = Path("/tmp/raimo_pamphlet_fill")
SHEET_DIR = Path(
    "/Users/matsunomasaharu2/Library/CloudStorage/OneDrive-個人用/"
    "215_神・大家さん倶楽部/C1_cursor/1c_神・大家さん倶楽部_AI推進/"
    "AI×周辺MAP/試走出力/2026-07-26_PathC_パンフレット"
)

STEP1_FIELDS = {
    "パンフレットの種類": "周辺MAP",
    "ページ数": "1",
    "制作目的": (
        "空室対策・入居者募集用の周辺施設MAPを、A4横・ペラ1枚で作成する。\n"
        "物件周辺の実在施設とアクセスを分かりやすく示し、内見・検討中の方に"
        "「この街で暮らせそう」と感じてもらう。\n"
        "ページ構成の詳細原稿やデザイン最終稿はこの段階では作らない。"
    ),
    "想定読者": (
        "主な想定: 20代後半の単身（栄方面通勤・タイパ／コスパ重視。休日はカフェや商店街散策）。\n"
        "広めの読者: 単身〜カップルの入居検討者。\n"
        "知りたいこと: 最寄り駅・徒歩分、日常の買い物、休日に寄れる評判の店、エリアの雰囲気。"
    ),
    "使用・配布シーン": (
        "内見時の配布、募集図面の添付、管理会社・仲介への共有、オーナー説明資料の1枚。\n"
        "印刷（A4横）およびPDFでの送付を想定。"
    ),
    "参考情報": (
        "【掲載対象】\n"
        "- 物件名: Grandole志賀本通\n"
        "- 住所: 愛知県名古屋市北区長田町4丁目69番地5\n"
        "- 用途: 賃貸マンションの周辺MAP（入居者募集）\n\n"
        "【サイズ・構成の前提】\n"
        "- A4横・1ページ（ペラ1枚）\n"
        "- 要素イメージ: タイトル／Access帯／中央に地図＋施設吹き出し／エリア一言／人物コメント（任意）\n\n"
        "【Access（掲載用・実測突合済み）】\n"
        "1. 地下鉄名城線「志賀本通駅」 約7分\n"
        "2. 名鉄瀬戸線「尼ケ坂駅」 約8分\n"
        "3. ナフコトミダ杉栄店（生鮮スーパー） 約3分\n"
        "4. ドラッグスギヤマ杉栄店 約3分\n"
        "5. 名古屋市北区役所 約18分\n"
        "6. ゲオ辻本通店 約14分\n\n"
        "【地図ピン＋吹き出し（実在確認済・最大8）】\n"
        "1. 志賀本通駅｜約7分｜栄まで地下鉄で直通。通勤に使いやすい駅です\n"
        "2. 尼ケ坂駅／SAKUMACHI商店街｜約8分｜高架下におしゃれな店が並ぶ休日の散策スポットです\n"
        "3. ナフコトミダ杉栄店｜約3分｜徒歩3分で大抵の買い物が済みます\n"
        "4. ドラッグスギヤマ杉栄店｜約3分｜日用品やコスメがすぐ揃います\n"
        "5. つばめパン＆Milk（尼ケ坂本店）｜約8分｜ふわもち食パンのモーニングが人気です\n"
        "6. Cafe de Lyon Palette｜約8分｜旬のフルーツを使ったパフェが楽しめます\n"
        "7. つけそば 神宮寺｜約8〜10分｜仕事帰りに寄れる、評判のつけそば店です\n"
        "8. コノズコーヒー（駅前）｜約8〜10分｜駅前でモーニングやランチが取れます\n\n"
        "【エリア一言】\n"
        "名城線と瀬戸線に挟まれた生活至便な立地。平日は栄へスマート通勤、休日はSAKUMACHI商店街でカフェ巡りを楽しめる街です。\n\n"
        "【制約（後工程共通）】\n"
        "- 地理（道路・駅・施設の位置関係）は参考地図／Canva成果に従い、創作・追加しない\n"
        "- 店名・駅名は上記リスト以外を増やさない\n"
        "- 番号ピン（P1等）は出さない\n"
        "- 公園・名所は実在確認済みのみ（今回リストに無いものは載せない）\n"
        "- 誇大表現（絶品・最強など）は使わない"
    ),
}

STEP1_ANSWER = """## パンフレット基本情報シート
### パンフレットの種類と目的
- パンフレット名：Grandole志賀本通 周辺MAP
- パンフレットの種類：周辺MAP（物件周辺施設案内）
- ページ数：1（A4横・ペラ1枚）
- 使用・配布シーン：内見配布、募集図面添付、管理会社・仲介共有、オーナー説明
- 制作目的：空室対策・入居者募集のため、実在の駅・店舗と徒歩目安を1枚で伝え、「この街で暮らせそう」と感じてもらう
- 読後の理想状態・取ってほしい行動：周辺生活のイメージが湧き、内見・申込検討が進む

---

### 掲載対象の基本情報
- 掲載対象：賃貸マンション周辺の生活・通勤・休日スポット
- 名称：Grandole志賀本通
- 概要：名古屋市北区長田町4丁目69番地5。名城線・瀬戸線に挟まれた生活至便な立地
- 主な内容：Access6件、地図上の施設ピン＋吹き出し最大8、エリア一言、任意で人物コメント
- 強み・特徴：栄への通勤利便、徒歩圏のスーパー・ドラッグストア、SAKUMACHI商店街の休日散策
- 読者に伝えるべき価値：平日の通勤と休日のカフェ時間が両立しやすい街であること

---

### 想定読者
- 属性：20代後半単身（主）。単身〜カップル（広）
- 読者の状態：入居検討中。栄方面通勤を想定し、タイパ／コスパを重視
- 読者が知りたいこと：駅と徒歩分、日常買い出し、休日の店、エリアの雰囲気
- 読者の悩み・課題：周辺がイメージできない、駅から遠いのでは、休日の居場所が無いのでは
- 判断時に不安になりそうなこと：徒歩分の過大表示、閉店・架空店舗の掲載

---

### 中心メッセージ
- パンフレット全体で伝える中心メッセージ：平日は栄へスマート通勤、休日はSAKUMACHIでカフェ——生活至便なGrandole志賀本通の周辺案内

---

### 掲載情報の方向性
- 優先して伝えること：実在確認済みの駅・店と徒歩目安、エリア一言
- 伝えすぎない方がよいこと：夜道の断定、定休日の細記、誇大な味評価、未確認の公園・名所
- パンフレット全体のトーン：親しみやすいが誇張しない。短文・吹き出し中心
- 後工程で活用できる情報：Access表、ピン吹き出し文、エリア一言、制約（地理・店名を創作しない）

---

### 未入力・確認が必要な情報
- 管理会社名・問い合わせ先（本MAPでは必須としない）
- 公開直前の店舗営業状態の再確認（つばめパン／Cafe de Lyon／神宮寺／コノズ）
"""

STEP2_ANSWER = """===================
参考資料パート
===================

-------------------------------------
■ 1. 編集方針
-------------------------------------

▼ パンフレットで最も伝えるべきこと
平日は栄へスマート通勤、休日はSAKUMACHIでカフェ——実在の駅・店で「暮らせそう」が伝わる周辺MAP。

▼ 掲載情報の採用基準
実在確認済み・徒歩目安突合済みのみ。誇大表現なし。リスト外の店・駅は追加しない。

▼ 情報の補完方針
読者課題と訴求軸の整理は入力から自然に言い換え。数値・店名は入力どおり。

▼ 注意すべき制約
・未確認の数値や実績：なし（徒歩は突合済みとして扱う）
・断定を避けるべき表現：夜道の安全性、味の優劣
・掲載前に確認が必要な情報：4店の営業状態（公開直前）

-------------------------------------
■ 2. 読者理解
-------------------------------------

▼ 想定読者
20代後半単身（主）／単身〜カップルの入居検討者

▼ 読者の現在の状態
周辺生活がイメージしづらく、通勤と休日の両方を短時間で知りたい

▼ 読者の課題
・課題1：駅までの距離感が分からない
・課題2：日常の買い物が近いか不安
・課題3：休日の居場所（カフェ・商店街）があるか分からない

▼ 読者が知りたいこと
・最寄り駅と徒歩分
・スーパー・ドラッグストア
・休日に寄れる評判の店

▼ 読後に目指す状態
「この物件周辺で平日も休日も回せそう」と感じて内見・検討を進める

-------------------------------------
■ 3. 掲載対象の要約
-------------------------------------

▼ 30字要約
栄通勤×徒歩圏買い出し×SAKUMACHI休日

▼ 100字要約
Grandole志賀本通は名城線・瀬戸線に挟まれた生活至便な立地。志賀本通駅約7分、尼ケ坂駅約8分。徒歩3分にスーパーとドラッグストア、休日はSAKUMACHI商店街のカフェが楽しめます。

▼ 詳細要約
物件住所は名古屋市北区長田町4丁目69番地5。Accessは志賀本通駅・尼ケ坂駅・ナフコ・スギヤマ・北区役所・ゲオの6件。地図ピンは駅・日常・休日店の8件（実在確認済）と吹き出し短文、エリア一言をA4横1枚にまとめる。

-------------------------------------
■ 4. 訴求軸
-------------------------------------

| 訴求ID | 訴求テーマ | 一言コピー | 根拠・背景 | 優先度 |
|--------|------------|------------|------------|--------|
| A01 | 通勤利便 | 栄まで地下鉄で直通 | 志賀本通駅 約7分 | 高 |
| A02 | 日常買い出し | 徒歩3分で買い物完了 | ナフコ・スギヤマ 約3分 | 高 |
| A03 | 休日散策 | SAKUMACHIでカフェ巡り | 尼ケ坂駅・商店街 約8分 | 高 |

▼ メイン訴求
生活至便——通勤と休日カフェが両立する周辺

▼ サブ訴求
・徒歩圏の日常インフラ
・実在店のみの安心感
・誇張しない短文トーン

-------------------------------------
■ 5. 紙面掲載素材リスト
-------------------------------------

| 素材ID | カテゴリ | 掲載候補テキスト | 使いどころ | 表現形式候補 | 優先度 | 情報状態 |
|--------|----------|------------------|------------|--------------|--------|----------|
| C01 | 課題 | 周辺がイメージできない | 導入付近 | 見出し | 中 | 確定 |
| C02 | 特徴 | 名城線と瀬戸線に挟まれた生活至便 | エリア一言 | 本文 | 高 | 確定 |
| C03 | 強み | 志賀本通駅 約7分／栄へ直通 | Access・ピン | キャプション | 高 | 確定 |
| C04 | メリット | 徒歩3分でスーパー・ドラッグストア | Access・ピン | 吹き出し | 高 | 確定 |
| C05 | 休日 | SAKUMACHI商店街でカフェ巡り | ピン・エリア一言 | 吹き出し | 高 | 確定 |
| C06 | CTA | 内見で周辺も歩いてみてください（仮置き） | フッター付近 | 補足 | 低 | 補完 |

-------------------------------------
■ 6. 紙面用コピー素材
-------------------------------------

▼ メインコピー候補
・コピー1：Grandole志賀本通 周辺MAP
  意図：物件名＋用途の明示
  向いているページ：表紙 / 中面 / 裏表紙

・コピー2：平日は栄へ。休日はSAKUMACHIへ。
  意図：生活シーンの対比
  向いているページ：表紙 / 中面 / 裏表紙

▼ サブコピー候補
・名城線と瀬戸線に挟まれた生活至便な立地
・徒歩3分で大抵の買い物が済みます

▼ ページ見出し候補
・表紙向け：Grandole志賀本通 周辺MAP
・課題提示ページ向け：（1枚のため省略可）
・特徴紹介ページ向け：Access / 周辺スポット
・実績・信頼ページ向け：（該当なし）
・CTAページ向け：（任意・控えめ）

▼ CTAコピー候補
・周辺の雰囲気は内見時にぜひご確認ください（仮置き）

▼ 補足コピー候補
・掲載店は実在確認済み（公開前に再確認）
・番号ピン表記なし

-------------------------------------
■ 7. ビジュアル化できる情報
-------------------------------------

▼ カード化に向いている情報
Access6件（駅・店名＋徒歩）

▼ 表に向いている情報
Access一覧

▼ 写真・イラストに向いている情報
中央の地図（参考画像どおり）、いらすとや風人物コメント（任意）

▼ 注意
地図の道路・駅・施設位置は参考画像どおり。架空の駅・店を足さない。
"""

STEP3_ANSWER = """## ページ構成シート（A4横・1ページ固定）

### 全体方針
- ページ数：1
- 役割：入居検討者向け周辺MAP（印刷・PDF配布）
- 主メッセージ：平日は栄へスマート通勤、休日はSAKUMACHIでカフェ
- 制約：地理は参考地図どおり／店名は確定リストのみ／番号・P表記なし／架空追加禁止

---

### ページ1：Grandole志賀本通 周辺MAP

#### ゾーンA：ヘッダー
- タイトル「Grandole志賀本通 周辺MAP」
- エリア一言「名城線と瀬戸線に挟まれた生活至便な立地。平日は栄へスマート通勤、休日はSAKUMACHI商店街でカフェ巡りを楽しめる街です。」

#### ゾーンB：Access帯（左または上）
Access6件を短文リストで配置：
1. 地下鉄名城線「志賀本通駅」 約7分
2. 名鉄瀬戸線「尼ケ坂駅」 約8分
3. ナフコトミダ杉栄店 約3分
4. ドラッグスギヤマ杉栄店 約3分
5. 名古屋市北区役所 約18分
6. ゲオ辻本通店 約14分

#### ゾーンC：中央地図＋施設吹き出し
- 地図ビジュアル：参考Canva／骨格図の道路・施設位置を維持（再描画でずらさない）
- 吹き出し8件（文言は確定リストどおり）：
  1. 志賀本通駅｜栄まで地下鉄で直通。通勤に使いやすい駅です
  2. 尼ケ坂駅／SAKUMACHI商店街｜高架下におしゃれな店が並ぶ休日の散策スポットです
  3. ナフコトミダ杉栄店｜徒歩3分で大抵の買い物が済みます
  4. ドラッグスギヤマ杉栄店｜日用品やコスメがすぐ揃います
  5. つばめパン＆Milk｜ふわもち食パンのモーニングが人気です
  6. Cafe de Lyon Palette｜旬のフルーツを使ったパフェが楽しめます
  7. つけそば 神宮寺｜仕事帰りに寄れる、評判のつけそば店です
  8. コノズコーヒー｜駅前でモーニングやランチが取れます

#### ゾーンD：人物コメント（任意・余白があれば）
- いらすとや風キャラ＋短文1つ（誇大なし）。素材が無ければ省略可

#### ゾーンE：フッター
- 住所「愛知県名古屋市北区長田町4丁目69番地5」を小さく
- ページ番号は「1」または省略

### 構成への示唆
- 店舗偏重に見えにくいよう、駅2＋日常2をAccessで先に見せ、休日店は吹き出し側
- 公園・名所は今回リスト外のため載せない（実在時のみ方針を維持）
"""

STEP4_ANSWER = """## Grandole志賀本通 周辺MAP

### ゾーン1：ヘッダー
── 物件名とエリアの第一印象を一気に伝える

- 「Grandole志賀本通 周辺MAP」（役割：大見出し）
  ── 紙面の主題を明示する
- 「名城線と瀬戸線に挟まれた生活至便な立地。平日は栄へスマート通勤、休日はSAKUMACHI商店街でカフェ巡りを楽しめる街です。」（役割：本文）
  ── 生活シーンを1行で要約する

---

### ゾーン2：Access帯
── 通勤・日常の距離感を先に読ませる

- 「Access」（役割：小見出し）
- `カード群`：6枚（または縦リスト）
  ── 徒歩目安をスキャンしやすくする

カード内容：
1. 駅｜タイトル「志賀本通駅」（役割：小見出し）｜説明「地下鉄名城線・約7分」（役割：キャプション）
2. 駅｜タイトル「尼ケ坂駅」（役割：小見出し）｜説明「名鉄瀬戸線・約8分」（役割：キャプション）
3. 店｜タイトル「ナフコトミダ杉栄店」（役割：小見出し）｜説明「約3分」（役割：キャプション）
4. 店｜タイトル「ドラッグスギヤマ杉栄店」（役割：小見出し）｜説明「約3分」（役割：キャプション）
5. 施設｜タイトル「名古屋市北区役所」（役割：小見出し）｜説明「約18分」（役割：キャプション）
6. 店｜タイトル「ゲオ辻本通店」（役割：小見出し）｜説明「約14分」（役割：キャプション）

---

### ゾーン3：中央地図＋吹き出し
── 地理の正しさを最優先し、文言は確定リストのみ使う

- `写真`：周辺地図（参考Canva成果／骨格図と同じ道路・駅・施設位置。再配置・駅の追加・道の描き直し禁止）
  ── 位置関係の正本として扱う
- `コラムボックス`：施設吹き出し8（番号・P表記なし。店名とコメントは次の文言のみ）
  ── 地図上の生活シーンを短文で補う

吹き出し文言：
1. 「志賀本通駅｜栄まで地下鉄で直通。通勤に使いやすい駅です」
2. 「尼ケ坂駅／SAKUMACHI商店街｜高架下におしゃれな店が並ぶ休日の散策スポットです」
3. 「ナフコトミダ杉栄店｜徒歩3分で大抵の買い物が済みます」
4. 「ドラッグスギヤマ杉栄店｜日用品やコスメがすぐ揃います」
5. 「つばめパン＆Milk｜ふわもち食パンのモーニングが人気です」
6. 「Cafe de Lyon Palette｜旬のフルーツを使ったパフェが楽しめます」
7. 「つけそば 神宮寺｜仕事帰りに寄れる、評判のつけそば店です」
8. 「コノズコーヒー｜駅前でモーニングやランチが取れます」

必須制約（画像生成時）：
- 地図の道路・施設位置は参考画像どおり
- 店名・コメントは上記のみ
- 番号・P表記なし
- 架空の駅・店を足さない
- A4横・1ページ

---

### ゾーン4：人物コメント（任意）
── 余白があれば親しみを足す。無ければ省略

- 「平日は駅まで歩いて、休日は尼ケ坂あたりでゆっくりしたいです」（役割：キャプション）（仮置き・素材があれば差替）
  ── 誇大にしない一人称コメント

---

### ゾーン5：フッター
── ページの終端を整え、住所を小さく添える

- `フッターライン`：ページ最下部に配置
- 「愛知県名古屋市北区長田町4丁目69番地5」（役割：補足）
- 「1」（役割：ページ番号）または省略
"""


def load_env() -> None:
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def login(page, email: str, password: str) -> None:
    page.goto("https://raimo.buzz/login", wait_until="domcontentloaded", timeout=120000)
    page.wait_for_timeout(2000)
    page.locator('input[type="email"],input[name="email"]').first.fill(email)
    page.locator('input[type="password"],input[name="password"]').first.fill(password)
    page.get_by_role("button", name=re.compile("ログイン")).first.click()
    page.wait_for_timeout(5000)


def open_studio_workflow(page):
    btn = page.get_by_role("button", name=re.compile("ライモAI ?スタジオ"))
    try:
        with page.context.expect_page(timeout=15000) as pop:
            btn.first.click()
        page = pop.value
        page.wait_for_load_state("domcontentloaded", timeout=60000)
    except Exception:
        btn.first.click()
    page.wait_for_timeout(4000)
    page.goto("https://movie.raimo.buzz/prompt-workflows/104", wait_until="domcontentloaded", timeout=120000)
    page.wait_for_timeout(5000)
    return page


def fill_labeled_textareas(page, mapping: dict[str, str]) -> dict:
    return page.evaluate(
        """(mapping)=>{
      const out={};
      const nodes=[...document.querySelectorAll('label,div,span,p,h3,h4')];
      for (const [label, value] of Object.entries(mapping)) {
        const lab = nodes.find(n => (n.innerText||'').trim() === label
          || ((n.innerText||'').trim().startsWith(label) && (n.innerText||'').length < label.length+6));
        let ta=null;
        if (lab) {
          let el=lab;
          for (let i=0;i<8 && el;i++) {
            ta = el.querySelector && el.querySelector('textarea');
            if (ta) break;
            const sib = el.nextElementSibling;
            if (sib) {
              ta = sib.matches && sib.matches('textarea') ? sib : sib.querySelector && sib.querySelector('textarea');
              if (ta) break;
            }
            el = el.parentElement;
          }
        }
        if (!ta) { out[label]='not-found'; continue; }
        const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
        setter.call(ta, value);
        ta.dispatchEvent(new Event('input', {bubbles:true}));
        ta.dispatchEvent(new Event('change', {bubbles:true}));
        out[label]='ok:'+value.slice(0,20);
      }
      return out;
    }""",
        mapping,
    )


def paste_ai_answer(page, text: str) -> str:
    return page.evaluate(
        """(text)=>{
      const tas=[...document.querySelectorAll('textarea')].filter(t=>{
        const r=t.getBoundingClientRect();
        return r.width>0 && r.height>0 && (t.placeholder||'').includes('AI');
      });
      const ta = tas[0] || [...document.querySelectorAll('textarea')].filter(t=>{
        const r=t.getBoundingClientRect(); return r.width>100 && r.height>80;
      }).slice(-1)[0];
      if(!ta) return 'no-textarea';
      const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
      setter.call(ta, text);
      ta.dispatchEvent(new Event('input', {bubbles:true}));
      ta.dispatchEvent(new Event('change', {bubbles:true}));
      return 'ok:'+ta.value.length;
    }""",
        text,
    )


def click_text(page, label: str) -> str:
    return page.evaluate(
        """(label)=>{
      const vis=el=>{const r=el.getBoundingClientRect();return r.width>0&&r.height>0&&!!el.offsetParent;};
      const cands=[...document.querySelectorAll('button,a,[role=button],div,span')]
        .filter(vis).filter(el=>(el.innerText||'').includes(label))
        .filter(el=>el.querySelectorAll('*').length<20)
        .sort((a,b)=>(a.innerText||'').length-(b.innerText||'').length);
      if(!cands.length) return 'not-found';
      let el=cands[0];
      for(let i=0;i<4;i++){const r=el.getBoundingClientRect(); if(r.height>24&&r.width>40) break; if(el.parentElement) el=el.parentElement;}
      el.scrollIntoView({block:'center'}); el.click();
      return 'clicked';
    }""",
        label,
    )


def snap(page, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    print(f"shot {name} url={page.url}")


def save_answers() -> None:
    SHEET_DIR.mkdir(parents=True, exist_ok=True)
    (SHEET_DIR / "Step1_回答.md").write_text(STEP1_ANSWER, encoding="utf-8")
    (SHEET_DIR / "Step2_回答.md").write_text(STEP2_ANSWER, encoding="utf-8")
    (SHEET_DIR / "Step3_回答.md").write_text(STEP3_ANSWER, encoding="utf-8")
    (SHEET_DIR / "Step4_レイアウト仕様書.md").write_text(STEP4_ANSWER, encoding="utf-8")
    print(f"saved answers under {SHEET_DIR}")


def main() -> int:
    load_env()
    email = os.environ["RAIMO_PORTAL_EMAIL"]
    password = os.environ["RAIMO_PORTAL_PASSWORD"]
    save_answers()
    do_complete = "--complete" in sys.argv

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 1400})
        login(page, email, password)
        page = open_studio_workflow(page)
        snap(page, "10_open")

        # ensure step1
        click_text(page, "基本情報")
        page.wait_for_timeout(2000)
        filled = fill_labeled_textareas(page, STEP1_FIELDS)
        print("fill step1:", json.dumps(filled, ensure_ascii=False))
        page.wait_for_timeout(1500)
        r1 = paste_ai_answer(page, STEP1_ANSWER)
        print("paste step1:", r1)
        snap(page, "11_step1_filled")
        click_text(page, "次のステップへ")
        page.wait_for_timeout(3500)
        snap(page, "12_step2")

        # step2
        click_text(page, "参考資料")
        page.wait_for_timeout(1500)
        r2 = paste_ai_answer(page, STEP2_ANSWER)
        print("paste step2:", r2)
        snap(page, "13_step2_filled")
        click_text(page, "次のステップへ")
        page.wait_for_timeout(3500)

        # step3
        click_text(page, "ページ構成")
        page.wait_for_timeout(1500)
        r3 = paste_ai_answer(page, STEP3_ANSWER)
        print("paste step3:", r3)
        snap(page, "14_step3_filled")
        click_text(page, "次のステップへ")
        page.wait_for_timeout(3500)

        # step4
        click_text(page, "レイアウト作成")
        page.wait_for_timeout(1500)
        r4 = paste_ai_answer(page, STEP4_ANSWER)
        print("paste step4:", r4)
        snap(page, "15_step4_filled")

        if do_complete:
            click_text(page, "ワークフローを完了")
            page.wait_for_timeout(8000)
            snap(page, "16_completed")
            print("COMPLETED")
        else:
            print("STOPPED_BEFORE_COMPLETE — awaiting user approval")
            print("Re-run with --complete after approval.")

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
