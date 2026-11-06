# LINE添付の会員向け根拠・ソース一覧

- executor: Chappy
- status: running
- request: 保存したLINE添付を回答根拠とLINEソース一覧の両方から開く。
- branch: codex/openchat-member-attachments-20261107
- scope: 添付ごとの確定ソースID、検索用メタデータ、既存会員認証下の署名URL、画面導線、日次メタデータ更新。
- acceptance: 本文由来IDへ推測で結合しない。保存済み添付が一覧・ファイル名検索・根拠から開ける。匿名/未承認/退会/失効を拒否。既存コミュニティ添付を維持。バイナリ再取得やOCR/文字起こしを追加しない。
- release: migration→Edge→Raimo画面→日次runtimeの順。既存の運営了承・マージを含む実装指示と、今回のLINE会員表示依頼の範囲で進める。新たな課金変更・外部連携の追加は含めない。既存保存を停止しない。

設計: `openchat_attachments.id`から決定的な`oc_`＋64桁のソースIDを作り、添付専用の発言行を保持する。投稿文・日時は原本APIから取得できた値のみを使用し、欠損は欠損として表示する。既存MDの発言とは自動結合しない。ファイル内容は未解析と明記する。

## 実装・検証

- migrationは専用ソースを作り、非公開/excludedソースは会員用ビューから除外。繰返し適用で重複せず、excludedを勝手にreadyへ戻さない。
- Edgeは既存の会員・親ログイン確認を共用し、source別にテーブル・バケット・パスを固定。ブラウザへroom_id/message_idやservice_roleを返さない。
- 一覧はファイル名検索と「添付のみ」、回答根拠は同じソースIDからの添付リンク。未解析ファイルの内容を回答で推測しない。
- 日次は追加のLINE呼出しなしに既存走査から日時・ルーム・投稿文を取得し、保存済みファイルはmetadataだけ更新。過去分のルーム名は元room_idの完全一致でのみ補完。日時・投稿文は推定しない。
- 一覧・ファイル名検索ではAIを呼ばず、OCR/動画解析は行わない。メタデータの意味検索用embeddingは既存の週次更新対象となるため、その既存AI使用量は生じる。
- Node84成功/既存1skip、Python全体255成功、Deno型検査と4試験、Next.js build成功。PGlite PostgreSQL実エンジンでmigration再適用・private権限・日時・excluded維持・検索を確認。
- 全権限の実会員アカウント試験は未完了。ローカル権限試験の成功を実本番試験済みとは扱わない。

## 適用手順

1. `20261107_openchat_attachment_sources.sql`を適用（旧migration再適用は不要）。
2. `community-attachments`と`semantic-search`を配備。既存秘密・フラグは変更しない。
3. 現行Raimoのhtml/jsだけを反映し、認証API定義を旧版へ巻き戻さない。
4. workerとqueueモジュール・日次の新コードを独立runtimeへ固定し、`--apply --sync-sources-only --routes-yaml ... --limit 100`を残件がなくなるまで実行。LINEログイン・メディア再取得は不要。
5. 会員ログインで「添付のみ」・ファイル名検索・実ファイル表示を確認。回答の根拠から同じソースと添付へ辿れることを確認。

ロールバックはUIを直前版へ戻して導線停止し、必要なら専用ソースをexcludedへ。原本・queue・旧発言を削除しない。新ログ行を一括削除したり元migrationを逆実行しない。
