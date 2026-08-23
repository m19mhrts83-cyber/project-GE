# KURASHIFT / Grok — 供給・ペルソナ・修繕 Bot（Phase 1 設計）

**更新**: 2026-08-24  
**Phase**: 1 = Grok paste 運用開始。K = KURASHIFT 投影（後続）

## 社員番号（部長は番号外）

| id | 社員 | ペース | 件名マーカー |
|---|---|---|---|
| （なし） | 不動産賃貸・部長 | — | `[Grok部長]` |
| S1 | 物件調査（一次） | 都度＋デイリー1件 | `[Grok調査]` |
| S2 | 物件業者開拓 | デイリー | —（Webフォーム） |
| S3 | 需給三次判断 | **都度**（問合せ以降） | `[Grok需給]` |
| S4 | 修繕業者開拓 | **デイリー** | `[Grok修繕候補]` |
| S5 | ペルソナ二次判断 | **都度**（問合せ以降） | `[Grokペルソナ]` |
| （番号なし） | 周辺MAP / Canva | 部長内蔵 | — |

## 都度フロー（問合せ以降）

```
第一問合せ → 仲介詳細メール
  →（一次不足なら S1）
  → S5 ペルソナ
  → S3 需給（ターゲット付き）
  → 人間ヒアリング（S3 末尾の質問リスト）
```

正本プロンプト:

- 二次: https://chapro.jp/prompt/321238/6843
- 三次: https://chapro.jp/prompt/321242/7193

## デイリー（本日分）

既存: Gmail確認 → S2 送信 → S1 調査 → S2 探索 → 日報  

追加: **S4 修繕**（エリア×職種 1〜2／日。S2 の直後推奨）

## スキーマ

- 供給・三次表: [`config/kurashift_re_supply_schema.yaml`](../config/kurashift_re_supply_schema.yaml)
- 修繕リスト例: [`config/kurashift_repair_vendor_list.example.yaml`](../config/kurashift_repair_vendor_list.example.yaml)
- Excel 参考: `230_物件調査/★物件調査まとめExcel/231_物件調査.xlsx`「外的調査分析」

## Phase K（KURASHIFT・後続）

| 段階 | 内容 |
|---|---|
| K1 | mail_match が新件名を deal の `summary_json.judgment` へ |
| K2 | deals ドロワー「判断」セクション＋一覧チップ |
| K3 | `/realestate/repair-vendors`（vendors と同型・別ページ） |

流れ: Grok → estate マーカーメール → Jarvis → Supabase → KURASHIFT（司令室）

## paste 正本

| Bot | ファイル |
|---|---|
| 部長 | `config/grok_sanbo_bot_grok_paste.md` |
| S5 | `config/grok_persona_bot_grok_paste.md` |
| S3 | `config/grok_supply_bot_grok_paste.md` |
| S4 | `config/grok_repair_vendor_bot_grok_paste.md` |

貼り方: 各 MD の `` ``` `` ブロック全文を Grok「説明」へ。
