# PROGRESS — 315 連携健全性点検係

作業再開時は **このファイル → `CLAUDE.md`** の順で読む。

## いまの位置（2026-10-15）

- 状態: **運用確認**（`00_🟡運用確認.md`）。日曜 schedule 成功後に Jarvis が sync で `運用` へ（方式1）
- 済: GHA本線・手動GHA緑・`#ops`・`--remediate-once`・launchd 日曜21:45・**Gmail token モニター**
- 残り: 日曜 cron（schedule）着弾待ち → 運用引き上げ

## ログ

| 日付 | やったこと | できたもの | 次の一手 |
|---|---|---|---|
| 2026-10-11 | 本線を GHA 日曜21:00＋`#ops` に確定 | workflow／CLI `--cloud` | 運用確認仕上げ |
| 2026-10-11 | Mac初回点検→`#ops` | `logs/20261011_163757_ops_health.md` | GHA手動 |
| 2026-10-11 | GHA手動成功（run 38125696617） | cloud→`#ops` | TODO3 |
| 2026-10-11 | 日曜cron1回＝運用OK（方式1） | promote-to-ops | schedule待ち |
| 2026-10-11 | **検知→1回トライ→結果** 実装 | `--remediate-once`／launchd 21:45／incident-flow | dry-run確認・schedule待ち |
| 2026-10-11 | smoke: `--remediate-once --dry-run` → 判定OK・トライ不要 | `logs/20261011_180441_ops_health.md` | 日曜 schedule＋21:45 着弾 |
| 2026-10-15 | Gmail token を 315 点検に追加 | `gmail_token_snapshot`／CLAUDE・incident-flow | Mac dry-runで行確認 |

## 禁止メモ

- トークン破壊の自動復旧・**Gmail 無人ブラウザ再同意**・QR無人完了・YAML大量無確認追記・WeStudy自動再実行
- 状態を無言で `運用` に上げる（schedule成功確認後の sync は了承済み）
- `#report`／チャットへの定時報告

## 315-A 差分実装（2026-11-22）

- 確定FlowForge読取・既存運用照合、専用worktreeで実装。工程差分と検証は [315a-alignment](docs/315a-alignment.md)。
- 315自身の完了GHA履歴・保存済みSquare・CHRLINE healthを接続。正常週次#ops抑止を解除、dry-run mark無効化、専用Webhook以外への転送防止。
- マージ・本番適用は未実施。schedule/plist/既存復旧1回を維持。状態の格上げなし。

## 2026-11-22 315-A CHRLINE health 取得修正

- 原因: 実行pythonにCHRLINE/geventが無く例外握りつぶしで「取得できない」。修正: `.venv` のpythonを子プロセスで呼びPYTHONPATHを付与、読取専用維持、失敗理由を説明に出す。テスト追加。
- Square: 手動probe保存（7/5以降更新なし）をやめ、常駐watchの状態ファイル（state・heartbeat 24h以内・書込エラー）で自動判定。probeは外した。マージ・launchd変更・Slack送信なし。

## 2026-11-22 CHRLINE exhausted 警告の整理（PR）

- 原因調査: retry キューの exhausted 146件は、書込先MDの親フォルダ名変更で書き込めず本文も未復号のまま枯渇した過去分（最後の枯渇は10月中旬、直近24hの増加は0）。新しい障害ではない。
- 対応: `line_unofficial_poc/chrline_retry_queue_archive.py`（既定dry-run、`--apply`で退避。削除せず `.chrline_sync_retry_queue.archive.json` へ、実行前にバックアップ）。exhausted 警告は「前回から増えた分」で判定（baselineなしは残り件数）。
- 退避の実行はマージ後に松野さん了承を確認してから。active は触らない。
- decode_stats が止まって見える件: 新着の本文取得が1件も無い日は記録を追記しない仕様のため。点検側は、標本0でもsync最終成功が48時間以内なら「新着なし＝OK」と判定（実装済み）。syncも古い時は確認不能。
