# 異常時の流れ（315・確定 2026-10-11）

意図: **検知 → 安全な復旧を1回トライ → 結果報告**。直らなければ人が判断。  
パートナー確認に頼らない（315の自律フロー内で回す）。

## 流れ（3段）

```
1 検知     → 日曜21:00 GHA --cloud → Slack #ops
2 1回トライ → 日曜21:45 Mac --remediate-once
              （異常時のみ recover／watch resume。WeStudy再実行なし）
           → 再点検 → #ops（修正済／未解決／OK）
3 人判断   → 未解決 → #consult（QR・YAML大量・WeStudy再実行・Gmail再同意の要否）
```

## いまできること

| 段 | 状態 | 備考 |
|---|---|---|
| 1 検知・報告 | ✅ GHA日曜21:00 | WeStudy中心。オプチャ／Gmail は Mac へ委譲 |
| 2 1回トライ | ✅ Mac launchd 日曜21:45 | `--remediate-once`（Gmail含む点検） |
| 3 人判断 | ✅ `#consult` | トークン破壊・Gmail再同意の自動は禁止 |

## 自動でやってよい復旧（v1）

- オプチャ: `jarvis_openchat_thread_health --push` → `jarvis_openchat_recover_worker`（queued時）
- watch 停止時: `open_chat_watch_resume` を1回
- WeStudy Fail: **再実行しない**（`#ops`／`#consult` に明記）
- Gmail token NG: **ブラウザ再同意しない**（是正コマンドを `#ops`/`#consult` に書くだけ）

## 人が見るもの（自動ではやらない）

- QR 再ログイン、トークン再発行、**Gmail ブラウザ再同意**（`reauth_estate_gmail_send.py` 等）
- YAML 大量追記
- Square 401 など構造限界を「直した」ことにする
- WeStudy 週次 workflow の再実行

## 報告の言い方

| 結果 | `#ops` | `#consult` |
|---|---|---|
| 異常なし | 判定OK | 出さない |
| トライして直った | **修正済**＋何をしたか | 出さない |
| トライしたがダメ | **未解決** | **出す** |
| WeStudy Failのみ | 要フォロー／未解決 | 出す（再実行は人） |
| Gmail token NG | 要フォロー／未解決 | 出す（再同意は人） |
