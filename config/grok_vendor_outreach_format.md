---
status: approved
version: A'-v2
approved_at: 2026-08-22
approved_by: 松野（Grok Bot2 A' + ボロAP1行・WeStudy step5-2）
supersedes: v1（土地値100%・第二希望ブロック）
send_gate: Phase4 — Grok Bot2 / approved A'-v2 の Web フォーム送信可（1日3社・リスト順）。都度承認不要。draft では送らない
---

# Grok 業者開拓 Bot — 問い合わせ形式（正本）

**用途**: 地場リストへの**初回アプローチ**（顧客登録・条件マッチ物件の紹介依頼）。  
**別物**: 具体物件が来てからの問合せ → `config/kurashift_re_inquiry_template.yaml`（KURASHIFT deals）

地場不動産会社の Web 問合せフォーム／メール用。Bot 説明文に本ファイルを貼る。

## 方針

- **第一候補**: 戸建（投資・賃貸運用）。ボロ戸建・空き家・要修繕 OK
- **ボロAP**: 初回文は **1行のみ**（第二希望ブロックは入れない）
- **リスト正本**: `config/kurashift_re_vendor_list.yaml`
- **送信者**: **松野個人**。**返信先・署名は `matsuno.estate@gmail.com`（松野エステイト）**
- **運営問合済み**: `ops_contacted_at` は神大家運営作業の参考のみ。個人として改めて送る
- **1日 N 件**: `daily_outreach_limit`（Phase 1=3 → 2=5 → 3=10）
- **系列重複**: 同一グループ・同一問合せ経路への二重送信禁止（Bot2 必須チェック）
- **地場向け**: **利回り%・土地値%は書かない**（安さ・即検討・3棟所有で信頼を取る）

## 必須 / 禁止

**必須**: 3棟所有／戸建第一／ボロ戸建 OK／安さ優先／市名列挙／ハザード除外／返信先 matsuno.estate@gmail.com／ボロAP **1行**

**禁止**: 利回り%（13%・20% 等）／土地値%／ボロAP第二希望ブロック／329社一括／Grandole 等固有名／draft 文面

**狭い欄で削る順**: ボロAP1行 → 3棟AP → ハザード（土地値は初回から書かない）

## 送信者プロフィール（文面に載せる属性）

| 項目 | 内容 |
|---|---|
| 氏名 | 松野真治（フリガナ: マツノマサハル） |
| 職業 | サラリーマン（本業）＋不動産投資 |
| 経験 | 不動産投資 約10年 |
| **所有** | **一棟アパート 3棟**（愛知・運用中） |
| 購入姿勢 | 条件合えば即検討・購入意思あり |

物件名は問合せ文では**棟数のみ**で十分（Grandole 等の固有名は載せない）。

## 問い合わせ文 — 標準（chubu）

```
件名: 戸建て物件の情報提供のお願い（愛知・岐阜・静岡）

御社HPを拝見しました。松野真治と申します。
サラリーマンをしながら不動産投資をしており、経験は約10年です。
現在、一棟アパートを3棟所有し、運用しております。

賃貸運用の戸建てを探しており、築年数が古くても（ボロ戸建てでも）構いません。
予算は500万〜3,000万円程度で、お値打ちの物件を優先したいです。
相続・空き家・要修繕でも構いません。

【候補エリア（市）】
愛知県：安城市、岡崎市、豊田市、西尾市、碧南市、刈谷市、知立市、高浜市、豊橋市
岐阜県：大垣市、岐阜市近郊
静岡県：浜松市 など
（上記以外の近隣市でもご紹介いただければ幸いです）

なお、愛知県中心で築古・ボロアパートの情報も、将来の仕込みとして共有いただければ幸いです。

ハザードリスクが大きい物件は除外希望です。
可能であれば概要資料（PDF等）を matsuno.estate@gmail.com 宛にご送付ください。
今後、未公開・特殊な物件が入りましたらご連絡いただけますと幸いです。

よろしくお願いいたします。
松野真治
matsuno.estate@gmail.com
```

## 200字版（chubu・文字数制限フォーム用）

```
松野真治です。経験約10年、一棟アパート3棟所有。賃貸用戸建てを探しています。ボロ戸建て・空き家・要修繕でも構いません。予算500万〜3,000万円で安いほど助かります。安城市・岡崎市・豊田市ほか西三河、大垣、浜松。ハザードリスク大は除外。資料は matsuno.estate@gmail.com まで。
```

（200字版ではボロAP1行は省略可）

## 滋賀（shiga）差し替え

**件名**: 戸建て物件の情報提供のお願い（滋賀県）

**エリア行のみ差替**（他は chubu 標準と同構造。ボロAP1行は「滋賀県中心」に読み替え可）:

```
【候補エリア（市）】
滋賀県：大津市、草津市、守山市、栗東市、野洲市、湖南市、甲賀市、近江八幡市、東近江市、彦根市、長浜市、米原市
（近隣も可。京都・大阪の都心は不要）
```

## フォーム共通の入力

| 欄 | 値 |
|---|---|
| お名前 | 松野真治 |
| フリガナ | マツノマサハル |
| メール | matsuno.estate@gmail.com |
| 電話 | JSON `form_contact.phone`（Jarvis が `--next` に付与）。無ければ松野に確認 |
| 住所 | JSON `form_contact.address` + `postal_code`。無ければ松野に確認 |

## 系列・グループ重複（心証）

- **単独店** … 送信可
- **同一問合せ URL／同一本部フォーム** … **2件目以降は送らない**（`skip` + 理由）
- **同一ブランドでも店舗別 URL** … **送ってよい**（C21 複数店舗等）
- 判定: **`contact_url` / `outreach_route_key` / `routes_contacted`** が主。ブランド名は参考のみ
- 詳細: `grok_vendor_outreach_bot_grok_paste.md` §系列

## URL 未登録（リストに URL なし）

- JSON `needs_url_discovery: true` → **公式サイト・問合せ URL を調査してから送信可**
- 同一性確認後、フォーム送信。`--mark` に `discovered_url:...` を必ず記載
- 見つからなければ `skip`（理由1行）。詳細: Instructions §URL 未登録時

## Bot 作業手順

### A. 既存リストへの問合せ（1日 N 件）

1. Jarvis `--next N`（`outreach_from: matsuno.estate@gmail.com`）
2. 上記 **A'-v2 標準文面**（list_region でエリア差替）
3. `ops_contacted_at` があっても個人未送信 → 送ってよい
4. フォームに **返信先メール matsuno.estate@gmail.com** を必記
5. **Bot2 が送信まで実行**（approved A'-v2・1日3社・都度承認不要）
6. 送信後: `--mark {id} --status contacted --note "個人Web送信(estate) YYYY-MM-DD"`

### B. 新規探索（1日 M 件・問合せは送らない）

`grok_vendor_discovery_append.md` → `--merge-append`

## 参照

- WeStudy: `config/kurashift_westudy_vendor_lesson.yaml`（**kamiooya-kiso-step5-2**）
- 文字起こし正本: `…/基礎講座文字起こし_kamiooya-kiso-step5-2.md`
- Grok 確定メール: estate `[Grok調査] 業者開拓 approved A' 2026-08-22`

## Jarvis 側

- CLI: `scripts/jarvis_kurashift_vendor_list.py`
- Bot 貼り付け: `config/grok_vendor_outreach_bot_grok_paste.md`
- 返信 → `property_mail_match.py`（estate）
- 具体物件 → deals → `kurashift_re_inquiry_template.yaml`

## 返信・物件送付の裁き（milestone 業者）

**ブロックリスト対象ではない。** 問合せの成功（期待どおりの返信）として扱う。

| 返信の種類 | 裁き | ブロック？ |
|---|---|---|
| 条件確認・質問のみ（予算・エリア・用途） | estate から短文返信（Jarvis 下書き可）。YAML `--mark … --status replied` | **しない** |
| 物件 PDF／リンク／概要資料 | `property_mail_match --apply` → deals → 候補なら Bot1 `[Grok調査]` → ファネル | **しない** |
| 挨拶・登録完了・「物件があれば連絡」 | `replied` 記録。deals 待ち | **しない** |
| 関係ない一斉・セミナー勧誘・スパム | `passed` または Gmail フィルタ。リスト `--status skip` | 物件メールとして除外（業者ブロックリストとは別） |

- **auto_pass**（エリア外・区分のみ等）= 物件のふるい。業者そのものの拒否リストではない。
- 返信が来た業者は **milestone（関係構築中）**。以降の物件メールは **パートナー系より軽い** が、**取込・評価パイプラインは同じ**（deals / Grok / 第一問合せ）。
- Bot2 は **返信対応・物件判断をしない**。estate 受信 → Jarvis 取込 → KURASHIFT deals が正本。
