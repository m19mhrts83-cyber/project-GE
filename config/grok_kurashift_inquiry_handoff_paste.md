# KURASHIFT / Grok Bot — paste 索引

**更新**: 2026-08-27  
**方針**: 追記内容は **各 Bot の paste 正本に統合済み**。このファイル単体を Instructions に貼らない。

## Grok「説明」欄に貼るファイル（正本）

| Bot（Grok UI 名） | 社員 | ファイル | 貼り方 |
|---|---|---|---|
| **参謀**（不動産賃貸部長） | （番号外） | `config/grok_sanbo_bot_grok_paste.md` | コードブロック全文を説明欄へ |
| **物件調査** | S1 | `config/grok_property_bot_grok_paste.md` | 同上 |
| **物件業者開拓** | S2 | `config/grok_vendor_outreach_bot_grok_paste.md` | 同上 |
| **需給三次判断** | S3 | `config/grok_supply_bot_grok_paste.md` | 同上 · **成果物は Obsidian `☆Real_Estate_Pick`（メールしない）** |
| **修繕業者開拓** | S4 | `config/grok_repair_vendor_bot_grok_paste.md` | 同上 |
| **管理会社開拓** | S9 | `config/grok_mgmt_vendor_bot_grok_paste.md` | 同上 |
| **ペルソナ二次判断** | S5 | `config/grok_persona_bot_grok_paste.md` | 同上 |
| **買付交渉** | S6 | `config/grok_deal_negotiation_bot_grok_paste.md` | 同上 |
| **融資相談** | S7 | `config/grok_loan_bot_grok_paste.md` | 同上 |
| **物件ライフライン** | S8 | `config/grok_property_util_bot_grok_paste.md` | 同上 |

- **名前・タイトル**は UI の短い欄のまま（paste MD 末尾の「Grok プロフィール設定」参照）
- **説明**＝上記コードブロック内の `# あなたの役割 — …` から末尾まで
- **S3 置き場正本**: `config/kurashift_obsidian_artifacts.yaml`
- チャットは **本日分・007から** 等の**当日司令**用。恒久ルールは説明欄のみ
- **未作成の UI 手順**: `config/grok_remaining_bots_setup.md`（S6/S7/S8）

## 設計（Phase 1＋フェーズ拡張）

- `docs/KURASHIFT_供給_ペルソナ_修繕Bot_設計_20260824.md`
- `docs/KURASHIFT_Grok_不動産フェーズBot_設計_20260824.md`
- 都度: 問合せ以降 → S5 → S3 →（購入後）S6 → S7 →（開通）S8
- デイリー: `本日分` = S2 → S4 → S1キュー → 業者探索。**物件自律探索** = 別ルーティン `S1物件探し`（10:30）
- 証憑 Drive: `docs/KURASHIFT_S1問合せ証憑_Drive_20260825.md`
- ルーティン: `config/grok_bucho_routine_本日分.md` · `config/grok_bucho_routine_S1物件探し.md`

## KURASHIFT 第一問合せ（参考 · Grok 非掲載）

- 実装: `apps/trade-desk/lib/reInquiryChannel.ts` / `scripts/jarvis_kurashift_re_inquiry_channel.py`
- 状態: `awaiting_grok`（poll スキップ）
- 初級者手順: `docs/KURASHIFT_Tier1_問合せ_初級者手順.md`

## 返信後・内見判断（`[Grok内見判断]`）

問合せ返信が `has_reply` になったあと、Jarvis が調査シート項目を抽出し、下書きを置く。

| 項目 | 正本 |
|---|---|
| 抽出 YAML | `config/kurashift_re_research_fields.yaml` |
| スクリプト | `scripts/jarvis_kurashift_re_reply_extract.py` |
| 下書き出力 | `.jarvis_state/kurashift_viewing_judgment_drafts/<deal_id>.md` |
| 件名 | `[Grok内見判断] {物件名}` |
| 担当 | **S1 物件調査**（必要なら参謀が S5→S3 に振分） |
| 出力ラベル | `内見: 行く|保留|見送り`（1行）＋理由3点以内 |

運用:

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_reply_extract.py --apply --emit-grok-mail-draft
```

poll 成功時も extract＋下書きを soft-fail で実行する。下書きを estate→自分宛で送る／チャンネルに貼るのはユーザー確認後（対外送信ルール）。

購入手前ストック: Notion `DB_物件購入検討(購入手前)` ＋ KURASHIFT deals（`has_reply` / 内見候補）。Drawer の運営フォーム→809→内見は従来どおり。

## 混同しないレーン（要約）

| レーン | 誰 | 何をする |
|---|---|---|
| 仲介メールあり | KURASHIFT | estate → **仲介** へ第一問合せ |
| 仲介なし | S1（参謀が振分） | `[KURASHIFT問合せ依頼]` → Web/調査 |
| 返信後・内見 | S1（→S5/S3） | `[Grok内見判断]` → 行く/保留/見送り |
| 業者開拓 A' | S2 | 地場リスト Web フォーム（approved 文面） |
| 二次・三次 | S5 → S3 | `[Grokペルソナ]` → **Obsidian `☆Real_Estate_Pick`**（S3・メールしない） |
| 買付・融資 | S6 / S7 | `[Grok買付]` / `[Grok融資]` |
| ライフライン（電水ネットガス） | S8 | `[Grokライフライン]` |
| 修繕候補 | S4 | `[Grok修繕候補]`（電話しない） |
| アプリ | アプリ開発統括 | 別部署 |