# スパイク: Raimo マイミニアプリ × 周辺MAP番号ピン

- **目的**: Tools から地図アプリを開き、スクショ→C1 につなぐ
- **2026-07-24 結論**: **Pages がコード正本**。Raimo マイミニアプリは **入口（URLを開く）**
- **公開URL**: https://m19mhrts83-cyber.github.io/project-GE/shuhen-map.html
- **Raimo ミニアプリURL**: https://ma-8cfk63x74bh5.raimo-app.buzz（編集 https://raimo.buzz/miniApp/4155/edit）→ 手順 `12`

| 項目 | 結果 |
|---|---|
| Pages 公開 | OK（`shuhen-map.html` を Pages ワークフローに含めた） |
| ビルダ内 Maps 丸ごと移植 | しない（制限・キーで不安定） |
| ミニアプリ入口 | OK（Pages へのリンク＋使い方テキスト。公開範囲は自分のみ） |
| MyPrompt C1 | OK https://raimo.buzz/prompt/474296 |

ローカル: `cd ~/git-repos && python3 -m http.server 8000` → http://localhost:8000/shuhen-map.html
