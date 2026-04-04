# DX互助会 cute スライド（表正本 → HTML）

## いつ使うか

- 勉強会スライドを **まず `slides_outline.md`（表）で固めてから**、`docs/css/slides-cute.css` ＋ `section.slide` の HTML に落とすとき。
- ビジュアルは **cute-illustration**（`/git-repos/cute-illustration` コマンドの要約をプロンプトに含める）。

## 正本と参照パス（git-repos / project-GE）

| 役割 | 例 |
|------|-----|
| 表（正本） | `docs/_drafts/slides_outline_<トピック>.md` |
| 共通 CSS | `docs/css/slides-cute.css` |
| イラスト | `docs/assets/<デッキID>/sN.svg` または `.png` |
| 出力 HTML | `docs/<タイトル>_cute.html` |
| 一覧へのリンク | `docs/2kai.html` または `docs/index.html` |

## エージェントへの依頼例

1. `@docs/_drafts/slides_outline_....md` と `@docs/Obsidian紹介_DX互助会向け_cute.html`（テンプレ）を添付。
2. 「表の各行を `<section class="slide" id="sN">` に対応させ、`slide-split` / `slide-full` / `slide-top-illust` を使い分け。`図案` がある行は `assets/.../sN.svg` を参照。」
3. 新規デッキなら `@.cursor/commands/cute-illustration` のスタイル要約を貼る。

## 公開

- [docs/README.md](docs/README.md) の手順: `git add docs/` → `commit` → `push`。GitHub Pages が数分で更新。

## 注意

- **既存の `_cute.html` でない**通常版 HTML を上書きしない（別ファイル `_cute.html` で併存する）。
