# Phase 1 着手メモ（311）

## 何を作るか

下書きパスを渡すと、3点ルール点検→OK/NGを出し、必要なら Slack に投稿する **1本のプログラム**（LLMは使わない）。

## あなたがやること

1. チャットで **「TODO全部OK」** と返す（追加のインストール・キー取得は不要）
2. 試したい下書きファイルのパスを1つ教える  
   - 省略可。省略時は既存のパートナー `4.送信下書き.txt` 等で dry-run する

## Jarvis がやること（OK後）

1. `~/git-repos/scripts/jarvis_send_gate_311.py` を作成
2. `--draft` / `--source` / `--dry-run` / `--post` で動かす
3. 成功確認: dry-run で OK または NG＋理由1行が出る／`--post` で Slack に届く

## 成功の見え方

- ターミナル（またはチャット要約）に `OK` または `NG: …` が1件分出る
- Slack `#report`（OK件数）または `#consult`（NG理由）に投稿される（`--post` 時）
