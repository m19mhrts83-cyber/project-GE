# Grok「コーチング部長」× advisor-weekly-pack 手順（2026-09-26 · 更新 2026-09-27）

## 目的

日曜ルーティン先頭で SB 週次パックを材料にする。  
**GSK_API_KEY は Grok に渡さない。シークレット値をチャットに貼らない。**

## 本線（Jarvis 確定 2026-09-27）

| 優先 | 経路 | 条件 |
|---|---|---|
| 1 | **Drive outbox**（`週次材料パック_*.md`） | Mac launchd **日曜 18:40** が `--apply` |
| 2 | **Computer Skill** `advisor-weekly-pack` | Mac 起動中。curl は **env 変数名のみ**（値は `.env.jarvis_private`） |
| 3 | 失敗1行＋薄い材料 | API/Skill 失敗時も止めない |

```bash
# launchd 導入
~/git-repos/launchd/install_advisor_weekly_pack_launchd.sh

# 手動投下
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_advisor_weekly_pack.py --apply
```

## Computer Skill 本文（値は埋め込まない）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a && \
curl -sS -X POST 'https://jarvis-dashboard-amber.vercel.app/api/advisor-weekly-pack' \
  -H "Authorization: Bearer $ADVISOR_WEEKLY_PACK_SECRET" \
  -H 'Content-Type: application/json' -d '{}'
```

Cloud 直叩き（人間・Jarvis 検証用）:

| 項目 | 値 |
|---|---|
| URL | `https://jarvis-dashboard-amber.vercel.app/api/advisor-weekly-pack` |
| Method | `POST` |
| Header | `Authorization: Bearer <ADVISOR_WEEKLY_PACK_SECRET>` |

秘密の正本: `.env.jarvis_private` ＋ Vercel 同名 env。

## 教訓（2026-09-27）

- Skill に Bearer **値**を未投入のまま Cloud 直叩き → **401 / 「シークレット未設定」**
- 対処: Drive 本線化 ＋ Computer は env 参照（チャットに値を貼らない）

## 関連

- 仕様: `docs/Grok_アドバイザー週次材料パック_仕様_20260926.md`
- ルーティン: `config/grok_coaching_bucho_routine_週次.md`
- paste: `config/grok_coaching_bucho_grok_paste.md`
