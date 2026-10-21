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

0. **最新残高を確認してから**プラン検討に入る（古い Zaim／liquidity だけで金額を決めない）
1. **プラン承認**（この時点では資金は動かない）
2. **Jarvis が入力・遷移**（実行クリックはしない）
3. **最終画面をユーザー確認**
4. **OTP／アプリ承認＋実行ボタンはユーザー**

無断振込・了承前の `--go` / `--execute` は禁止。  
**残高未確認のままギャップ表・寄せ金額を確定しない。**

## 手順

### 0. 対象を1行で確定

文脈が無ければ短く聞く（分かるなら省略可）:

- 対象支払い（Olive INF／Amex／固定引落／全般）
- 期限（今月 due／指定日）
- 寄せ先（既定: **SMBC刈谷**＝カード引落口座）

### 0b. 事実確認は先に自分で（松野に聞かない）

**引落済・請求額など Zaim／Vpass／state で分かることは、質問せずに確認してからプランに反映する。**  
（**口座残高そのものは §0c。** 週次 CSV／古い liquidity を「最新残高」扱いしない。）

| 確認したいこと | 正 |
|---|---|
| カード引落が済んだか | Zaim 年度 CSV（例: `…/2026年度/Zaim.2026年度.csv`）で due 前後の **支払元→カード** 振替／支出 |
| 請求額・due | `jarvis_card_debit_watch.py --fetch-vpass`（SMCC）／カード通知 |
| 給与余りゲート | `jarvis_salary_pay_calendar.py` ＋ **寄せ先口座の最新残高**（§0c） |

- 引落確認できた → プランから外す／済と扱う。不安なら **「Zaimで確認済: …」と1行報告**するだけでよい（「済みましたか？」と聞かない）
- CSV に無い・金額不一致・口座が特定できない → そのときだけ短く聞く

### 0c. 最新残高ゲート（プラン前必須・2026-10-21 教訓）

**寄せプランの金額を出す前に、使う口座の残高を最新化する。**  
Zaim `liquidity_snapshots`／週次 CSV だけでは不足しうる（例: SMBC・SBI がアプリと数万〜十万円単位でズレた）。

#### 必須で最新化する口座

| 優先 | 口座 | 理由 |
|---|---|---|
| 必須 | 寄せ先（既定 `smbc_kariya`） | 不足額の起点 |
| 必須 | プランで送出する各口座（SBI本／副・東海労金・滋賀・京都・PayPay 等） | usable・送金額の正 |
| 推奨 | 給与振分先（名銀・大垣・東海） | 余り・固定振分の着金確認 |

#### 取り方（止まず・優先順）

秘密は `.env.jarvis_private`。チャットに PW／OTP を出さない。

1. **Zaim 連携更新 → liquidity 再取得**（まとめて更新向き）  
   ```bash
   cd ~/git-repos && set -a && source .env.jarvis_private && set +a
   # 対象名は Zaim 画面の表記に合わせる（SBI は「住信 SBI ネット銀行」等）
   ~/selenium_env/venv/bin/python scripts/jarvis_zaim_bank_sync_manual.py --try-otp --lock-wait 120 --names \
     '★三井住友銀行' '住信 SBI ネット銀行' '★東海労金' '★滋賀銀行' '★PayPay銀行' '★京都銀行'
   # 更新反映を数十秒待ってから
   ~/selenium_env/venv/bin/python scripts/jarvis_liquidity_weekly.py --json
   ```
2. **銀行 IB／NEOBANK に Jarvis がログインして残高照会**（Zaim が lag／不一致のとき）  
   - 滋賀・京都: `config/kurashift_ib_*.yaml` ＋ env（合言葉・強制ログインあり）  
   - SBI／ドコモSMTB: アプリ目視 or 既存 NEOBANK 自動化の残高確認  
   - 東海労金: `TOKAIROKIN_*` ＋ browser_automation
3. **ユーザーの銀行アプリ目視**（スクショ／数字）。Jarvis が取れない・OTP で止まったときだけ依頼

#### ゲート通過条件

次を満たすまで **§3 の寄せプラン金額を確定しない**（必要額・Vpass の収集は先行してよい）:

- 寄せ先＋送出候補の各残高に **取得元と時刻**がある（例: `olive_app` / `shiga_ib` / `zaim_after_update`）
- アプリ／IB と Zaim が食い違う → **アプリ／IB を正**。state に上書き（`card_debit_watch.json` の live 残高メモ可）
- 取れない口座は「要目視」とし、その口座からの送金額を仮置きで確定しない

報告に1行: `残高確認: SMBC …（出典） / SBI … / …`

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
**余り見積だけを信じず、寄せ先の最新残高（§0c）で着金有無を見る。**

### 2. usable を計算する（§0c の最新残高のみ）

```
usable = 最新残高 − keep_floor − （該当する known_recurring の月額）
```

**必須キープ（忘れるな）**

| 口座 | keep |
|---|---|
| `sbi_net_main`（ドコモSMTB／第一生命NEOBANK本） | 最低 **解約済 Preferred 残債 10,860円**（〜2027-07・毎月26日）。レール YAML の古い `keep_floor_jpy`（例: 31万）は当サイクルの実残高と照合してから使う |
| `mufg_atsuta` | BMW/MINI マイカー月額（約32,426・ボーナス月は別）を SBI keep に足さない |
| その他 | レール YAML の `keep_floor_jpy`（残高未満なら送出不可・要見直し） |

「カード使えない＝引落なし」とみなさない。

### 3. ギャップ表を出す（残高確認後）

チャットに必ず出す（実行前）:

```
📎 資金確認（adjust-cash）— YYYY-MM-DD
【残高確認】出典・時刻（例: SMBC olive_app 21:43 / SBI NEOBANKアプリ / 滋賀 IB 21:57 / 他 zaim_after_update）
【支払い】
- 対象: … / due: … / 必要額: …円 / 寄せ先: SMBC刈谷（等）
【口座】
| 口座 | 最新残高 | 出典 | keep | usable | 判定 |
| … | … | … | … | … | OK / 不足 N円 |
【ギャップ合計】不足 …円
【寄せプラン案】（金額・レール・手段）
1. …
【ゲート】給与余り待ち: あり/なし
【次】このプランで進めてよいですか？（承認後にだけ実行）
```

残高が取れない口座は「要目視」とし、推測で OK／送金額確定にしない。

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

- **最新残高未確認のまま**寄せ金額・ギャップ表を確定する（古い Zaim／liquidity のみ）
- 了承前の本番送金
- SBI本を Preferred 残債無視で空にする
- 名義違いを AW に載せる
- 秘密（口座全文・PW・OTP）をチャットに再掲
- NISA 月9万／生活防衛／次物件キープを削る寄せの推奨
