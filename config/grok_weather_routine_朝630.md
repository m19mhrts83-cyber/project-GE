# Grok ルーティン「天気 · 朝6:30」— 指示コピペ用

| 項目 | 値 |
|---|---|
| 名前 | 天気 · 朝6:30 |
| チャンネル | 天気お知らせ |
| トリガー | 毎日 **6:30 JST** |

## 指示（貼る）

```
@天気お知らせ
【朝パック】
1. Drive「【with Grok bot】/outbox_to_teams/weather/」の本日 MD を読む。
2. 天気・予定を短く整理。
3. 材料の「## 乗る便（何時何分）」があるときは、発時刻・列車名／便名をそのまま投稿に載せる（曖昧な「おすすめ」に置き換えない）。予約があれば予約優先。
4. 材料が無い／古い場合は豊明の天気＋カレンダー。乗換時刻はでっち上げない（材料待ちと書く）。材料未着だけで終わらない。
5. 済んだら 90_archive/ へ。パスワードは出さない。
```

## Mac 側（材料 · 6:05）

```bash
cd ~/git-repos
~/selenium_env/venv/bin/python scripts/jarvis_weather_morning_brief.py
# 定時: ~/git-repos/launchd/install_weather_morning_brief_launchd.sh
```
