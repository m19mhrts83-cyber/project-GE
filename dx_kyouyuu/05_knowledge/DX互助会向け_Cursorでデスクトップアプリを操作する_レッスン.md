# Cursor でデスクトップアプリを操作する — レッスン＆ラーン（2026-08-30）

DX互助会メンバー向け。**Web サイトの Playwright**（別資料「ブラウジングオートメーション」）の隣にある話です。  
対象は **Mac に入っているアプリそのもの**（例: Cursor の Grok Bot.app）。

---

## 1. 最初に信じていたこと（誤り）

「Cursor のエージェントはエディタとブラウザは触れるが、**デスクトップアプリは操作できない**」

これは半分正しく、半分古いです。

| 経路 | できること | できないこと |
|---|---|---|
| **Cloud Agent**（cursor.com） | リポジトリのコード | 自分の Mac の画面・アプリ |
| **Cursor 内蔵ブラウザ** | そのタブの Web | 別プロセスのアプリ |
| **ローカル Agent + シェル** | Mac 上のプロセス | 「公式 API が無いアプリ」と決めつけること |

アプリ操作ができなかった本当の理由は「AI に権限が無い」ではなく、**対象アプリに話しかける口が無かった**ことです。

---

## 2. きっかけ（何が変わったか）

Grok Bot（Cursor のデスクトップ Bot アプリ）のメンバー追加・指示貼付・ルーティン作成を、手作業なしでやりたかった。  
見た目はネイティブアプリだが、中身は **Electron（Chromium）** だった。

Chromium 系なら、Chrome と同じ **CDP（Chrome DevTools Protocol）** を開けば、ページの DOM をクリック・入力できる。  
銀行サイト用に既にやっていた「Chrome を `--remote-debugging-port` で起動する」の延長だった。

```
Web（Playwright / CDP Chrome）
        ↑ 同じ口
Electron アプリ（Grok Bot 等）  ← 今回ここがつながった
```

**動きの順**

1. アプリを **デバッグポート付き**で起動する  
2. `http://127.0.0.1:ポート/json/list` でページの WebSocket を取る  
3. Python から CDP で `Runtime.evaluate`（DOM）と `Input.dispatchMouseEvent`（実クリック）

これで「操作できない」は撤回。以降は UI の癖（React 入力・ホバーメニュー）との戦い。

---

## 3. Cursor に渡す指示（コピー用）

メンバーが自分の環境で試すときの依頼文です。Grok Bot 専用ではなく、**Electron / Chromium 系アプリ一般**に使えます。

```text
この Mac アプリを、手作業なしで操作して。

前提:
- ローカルの Cursor Agent（Cloud ではない）で実行する
- 中身が Electron / Chromium なら、Chrome DevTools Protocol (CDP) で触れる
- Cursor 内蔵ブラウザは使わない（別プロセスだから）

やってほしいこと:
1. アプリが Chromium 系か確認する（Info.plist / プロセス名 / Electron Framework）
2. いったん終了し、次の形で起動する
   open -a "アプリ名" --args --remote-debugging-port=9222 --force-renderer-accessibility
3. curl http://127.0.0.1:9222/json/list で type=page の WebSocket を取る
4. Python（websockets）で CDP 接続し、やりたい画面操作を実行する
5. element.click() だけで消える入力は、React の onChange か実座標クリックを試す

ポート 9222 が他用途なら空いている番号を使う。localhost 以外に公開しない。
```

**短い版**

```text
Grok Bot を CDP（9222）で操作して。内蔵ブラウザは使わず、
open -a "Grok Bot" --args --remote-debugging-port=9222 で口を開けてから進めて。
```

---

## 4. レッスン（つまずきと直し）

| つまずき | 直し |
|---|---|
| アプリは開いているが `json/list` が空 | **CDP なしで先に起動している**。終了して `--remote-debugging-port` 付きで入れ直す |
| `element.click()` したのに画面が変わらない | メニュー系は座標クリック。画面外なら `scrollIntoView` してから |
| テキストを入れても保存されない | React: native の value setter + `_valueTracker` + `onChange` |
| 「スケジュール」に矢印があるのに選べない | クリックではなく **ホバー**してサブメニューを出してから |
| Cloud エージェントに頼んだ | Mac の画面は見えない。**ローカル Agent** に切り替える |
| ポートが既に銀行 Chrome で塞がっている | アプリごとにポートを分ける（例: アプリ 9222、Chrome 9223〜） |

---

## 5. やってよい範囲 / やらない

**よい**: 自分の Mac・自分のログイン済みセッションでの定型操作（設定貼付、ルーティン作成、テスト実行）。  
**やらない**: デバッグポートを LAN に晒す、他人の画面の遠隔操作、パスワードをチャットに貼る。

対外送信・振込の最終クリックは、従来どおり人間の確認を挟む。

---

## 6. 関連

- ブラウジング（Web）: `dx_kyouyuu/05_knowledge/DX互助会向け_ブラウジングオートメーションの取り組み紹介.md`
- Jarvis 本線ヘルパー: `scripts/jarvis_grok_bot_cdp.py`
- Jarvis ルール: `.cursor/rules/jarvis-mac-app-cdp.mdc`
- コマンド正本: `docs/運用コマンド一覧.md` §7.7
