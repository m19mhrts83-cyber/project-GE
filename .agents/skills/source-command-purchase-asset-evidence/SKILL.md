---
name: "source-command-purchase-asset-evidence"
description: "Migrated source command `purchase-asset-evidence`"
---

# source-command-purchase-asset-evidence

Use this skill when the user asks to run the migrated source command `purchase-asset-evidence`.

## Command Template

# 購入時・金融資産／残債エビデンス収集

呼び出し: **`/purchase-asset-evidence`**

スキル正本:

- 個人: `~/.cursor/skills/purchase-asset-evidence/SKILL.md`
- リポ: `.cursor/skills/purchase-asset-evidence/SKILL.md`
- 詳細: `.cursor/skills/purchase-asset-evidence/reference.md`

このコマンドが呼ばれたら、**スキルの手順に従う**（説明だけで終わらない）。

---

## 第1ターン — 収集まで

1. 宛先パートナー／保存先・目的（2,000万証明等）・税務同梱の有無を1行で確定（分かるなら省略）。
2. `3.送信添付/YYYY-MM-DD_金融資産スクショ/` を作り、オーケストレータを回す:

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_purchase_asset_evidence.py \
  --out '（絶対パス）' --only all
```

3. チャットに収集表（成功／スキップ理由）。スキップ画面は `_skip_内部用/`。
4. 依頼どおりなら `4.送信下書き.txt` を1通まとめに更新＋README／`5.やり取り.md` 同期。
5. **送信プレビュー**を出し「これで送ってOK？」で止める（了承前は送らない）。

---

## 第2ターン — 了承後のみ送信

了承後: 311ゲート → `yoritoori_send.py`（`--via` は推測しない）。
