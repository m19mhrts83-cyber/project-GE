# Jarvisダッシュボード更新係

複数ツールから同じフォルダを開いて使う指示書。直した運用知見はこのファイルに追記する。

## AIオートメーション（作業フロー）

- **FlowForge（開く）**: [flow_wkFbA0v6bq3ouq9dmpX-cxc1](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_wkFbA0v6bq3ouq9dmpX-cxc1)
- 一覧・進捗: [`15_FlowForge全体系_進捗_20261010.md`](../../15_FlowForge全体系_進捗_20261010.md)
- 設計の流れ図（あれば）: [`flow.md`](./flow.md)

## 1. 役割

- やること: Jarvisダッシュボード（triage/watch/cards/メトリクス等）の定期投影・更新サイクルを回す。松野が見たい画面が鮮度落ちしないようにする。
- やらないこと: 対外送信・秘密のチャット掲出・UIの独断大幅改修（改修案は#consult）。

## 2. 動き出す合図（4種のいずれか）

- [ ] 人が頼む
- [x] 時間（スケジュール）: 時間（例: 朝・パートナー確認後・夜間）。失敗見回り。
- [ ] 何かが届いたら（イベント）:
- [x] 変化・失敗を見回ったら: 投影失敗・鮮度切れ

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| チャット・検索 | ○ | |
| 外部連携（API/MCP） | ○ | Supabase投影・所定API |
| CLI | ○ | 定めた runner / push |
| ブラウザ | △ | 確認用 |
| 画面操作 | × | 原則しない |

**人が確かめる（必須）**: お金・外に出す・消す。UIの破壊的変更。

## 4. 報告先

| 種別 | 行き先 |
|---|---|
| 問題あり（投影失敗・鮮度48h超等） | Slack `#ops`（1〜2行） |
| 問題なし | **投稿しない**（`logs/` のみ） |
| 要判断・相談 | Slack `#consult` |
| Webhook（秘密） | env キー名のみ |

### Slack 書き出し（FRIDAY／Jarvis 共通）

| ch | いつ |
|---|---|
| `#report` | 完了・定型・生存確認 |
| `#consult` | 要判断。末尾「次の担当」3行必須 |
| `#ops` | 障害・失敗・枠切れ |

`#consult` 末尾: `次: Grokで続行 | Jarvisに依頼 | 人判断のみ` ＋ `担当メモ` ＋ `橋渡し`  
正本: [`38_Slack書き出し_FRIDAY_Jarvis_20261018.md`](../../38_Slack書き出し_FRIDAY_Jarvis_20261018.md) · [`36_`](../../36_Slack_consult手渡し_次の担当_20261018.md)

## 5. 成果物の置き場

- このフォルダ内: `logs/`
- 外部正本: Jarvisダッシュボード / KURASHIFT（Vercel）・Supabase投影

## 6. 作業手順（チェックリスト）

1. 対象ページ／投影ジョブを確認
2. runner / push 系を実行（dry-run可）
3. **要フォロー時だけ** Slack #ops へ短文。OKは logs のみ
4. 失敗は logs/ に残す

### 一括（Phase L）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_ui_cycle_814_815.py --agent 814 --post
# 投影も回す: --push --post
# OKでも投稿したい検証: --force-post
```

本線時間: launchd `dashboard-push` **12:30**（ui_cycle は問題時のみ `#ops`）。  
停止: `JARVIS_UI_CYCLE_DISABLE=1`

## 7. 改善ログ

| 日付 | 変更 |
|---|---|
| 2026-10-09 | スタブ作成（俯瞰UI更新担当） |
| 2026-10-11 | Phase L: `jarvis_ui_cycle_814_815.py`＋dashboard-push 後 `#ops` |
| 2026-10-16 | `#ops` は要フォロー時のみ（OKは投稿スキップ） |
