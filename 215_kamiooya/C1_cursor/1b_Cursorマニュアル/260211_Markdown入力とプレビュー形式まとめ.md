# Markdown（.md）の入力形式とプレビュー形式まとめ

拡張機能を入れたときに .md の見た目や編集しやすさが変わりやすいため、**入力（編集）の形式**と**プレビューの形式**を網羅的に整理したメモ。運用で「やりやすい組み合わせ」を選ぶときの参照用。

---

## 1. 入力（編集）の形式

.md を「どのエディタで開くか」で、入力の仕方が変わる。

| 形式 | 説明 | 編集のしやすさ | トグル（折りたたみ） | 備考 |
|------|------|----------------|----------------------|------|
| **default（標準テキストエディタ）** | ソース（記号やタグ）をそのまま編集。Cursor/VS Code の通常のエディタ。 | ◎ いつも通り編集できる | ◎ `<details>` / `<summary>` がそのまま書ける。プレビューで開閉可能 | **推奨**。拡張の影響を受けにくい |
| **Office Viewer の Markdown ビューア**（cweijan.markdownViewer） | WYSIWYG 風。見た目に近い形で編集。 | △ 記法に不慣れだと書きづらい場合あり | × HTML の `<details>` は効かない | Office Viewer 導入で .md がこれで開くことがある |
| **その他 WYSIWYG 系**（vditor 等） | リッチテキストに近い編集。 | △ ソースを触りたいときは向かない | 拡張による | 用途が「文書中心」ならあり |

### 設定でどう開くか決める

- **Workbench: Editor Associations**（`workbench.editorAssociations`）で、`*.md` をどのエディタで開くか指定する。
- **`"*.md": "default"`** にしておくと、.md は常に標準テキストエディタで開き、**編集・トグル・プレビュー**のどれも従来どおり使える。
- ここを指定しないと、Office Viewer などが .md を「自分のビューア」で開いてしまい、表示や編集の仕方が変わる。

---

## 2. プレビューの形式

「編集はソースのまま」で、**見た目を確認する**ためのプレビューには次のような種類がある。

| 形式 | 出し方（目安） | 特徴 | トグル | 図・数式など |
|------|----------------|------|--------|--------------|
| **ビルトイン Markdown プレビュー** | `Cmd + Shift + V` | シンプル。標準機能。 | ○ `<details>` 対応 | 基本的な記法のみ |
| **Markdown All in One のプレビュー** | `Cmd + Shift + V`（拡張が効く） | 目次・テーブル整形・ショートカットなど編集支援が豊富 | ○ `<details>` 対応 | 基本〜表など |
| **Markdown Preview Enhanced のプレビュー** | `Cmd + Shift + V` または 右クリックメニュー | PDF/HTML 出力、mermaid 図、テーマ変更など高機能 | ○ `<details>` 対応 | ◎ mermaid・数式・PDF 出力可 |
| **横並びプレビュー** | `Cmd + K` のあと `V` | 編集とプレビューを左右に並べて表示 | 上記のプレビューと同じ | 上記に準拠 |

※ 実際にどれが使われるかは、入っている拡張と「既定のプレビュー」の優先順による。

### プレビューで効く・効かない記法（目安）

| 記法 | ビルトイン | Markdown All in One | Markdown Preview Enhanced |
|------|------------|---------------------|----------------------------|
| 見出し・リスト・リンク・画像 | ○ | ○ | ○ |
| 表（テーブル） | ○ | ○（整形可） | ○ |
| **HTML `<details>` / `<summary>`（トグル）** | ○ | ○ | ○ |
| mermaid 図 | × | △ 要確認 | ◎ |
| 数式（LaTeX） | △ | △ | ◎ |
| PDF エクスポート | × | × | ◎ |

※ トグルを使う場合は、**編集は「default」のテキストエディタ**にしておくと、ソースもプレビューも扱いやすい。

---

## 3. 拡張機能と .md の関係（影響を受けないようにする）

次のような拡張は「.md を自分で開く」設定を持っていることがある。

| 拡張機能 | .md に対する動き | 推奨設定 |
|----------|------------------|----------|
| **Office Viewer**（cweijan.vscode-office） | .md を WYSIWYG 風ビューア（cweijan.markdownViewer）で開く | `"*.md": "default"` を **明示的に追加** すると、.md は標準エディタのまま |
| **Docx Renderer** | .md には関与しない | 特になし |
| **Markdown All in One** | 編集は「default」のまま。プレビュー・ショートカット・目次などを提供 | そのままでよい |
| **Markdown Preview Enhanced** | 同上。プレビューとエクスポートを強化 | そのままでよい |

**ポイント**  
- .docx 用に Office Viewer を入れた場合でも、**`workbench.editorAssociations` に `"*.md": "default"` を入れておく**と、.md の入力・トグル・プレビューが従来どおりになる。
- 新しい拡張を入れたあとで「.md の表示や編集が変わった」ときは、まずこの設定を確認するとよい。

---

## 4. MD ファイルとして「やりやすい」運用のまとめ

- **入力（編集）**  
  - **.md は「default」（標準テキストエディタ）で開く**ようにする。  
  - 設定：`workbench.editorAssociations` に `"*.md": "default"` を追加（ユーザー設定 or ワークスペースの .vscode/settings.json）。
- **プレビュー**  
  - 編集画面のまま `Cmd + Shift + V` でプレビュー（**Markdown Preview Enhanced** が開くようキーバインドを設定済み）。  
  - 横並びにしたいときは `Cmd + K` → `V`（同上、Enhanced の横並び）。  
  - PDF や mermaid 図・数式も Markdown Preview Enhanced で表示可能。
- **トグル（折りたたみ）**  
  - ソースに `<details>` / `<summary>` を書く。  
  - 編集は default、プレビューは上記のいずれかで表示すれば、トグルはプレビュー側で開閉できる。
- **拡張を入れるとき**  
  - Office Viewer など「.md を別ビューアで開く」拡張を入れたら、**必ず `"*.md": "default"` を確認**しておく。  
  - これで「入力とプレビューの形式」を意図どおりに保ちやすい。

---

## 5. クイック参照

### 今の環境で .md を「元どおり」にする手順

1. **設定を開く**：`Cmd + ,`
2. 検索欄に **「editorAssociations」** と入力
3. **Workbench: Editor Associations** で  
   - `*.docx` → `cweijan.officeViewer`（.docx は Office Viewer のまま）  
   - **`*.md` → `default`**（.md は標準エディタ）
4. **Cursor を再読み込み**：`Cmd + Shift + P` → 「Developer: Reload Window」
5. .md ファイルを開き直す

### プレビュー・横並びのショートカット

| 操作 | キー |
|------|------|
| プレビューを開く | `Cmd + Shift + V` |
| 横並びプレビュー | `Cmd + K` → `V` |

### プレビューコマンドの「効く・効かない」と現在の設定

| コマンド（キーで実行されるもの） | 意図 | 効く条件 |
|----------------------------------|------|----------|
| **Markdown Preview Enhanced: Open Preview**（`Cmd + Shift + V`） | Enhanced のプレビューを開く | 拡張「Markdown Preview Enhanced」が**インストール済み**のとき |
| **Markdown Preview Enhanced: Open Preview to the Side**（`Cmd + K` → `V`） | Enhanced の横並びプレビュー | 同上 |
| ビルトイン「Markdown: Open Preview」 | 標準プレビューを開く | 拡張がなくても常に利用可能 |

- **効かないとき**：`Cmd + Shift + V` を押しても反応しない／別のプレビューが開く  
  → 下記「設定の確認チェックリスト」で原因を切り分ける。
- **現在のキーバインド**：`Cmd + Shift + V` / `Cmd + K` → `V` は **Markdown Preview Enhanced** のコマンドに割り当て済み（`keybindings.json`）。Enhanced が入っていないとそのコマンドは存在せず、キーが効かない。

### 設定の確認チェックリスト（プレビューが出ないとき）

1. **.md を標準エディタで開いているか**  
   - `settings.json` の `workbench.editorAssociations` に **`"*.md": "default"`** があるか確認。  
   - ない、または `*.md` が別のビューア（例: `cweijan.markdownViewer`）になっていると、プレビューが出ない／別タブになることがある。
2. **Markdown Preview Enhanced が入っているか**  
   - 拡張機能パネルで「Markdown Preview Enhanced」（発行元 shd101wyy）を検索。  
   - 未インストールなら「インストール」→ 再読み込み後、`Cmd + Shift + V` を再試行。
3. **コマンドが存在するか**  
   - `Cmd + Shift + P` → 「Markdown Preview Enhanced」と入力。  
   - 「Markdown Preview Enhanced: Open Preview」が出れば拡張は有効。それを実行してプレビューが開くか確認。  
   - 開くならキーバインドだけの問題なので、キーボードショートカット設定で `Cmd + Shift + V` が「markdown-preview-enhanced.openPreview」に割り当たっているか確認。
4. **フォーカスが .md の編集タブにあるか**  
   - プレビューは「**いまアクティブなエディタが Markdown のとき**」だけ効く。  
   - 対象の .md（例: 260228_面談準備_方針と資料.md）のタブをクリックしてから `Cmd + Shift + V` を押す。
5. **ウィンドウの再読み込み**  
   - 設定やキーバインドを変えたあとは `Cmd + Shift + P` → 「Developer: Reload Window」で再読み込みしてから試す。

**現在の設定（確認済み）**  
- `settings.json`: `"*.md": "default"` あり → .md は標準エディタで開く。  
- `keybindings.json`: `Cmd + Shift + V` → `markdown-preview-enhanced.openPreview`（`editorLangId == markdown`）、`Cmd + K` → `V` → `markdown-preview-enhanced.openPreviewToSide`。  
→ 拡張が入っていれば、**260228_面談準備_方針と資料.md** を開いた状態で `Cmd + Shift + V` で Enhanced プレビューが開く想定。

---

*2026/02/11 作成（拡張機能導入時の .md 表示変更をきっかけに整理）*
