# 周辺MAP仕上げ：元アプリ寄せ（手打ちマイマップ廃止）

- **確定日**: 2026-07-23（改訂: 同日夜）
- **7/29必須**: 番号ピン骨格 → Canva／NB 装飾（旧手打ち Phase A は廃止）
- **利用者**: 自分＋Jarvis（メンバーがアプリ操作する前提にしない）
- **本命の箱**: **賃貸管理会社検索アプリ（project-GE）と同じ型**で番号ピン
- **第2候補**: Raimo Bizミニアプリ（Maps スパイク後。必須ではない）

公開（管理会社検索）: https://m19mhrts83-cyber.github.io/project-GE/  
周辺MAP用ページ（ローカル／Pages）: `shuhen-map.html`（APIキーは管理会社検索と共有・localStorage）  
同一プロジェクト `serch-property-management-co` のキーで使う API: **Maps JavaScript / Places / Geocoding / Maps Static**  
下地PNGの一括取得: `scripts/jarvis_shuhen_static_clean.py`（Static）または `jarvis_shuhen_capture_clean.py`（ブラウザ）

比較: Cursor Canvas `map-raimo-hybrid-vs-miniapp`

---

## 役割分担

| 層 | 担当 |
|---|---|
| 店リスト・吹き出し文言・プロンプト | Raimo MyPrompt（既存 473911 等）＋ `06` |
| 場所の正しさ・番号ピン骨格 | **project-GE 系 `shuhen-map.html`** |
| Access・縁吹き出し・アイコン | Canva／NotebookLM（ピンを動かさない） |

---

## 廃止したもの

- Google マイマップに店を1件ずつ打つ手作業（旧 Phase A）

代替: 物件住所＋店名リストをアプリに渡す → Geocode／Find Place → **P0〜P8 番号ピン**

---

## 実行手順（本命）

1. `~/git-repos` で `python3 -m http.server 8000`
2. http://localhost:8000/shuhen-map.html を開く
3. APIキー入力（管理会社検索と同じキーで可）
4. 「Grandoleプリセット」→「ピンを表示」（既定で**クリーン表示**＝丁目・店名・道名オフ）
5. 東西（志賀本通／尼ケ坂）が離れているか確認し、**ビュー範囲を確定**
6. 「ピンを隠す」→「表示を更新」→「マップのみ表示」→ スクショ（または Jarvis 一括）  
   - ピンなし: `試走出力/基準_下地_Grandole_クリーン.png`  
   - ピン付き: `試走出力/基準_骨格図_Grandole_クリーン.png`  
   - Jarvis: `scripts/jarvis_shuhen_capture_clean.py` ／ Static: `jarvis_shuhen_static_clean.py`
7. **Phase C（書き出し直後）**: ピンなし下地をベージュ／イラスト寄りへ（詳細は `10c`）  
   - C0: `jarvis_shuhen_recompose_decor.py`（即時）  
   - C1: Gemini／ChatGPT でさらに寄せる（任意・両方試可）→ 再合成  
8. Canva で Access・タイトル・吹き出し清書（**ピンは動かさない**）

チェックリスト: `試走出力/PhaseA_チェックリスト_Grandole.md`

---

## 地図を見本寄りにする（工程の切り分け）

```text
アプリ（クリーン＋範囲）→ ピンなし下地 → C0/C1 色味 → ピン再合成 → Canva
```

| 層 | 手段 | アプリ内？ |
|---|---|---|
| 地理・文字量 | Styled Map（クリーン表示） | ○ |
| 範囲確定 | ズーム／マップのみ／スクショ | ○ |
| ベージュ・イラスト風下地 | Phase C（`10c`）。Maps API では不可 | **書き出し後** |
| Access・吹き出し | Canva（縁スロット） | × |

全文プロンプトで地図を描き直すのは非推奨（道路が崩れやすい）。AI を `shuhen-map` に埋め込まない。

---

## Phase B / C（位置づけ）

| 旧名 | いま |
|---|---|
| Phase B Jarvis新規 | **本命は `shuhen-map.html` 拡張**（別途 Jarvis 新規は不要） |
| Phase C 色味 | `10c`：C0（PIL）→ C1（Gemini／ChatGPT）→ ピン再合成 |
| Raimo ミニアプリ | Pages 正本への入口（登録済）。ビルダ内 Maps 移植はしない |

仕様詳細: `10b_PhaseB_Jarvis下地ツール仕様.md`

---

## Plus AI による「地図上への自動配置」（2026-07-27 検証）

周辺MAPチラシで「クリーン地図を下地に、吹き出し・Access を AI が置き、PPT で直す」を Plus AI（Slides）で試した。

| 結果 | 内容 |
|---|---|
| **判定** | **不採用（要件未達）** |
| できたこと | 編集可能なテキスト箱スライドの生成（説明資料向き） |
| できなかったこと | 実地図を下地として残したまま、ピン近傍へ吹き出しをネイティブ配置 |
| 本線への影響 | **なし。仕上げは Canva Path A のまま** |

証拠・詳細: Drive `200_NoteBookLM/99_PlusAI検証_20260727/07_周辺MAP_地図下地AI配置PoC/00_検証結果.md`  
要約: `docs/N1_NotebookLM/検証_周辺MAP_地図下地AI配置.md`

PPT で誤字を直したい場合の保険は、地図背面＋テキスト箱の手置き（同 PoC の Track C）。ピン位置合わせの手間は Canva と同種。

---

## 関連

- 配置: `09_プロット基準図_Grandole.md`
- NB装飾: `07_仕上げ_NotebookLM試走手順.md`
- Canva磨き: `08_Canva磨きチェックリスト.md`
- Canva本線手順: `15_Canva手順_印刷用仕上げ_PathA.md`
- 元アプリ: `~/git-repos/{index.html,app.js}` / 作業コピー `google_map_reserch/real-estate-search/`
