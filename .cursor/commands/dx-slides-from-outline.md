# DX互助会スライド（表 → NotebookLM で図 → HTML 公開）

## 方針（2026）

- **イラスト・スライドビジュアルは NotebookLM**（**Nano Banana / Nano Banana Pro** 等が使える出力）を主軸にする。
- **Cursor** は **`slides_outline.md`（表）** と **HTML/CSS・画像の組み込み・GitHub push** を担当する。
- 手描き **SVG 量産や cute-illustration のみでの HTML 再現**はフォールバック（出来栄え優先なら NB 側）。

## パス（project-GE / `docs/`）

| 役割 | 例 |
|------|-----|
| 表（正本） | `docs/_drafts/slides_outline_<トピック>.md` |
| NotebookLM に載せるソース | 上記＋補助 MD＋（任意）旧スライド PDF |
| NB 由来の画像 | `docs/assets/<デッキID>/sN.png`（`slide_id` と対応） |
| レイアウト CSS | `docs/css/slides-cute.css` |
| 公開 HTML | `docs/<タイトル>_cute.html` 等 |
| 一覧 | `docs/2kai.html` |

## NotebookLM での手順（要旨）

1. ノートブックに `slides_outline.md` 等をアップロード。
2. **Studio** でスライド／ビジュアル付き出力を作成（**Nano Banana Pro やスタイルプリセットが選べれば指定**）。
3. 各スライド画像を **`s1.png` …** として保存（ダウンロード or 高解像度キャプチャ）。

## Cursor での手順（要旨）

1. `@docs/_drafts/slides_outline_....md` とテンプレ HTML（例: `Obsidian紹介_DX互助会向け_cute.html`）、`@docs/css/slides-cute.css` を添付。
2. 「`assets/<デッキ>/sN.png` を `<img>` で参照。本文は HTML テキスト。`section.slide` 構造を維持。」
3. `git add docs/` → `commit` → `push`（[docs/README.md](docs/README.md)）。

## スタイル指示を NB に渡すとき

- `cute-illustration` コマンドの**要約を 1 ソースとして貼り付け**ると、「ゆるい・水彩・白背景」などのトーンをチャット／生成に寄せやすい（**HTML 用の唯一の正本ではない**）。

## 注意

- 既存 HTML を上書きせず、新規 `_cute.html` や別名で併存してよい。
- NotebookLM の機能名はアップデートで変わるため、不明時は Google の NotebookLM ヘルプで「スライド」「画像」「Nano Banana」を確認する。
