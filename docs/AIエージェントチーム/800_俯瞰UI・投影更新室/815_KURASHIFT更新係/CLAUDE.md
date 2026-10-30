# KURASHIFT更新係

複数ツールから同じフォルダを開いて使う指示書。直した運用知見はこのファイルに追記する。

## AIオートメーション（作業フロー）

- **FlowForge（開く）**: [flow_Xy85GrVwta9qwVlLQcHAwNjI](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_Xy85GrVwta9qwVlLQcHAwNjI)
- 一覧・進捗: [`15_FlowForge全体系_進捗_20261010.md`](../../15_FlowForge全体系_進捗_20261010.md)
- 設計の流れ図（あれば）: [`flow.md`](./flow.md)

## 1. 役割

- やること: KURASHIFT（deals・買い進め・物件投影等）の定期更新サイクルを回す。松野が俯瞰する画面の鮮度を保つ。
- やらないこと: 問合せ対外送信の独断実行・Tier3無断ON・秘密掲出。

## 2. 動き出す合図（4種のいずれか）

- [ ] 人が頼む
- [x] 時間（スケジュール）: 時間（日次／買い進め関連の後）。deals停滞・取込失敗の見回り。
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

1. deals/候補/取込の鮮度を確認
2. 更新スクリプトまたは定められたジョブを実行
3. **要フォロー時だけ** Slack #ops へ短文。OKは logs のみ
4. 要判断は #consult

### LINEオプチャの正本と監視

- 正本MDはOneDrive `P815_神大家オプチャ/*/5.やり取り.md`。ここからSupabase `line_openchat_logs`へ差分取込する
- Google Drive `【with Grok bot】` は任意の二次出力。日次本線からは外し、必要時だけ `--export-grok` で明示実行する
- スレッドは30日経過でアクセス不能になるため、削除済み404は想定内。stateでdeleted化し日常取得をスキップする
- 健全性attentionは、返信または新着スレッド通知など「スレッド活動の証拠」があるのに取得できない場合に限る。メイン投稿だけでは取りこぼし扱いにしない

### 一括（Phase L）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_ui_cycle_814_815.py --agent 815 --post
```

朝: `jarvis_morning_mac_refresh` の kurashift vendor / obsidian pick。  
12:30 dashboard-push 相乗り（`--agent both`）。`#ops` は問題時のみ。停止: `JARVIS_UI_CYCLE_DISABLE=1`

## 7. 改善ログ

| 日付 | 変更 |
|---|---|
| 2026-10-09 | スタブ作成（俯瞰UI更新担当） |
| 2026-10-11 | Phase L: ui_cycle 報告経路。朝refresh＋12:30相乗り |
| 2026-10-16 | `#ops` は要フォロー時のみ（OKは投稿スキップ） |
| 2026-10-30 | 30日失効404を想定内化。Grok二次出力を日次本線から分離し、スレッド活動証拠ベースの監視へ修正 |
