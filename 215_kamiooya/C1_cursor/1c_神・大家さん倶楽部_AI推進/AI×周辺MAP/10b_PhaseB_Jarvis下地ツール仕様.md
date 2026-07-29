# Phase B 仕様 — 番号ピン付き下地（元アプリ寄せ）

- **本命**: project-GE 系の **`shuhen-map.html` / `shuhen-map.js`**（管理会社検索を壊さない別ページ）
- **第2候補**: Raimo Bizミニアプリへ同ロジック移植（Mapsスパイク OK 時のみ）
- **廃止**: Jarvis でゼロから地図を新規実装する案（元アプリが既に Maps＋Places 済みのため）

関連: `10_フェーズAtoC_ハイブリッド方針.md`

---

## 目的

入力した店名リストから、地図上に **番号ピン P0〜P8** を出し、骨格スクショ用にする。

---

## 実装場所

| ファイル | 役割 |
|---|---|
| `~/git-repos/shuhen-map.html` | UI |
| `~/git-repos/shuhen-map.js` | Geocode／Find Place／番号マーカー |
| `~/git-repos/style.css` | 共有スタイル＋周辺MAP用追記 |
| 作業コピー | `215_kamiooya/.../google_map_reserch/real-estate-search/` へ同期 |

管理会社検索（`index.html` / `app.js`）は **変更最小**（ヘッダーに周辺MAPへのリンクのみ）。

---

## 入力

| 項目 | 例 |
|---|---|
| 物件住所 | 愛知県名古屋市北区長田町4丁目69番地5 |
| 店リスト | `06` の施設（プリセット内蔵） |
| ズーム | bounds fit（徒歩約10分圏が収まる） |

---

## 処理

1. Geocoding（物件）→ 中心・P0  
2. 各店: Places **findPlaceFromQuery**（locationBias＝物件）  
3. 番号マーカー P0〜P8（別ラベル）  
4. 一覧表＋失敗した店名の明示  
5. 「マップのみ表示」でスクショ用に UI を隠す  

### スタイル方針（下地）

- 意図しない Nearby 連打はしない（指定店のみ）  
- 北区役所・ゲオは載せない（Accessのみ）  

---

## 出力

- ブラウザ地図 → スクショ `試走出力/基準_骨格図_Grandole.png`  
- （任意）画面の JSON コピー → `試走出力/基準_coords_Grandole.json`

---

## 秘密

- APIキーは画面入力＋ localStorage（管理会社検索と同一キー名 `googleMapsApiKey`）  
- リポジトリにキーを埋め込まない  
- GitHub Pages 利用時は HTTPリファラ制限  

---

## Raimo ミニアプリ版（条件付き）

スパイク OK なら `shuhen-map.js` 相当を移植。不可なら **Pages／ローカル継続**。

---

## 非目標

- 管理会社検索（Nearby `不動産 賃貸 管理`）の挙動変更  
- 縁吹き出しの自動美装（Canva/NB）  
- Gemini 色味（→ `10c`）  
