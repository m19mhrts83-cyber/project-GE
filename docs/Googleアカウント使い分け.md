# Google アカウント使い分け

Jarvis 向けルール正本: `.cursor/rules/jarvis-google-accounts.mdc`  
Gmail 受信集約の手順: [Gmailアカウント集約_手順.md](./Gmailアカウント集約_手順.md)

## 3アカウント

| 略称 | アドレス | 役割 |
|---|---|---|
| **m19m** | `m19m.hrts83@gmail.com` | 開発ベースライン（GCP / GitHub / Gemini API） |
| **admin** | `admin@livingsupport-matsu.co.jp` | Workspace・Drive 正本・Gmail 受信集約・**カレンダー予定** |
| **estate** | `matsuno.estate@gmail.com` | 不動産・**神大家関連**・対外 From（パートナー送信既定） |

## 推奨構成（結論）

**全面移行しない。役割分担を固定する。**

| 領域 | 置き場所 |
|---|---|
| GCP OAuth・API・Maps・Gemini API・GitHub | **m19m** |
| Drive（リビングサポート・車両等）・Gmail 取込・カレンダー予定・Workspace Gemini | **admin** |
| パートナー送信 From・LINE 公式エクスポート・**神大家運営の Google フォルダ** | **estate**（送信は既存スレッドが m19m なら m19m） |

### 特記: 神・大家さん

運営とのやり取り・共有 Google フォルダは **estate（`matsuno.estate@gmail.com`）**。ローカル OneDrive `215` と Google 側ログインを混同しない。

### Workspace に寄せて得しやすいこと

- 対話系 Gemini / 社内共有を admin で使い、個人枠の消費を減らす
- Drive・権限を用途ごとに admin / estate で分けると取り違え事故を減らす

### 寄せない方がよいこと

- 「開発を Workspace に移せば API が安くなる」→ **否**（課金は GCP プロジェクト側）
- estate の対外 From や神大家 Google を admin に統合 → 相手スレッド・共有権限が壊れやすい

## token 早見

`215_kamiooya/C1_cursor/1b_Cursorマニュアル/`

| 用途 | ファイル |
|---|---|
| 取込（admin） | `token_livingsupport.json` |
| 送信・LINE export（estate） | `token_estate.json` |
| 個人（m19m） | `token_m19m.json` |
| カレンダー（admin） | `token_calendar.json`（`--login-hint admin@livingsupport-matsu.co.jp`） |

## フィードバック

- **迷ったら確認** → 答えをルールに蓄積 → 次回は確認なしで選べる、が正運用。
- うまくいかなかった事例も、Jarvis と一緒に `jarvis-google-accounts.mdc` の対応表・教訓ログへ反映する。
