# adjust-cash — 参照

## 口座 ID（レール・キープで使う）

| id | 呼び名 |
|---|---|
| `smbc_kariya` | 三井住友 刈谷（カード寄せ先の既定） |
| `sbi_net_main` | ドコモSMTB／第一生命NEOBANK本（イチゴ） |
| `sbi_net_sub` | 同上・副 |
| `tokairokin` | 東海労金 |
| `mufg_atsuta` | 三菱UFJ 熱田（真治・マイカー引落） |
| `mufg_toyoake` | 三菱UFJ 豊明（千景・真治 AW 不可） |
| `shiga` | 滋賀銀行 |
| `kyoto_kariya` | 京都銀行 刈谷 |

## 必須キープ（2026-10〜）

| id | 口座 | 月額 | 日 | 期限 |
|---|---|---|---|---|
| `smcc_preferred_residual_docomo_smtb` | `sbi_net_main` | 10,860 | 26 | 〜2027-07 |
| `bmw_mini_mufg_mycar` | `mufg_atsuta` | ≈32,426（ボーナス月別） | 21 | 継続 |

正本: `config/known_recurring_debits.yaml`

## レール → ランチャ（browser_automation）

カレント: `~/git-repos/215_kamiooya/C1_cursor/browser_automation`

| rail id | スクリプト |
|---|---|
| `sbi_main_smbc` | `./run_phase1_sbi_main_to_smbc.sh` |
| `sbi_sub_smbc` | `./run_phase1_sbi_sub_to_smbc.sh` |
| `tokairokin_smbc` | `./run_phase1_tokairokin_to_smbc.sh` |
| `mufg_airwallet` | `./run_phase1_airwallet_to_smbc.sh`（千景は IB 経路） |
| `shiga_smbc` | `./run_phase1_shiga_to_smbc.sh`（≤10万は AW 優先） |
| `kyoto_smbc` | `./run_phase1_kyoto_to_smbc.sh`（同上） |

例:

```bash
./run_phase1_sbi_main_to_smbc.sh --preview
./run_phase1_sbi_main_to_smbc.sh --go --execute --money-ops-id <UUID>
```

## money-ops

- UI: https://jarvis-trade-desk.vercel.app/money-ops
- 横断キュー: `scripts/jarvis_transfer_queue.py --money-ops-id <UUID>`
- 設計: `docs/KURASHIFT_送金アシスト_実務者設計_20260814.md`

## 最新残高の取り方（プラン前・SKILL §0c）

| 手段 | コマンド／手順 | 備考 |
|---|---|---|
| Zaim 連携更新 | `scripts/jarvis_zaim_bank_sync_manual.py --try-otp --names …` | SBI 表記は画面どおり（例: `住信 SBI ネット銀行`）。親「ドコモ SMTB」は not found になりやすい |
| liquidity 再取得 | `scripts/jarvis_liquidity_weekly.py --json` | 更新クリック後、数十秒置いてから |
| 滋賀 IB | `config/kurashift_ib_shiga.yaml` ＋ `SHIGA_IB_*` | 合言葉・**強制ログイン**・端末登録「しない」 |
| 京都 IB | `config/kurashift_ib_kyoto.yaml` ＋ `KYOTO_IB_*` | 同上系 |
| 東海労金 | `TOKAIROKIN_*` ＋ `browser_automation` | 合言葉 env |
| ユーザーアプリ | Olive／NEOBANK 等のスクショ | Jarvis が取れないとき。アプリ／IB を Zaim より優先 |

食い違い時は **アプリ／IB を正**にし、`card_debit_watch.json` の live 残高メモを更新してよい。

## よくある失敗

| 症状 | 対処 |
|---|---|
| 古い Zaim 残高でプランを組んだ | §0c。連携更新＋liquidity／IB／アプリで再確認してから金額確定 |
| スクリプト終了＝送金完了と思った | 完了画面・残高で確認 |
| SBI を空にしたら Preferred 残債で不足 | usable から 10,860 を先に残す |
| Cursor ターミナルで OTP が進まない | Terminal.app で同じコマンド |
| 千景 MUFG を AW 提案した | IB（または本人 AW）。真治 AW 直結不可 |
| 給与前に大型寄せ | `jarvis_salary_pay_calendar.py` ＋ **寄せ先の最新残高**で余り着金を見る |
