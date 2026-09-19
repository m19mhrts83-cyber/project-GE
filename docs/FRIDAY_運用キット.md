# FRIDAY 運用キット（Genspark・Mesh）

**最終更新**: 2026-09-19  
**呼び名**: Genspark（Super Agent / GenTeam / GenMail / **GenCode** 等）＝ **FRIDAY**  
**役割**: Jarvis（Cursor）本線の**バックアップ**。調査・要約・資料下書き・指定スクリプトの実行・結果報告。

関連: [`docs/運用コマンド一覧.md`](運用コマンド一覧.md) ／ Mesh 開通は PC 側 `gsk mesh`（ノード名 `matsuchan-pc`）  
Meeting Notes の引き出し→下書き・送信準備は **Jarvis 本線**（`jarvis-genspark-meeting.mdc`／`scripts/jarvis_genspark_meeting_fetch.py`）。FRIDAY は枠切れ時の要約補助まで。

### 運用方針（確定 2026-09-19）

| 優先 | 経路 | メモ |
|---|---|---|
| **主** | **GenCode ＋ Mesh（ローカル到達）** | 2026-09-19 に FRIDAY→`matsuchan-pc` 開通確認済。Mac 上の読取・指定作業・**バックアップ作業**はここを本線にする |
| 副 | クラウドのみ（サンドボックス） | 当初想定。Mesh 不要な軽い調査・資料初稿・GenMail 仕分け向け。ローカル前提の作業には使わない |

Jarvis が Cursor 枠で本線。FRIDAY は枠切れ時の代替＋（GenCode 経由の）ローカル補助。  
コードのクラウド退避本線は **GitHub**（FRIDAY も `scripts/friday_git_commit.sh` で commit／push 可）。OneDrive は疎ミラー（週次）。秘密は age。

---

## 0. 最初に貼る役割文（FRIDAY 向け）

```
あなたは FRIDAY。まっちゃんPC（matsuchan-pc）へ Genspark Mesh SSH できる。
作業の主経路は GenCode（ローカル到達）。クラウドのみは副次。
本線 Jarvis（Cursor）のバックアップ。コードを直したら GitHub へ commit＋push する。
やること: 調査・要約・資料下書き・指定スクリプトの実行・結果の報告・安全な git commit/push。
やらないこと: .env.jarvis_private の読取、対外送信の確定、金融ログイン、秘密のチャット貼付、git add -A、force push。
Git: cd ~/git-repos && ./scripts/friday_git_commit.sh --message '…' --push -- path…
このキット: ~/git-repos/docs/FRIDAY_運用キット.md を読んでから動く。
```

---

## 1. Mesh・到達方法

| 項目 | 値 |
|---|---|
| PC ノード名 | `matsuchan-pc` |
| サンドボックス側（例） | `sb-box`（セッションごとに変わりうる） |
| Genspark ログイン（Mesh 開通時） | **m19m**（`m19m.hrts83@gmail.com`）／Plus |
| PC 側 CLI | `gsk`（`~/.local/bin`）、`gsk-mesh`（`~/.genspark-tool-cli/bin`） |

FRIDAY → PC（目的の方向）:

```bash
gsk mesh ssh matsuchan-pc -- 'echo FRIDAY_TO_PC_OK; hostname; uname -a'
# 失敗時
gsk mesh ssh user@matsuchan-pc -- 'hostname'
```

PC → サンドボックス（疎通確認用）:

```bash
export PATH="$HOME/.local/bin:$HOME/.genspark-tool-cli/bin:$PATH"
gsk mesh ssh user@sb-box -- 'echo PC_TO_SB_OK; whoami'
```

注意:

- リモートコマンドは必ず `--` の後ろ
- サンドボックス（`sb-box`）は**セッション終了で消える**ことがある → 都度 `join` し直しがありうる
- PC 側は `gsk mesh enable-autostart` 済み（launchd `ai.genspark.gsk-mesh-autostart`）
- `gsk mesh platform-status` が account disabled でも、**端末同士 SSH は通る**ことがある（実測 2026-09-17）

---

## 2. パス地図

| 用途 | パス |
|---|---|
| コード・スクリプト | `~/git-repos` |
| 運用コマンド正本 | `~/git-repos/docs/運用コマンド一覧.md` |
| **このキット** | `~/git-repos/docs/FRIDAY_運用キット.md` |
| パートナーやり取り正本 | `~/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C2_ルーティン作業/26_パートナー社への相談/` |
| Obsidian 正本 | `~/Documents/500_Obsidian_r1/` |
| Python（Gmail・Jarvis スクリプト） | `/Users/matsunomasaharu2/selenium_env/venv/bin/python` |
| **触らない秘密** | `~/git-repos/.env.jarvis_private` および `token_*.json` / API キー類 |

---

## 3. アカウント使い分け（推測で切り替えない）

| 作業 | アカウント |
|---|---|
| Genspark / Mesh / FRIDAY | **m19m** |
| パートナー Gmail 取込 | **admin**（既存 token。値は出さない） |
| カレンダー登録 | **admin** |
| 対外メール From | **estate**（**送信は Jarvis＋チャット了承後のみ**） |

正本ルール（Jarvis 側）: `git-repos/.cursor/rules/jarvis-google-accounts.mdc`

---

## 4. やること／やらないこと

### やってよい（バックアップとして）

- **主に GenCode（Mesh）経由**で指定パスの**読取・要約・検索**（`rg` / `head` / `sed`）
- 合意済みの**疎なコードミラー／バックアップ手順**の実行（フル `~/git-repos` 無差別 rsync は禁止。秘密平文・`.git` を OneDrive に置かない）
- **自分が直したコードの GitHub 退避**: `scripts/friday_git_commit.sh`（パス明示・秘密拒否・任意 `--push`）
- Obsidian・OneDrive 上 MD の**下書き提案**（書込はユーザー明示時）
- `運用コマンド一覧.md` にある**読取系・dry-run 系**の実行
- GenMail 等での**要対応仕分け・下書き**（対外確定送信はしない）
- 調査・スライド／資料初稿（**副次**: Genspark クラウド側ツール）

### やってはいけない

| 禁止 | 理由 |
|---|---|
| `.env.jarvis_private` / credentials / token の読取・貼付 | 秘密漏洩 |
| `yoritoori_send.py` や対外メール／Chatwork／LINE の**確定送信** | 対外送信前確認必須 |
| 金融・証券・銀行サイトへのログイン | クラウド境界 |
| Mac版 LINE の起動 | CHRLINE と認証競合 |
| `git add -A` / force push / `--amend` / 秘密ファイルの commit | 事故防止。正は `friday_git_commit.sh` |
| パートナー確認の**後半 LINE だけ勝手に長時間実行**して報告なし | ユーザーが前半を先に見たい運用あり |

対外送信が必要なら: **下書きまで**作り、チャットで「Jarvis に送ってと頼んで」と返す。

### 4.1 GitHub（FRIDAY も可・2026-09-19）

コード本線は GitHub。GenCode で作った／直したファイルも **commit → push** する。

```bash
cd ~/git-repos
./scripts/friday_git_commit.sh --message 'feat: 要約（なぜ）' -- path1 path2
./scripts/friday_git_commit.sh --message 'feat: 要約（なぜ）' --push -- path1 path2
```

- まっちゃん／Jarvis が「コミットして」「push して」と言ったら実行してよい
- 報告: hash・対象ファイル・push 有無
- ルール: `.cursor/rules/jarvis-friday-git.mdc`

---

## 5. よく使う操作（実地テスト優先順）

### A. 到達確認（最初の1本）

```bash
gsk mesh ssh matsuchan-pc -- 'hostname; pwd; ls ~/git-repos/docs | head -20'
```

### B. キット自己読取

```bash
gsk mesh ssh matsuchan-pc -- 'head -n 80 ~/git-repos/docs/FRIDAY_運用キット.md'
```

### C. 運用コマンドの見出し抽出

```bash
gsk mesh ssh matsuchan-pc -- 'rg -n "^## " ~/git-repos/docs/運用コマンド一覧.md | head -40'
```

### D. パートナー確認（読取・取込まで／送信しない）

手順の正本は `運用コマンド一覧.md` の「パートナー（やり取り）」。  
**前半**（Gmail / MailGates / LEAFくらさぽ / iMessage / Chatwork）までならバックアップ向き。  
LINE／オプチャ後半は重い・QR がありうる → **ユーザー明示時のみ**。

例（カレントと Python は一覧どおり）:

```bash
cd ~/git-repos/215_kamiooya/C1_cursor/1b_Cursorマニュアル
# 具体コマンドは 運用コマンド一覧.md を開いてコピー（ここでは省略・正本優先）
```

### E. Obsidian 要約

```bash
# 例: Literature Note の特定ファイルを読んで3行要約（パスは依頼で指定）
gsk mesh ssh matsuchan-pc -- 'ls ~/Documents/500_Obsidian_r1/03_Literature\ Note\(まとめノート\)/仕事術・AI連携/ | head'
```

書込・OGD 同期が必要なら Jarvis に引き継ぐか、ユーザーが「書いて」と明示したときだけ。

### F. GenMail

要対応の洗い出し・下書きまで。パートナー重要スレの**送信確定は Jarvis**。

---

## 6. 報告フォーマット（必須）

```
【やったこと】
【使ったパス／コマンド】
【結果（件数・要約）】
【次に人がやること】
【読まなかった／触らなかった秘密】あり
```

---

## 7. 第1依頼文（実地テスト用・そのまま貼れる）

```
matsuchan-pc に SSH して次だけやって。秘密ファイルは触らない。
キット: ~/git-repos/docs/FRIDAY_運用キット.md

1. hostname と pwd
2. ls ~/git-repos/docs | head -20
3. ~/git-repos/docs/運用コマンド一覧.md から「パートナー」関連の見出しを箇条書き
4. 結果をキットの報告フォーマットで返す
```

---

## 8. Jarvis（Cursor）との役割分担

| | Jarvis | FRIDAY |
|---|---|---|
| 本線 | ○（ルール・MCP・launchd・秘密） | バックアップ |
| Cursor 枠 100% 時 | on-demand で継続 | 軽い知的作業・読取・下書き |
| パートナー送信 | 了承後に実行 | 下書きまで |
| Mesh | PC 側セットアップ担当 | サンドボックス側／利用側 |

Cursor 枠切れ時の方針（2026-09-16 確定）: **on-demand ＋ Genspark クラウド**。  
Claude Code 未課金のため GenTeam×Claude は使わない。Cursor CLI 経由は枠を食うのでバックアップに数えない。

---

## 9. トラブル時

| 症状 | 対処 |
|---|---|
| `matsuchan-pc` に繋がらない | PC で `gsk mesh status` / `gsk mesh devices`。offline なら `gsk mesh join --name matsuchan-pc` → `gsk mesh serve` |
| Permission denied | `user@matsuchan-pc` を試す |
| sb-box が消えた | FRIDAY セッション側で再 join（仕様） |
| 秘密が必要 | **止めてユーザー／Jarvis に渡す**。自分で `.env` を開かない |

離脱（緊急）:

```bash
gsk mesh leave
# または serve のみ止める
gsk mesh serve --stop
```

---

*PC 側 Mesh 開通実測: 2026-09-17（join / serve / PC→sb-box SSH・scp OK / autostart ON）*
