# フロー — 連携健全性点検係（315）

- FlowForge: [flow_zYjp6A4HDURefJhSm0h_zUtX](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_zYjp6A4HDURefJhSm0h_zUtX)
- 実装CLI: `scripts/jarvis_ops_health_315.py`

## 型（Day2どおり）

1. **起動**（週次・GHA Fail・パートナー確認ついで・依頼）
2. **取得** — WeStudy週次チェック ＋ オプチャ（launchd／heartbeat／今日の`【スレッド】`／例外）
3. **まとめ** — OK／要フォロー
4. **Slack `#ops`**（要判断は `#consult` に1行。業務報告 `#report` と混ぜない）

## 最小実装（1回動く）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_ops_health_315.py --post --mark-checked
```

- ドライラン: フラグなし（本文＋`logs/` のみ）
- QR／YAML大量追記／構造限界の「無理直し」はしない（人が確かめる）

## 手順メモ

- 本数と投稿数を混ぜない（オープンチャット）
- Square probe NG は構造限界として報告し、無意味な再試行を繰り返さない
- 是正が必要なら既知手順（pause → discover → threads-only → resume）を提案または手順どおり実行

## 改善ログ（フロー側）

| 日付 | 変更 |
|---|---|
| 2026-10-09 | 型だけ記載 |
| 2026-10-11 | CLI 実装・#ops 報告1通まで（下準備プラン1体目） |
| 2026-10-11 | Phase H: launchd Sun 09:15（`install_ops_health_315_launchd.sh`） |
