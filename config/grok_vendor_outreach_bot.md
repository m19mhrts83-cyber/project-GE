# Grok 業者開拓 Bot — 作業説明（Phase 4 正本）

**status**: `grok_vendor_outreach_format.md` が **approved** のときのみ送信可。  
**別Bot**: 物件調査（`[Grok調査]` → estate）は `config/grok_property_report_format.md`

## 毎日の流れ（1日3件）

1. Mac で次の3社を取得（ユーザーまたは Jarvis が実行）:

```bash
cd ~/git-repos
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_vendor_list.py --next 3
```

2. 出力された各社について:
   - `contact_url` または `url` の Web 問合せフォームを開く
   - **本文**: `config/grok_vendor_outreach_format.md` の標準文面（list_region でエリア差替）
   - **返信先**: matsuno.estate@gmail.com（必須）
   - **From/署名**: 松野真治 / matsuno.estate@gmail.com

3. 送信後、Mac で記録:

```bash
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_vendor_list.py \
  --mark {id} --status contacted --note "個人Web送信(estate) YYYY-MM-DD"
```

4. **対外送信前**: ユーザーがフォーム最終画面を確認（Jarvis は自動送信しない）

## 禁止

- `status: draft` の文面で送らない（現在は approved）
- 利回り%をフォームの目立つ欄に大書きしない
- 329社一括送信
- 具体物件への第一問合せ（それは KURASHIFT deals 経由・別テンプレ）

## 新規探索（問合せは送らない）

```bash
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_vendor_list.py --grok-discovery-prompt
# → YAML 追記 → --merge-append
```

## リスト概要

```bash
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_vendor_list.py --summary
```
