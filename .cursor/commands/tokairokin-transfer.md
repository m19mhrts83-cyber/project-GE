# 東海労金 インターネットバンキングでログイン・振込を行う

このコマンドは **次の2ステップ** で動く。認証情報（.env）は未設定時やエラー時に案内する。

---

## ステップ 1: 振込内容の確認

- **「振込先（銀行・支店・口座番号）・振込金額を教えてください」** と聞く。
- ユーザーが回答したら、その内容を把握する。
- 銀行コード・支店コードが必要な場合（例: 三菱UFJ 熱田支店 → 銀行0005、支店405）は調べて補完する。

---

## ステップ 2: ログイン → 振込の実行

ユーザーから振込内容の回答を受けたら、次の順で実行する。

### 事前確認（このチャットから実行するとき）

- **OTP（ワンタイムパスワード）はユーザーの手動入力・実行確定が無いと振込は完了しない**。スクリプトがログやメッセージで終了していても、**OTP を操作していなければ資金移動は済んでいない**可能性が高い。
- **Cursor の統合ターミナル**では Enter が自動で処理されることがあり、OTP のホールドや合言葉待ちが意図どおり止まらない。**OTP の確認や Enter 待ちが絡むときは Terminal.app で同じコマンドを実行する**よう案内する。
- **`--non-interactive` / `TOKAIROKIN_NON_INTERACTIVE=1`** は Enter 待ちを短い待機で潰すため、**OTP を手入力で確実に止めたい検証・本番運用には向かない**。Jarvis の自動実行など別用途では、OTP 完了はユーザー側ブラウザ操作で別途確認する前提とする。

### 1. スクリプトの実行

- **カレント**: `~/git-repos/215_kamiooya/C1_cursor/browser_automation`（詳細は `~/git-repos/docs/運用コマンド一覧.md` の「ブラウザ自動化」）
- **振込内容を指定して実行**（フォーム自動入力）:
  - `.env` に `TOKAIROKIN_DEFAULT_BANK_CODE` 等の既定振込先があれば、**金額だけ**指定して実行できる:
    ```
    .venv/bin/python fetch_after_login.py tokairokin --amount 240000
    ```
  - 金融機関名・支店名で入力する場合（東海労金の検索画面向け）:
    ```
    .venv/bin/python fetch_after_login.py tokairokin --bank-name "三菱UFJ銀行" --branch-name "熱田支店" --account 0526519 --amount 10000
    ```
  - 銀行コード・支店コードで入力する場合:
    ```
    .venv/bin/python fetch_after_login.py tokairokin --bank 0005 --branch 405 --account 0526519 --amount 10000
    ```
- 振込パラメータなしの場合は `python fetch_after_login.py tokairokin` のみ。
- 無操作でセッション中断される場合・セレクタ検証のみのとき: `--inspect-transfer-screen`（振込URL表示直後に Enter 待ち）。待機中は `session_keepalive_*` で軽いページ操作を挟む。
- **未セットアップの場合**は、215 の browser_automation README を参照し、東海労金用の config_tokairokin.yaml と .env の設定を案内する。

### 2. ログインURL（案内ページ）

- 東海労金インターネットバンキング（入口の案内）: https://ib.rokin.jp/nprotect/?bid=22  
  実ログインフォームは config の `login_url`（parasol.anser.ne.jp）側。

### 3. ログイン後の「主経路」と合言葉

検証上、**合言葉（追加認証）画面は出ない運用**がありうる。その場合の位置づけは次のとおり。

**用語の整理（指示との対応）**: 「検出キーワード」には **二種類**ある。（A）**合言葉画面であることを示すマーカー**（`secret_phrase_page_markers` 等）が DOM に現れた場合は **追加認証として扱い、勝手にスキップしない**。（B）**ログイン後トップ相当かどうか**は `post_login_dashboard_detect` で判定する。**ユーザーの意図する主経路**は「（A）が検出されない ∧ （B）でログイン後トップ相当と判定できる → 合言葉用 Enter 待ちを省略して振込へ」である。

- **主経路**: 合言葉画面のマーカーが **検出されない** こと、および **`post_login_dashboard_detect`**（既定では URL に `BLI001Dispatch` を含む等）で **ログイン後トップ相当** と判定できること → **合言葉用の Enter 待ちをスキップ**し、そのまま振込メニュー遷移へ進む。
- **主経路から外れたとき**: stderr に「主経路から外れた可能性」と出たら、ブラウザで実画面を確認する。**トップなのに止まる**なら `post_login_dashboard_detect` を調整。**合言葉が実際に出ている**なら `secret_phrase_page_markers`・`secret_phrase_auto`・入力セレクタを見直す。

詳細キーは `config_tokairokin.yaml` の `post_login_dashboard_detect`（`allow_dispatch_url_without_body_markers` など）と README を参照。

### 4. 振込フォームと OTP（ワンタイムパスワード）

- 振込パラメータ（`--bank` 等）を渡した場合、`transfer_form` のセレクタが設定されていれば **確認画面・実行画面の手前まで**自動入力する。
- **OTP の既定運用（実運用の正）**
  - 東海労金の OTP は **メールではなくスマホアプリ「ワンタイムPW」**。
  - `fetch_otp_from_gmail: false`（既定）のとき、スクリプトは **OTP を自動入力しない**。`otp_hold_before_manual_entry` 等で **入力・実行確定の直前でホールド**し、ユーザーがアプリで確認してブラウザへ入力・実行したうえで、ターミナルの案内どおり進める。
- **オプション**: メール経由で OTP を自動取得したい場合のみ `fetch_otp_from_gmail: true` とし、`tokairokin_gmail_otp.py`・`.env` の `TOKAIROKIN_OTP_*` を設定する（README「4. ワンタイムパスワード」）。
- **振込完了の判断**: ブラウザの完了画面・残高で確認する。スクリプト終了だけでは完了と断定しない。
- 初回は `headless: false` のまま実行し、画面でログイン〜OTP まで確認するよう促す。

---

## 注意

- ログインに失敗している場合は、その旨を伝え、headless: false で画面確認するよう促す。
- 認証情報（.env）は 215 の browser_automation にあり、リポジトリに含めずユーザー自身で設定する。
- **振込は金銭を移動する操作のため、実行前に振込内容をユーザーに確認させる。**
