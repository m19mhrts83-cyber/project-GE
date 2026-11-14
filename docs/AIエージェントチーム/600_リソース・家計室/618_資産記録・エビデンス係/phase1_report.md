# 618 Phase 1：読取専用の結果判定とSlack下書き

2026-11-14、松野さんのOKを受け実装。金融照会・取得本体・DB writer・通知送信は動かさない独立した診断処理。

## 動くもの

- 人間: 松野さんが下書きと未検証範囲を確認する。
- AI: Codexがコード変更とテストを担当。診断実行時にAI APIは呼ばない。
- プログラム: `scripts/jarvis_asset_618_report.py`。Python標準ライブラリで判定し、DB読取時のみ既存Supabase SDKを使う。
- 外部ツール: SupabaseへSELECTのみ。Slackは出力する下書きの宛先名で、投稿機能自体を持たない。

## 入力と実行

標準は同じリポの `.jarvis_state/portfolio_weekly.json` を読み、投稿せずJSONを標準出力する。`--state`で既存結果の場所を明示できる。

```sh
~/selenium_env/venv/bin/python scripts/jarvis_asset_618_report.py \
  --state /Users/matsunomasaharu2/git-repos/.jarvis_state/portfolio_weekly.json \
  --read-db --env-file /Users/matsunomasaharu2/git-repos/.env.jarvis_private \
  --out /absolute/path/to/local-output
```

`--read-db`なしではネットワークを使わない。指定時は財務用の既存接続を利用し、口座IDとsnapshotのaccount_id/as_of/sourceだけを読み、金額・氏名・自由記述はSELECTしない。別worktreeでも`--state`と`--env-file`を正本の絶対パスで指定する。秘密の値は表示しない。

出力は `report.json` と `slack_drafts.txt`。同じ出力先を再指定するとこの2ファイルを更新する。投稿用フラグは存在しない。元データの更新・削除はしない。

## 判定の意味

- `reported_ok`: 今週の収集記録上でok。ただし今回の取得・書込・画面反映まで保証しない。
- `reference`: 手入力や過去成功の再利用・保全と分かる値。今回取得の成功件数と分ける。
- `skipped / failed / unverified`: 未取得、収集エラー、未検証。未検証を失敗扱いにしない。
- `current_week / older / missing / invalid_date`: DB基準日の状態。レコードがあることだけで今回書込済みにしない。
- DB未照会は`not_checked`、失敗は`unavailable`。対象一覧が未確認の場合は件数を暫定と表示。
- `metadata_consistent`は収集報告と今週のDB基準日が整合した状態。`current_write`と`kurashift_display`はPhase 1では常に`not_verified`。
- 画像は今回更新を依頼しておらず、撮影も検証もしていない。画像なしを数値失敗にしない。
- bank等は`liquidity_weekly=ok`という集計工程だけでは口座単位の取得成否を確認できないため、口座ごとは未検証になる。工程数と金融口座数を混ぜない。
- `last_full_ok`は使わない。日時不明・過去週・未来日時・cloud-onlyのokを、今回の金融ログイン取得成功に数えない。

既知の資産ID以外はハッシュ参照にして、未確認の口座ID・名称・金額・URL・例外本文を出力しない。対象別の人向け名称と対応表はPhase 2で整備する。

## 検証と制限

17件の単体・CLIテストで、skipのある成功、前回値保持、手入力、古い基準日、cloud-only、集計工程、DB読取失敗、機密非出力、投稿機能がないことを確認。既存DBとローカル結果でも読取実行し、全件成功と誤表示しないことを確認した。

CLI終了値0は「診断処理が完了」であり、全対象取得成功ではない。入力不正・DB読取失敗は終了値2。結果判定はJSONの各状態を確認する。

収集時点とDB読取時点は完全な単一トランザクションではない。今回の値の一致・全契約の網羅性・KURASHIFT表示・最新画像は未検証。Phase 1は既存定期ジョブへ組み込んでいないため、既存の通知や取得動作は変わらない。
