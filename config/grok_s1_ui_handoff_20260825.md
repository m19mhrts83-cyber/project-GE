# S1 役割復元 — Grok UI 手作業（2026-08-25）

Jarvis が正本を更新済み。以下を Grok で実施。

## 1. 物件調査（S1）Instructions 再貼り

正本: `config/grok_property_bot_grok_paste.md`  
フェンス内（`# あなたの役割 — 物件調査 Bot` 〜 末尾）を全文差し替え。

要点: 自律探索＋聞くもの自動問合せ／経路3／キャプチャ必須／`## 問合せ` テンプレ。

## 2. 参謀（部長）Instructions 再貼り

正本: `config/grok_sanbo_bot_grok_paste.md`  
本日分＝キューのみ、S1物件探し＝別枠、**§仲介返信パック（18:00）**、愛知→名銀・越野 を含む版。

## 4. 融資相談（S7）— **新規Botは作らない**（既存を更新）

S7 は **不動産・購入フェーズ** チームに既にある。  
→ **Instructions の全文差し替えのみ**（新ポッド／新Bot作成はしない）。

正本: `config/grok_loan_bot_grok_paste.md`  
フェンス内（`# あなたの役割 — 融資相談 Bot` 〜 禁止節の閉じまで）を貼る。

追加で入る要点: 愛知→**名銀・越野将志**のソフト打診準備。銀行送信禁止。

S5・S3 も既存メンバーのまま（新規作成しない）。  
**S3（2026-08-27）**: Instructions を `config/grok_supply_bot_grok_paste.md` で差し替え — 成果物は **Obsidian `☆Real_Estate_Pick`**（`[Grok需給]` メール廃止）。  
参謀・仲介返信ルーティンも同趣旨で再貼り推奨。

## 3. ルーティン（既存チャンネルに追加のみ）

**新チャンネル／新ポッドは作らない。**  
既存の **不動産Dailyチーム**（朝の本日分がある方）にルーティンを1本追加。

| 名前 | 時刻 | 指示の正本 |
|---|---|---|
| `不動産Daily · 本日分` | 9:00（既存） | `config/grok_bucho_routine_本日分.md`（朝Gmail＝調査候補。問合せ返信本線は18:00と明記）を再貼り推奨 |
| `不動産Daily · S1物件探し` | **10:30** | `config/grok_bucho_routine_S1物件探し.md` |
| `不動産Daily · 仲介返信` | **18:00（新規ルーティン）** | `config/grok_bucho_routine_仲介返信.md` の指示フェンス全文 |
| `不動産Daily · Jarvisボックス` | 日中 2〜3時間おき | `config/grok_bucho_routine_Jarvisボックス.md`（Drive outbox 先読み） |
| `不動産Daily · 管理会社返信` | **11:00（推奨）** | `config/grok_bucho_routine_管理会社返信.md`（空室可否判定＋2回目以降は承認後送信） |

購入フェーズ側に 18:00 を二重登録しない（Daily 側が本線）。

チャンネル: **不動産Dailyチーム**。

## 部長へ一言（任意）

```
S1は二本柱。9時はキュー消化のみ。10:30が物件ポータル自律探索。
18:00が仲介返信→S5→S3。S3は Obsidian ☆Real_Estate_Pick へ保存（メールしない）。愛知はS7で名銀・越野さん打診準備（送信はJarvis承認後）。
聞く判定は自動で第一問合せ可（経路3）。キャプチャ必須。[Grok調査]に問合せセクション。
```

## 動作確認（Mac）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_property_mail_match.py --grok-only --dry-run
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_s1_evidence_to_drive.py --poll-recent --dry-run
```

証憑設計: `docs/KURASHIFT_S1問合せ証憑_Drive_20260825.md`

## 残アクション・リマインド

- 一覧: `docs/S1_Grok_残アクション_20260826.md`
- plan（閉じても開ける）: `~/.cursor/plans/s1役割復元_7a105b3b.plan.md`
- 夕方 plan: `~/.cursor/plans/夕方仲介返信デイリー_a2426f31.plan.md`
- Jarvis ルール: `.cursor/rules/jarvis-s1-grok-followup.mdc`

## Jarvis ↔ Grok データ共有（admin Drive）

- フォルダ: `【with Grok bot】`（**部長ボックス**=inbox / **Jarvisボックス**=outbox / shared / archive）
- 設定: `config/kurashift_grok_bridge_folders.yaml`
- 部長 paste に **§データ共有**（先読み・ボックス運用）→ Instructions **再貼り推奨**
- 対外チラシは `【仲介パートナー共有】`（別）

### Grok ルーティン追加（手作業）

| 名前 | 時刻 | 正本 |
|---|---|---|
| `不動産Daily · Jarvisボックス` | 日中 2〜3時間おき（例 11/14/16） | `config/grok_bucho_routine_Jarvisボックス.md` |
| 本日分 / S1 / 仲介返信 | 既存時刻 | 各 MD 先頭に **Jarvisボックス先読み** 追記済み → **再貼り** |

### Mac コマンド

```bash
# Jarvis → 部長
cd ~/git-repos && ~/selenium_env/venv/bin/python scripts/jarvis_bucho_outbox_write.py \
  --title 'S9事前確認2社' --action s9_precheck --priority high \
  --body '北区1・緑区1で --next 2 --balanced'

# 部長 → Jarvis（ポーリング）
~/selenium_env/venv/bin/python scripts/jarvis_bucho_inbox_poll.py
~/selenium_env/venv/bin/python scripts/jarvis_bucho_inbox_poll.py --push
# 処理後
~/selenium_env/venv/bin/python scripts/jarvis_bucho_inbox_poll.py --archive 'YYYY-MM-DD_題名.md'

# launchd（15分）
~/git-repos/launchd/install_bucho_inbox_poll_launchd.sh
```

---

## at home（会員プロフィール）

- ログイン: `ATHOME_LOGIN_EMAIL` + `ATHOME_PASSWORD`（空なら `PORTAL_LOGIN_*`）
- 結論（2026-08-26）: ログイン可。**投資用の年収・棟数プロフィール欄なし**（問合せ都度）
- 再確認（2026-08-27）: headless は Geetest でブロック。PW は共通正本に同期済み
- スナップ正本: `config/grok_s1_inquiry_profile.yaml` の `profile_snapshot`

---

## 追記（2026-08-26）S9 管理会社開拓 · 生存確認

### Grok UI 手作業

1. **新 Bot「管理会社開拓」**（社員 S9）を作成し、`config/grok_mgmt_vendor_bot_grok_paste.md` のフェンス全文を Instructions に貼る
2. **不動産Dailyチーム** に S9 をメンバー追加
3. **部長** Instructions を `config/grok_sanbo_bot_grok_paste.md` で再貼り（S9 ロスター・§管理会社開拓）
4. **本日分** ルーティンを `config/grok_bucho_routine_本日分.md` で再貼り（4b 任意 S9）
5. **修繕業者開拓** Instructions を再貼り（生存確認節）

### Mac

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_mgmt_vendor_list.py --import-xlsx --merge
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_mgmt_vendor_sync.py --apply
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_repair_vendor_list.py --bootstrap
~/selenium_env/venv/bin/python scripts/jarvis_vendor_alive_web_check.py --kind mgmt --apply --limit 30
```

UI: `/realestate/mgmt-vendors` · `/realestate/repair-vendors?filter=alive`
