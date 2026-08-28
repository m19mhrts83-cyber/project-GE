# Grok 組織索引 — AI三柱＋全部署

**更新**: 2026-08-28  
**方針**: 各 Bot の Instructions 正本は下表の paste。本ファイルは索引のみ。

## AI三柱（松野直属）

```
松野（司令塔）
├─ Jarvis ………… 右腕（Mac 実行 · Cursor）
├─ ホーク参謀 … 左腕（Grok · Bot 指揮 · 参謀室）
└─ カール ……… 第三柱（Gemini · ★Journal 振り返り）
```

| 柱 | 愛称 | 本体 | 入口 |
|---|---|---|---|
| 右腕 | Jarvis | Cursor / Mac | Cursor 直接 |
| 左腕 | **ホーク** | Grok 参謀 Bot | `@ホーク` · 参謀室 |
| 第三柱 | カール | Gemini | Workspace 会話 · Journal 見出し「カール参謀」 |

**1行**: 実行→Jarvis｜戦略・Bot→ホーク｜振り返り→カール

## Grok 部署一覧

| 部署 | 統括／部長 | チャンネル（推奨） | paste 正本 |
|---|---|---|---|
| 参謀室 | **ホーク参謀** | 参謀室 | `config/grok_sanbo_bot_grok_paste.md` |
| 不動産賃貸 | **不動産賃貸部長** | 不動産Dailyチーム | `config/grok_realestate_bucho_grok_paste.md` |
| 家族コーチ | 家族コーチ統括 | 家族コーチングチーム | `config/grok_family_manager_grok_paste.md` |
| アプリ開発 | アプリ開発統括 | アプリ開発チーム | `config/grok_app_dev_manager_grok_paste.md` |
| 総務計画 | 総務計画T統括 | **2ch**（下記） | `config/grok_somu_keikaku_manager_grok_paste.md` |
| パートナーDX | パートナーDX統括 | パートナーDXコーチングチーム | `config/grok_partner_dx_manager_grok_paste.md` |
| 天気 | 天気お知らせ | 天気お知らせ（**ホーク傘下**） | `config/grok_weather_bot_grok_paste.md` |

## 総務計画 2ch

| ch | メンバー |
|---|---|
| **コーチ ch** | 総務計画T統括 ＋ コーチ5（磯崎・田中・山下・川畑・慎二） |
| **アドバイザー ch** | アドバイザー5（中島・太田章嗣・今井・大原・蜂谷） |

索引: `config/grok_somu_keikaku_coaching_handoff_paste.md`

## Drive 3層（JarvisBox）

| 層 | パス | 誰 |
|---|---|---|
| L1 | `20_outbox_to_grok/` | Jarvis → ホーク |
| L2 | ホーク振り分け | → `outbox_to_teams/{re,family,…}/` |
| L3 | `outbox_to_teams/re/` 等 | 部長／統括／天気 |
| 返信 | `10_inbox_from_grok/` | → Jarvis poll |

設定: `config/kurashift_grok_bridge_folders.yaml`  
ホークルーティン: `config/grok_hawk_routine_Jarvisボックス.md`

## JarvisBox パック（Drive）

| パック | パス |
|---|---|
| 組織再編・ホーク | `30_shared_working/2026-08-28_組織再編_ホーク参謀/` |
| 天気Bot | `30_shared_working/2026-08-28_天気Bot/` |
| パートナーDX | `30_shared_working/2026-08-28_パートナーDXコーチング_Bot新設/` |
| 総務計画 | `30_shared_working/2026-08-28_総務計画コーチング_Bot新設/` |

## Grok UI 作業順（目安）

1. ホーク参謀 Bot → 参謀室
2. 不動産部長 Bot（既存 sanbo UI を差し替え）
3. 天気Bot（6:30 · ホーク傘下）
4. 総務 2ch ＋ 11 Bot
5. パートナーDX 1ch ＋ 3 Bot
