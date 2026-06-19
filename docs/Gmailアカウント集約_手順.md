# Gmail 3アカウント → admin@livingsupport-matsu.co.jp 集約

## 対象アカウント

| 役割 | アドレス | token |
|---|---|---|
| **集約先（正）** | admin@livingsupport-matsu.co.jp | `token_livingsupport.json` |
| 個人1 | matsuno.estate@gmail.com | `token_estate.json` |
| 個人2 | m19m.hrts83@gmail.com | `token_m19m.json` |

---

## 1. 受信メールの転送（各個人 Gmail で設定）

Gmail API では個人 @gmail.com の転送 ON/OFF は操作できないため、**ブラウザで各アカウントにログインして設定**する。

### 手順（matsuno.estate / m19m.hrts83 それぞれ）

1. Gmail → **設定（歯車）→ すべての設定を表示**
2. **「メール転送と POP/IMAP」** タブ
3. **転送先を追加** → `admin@livingsupport-matsu.co.jp`
4. **admin@ 側**に届く「Gmail の転送の確認」メール内リンクをクリック（承認）
5. 元アカウントに戻り、**「受信メールのコピーを転送する」** を ON  
   - 推奨: **「転送後も Gmail のコピーを受信トレイに残す」**（移行期間中）
   - 安定後: 「転送後にアーカイブ」または「転送後に削除」も可

### 転送確認メールの再取得

```bash
cd ~/git-repos/215_kamiooya/C1_cursor/1b_Cursorマニュアル
GMAIL_TOKEN_PATH=token_livingsupport.json ~/selenium_env/venv/bin/python gmail_consolidation_helper.py --show-forward-links
```

未承認リンクがあればブラウザで開く（`--open-forward-links`）。

---

## 2. 送信履歴を admin@ に残す

Gmail には「他アカウントの Sent を自動で Sent に同期」する標準機能はない。

### A. Jarvis / スクリプト送信（自動・済）

`matsuno.estate@gmail.com` / `m19m.hrts83@gmail.com` から  
`yoritoori_send.py` / `send_mail.py` / `gmail_send_insurance_submit.py` で送る場合、  
**admin@livingsupport-matsu.co.jp へ BCC 控え**する（`gmail_archive_bcc.py`）。

無効化: `GMAIL_ARCHIVE_BCC_DISABLE=1`

### B. Gmail アプリ / ブラウザから手動送信

各個人 Gmail で送信するとき **Bcc に admin@livingsupport-matsu.co.jp を追加**する。  
（Gmail 標準に「常時 BCC」設定はない）

### C. admin@ でラベル整理（推奨）

admin@ でフィルタを作成:

- **条件**: `from:(matsuno.estate@gmail.com OR m19m.hrts83@gmail.com)` かつ `-to:admin@livingsupport-matsu.co.jp`
- **処理**: ラベル「送信控え（個人Gmail）」を付与

BCC 控え・転送メールの見分けがしやすくなる。

### D. 中長期（任意）

送信も admin@ 一本化し、**「別のアドレスから送信」** で旧アドレスを表示名として使う。

---

## 3. 取り込みスクリプト（gmail_to_yoritoori）との関係

転送完了後、パートナーメールは admin@ に届く。

**2026-06 転送承認済み**: `gmail_to_yoritoori.py` の既定は **`token_livingsupport.json`（admin@）のみ**（受信の確認用）。

**Jarvis 送信**（`yoritoori_send.py`）は **相手に届く From を変えない**ため、  
`matsuno.estate@gmail.com` / `m19m.hrts83@gmail.com` から送信（既存スレッドがある方を自動選択、なければ estate 優先）。  
同時に **admin@ へ BCC 控え**が付く。

旧運用（estate + m19m も取り込み走査）: `GMAIL_LEGACY_MULTI_ACCOUNTS=1`

---

## 4. チェックリスト

- [x] matsuno.estate → admin@ 転送確認リンクを承認（2026-06）
- [x] m19m.hrts83 → admin@ 転送確認リンクを承認（2026-06）
- [ ] 各アカウントで「受信メールのコピーを転送する」を ON
- [ ] admin@ でテスト受信（外部から個人 Gmail 宛に送り、admin@ に届くか確認）
- [ ] admin@ に「送信控え（個人Gmail）」ラベル・フィルタ作成
- [ ] 手動送信時は Bcc: admin@ を習慣化
