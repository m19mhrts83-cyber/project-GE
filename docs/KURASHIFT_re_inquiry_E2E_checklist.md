# KURASHIFT — 第一問合せ E2E チェックリスト

更新: 2026-08-22  
前提: `聞く価値: 聞く` の物件が deals に載ったとき（Grok 調査 or 通常メール）

## 1. deals で候補確認

- [ ] KURASHIFT `/realestate/deals` で対象 deal を開く
- [ ] `source=mail_grok` なら Grok 行（方式・土地値・HZ・聞く）を目視
- [ ] `status` が `info` または `viewing`（見送り `passed` ではない）
- [ ] ハザード `除外` でないこと
- [ ] 土地値100% が `聞く` または `保留`

## 2. 第一問合せプレビュー

- [ ] deals 画面「問合せプレビュー」または CLI:

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_inquiry.py --preview-deal-id <uuid>
```

- [ ] From=**estate**（matsuno.estate@gmail.com）
- [ ] 倍率物件なら固定資産税資料依頼が本文に入っている
- [ ] 宛先 `--to` が正しい（不動産会社メール）

## 3. 送信（2段確認）

- [ ] UI: プレビュー確認 → 送信（`re_deal_inquiry_send` ジョブ）
- [ ] または CLI（**ユーザー承認後のみ** `--i-confirm-send`）:

```bash
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_inquiry.py \
  --send-deal-id <uuid> --to 'agent@example.com' --i-confirm-send
```

- [ ] `inquiry_status` → `awaiting_reply`
- [ ] `inquiry_thread_id` が記録されている

## 4. 返信取込

```bash
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_inquiry.py --poll-replies
# 1件だけ: --deal-id <uuid>
```

- [ ] inbound が `kurashift_re_deal_messages` に追記
- [ ] `inquiry_status` → `has_reply`
- [ ] PDF 添付あり → Phase PDF-0（下記）

## 5. PDF 添付（PDF-0）

```bash
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_deal_pdf_fetch.py --deal-id <uuid>
# 問合せスレッド全体: --poll-all
```

- [ ] `.jarvis_state/kurashift_re_deal_attachments/<deal_id>/` に PDF 保存
- [ ] deals UI に「添付 N件」表示
- [ ] 中身解析（PDF-1）は未実装 — 人が PDF を開いて確認

## 6. 通常物件メール取込（地場返信・紹介）

```bash
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_property_mail_match.py --apply
```

- [ ] 新規 deal または既存 deal 更新
- [ ] Gmail 既読は UI「確認した／対象外」経由（取込時は既読にしない）

## 7. 運営相談（任意）

```bash
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_inquiry.py --build-ops-pack --deal-id <uuid>
```

---

## Phase 5 通しテスト（2026-08-22 実施）

自動ランナー `scripts/jarvis_kurashift_grok_e2e_runner.py` で **PASS**（fixture 物件・対外送信は dry-run）。

| 段階 | 結果 |
|---|---|
| Grok レポート → estate | ✅ m19m → matsuno.estate |
| `mail_grok` 取込 | ✅ status=viewing・聞く・倍率・HZ OK |
| 第一問合せプレビュー | ✅ From=estate・倍率ブロック挿入 |
| 送信 | ✅ `--dry-run`（実送信は UI 確認後） |
| 返信 poll | ✅ 0件（fixture 返信は seed） |
| ops パック | ✅ `kurashift_consultations` 作成 |

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_grok_e2e_runner.py
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_grok_e2e_runner.py --cleanup
```

## 本番 E2E（`聞く` 実物件）

Bot1 が `聞く価値: 聞く` の `[Grok調査]` を estate に送ったら、上記チェックリスト §1〜7 を手動で実施。  
2026-08-22 時点の Grok 3件はすべて `見送り`（HZ除外）のため本番問合せは未実施。

## 正本

- テンプレ: `config/kurashift_re_inquiry_template.yaml`
- パイプライン: `docs/KURASHIFT_GrokBot_不動産パイプライン.md`
- 仕様: `docs/KURASHIFT_買い進めJob仕様.md`
