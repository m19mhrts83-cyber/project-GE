# ~/.claude/CLAUDE.md（草案・この家用）

**使い方（Mac）**: このファイルを `~/.claude/CLAUDE.md` にコピーする（無ければ `mkdir -p ~/.claude`）。  
プロジェクト直下に置く場合は `~/git-repos/CLAUDE.md` ではなく、**AIチーム運用の正本**  
`docs/AIエージェントチーム/CLAUDE.md` を読む（ルートに二重正本を作らない）。  
**長さ**: 短い家ルールだけ。詳細はリポの MD を都度読む。

**受け渡しの正本**: `docs/AIエージェントチーム/43_Claude_Code参加_受け渡し_20261023.md`

---

## 起点

- 運用の起点は **Jarvis（Cursor）**。ルールの正本更新も Jarvis 経由を優先する。
- 秘密・トークン・パスワードはチャット／MD／Slack に書かない。正本は `~/git-repos/.env.jarvis_private`（社員は各 `.env` 二層）。

## リポを開いたら最初に読む

1. **受け渡し**  
   `docs/AIエージェントチーム/43_Claude_Code参加_受け渡し_20261023.md`
2. **AIチーム運用**なら  
   `docs/AIエージェントチーム/AGENTS.md` → 正本 **`CLAUDE.md`**
3. 社員タスクなら  
   `docs/AIエージェントチーム/…/NNN_名前/AGENTS.md` → **`CLAUDE.md`** ＋ **`TASK.md`**
4. Cursor 専用の `.cursor/rules/*.mdc` を全部読もうとしない。必要なテーマは docs／社員 CLAUDE へ。

## 共通ルール（2026-10-24・正本 `docs/AIエージェントチーム/49_共通ルール_AI使用量と入力_20261024.md`）

- 松野さんの指示は **Typeless の音声入力**。誤記を前提に意図を補って読み、解釈が分かれるときだけ確認する
- 文字起こしは AI チャットでやらない → `scripts/jarvis_transcribe_m4a.py`
- PDF を作ったら元 MD を同じフォルダに同名で置く。AI は MD を読む
- ダッシュの「聞く」はオートでも軽いモデルから。不足時だけ重い側へ
- `48_読まなくてよいMD一覧` は名指し時のみ。`docs/運用コマンド一覧.md` は該当節だけ読む

## 守ること（L0）

- 対外送信・振込・削除・課金変更は **人の了承**まで実行しない
- Todoist 完了は **いきなり close しない**（オーナー確認 → 了承後）。確認のみ例外は社員 313 の定義に従う
- Slack 投稿は **番号＋短い役割語**。見る端末は iPhone 前提（空行・1項目2行以内）。詳細は  
  `docs/AIエージェントチーム/38_…` と `41_Slackスマホレイアウト_草案_…`
- 短い合図・進捗は Slack `#ai-hub`。作業本体は社員フォルダの `TASK.md`／`input`／`output`
- Drive `【with Grok bot】` は **Grok↔Jarvis 専用**。Claude から日常キューに書かない（Grok へ渡す長文は Jarvis 経由）
- 定期実行の本線は **GHA**（または launchd）。Claude Code Routines に本番をロックしない
- 変更したら同じターンで社員 `CLAUDE.md` か docs を更新（チャットだけで終わらない）

## やらないこと

- `.env` の値をエコーしてログに残す
- 番号だけの Slack 書き出し
- 確認なしの本番送信・一括 close
- 送金・OTP・銀行 IB（617 は Jarvis 専属）
