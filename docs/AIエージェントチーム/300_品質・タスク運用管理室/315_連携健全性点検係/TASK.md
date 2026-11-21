# TASK — 315 連携健全性点検係

規格: [`30_共通Agentフォルダ規格_BCP`](../../30_共通Agentフォルダ規格_BCP_20261017.md)

| 項目 | 値 |
|---|---|
| task_id | codex-quality-plan-20261025 |
| agent_id | 315 |
| executor | codex |
| status | done |
| started_at | 2026-10-25T01:02:42+09:00 |
| finished_at | 2026-10-25T15:26:43+09:00 |

## 依頼

文書50の品質・効率改善計画を実施する。既存315を拡張し、4者の実行担当は固定しない。実際の1件の引き継ぎ検証は次回。

## 完了条件

- [x] 期待する成果物が `output/`（または記した外部パス）にある
- [x] `tests/` のチェックを通す
- [x] 必要なとき Slack `#report`／`#consult`／`#ops` に報告（今回は外部投稿不要）

## 成果物

- `output/20261025_品質改善検証.md`
- `../../50_4者共通運用と品質改善_20261025.md`
- `../../51_品質確認セット_20261025.md`

## メモ・障害

- Supabase egress上限超過を検出。課金変更せずTodoistオーナー確認へ起票。
- Dashboard本体はローカルbuild成功。ログイン後UIだけSupabase制限で未確認。
- 実際の1件を使った引き継ぎは次回（ユーザー指定）。

## 引き継ぎ

- 正本入力・版: 文書50 v1 / 文書51 v1
- 完了: 共通運用、品質ケース、TASKテンプレート、315、Askコスト制御、資料ハブ、残件整理、admin Drive写し同期
- 判断・了承: 外部投稿・デプロイ・課金変更なし
- 残作業: Supabase判断、実モデル評価、実1件の引き継ぎ検証
- 検証: Python 84、Node 6、TypeScript、Next build成功
- 次の一手: Todoist `6hqg5j75rjx8RWG6` を確認
- ロック: `codex-quality-plan-20261025` を final=done で解放済み

## 2026-11-22 315-B参照切替

- task_id: task_0d225d7c3974
- executor: codex（Chappy）
- status: done（実装・ローカル検証完了、PRチェック確認後もマージは本人）
- 依頼: 作り直した315-Bへregistry・共有URL・Dashboard投影を切り替える。315-A・旧フロー・FlowForge内容は変更しない。
- 完了条件: 対象参照だけの差分、315/315-B resolve・patch宛先検証、Node/Python/tsc/build/public guard成功、PR作成とチェック確認。マージは本人。
- 検証: Dashboard npm test 134件・Python unittest 23件・tsc --noEmit・Next build成功。ローカルMCPのresolve(view=edit)は315-B→flow_ZQIfYZY4GJF2XspXY8i0sGWD、315→flow_S5g_i7CCiE0P6RKIp2_MkMTA。共有APIの読取のみで確認。
- 差分: agentTeam.jsonはupdatedと315.extra_flows以外同一。同期で日付だけ変わった31ファイルは復元。patch待ち箱の実関数をメモリ内の保存先で実行し、315-B/315のflow_idを検証（本番書込なし）。
- マージ後: Vercelデプロイ成功と本番resolveを確認し、Macのmainを追従。今回のデータ変更に見張り再起動は不要（1件ごとにJSON読取）。切替前の待ち箱が残っていれば内容と新フローのノードIDの適合を確認してから扱う。

## 2026-11-22 315-A 確定工程への差分実装

- task_id: task_74a1ee3381cf / executor: codex / status: done（実装・ローカル検証完了、PRチェック確認）
- 依頼: 315-Aのみ、既存週次運用と確定FlowForgeを照合し最小差分を実装する。
- 完了条件: GHA履歴・保存済みSquare probe・CHRLINE healthを突合、成功/部分成功/失敗を区別、dry-runで投稿/mark/復旧なし、テストとpublic guard成功、PR確認。マージ/デプロイなし。
- 方針: Square liveはtoken削除/更新を伴うため呼ばない。保存済み結果だけ参照する（調整担当了承済み）。
