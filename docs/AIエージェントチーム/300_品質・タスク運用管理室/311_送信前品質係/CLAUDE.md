# 送信前品質係

**作業を始めたら、まず [`PROGRESS.md`](./PROGRESS.md) を読む。**

ID: **311**（旧フォルダ `10_` → 3桁化）。  
外に出る文面を、**送信前に機械的に止めるゲート**。文面の良し悪しは見ない。抜け・誤送を止めるだけ。送信ボタンは押さない。

### 実行の正（2026-10-18）

- FlowForgeの「AIエージェント」＝役割ラベル。点検本体は **ルールエンジン（Python）**（LLM従量は初版不要）
- 報告は既存 `jarvis_slack_webhook_post.py`（`.env.jarvis_private` の Webhook）
- **本線CLI**: `~/git-repos/scripts/jarvis_send_gate_311.py`
  - 経路B: `--draft` `--source` `--dry-run` / `--post`
  - 経路A: `--from-inbox`（`input/*.md` → `processed/`。`README`/`example_*` スキップ）
  - 上流キック: `--enqueue --draft … --source …`
- **定常**: launchd `com.matsunoma.jarvis.send-gate-311-inbox-poll`（15分）  
  設置: `launchd/install_send_gate_311_inbox_poll_launchd.sh`  
  無効: `JARVIS_SEND_GATE_311_POLL_DISABLE=1` または uninstall
- **上流**: 211＝apply後自動enqueue／ホーク＝`action: send_gate_311`（bucho poll）／手順 `docs/phase3-upstream.md`
- 禁止パターン: `config/banned_patterns.yaml`
- Phase 1〜3 済
- NG報告は「要約・内訳・見方・次」を必ず含める（運用しながら文言を磨く）

## AIオートメーション（作業フロー）

- **FlowForge 改訂版（本線）**: [flow_x4Sw8mVvuGVme1fXz9JGfs3v](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_x4Sw8mVvuGVme1fXz9JGfs3v)（きっかけ起動）
- **FlowForge 変更前（デモ・触らない）**: [flow_AKQv6lgUEtudWlE5fQUhQnh2](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_AKQv6lgUEtudWlE5fQUhQnh2)
- 一覧・進捗: [`15_FlowForge全体系_進捗_20261010.md`](../../15_FlowForge全体系_進捗_20261010.md)
- 設計メモ: [`flow.md`](./flow.md)／人向け1枚: [`README.md`](./README.md)

## 1. 役割

- やること:
  - 渡された **下書き1件** について、初版チェック3点を実施
  - 結果は **OK／NG** と NG理由1行
  - NG → Slack `#consult`（送信を止める材料）／通過 → `#report` に件数のみ
- やらないこと:
  - 日次で「何が下書きに入ったか」のデルタ探索
  - 文面の書き換え・誤字校正・トーン修正（**それは Jarvis の送信プレビュー点検**＝`jarvis-outbound-confirm`。311ではない）
  - 了承なしの本番送信
  - 秘密の再掲

### 初版チェック（3点だけ）

1. **宛先** — アドレス／フォームURLが対象の会社・スレッドと一致。返信なら元スレッド相手と同じか
2. **本人名** — 送信者が松野真治、返信先が `matsuno.estate@gmail.com`。相手担当者名の食い違い
3. **運営宛禁止** — ポータル運営・サイト管理者・noreply 等になっていないか

物件名照合は2版以降（KURASHIFT deals の識別が埋まってから）。

## 2. 動き出す合図

- [ ] 人が頼む（副・手動のみ。本線ではない）
- [ ] 時間（**使わない**。旧デモの毎日18:00は捨てた）
- [x] **何かが届いたら／きっかけ** — 上流が下書きパスを渡したとき → **人間ノードを挟まず AI が点検**  
  対象上流: **S9**（管理会社開拓）／**211**（返信案内下書き）／**ホーク**（業者返信等）／S2 送信前

### パス受領の二本柱（確定 2026-10-17）

| 経路 | 誰向け | やり方 |
|---|---|---|
| **A. inbox MD** | S9／ホーク | `input/`（または Drive 相当）に短い依頼 MD（`draft_path` / `source`）。Jarvis／poll が拾う |
| **B. CLI** | 211 GHA・Jarvis | `jarvis_send_gate_311.py --draft … --source …`（実装時） |

ペイロード最小: `draft_path`＋`source`（s9|211|hawk|s2|manual）。本文は渡さない。  
**フロー上の「人間が見る」は入れない**（パス確認も判定レビューも）。人が見るのは送信直前の outbound-confirm のみ。結果は Slack。

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| チャット・検索 | ○ | 渡された下書き・やり取り.md を読む |
| 外部連携（API/MCP） | △ | 必要なら読取のみ（送信しない） |
| CLI | ○ | パス受領 B・点検本体 |
| ブラウザ | △ | 最終画面の目視補助まで |
| 画面操作 | × | 送信クリックは人 |

**人が確かめる**: 外に出す（送信・投稿）。金・削除も人。ゲート途中の承認待ちは置かない。

## 4. 報告先

| 種別 | 行き先 |
|---|---|
| 通過（件数） | Slack `#report` |
| NG・要判断 | Slack `#consult` |
| Webhook | `SLACK_WEBHOOK_AI_TEAM_REPORT`（URLは env のみ） |

## 5. 成果物の置き場

- 下書き正本: OneDrive 各パートナー `4.送信下書き.txt` 等（**きっかけで渡されたパスのみ**）
- ルール: `jarvis-outbound-confirm.mdc` / `partner-email-send.mdc`
- ログ: このフォルダ `logs/`

## 6. 作業手順（チェックリスト）

1. A または B で `draft_path` を受け取り、更新日時を確認（1件）
2. 3点点検（自動・人間待ちなし）
3. OK／NG＋理由1行を出す（書き換え・送信はしない）
4. NG → `#consult`／通過 → `#report` 件数
5. ユーザー了承後の送信は別タスク（outbound-confirm）

## 7. 改善ログ

| 日付 | 変更 |
|---|---|
| 2026-10-09 | ハブ初期化・候補として作成 |
| 2026-10-09 | 3桁化（旧10_ → 311）。ビルダー部門「品質・タスク運用管理室」配下へ |
| 2026-10-16 | ホーク修正指示: 次作る＝311。3点ゲート・人が頼む→上流送信前 |
| 2026-10-17 | 改訂版 FlowForge `flow_x4Sw8…`（きっかけ）。18時定期は捨て。変更前デモ `flow_AKQv6…` は残置 |
| 2026-10-17 | 開始＝A+B確定。人間ノード削除。結果系＝Slack #report／#consult |
| 2026-10-17 | FlowForge に経路A／B分岐＋合流（次の担当=AI）を明示 |
| 2026-10-18 | Phase1 CLI＋Slack。Phase2 inbox poll（15分 launchd） |
| 2026-10-18 | Phase3 上流キック（enqueue・211配線・ホーク action） |
