# TASK — 611 リソース制約・配車係（実装 第1弾）

| 項目 | 値 |
|---|---|
| task_id | 611-impl-1 |
| agent_id | 611 |
| executor | 実装は全エージェントの使用量を見て決める（2026-11-05 訂正）。ミスレモン（Claude Code）でも Codex でも可。ローカルログの確認は Mac 上で動かす必要がある |
| status | review（2026-11-06 ミスレモン実装。下書き PR・松野さんの判断待ち） |
| 依頼者 | 松野さん（2026-11-05 に「611の実装を渡す」を選択） |

## 依頼

使用量の集計を作る。動きA（週次の使用状況リサーチ）の材料づくり。**第1弾は「集計できるかの確認」と、できる範囲の集計まで**。配車案の自動投稿（動きB）は次の弾。

## 読むファイル

- [`flow.md`](flow.md) の §3 動きA、§4 実装の切り出し 1・2
- `scripts/jarvis_cursor_usage_watch.py`（Cursor。目視％の手入力、閾値 70%／90%）
- `docs/AIエージェントチーム/49_共通ルール_AI使用量と入力_20261024.md`
- `docs/AIエージェントチーム/50_4者共通運用と品質改善_20261025.md`（4者運用）

## やること

1. Mac のローカルログから Claude Code と Codex の使用量を集計できるか確認する（保存場所・形式・取れる粒度）。**未確認**。取れないものは「手入力」と明記して結論を出す。
2. 取れる分は週次集計の関数にする。GenCode と ChatGPT モードは手入力欄だけ用意する。
3. Cursor の既存 state と合わせて 1 つの表にする。置き場は Supabase を正本とし、`.jarvis_state/ai_usage_weekly.json` は写し。**テーブル設計は台帳 DB の設計（comm_items など）と揃える。先に既存スキーマを確認し、新規テーブルを作る前に松野さんに案を出す。**
4. 週次の既存スケジュールに相乗りする（専用スケジューラは増やさない）。

## 完了条件

- 4者それぞれの「取れる／取れない」が表で分かる。
- 取れるものは週次の数値が表に入る。
- LLM を使わない（ルールだけで回る）。

## してはいけないこと

- ツールの切替・課金変更・社員の停止・作業の自動起動。
- Supabase の本番スキーマ変更を許可なしで実行すること（案を出して許可を取る）。
- 秘密の値のコミット。

## 次の一手

実装後に `#consult` へ結果を出し、松野さんが動きB（配車案の投稿）に進むか決める。

## 検証結果

2026-11-06 ミスレモン（Claude Code、Mac 上で実行）。詳細: [`output/20261106_実装1_使用量集計の結果.md`](output/20261106_実装1_使用量集計の結果.md)

- 取れる: Claude Code（トークン・枠到達。％は無し）、Codex（トークン＋5時間／週次％）。取れない＝手入力: Cursor・GenCode・ChatGPT モード（Claude の％も手入力欄あり）
- `scripts/jarvis_ai_usage_weekly.py` を追加（LLM なし）。直近7日のドライランで Codex 週次 63%、Claude 枠到達3回を確認
- 週次は 314 の土曜 runner に相乗り（失敗しても 314 は止めない）。Supabase へは未送信
- テスト: `python3 -m unittest scripts/tests/test_ai_usage_weekly.py` → 4件 OK
- 2026-11-09 Supabase 確認: 使用量テーブルは無し。新テーブルは作らず既存 `metrics`（metric/entity/recorded_at 一意）＋`sync_meta` に載せる形に変更（スキーマ変更なし）
- 2026-11-09 Cursor 自動取得を追加（`scripts/jarvis_cursor_usage_fetch.py`、314 runner に相乗り、失敗しても手入力値を残す。テスト4件）。手入力: Claude 7%・Cursor 37%/1%・Grok Bot 96%（誤り。正は使用 3.6%＝残り 96.4%）
- 2026-11-09 夜: Playwright のブラウザは Google ログインで「安全でない」と弾かれたため、普通の Chrome を専用プロフィール（`.jarvis_state/cursor_usage_chrome/`）＋リモートデバッグで起動して読む方式に変更
- 未了: Cursor 取得用プロフィールへの初回ログイン（松野さん、マージ後に `--login`）、（2026-11-09 了承済み: 週次 runner に `--push` を付けた）、ChatGPT・Genspark の％の取り方

---

## 実装 第2弾（611-impl-2・2026-11-10 松野さん「実装進めて」）

- 動きB（配車案）: `scripts/jarvis_ai_dispatch_suggest.py`＋テスト 7 件
- ルール: 磨き上げ・設計＝チャッピー固定／お金まわり＝ジャービスか Codex／実装・文書・点検＝週次％が低い順（90% 以上とクレジット切れは外す、同点は Codex→ミスレモン→ジャービス→フライデー）／ログインが要る作業は Mac launchd と注記／渡し票の依頼が空なら「書いてから」
- 出力はファイルだけ（dry-run）。#consult 投稿は `--post`、松野さんが文面を OK するまで使わない
- 未決: 入力元（手動で TASK.md を指定／Todoist の実装タスク／TASK.md の status=queued を週次で拾う）

## 以前の完了タスクの記録（2026-11-01）

以下は `ai-usage-management-20261101` の調査完了記録です。上の `611-impl-1` とは別タスクとして保持します。

### TASK — 611 リソース制約要約係

- task_id: ai-usage-management-20261101
- agent_id: 611
- executor: codex
- status: done
- started_at: 2026-11-01T10:03:42+09:00

#### 依頼・完了条件

Codex、Claude Code、Cursor、Gensparkの本人契約、請求／補充日、短期・週次制限、残量を一次資料で調べ、確認済み／旧記録／未確認を区別してObsidian正本へ保存する。既存OGDスクリプトで対象ノートのみ同期し、成否を確認する。契約・課金設定は変更しない。

#### 確認状況

- Codex: Plus、5時間4%使用、週次89%使用（ツール取得時点）。
- Claude: Pro月額、11月23日更新、週次97%、水曜7時リセット、使用クレジットOFF。ブラウザと領収書を確認。
- Cursor/Genspark: Chrome拡張機能のUIが自動操作を阻害。ユーザーへ解除依頼済み。既存記録も参照中。

#### 成果物・検証結果

- 完了: /Users/matsunomasaharu2/Documents/500_Obsidian_r1/03_Literature Note(まとめノート)/仕事術・AI連携/20261101_AIエージェント使用量管理_Codex_Claude_Cursor_Genspark.md
- 既存OGDプログラムの実行成功: uploaded=1 updated=0 already_ok=0 missing_local=0。iPhoneでのPull確認は未実施。
- 社員outputに一次確認記録、CLAUDE.mdに参照を追加。
- 契約／課金／リセット権／本番頻度は未変更。
- 未確認: Codex月額更新日・実請求額、Cursorの税等、Genspark次回年額。本人へCodex更新日を確認中。

#### 追加質問への対応 2026-11-01T10:11:58+09:00

Codexの月額更新日を本人請求画面で11/25と特定。Claude週次回復は契約開始日と独立、Codex曜日変更は未確認。主担当曜日を分ける案を正本へ追記。課金変更・リセット権使用は行わず。
- 2026-11-10 訂正: Grok Bot 週次は使用 3.6% が正（自動取得と一致）。GenCode はクレジット切れ（残り 0）→ 手入力欄 `gencode` に 100%＋メモで記録。次の土曜の週次で Supabase にも入る
