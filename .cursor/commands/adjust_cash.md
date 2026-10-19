# 資金確認・寄せ（支払口座の不足を埋める）

呼び出し: **`/adjust_cash`**

スキル正本:

- 個人: `~/.cursor/skills/adjust-cash/SKILL.md`
- リポ: `.cursor/skills/adjust-cash/SKILL.md`
- 詳細: `.cursor/skills/adjust-cash/reference.md`

このコマンドが呼ばれたら、**スキルの手順に従う**（診断だけの説明で終わらない）。

---

## 第1ターン — 確認表まで出す

1. 対象支払いが文脈に無ければ1行聞く（Olive／Amex／全般・due・寄せ先）。分かるなら省略。
1b. **済んだ支払いは Zaim CSV 等で自分で確認**（「済みましたか？」と聞かない）。確認できたらプラン外＋「Zaimで確認済」1行。分からなければそのときだけ聞く。
2. 止まずに必要額・キープ・usable を集める:
   - `jarvis_card_debit_watch.py --fetch-vpass`
   - `jarvis_salary_pay_calendar.py`（大型寄せゲート）
   - `config/known_recurring_debits.yaml`（Preferred 10,860・マイカー等）
   - `config/kurashift_transfer_rails.yaml`
3. チャットに **`📎 資金確認（adjust-cash）`** ギャップ表＋寄せプラン案を出す。
4. **「このプランで進めてよいですか？」** で止める（了承前に送金しない）。

SBI本（`sbi_net_main`）から出す案では、解約済 Preferred 残債 **10,860円** を usable から必ず残す。

---

## 第2ターン以降 — 了承後のみ実行

了承（「これでOK」「進めて」等）が出たらスキル §5:

1. 無料レール → ≤10万 AW → IB の順
2. 各レール `--preview` → 了承済みなら `--go`（必要なら `--execute`）
3. OTP／最終確認はユーザー。Terminal.app 案内可
4. 完了は画面・残高・着金で判断
5. Chrome 片付け → money-ops／`--dismiss-due` が必要なら実施
6. **`📎 資金寄せ結果`** を報告

money-ops: https://jarvis-trade-desk.vercel.app/money-ops  
コマンド正本: `docs/運用コマンド一覧.md`（送金アシスト）

---

## やらないこと

- 了承前の `--go` / `--execute`
- Preferred 残債・マイカー引落を無視した寄せ
- 秘密・OTP をチャットに再掲
