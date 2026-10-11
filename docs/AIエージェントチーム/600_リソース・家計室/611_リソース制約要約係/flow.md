# フロー（AIオートメーション／Flowforge 写し）

- Flowforge: https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_azD9MyV6Lk3Pn63YMzf9uIFo
- 指示書: [`CLAUDE.md`](CLAUDE.md)

## 型（611・リソースコントロール）

1. 起動（週次相乗り／逼迫時／人が頼む）
2. **AI使用状況**の取得（枠・Fail・起動回数の目安）
3. **レビュー結果**の突合（意図OK／ダメ出し／動きすぎ・不足）
4. 制約サマリー生成
5. **頻度コントロール表**（減／据置／増）を作成
6. 人確認（`#consult`）→ 了承後のみ Jarvis が反映
7. Slack `#ops` 報告（増減案は `#consult`）

## 手順メモ

- kintone／未採用監視は使わない
- 813 代行指揮とセット: 枠切替＋頻度を同時に提案してよい
- 正本反映先: `agents_registry.yaml` note・launchd・各 `flow.md` の合図
