# 【候補】617 資金移動係（J専）

寄せ（資金移動）の **定型作業の型**。**（J専）＝Jarvis実行専属**。起動は **人が頼む** が本線。

| 項目 | 内容 |
|---|---|
| 識別 | **（J専）**＝Jarvis のみ実行（他ツール送金禁止） |
| 位置づけ | プレイブック枠。通常社員のように他ツール実行しない |
| 合図 | **`/adjust_cash`**＝本係発動（人が頼む言い回しも同義。616 手渡しは副） |
| 実行入口 | Cursor **`/adjust_cash`**（skill `adjust-cash`・Jarvis） |
| 促し | **616**（検知のみ → Jarvis へ手渡し） |
| 設計正本 | [`設計案_20261021.md`](./設計案_20261021.md) |
| Cursor ルール | `.cursor/rules/jarvis-agent-617-fund-transfer.mdc` |
| Slack | `#report`／`#consult` `【報告】617 資金移動（J専）｜…` |
| 組織図 | [ビルダー共有](https://agent-team-builder-teal.vercel.app/s/uksxiDIzE1AEckKH)（追記待ち・表示名に（J専）） |
| 作業フロー | [`flow.md`](./flow.md) · [FF編集](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_duOrNmGET7-E_c7AAQE9fLfO) · [閲覧](https://flowforge-259747770348.asia-northeast1.run.app/share/NYLpUySk0tY27PvI) |
| 指示書 | [`CLAUDE.md`](./CLAUDE.md) |
