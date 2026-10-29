# ポイント・還元ウォッチ係（614）

複数ツール（Claude Code / Cursor / Codex / GenCode / FlowForge 等）から同じフォルダを開いて使う指示書。  
直した運用知見は**このファイルに追記**する（チャットだけの修正にしない）。

ジャンル: **リソース・家計（得る側）**。隣係: **612** は払う側（年会費・課金ガード）／**613** Zaim鮮度。  
出口: `/vpoint`（テイチャン・Vポイント）＋ `/etc`（ETC還元）。

## AIオートメーション（作業フロー）

- **FlowForge**: ノード未作成。**素案の正は [`flow.md`](./flow.md)**（作り込み後に registry URL を追記）
- ビルダー（組織図）: https://agent-team-builder-teal.vercel.app/s/uksxiDIzE1AEckKH
- 一覧・進捗: [`15_FlowForge全体系_進捗_20261010.md`](../../15_FlowForge全体系_進捗_20261010.md)
- 設計の流れ図: [`flow.md`](./flow.md)
- Slack 短報正本: `scripts/jarvis_points_rebate_slack_report.py`（`--kind teiki|etc|vpoint`）
- 本線スクリプト:
  - テイチャン: `jarvis_teiki_barai_chance.py` ＋ `launchd/teiki_draw_runner.sh`
  - ETC還元: `jarvis_etc_rebate_fetch.py` ＋ 月次 launchd（20〜26日）
  - Vポイント定例: `jarvis_vpoint_routine.py`（窓C）

## 設計ゲート（4点）

| 柱 | 内容 |
|---|---|
| **入口** | Vpass／smile-etc／Vポイント state（`teiki_*` / `etc_monthly` / `vpoint_*`） |
| **確認** | 抽選・還元取得は自動。OTP・Wallet・規約未同意・ログイン失敗だけ人 |
| **履歴** | Slack `#report` 控え `reports/`・各 state・ダッシュ `/vpoint` `/etc` |
| **停止** | 各本線の `*_DISABLE` ／ `JARVIS_POINTS_REBATE_SLACK_REPORT_DISABLE=1` |

## 1. 役割

- **やること（得る側の見える化）**
  1. テイチャン券確認・抽選 → `/vpoint` ＋ Slack
  2. ETC 平日朝夕の還元サマリ取得 → `/etc` ＋ Slack
  3. Vポイント定例（窓C）の要約 → `/vpoint` ＋ Slack
- **やらないこと**
  - 年会費・二重課金ガード本体（**612**＝払う側）
  - Zaim 鮮度・費目（**613**）
  - 秘密の再掲・対外送信

## 2. 動き出す合図

- [x] テイチャン: 月・木 10:15／朝取りこぼし
- [x] ETC還元: 毎月 20〜26日 09:30／朝取りこぼし
- [x] Vポイント: 25〜月末 09:40（窓C）／朝取りこぼし
- [x] 人が頼む: 「テイチャン」「ETC還元」「Vポイント定例」

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| CLI | ○ | 上記本線＋ `jarvis_points_rebate_slack_report.py` |
| ブラウザ／CDP | ○ | Mac Chrome 専用プロファイル（終了時 auto-quit） |
| Slack Webhook | ○ | `#report`（失敗時 `#ops`） |

**秘密**: `.env.jarvis_private` の `VPASS_*` / `ETC_*` / `SLACK_WEBHOOK_AI_TEAM_*`。本フォルダに値を書かない。

## 4. 報告先

| 種別 | 行き先 |
|---|---|
| 定時・結果 | Slack `#report`（【614 ポイント還元｜…】） |
| 失敗 | Slack `#ops` |
| 人が見る画面 | `/vpoint` · `/etc` |

### Slack 書き出し（FRIDAY／Jarvis 共通）

| ch | いつ |
|---|---|
| `#report` | 完了・定型・生存確認 |
| `#consult` | 要判断。末尾「次の担当」3行必須 |
| `#ops` | 障害・失敗・枠切れ |

`#consult` 末尾: `次: Grokで続行 | Jarvisに依頼 | 人判断のみ` ＋ `担当メモ` ＋ `橋渡し`  
正本: [`38_Slack書き出し_FRIDAY_Jarvis_20261018.md`](../../38_Slack書き出し_FRIDAY_Jarvis_20261018.md) · [`36_`](../../36_Slack_consult手渡し_次の担当_20261018.md)

## 5. 成果物の置き場

| 種類 | 場所 |
|---|---|
| state | `.jarvis_state/teiki_barai_chance.json` / `etc_monthly.json` / `vpoint_*.json` |
| Mac ログ | `~/Library/Logs/jarvis_teiki/` 等 |
| Slack 控え | 本フォルダ `reports/` |

## 6. 作業手順

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
# テイチャン（ダッシュ＋Slack）
~/selenium_env/venv/bin/python scripts/jarvis_teiki_barai_chance.py --run --push
# ETC（取得反映＋ダッシュ＋Slack）
~/selenium_env/venv/bin/python scripts/jarvis_etc_rebate_fetch.py --apply --push
# Vポイント定例
~/selenium_env/venv/bin/python scripts/jarvis_vpoint_routine.py --apply --push
# Slack だけ dry-run
~/selenium_env/venv/bin/python scripts/jarvis_points_rebate_slack_report.py --kind etc --from-state --dry-run
```

## 状態

`agents_registry.yaml` の `status` を変えるときは**先にチャットで提案**し、了承後:

```bash
cd ~/git-repos && ~/selenium_env/venv/bin/python scripts/jarvis_agent_team_status_sync.py
```

## 7. 改善ログ

| 日付 | 変更 |
|---|---|
| 2026-10-17 | 係新設（旧名・テイチャン単体）→ Slack #report |
| 2026-10-17 | **ポイント・還元ウォッチ**に改名・拡大。ETC／Vポイント定例も `#report` 相乗り。612（払う側）と分離 |
| 2026-10-17 | ビルダー組織図に追加（共有 `uksxiDIzE1AEckKH`）。`flow.md` 素案を613型で充填 |
| 2026-10-29 | Vポイント Slack の文面を人の言葉に: 「要Jarvis確認」→「手で確認する項目: N件（一覧は下のページ）」、「窓C定例」→「月末の定例チェック（25日〜末日）」（松野FB） |
