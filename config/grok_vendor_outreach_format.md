---
status: approved
approved_at: 2026-08-22
approved_by: 松野（WeStudy kamiooya-otoiawase 方針 + 現行3棟所有）
send_gate: Phase4 — Grok Bot2 / 手動 Web 送信のみ。draft では送らない
---

# Grok 業者開拓 Bot — 問い合わせ形式（正本）

**用途**: 地場リストへの**初回アプローチ**（顧客登録・条件マッチ物件の紹介依頼）。  
**別物**: 具体物件が来てからの問合せ → `config/kurashift_re_inquiry_template.yaml`（KURASHIFT deals）

地場不動産会社の Web 問合せフォーム／メール用。Bot 説明文に本ファイルを貼る。

## 方針

- **第一候補**: 戸建（投資・賃貸運用）
- **第二候補（仕込み）**: 築古ボロアパート（愛知中心・融資先あり。即買いより情報収集・仕込み）
- **リスト正本**: `config/kurashift_re_vendor_list.yaml`
- **送信者**: **松野個人**。**返信先・署名は `matsuno.estate@gmail.com`（松野エステイト）**
- **運営問合済み**: `ops_contacted_at` は神大家運営作業の参考のみ。個人として改めて送る
- **1日 N 件**: `daily_outreach_limit`（既定 3）
- **地場向け**: **利回り%は前面に出さない**（土地値・即検討・所有実績で信頼を取る）

## 送信者プロフィール（文面に載せる属性）

| 項目 | 内容 |
|---|---|
| 氏名 | 松野真治 |
| 職業 | サラリーマン（本業）＋不動産投資 |
| 経験 | 不動産投資 約10年 |
| **所有** | **一棟アパート 3棟**（愛知・運用中） |
| 購入姿勢 | 条件合えば即検討・購入意思あり |
| 融資 | 地銀等（愛知の築古APも打診可能な見込み） |

物件名は問合せ文では**棟数のみ**で十分（Grandole 等の固有名は載せない）。

## 問い合わせ文 — 標準（中部・滋賀共通）

エリア行だけ `list_region` に合わせて差し替え。

```
件名: 投資物件の情報提供のお願い（戸建中心・愛知・岐阜・滋賀）

御社HPを拝見しました。松野真治と申します。
サラリーマンをしながら不動産投資をしており、不動産経験は約10年です。
現在、一棟アパートを3棟所有し、運用しております。

【第一希望：戸建（投資・賃貸運用）】
・エリア: 愛知県・岐阜県・滋賀県（近隣も可）
・価格帯: 500万〜3,000万円程度
・土地値が購入価格に対して高い物件を優先
・ハザードリスクが大きい物件は除外希望

【第二希望：仕込みとして築古ボロアパート】
・上記戸建が第一候補ですが、愛知県中心で
  築古・ボロアパートも将来の仕込みとして情報提供をお願いします
・土地値・キャッシュフローが合えば検討します（即時購入より情報収集も歓迎）

条件に近い物件が出ましたら、即検討します。
可能であれば概要資料（PDF等）を matsuno.estate@gmail.com 宛にご送付ください。
今後、条件に合う物件が入りましたらご連絡いただけますと幸いです。

よろしくお願いいたします。
松野真治
matsuno.estate@gmail.com
```

### エリア差し替え例

- **中部リスト（chubu）**: 件名・本文のエリアを「愛知県・岐阜県・静岡県」
- **滋賀リスト（shiga）**: 「滋賀県（近隣も可）」を先頭に

## Bot 作業手順

### A. 既存リストへの問合せ（1日 N 件）

1. Jarvis `--next N`（`outreach_from: matsuno.estate@gmail.com`）
2. 上記**標準文面**を使用（戸建＋ボロAP仕込み・3棟所有は**必ず含める**）
3. `ops_contacted_at` があっても個人未送信 → 送ってよい
4. フォームに **返信先メール matsuno.estate@gmail.com** を必記
5. 送信後: `--mark {id} --status contacted --note "個人Web送信(estate) YYYY-MM-DD"`

### B. 新規探索（1日 M 件・問合せは送らない）

`grok_vendor_discovery_append.md` → `--merge-append`

## 参照（旧・神大家付属）

- `OneDrive/215/…/不動産業者リスト/販売業者向け定型文.txt` … AP向け・**1棟所有・利回り13%は旧版**。現行は**3棟・利回り前面NG**
- WeStudy: `config/kurashift_westudy_vendor_lesson.yaml`（**kamiooya-kiso-step5-2**）
- 文字起こし正本: `…/基礎講座文字起こし_kamiooya-kiso-step5-2.md`（Vimeo VTT）

## Jarvis 側

- CLI: `scripts/jarvis_kurashift_vendor_list.py`
- Bot 説明: `config/grok_vendor_outreach_bot.md`
- 返信 → `property_mail_match.py`（estate）
- 具体物件 → deals → `kurashift_re_inquiry_template.yaml`
