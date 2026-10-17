# Vポイント・テイチャン係（614）

複数ツール（Claude Code / Cursor / Codex / GenCode / FlowForge 等）から同じフォルダを開いて使う指示書。  
直した運用知見は**このファイルに追記**する（チャットだけの修正にしない）。

ジャンル: **リソース・家計**。隣係: **612** 年会費ガード／**613** Zaim鮮度。ダッシュ出口は `/vpoint`（テイチャン欄）。

## AIオートメーション（作業フロー）

- **FlowForge**: 作り込み待ち（registry に URL を追記する）
- 一覧・進捗: [`15_FlowForge全体系_進捗_20261010.md`](../../15_FlowForge全体系_進捗_20261010.md)
- 設計の流れ図: [`flow.md`](./flow.md)
- 実装本線: `scripts/jarvis_teiki_barai_chance.py` ＋ `launchd/teiki_draw_runner.sh`
- Slack 短報: `scripts/jarvis_teiki_slack_report.py`

## 設計ゲート（4点）

| 柱 | 内容 |
|---|---|
| **入口** | Vpass（テイチャン SSO）・`teiki_barai_chance.json`・券数画面 |
| **確認** | 抽選は自動。規約未同意・ログイン失敗・迷うサービス追加だけ人 |
| **履歴** | Slack `#report` 控え `reports/`・state JSON・ダッシュ `/vpoint` |
| **停止** | `JARVIS_TEIKI_BARAI_DISABLE=1`／state `disabled`／`JARVIS_TEIKI_SLACK_REPORT_DISABLE=1` |

## 1. 役割

- **やること**
  1. 定期払いチャンス（テイチャン）の券確認・あれば抽選
  2. 結果を Jarvis `/vpoint` に投影（`--push`）
  3. **同じ結果を Slack `#report` に短報**（自動で動いたことがチャットでも分かる）
  4. （将来）Vポイント cadence／月次ウィンドウC の要約も本係に寄せる
- **やらないこと**
  - 年会費ガード本体（**612**）・Zaim 鮮度・費目（**613**）
  - 秘密（VPASS_*）の再掲・対外送信

## 2. 動き出す合図

- [x] **時間（本線）**: 月・木 10:15 JST — `teiki_draw_runner.sh`
- [x] **朝オープン取りこぼし**: `jarvis_morning_mac_refresh`（due 時）
- [x] **人が頼む**: 「テイチャン確認して」「抽選して」
- [ ] Vポイント定例の Slack 短報（cadence／ウィンドウC）— 次波

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| CLI | ○ | `jarvis_teiki_barai_chance.py` / `jarvis_teiki_slack_report.py` |
| ブラウザ／CDP | ○ | Mac Chrome 専用プロファイル（終了時 auto-quit） |
| Slack Webhook | ○ | `#report`（失敗時 `#ops`） |

**秘密**: `.env.jarvis_private` の `VPASS_*` / `SLACK_WEBHOOK_AI_TEAM_*`。本フォルダに値を書かない。

## 4. 報告先

| 種別 | 行き先 |
|---|---|
| 定時・結果 | Slack `#report`（【614 Vポイント・テイチャン係】） |
| 失敗 | Slack `#ops` |
| 人が見る画面 | https://jarvis-dashboard-amber.vercel.app/vpoint#teiki-barai |

## 5. 成果物の置き場

| 種類 | 場所 |
|---|---|
| state | `~/git-repos/.jarvis_state/teiki_barai_chance.json` |
| Mac ログ | `~/Library/Logs/jarvis_teiki/` |
| Slack 控え | 本フォルダ `reports/` |

## 6. 作業手順

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
# 本線相当（ダッシュ＋Slack）
~/selenium_env/venv/bin/python scripts/jarvis_teiki_barai_chance.py --run --push
# Slack だけ（state から）
~/selenium_env/venv/bin/python scripts/jarvis_teiki_slack_report.py --from-state --outcome checked --dry-run
```

## 状態

`agents_registry.yaml` の `status` を変えるときは**先にチャットで提案**し、了承後:

```bash
cd ~/git-repos && ~/selenium_env/venv/bin/python scripts/jarvis_agent_team_status_sync.py
```

## 7. 改善ログ

| 日付 | 変更 |
|---|---|
| 2026-10-17 | 係新設。テイチャン結果 → Slack #report を本線（`--push` 相乗り）に接続 |
