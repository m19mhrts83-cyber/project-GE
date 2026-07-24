# Raimo マイミニアプリ：周辺MAP 番号ピン

- **用途**: クリーン表示の番号ピン地図（`shuhen-map`）を Raimo Tools から開き、スクショして C1 に渡す
- **コード正本**: GitHub Pages 上の HTML／JS／CSS（ビルダに Maps を丸ごと貼らない）
- **公開URL（Pages）**: `https://m19mhrts83-cyber.github.io/project-GE/shuhen-map.html`
- **Raimo ミニアプリURL**: https://ma-8cfk63x74bh5.raimo-app.buzz（編集: https://raimo.buzz/miniApp/4155/edit）
- **APIキー**: 公開版は運営負担（入力不要）。制限・移管: `運用手順_周辺MAP_MapsAPIキー_運営移管.md`
- **徒歩動線**: トグルで最寄駅→物件の赤線 1 本（Directions）

関連: `11_Raimoプロンプト_C1下地色味寄せ.md` / `03_使い方_基本と発展.md` / `10_フェーズAtoC_ハイブリッド方針.md`

---

## 方針

| 役割 | 置き場 |
|---|---|
| プログラム（HTML／JS／CSS） | Pages（上記 URL） |
| 入口 | Raimo マイミニアプリ（Tools／AI周辺MAP 近く） |

APIキーは画面で入力（localStorage。管理会社検索と同じキー名可）。

---

## Raimo 登録手順

1. Raimo でマイミニアプリ新規作成  
2. 名称: `周辺MAP_番号ピン`  
3. 公開URL（上記 Pages）を開く／リンクとして配置。短い使い方テキストを添える  
4. Tools 上で Step1・C1 MyPrompt と並べて説明できるようにする  
5. 登録後のミニアプリ URL を本ファイル先頭に追記  

### ミニアプリ内の短い使い方（貼付用）

```text
1. APIキーを入力（Maps JS / Places / Geocoding）
2. Grandoleプリセット → ピンを表示（クリーン表示オン）
3. 範囲を確認 → 下地用は「ピンを隠す」→ マップのみ → スクショ
4. スクショを Gemini に添付し、MyPrompt「周辺MAP_C1_下地色味寄せ」を実行
```

---

## ローカル確認

```bash
cd ~/git-repos && python3 -m http.server 8000
# http://localhost:8000/shuhen-map.html
```

---

## スパイク更新

旧結論（Pages継続・ミニアプリ任意）を、**Pages 正本＋Raimo マイミニアプリ入口**に更新。ビルダ内 Maps 移植は引き続きしない。
