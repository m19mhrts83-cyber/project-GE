# 単独Web検証 — パイロットメモ（Phase 5）

- **作成日**: 2026-08-01
- **対象**: 神・大家メンバー 2〜3名
- **完了定義**: 色付き下地（C0）まで。C1は任意
- **入口**: `shuhen-auto.html`（Raimo用語なし）

関連: [`18_単独Web検証_仕様.md`](18_単独Web検証_仕様.md)

---

## 起動（検証ホスト）

```bash
cd ~/git-repos
set -a && source .env.jarvis_private && set +a
# 任意: 共有リンク用トークン / ポート
# export SHUHEN_AUTO_TOKEN='短い共有用文字列'
# export SHUHEN_AUTO_PORT=8770
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/shuhen_auto_server.py
```

メンバーURL例:

- ローカル: `http://127.0.0.1:8765/shuhen-auto.html?demo=1`（ポートは `SHUHEN_AUTO_PORT`）
- トークンあり: `...?token=...`
- Pages静的UIのみの場合は `?api=https://（APIホスト）` が必要（生成APIは Pages 単体では動かない）

**検証済み（2026-08-01・Grandole）**: CLI で施設8/8 Places確定・C0 PNG生成成功。C1は `gemini-2.5-flash-image` で ready。

CLIスモーク:

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/shuhen_auto_pipeline.py \
  --property Grandole志賀本通 \
  --address '愛知県名古屋市北区杉栄町' \
  --out /tmp/shuhen_grandole
```

---

## 計測シート（コピーして使う）

| # | 日付 | 参加者 | 物件 | 所要分 | 施設件数 | 明らかな誤り | C1利用 | C1採用 | 完了(C0まで) | メモ |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 |  |  |  |  |  |  | 有/無 | 有/無/— | 有/無 |  |
| 2 |  |  |  |  |  |  |  |  |  |  |
| 3 |  |  |  |  |  |  |  |  |  |  |

**成功の目安**: 3件中2件以上が「完了(C0まで)=有」、明らかな誤りが致命的でないこと。

---

## メンバー向け一言案内（貼付用）

```text
周辺MAPを自動作成する検証ページです。
1. 物件名と住所を入れる
2. 「周辺MAPを作成」を押す（数分かかることがあります）
3. 周辺施設・地図・ベージュの色付き下地が出ればOK
4. 「色味をさらに寄せる」は任意。道路がおかしいときは破棄
印刷用の最終仕上げはこれまでどおり Canva でお願いします。
```

---

## フィードバック記録

（パイロット後に追記）

-
