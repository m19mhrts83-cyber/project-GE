# Grok ↔ Jarvis — JarvisBox フォーク原則（正本）

**更新**: 2026-09-21  
**Drive**: admin `【with Grok bot】/` · 設定: `config/kurashift_grok_bridge_folders.yaml`

## フォーク（基本形）

| 側 | 役割 | 本体 |
|---|---|---|
| **Grok** | 整理 · 委譲 · 助言 · 文案 · ルーティン実行 · 日報メール | Grok Bot / チャンネル |
| **Jarvis** | Mac 実行 · 取込 · DB · 送信承認 · 秘密 · launchd | Cursor / Mac |

**松野がチャットをコピペしなくてよい** — 運用上のやり取りは **Drive JarvisBox 必須**。

## 必ず JarvisBox 経由（正）

| 向き | フォルダ | 書く人 | 読む人 |
|---|---|---|---|
| Jarvis → Grok | `20_outbox_to_grok/`（`target:` 付） | Jarvis | ホークアイ → 各 `outbox_to_teams/*/` |
| Jarvis → 部長／統括 | `outbox_to_teams/{re,resource,…}/` | Jarvis（`--target`） | 該当 Bot ルーティン先読み |
| Grok → Jarvis | `10_inbox_from_grok/` | **部長 · 各統括**（完了・依頼・メモ） | Jarvis poll（15分） |
| 済 | `90_archive/` | 処理後 | 参照 |

`30_shared_working/` は **手順 · B1 正本**。日常キューは **inbox / outbox / team フォルダ**。

## アドバイザー週次材料パック（SB · 2026-09〜）

| 項目 | 正 |
|---|---|
| きっかけ | コーチング部長 日曜19:00 → Cloud `POST /api/advisor-weekly-pack` |
| 秘密 | `ADVISOR_WEEKLY_PACK_SECRET`（Action）＋サーバー側 `GSK_API_KEY`。**Grok に GSK を渡さない** |
| 材料の正 | API 応答 `markdown`（Mac スリープ可）。Drive outbox は後続・Macフォールバック |
| Journal | **理解の正本**（全文ログではない）。アドバイザーは「Journalに無い重要」をメンション |
| 仕様 | `docs/Grok_アドバイザー週次材料パック_仕様_20260926.md` |

## Grok チャンネル（履歴 · キューと別）

| チャンネル | 用途 |
|---|---|
| **参謀室** | 首脳会議（統括メンバー · 日曜20:00 `@`） |
| **Jarvisボックス** | Jarvis↔ホークの**作業履歴**（ホークのみ · 天気は入れない） |

Drive `20_outbox_to_grok/` はこれまでどおり **仕事キュー**。チャンネルと同名だが混ぜない。

**投稿の識別（Grok ch 本文 · 確定 2026-08-30）**

| 誰が書く | 印 |
|---|---|
| 松野直筆 | **印なし** |
| Jarvis（CDP・手貼り含む） | 先頭 **`[Jarvis]`** |
| Drive MD（`action:`） | 対象外 |

チャンネル **Jarvisボックス** も同じ（履歴でも印を付ける。使い分けしない）。

## Grok Bot Instructions に載せる一文（統括・部長）

```
## Jarvis への共有（必須 · フォーク）

- Mac 実行・取込・送信・秘密は **Jarvis**。あなたは Grok 内で完結させ、結果を Drive へ書く。
- Jarvis に伝えること（完了 · 依頼 · 長メモ）は **必ず** admin Drive
  `【with Grok bot】/10_inbox_from_grok/` に `YYYY-MM-DD_題名.md`。
- 先頭 YAML 推奨: `action:` / `priority:` / `target: jarvis`
- **本文は改行を残す**（1行に潰さない）。`# 見出し` · 箇条書き · 番号リスト · コードフェンス。ダッシュボード状況ウォッチがそのまま描画する
- **ホーク Notion**: `action: notion_tasks` → Jarvis が `jarvis_hawk_notion_tasks_apply.py --apply`（移行期）
- **ホーク／部長 Todoist（本線）**: `action: todoist_tasks` → Mac が自動 apply（`jarvis_bucho_inbox_poll`）。`summary`/`links` → コメントの Markdown ハイパーリンク
- **要ボス／要Jarvis連携**は必ず Todoist ラベル付き起票（Drive メモだけでは漏れ扱い）
- Drive `20_outbox` 空は正常。ホーク判断は Todoist `要ホーク`
- **二重起票禁止**: 同 L-id／同趣旨タイトルがあれば create せず更新・列移動・コメントのみ（Jarvis 正本: `docs/Todoist_タスク正本_設計_20260921.md`「二重起票防止」）
- **Jarvis 分身 Gmail**（Todoist コメント通知の入口）: アドレスは `JARVIS_TODOIST_EMAIL`（Jarvis のみログイン・API）。**Grok はログインしない**（秘密・トークン禁止）
- **共有メンバー（見える側）**: **ホークアイ（参謀）** · **不動産賃貸部長**（ほか統括はホーク経由）。Jarvis が要約を Drive outbox（`target: hawk` / `re`）へ書く／Todoist コメントで返す
- **松野にチャット全文コピーを求めない**（JarvisBox が正本）。
```

サブ Bot（コーチ・アドバイザー）は **統括 Bot 経由**でよい。統括が inbox にまとめる。

## Jarvis分身Gmail（誰が「見える」か）

Todoist「通知全員」→ **jarvis@**（`JARVIS_TODOIST_EMAIL`）に通知メール。**読むのは Jarvis のみ**（Gmail API）。

| メンバー | 見えるか | 経路 |
|---|---|---|
| **Jarvis** | 本線 | Gmail API · Todoist API |
| **ホークアイ（参謀）** | **共有** | Drive outbox `target: hawk` · 参謀室／Jarvisボックス · Todoist `要ホーク` |
| **不動産賃貸部長** | **共有** | `outbox_to_teams/re/` · Todoist |
| ほか統括・コーチ | ホーク経由 | jarvis@ ログイン・API は渡さない |

UI 差替手順: Drive `30_shared_working/2026-09-21_Jarvis分身Gmail_フォーク共有/00_松野向け_Grok_UI手順.md`

## Jarvis の動作（必須）

1. Grok へ依頼・結果共有 → `jarvis_bucho_outbox_write.py --target …`（チャットだけで終わらない）
2. Grok inbox 未処理 → `jarvis_bucho_inbox_poll.py`（パートナー確認ついで可）
3. Instructions 更新 → git `config/grok_*_paste.md` → Drive `B1_*_全文.txt` 再生成を案内
4. jarvis@ の Todoist 通知を処置したら、必要に応じ **ホーク／部長へ Drive 要約**（`target: hawk` / `re`）

## 例外（JarvisBox 以外の正本）

| 種類 | 正本 |
|---|---|
| `[Grok部長]` 日報 / 夕方 / 週次 | **estate Gmail** → Jarvis 取込 |
| `[Grok調査]` 等社員成果 | **estate Gmail** |
| 急ぎ Jarvis 依頼（任意） | estate 件名 `[Jarvis依頼] …` |
| 天気 ch 直投のみ（本人DM・通知不要） | `outbox_to_teams/weather/` → 天気Bot → ch「天気お知らせ」。松野は ch を開いて確認 |

## 関連

- 索引: `config/grok_org_handoff_index.md`
- ホーク L2: `config/grok_hawk_routine_Jarvisボックス.md`
- Jarvis ルール: `.cursor/rules/jarvis-grok-jarvisbox-fork.mdc`
