# 2026-10-17 — Cursor×別Agent 比較実験（GenCode 実行分）

- 実験: `6hmrRCwjPjGQ43Mv`（Cursor制限時BCPの検証）
- 実行ツール: **GenCode**（executor=gencode）
- Agent: 114 物件一次判定係
- 結果: **成功**（Slack本番は出さず dry-run のみ）

## 所要時間

| 区間 | 時間 |
|---|---|
| ロック取得 → 実行コマンド完了 | 約 4.7 秒（`degraded.py --dry-run` 実測） |
| ロック取得 → ログ記録完了（全体） | 約 40 秒 |
| 本線コマンド単体 | 4.702s total（user 0.84s / sys 0.10s） |

## 実行内容

| # | 手順 | 結果 |
|---|---|---|
| 2 | ロック取得 `acquire --task-id 6hmrRCwjPjGQ43Mv --agent-id 114 --executor gencode` | `ACQUIRED: todoist:6hmrRCwjPjGQ43Mv`（exit 0／二重起動なし） |
| 3 | TASK.md を status=running / executor=gencode に更新 | 更新済 |
| 4 | `jarvis_property_gate_degraded.py --dry-run` | exit 0 |
| 5 | tests/checklist.md | 5/6 チェック（B投稿のみ N/A） |
| 6 | 本ログ作成 | 完了 |
| 7 | ロック release ／ TASK.md 更新 | 完了 |

## 結果（dry-run）

```
KURASHIFT_RESULT:{"ok": true, "count": 153, "lanes": {"A": 1, "B": 33, "C": 119}, "b_posted": 0, "b_deferred": 0}
```

- 内部実行: `--heal-handoff`（0件）→ `--scan --dry-run` → `jarvis_property_gate_remind.py`（保留なし）
- ログ: `logs/20261017_230821_gate114.md`（155行）

## 通ったチェック

- [x] 入力: Grok調査取込済み deals が分かる（153件）
- [x] 本線コマンドが動いた（Cursor 不要）
- [x] A/B/C の結果がログに残っている
- [x] To 未解決で止まらず、全て lane 判定で前進
- [x] 秘密（トークン）を MD／Slack に書いていない
- [ ] B カードの `#consult` 投稿 → dry-run のため未実施（本番禁止指示）

## 詰まった点

- なし。`--dry-run` は Slack 投稿をスキップするため本番副作用なしで完走。
- 注意: 実行ログは `logs/20261017_230821_gate114.md` に自動生成される（本比較ログとは別ファイル）。

## 修正回数

- スクリプト・コードの修正: **0回**
- 手順の作り直し: **0回**（指示どおりの順で一発完走）

## 所見（比較用）

- GenCode は「必読→ロック→コマンド→チェック→記録→解放」の定型を、対話的な作り直しなしで一通り実行できた。
- 判断を要した点はなく、本規格の TASK.md／checklist.md がそのまま作業台として機能した。
- dry-run 結果の解釈（B=33 だが投稿は本番のみ）は指示の「Slack本番は出さない」で明確だった。
