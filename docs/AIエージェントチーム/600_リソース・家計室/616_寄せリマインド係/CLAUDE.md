# 616 寄せリマインド係

ID: **616**。リソース・家計室。

## 実行ツール（重要）

**スキル／スラッシュに振り分けない。**  
どのエージェントツールでも、本 `CLAUDE.md`（と Cursor なら `.cursor/rules/jarvis-agent-616-cash-remind.mdc`）を読めば同じ手順で動く。

| 層 | 正本 | 実行可 |
|---|---|---|
| 検知・促し（本係） | 本ファイル ＋ Cursor ルール | Jarvis／FRIDAY／GenCode／Claude Code／Codex 等 |
| 送金・OTP | Jarvis ＋人了承（寄せ手順。スキル名は任意） | **616 ではやらない** |

## AIオートメーション（作業フロー）

- **FlowForge（開く）**: 未作成（[`flow.md`](./flow.md) が当面の正）
- 一覧・進捗: [`15_FlowForge全体系_進捗_20261010.md`](../../15_FlowForge全体系_進捗_20261010.md)
- Cursor ルール: `~/git-repos/.cursor/rules/jarvis-agent-616-cash-remind.mdc`

## 1. 役割

- やること:
  - 直近カード／固定引落の **必要額 vs 寄せ先残高** を見て不足を検知
  - Zaim CSV 等で **済んだ支払いは除外**（人に「済み？」と聞かない）
  - Slack／チャットに短報し、**次は Jarvis が寄せ実行（人了承）** と明記
  - keep（Preferred 残債 10,860 等）を忘れない旨を1行添える
- やらないこと:
  - 銀行ログイン・OTP・振込・`--go`／`--execute`
  - IB／AW の秘密を社員 `.env` に持つ
  - 契約者貸付・コア売却の推奨
  - money-ops の無確認完了操作
  - 「`/adjust_cash` が無いと動けない」と案内する（リマインドはルール本線）

## 2. 動き出す合図

- [x] 時間: 引落 **7日以内**かつ不足ありのとき（目安: 毎朝／パートナー確認前半末尾のついで）
- [x] 人が頼む: 「寄せリマインド」「支払いに足りるか」
- [x] 変化: `card_debit_watch` の shortfall 悪化・Vpass 新請求
- [ ] イベント: money-ops 未完了が due 接近（将来）

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| CLI | ○ | `jarvis_card_debit_watch.py`（読取）／Zaim CSV 読取／将来 `jarvis_adjust_cash_remind.py` |
| 外部API | △ | Slack Webhook（報告のみ） |
| ブラウザ | × | 銀行・カード Web ログインはしない（Vpass 取得が要るときは Jarvis に渡す） |
| 画面操作 | × | |
| スキル／スラッシュ | × | **本係の入口にしない** |

**秘密**: Webhook キー名のみ（`.env.example`）。銀行 PW／OTP は **渡さない**。  
**人が確かめる**: 寄せプラン了承・送金 OTP／実行ボタン（Jarvis）。本係はリマインドまで。

## 設計4点

| 柱 | 内容 |
|---|---|
| **入口** | `card_debit_watch.json`・`known_recurring_debits.yaml`・給与着金カレンダー・Zaim 年度 CSV（済確認） |
| **確認** | 不足があるとき Slack。送金は人了承＋Jarvis。済は Zaim で自己確認 |
| **履歴** | `reports/`・Slack・state（将来 `.jarvis_state/adjust_cash_remind.json`） |
| **停止** | `disabled`／`JARVIS_ADJUST_CASH_REMIND_DISABLE=1`／二重促し（同 due は N 日以内再掲しない） |

## 4. 報告先

| 種別 | 行き先 |
|---|---|
| 定例・不足あり | Slack `#consult`（次: Jarvisに依頼＝寄せ実行）または `#report`（軽微） |
| 失敗 | Slack `#ops` |
| 控え | `reports/YYYY-MM-DD.md` |

**書き出し例**: `【相談】616 寄せリマインド・Olive不足`

### Slack 書き出し（FRIDAY／Jarvis／他ツール共通）

| ch | いつ |
|---|---|
| `#report` | 不足なし・生存確認のみ |
| `#consult` | 不足あり・寄せ判断が要る。末尾「次の担当」3行必須 |
| `#ops` | スクリプト失敗 |

`#consult` 末尾:

```
次: Jarvisに依頼
担当メモ: 寄せ実行（ギャップ表→了承→OTP）。スキル名に依存しない
橋渡し: 松野が了承したら Jarvis へ一声
```

## 5. 成果物の置き場

- 設計正本: 本 `CLAUDE.md`・[`flow.md`](./flow.md)・[`設計案_20261019.md`](./設計案_20261019.md)
- Cursor ルール: `.cursor/rules/jarvis-agent-616-cash-remind.mdc`
- 寄せ**実行**（別レーン）: Jarvis 向け skill `adjust-cash`（任意・送金時のみ）

## 6. 作業手順（チェックリスト）

1. `card_debit_watch` を読む（Vpass 再取得が必要なら Jarvis に依頼）
2. Zaim CSV で due 済みカードを除外
3. SMBC（または決済口座）残高 vs need → shortfall
4. 給与ゲート（余り待ち）を1行
5. 不足なら Slack／チャット。**送金しない**
6. `TASK.md` 更新

## 7. 改善ログ

| 日付 | 内容 |
|---|---|
| 2026-10-19 | 新設（設計中）。銀行秘密は持たない |
| 2026-10-19 | Builder 組織図反映（共有 `uksxiDIzE1AEckKH`）。Drive 旧 `614_Vポイント・テイチャン係` を `_unused_` 退避 |
| 2026-10-19 | **スキル振分を廃止**。ルール＋CLAUDE.md 本線。他ツール可。送金だけ Jarvis |
