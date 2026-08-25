# Grok 不動産フェーズ Bot — 設計（2026-08-24）

## 位置づけ

購入判断（S1/S5/S3）の **後**。部長配下。

| id | 社員 | 独立性 | 件名 |
|---|---|---|---|
| S6 | 買付・内見・価格交渉 | 独立 Bot | `[Grok買付]` |
| S7 | 融資相談・打診 | 独立 Bot | `[Grok融資]` |
| S8 | 物件ライフライン（電・水・ネット・ガス） | 独立 Bot | `[Grokライフライン]` |
| （なし） | 契約リーガルチェック | **部長内蔵** | — |
| （なし） | 火災保険アドバイス | **部長内蔵** | — |

## S8 補足（2026-08-25）

- 対象は **賃貸運用物件**のライフライン。自宅個人契約の専任ではない  
- 活躍: **購入時の新規加入** および **見直し**（プロパン給湯器無料スキーム等の比較含む）  
- S4（修繕・一人親方）と分離。開通・プランは S8、職人探しは S4  
- 実申込・対外送信は Jarvis／松野確認。Bot は比較・手順・Jarvis向け手続カードまで  

## 材料

| 役 | パス |
|---|---|
| S6 | `docs/KURASHIFT_買い進めJob仕様.md`、`/realestate/deals`、OneDrive `10_【購入】` |
| S7 | `docs/KURASHIFT_融資提出パック.md`、`config/kurashift_re_finance_doc_templates.yaml`、OneDrive `240_融資`、WeStudy融資フォーラム |
| S8 | 物件所在・入居予定、業者見積／チラシ要点、開通手続きの一般知識（秘密は jarvis_private） |
| 契約内蔵 | `25_契約確認`、property_master（弁護士代替禁止） |
| 保険内蔵 | `jarvis-fire-insurance-subrogation.mdc`、`215/60_保険`、311/313/317 |

## 禁止（全フェーズ共通）

法的断定・融資保証・無断対外送信・秘密のチャット再掲。

## paste

- S6: `config/grok_deal_negotiation_bot_grok_paste.md`
- S7: `config/grok_loan_bot_grok_paste.md`
- S8: `config/grok_property_util_bot_grok_paste.md`
- UI手順: `config/grok_remaining_bots_setup.md`
- 部長ロスター: `config/grok_sanbo_bot_grok_paste.md`
