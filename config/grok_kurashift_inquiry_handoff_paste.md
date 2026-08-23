# KURASHIFT / Grok Bot — paste 索引

**更新**: 2026-08-24  
**方針**: 追記内容は **各 Bot の paste 正本に統合済み**。このファイル単体を Instructions に貼らない。

## Grok「説明」欄に貼るファイル（正本）

| Bot（Grok UI 名） | 社員 | ファイル | 貼り方 |
|---|---|---|---|
| **参謀**（不動産賃貸部長） | （番号外） | `config/grok_sanbo_bot_grok_paste.md` | コードブロック全文を説明欄へ |
| **物件調査** | S1 | `config/grok_property_bot_grok_paste.md` | 同上 |
| **物件業者開拓** | S2 | `config/grok_vendor_outreach_bot_grok_paste.md` | 同上 |
| **需給三次判断** | S3 | `config/grok_supply_bot_grok_paste.md` | 同上 |
| **修繕業者開拓** | S4 | `config/grok_repair_vendor_bot_grok_paste.md` | 同上 |
| **ペルソナ二次判断** | S5 | `config/grok_persona_bot_grok_paste.md` | 同上 |

- **名前・タイトル**は UI の短い欄のまま（paste MD 末尾の「Grok プロフィール設定」参照）
- **説明**＝上記コードブロック内の `# あなたの役割 — …` から末尾まで
- チャットは **本日分・007から** 等の**当日司令**用。恒久ルールは説明欄のみ

## 設計（Phase 1）

- `docs/KURASHIFT_供給_ペルソナ_修繕Bot_設計_20260824.md`
- 都度: 問合せ以降 → S5 → S3 → 人間ヒアリング
- デイリー: `本日分` = S2 → S4 → S1 → 探索

## KURASHIFT 第一問合せ（参考 · Grok 非掲載）

- 実装: `apps/trade-desk/lib/reInquiryChannel.ts` / `scripts/jarvis_kurashift_re_inquiry_channel.py`
- 状態: `awaiting_grok`（poll スキップ）
- 初級者手順: `docs/KURASHIFT_Tier1_問合せ_初級者手順.md`

## 混同しないレーン（要約）

| レーン | 誰 | 何をする |
|---|---|---|
| 仲介メールあり | KURASHIFT | estate → **仲介** へ第一問合せ |
| 仲介なし | S1（参謀が振分） | `[KURASHIFT問合せ依頼]` → Web/調査 |
| 業者開拓 A' | S2 | 地場リスト Web フォーム（approved 文面） |
| 二次・三次 | S5 → S3 | `[Grokペルソナ]` → `[Grok需給]` |
| 修繕候補 | S4 | `[Grok修繕候補]`（電話しない） |
