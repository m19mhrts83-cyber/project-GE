# フロー（Flowforge 写し）

- Flowforge: https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_whqVaN6KcGoUZnFpJKJjL7jN
- 指示書: [`CLAUDE.md`](CLAUDE.md)
- 連携: [`611_リソース制約要約係`](../../600_リソース・家計室/611_リソース制約要約係/)

## 型（813・枠＋頻度）

1. 起動（枠逼迫／611申し送り／人が頼む）
2. 利用状況・Fail 取得（Datadog等は使わない。既存ログ・GHA・611）
3. 代行ルート案＋必要なら頻度の減／増
4. `#consult` 承認
5. Jarvis 反映 → `#ops` 完了

## 手順メモ

- 無断切替禁止
- 611の頻度表を入力に含める
