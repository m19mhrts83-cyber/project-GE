# Grok ルーティン「不動産Daily · 管理会社返信」— 指示コピペ用

チャンネル **不動産Dailyチーム** に追加する（毎日軽く可）。

Jarvis が estate で返信を拾い、判定案＋返信下書きを出す。部長は仕分けと松野確認を助ける。

## ルーティン設定（推奨）

| 項目 | 値 |
|---|---|
| 名前 | `不動産Daily · 管理会社返信` |
| Active | ON |
| トリガー | スケジュール **毎日 11:00（JST）**（または週3: 月水金） |
| チャンネル | 不動産Dailyチーム |

## 指示（そのまま貼る）

```
チャンネル「不動産Dailyチーム」で、管理会社・事前確認の返信仕分けを行う。

【実行順】
-0. Jarvisボックス先読み（未処理があれば先に）

0. 開始1行: 【管理会社返信仕分け】

1. Jarvis の提案を正とする（なければ「Jarvis に管理会社返信ポーリングを」と1行）
- スクリプト: jarvis_grok_mgmt_reply_apply.py --days 14 --write-drafts
- 下書き場所: .jarvis_state/mgmt_reply_drafts/

2. 各社の判定（松野と相談。勝手に空室対象に確定しない）
- 募集・紹介 OK →:
  --mark {id} --status replied --vacancy-listing-ok true [--kodate-mgmt-ok true|false]
- 不可 →:
  --mark {id} --status skip --vacancy-listing-ok false --note "不可: …"
- 曖昧 → 松野に1行確認

3. 返信メール（2回目以降）
- 下書きをチャンネルまたは Jarvis 経由で松野に提示
- **松野承認後のみ送信**（初回の定型事前確認は確認不要・こちらでは送らない）
- 承認前に対外送信しない

4. 締め
- 判定件数・要承認の返信下書き件数を1行
- 空室一括送信は Jarvis／松野（--vacancy-eligible）。S9 は送らない

【禁止】
- 未承認の2回目以降メール送信
- 空室 Excel 一斉送信
- ハウスコム大曽根など既存取引先への新規開拓メール再送
```
