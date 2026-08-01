# 単独Web検証 — 仕様（Phase 0）

- **案件**: 神・大家さん倶楽部 AI推進・周辺MAP
- **作成日**: 2026-08-01
- **入口**: 単独Web（Raimo／MyPromptをUIに出さない）
- **利用者**: 神大家メンバー（検証パイロット）
- **完了定義**: Canva前まで。**C0（ベージュ紙面）本線自動**、**C1は任意ボタン＋人が合否**

関連: `00_課題メモ` / `10` / `10c` / `shuhen-auto.html`

---

## 入力（フォーム）

| フィールド | 必須 | 既定 | 由来 |
|---|---|---|---|
| `property_name` 物件名 | ○ | — | `01` `{物件名}` |
| `address` 住所 | ○ | — | `01` `{住所}` |
| `target` ターゲット | — | `単身〜カップル想定の一般向け` | `01` `{ターゲット}` |
| `facility_count` 施設数目安 | — | `15` | `01` `{施設数の目安}` |

---

## 出力契約（JSON）

```json
{
  "job_id": "uuid",
  "property_name": "string",
  "address": "string",
  "area_blurb": "string",
  "access": [{"name": "string", "kind": "string", "walk": "string", "note": "string"}],
  "facilities": [
    {
      "id": "P1",
      "query": "検索クエリ",
      "name": "表示名",
      "blurb": "一言",
      "category": "駅|スーパー|…",
      "lat": 35.0,
      "lng": 136.0,
      "ok": true,
      "needs_check": true
    }
  ],
  "property_pin": {"id": "P0", "lat": 0, "lng": 0, "name": "物件名", "ok": true},
  "places_list_text": "P1 | query | name\\n…",
  "images": {
    "c0_base_png_b64": "…",
    "c0_with_pins_png_b64": "…"
  },
  "c1": {"status": "idle|ready|failed|skipped", "png_b64": null, "message": ""},
  "errors": [],
  "steps": [{"id": "wash|verify|places|static|c0", "ok": true, "detail": ""}]
}
```

地図アプリ互換テキスト: `places_list_text` は既存 `shuhen-map` の「ID | 検索クエリ | 表示名」形式。

---

## 成功基準（Grandole志賀本通）

人手コピペなしで次が揃うこと:

1. 施設リストが 1 件以上（駅を含む）
2. 番号ピン地図（ブラウザ）または C0 付き骨格画像にピンが載る
3. **C0色付き下地 PNG** がダウンロードできる
4. C1 は押さなくても検証完了扱い

入力例:

- 物件名: `Grandole志賀本通`
- 住所: `愛知県名古屋市北区杉栄町`

---

## 実行

```bash
cd ~/git-repos
set -a && source .env.jarvis_private && set +a
# 8765 が他プロセスで埋まっている場合:
# export SHUHEN_AUTO_PORT=8770
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/shuhen_auto_server.py
# → http://127.0.0.1:8765/shuhen-auto.html （または SHUHEN_AUTO_PORT）
```

要: `GEMINI_API_KEY` / `GOOGLE_MAPS_API_KEY`（Static・Places・Geocoding）  
任意: `GEMINI_IMAGE_MODEL`（既定 `gemini-2.5-flash-image`）、`SHUHEN_AUTO_TOKEN`、`SHUHEN_AUTO_RATE_PER_HOUR`
