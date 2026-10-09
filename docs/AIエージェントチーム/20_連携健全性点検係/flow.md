# フロー — 連携健全性点検係

- Flowforge: https://flowforge-259747770348.asia-northeast1.run.app/ （作成後にリンク追記）

## 型

1. 起動（週次・Fail・依頼）
2. チェックスクリプト／ログで現状取得
3. OK／要フォローにまとめ
4. Slack `#ops` へ（要判断は `#consult`）

## 手順メモ

- 本数と投稿数を混ぜない（オープンチャット）
- Square probe NG は構造限界として報告し、無意味な再試行を繰り返さない
