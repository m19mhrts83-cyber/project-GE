# Zaim鮮度・二重取込係（613）

複数ツール（Claude Code / Cursor / Codex / GenCode / FlowForge 等）から同じフォルダを開いて使う指示書。  
直した運用知見は**このファイルに追記**する（チャットだけの修正にしない）。

ジャンル: **リソース・家計**（`config/agent_team_genres.yaml`）。Grok リソース経営とは別線（`mixup_kind: none`）。隣係: **612** 年会費ガード／**611** AI枠要約／**316** は財務メトリクス分析（本係は鮮度・費目実行）。

## AIオートメーション（作業フロー）

- **FlowForge（開く・閲覧）**: [共有](https://flowforge-259747770348.asia-northeast1.run.app/share/v2D2xrS4Gm9bY0bP)（外部ブラウザOK）
- **FlowForge（編集）**: [flow_5GzzES3EaIqhlotG9IGGNXjF](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_5GzzES3EaIqhlotG9IGGNXjF)（Cursor インブラウザ・**m19m**）
- 一覧・進捗: [`15_FlowForge全体系_進捗_20261010.md`](../../15_FlowForge全体系_進捗_20261010.md)
- 設計の流れ図: [`flow.md`](./flow.md)
- 運用ルール（Jarvis）: `.cursor/rules/jarvis-zaim-watch.mdc`

## 設計ゲート（4点）

| 柱 | 内容 |
|---|---|
| **入口** | Zaim CSV・`online_accounts`・前回 learn snapshot・学習ルール・`config/zaim_category_catalog.yaml` |
| **確認** | 高確信度の集計／費目は自動適用。曖昧費目・OTP失敗・「おかしい」suppress 解除だけ人 |
| **履歴** | `/zaim` changelog・学習ルール JSON・Todoist（残留 stale）・本フォルダ `logs/` |
| **停止** | `JARVIS_ZAIM_*_DISABLE`／口座 `automation: off`／Playwright lock 競合／OTP 不可口座は更新スキップ |

## 1. 役割

- **やること**
  1. **銀行・カード連携の鮮度**: 遅れ（stale）検知 →（Mac）更新ボタン／OTP 可能なら再接続 → 再 check
  2. **二重取込・集計の安全な直し**: Watch runner の高確信度アクションを適用
  3. **費目学習**: 手動直し差分を学習し、確信度が十分な「その他／使途不明」等を自動直し。結果を `/zaim` に載せる
  4. **開いたときの状態**: 定時サイクル後、ダッシュ冒頭が「遅れなし／学習・修正は確認用」に近づくこと
- **やらないこと**
  - 対外送信・秘密の再掲・勝手な Todoist close
  - Suica 画像認証・ANA／NRK 等の対象外口座の無理押し
  - 学習1回だけの断定適用（原則 `count>=2`。閾値変更は別チャットで合意してから）
  - 年会費ガード本体（**612**）・AI枠頻度提案（**611**）・夜間メトリクス分析の本線（**316**）

## 2. 動き出す合図

- [x] **時間（本線・朝）**: 火・金 **09:00** JST — bank check ＋（設定時）stale 更新 ＋ Watch（`--skip-finance`）
- [x] **時間（本線・昼）**: 火・金 **12:00** JST — CSV 取込 → learn → Watch → snapshot
- [x] **時間／CI**: GHA `zaim-finance-sync` — check と Watch（**更新ボタンは押さない**）
- [x] **人が頼む（副）**: 「Zaim 見て」「再接続して」「費目直して」等 → runner／reconnect
- [x] **ダッシュキュー**: `/zaim`「今すぐ更新」→ Mac `refresh_queue` poll
- [ ] 毎日朝オープン取りこぼし強化（合意後に本線化）

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| チャット・検索 | ○ | 鮮度・学習件数の要約、`#ops` 文面 |
| 外部連携（API） | ○ | Supabase `watch_status`（`zaim_quality`）投影 |
| CLI | ○ | `jarvis_zaim_*` 一式（下記） |
| ブラウザ／Playwright | ○ | Mac 専有。CSV export・銀行更新ボタン。GHA は check のみ |
| 画面操作（OTP） | △ | Messages DB／メール OTP。値はチャットに出さない |

**秘密**: `.env.jarvis_private` のみ。本フォルダ `.env` はキー名だけ（[`.env.example`](./.env.example)）。  
**人が確かめる**: `/zaim` の「確認した」「おかしい」、曖昧費目のピッカー、OTP が取れない口座の手動更新。

## 4. 報告先

| 種別 | 行き先 |
|---|---|
| 定時・健全性 | Slack `#ops`（失敗・残留 stale・学習衝突があるとき。ゼロ報告は連投しない） |
| 要判断 | Slack `#consult`（費目方針・閾値変更・口座 automation 変更） |
| 人が見る画面 | Jarvis `/zaim`（ピン・学習一覧） |
| Webhook | env キー名のみ: `SLACK_WEBHOOK_OPS` 系 |

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
| 人が見る入口 | https://jarvis-dashboard-amber.vercel.app/zaim （ローカルは `/zaim`） |
| Watch／changelog | Supabase `jarvis-dashboard` の `watch_status`（id=`zaim_quality`） |
| 学習ルール・snapshot | `~/git-repos/.jarvis_state/`（`zaim_learn*` 等。値・中身をチャットに貼らない） |
| 口座設定 | `config/zaim_bank_sync_watch.yaml` / `config/zaim_quality_watch.yaml` / `config/zaim_category_catalog.yaml` |
| Mac ログ | `~/Library/Logs/jarvis_zaim/` |
| このフォルダ | `logs/`（サイクル結果の短い MD。秘密なし） |

## 6. 作業手順（一本の流れ）

外部ツール（launchd／GHA）と AI は**別線にしない**。実装手段が違うだけの**分岐→合流**。最終の人向け出口は常に **`/zaim`**（＋必要時 `#ops`）。

### A. 火・金 09:00（鮮度）

1. `jarvis_zaim_bank_sync_check.py`（遅れ・欠落の数値化）
2. 許可時: `jarvis_zaim_bank_sync_manual.py --from-stale`（または `jarvis_zaim_reconnect.py --from-stale`）。OTP は YAML `otp_channel` がある口座のみ
3. `jarvis_zaim_watch_runner.py --skip-finance`（二重取込・費目の安全適用）
4. 残留 stale／失敗があれば Todoist または `#ops`（dedupe あり）

### B. 火・金 12:00（CSV＋学習）

1. Zaim CSV export（Playwright・`zaim_playwright.lock` 共有）
2. finance／energy メトリクス push（既存 runner）
3. `jarvis_zaim_watch_runner.py` 本線: **learn → 品質検知 → 高確信度 apply → snapshot → changelog → push**
4. `/zaim` に「学習・修正された内容」が載る。人は違うときだけ「おかしい」

### C. 副合図・キュー

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
# 鮮度だけ
~/selenium_env/venv/bin/python scripts/jarvis_zaim_bank_sync_check.py
# stale 再接続（OTP 試行は明示時）
~/selenium_env/venv/bin/python scripts/jarvis_zaim_reconnect.py --from-stale [--try-otp] [--notify]
# Watch 一式（学習込み）
~/selenium_env/venv/bin/python scripts/jarvis_zaim_watch_runner.py
# 学習だけ dry-run
~/selenium_env/venv/bin/python scripts/jarvis_zaim_learn.py --dry-run --json
```

### D. FlowForge で作り込むときのノード対応（別チャット用）

| ノード案 | 既存スクリプト／手段 |
|---|---|
| 起動（火金09 / 火金12 / キュー／人） | launchd / GHA / refresh_queue / 会話 |
| check | `jarvis_zaim_bank_sync_check.py` |
| stale 更新 | `jarvis_zaim_bank_sync_manual.py` / `reconnect`（Mac） |
| CSV | `zaim_csv_export`（Mac） |
| learn＋apply | `jarvis_zaim_watch_runner.py` |
| 投影 | Supabase push → `/zaim` |
| 報告 | `#ops`（異常時） |

**成功の見た目**: `/zaim` 冒頭が「遅れなし」、未確認の学習ピンは例外だけ、その他費目の残件が週次で減る。

## 状態（作成・status変更時）

フォルダ名は変えない。`agents_registry.yaml` の `status` を直すときは**先にチャットで提案**し、了承後:

```bash
cd ~/git-repos && ~/selenium_env/venv/bin/python scripts/jarvis_agent_team_status_sync.py
```

詳細: ハブ [`CLAUDE.md`](../../CLAUDE.md) / [`22_運用状態の識別`](../../22_運用状態の識別_20261011.md)

## 7. 改善ログ

| 日付 | 変更 |
|---|---|
| 2026-10-09 | Phase D スタブ |
| 2026-10-14 | 指示書を本線配線で充填。役割に費目学習を明記。FlowForge 作り込み用に手順・4点・スクリプト対応を固定（status は候補のまま） |
