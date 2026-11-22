# Todoist消化係（318・仮）

**作業を始めたら、まず [`PROGRESS.md`](./PROGRESS.md) を読む**（どの Phase まで出来ているか・持ち越しがここにある）。

Todoist の未完了タスクを優先順に拾い、前回から変わっていない件は飛ばし、①AIのみ／②松野さんの判断／③本人操作に仕分ける。
Phase 2 以降で ① を AI が進め、② を `/313/bulk` で判断してもらい、③ を 312 の週次へ渡す（今はまだ作らない）。

- 状態: **設計中**（registry の status は変えない。昇格は松野さんの了承後）
- 設計の正本: FlowForge [flow_HMy15MUxWiSpw5QgAPYa_8e4](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_HMy15MUxWiSpw5QgAPYa_8e4)（承認済み 15 ノード・11 接続）。各ノードの説明文が仕様。読み方は [`flow.md`](./flow.md)
- 仕様を変えたい時は独断で変えない。300 BL（ラスカル）に相談する
- 実装: `scripts/jarvis_todoist_318_triage.py`／基準: `config/todoist_318_criteria.yaml`／テスト: `scripts/tests/test_todoist_318_triage.py`
- 関係: 起票は [312](../312_Todoist起票整理係/CLAUDE.md)、完了・片付け・毎朝の 0.5 は [313](../313_完了候補確認係/CLAUDE.md)、コメント起動は [317](../317_コメント起動係/CLAUDE.md)

## 1. 役割

- **やること（Phase 1・いま動くもの）**
  - 開始チェック: 停止スイッチ・排他（ロックファイル）・313 との重なり・Todoist 接続・本人権限
  - 1-1 採用済み基準（`config/todoist_318_criteria.yaml` の `adopted`）と判断履歴（313 の「残す」記録・318 の履歴）を読む。読めなければ安全停止
  - 1-2 対象の抽出と並べ替え（今日まで＋締切が近い・担当が自分か未割当）。読取失敗は0件扱いにせず失敗終了
  - 1-3 前回から変化なしの除外（題・説明・期限・締切・優先度・ラベル・コメント・本人回答・親子の依存）
  - 1-4 3分類と根拠。迷ったら②。大規模は印だけ付けて既存タスクのまま
  - 内部ログ（`.jarvis_state/todoist_318/`・git 管理外）に分類根拠・採用基準・判断案・停止理由・次回再評価条件・処理日時と「報告案」を保存
- **やらないこと（Phase 1）**
  - Todoist への書き込み一切（コメント・完了・削除・期限変更）
  - Slack 送信（#consult・#ai-hub とも「案」の保存だけ）、`/313/bulk` への登録
  - ① の自律実行、他エージェントへの新規依頼
  - 定期起動の登録（10:30 の launchd・GHA・cloud 予定タスク）、313 の起動設定の変更（313 の 0.5 はそのまま動かす。松野さん了承済み）
  - 外部送信・削除・支払い・契約・マージ・デプロイ

## 2. 動き出す合図

- [x] 人が頼む（手動実行だけ。Phase 1）
- [ ] 時間（毎朝 10:30。**Phase 1 では登録しない**。313 0.5 との二重起動禁止の取り決めが先）

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| 外部連携（API） | ○（読むだけ） | Todoist API v1 を GET だけ。`TODOIST_API_TOKEN_OWNER`（本人権限）。分身トークンでは読まない |
| CLI | ○ | `scripts/jarvis_todoist_318_triage.py` |
| Slack | × | Phase 1 は送らない |
| 画面操作 | × | |

秘密は `.env.jarvis_private`。値を表示・記録しない。

## 4. 報告

- Phase 1 は **報告案を内部ログ（`runs/<run_id>.json` の `report_draft`）に置くだけ**。件数と ①②③ の内訳だけでタスク名は書かない
- Phase 2 以降の出口（フロー end ノード）: 既存の送信承認ルールで許された時だけ所定 Slack に1通。313 と二重に報告しない

## 5. 使い方（Mac）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
PY=~/selenium_env/venv/bin/python
$PY scripts/jarvis_todoist_318_triage.py run --dry-run      # 履歴は更新しない（内部ログは残す）
$PY scripts/jarvis_todoist_318_triage.py run                # 履歴も更新（Todoist は読むだけ）
$PY scripts/jarvis_todoist_318_triage.py status             # ロック・停止スイッチ・直近の報告案
$PY scripts/jarvis_todoist_318_triage.py unlock --force     # 異常終了で残ったロックを外す（実行中でないと確かめてから）
touch .jarvis_state/todoist_318/STOP                         # 停止スイッチ（消すと解除）。環境変数 TODOIST_318_STOP=1 でも可
```

- 最大 60 分・処理 5 件（引数で増やせない）。コメントを読むのは 1 回 30 件まで（残りは繰越）
- 10:15–11:30 は 313 0.5 の時間帯なので止まる（重ならないと確かめた時だけ `--allow-313-window`）
- worktree から本番の state を読む時は `--state-dir ~/git-repos/.jarvis_state`

### AI 分類（この実行の Claude Code で見直す・追加の有料 API なし）

1. `run --dry-run --emit-packet` → `.jarvis_state/todoist_318/packet.json`（題・説明・直近コメント・ルールの結果。非公開の置き場だけ）
2. Claude Code が読んで `answers.json` を書く: `{task_id: {category: "1"|"2"|"3", reason: "…", snapshot_id: packet の値, large: bool}}`
3. `run --ai-answers .jarvis_state/todoist_318/answers.json`
- AI は ②③（実行しない側）へはいつでも動かせる。① にできるのは採用済み②基準に当たらない件だけ。内容が変わって snapshot_id が違う回答は使わない
- ログには `classified_by`（rule / ai(claude_code)）と `rule_category`（ルールの結果）を両方残す

## 6. 判定

| 結果 | いつ |
|---|---|
| success | 対象が「分類済み・変化なしスキップ・313 で残す済・繰越」のどれかに到達し、内部ログを保存できた（0件・上限で繰越も成功） |
| partial | 一部のコメントが読めず保留にした等、未解決のエラーが残った |
| failed | 読取不可・権限不足・排他異常・基準/履歴が読めない・内部ログの保存失敗 |
| stopped | 停止スイッチによる正常停止（別記） |

終了コード: success/stopped=0、partial=1、failed=2。

## 7. 改善ログ

| 日付 | 変更 |
|---|---|
| 2026-11-22 | FlowForge でフロー設計（たたき台→承認済み 15 ノード） |
| 2026-11-23 | Phase 1 実装（読むだけ・抽出・変化なし除外・3分類・内部ログ・手動実行）。社員フォルダ作成。313 の順位付けの部分一致・同点集中・読取の取りこぼしを直して再利用 |
