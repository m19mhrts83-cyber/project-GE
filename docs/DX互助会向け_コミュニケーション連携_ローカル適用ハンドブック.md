# DX互助会向け_コミュニケーション連携_ローカル適用ハンドブック

## 0. この手順のゴール

各メンバーのローカル環境で、次の 5 手段を Cursor 運用で再現する。

1. Gmail API
2. ChatWork API
3. iMessage
4. LINE（個人・グループ）
5. LINE（オープンチャット）

---

## 1. 先に揃えるファイル（最小セット）

## 1-1. スクリプト

- `C1_cursor/1b_Cursorマニュアル/gmail_to_yoritoori.py`
- `C1_cursor/1b_Cursorマニュアル/imessage_to_yoritoori.py`
- `C1_cursor/1b_Cursorマニュアル/chatwork_to_yoritoori.py`
- `C1_cursor/1b_Cursorマニュアル/yoritoori_send.py`
- `line_unofficial_poc/chrline_sync_to_yoritoori.py`
- `line_unofficial_poc/chrline_open_chat_to_md.py`
- `line_unofficial_poc/chrline_open_chat_realtime_watch.py`

## 1-2. ルール（.cursor/rules）

- `partner-email-check.mdc`
- `partner-email-send.mdc`
- `open-chat-archive.mdc`
- `815-openchat-no-reply-proposal.mdc`

## 1-3. 設定・認証

- `連絡先一覧.yaml`（パートナー情報）
- Gmail: `credentials.json` / `token.json`
- ChatWork: `.env` に `CHATWORK_API_TOKEN`
- LINE: `LINE_UNOFFICIAL_AUTH_DIR` と CHRLINE 認証
- OpenChat: `open_chat_routes.yaml`

---

## 2. 導入手順（推奨順）

1. **Gmail API を有効化し認証取得**  
   - `credentials.json` 配置  
   - 初回実行で `token.json` 取得
2. **連絡先一覧を整備**  
   - メール・電話・ChatWork room id を必要分登録
3. **4系統取り込み（Gmail/iMessage/ChatWork/LINE）を確認**
4. **OpenChat ルートを設定して同期確認**
5. **ルールを配置して Cursor 依頼文で再現確認**

---

## 3. Cursor への依頼テンプレート（そのまま使える文）

## 3-1. 受信取り込み

`パートナーからのメールなどを確認して。`

期待動作:
- Gmail / iMessage / ChatWork / LINE を実行
- 該当 `5.やり取り.md` に追記

## 3-2. メール送信

`LEAF へメール送信して。送信前に経路（Gmail/iMessage）は確認して。`

期待動作:
- `yoritoori_send.py` で送信
- 4.送信下書き.txt を使用

## 3-3. OpenChat 取り込み

`LINE のオープンチャットを同期して。`

期待動作:
- `chrline_open_chat_to_md.py` 実行
- `open_chat_routes.yaml` のルートへ追記

## 3-4. 815 運用（情報収集）

`815オプチャの有益情報を、返信提案とは別枠で共有して。`

期待動作:
- 返信提案には 815 を含めない
- 有益情報のみ別枠で通知

---

## 4. ルールのアレンジ指針

## 4-1. 最小運用（まず動かす）

- `partner-email-check.mdc`
- `partner-email-send.mdc`

## 4-2. OpenChat 運用追加

- `open-chat-archive.mdc`
- `815-openchat-no-reply-proposal.mdc`

## 4-3. アレンジ時に崩さない点

- 送信導線を `yoritoori_send.py` に統一する
- 取り込み導線をルール上で固定する
- 返信提案と情報共有の条件を分離する

---

## 5. 失敗時チェックリスト

## Gmail
- `credentials.json` / `token.json` の配置先が正しいか
- OAuth 同意画面がテストのままでないか
- `invalid_grant` 時に token 再発行済みか

## ChatWork
- `CHATWORK_API_TOKEN` が設定済みか
- `chatwork_room_id` が連絡先一覧にあるか

## iMessage
- 実行端末が macOS か
- 権限・端末状態に問題がないか

## LINE / OpenChat
- `LINE_UNOFFICIAL_AUTH_DIR` が設定済みか
- CHRLINE のログイン状態が有効か
- `open_chat_routes.yaml` の `square_chat_mid` と出力先が正しいか

---

## 6. OpenChat スレッドのBeta運用

LINE OpenChat は API 側制約でスレッド本文が取り切れない場合がある。  
その場合は次の運用を推奨。

1. まず自動同期でメインを回収
2. 重要スレッドだけ手動補完
3. 815 は「返信提案」ではなく「有益情報共有」で運用

---

## 7. 導入完了の判定

以下を満たせば導入完了。

- 5 手段のうち必要手段が動作確認済み
- `5.やり取り.md` に追記される
- Cursor 依頼テンプレで再現できる
- ルールの意図を説明できる（なぜその運用か）

---

## 8. 勉強会向け補足（配布時に伝えること）

- 「まず最小運用から始める」こと（全部を初回でやらない）
- OpenChat スレッドは Beta（制約前提）で扱うこと
- ルールはコピー後に必ず各自の運用に合わせて調整すること
