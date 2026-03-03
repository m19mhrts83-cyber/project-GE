# ターミナルが Python 対話モード（>>>）になる問題：原因と対策

---

## 【2026年2月14日】今日の実行結果と解決策まとめ

### 事象

- `bash 送信_G2_260213.sh` や `送信_G2_260213.command` を実行すると、スクリプトが動かず **Python の対話モード（>>>）** に入る
- Cursor のターミナル、Mac のターミナル、.command のダブルクリック、AppleScript 経由のいずれでも同じ

### 試したが効果がなかったもの

| 対策 | 結果 |
|------|------|
| `PYTHONINSPECT=` を付けて実行 | 対話モードのまま |
| `env -i` で環境変数をクリアして実行 | 対話モードのまま |
| AppleScript 経由で実行 | 対話モードのまま |
| Cursor を閉じて Mac ターミナルで実行 | 対話モードのまま |
| `~/.zshrc` 等に `PYTHONINSPECT` の記述 | なし（原因ではなかった） |

### 実施したこと

1. **python -c で exec する方式への変更**  
   `python send_mail.py ...` ではなく、`python -c "exec(compile(...))"` でスクリプトを読み込んで実行する形に変更

2. **venv の再作成**  
   `rm -rf venv && python3 -m venv venv && pip install -r requirements.txt`

### 解決した要因

**venv の再作成** が決定的に効いた。  
`.command` をダブルクリックしたところ、**対話モードにならずに正常に動作**した。

### 推測される原因

古い venv 内の Python が、何らかの理由で対話モード（`-i` 相当）で起動していた可能性が高い。

- venv の `python` がラッパースクリプトで `-i` を付けていた
- venv の設定やキャッシュの不整合
- いずれにせよ、**venv を削除して作り直すことで解消**

### 今後の同様トラブル時の推奨手順

1. **まず venv を再作成**（最も効果が高かった）
2. それでもダメなら python -c 方式を試す
3. 上記で解決しない場合、対策1〜6 を順に確認

---

## 事象の整理（一般論）

- **症状**: `bash script.sh` や `.command` を実行すると、スクリプトが動かず Python の対話モード（`>>>`）になる
- **発生箇所**: Cursor のターミナル、Mac のターミナル、.command のダブルクリックのいずれでも発生
- **確認済み**: `python3 -c "print('hello')"` は正常に動作（プロンプトに戻る）

---

## 原因と対策（確度の高い順）

### 対策1: Cursor / VS Code のターミナルプロファイルを zsh に変更【確度：高】

**原因**: Cursor（VS Code 系）では、ターミナルのデフォルトプロファイルを「Python」にできる。この場合、**開いたターミナルが最初から Python REPL** になっており、`bash` と打ってもシェルではなく Python が動いている。

**対策**:
1. Cursor で **⌘ + Shift + P**（コマンドパレット）を開く
2. **「Terminal: Select Default Profile」** を実行
3. **「zsh」** または **「bash」** を選択（**「Python」は選ばない**）
4. 既存のターミナルを閉じ、**新しいターミナル**を開く
5. プロンプトが `$` や `%` になっていることを確認してからスクリプトを実行

**ワークスペース設定**（`settings.json` や `.code-workspace`）で次を指定する方法もある:

```json
"terminal.integrated.defaultProfile.osx": "zsh",
"python.terminal.activateEnvironment": false
```

---

### 対策2: 環境変数 PYTHONINSPECT の確認と削除【確度：高】

**原因**: Python 公式ドキュメントによると、`PYTHONINSPECT` が**空でない文字列**だと、`python -i` と同等になり対話モードになる。**`0` も有効**（「0」は非空のため）。

**対策**:
1. 次のファイルに `PYTHONINSPECT` の記述がないか確認する:
   - `~/.zshrc`
   - `~/.bash_profile`
   - `~/.bashrc`
   - `~/.profile`
2. `export PYTHONINSPECT=1` や `PYTHONINSPECT=0` などがあれば**削除またはコメントアウト**
3. ターミナルを開き直してから再度実行

**確認コマンド**:
```bash
grep -r PYTHONINSPECT ~/.zshrc ~/.bash_profile ~/.bashrc ~/.profile 2>/dev/null
```

---

### 対策3: Mac のターミナルで「シェル」が Python になっていないか確認【確度：中】

**原因**: Mac のターミナル設定で、「Shells open with」が「Command」で、そのコマンドが `python` などになっていると、ターミナル起動時に Python が開く。

**対策**:
1. **ターミナル** → **設定**（環境設定）→ **一般**
2. 「Shells open with」で **「デフォルトのログインシェル」** を選択
3. または「Command」の場合は `/bin/zsh` または `/bin/bash` を指定

**デフォルトシェルの確認・変更**:
```bash
# 現在のデフォルトシェルを確認
echo $SHELL

# zsh に変更する場合
chsh -s /bin/zsh
```

---

### 対策4: .command ファイルの「このアプリケーションで開く」を確認【確度：中】

**原因**: `.command` の関連付けが Python や Python Launcher になっていると、ダブルクリックで Python が起動し、中身がシェルスクリプトのため対話モードになる。

**対策**:
1. `送信_G2_260213.command` を右クリック → **情報を見る**
2. 「このアプリケーションで開く」で **「ターミナル」** を選択
3. 「すべてを変更」をクリックして、他の `.command` にも適用

---

### 対策5: Conda / pyenv などの Python 環境の初期化スクリプト【確度：中】

**原因**: Conda や pyenv の初期化ブロックが `.zshrc` などにあり、ターミナル起動時に Python 環境が有効化される。その過程で `PYTHONINSPECT` が設定される場合がある。

**対策**:
1. `~/.zshrc` 内の `conda initialize` や `pyenv init` のブロックを確認
2. 必要に応じて、該当ブロック内やその前後で `unset PYTHONINSPECT` を追加
3. または、スクリプト実行時のみ `PYTHONINSPECT=` を付けて実行（例: `PYTHONINSPECT= bash script.sh`）

---

### 対策6: 実行方法を変える（Cursor を経由しない）【確度：高・回避策】

**原因**: Cursor のターミナルや環境が、何らかの理由で Python 対話モードを引き起こしている。

**対策**:
- **AppleScript で実行**: `送信_G2_260213.scpt` をダブルクリック → スクリプトエディタが開く → ▶ 実行 → Mac のターミナルが開いてスクリプトが実行される
- **Cursor を終了**してから、Mac のターミナル（Spotlight で「ターミナル」検索）を開き、`bash 送信_G2_260213.sh` を実行

---

### 対策7: venv の再作成【確度：高・2026/2/14 に効果あり】

**原因**: 古い venv 内の Python が、何らかの理由で対話モード（`-i` 相当）で起動している可能性がある。

**対策**（mail_automation ディレクトリで実行）:
```bash
cd "/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/mail_automation"
rm -rf venv
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

※ `credentials.json` と `token.pickle` は venv 外にあるため削除されない。Gmail 認証の再設定は不要。

---

### 対策8: python -c で exec する方式に変更【確度：中・回避策】

**原因**: `python script.py` のようにスクリプトファイルを引数で渡すと、何らかの理由で対話モードになる場合がある。一方、`python -c "..."` でコードを直接渡すと、ファイルパスを渡さないため対話モードにならない可能性がある。

**対策**:
- `送信_G2_260213.sh` と `送信_G2_260213.command` を、`python send_mail.py ...` ではなく `python -c "exec(...)"` 方式に変更済み
- スクリプトの内容を `compile` + `exec` で読み込んで実行するため、Python にファイルパスを渡さない
- この方式で `>>>` が出なくなるか、まず試す

---

## 推奨する実施順序

**2026/2/14 の経験に基づく優先順位:**

1. **対策7**: venv の再作成（今回これで解決した）
2. **対策8**: python -c 方式での実行（既に変更済み。venv 再作成と併用）
3. **対策1**: Cursor のターミナルプロファイルを zsh に変更
4. **対策2**: `PYTHONINSPECT` をシェル設定から削除
5. **対策3**: Mac のターミナル設定でデフォルトシェルを確認
6. **対策6**: AppleScript または Cursor を閉じた状態で Mac のターミナルから実行（回避策）

---

## 参考：Python 公式ドキュメントより

- **`-i`**: スクリプト実行後にインタラクティブモードに入る
- **`PYTHONINSPECT`**: 空でない文字列に設定されていると、`-i` と同等の挙動になる（`0` も有効）

---

## 本ドキュメントの更新履歴

- **2026年2月14日**: 初版作成（ウェブリサーチと事象を基に）
- **2026年2月14日**: venv 再作成で解決した実行結果を追記。対策7を「venv の再作成」に更新し、推奨順序を変更

---

## 補足：同日に発生した別問題（メールアドレスが1件も見つからない）

対話モード解決後、送信時に「メールアドレスが1件も見つかりませんでした」というエラーが発生。  
**原因**: Excel の G2 シートで、スクリプトが「個別メール」列（ほぼ空）を選んでいた。実際のメールアドレスは「mail」列にあった。  
**対策**: 送信スクリプトに `--email-column mail` を追加。
