# Grok 業者探索 — リスト追記形式

Jarvis が `--merge-append` で取り込む YAML ブロック。Grok 日次探索の出力正本。

## 1日の流れ（Grok 部長 · 本日分）

1. 部長が **本日分** で S2 送信 → S1 調査 → **S2 探索**（Phase 1=3件 · 送信なし）を実行
2. 部長日報メール `[Grok部長] 日報` に **`📎 Jarvis 用（探索追記）`** + YAML `vendors:` を載せる
3. Jarvis: `jarvis_grok_bucho_mail_apply.py --apply`（`--mark` と探索 YAML を同時反映）

手動（メール障害時）:

4. ユーザーが Jarvis に「追記して」→ `--merge-append discovered.yaml`

## 1日の流れ（旧 · 独立 Bot / 手動）

1. Jarvis が `--grok-discovery-prompt` の文面を Bot に渡す（または Bot 説明に固定）
2. Grok が **daily_discovery_limit 件** まで新規会社を調査（**問合せ送信はしない**）
3. 下記 `vendors:` ブロックを返す
4. ユーザーが Jarvis に「追記して」→ `--merge-append discovered.yaml`

## 問合せ送信（別タスク・1日 outreach_limit 件）

1. Jarvis `--next 3` で pending/discovered を表示
2. Grok または手動で Web フォーム送信（`grok_vendor_outreach_format.md` の文面）
3. `--mark {id} --status contacted --note "Web送信 2026-08-22"`
4. 返信が来たら `--status replied`

## 追記ブロック（Grok が返す形式）

```yaml
vendors:
  - name: "株式会社サンプル不動産"
    area: "愛知県岡崎市"
    prefecture: "愛知県"
    city: "岡崎市"
    url: "https://example.co.jp/"
    contact_url: "https://example.co.jp/contact"
    channel: web_form
    contact_email: "info@example.co.jp"
    status: discovered
    source: grok_discovery
    notes: "戸建賃貸の取扱いページあり"
```

## 仲間紹介（優先差し込み · Jarvis）

探索 YAML ではなく **`--peer-add`** が正（デイリーの先頭枠・Phase上限内）:

```bash
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_vendor_list.py --peer-add \
  --name "株式会社サンプル不動産" --area "愛知県名古屋市" \
  --url "https://example.co.jp/" --contact-url "https://example.co.jp/contact" \
  --reason "peer_referral:戸建情報良いと聞いた" --until 2026-09-03
```

手動 YAML で `--merge-append` する場合の例:

```yaml
vendors:
  - name: "株式会社サンプル不動産"
    area: "愛知県名古屋市"
    prefecture: "愛知県"
    city: "名古屋市"
    url: "https://example.co.jp/"
    contact_url: "https://example.co.jp/contact"
    channel: web_form
    status: discovered
    source: peer_referral
    priority: 0
    priority_reason: "peer_referral:戸建情報良いと聞いた"
    priority_until: "2026-09-03"
    notes: "仲間紹介。デイリー先頭枠"
```

## Jarvis 取込

**本線（部長日報メール）**:

```bash
cd ~/git-repos
~/selenium_env/venv/bin/python scripts/jarvis_grok_bucho_mail_apply.py --apply
```

メール本文の `📎 Jarvis 用（探索追記）` 内 YAML を自動 merge。

**手動ファイル**:

```bash
cd ~/git-repos
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_vendor_list.py --merge-append /tmp/grok_vendors.yaml
```

## 重複ルール

- 同一 `name` + `area` → id スラッグでマージ
- 既存 `contacted` / `replied` は Grok 出力で上書きしない（status は Jarvis 側優先）
