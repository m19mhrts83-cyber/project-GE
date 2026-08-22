# Grok 業者開拓 Bot — 作業説明（Phase 4 正本）

**Grok Bot 名（推奨）**: **物件業者開拓**（Bot2）  
**Instructions 貼り付け**: `config/grok_vendor_outreach_bot_grok_paste.md`（コードブロック内を Grok に貼る）

**status**: `grok_vendor_outreach_format.md` が **approved** のときのみ送信可。  
**送信**: **A'-v2 固定・リスト3社/日・都度承認不要**（2026-08-22 松野委任）。  
**別Bot**: 物件調査（`[Grok調査]` → estate）は `config/grok_property_report_format.md`（Bot1）

## 毎日の流れ（1日3件）

1. Mac で次の3社を取得（ユーザーまたは Jarvis が実行）:

```bash
cd ~/git-repos
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_vendor_list.py --next 3
```

2. JSON を Bot2 に渡す。Bot2 が各社について:
   - `contact_url` または `url` の **Web 問合せフォーム**を開く
   - **本文**: `config/grok_vendor_outreach_format.md` の A'-v2（list_region でエリア差替）
   - **返信先**: matsuno.estate@gmail.com（必須）
   - **送信まで実行**（approved 条件内）

3. 送信後、Mac で記録:

```bash
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_vendor_list.py \
  --mark {id} --status contacted --note "個人Web送信(estate) YYYY-MM-DD"
```

4. **Jarvis / パートナー確認**で estate 返信を取込:

```bash
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_property_mail_match.py --apply
```

## 返信・milestone 業者の裁き

**ブロックリスト対象ではない。** 問合せの目的どおりの返信。

| 種類 | やること |
|---|---|
| 条件質問のみ | estate から短文返信（Jarvis 下書き）。`--status replied` |
| 物件 PDF／リンク | `property_mail_match` → deals → 必要なら Bot1 `[Grok調査]` |
| 登録完了・挨拶 | `replied` 記録。物件待ち |
| 無関係スパム | 物件 `passed` または skip。業者拒否リストとは別 |

- **auto_pass** = 物件が条件外（エリア・区分等）。**業者をブロックする意味ではない**。
- 第一問合せ（具体物件）は **KURASHIFT deals UI**（2段確認）。Bot2 文面とは別。
- Bot2 は **返信対応しない**（送信専用）。

## 禁止

- `status: draft` の文面で送らない
- 利回り%・土地値%をフォームに大書き
- 329社一括送信
- リスト外・approved 改変
- 具体物件への第一問合せ（KURASHIFT deals 経由）

## 新規探索（問合せは送らない）

```bash
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_vendor_list.py --grok-discovery-prompt
# → YAML 追記 → --merge-append
```

## リスト概要

```bash
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_vendor_list.py --summary
```
