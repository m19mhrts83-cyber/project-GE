# Raimo マイミニアプリ：周辺MAP 自動作成（単独Web）

- **用途**: 物件名・住所を入れると洗い出し→地図→**C0色付き下地**まで進む単独Web（`shuhen-auto`）を、Raimo Tools／マイミニアプリから開く
- **コード正本**: GitHub Pages（ビルダに Maps／生成APIを丸ごと貼らない）
- **公開URL（Pages）**: `https://m19mhrts83-cyber.github.io/project-GE/shuhen-auto.html`
- **Raimo ミニアプリURL**: https://ma-qr4gudwmgqtg.raimo-app.buzz
- **編集URL**: https://raimo.buzz/miniApp/4344/edit
- **miniApp ID**: **4344**（`ma-qr4gudwmgqtg`）
- **生成API**: Pagesは静的UIのみ。**自分用（フル自動）はローカル `http://127.0.0.1:8770/`**（`scripts/shuhen_auto_open.sh`）
- **注意**: 8765 は Jarvis ダッシュボード。周辺MAP API は **8770**

関連: `18_単独Web検証_仕様.md` / `19_単独Web検証_パイロットメモ.md` / `12_Raimoミニアプリ_周辺MAP番号ピン.md`

---

## 方針

| 役割 | 置き場 |
|---|---|
| UI（HTML／JS） | Pages（上記 URL）／ローカル同一ファイル |
| 入口 | Raimo マイミニアプリ（番号ピン・MyPrompt と同列）※PagesはUIのみ |
| 生成オーケストレーション | **自分用: ローカル :8770**／将来: 別APIホスト |

番号ピン（4155）と同じ **リンク型**。フルアプリ移植はしない。

---

## Raimo 登録手順

1. Raimo → **Myミニアプリ** → 新規作成  
2. 名称: `周辺MAP_自動作成`  
3. 公開URL（上記 Pages）を開く／リンクとして配置。下の使い方テキストを添える  
4. Tools 上で `周辺MAP_番号ピン`・Step系 MyPrompt の近くに置く  
5. 発行された `ma-…` URL と編集URLを本ファイル先頭と `config/apps_prompts_catalog.yaml` に追記  

### ミニアプリ内の短い使い方（貼付用）

```text
【周辺MAP 自動作成】
1. 下のリンクを開く（GitHub Pages）
   https://m19mhrts83-cyber.github.io/project-GE/shuhen-auto.html
2. 物件名・住所を入力 → 実行
3. 出てきた C0（ベージュ色付き下地）をダウンロード
4. 印刷の Access／吹き出しは Canva。C1色味寄せは任意
※ 生成APIが未接続のときは地図プレビューのみ／ローカルサーバが必要
```

---

## 自分用（API付き・推奨）

```bash
# 起動＋ブラウザ（未起動ならサーバも立てる）
cd ~/git-repos && ./scripts/shuhen_auto_open.sh
# キャラメル試走
cd ~/git-repos && ./scripts/shuhen_auto_open.sh --caramel
# → http://127.0.0.1:8770/shuhen-auto.html
```

手動:

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/shuhen_auto_server.py
# → http://127.0.0.1:8770/shuhen-auto.html
```
