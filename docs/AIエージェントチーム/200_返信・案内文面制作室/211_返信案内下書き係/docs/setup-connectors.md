# 連携確認メモ（朝便返信下書き）

更新: 2026-10-11（Phase3 Graph／GHA）

## 実行環境

| 項目 | 正 |
|---|---|
| 製品 | Cursor（Jarvis）＋ GitHub Actions |
| 実行タイプ | **本線: GHA（クラウド）**／保険: Mac ローカル |
| 作業フォルダ（運用ハブ） | admin Drive `★AIエージェントチーム/…/211_返信案内下書き係/` |
| Gitミラー | `~/git-repos/docs/AIエージェントチーム/…/211_返信案内下書き係/` |
| 設計メモ | このフォルダの `CLAUDE.md`（Codex 互換は `AGENTS.md`） |
| 下書き正本 | OneDrive `26_パートナー社への相談/{三桁}/4.*送信下書き.txt`（Graph PUT） |

FlowForge は設計・指示の参照。無人朝便の実行本体は **GHA＋Microsoft Graph**（`docs/Jarvis_OneDrive_Graph.md`）。

## 接続状況（2026-10-11）

| 用途 | 手段 | 状態 |
|---|---|---|
| パートナーメール取込 | Gmail API（admin）／既存 GHA 05:00 | 接続済 |
| やり取り・下書き正本 | **Microsoft Graph**（`MS_GRAPH_*`） | **本線**（読取・PUT 疎通済） |
| ローカル OneDrive path | Finder 同期 | 保険・併写 |
| 要返信トリアージ下地 | `jarvis_night_triage.py` | 既存（heuristic） |
| 朝便オーケストレーション | `jarvis_gha_reply_draft_211.py` | **Phase3** |
| Slack `#report` 等 | Incoming Webhook | 接続済 |
| 返信 From（送信は別） | estate Gmail API | 接続済（人了承後） |

## 標準で賄えないもの（割り切り）

- FlowForge 定義だけでの実行 → 実行は GHA／Jarvis スクリプト
- LINE／iMessage／CHRLINE 取込 → Mac 本線のまま
- OA Bot からの LINE push 送信 → しない（人が貼付）

## 秘密の置き場

- `.env.jarvis_private`（Git 非共有）＋ GitHub Secrets（`MS_GRAPH_*` / Slack webhook）
- refresh 回転: `jarvis_ms_graph_sync_refresh.py`（＋ `--push-gha`）
- チャットにキー・パスワードを貼らない
