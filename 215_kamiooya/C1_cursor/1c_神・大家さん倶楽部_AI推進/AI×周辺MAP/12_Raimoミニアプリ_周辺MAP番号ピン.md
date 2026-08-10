# Raimo マイミニアプリ：周辺MAP 番号ピン

- **用途**: クリーン表示の番号ピン地図（`shuhen-map`＝Step2）を Raimo Tools から開き、スクショして Step3（旧C1）に渡す
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
4. Tools 上で Step1.1〜1.2・Step3（旧C1）MyPrompt と並べて説明できるようにする  
5. 登録後のミニアプリ URL を本ファイル先頭に追記  

### ミニアプリ内の短い使い方（貼付用）

```text
1. できれば Pages 直開き（地図が出ないときの正）: https://m19mhrts83-cyber.github.io/project-GE/shuhen-map.html
2. Step1.2 の ## E（**コードブロック1つ**）を「一括貼付」へ貼る →「ピンを表示」（手分け不要）
3. 地名が見えない → クリーン表示オフ → 表示を更新
4. 下地用は「ピンを隠す」→ マップのみ → スクショ
5. 仕上げ本線は Canva（Step3画像は任意）
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
