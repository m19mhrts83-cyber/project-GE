# 215 リポジトリ運用メモ：ローカル本番・GitHub へバックアップ

## 運用の前提：ファイルは OneDrive、Git はローカルで

- **ファイルの追加・編集（「215」の管理）**  
  → **OneDrive の「215_神・大家さん倶楽部」** で行う。ここが**元の置き場所**です。
- **Git 管理（コミット・履歴・push）**  
  → OneDrive 上の `.git` は壊れており Git が使えないため、**OneDrive の内容をローカル `~/git-repos/215_kamiooya` に反映したうえで、そこで commit → push** する運用にします。

つまり「ファイルは OneDrive で管理し、Git で履歴を残すときだけローカルに同期してから commit/push する」形です。

---

## フォルダの役割

| 場所 | 役割 |
|------|------|
| **OneDrive「215_神・大家さん倶楽部」** | ファイルの追加・編集・日々の管理（ここが元）。Git はここでは動かない。 |
| **ローカル `~/git-repos/215_kamiooya`** | OneDrive の内容を同期したうえで、ここで commit ・ push する。履歴は GitHub に残る。 |

---

## リモート（GitHub）

- **登録済み:** `https://github.com/m19mhrts83-cyber/project-GE`（空のリポジトリを活用）
- **確認:** `git remote -v`

### 初回 push がブロックされた理由

GitHub の **Push Protection** により、過去のコミットに含まれる次のような秘密が検知され、push が拒否されました。

- `C1_cursor/1b_Cursorマニュアル/token.json.expired` … Google OAuth トークン・Client ID/Secret
- `C1_cursor/Gmail_MCP_エラー解消手順.md` … 手順書内の OAuth Client ID

→ **秘密を含まない「クリーンな履歴」だけを GitHub に送る**必要があります。

---

## クリーンな履歴で project-GE に push する手順（手元のターミナルで実行）

次の手順を **ターミナルで** 実行してください（Cursor からだと `git add` がタイムアウトすることがあります）。

1. **ルートに .gitignore を置く（秘密・手順書を push 対象から外す）**
   ```bash
   cd ~/git-repos/215_kamiooya
   cp C1_cursor/.gitignore_for_push_example .gitignore
   ```

2. **秘密を含まない新規履歴用のブランチを作成**
   ```bash
   git checkout --orphan clean-main
   git reset
   git add .
   git commit -m "Initial commit: 215 本番 (secrets excluded)"
   ```

3. **main を clean-main で置き換えて push**
   ```bash
   git branch -D main
   git branch -m main
   git push -u origin main --force
   ```

4. **今後**
   - 編集・コミットはこのローカルで行い、`git push` で project-GE に送る。
   - 秘密が含まれるファイルは .gitignore に入っているので、誤って push されません。
   - **旧履歴（秘密含む）** はローカルの `main-backup-with-secrets` ブランチに残してあります。必要なら参照用にのみ使い、push しないでください。

---

## エラー: 「100 MB 超」「Large files detected」で push が拒否された場合

### どういう意味か

- **コミット** = Git が「この時点のファイル一式」として記録した**ひとまとまり**（スナップショット）。
- **直近のコミット** = いまの main で、いちばん新しいそのスナップショット（さっき「Initial commit」で作ったもの）。
- そのスナップショットの中に、**大きいフォルダ `.venv`（112MB）が入っている**ので、GitHub が「100MB 超はダメ」と拒否している。
- **「.venv だけ外す」** = その**同じスナップショットを書き換えて**、「.venv は含めない版」にすること。  
  → 中身を変えた「新しい直近コミット」ができるので、その状態で再度 push する。

**やることの流れ（3つだけ）：**

1. Git に「.venv はもうこのコミットの対象にしない」と伝える（`git rm -r --cached ...`）。  
   ※ パソコン上のフォルダは消さないので、.venv はそのまま使える。
2. その変更を「直近のコミットに上書きする」（`git commit --amend`）。  
   → 「.venv を除いたスナップショット」が直近コミットになる。
3. その直近コミットを GitHub に送り直す（`git push --force`）。

---

### ターミナルで実行するコマンド（順番に）

```bash
cd ~/git-repos/215_kamiooya
```

```bash
git rm -r --cached C1_cursor/browser_automation/.venv
```
→ 「このリポジトリの記録から .venv を外す」だけ。フォルダ自体は消えません。

```bash
git add .gitignore
```
→ **ここでは `git add .gitignore` だけにする。** `git add -A` は使わない（未追跡になった .venv が .gitignore の効き方で再追加され、amend しても 100MB エラーが残ることがあるため）。

```bash
git commit --amend --no-edit
```
→ 直近のコミットを「.venv を除いた内容」に書き換えます。メッセージはそのまま「Initial commit...」です。

```bash
git push -u origin main --force
```
→ 書き換えた直近コミットを GitHub に送り直します。

- 上記の前に、ルートに `.gitignore` があると安心です（`cp C1_cursor/.gitignore_for_push_example .gitignore` でコピー済みならそのままで OK）。`.gitignore` に `**/.venv/` や `C1_cursor/browser_automation/.venv/` を入れておく。
- 今後は `.venv` はコミットしないので、clone した人は各自 `python -m venv .venv` と `pip install -r requirements.txt` で再作成してください。

**なぜ 100MB エラーが再発するか:** 同期に rsync を使うとき、`.gitignore` を除外していないと、OneDrive 側の .gitignore が 215_kamiooya を上書きします。すると `.venv` が無視されず、次に `git add -A` したときに再び取り込まれ、push で同じエラーになります。**同期コマンドには必ず `--exclude='.gitignore'` と `--exclude='.venv'` / `--exclude='**/.venv'` を含める**（本文「運用サイクル」参照）。

---

## エラー: 「Push Protection」「secrets」「cannot contain secrets」で拒否された場合

GitHub がコミット内の **秘密（OAuth トークン・Client ID 等）** を検知して push をブロックしている場合の対処です。

### 除外するファイルの例

- `C1_cursor/1b_Cursorマニュアル/token.json.expired`
- `C1_cursor/1b_Cursorマニュアル/Gmail_MCP_エラー解消手順.md`（手順書内に OAuth Client ID 等が含まれる場合）

### ターミナルで実行するコマンド（順番に）

```bash
cd ~/git-repos/215_kamiooya
```

```bash
git rm --cached "C1_cursor/1b_Cursorマニュアル/token.json.expired" "C1_cursor/1b_Cursorマニュアル/Gmail_MCP_エラー解消手順.md"
```
→ 記録からだけ外す。ローカルのファイルは消えません。

```bash
git add .gitignore
git commit --amend --no-edit
```

```bash
git push -u origin main --force
```

- ルートの `.gitignore` に `token*.json`、`*.expired`、`C1_cursor/Gmail_MCP_エラー解消手順.md` 等を入れておくと、今後は誤ってコミットされません（`.gitignore_for_push_example` 参照）。

---

## リモートの確認が必要だった理由（参考）

- 以前はリモート未設定で、**履歴はローカルだけ**でした。
- そのため **ローカルがクラッシュすると履歴を復元できない**可能性があり、リモートを設定して push することで「GitHub に履歴を残す」＝クラッシュ時に復元できるようにする必要がありました。
- いまは **project-GE をリモートに登録済み**。上記のクリーン push が完了すれば、履歴（秘密除く）は GitHub に残り、クラッシュ時も `git clone https://github.com/m19mhrts83-cyber/project-GE.git` で復元できます。

---

## 理解の確認：Git 管理と「ローカルが重くならない」について

### いまの環境

- **Git 管理を行い、コミットで履歴を残せる環境になっている**という理解で問題ありません。
- 編集はローカル `~/git-repos/215_kamiooya` で行い、`git commit` → `git push` で GitHub（project-GE）に履歴が残ります。

### 「GitHub で管理していればローカルは重くならない」の意味

- ここで言っていたのは、**「リポジトリを OneDrive とローカルの両方に置いて二重に持たない」**という意味です。
- OneDrive に置くと同期で壊れたり、同じ中身が複数場所にあったりするので、**作業用はローカル 1 か所だけ**にし、**履歴のバックアップは GitHub に push する**形にした、という話です。
- なので「ローカルに大きなフォルダを**もう一セット**増やさない」という意味であり、**「ローカルの .git や作業ツリーのサイズが増えない」**という保証ではありません。

### ローカルのサイズが気になる場合

- **作業ツリー**（普段触っているファイル）のサイズは、コミットするファイルが増えればその分だけ増えます。.gitignore で .venv や大きなファイルを除外しているので、急に巨大にはなりにくいです。
- **.git（履歴）** は、コミットを重ねるほど増えていきます。ただし Git は中身を圧縮して持つので、大容量のバイナリをコミットしなければ、そこまで急激には膨らみません。
- **定期的にやっておくとよいこと：**
  1. **大きなファイルはコミットしない**  
     .venv、PDF・画像の大量追加などは .gitignore で除外する（すでに .venv 等は設定済み）。
  2. **たまにリポジトリを圧縮する**  
     `git gc`（必要なら `git gc --aggressive`）で、.git 内の古いオブジェクトを整理・圧縮できます。数ヶ月に一度程度で十分です。
     ```bash
     cd ~/git-repos/215_kamiooya
     git gc --aggressive
     ```
  3. **「履歴は GitHub に任せて、ローカルは軽く」したい場合**  
     その PC では「最新だけあればよい」という運用なら、いったん別フォルダに `git clone --depth 1 https://github.com/m19mhrts83-cyber/project-GE.git` で浅いクローンを作り、そこで作業する方法もあります。履歴は GitHub にだけあり、ローカルの .git は軽くなります（本番用の 1 台は通常の clone のままにして、履歴を残し続ける運用がおすすめです）。

---

## 運用サイクル：OneDrive で編集 → 同期 → コミット → push

**前提:** ファイルの追加・編集は OneDrive「215_神・大家さん倶楽部」で行い、Git で履歴を残すときだけローカル 215_kamiooya に同期してから commit ・ push します。

### 1. コミット・push するときの流れ

0. **OneDrive の内容を 215_kamiooya に同期する**  
   OneDrive で編集した内容を、ローカル `~/git-repos/215_kamiooya` に反映します。
   - **上書きしないもの:** `.git`（Git の履歴）、`.gitignore`（.venv 等の除外設定を守るため）、`.venv`（100MB 超で GitHub 拒否になるため）。**`.cursor`、`.obsidian`、`.vscode` も除外**（OneDrive 上でこれらのフォルダにアクセスすると `mmap: Operation timed out` が出て rsync が止まることがあるため）。
   ```bash
   rsync -av --timeout=120 --ignore-errors \
     --exclude='.git' --exclude='.gitignore' --exclude='.venv' --exclude='**/.venv' \
     --exclude='.cursor' --exclude='.obsidian' --exclude='.vscode' \
     "/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/" \
     ~/git-repos/215_kamiooya/
   ```
   **重要:** `.gitignore` を除外しないと、OneDrive 側の .gitignore で 215_kamiooya の設定が上書きされ、`.venv` が再び add されて push エラーになります。
   **rsync で `mmap: Operation timed out` が出る場合:**  
   - `.cursor`、`.obsidian`、`.vscode` を除外（上記のとおり）。  
   - それでも通常ファイルでエラーが出ることがあります。そのときは **`--timeout=120` と `--ignore-errors`** でエラーが出ても**完了まで待つ**。失敗した 1 ファイル以外はすべて同期されているので、**そのままコミット・push に進んでよい**。  
   - **同じファイルが毎回だけ失敗する場合**（例: `00_活動報告・成果報告・全般/231225_契約時の連絡_LINE 関連.md`）は、そのファイルを rsync の除外に追加すると、次回からエラーが出ずに終わります。下記「特定ファイルを除外する場合」のコマンドを参照。
   **特定ファイルを除外する場合**（毎回同じファイルでエラーになるとき）:
   ```bash
   rsync -av --timeout=120 --ignore-errors \
     --exclude='.git' --exclude='.gitignore' --exclude='.venv' --exclude='**/.venv' \
     --exclude='.cursor' --exclude='.obsidian' --exclude='.vscode' \
     --exclude='00_活動報告・成果報告・全般/231225_契約時の連絡_LINE 関連.md' \
     "/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/" \
     ~/git-repos/215_kamiooya/
   ```
   （手動でコピーする場合は、215_kamiooya の `.git` と `.gitignore` を消さず、`.venv` はコピーしない。）

1. **コミット**（メッセージ例に沿って自分でコミット）
2. **push**  
   ```bash
   cd ~/git-repos/215_kamiooya
   git add -A
   git commit -m "ここにメッセージ例を入れる"
   git push
   ```
3. **（任意）ローカルを軽くする**  
   - **A. 圧縮だけする**（数ヶ月に 1 回程度でよい）  
     ```bash
     cd ~/git-repos/215_kamiooya
     git gc --aggressive
     ```
   - **B. 「最新だけ」の浅いクローンに差し替える**（ローカルをなるべく軽くしたいとき）  
     1. 別フォルダに浅いクローンを作る：  
        `git clone --depth 1 https://github.com/m19mhrts83-cyber/project-GE.git 215_kamiooya_new`  
     2. 未コミットの変更があれば 215_kamiooya で commit するか退避してから、  
        作業用フォルダを 215_kamiooya_new に切り替える（旧 215_kamiooya は削除してよい）。  
     3. 今後は 215_kamiooya_new で編集 → commit → push を繰り返す。

### 2. GitHub から復元したいとき（何かあった場合）

- 最新だけ取り直す：  
  `git clone https://github.com/m19mhrts83-cyber/project-GE.git`  
- 過去の状態に戻す必要があるときは、その時点で「立ち戻り方」を聞きながら対応する想定（運用メモに詳細は別途追記可）。
