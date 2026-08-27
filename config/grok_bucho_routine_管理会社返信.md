# Grok ルーティン「不動産Daily · 管理会社返信」— 指示コピペ用

チャンネル **不動産Dailyチーム** に追加する（週数回〜毎日軽く可）。

## ルーティン設定（推奨）

| 項目 | 値 |
|---|---|
| 名前 | `不動産Daily · 管理会社返信` |
| Active | ON |
| トリガー | スケジュール **毎日 11:00（JST）** または週3（例: 月水金） |

## 指示（そのまま貼る）

```
チャンネル「不動産Dailyチーム」で、管理会社・事前確認の返信仕分けを行う。

1. 参謀が Jarvis の提案（または estate 受信の要約）を確認
2. 募集・紹介 OK → チャンネルに1行:
   --mark {id} --status replied --vacancy-listing-ok true [--kodate-mgmt-ok true|false]
3. 不可 →:
   --mark {id} --status skip --vacancy-listing-ok false --note "不可: …"
4. 曖昧なら松野に1行で確認し、勝手に空室メール対象にしない

空室対策メールの一斉送信は Jarvis／松野（send_mail）。S9 は送らない。
北区と緑区で宛先リストは別（--vacancy-eligible --lane …）。
```
