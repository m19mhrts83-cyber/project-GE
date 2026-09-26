# Grok「コーチング部長」× advisor-weekly-pack Action 手順（2026-09-26）

## 目的

日曜ルーティン先頭で Cloud プロキシを叩き、応答 `markdown` を材料にする。  
**GSK_API_KEY は Grok に渡さない。** 渡すのは `ADVISOR_WEEKLY_PACK_SECRET` のみ。

| 項目 | 値 |
|---|---|
| URL | `https://jarvis-dashboard-amber.vercel.app/api/advisor-weekly-pack` |
| Method | `POST`（`GET` も可） |
| Header | `Authorization: Bearer <ADVISOR_WEEKLY_PACK_SECRET>` |
| Body | `{}` または空 |

秘密の正本: `.env.jarvis_private` の `ADVISOR_WEEKLY_PACK_SECRET`（Vercel 同名 env と一致）。**チャットに貼らない。**

## 現状（Jarvis 実施結果）

| 項目 | 状態 |
|---|---|
| Instructions 再貼り（CDP） | ✅ ★コーチング部長 |
| ルーティン「コーチング部 · 週次」指示差し替え | ✅ SB週次パック取得が先頭 |
| Custom Action / HTTP Action UI | **Grok Bot に ChatGPT 型 Action UIは見当たらない**（Plugins/OAuth 本線） |
| 秘密をチャット経由で渡す | **禁止**（一度露出→即ローテ済み） |

## 推奨の次（人が1回）

1. Grok Bot で ★コーチング部長を開く  
2. Plugins / Skills / Computer のうち、**HTTP を秘密付きで呼べる入口**があれば:
   - Name: `advisor-weekly-pack`
   - 上記 URL + Bearer（値は `.env.jarvis_private` からコピー。チャット禁止）
3. 無ければ **Computer Skill** として「日曜ルーティン時に curl POST」を Bot に作らせ、秘密は Bot の安全な保存欄（あれば）へ。チャット履歴には書かない  
4. Test: 応答 JSON に `ok: true` と `sb_count`（数字）があれば OK

## フォールバック

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_advisor_weekly_pack.py --apply
```

FRIDAY Mesh 可（Mac 要起動）。

## 関連

- 仕様: `docs/Grok_アドバイザー週次材料パック_仕様_20260926.md`
- paste: `config/grok_coaching_bucho_grok_paste.md` / `config/grok_coaching_bucho_routine_週次.md`
