# 311 完了チェック

## Phase 1（CLIゲート）

- [x] `--draft` で1件読める
- [x] 3点点検（宛先／名義／禁止）が動く
- [x] OK → `#report`／NG → `#consult`（`--post`）
- [x] 送信・下書き書き換えをしない（読取のみ）
- [x] `output/gate_*.json` に結果が残る

## Phase 2（inbox poll）

- [x] `--from-inbox` が複数 MD を処理（README/example スキップ）
- [x] 処理後 `input/processed/` へ退避
- [x] launchd 15分 runner／install／uninstall
- [x] 経路A `--post` で Slack 到達

## Phase 3（上流キック）

- [x] `--enqueue` で input/ に依頼 MD が書ける
- [x] 211 apply 後に enqueue（soft-fail）
- [x] ホーク `action: send_gate_311` → apply → enqueue

## 共通

- [x] 権限境界を超えていない（外送信は人了承）
