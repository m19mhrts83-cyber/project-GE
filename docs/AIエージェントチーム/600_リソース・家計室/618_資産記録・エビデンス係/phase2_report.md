# 618 Phase 2：共通排他・判断ログ・明示的な部分再実行

2026-11-14 / Codex / branch `codex/618-phase1-report`

## 状態

隔離worktreeで実装・ローカル検証済み。本番mainへの反映、定期ジョブの切替、金融ログイン、DB書込、Slack投稿は未実施。
既存の週次Python・画像取得Python・KURASHIFT既存workerへ組み込んだ変更案。専用UI・新サービス・Slack監視は追加していない。

## 合意したフローとの対応

| 工程 | 実装と主体 | 記録・動作 |
|---|---|---|
| 03 取り直し | 人間：松野さんが音声・チャットで依頼。AI：実行担当が対象を解釈。プログラム：既存Pythonへ渡す | `--retry-run` は前の実行記録の未完了だけ。`ok` / `excluded` は除外。自動反復なし |
| 04 排他 | プログラム：`jarvis_asset_618_runtime.py` | 週次、既存KURASHIFT worker、画像取得が同じkernel lockを取得。生きたロックを時間で奪わない |
| 05 基準取得 | プログラム → 外部サービス：既存Supabase `owner_decisions` | employee=618 / surface=asset_618、ページ取得。読取失敗は収集前に停止。未取得を基準なし扱いしない |
| 06–07 対象と判断 | プログラム：確定した構造化判断の解決 | 対象除外・対象保留・矛盾は該当対象だけに適用。他の対象は続行。壊れた履歴全体は停止 |
| 13 実行履歴 | プログラム → MacローカルJSON、既存週次状態・sync_meta | 実行ID、判断ID、基準版、対象ID、対象別結果。金額・自由記述を新しい実行台帳に複製しない |
| 17–18 判断の記録 | 人間：選択と理由。AI：記録内容の整理。プログラム → 共通DB | `jarvis_asset_618_decisions.py`。デフォルトはプレビュー、本人確認の明示フラグ付き適用でのみinsert。同一キーの再送は同一ID、内容違いはエラー |

18→03は人が今回の取り直しを依頼した時だけ。18→05は次の実行が始まる時に採用済み基準を取得。記録しただけでは実行しない。

## 判断の意味

- `rule_accept`：次回以降の採用基準。判断キーごとに新しい採用を優先。
- `rule_once`：指定した実行IDだけ。取り直しにも適用する場合のみ `allow_retry=true` を本人の判断として明示。
- `rule_reject` / `comment`：記録だけで基準にはしない。
- `rule_revert`：既存判断IDを明示して取消。後から採用した恒久基準の取消・期限切れで古い恒久基準は自動復活しない。今回だけの上書きが切れた場合は有効な恒久基準が残る。
- `effective_from` / `expires_at` はタイムゾーン必須。適用期間外の判断は実行に使わない。
- `exclude_target` は除外、`hold_target` は対象保留、`include_target` は候補を許可。include/excludeの競合は対象保留。
- `review_note` は参照用、`retry_target` は今回の対象への注記。どちらも新しい自動実行や対象追加を発生させない。
- 本人が述べていない理由はnull。AI提案と本人選択を別に保存。採用判断には本人確認と明示した選択文が必要。

## 判断入力（例示。未登録）

```json
{
  "action": "rule_accept",
  "owner_confirmed": true,
  "idem_key": "618-rule-example-001",
  "choice": "この対象を次回から除外する",
  "reason": null,
  "ai_proposal": null,
  "rule": {
    "decision_key": "example-sbi-scope",
    "targets": ["sbi_index"],
    "effect": "exclude_target",
    "effective_from": "2026-11-14T00:00:00+09:00",
    "expires_at": null
  }
}
```

このJSONは書式の説明であり、松野さんの実際の除外判断ではない。実DBへ登録していない。
`--input`のみでプレビュー。`--apply --owner-confirmed`を伴う場合だけ書込可能。実行担当は本人が確定していない判断をこの経路に渡さない。
読取は `--read --input` へ targets / run_id / 任意retry_ofを渡す。Slackからの受信処理はない。
今回だけの判断を先に記録する場合は新しいUUIDを予約し、rule.run_idと既存収集コマンドの`--run-id`を一致させる。既存の実行IDの使い回しは拒否。

## 保存と範囲

- 排他：`~/Library/Logs/jarvis_portfolio/asset618.execution.lock`。プロセス終了時にkernelが解放。旧 `weekly.lock.d` がある場合は実行中の可能性として停止し、自動削除しない。
- 実行台帳：同フォルダ `asset618-runs/{UUID}.json`、ファイル0600。状態running/blocked/failed/partial/complete/skipped/preview。保存済み数値の対象結果を逐次記録し、中断した実行も未完了だけ取り直せる。
- 週次状態：既存 `.jarvis_state/portfolio_weekly.json` の `asset_618`。既存 `sync_meta.portfolio_weekly_summary` に同じ実行ID・判断IDを付帯。KURASHIFTの画面表示そのものは未検証。
- 部分取得の際、以前の対象値はreferenceとして保持。今回取得した成功へ昇格させない。部分実行をフル週次完了扱いしない。
- 画像取得：既存 `_capture_summary.json` に加えて `_asset618_run.json`。既存取得器の画像鮮度がまだ検証できないため、成功ログだけで最新正常画像の証明としない。
- 数値の保存先・既存account/dateキーを継続。新テーブル・スキーマ変更なし。契約surfaceを正本と2つの写しで同期。

取り直し単位の制約：数値は既存の口座IDを指定。Sony/Prudentialはサイト側の一括ログイン取得を共有するが、保存先は指定口座だけに制限する。銀行は既存 `liquidity_weekly` グループ単位で、銀行一口座だけの再取得は未対応。画像は既存STEP_KEYSの9ステップ単位で、同一ステップ内の複数契約を分割する機能は未対応。
Zaim反映だけの取り直しは同週の正常な元データがある場合だけ利用し、元口座を再取得しない。依存データがなければ保留し、全件取得に拡大しない。対象を限定した実行では横断的な保険配分・証券内訳の更新を起動しない。

## 検証

- Python：618関連55件（Phase 1回帰17件を含む）、共通契約4件、既存営業時間11件。
- TypeScript：判断契約10件。worktreeに依存パッケージがなかったため、既存mainのTypeScriptをローカル参照して検証。追加インストールなし。
- 合計80件。別プロセス排他、旧ロック、例外解放、読取障害時停止、採用／今回だけ／期限／取消／矛盾、冪等保存、保存失敗、中断後の部分再実行、他の取得器を呼ばないこと、古い画像の非成功判定、契約同期を確認。
- Python構文、zsh構文、差分空白チェック。
- 実Supabase：判断ログのSELECTに成功、618の既存判断0件。insert/updateなし。実書込・金融サイト・本番workerのE2Eは未検証。

## 本番反映前と次段階

旧runnerから移行する際は旧ジョブが終わっていることを確認してから、Pythonとrunnerを同じ変更として反映する。旧runnerと新しいコードの混在運用を前提にしない。ロックファイルを勝手に消さない。

Phase 3：証拠鮮度・最新正常画像のprivate Storage保存、数値保存後の読戻し、KURASHIFTの最新証拠・状態表示と反映確認。実行時レコードと画面を照合するE2Eが残る。Slackは引き続き報告案のみ。
