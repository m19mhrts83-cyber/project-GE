# Grok ルーティン「天気 · 朝6:30」— 指示コピペ用

| 項目 | 値 |
|---|---|
| 名前 | 天気 · 朝6:30 |
| チャンネル | 天気お知らせ |
| トリガー | 毎日 **6:30 JST** |

## 指示（貼る）

```
@天気お知らせ
Drive「【with Grok bot】/outbox_to_teams/weather/」の最新 MD を読み、
天気と本日の予定を松野向けに3〜7行で投稿。済んだら 90_archive/ へ。
0件なら「材料未着」と1行。
```

## Mac 側

```bash
cd ~/git-repos
~/selenium_env/venv/bin/python scripts/jarvis_weather_morning_brief.py
```

launchd / `jarvis_morning_mac_refresh.py` から 6:00 頃に実行可。
