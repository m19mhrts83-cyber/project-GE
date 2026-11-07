# TASK — 114 物件一次判定係

規格: [`30_共通Agentフォルダ規格_BCP`](../../30_共通Agentフォルダ規格_BCP_20261017.md)

| 項目 | 値 |
|---|---|
| task_id | 6hmrRCwjPjGQ43Mv |
| agent_id | 114 |
| executor | cursor（比較・後追い）／gencode（先に完了） |
| status | done |
| started_at | 2026-10-17T23:08:04+09:00（gencode） |
| finished_at | 2026-10-17T23:10:42+09:00（cursor 比較完了） |

## 依頼（今回）

Cursor×GenCode 比較実験（dry-run）。本番 Slack 投稿なし。

## 完了条件

- [x] 振分結果がログに残っている（双方 A=1/B=33/C=119）
- [x] `tests/checklist.md` を通す（B投稿は dry-run で N/A）
- [x] 比較ログを残す（gencode／cursor）

## 成果物

- `logs/20261017_compare_gencode.md`
- `logs/20261017_compare_cursor.md`
- `logs/20261017_230821_gate114.md` / `20261017_231042_gate114.md`
- 正本表: [`32_`](../../32_Cursor×別Agent比較実験_手順_20261017.md)

## メモ・障害

- 2026-10-17 松野: `#report` は **A詳細を主**。Cは見送り羅列だと何を見るか分からない → 件数サマリのみ（`--c-list` で旧列挙）。正本 [`23_`](../../23_物件進行ゲート_Grok調査_20261012.md)

---

## 2026-10-30 Slack物件判断・犬山チケット欠落対応

| 項目 | 値 |
|---|---|
| task_id | `20261030-inuyama-slack-ticket` |
| agent_id | 114（312起票と連携） |
| executor | codex |
| status | done |
| started_at | 2026-10-30T13:00:00+09:00 |
| finished_at | 2026-10-30T13:51:02+09:00 |

### 依頼

Slackで物件判断を聞いても回答・Todoistチケットが出ない症状を調べ、ミスレモンのルーティン状況と犬山物件の欠落を是正する。

### 完了条件

- [x] Slackの対象投稿と物件を特定
- [x] 114 launchd・投稿ログ・Slack監視状態を確認
- [x] Todoistの重複を確認し、判断用チケットを起票
- [x] ルーティンの取りこぼし原因と改善を正本に記録
- [x] ロック解放・引き継ぎ更新

### 結果・検証

- 対象: 2026-10-30 10:53 `#consult`「犬山市鳥屋越60-5 戸建520万の第一問合せを進めてよいか」。
- 114 launchd は 11:15 に exit 0。既存判定済みのため `b_posted=0`。本件は判定カード生成後のTodoist落としが無かった。
- Miss Lemon `slack-fb-daily` は「有効・毎日~19:45・このコンピュータのみ」。従来はスレッド返信のみで、当日ルート投稿の要ボス依頼は対象外だった。
- Todoist `kodate` は admin 所有だが `use_owner_token` が無く、初回は `Section not found` で失敗。設定を是正した。
- 起票済み: task `6hrq4c59GM8PqhWR`、戸建て／オーナー確認。コメントとSlack／依頼MDリンク付き。第一問合せは未送信。
- `jarvis_todoist_api.py lane --id kodate`: 1件をオーナー確認で取得。対象ファイルの `git diff --check` は問題なし。
