# DX互助会向け_コミュニケーション連携_ローカル適用ハンドブック

## 0. この手順のゴール

各メンバーのローカル環境で、次の 5 手段を Cursor 運用で再現する。

1. Gmail API
2. ChatWork API
3. iMessage
4. LINE（個人・グループ）
5. LINE（オープンチャット）

---

## 0-1. 配布先での読み方（フォルダ構成が PC ごとに違う場合）

パッケージを受け取ったメンバー向け。**「どこに置くか」は人ごとに違ってよい**前提で読んでください。本書や同梱 MD に出てくる `215_kamiooya/...` などは、作者環境での**相対パスの例**です。自宅・会社・クラウド同期の有無によってフォルダ名は変わるため、**例のパスをそのままコピーして実行しない**でください。

### 資料の役割（3 点）

| 資料 | 使い方 |
|------|--------|
| **本ハンドブック** | 全体の地図。何を揃え、どんな順で試すか。 |
| [DX互助会向け_パッケージ参照プロンプト一覧.md](DX互助会向け_パッケージ参照プロンプト一覧.md) | Cursor に貼る**依頼文のコピペ元**。 |
| [運用コマンド一覧.md](運用コマンド一覧.md) | **シェルコマンドと `cd` 先の正本**。環境が違うときは、自分のワークスペースに合わせて書き換える（または Cursor に書き換えを依頼する）。 |

推奨の読み順: **本書で目的を把握 → プロンプト一覧で依頼文をコピー → 運用コマンド一覧でパスを自分用に合わせる。**

### 手順のイメージ

1. **ローカルに保存する**  
   ZIP でも Git でもよい。**Cursor で「フォルダを開く」した先**を、以降の手順での「ワークスペースのルート」とみなす。同梱の MD は、ルート配下の分かりやすい場所（例: `docs/`）に置くと参照しやすい。
2. **参照ファイルとして Cursor に渡す**  
   チャットで **`@` + ファイル名**（または該当 MD をコンテキストに追加）し、「このハンドブックに沿ってセットアップして」と依頼する。  
   **`.cursor/rules/*.mdc`** は Cursor のプロジェクトルールとして配置する。ルールが無い環境では、プロンプト一覧に書いた「期待する動き」とは一致しない。
3. **環境に合わせる**  
   まず **自分のルートパス・スクリプトを置いた親フォルダ** を決め、[運用コマンド一覧.md](運用コマンド一覧.md) の `cd` やスクリプトへの相対パスを、その前提で読み替える。

### 導入時の最初の依頼文（例）

ワークスペースを開いたうえで、次をコピペしてもよい（パスは Cursor が自分用の手順に落とし込みやすくなる）。

```text
コミュニケーション連携パッケージを導入します。まず次を確認してください。
1) いま Cursor で開いているワークスペースのルート（フォルダのフルパス）
2) スクリプト・設定・メモを置く親フォルダ（1 と同じでよいか）

その前提で、同梱の「DX互助会向け_コミュニケーション連携_ローカル適用ハンドブック」に沿い、
運用コマンド一覧の cd / パスを私の環境用に書き換えた手順を短く提示してください。
```

### セキュリティ（配布パッケージに含めないもの）

- `credentials.json` / `token.json`、ChatWork の API トークン、個人用の連絡先一覧の実データなどは**共有 ZIP に入れない**。各自がルールに従ってローカルに配置する。

---

## 1. 先に揃えるファイル（最小セット）

## 1-1. スクリプト

- `C1_cursor/1b_Cursorマニュアル/gmail_to_yoritoori.py`
- `C1_cursor/1b_Cursorマニュアル/imessage_to_yoritoori.py`
- `C1_cursor/1b_Cursorマニュアル/chatwork_to_yoritoori.py`
- `C1_cursor/1b_Cursorマニュアル/yoritoori_send.py`
- `line_unofficial_poc/chrline_sync_to_yoritoori.py`
- `line_unofficial_poc/chrline_open_chat_to_md.py`
- `line_unofficial_poc/chrline_open_chat_realtime_watch.py`（任意・常駐）
- `215_kamiooya/C1_cursor/1b_Cursorマニュアル/line_open_chat_thread_clip_to_yoritoori.py`（スレッド手動補完）
- （任意）`line_unofficial_poc/launchd/open_chat_healthcheck_runner.sh` … 認証疎通の通知用

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
3. **受信取り込み（ルールどおり 5 チャネル）を確認** … Gmail / iMessage / ChatWork / LINE（個人・グループ）/ オープンチャット同期
4. **OpenChat ルートを設定して同期確認**
5. **ルールを配置して Cursor 依頼文で再現確認**

---

## 3. Cursor への依頼テンプレート（そのまま使える文）

コピペ用の**一覧・表現の揺れを減らした版**は [DX互助会向け_パッケージ参照プロンプト一覧.md](DX互助会向け_パッケージ参照プロンプト一覧.md) を参照（配布パッケージ用）。本章はハンドブック内の最短記述です。

## 3-1. 受信取り込み

`パートナーからのメールなどを確認して。`

期待動作（`partner-email-check.mdc` 想定）:
- Gmail / iMessage / ChatWork / LINE（`chrline_sync_to_yoritoori.py`）/ オープンチャット（`chrline_open_chat_to_md.py`）を順に実行
- 該当 `5.やり取り.md`（およびオプチャ用 MD）に追記

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
- `LINE_UNOFFICIAL_AUTH_DIR` が設定済みか（**トーク同期とオープンチャットで同じパス**を使うと QR 負荷が増えにくい）
- CHRLINE のログイン状態が有効か（失効時は QR 再認証が必要・非公式 API の制約）
- `open_chat_routes.yaml` の `square_chat_mid` と出力先が正しいか
- 認証を OneDrive 等のクラウド同期直下に置いていないか（競合で QR が増えやすい。未設定なら `line_unofficial_poc/.line_auth_local` 既定を推奨）

---

## 5-1. OpenChat 認証まわり（QR を増やさないための要点）

実装の詳細は `line_unofficial_poc/chrline_client_utils.py` を参照。

1. **保存先を分けない** … `chrline_sync_to_yoritoori.py` と `chrline_open_chat_to_md.py` は、同じ `LINE_UNOFFICIAL_AUTH_DIR` と `build_logged_in_client` を使う。
2. **`.tokens/` に複数ファイルがあってもよい** … 更新日時の新しい順に試行し、有効なトークンがあれば QR なしで起動する。
3. **QR のあと必ず永続化** … 再認証で得たトークンを `.tokens` に保存しないと、次回また QR になりやすい。
4. **クラウド同期パスは避ける** … 環境変数でクラウド配下を指定すると警告が出る設計（セッション競合の抑止）。
5. **任意** … `LINE_CHRLINE_AUTO_OPEN_QR=1` で QR 画像を自動表示（回数は減らないが操作は楽）。
6. **任意** … `launchd/open_chat_healthcheck_runner.sh` で疎通失敗時に通知し、気づきを早める。

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

- **フォルダが人によって違う前提**の読み方は **§0-1** を最初に案内する
- 「まず最小運用から始める」こと（全部を初回でやらない）
- OpenChat スレッドは Beta（制約前提）で扱うこと
- ルールはコピー後に必ず各自の運用に合わせて調整すること
- 自然言語の依頼例は [DX互助会向け_パッケージ参照プロンプト一覧.md](DX互助会向け_パッケージ参照プロンプト一覧.md) を同梱すると再現しやすい
