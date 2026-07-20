# WeStudy 採点自動化 — バージョン履歴

**相手先向けの版（V1.0 起点）の正本はスプレッドシートの `バージョン履歴` シート。**  
本ファイルは開発中のメモおよび提供後の写し用。

## 提供ステータス

| 項目 | 状態 |
|---|---|
| 相手先への提供 | **V1.0 提供開始**（2026-06-27） |
| 正本（Google SS） | https://docs.google.com/spreadsheets/d/1ZX2xVBpUAtQOB6wz4_CpcZ3lIxhVdtrzS_dGd1yqPkQ/edit |
| Drive フォルダ | https://drive.google.com/drive/folders/1QI-r0upkP335FZNQ8q99pe7FpPfTt1h_ |
| OneDrive バックアップ（V1.0） | `WeStudy_採点自動化_V1.0_20260627.xlsx` + `04_gas_Code_V2.1_V1.0.gs` |
| 開発用 GAS ファイル | `04_gas_Code_V2.1.gs` |

## 相手先向け版（`バージョン履歴` シート）

| 版 | 日付 | 変更内容 | 備考 |
|---|---|---|---|
| V1.0 | 2026-06-27 | 初回提供。Google SS+GAS。CSV取込（WeStudy_for_scoring.csv）・採点実行・補正学習・ヘッダー初期化。Gemini 2.5-flash。O列最終点/N列自動。 | 神大家向け（目黒さん） |

以降の変更は **V1.1, V1.2 …** をスプレッドシートの `バージョン履歴` タブに1行ずつ追記。

---

## 開発リポジトリ内ファイル版（提供版 V1.x とは別）

| ファイル | 版 | メモ |
|---|---|---|
| `04_gas_Code_V2.1.gs` | dev V2.1 | V1.0 提供時点の GAS 本体 |
| `16_deploy_gas.py` | dev V1.2 | |
| `18_export_spreadsheet_backup.py` | dev V1.0 | OneDrive xlsx バックアップ |

ルール: `~/git-repos/.cursor/rules/jarvis-version-filename.mdc`
