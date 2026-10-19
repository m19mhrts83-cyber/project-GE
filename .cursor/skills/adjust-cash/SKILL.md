---
name: adjust-cash
description: >-
  支払いに必要な資金が各口座にあるか確認し、不足口座へ寄せ（資金移動）プランを立てて実行する。
  Use when the user runs /adjust_cash, or asks for 資金確認、資金移動、寄せ、口座残高不足、
  カード引落バッファ、money-ops、支払いに足りるか。
---

# 資金確認・寄せ（adjust-cash）

## 616 との境界（混同しない）

| 仕事 | 正 |
|---|---|
| **不足の検知・促しだけ** | **616**（ルール `jarvis-agent-616-cash-remind.mdc` ＋社員 `CLAUDE.md`）。**本スキルは使わない** |
| **ギャップ表→了承→送金** | **本スキル**（Jarvis）。ユーザーが寄せ実行を頼んだとき |

616 をスキル／スラッシュに振り分けない。

## 目的

直近の支払い（カード引落・固定引落など）に対し、**各口座の usable を見て不足を特定**し、**無料レール→AW→IB** の順で寄せプランを出し、了承後に実行する。

## 呼び出し

- スラッシュ: **`/adjust_cash`**
- 言い回し例: 「支払いに足りるか見て」「寄せて」「資金移動したい」「カード引落のバッファ」

## 鉄板 UX（崩さない）

1. **プラン承認**（この時点では資金は動かない）
2. **Jarvis が入力・遷移**（実行クリックはしない）
3. **最終画面をユーザー確認**
4. **OTP／アプリ承認＋実行ボタンはユーザー**

無断振込・了承前の `--go` / `--execute` は禁止。

## 手順

### 0. 対象を1行で確定

文脈が無ければ短く聞く（分かるなら省略可）:

- 対象支払い（Olive INF／Amex／固定引落／全般）
- 期限（今月 due／指定日）
- 寄せ先（既定: **SMBC刈谷**＝カード引落口座）

### 0b. 事実確認は先に自分で（松野に聞かない）

**Zaim／Vpass／state で分かることは、質問せずに確認してからプランに反映する。**

| 確認したいこと | 正 |
|---|---|
| カード引落が済んだか | Zaim 年度 CSV（例: `…/2026年度/Zaim.2026年度.csv`）で due 前後の **支払元→カード** 振替／支出 |
| 請求額・due | `jarvis_card_debit_watch.py --fetch-vpass`（SMCC）／カード通知 |
| 残高目安 | Zaim CSV・liquidity／口座スクリプト（古いときは「要目視」と明記） |

- 確認できた → プランから外す／済と扱う。不安なら **「Zaimで確認済: …」と1行報告**するだけでよい（「済みましたか？」と聞かない）
- CSV に無い・金額不一致・口座が特定できない → そのときだけ短く聞く
- 週次 CSV が due より古いときだけ、再エクスポート or 目視を提案

### 1. 必要額を集める（止まず）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_card_debit_watch.py --fetch-vpass
~/selenium_env/venv/bin/python scripts/jarvis_salary_pay_calendar.py
```

正本を読む:

| 何 | パス |
|---|---|
| 定期引落・キープ | `config/known_recurring_debits.yaml` |
| 送金レール | `config/kurashift_transfer_rails.yaml` |
| キープルール | `.cursor/rules/jarvis-fund-transfer-keep.mdc` |
| AW優先 | `.cursor/rules/jarvis-airwallet-prefer.mdc` |
| 助言順 | `.cursor/rules/jarvis-finance-philosophy.mdc` |

大型寄せは給与余り着金後（`wait_for_salary_before_xfer`）をゲートにする。

### 2. usable を計算する

```
usable = 残高 − keep_floor − （該当する known_recurring の月額）
```

**必須キープ（忘れるな）**

| 口座 | keep |
|---|---|
| `sbi_net_main`（ドコモSMTB／第一生命NEOBANK本） | YAML `keep_floor` ＋ **解約済 Preferred 残債 10,860円**（〜2027-07・毎月26日） |
| `mufg_atsuta` | BMW/MINI マイカー月額（約32,426・ボーナス月は別）を SBI keep に足さない |
| その他 | レール YAML の `keep_floor_jpy` |

「カード使えない＝引落なし」とみなさない。

### 3. ギャップ表を出す

チャットに必ず出す（実行前）:

```
📎 資金確認（adjust-cash）— YYYY-MM-DD
【支払い】
- 対象: … / due: … / 必要額: …円 / 寄せ先: SMBC刈谷（等）
【口座】
| 口座 | 残高目安 | keep | usable | 判定 |
| … | … | … | … | OK / 不足 N円 |
【ギャップ合計】不足 …円
【寄せプラン案】（金額・レール・手段）
1. …
【ゲート】給与余り待ち: あり/なし
【次】このプランで進めてよいですか？（承認後にだけ実行）
```

残高が画面で取れない口座は「要目視」とし、推測で OK にしない。

### 4. 寄せプランの優先順

1. **無料**（SBI本／副 → SMBC・ことら）
2. **≤10万かつ AW 紐づけ可** → エアウォレット（滋賀・京都・MUFG熱田など。千景 MUFG豊明は真治 AW 不可）
3. **IB**（東海労金・千景MUFG 等）— Terminal.app・OTP はユーザー
4. 契約者貸付・コア売却は **このスキルの対象外**（金融理念ルールへ）

レール定義・ランチャ: `config/kurashift_transfer_rails.yaml`  
UI: https://jarvis-trade-desk.vercel.app/money-ops  
コマンド正本: `docs/運用コマンド一覧.md`（送金アシスト節）

### 5. 了承後の実行

- money-ops にプランがあれば `--money-ops-id` を付ける
- 各レールは **先に `--preview`**、了承後に `--go`（必要なら `--execute`）
- OTP がアプリ／合言葉のレールは **Terminal.app** を案内（Cursor 統合ターミナルは Enter が潰れることがある）
- 完了判断はスクリプト終了ではなく **完了画面・残高・着金**
- 終わったら Chrome 片付け: `scripts/jarvis_automation_chrome_cleanup.py`
- 寄せ完了後: money-ops「寄せ完了」／必要なら `jarvis_card_debit_watch.py --dismiss-due`

### 6. 完了報告

```
📎 資金寄せ結果
- 実行レール: …（完了/待ち/失敗）
- 寄せ先残高目安: …
- 残ギャップ: 0 / N円
- 証跡: 完了画面 or 残高減 or 着金
- 次: なし / 残りレールの続行
```

## 詳細

口座 ID・レール対応・よくある失敗は [reference.md](reference.md)。

## やらないこと

- 了承前の本番送金
- SBI本を Preferred 残債無視で空にする
- 名義違いを AW に載せる
- 秘密（口座全文・PW・OTP）をチャットに再掲
- NISA 月9万／生活防衛／次物件キープを削る寄せの推奨
