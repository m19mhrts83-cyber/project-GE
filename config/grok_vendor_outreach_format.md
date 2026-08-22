# Grok 業者開拓 Bot — 問い合わせ形式（正本）

地場不動産会社の Web 問合せフォーム／メール用。Bot 説明文に本ファイルを貼る。

## 方針

- **対象**: 戸建て投資向けの地場不動産（愛知・岐阜・三重・滋賀・静岡）
- **リスト正本**: `config/kurashift_re_vendor_list.yaml`（Jarvis が整備）
- **送信者**: **松野個人**として。**返信先・署名は必ず `matsuno.estate@gmail.com`（松野エステイト）**
- **運営問合済み**: 滋賀リスト等に `ops_contacted_at` / メモ「運営問合済(参考)」があっても、**神大家運営の作業**。松野個人としての顧客登録は未完了 → **改めて個人名義で送る**（`status: pending` のまま対象）
- **送信**: Web フォームまたは問合せメール。1日 N 件（`daily_outreach_limit`）
- **秘密**: `.env` / token は触らない

## 問い合わせ文 — 中部（愛知・岐阜中心）

```
件名: 戸建投資物件の情報提供のお願い（愛知・岐阜エリア）

お世話になっております。松野真治と申します。
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

## 問い合わせ文 — 滋賀

```
件名: 戸建投資物件の情報提供のお願い（滋賀県）

お世話になっております。松野真治と申します。
戸建ての投資用物件（滋賀県）の情報提供を希望しております。

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

1. Jarvis `--next N` で pending を確認（`outreach_from: matsuno.estate@gmail.com`）
2. `list_region` が `shiga` なら **滋賀用文面**、それ以外は中部用
3. `ops_contacted_at` があっても **個人として未送信** → 送ってよい
4. リストの `contact_url` / `url` を開き、フォームに **返信先メール matsuno.estate@gmail.com** を必ず記載
5. 戸建・投資向けか目視（違えば `status: skip`）
6. 送信後: `--mark {id} --status contacted --note "個人Web送信(estate) YYYY-MM-DD"`

### B. 新規探索（1日 M 件・問合せは送らない）

1. `grok_vendor_discovery_append.md` の形式で YAML 追記ブロックを返す
2. Jarvis `--merge-append` でリストに追加（`status: discovered`）
3. 問合せは **A** の別セッションで

## Jarvis 側

- リスト正本: `config/kurashift_re_vendor_list.yaml`
- CLI: `scripts/jarvis_kurashift_vendor_list.py`
- 個人送信記録: `contacted_at`（運営参考日は `ops_contacted_at`）
- 返信メール → `property_mail_match.py`（estate 受信）
- 候補 deal → deals「Grok調査用コピー」→ 物件調査 Bot
