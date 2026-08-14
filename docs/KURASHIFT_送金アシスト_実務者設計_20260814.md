# 資金送金アシスト — 実務者設計（2026-08-14）

**役割**: 品質点検済み仕様の実装正本（Wave 0〜）  
**顧客意図**: 承認後は Jarvis が最大限アシスト。取れる OTP は自動。アプリ OTP・生体だけユーザー。

**本番**: https://jarvis-trade-desk.vercel.app/money-ops  
**点検仕様**: [`KURASHIFT_送金アシスト_点検者向け仕様_20260814.md`](KURASHIFT_送金アシスト_点検者向け仕様_20260814.md)

---

## 1. 製品仕様（変更しない）

| 項目 | 正 |
|---|---|
| 承認 | 計画合意のみ。記帳しない（T-SEC-1） |
| 実行入口 | Terminal.app ランチャ → Preview → Go |
| 宛先（Phase1 集約） | SMBC 刈谷 = `PERSONAL_BANK_*` / `smbc_kariya`（銀行 0009・支店 486・普通・下4桁突合） |
| OTP | `gmail_api`／`sms_messages` → Jarvis。`app_onetime_pw`／`passkey_or_bio` → ユーザー |
| 秘密 | `.env.jarvis_private` のみ。チャット・監査に値を出さない |
| SBI ネット認証 | `SBI_NET_*`（証券 `SBI_SEC_*` と分離） |
| headless | 本番 false（アプリ OTP 時に画面を見る） |

---

## 2. レール定義

正本: `config/kurashift_transfer_rails.yaml`

Phase1 目安（2026-08 Infinite）:

| rail_id | 額目安 | otp_channel | Jarvis 上限 |
|---|---:|---|---|
| `tokairokin_smbc` | 233,000 | `app_onetime_pw` | 確認まで＋ホールド。OTP ユーザー |
| `sbi_main_smbc` | 26,000 | 調査後（gmail/sms/app） | 取れるなら実行まで |
| `sbi_sub_smbc` | 161,000 | 同上 | 同上 |
| `mufg_airwallet` | 290,000 | 調査後 | 初回着金証明ゲート |
| `shiga_smbc` / `kyoto_smbc` | 62k／50k | 調査後 | 東海労金型 |
| blocked | PayPay 等 | — | 起動禁止 |

推奨順: 無料レール（SBI）→ IB 他行（東海労金・滋賀・京都）→ アプリ系（エアウォレット）。同一 `from_account_id` の並列禁止。連続間隔 ≥60 秒。

---

## 3. モジュール

### 3.1 OTP — `scripts/jarvis_transfer_otp.py`

```text
入力: rail_id, otp_channel, sender_hint, gmail_account, timeout_sec, after_ms
出力: コード文字列（stdout は成功時のみ呼び出し元が受け取り、ログに残さない）
監査: otp_obtained=true/false のみ
```

- Gmail: 215 token（`token_m19m.json` 等。レールで指定）
- SMS: Messages DB（`jarvis-sms-otp-messages` 同型）
- `app_onetime_pw`: 例外 `NeedsUserOtp` → レール `waiting_user`

### 3.2 監査・ロック — `scripts/jarvis_transfer_audit.py`

- ディレクトリ: `.jarvis_state/transfer_audit/`（gitignore）
- `idempotency_key` = `{money_ops_id}:{rail_id}:{amount}:{dest_mask}`
- ロックファイル: `.jarvis_state/transfer_locks/{key}.lock`
- 記録: 時刻、rail、amount、dest_mask、status、otp_channel、otp_obtained、evidence 種別
- 禁止: PW、OTP 値、口座全文、合言葉、Gmail 本文全文

### 3.3 ガード（起動前）

1. plan `amount_jpy` == CLI `--amount`
2. 出金元スナップ − keep下限 ≥ amount
3. 確認画面 DOM 金額 == amount（不一致なら実行しない）
4. ロック取得成功
5. 無料枠・営業時間ゲート（レール設定）

---

## 4. money-ops 連携

`assist_payload.rails[]` 各要素:

```json
{
  "id": "tokairokin_smbc",
  "label": "東海労金→SMBC刈谷",
  "amount_jpy": 233000,
  "from_account_id": "tokairokin",
  "to_account_id": "smbc_kariya",
  "otp_channel": "app_onetime_pw",
  "keep_floor_jpy": 121000,
  "status": "pending",
  "idempotency_key": null,
  "evidence": null,
  "last_error": null
}
```

- 作成時: YAML Phase1 既定を埋め込み（額は調整可）
- UI: 一覧にレール status を表示
- `done`（オペ全体）: 必須レールが証跡付き done、またはユーザー明示完了

---

## 5. 東海労金（テンプレ）

```bash
# Terminal.app のみ
cd ~/git-repos/215_kamiooya/C1_cursor/browser_automation
./run_phase1_tokairokin_to_smbc.sh --preview
./run_phase1_tokairokin_to_smbc.sh --go --money-ops-id <UUID>
```

- Playwright 優先（arm64）
- OTP: `app_onetime_pw` → Enter ホールドでユーザー入力
- 将来チャネルがメール／SMS になったら `otp_channel` を差し替え、自動入力へ

---

## 6. 実装 Wave

| Wave | 内容 | 状態 |
|---|---|---|
| **0** | 仕様・R6'・rails[]・OTP／監査骨格・東海労金プロトコル | 完了 |
| **1** | 住信SBIネット→SMBC（本／副）・ことら分割・スマート認証NEO待ち | 完了（ログイン〜確認） |
| **1b** | 最小ユーザー操作＋実行クリック＋証跡 done／resume | 完了 |
| **2** | エアウォレット（手順・初回着金ゲート・SMS OTP） | **完了（アプリタップはユーザー最小）** |
| **3** | 滋賀・京都 IB（東海労金型 Preview→Go） | **骨格完了（creds 待ち）** |
| **4** | ことら分割キューの横断オーケストレーション | **骨格（`jarvis_transfer_queue.py`）** |

---

## 7. 受け入れ（Wave 0）

- [x] 点検／実務 MD 正本化
- [x] R6' 反映（引落仕様・UI 文言）
- [x] `kurashift_transfer_rails.yaml` + OTP／監査モジュール
- [x] money-ops `rails[]` 表示
- [x] 東海労金 Preview／Go／監査フック
- [x] SBIネット Preview／Go（ログイン〜確認。スマート認証NEOは waiting_user）
- [x] SBI 実行クリック＋証跡 done／resume（Wave 1b）

### 最小ユーザー操作モデル（正・Wave1b）

| 行為 | Jarvis | あなた |
|---|---|---|
| money-ops 承認・Terminal Preview/Go | 主 | Go の一声／承認ボタン |
| ログイン ID/PW | 主（env） | 初回だけ env 追記 |
| メール／SMS OTP | **主（自動取得・入力）** | Full Disk／再認証時のみ |
| スマート認証NEO・アプリ承認 | ホールド案内 | **主（一手）** |
| Jarvis が取れない OTP | 入力・続行 | **コードを Terminal に1行**（チャット禁止） |
| 振込金額・宛先入力・照合 | 主 | — |
| 実行クリック | 照合OKなら主（`--execute`） | — |
| 完了証跡 → done | 主 | 「承認した」→ `--resume` 可 |

**原則**: あなたがやるのは「あなたにしかできない所有物・生体」だけ。渡した直後の続行は Jarvis。

### Wave1 補足（ドコモSMTB／旧住信SBI）

- ログイン URL: `https://www.netbk.co.jp/contents/pages/wpl020601/i020601CT/DI02060100`
- Creds: `SBI_NET_USER` / `SBI_NET_LOGIN_PASSWORD`（`SBI_SEC_*` と分離）
- 無料寄せ: ことらおおむね **1件10万**。副口座 161k は **100k+61k**（`--chunk 0/1`）
- 取引実行はスマート認証NEO（アプリ承認）が多い → Terminal で Enter または `--resume`

```bash
# Terminal.app
cd ~/git-repos/215_kamiooya/C1_cursor/browser_automation
./run_phase1_sbi_main_to_smbc.sh --preview
./run_phase1_sbi_main_to_smbc.sh --go --execute --money-ops-id <UUID>
# アプリ承認待ちで止まったら承認 → Enter（同プロセス）または
./run_phase1_sbi_main_to_smbc.sh --resume --execute
./run_phase1_sbi_sub_to_smbc.sh --go --chunk 0 --execute
./run_phase1_sbi_sub_to_smbc.sh --go --chunk 1 --execute
```

### Wave2 エアウォレット

- アプリ中心。Jarvis=手順・初回着金ゲート・SMS OTP・監査／あなた=アプリタップ
- 状態: `.jarvis_state/airwallet_arrival_proof.json`

```bash
cd ~/git-repos/215_kamiooya/C1_cursor/browser_automation
./run_phase1_airwallet_to_smbc.sh --preview
./run_phase1_airwallet_to_smbc.sh --go --money-ops-id <UUID>
# 初回 SMBC 着金確認後
./run_phase1_airwallet_to_smbc.sh --mark-arrival-proven --note 'SMBC着金OK'
# SMS OTP のみ取得（値は stdout・ログに残さない）
./run_phase1_airwallet_to_smbc.sh --fetch-sms-otp
```

### Wave3 滋賀・京都 IB

- Creds: `SHIGA_IB_*` / `KYOTO_IB_*`（jarvis_private）
- 設定: `config/kurashift_ib_shiga.yaml` / `kurashift_ib_kyoto.yaml`

```bash
./run_phase1_shiga_to_smbc.sh --preview
./run_phase1_shiga_to_smbc.sh --go --execute
./run_phase1_kyoto_to_smbc.sh --preview
./run_phase1_kyoto_to_smbc.sh --go --execute
```

---

## 8. 禁止

- 承認のみでの振込実行
- ホワイトリスト外宛先の自動入力
- OTP／口座全文のチャット・監査出力
- 証跡なしの `done`
- Cursor 統合ターミナルでの本番 OTP 待ち（Enter 自動消費）
