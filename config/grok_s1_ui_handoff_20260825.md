# S1 役割復元 — Grok UI 手作業（2026-08-25）

Jarvis が正本を更新済み。以下を Grok で実施。

## 1. 物件調査（S1）Instructions 再貼り

正本: `config/grok_property_bot_grok_paste.md`  
フェンス内（`# あなたの役割 — 物件調査 Bot` 〜 末尾）を全文差し替え。

要点: 自律探索＋聞くもの自動問合せ／経路3／キャプチャ必須／`## 問合せ` テンプレ。

## 2. 参謀（部長）Instructions 再貼り

正本: `config/grok_sanbo_bot_grok_paste.md`  
本日分＝キューのみ、S1物件探し＝別枠、を含む版。

## 3. ルーティン

| 名前 | 時刻 | 指示の正本 |
|---|---|---|
| `不動産Daily · 本日分` | 9:00（既存） | `config/grok_bucho_routine_本日分.md` の指示を更新貼り |
| `不動産Daily · S1物件探し` | **10:30（新規）** | `config/grok_bucho_routine_S1物件探し.md` |

チャンネル: **不動産Dailyチーム**。

## 部長へ一言（任意）

```
S1は二本柱。9時はキュー消化のみ。10:30が物件ポータル自律探索。
聞く判定は自動で第一問合せ可（経路3）。キャプチャ必須。[Grok調査]に問合せセクション。
```

## 動作確認（Mac）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_property_mail_match.py --grok-only --dry-run
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_s1_evidence_to_drive.py --poll-recent --dry-run
```

証憑設計: `docs/KURASHIFT_S1問合せ証憑_Drive_20260825.md`
