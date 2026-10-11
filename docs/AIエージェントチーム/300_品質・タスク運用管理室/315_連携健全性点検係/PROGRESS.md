# PROGRESS — 315 連携健全性点検係

作業再開時は **このファイル → `CLAUDE.md`** の順で読む。

## いまの位置（2026-10-11）

- 状態: **運用確認**（`00_🟡運用確認.md`）。日曜 schedule 成功後に Jarvis が sync で `運用` へ（方式1）
- 済: GHA本線・手動GHA緑・`#ops`・`--remediate-once`・launchd 日曜21:45
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

## 禁止メモ

- トークン破壊の自動復旧・QR無人完了・YAML大量無確認追記・WeStudy自動再実行
- 状態を無言で `運用` に上げる（schedule成功確認後の sync は了承済み）
- `#report`／チャットへの定時報告
