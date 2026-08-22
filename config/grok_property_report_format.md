# Grok 物件調査 Bot — レポート形式（正本）

松野エステイト Gmail 宛 `[Grok調査]` メール。Jarvis `property_mail_match` が `mail_grok` として取込。

## 送信方針

- **宛先**: `matsuno.estate@gmail.com`（松野エステイト宛は承認不要・送信してよい）
- **件名**: `[Grok調査] {市区町村} {物件短名}`
- **From**: m19m 等（estate ログインは Grok VM に載せない）

## 本文テンプレート

```
件名: [Grok調査] {市区町村} {物件短名}
本文:
---
source: grok_bot
bot: 物件調査
report_id: {YYYYMMDD-HHMM}
---

## 物件
- 所在:
- 価格_万:
- 土地面積:
- 建物:
- 駐車場: あり|なし|不明
- URL:

## 土地評価
- 方式: 路線価|倍率
- 倍率:
- 土地値100%判定: 聞く|保留|見送り
- 根拠URL:

## 人口（チャプロ軸）
- 評価: 安全|選別|攻め
- 表: （Markdown 1行）

## 総合
- 聞く価値: 聞く|保留|見送り
- 理由1行:
```

## Jarvis 中継（Cursor から送る場合）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_grok_report_mail.py --file report.md --send
```

## 取込

```bash
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_property_mail_match.py --grok-only --dry-run
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_property_mail_match.py --apply
```
