# Grok 業者開拓 Bot — 問い合わせ形式（正本）

地場不動産会社の Web 問合せフォーム／メール用。Bot 説明文に本ファイルを貼る。

## 方針

- **対象**: 戸建て投資向けの地場不動産（愛知・岐阜・三重中心）
- **リスト正本**: `config/kurashift_re_vendor_list.yaml`（Jarvis が整備。既存リストを転記）
- **送信**: Web フォームまたは問合せメール。試行段階は **1社ずつ**、送信前にユーザー確認でも可
- **秘密**: `.env` / token は触らない

## 問い合わせ文（コピー用）

```
件名: 戸建投資物件の情報提供のお願い（愛知・岐阜エリア）

お世話になっております。松野と申します。
戸建ての投資用物件（愛知県・岐阜県中心）の情報提供を希望しております。

【希望条件（目安）】
・戸建（賃貸運用想定）
・価格帯: 500万〜3,000万円程度
・利回り: 15%以上を目安（要相談）
・土地値が購入価格に対して高い物件を優先的にご紹介いただけますと幸いです
・ハザードリスクが大きい物件は除外希望

【お願い】
・現在ご紹介可能な物件があれば、概要資料（PDF等）をメールにて
  matsuno.estate@gmail.com 宛にご送付ください
・今後、条件に合う物件が入りましたらご連絡いただけますと幸いです

よろしくお願いいたします。
松野真治
matsuno.estate@gmail.com
```

## Bot 作業手順

### A. 既存リストへの問合せ（1日 N 件）

1. Jarvis `--next N` で pending / discovered を確認
2. リストの `contact_url` を開く
3. 戸建・投資向けか目視（違えば `status: skip`）
4. 問い合わせ文で送信
5. Jarvis `--mark {id} --status contacted --note "Web送信 YYYY-MM-DD"`

### B. 新規探索（1日 M 件・問合せは送らない）

1. `grok_vendor_discovery_append.md` の形式で YAML 追記ブロックを返す
2. Jarvis `--merge-append` でリストに追加（`status: discovered`）
3. 問合せは **A** の別セッションで

## Jarvis 側

- リスト正本: `config/kurashift_re_vendor_list.yaml`
- CLI: `scripts/jarvis_kurashift_vendor_list.py`
- 返信メール → `property_mail_match.py`（既存）
- 候補 deal → deals「Grok調査用コピー」→ 物件調査 Bot
