# Grok 組織索引 — AI三柱＋全部署

**更新**: 2026-08-29  
**方針**: 各 Bot の Instructions 正本は下表の paste。本ファイルは索引のみ。

## AI三柱（松野直属）

```
松野（司令塔）
├─ Jarvis ………… 右腕（Mac 実行 · Cursor）
├─ ホークアイ（参謀） … 左腕（Grok · Bot 指揮 · 参謀室）
└─ カール ……… 第三柱（Gemini · ★Journal 振り返り）
```

| 柱 | 愛称 | 本体 | 入口 |
|---|---|---|---|
| 右腕 | Jarvis | Cursor / Mac | Cursor 直接 |
| 左腕 | **ホークアイ** | Grok 参謀 Bot | `@ホークアイ` · 参謀室 |
| 第三柱 | カール | Gemini | Workspace 会話 · Journal 見出し「カール参謀」 |

**1行**: 実行→Jarvis｜戦略・Bot→ホークアイ｜振り返り→カール

## Grok 実行の度合い（ブロック別 · 2026-08-28）

**全体デフォルト**は整理・移譲・助言・日報。**ブロックでカーディロード（実務量）が違う。**

| ブロック | Grok の役割 | 実行の度合い | Jarvis／松野 |
|---|---|---|---|
| **ホークアイ（参謀）** | 横断 · QOL · 委譲 | 低（振り分け中心） | 方針 |
| **不動産賃貸部長** | Daily · S1–S9 · 日報 | **高（Grok内の実務実行）** | 最終判断 · 送信承認 · `--apply` |
| **リソース経営部長** | brush-up · 税務論点 · 制約 | 中（論点整理 · 制約出力） | 税理士 · 振込 |
| **家族コーチ統括** | 材料読取 · 振り分け · QOL | 中（助言 · 委譲） | 子どもへの実行 |
| **アプリ開発統括** | 週次 · 怪しさ · 壁打ち | **低（提案・アドバイスまで）** | コード · PR · デプロイ |
| **天気お知らせ** | 朝6:30 · ch直投 | 低（定型） | Jarvis が weather/ に材料 |

**不動産の「実行」例（Grok）**: 本日分パック · S1–S9 連携 · 調査・文案 · `[Grok部長]` 日報。  
**Grok が触らない線**: 振込 · 秘密 · deals UI · 承認なし対外送信。

**アプリの位置づけ**: 改善提案・実装方針・Jarvis向けカード。**コード実装は Jarvis のみ。**

## Grok 部署一覧

| 部署 | 統括／部長 | チャンネル（推奨） | paste 正本 |
|---|---|---|---|
| 参謀室 | **ホークアイ（参謀）** | 参謀室 | `config/grok_sanbo_bot_grok_paste.md` |
| 不動産賃貸 | **不動産賃貸部長** | 不動産Dailyチーム | `config/grok_realestate_bucho_grok_paste.md` |
| **リソース経営** | **リソース経営部長** | **リソース経営チーム** | `config/grok_resource_keiei_bucho_grok_paste.md` |
| 家族コーチ | 家族コーチ統括 | 家族コーチングチーム | `config/grok_family_manager_grok_paste.md` |
| アプリ開発 | アプリ開発統括 | アプリ開発チーム | `config/grok_app_dev_manager_grok_paste.md` |
| 総務計画 | 総務計画T統括 | **2ch**（下記） | `config/grok_somu_keikaku_manager_grok_paste.md` |
| パートナーDX | パートナーDX統括 | パートナーDXコーチングチーム | `config/grok_partner_dx_manager_grok_paste.md` |
| 天気 | 天気お知らせ | 天気お知らせ（**ホークアイ傘下 · 直投**） | `config/grok_weather_bot_grok_paste.md` |

## 総務計画 2ch

| ch | メンバー |
|---|---|
| **コーチ ch** | 総務計画T統括 ＋ コーチ5（磯崎・田中・山下・川畑・慎二） |
| **アドバイザー ch** | アドバイザー5（中島・太田章嗣・今井・大原・蜂谷） |

索引: `config/grok_somu_keikaku_coaching_handoff_paste.md`

## リソース経営 · 家族空手（handoff）

| ブロック | handoff |
|---|---|
| リソース経営 | `config/grok_resource_keiei_handoff_paste.md` |
| 家族（含 空手） | `config/grok_family_coaching_handoff_paste.md` |

## Drive 3層（JarvisBox）

| 層 | パス | 誰 |
|---|---|---|
| L1 | `20_outbox_to_grok/` | Jarvis → ホークアイ |
| L2 | ホークアイ振り分け | → `outbox_to_teams/{re,resource,family,…}/` |
| L3 | `outbox_to_teams/re/` 等 | 部長／統括／天気 |
| 返信 | `10_inbox_from_grok/` | → Jarvis poll |

設定: `config/kurashift_grok_bridge_folders.yaml`  
ホークアイルーティン: `config/grok_hawk_routine_Jarvisボックス.md`

## フォーク原則（JarvisBox 必須）

| 側 | やること |
|---|---|
| **Grok** | Bot 内で整理・文案・委譲。Jarvis へは **`10_inbox_from_grok/`** に MD |
| **Jarvis** | Mac 実行・取込・送信承認。Grok へは **`jarvis_bucho_outbox_write.py --target …`** |

松野のチャットコピペは **運用正本にしない**。詳細: `config/grok_jarvisbox_fork_policy.md` · ルール `jarvis-grok-jarvisbox-fork.mdc`

## JarvisBox パック（Drive）

| パック | パス |
|---|---|
| 組織再編・ホーク | `30_shared_working/2026-08-28_組織再編_ホーク参謀/`（不動産部長貼付: **`B1_不動産部長_Instructions_全文.txt`**） |
| 天気Bot | `30_shared_working/2026-08-28_天気Bot/` |
| **リソース経営部長** | `30_shared_working/2026-08-28_リソース経営部長/` |
| **空手アドバイザー** | `30_shared_working/2026-08-28_空手アドバイザー/` |
| パートナーDX | `30_shared_working/2026-08-28_パートナーDXコーチング_Bot新設/` |
| 総務計画 | `30_shared_working/2026-08-28_総務計画コーチング_Bot新設/` |

## Grok UI 作業順（目安）

| # | 項目 | UI | Driveパック |
|---|---|---|---|
| 1 | **ホークアイ（参謀）** | ✅ 済 | `2026-08-28_組織再編_ホーク参謀/` |
| 2 | 不動産部長 | ✅ 済 | 同 · `B1_不動産部長_Instructions_全文.txt` |
| 3 | 天気Bot（6:30） | ✅ 済 | `2026-08-28_天気Bot/` |
| 4 | **リソース経営部長** | ✅ Bot＋**月次ルーティン済**（2026-08-29） | `2026-08-28_リソース経営部長/` |
| 5 | **空手・ちかげ・家族統括** | ✅ 済 | 空手 / ちかげ / 家族コーチ_Obsidian直読み |
| 6 | **パートナーDX** 1ch＋3 Bot | ✅ 済（2026-08-28） | `2026-08-28_パートナーDXコーチング_Bot新設/` |
| 7 | **総務計画** 2ch＋11 Bot | ✅ 済（2026-08-28） | `2026-08-28_総務計画コーチング_Bot新設/` |

**並行チェックリスト**: `30_shared_working/2026-08-28_組織再編_ホーク参謀/00_残作業_並行_20260829.md`

### B1 抽出（Jarvis）

```bash
~/selenium_env/venv/bin/python scripts/jarvis_grok_paste_to_b1_txt.py \\
  config/grok_shift_ai_advisor_grok_paste.md -o /path/B1_シフトAI_Instructions_全文.txt
```

ネスト ``` あり（不動産部長等）は **`B1_*_全文.txt` 正本**のみ使う。
