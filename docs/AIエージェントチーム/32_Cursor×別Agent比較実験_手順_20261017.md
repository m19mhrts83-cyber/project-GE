# Cursor × 別Agent 比較実験 — 手順

- 着手: 2026-10-17
- Todoist: `6hmrRCwjPjGQ43Mv`（進行中）
- 前提: [`30_共通Agentフォルダ規格_BCP`](30_共通Agentフォルダ規格_BCP_20261017.md)

## 目的

同じ入力・同じ完了条件で、実行ツールだけ変えて差を見る。  
結果が出るまで **Claude Code Pro の新規課金は判断しない**。

## 実験対象（第1回）

| 項目 | 内容 |
|---|---|
| 社員 | **114 物件一次判定係**（パイロット済み） |
| 完了条件 | [`114/tests/checklist.md`](100_連絡・物件動向把握室/114_物件一次判定係/tests/checklist.md) |
| 依頼正本 | [`114/TASK.md`](100_連絡・物件動向把握室/114_物件一次判定係/TASK.md) |
| 作業 | dry-run または本番相当1回（Slack投稿の有無は事前に決める） |
| **対戦相手** | **GenCode（Friday）**（2026-10-17 確定） |

## 比較軸

| 評価項目 | 見るポイント |
|---|---|
| 品質 | 成果物と tests チェックの差 |
| 継続性 | Cursor 制限時に引き継げたか |
| 修正工数 | 指示・コードを直す手間 |
| コスト | 完了1回あたりの目安費用 |
| 安全性 | ファイル操作・外部送信・権限 |

## 実行手順（両ツール共通）

1. `jarvis_agent_run_lock.py acquire --task-id 6hmrRCwjPjGQ43Mv --agent-id 114 --executor {cursor|claude_code|gencode}`
2. `TASK.md` を更新（status=running、executor を記入）
3. 処理（CLI 本線なら `jarvis_property_gate_degraded.py --help` で範囲確認。投稿ありは要了承）
4. `tests/checklist.md` を埋める
5. 結果を `logs/YYYYMMDD_compare_{executor}.md` に残す
6. `release` ＋ TASK を done

## 対戦相手の候補（松野が1つ選ぶ）

| 候補 | 向き | 備考 |
|---|---|---|
| **GenCode（Friday）** | 既存契約を活かす | 追加課金なしで先に試せる |
| Claude Code（既存枠があれば） | BCP 本命の一つ | Pro 新規は実験後 |
| Cursor 内 Grok Bot | 参考 | フォルダ直編集は弱い場合あり |

## 結果表（2026-10-17・dry-run）

| 項目 | Cursor（Jarvis） | GenCode（Friday） |
|---|---|---|
| 所要時間 | 約2秒（acquire〜release） | コマンド約4.7秒／全体約40秒（記録込み） |
| checklist 通過 | 5/6（B投稿は dry-run で N/A） | 5/6（同） |
| 振分結果 | A=1 / B=33 / C=119（153件） | **同値** |
| 修正回数 | 0 | 0 |
| メモ | 手順は Jarvis 側が既知 | 必読→ロック→実行→ログまで一発完走 |

ログ:

- GenCode: [`logs/20261017_compare_gencode.md`](100_連絡・物件動向把握室/114_物件一次判定係/logs/20261017_compare_gencode.md)
- Cursor: [`logs/20261017_compare_cursor.md`](100_連絡・物件動向把握室/114_物件一次判定係/logs/20261017_compare_cursor.md)

### 結論（この実験）

- **共通フォルダ規格＋CLI本線**なら、実行ツールを変えても成果物（振分）は揃う。
- GenCode は追加課金なしで BCP 代行として使える目安が立った。
- Claude Code Pro は「必須」ではなく、別観点（編集体験・長期コスト）が欲しいときだけ検討でよい。

## 次

結果を見て Todoist [`Claude Code Pro課金判断`](../04_Todoist進捗_20261009.md) `6hmrRF3QrgQr6fhv` へ（要ボス）。
