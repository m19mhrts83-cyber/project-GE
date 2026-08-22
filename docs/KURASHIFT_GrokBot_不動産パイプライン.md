# KURASHIFT × Grok Bot — 不動産パイプライン（Jarvis + Grok 併走）

更新: 2026-08-22

## 全体像

```mermaid
flowchart TB
  user[松野]
  bucho[不動産賃貸·部長 Bot]
  subgraph dept [Grok 不動産賃貸部署]
    bot1[物件調査 S1]
    bot2[業者開拓 S2]
  end
  user --> bucho
  bucho --> bot1
  bucho --> bot2
  subgraph mail [estate Gmail]
    grokMail["[Grok調査]"]
    vendorReply[不動産会社返信]
  end
  subgraph jarvis [Jarvis / KURASHIFT]
    match[property_mail_match]
    deals[deals UI]
    inquiry[第一問合せ]
  end
  bot2 -->|Web問合せ| vendors[地場不動産]
  vendors --> vendorReply
  bot1 --> grokMail
  grokMail --> match
  vendorReply --> match
  match --> deals
  deals --> inquiry
  inquiry --> vendors
  bot1 -.->|候補1件| deals
```

| 役割 | 担当 | 正本 |
|---|---|---|
| Mac 右腕・参謀 | **Jarvis** | `--apply-marks` / KURASHIFT |
| **Grok 窓口（不動産賃貸部署）** | **部長 Bot** | `config/grok_sanbo_bot_grok_paste.md` |
| ネット調査 | **S1 物件調査**（部長が振分） | `[Grok調査]` → `mail_grok` |
| 地場初回接触 | **S2 業者開拓**（部長が振分） | `config/grok_vendor_outreach_format.md` |
| メール取込・スコア・ファネル | **KURASHIFT** | `property_mail_match.py` / deals |
| 物件詳細の第一問合せ | **KURASHIFT UI** | estate 送信・2段確認 |
| PDF 添付の中身読取 | **未実装（Phase PDF）** | 下記 |

---

## 部長 Bot — 不動産賃貸部署（2026-08-22）

**Grok Bot 名**: **不動産賃貸部長**（短く **部長**）  
**部署**: 不動産賃貸のみ（他テーマは将来別部長）  
**Instructions**: `config/grok_sanbo_bot_grok_paste.md`  
**運用**: `config/grok_sanbo_bot.md`

松野は Grok では **部長だけ** に指示。部長が S1/S2 等へ振り分け・連携。  
**Mac 同期**: 部長が `[Grok部長]` 日報を **estate メール** へ送信 → Jarvis が `jarvis_grok_bucho_mail_apply.py --apply` で `--mark` 反映（手動コピー不要）。

**初回 / キュー補充**: `--batch-week --grok-kickoff` → **部長** に貼る（枯渇時は部長が促す）。  
**毎日**: 部長スレッドで `本日分`（土日含む）。**土 or 日** に部長が `[Grok部長] 週次` メール。

---

## Bot 1 — 物件調査（実装済・本線）

- テンプレ: `config/grok_property_report_format.md`
- **Grok Instructions 貼り付け**: `config/grok_property_bot_grok_paste.md`
- 取込: `jarvis_kurashift_property_mail_match.py --grok-only --apply`
- deals「Grok調査用コピー」で候補を Bot に渡す
- Step A 手順: `docs/KURASHIFT_grok_first_stepA.md`

---

## Bot 2 — 業者開拓（試行・次フェーズ）

**Grok Bot 名**: **物件業者開拓**  
**Instructions**: `config/grok_vendor_outreach_bot_grok_paste.md`（コードブロックを Grok に貼る）

**目的**: 戸建ては地場不動産経由。リストへ **順次問合せ** + Grok **日次 N 件探索** で表を増やす。

| 操作 | 担当 | コマンド / 正本 |
|---|---|---|
| リスト取込 | Jarvis | `--import-xlsx` → `kurashift_re_vendor_list.yaml` |
| **週次バッチ** | Jarvis → Grok | `--batch-week --grok-kickoff`（7日×Phase上限） |
| 日次のみ | Jarvis → Grok | `--next 3`（enriched JSON） |
| 結果記録（単件） | Jarvis | `--mark ID --status contacted` |
| **結果記録（一括）** | Jarvis | `--apply-marks grok_summary.txt`（Grok 週次サマリー） |
| 日次探索 | Grok Bot | `--grok-discovery-prompt` → `--merge-append` |
| **返信・物件** | Jarvis / KURASHIFT | `property_mail_match` → deals（**ブロックしない**） |
| **返信下書き・送信** | **Jarvis Dashboard** | `docs/Jarvis_Dashboard_業者返信下書き.md` |

**送信**: Bot2 は approved A'-v2 で **Web フォーム送信まで自動**（Phase 1=3社/日・都度承認不要）。

**週次運用（2026-08-23）**: `--batch-week` JSON を Grok に渡す（初回・枯渇時）→ **毎日**「本日分」（土日含む）。**土 or 日** に `[Grok部長] 週次`。キュー枯渇時は部長が Jarvis 再生成を促す。系列 skip は **同一問合せ URL** のみ。

正本: `config/kurashift_re_vendor_list.yaml`（gitignore）  
CLI: `scripts/jarvis_kurashift_vendor_list.py`  
Grok 追記形式: `config/grok_vendor_discovery_append.md`

---

## 現行の判断基準（property_mail_match）

**入力**: Gmail **件名 + 本文テキストのみ**（PDF 添付は未読）

| 段階 | 条件 | 結果 |
|---|---|---|
| スコア | 愛知/岐阜/三重ヒント、戸建、利回り、価格500〜3500万 等で加点 | `match_score` |
| 明確除外 | 件名ノイズ、区分のみ、都内のみ、スコア下限未満 | `passed` + `auto_pass_reason` |
| Grok 上書き | `聞く価値=見送り` または `ハザード=除外`（聞く以外） | `passed` |
| Grok 加点 | 聞く・土地100%・路線価・駐車場・HZ | スコア調整 |

買い進め条件の正: `kurashift_buy_plan_criteria` + Notion（戸建・20%・300万・土地値60%・愛知中心）。

**Grok 調査後**の最終判断は deals 上の `grok.*` + 第一問合せ返信（PDF 含む）を人が見る。

---

## Phase PDF — 添付読取（未実装・要目合わせ）

**現状**: `property_mail_match` は **PDF を開かない**。価格・土地面積は本文の正規表現（`(\d{2,5})\s*万`、`土地面積` 行）のみ。

**懸念（ユーザー指摘）**: 不動産会社返信は PDF 多め → 本文だけでは不足。

**提案ロードマップ**

| Phase | 内容 |
|---|---|
| PDF-0 | 返信メールの PDF を Gmail API で `kurashift_re_deal_attachments/` に保存（deal_id 紐付け） |
| PDF-1 | Mac: `pdfplumber` / Gemini で 価格・土地面積・構造 を抽出 → `summary_json.extracted` |
| PDF-2 | 抽出結果を deals UI 表示 + スコア再計算（任意） |
| PDF-3 | Grok Bot に PDF 要約を `[Grok調査]` 形式で estate 送信（Jarvis 取込と同型） |

**目合わせポイント**

- PDF から自動確定する項目 vs 人確認必須項目
- 健美家メルマガ型（本文に十分情報） vs 地場 PDF のみ型の優先度

---

## 実装順（Jarvis + Grok 併走）

1. ✅ 倍率→固定資産税依頼、Grok調査コピー、路線/HZ 拡張
2. ✅ 業者リスト YAML + Grok 業者開拓テンプレ（`status: approved`）
3. ✅ estate `[Grok調査]` → `--grok-only --apply`（朝バンドル含む）→ deals 3件取込済（2026-08-22）
4. ✅ Phase PDF-0（`jarvis_kurashift_re_deal_pdf_fetch.py` + deals UI 添付件数）
5. ✅ E2E パイプライン（fixture PASS）— `jarvis_kurashift_grok_e2e_runner.py` / `docs/KURASHIFT_re_inquiry_E2E_checklist.md`
6. ⏳ 本番第一問合せ（`聞く` 実物件待ち）— `docs/KURASHIFT_grok_first_stepA.md` §5
7. ⏳ Phase PDF-1（PDF 中身抽出）
8. ✅ 業者開拓送信（Bot2 週次バッチ・Phase 1 試運転 001-003 済 2026-08-22）

---

## 業者返信（milestone）— ブロックしない

問合せ後に業者から **質問・物件PDF** が estate に届くのは成功。Gmail ブロック／拒否リストには載せない。

```mermaid
flowchart LR
  bot2[Bot2 初回問合せ] --> vendor[地場業者]
  vendor --> reply[estate 返信]
  reply --> match[property_mail_match]
  match --> deals[deals]
  deals --> grok[Bot1 Grok調査]
  deals --> inquiry[第一問合せ UI]
```

| 返信 | 裁き |
|---|---|
| 予算・エリア等の質問 | estate 短文返信 + `--status replied` |
| 物件資料 | deals 取込 → Grok → ファネル |
| スパム・無関係 | 物件 `passed` のみ（業者ブロックとは別） |
