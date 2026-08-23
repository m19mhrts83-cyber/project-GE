# KURASHIFT 第一問合せ依頼 — Grok 反映（索引）

**更新**: 2026-08-23  
**方針**: 追記内容は **各 Bot の paste 正本に統合済み**。このファイル単体を Instructions に貼らない。

## Grok「説明」欄に貼るファイル（正本）

| Bot（Grok UI 名） | ファイル | 貼り方 |
|---|---|---|
| **参謀**（不動産賃貸部長） | `config/grok_sanbo_bot_grok_paste.md` | コードブロック（`` ``` `` 〜 `` ``` ``）**全文**を説明欄へ |
| **物件調査**（S1） | `config/grok_property_bot_grok_paste.md` | 同上 |
| **物件業者開拓**（S2） | `config/grok_vendor_outreach_bot_grok_paste.md` | 同上 |

- **名前・タイトル**は UI の短い欄のまま（paste MD 末尾の「Grok プロフィール設定」参照）
- **説明**＝上記コードブロック内の `# あなたの役割 — …` から末尾まで（2026-08-23 追記込み）
- チャットは **本日分・007から** 等の**当日司令**用。恒久ルールは説明欄のみ

## 今回追記した節（各正本内）

| Bot | 節名 |
|---|---|
| 参謀 | `§KURASHIFT 第一問合せ依頼` · 振り分け表1行 · Gmail「拾う」表1行 |
| 物件調査 | `KURASHIFT 第一問合せ依頼` |
| 業者開拓 | `別Bot（混同禁止）` に4行追加 |

## KURASHIFT 側（参考 · Grok 非掲載）

- 実装: `apps/trade-desk/lib/reInquiryChannel.ts` / `scripts/jarvis_kurashift_re_inquiry_channel.py`
- 状態: `awaiting_grok`（poll スキップ）
- To 解決: Reply-To → From（自己除外）→ vendor → 無ければ handoff
- 初級者手順: `docs/KURASHIFT_Tier1_問合せ_初級者手順.md`

## 混同しない3レーン（要約）

| レーン | 誰 | 何をする |
|---|---|---|
| 仲介メールあり | KURASHIFT | estate → **仲介** へ第一問合せ |
| 仲介なし | S1（参謀が振分） | `[KURASHIFT問合せ依頼]` → Web/調査 |
| 業者開拓 A' | S2 | 地場リスト Web フォーム（approved 文面） |
