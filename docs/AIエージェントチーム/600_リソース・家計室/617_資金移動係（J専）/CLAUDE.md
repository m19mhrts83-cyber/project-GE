# 617 資金移動係（J専）

ID: **617**。リソース・家計室。  
表示名の **（J専）** ＝ **Jarvis 実行専属**（他ツールは送金しない）。

## 位置づけ（他社員と違う）

本係は **定型作業の型（プレイブック）** を置くための社員枠である。  
**起動は人が頼む形が本線**。実行を頼む相手は **Jarvis のみ**。FRIDAY／GenCode／Claude Code／Codex／Grok 等に送金・OTP・IB／AW 操作を振らない。

| 層 | 正本 | 誰が動く |
|---|---|---|
| 不足の検知・促し | **616** | どのツールでも可（ルール＋616 CLAUDE） |
| **本係の発動・寄せ実行** | **`/adjust_cash`**（skill `adjust-cash`）＋本フォルダ | **Jarvis のみ**。コマンド＝本係起動 |
| 定型手順・境界 | 本フォルダ `CLAUDE.md`／`flow.md` | 発動時に Jarvis が読む。他ツールは実行しない |

**頼み方（正）**: Cursor で **`/adjust_cash`** → Jarvis が本係を起動（先頭に `【617 資金移動係（J専）】起動`）。  
他社員のように「社員フォルダを開いて定期ジョブで回す」対象ではない。

## 実行ツール（厳守）

| ツール | 本係でやってよいこと |
|---|---|
| **Jarvis（Cursor）** | **`/adjust_cash` で本係を発動**→プラン〜了承後の入力・遷移。OTP／実行ボタンは人 |
| FRIDAY／GenCode／Claude Code／Codex／Grok | **やらない**。必要なら「Jarvis に `/adjust_cash` を頼んで」と手渡しのみ |
| スキル名への振分（616側） | 616 の入口にしない（既存方針）。617 発動入口は Jarvis の `/adjust_cash` |

## AIオートメーション（作業フロー）

- **FlowForge（開く）**: [flow_duOrNmGET7-E_c7AAQE9fLfO](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_duOrNmGET7-E_c7AAQE9fLfO) · [閲覧](https://flowforge-259747770348.asia-northeast1.run.app/share/NYLpUySk0tY27PvI)
- 素案正本: [`flow.md`](./flow.md)（ノードは（J専）注釈・残高ゲート・了承／残高NG停止あり）
- 一覧・進捗: [`15_FlowForge全体系_進捗_20261010.md`](../../15_FlowForge全体系_進捗_20261010.md)
- 実行手順の正本（コード側）: `~/git-repos/.cursor/skills/adjust-cash/SKILL.md`
- Cursor ルール（境界）: `~/git-repos/.cursor/rules/jarvis-agent-617-fund-transfer.mdc`

## 1. 役割

- やること:
  - カード引落バッファ等への **寄せ（資金移動）の定型手順**を文書化する
  - 最新残高ゲート・keep・レール優先（無料→AW→IB）・了承→OTP の順序を崩さない
  - 616 からの手渡し先として「次は Jarvis／617 型」と明示できるようにする
  - 完了後の money-ops／state 更新の置き場を示す
- やらないこと:
  - **本係フォルダ単体での自動送金**（定期ジョブ・他ツールからの `--go`）
  - FRIDAY／他エージェントへの送金委譲
  - 銀行 PW／OTP を社員 `.env` に持つ
  - 契約者貸付・SBIコア売却の推奨
  - 残高未確認のままギャップ金額を確定する
  - 616（促し）と役割を混ぜる

## 2. 動き出す合図

- [x] **スキルコマンド（本線）**: **`/adjust_cash`** → 本係発動（コマンド正本 `.cursor/commands/adjust_cash.md`）
- [x] **人が頼む（同義）**: 「寄せて」「資金移動」「Olive に足りるように」→ 同上（スキル／617 として扱う）
- [x] 616 からの手渡し（副）: Slack `#consult` 末尾「次: Jarvisに依頼」→ 人が `/adjust_cash` または一声
- [ ] 時間: **付けない**（自動送金しない。促しは 616）
- [ ] 変化の見回り単独: **付けない**（616 の仕事）

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| CLI | ○（**Jarvisのみ**） | `run_phase1_*`／transfer 系（了承後）。読取は watch／Zaim／給与カレンダー |
| ブラウザ／画面操作 | ○（**Jarvisのみ**） | IB／AW 入力・遷移。実行クリックは人 |
| 外部API | △ | Slack 完了報告（任意）。Webhook キー名のみ |
| スキル／スラッシュ | ○ | **`/adjust_cash`** が実行入口（Jarvis） |
| 他ツールからの実行 | × | 禁止 |

**秘密**: 銀行・カードは `.env.jarvis_private` のみ。本フォルダ `.env` にはキー名だけ。  
**人が確かめる**: プラン了承・最終画面・OTP／アプリ承認・実行ボタン。

## 設計4点

| 柱 | 内容 |
|---|---|
| **入口** | 人依頼 or 616 手渡し。`card_debit_watch`・`known_recurring_debits.yaml`・最新口座残高（§0c）・給与カレンダー・Zaim 済確認 |
| **確認** | ギャップ表の了承 → 最終画面 → OTP／実行は人。了承前 `--go` 禁止 |
| **履歴** | transfer_audit／money-ops／`reports/`／チャットの完了1行 |
| **停止** | 人の中止・残高ゲート失敗・Mac版LINE競合等の銀行側失敗・`JARVIS_ADJUST_CASH_*` 系無効化（あれば） |

## 4. 報告先

| 種別 | 行き先 |
|---|---|
| 完了・生存 | Slack `#report`（任意）またはチャット |
| 要判断（レール選択・金額） | Slack `#consult` またはチャット（**実行は Jarvis**） |
| 失敗 | Slack `#ops` |

**書き出し例**: `【報告】617 資金移動・Olive寄せ完了`

### Slack 書き出し

| ch | いつ |
|---|---|
| `#report` | 寄せ完了の短報 |
| `#consult` | プランで判断が要るとき（了承前）。末尾は Jarvis |
| `#ops` | 送金失敗・ロック・残高不一致 |

`#consult` 末尾（他ツールが誤って触ったとき用）:

```
次: Jarvisに依頼
担当メモ: /adjust_cash（617型）。他ツールは送金しない
橋渡し: 松野了承後に Jarvis へ一声
```

## 5. 成果物の置き場

- 定型の型: 本 `CLAUDE.md`・[`flow.md`](./flow.md)・[`設計案_20261021.md`](./設計案_20261021.md)
- 実行手順: skill `adjust-cash`／`docs/運用コマンド一覧.md`「資金確認・寄せ」
- レール: `config/kurashift_transfer_rails.yaml`
- キープ: `config/known_recurring_debits.yaml`／`jarvis-fund-transfer-keep.mdc`
- 促し側: **616**

## 6. 作業手順（チェックリスト・Jarvis用）

1. 対象支払い・due・寄せ先を1行で確定
2. **最新残高ゲート**（寄せ先＋送出口座。アプリ／IB 優先。古い Zaim だけで金額を決めない）
3. Zaim で済んだ引落を除外／need を確定
4. keep（Preferred 残債 10,860→`sbi_net_main` 等）を usable から控除
5. ギャップ表＋レール案（無料→AW→IB）を出し、**了承待ち**
6. 了承後のみ入力・遷移。OTP／実行は人
7. 完了を1行報告。money-ops／watch を必要なら更新
8. `TASK.md` を done

## 7. 改善ログ

| 日付 | 内容 |
|---|---|
| 2026-10-21 | 新設（設計中）。**定型の型のみ／実行は Jarvis 専属**。616（促し）と分離 |
| 2026-10-21 | 残高ゲート §0c を skill 側に反映済（同日コミット）を本型に織り込み |
