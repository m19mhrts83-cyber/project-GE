# Quiet Edge — Health ソース引き継ぎ（2026-08-08）

ローカル書き出しから確認した内容。**Git に Health 生データは入れない。**

## 書き出しパス（Mac）

```
/Users/matsunomasaharu2/Downloads/apple_health_export/
  export.xml          … 本体（約1.3GB・Record 正本）
  export_cda.xml      … CDA（臨床文書寄り・Quiet Edge 用途ではほぼ使わない）
  electrocardiograms/
  workout-routes/
```

Jarvis が参照するとき:

```bash
# ソース名の件数
rg -o 'sourceName="[^"]+"' ~/Downloads/apple_health_export/export.xml | sort | uniq -c | sort -rn | head -20
```

## ソース実態（export.xml）

| sourceName | 件数目安 | 役割 |
|---|---|---|
| 松野真治さんのApple Watch | 約258万 | 圧倒的多数（心拍・呼吸・SpO2・睡眠など） |
| iPhone (5) | 約45万 | 歩数等 |
| AutoSleep | 約4400 | **睡眠のみ** |
| **MemoHealth** | 約2618 | **リング（OraMemo）** ※source 名は OraMemo ではなく MemoHealth |
| ヘルスケア / 時計 他 | 少数 | — |

### Quiet Edge 対象指標 × ソース

| 指標 | Watch | MemoHealth（リング） | 備考 |
|---|---|---|---|
| SpO2 | 多数 | あり（177件） | 混在。絞らないと Watch が勝ちやすい |
| 睡眠 | 多数 | あり（717） | AutoSleep も多い |
| 呼吸数 | Watchのみ | なし | リング第一にできない |
| HRV | 多数 | あり（570） | 混在 |
| 安静時心拍 | Watchのみ | なし | Watch でよい |

MemoHealth の直近サンプル例: 2026-08-05 前後まであり（書き出し時点）。

## ショートカット現状（このチャットで確立）

- 名前: `Quiet Edge Health`
- 自動化: **毎日 11:30・すぐに実行**（尋ねる OFF）
- 送信先: `POST …/api/quiet-edge/health/ingest`
- 送信済み確認: `spo2` + `respiratory_rate`（`ok` / upserted）
- 次の作業: **リング優先**（下記）

## リング優先への変更手順（実施中）

詳細正本: `docs/Quiet_Edge_ヘルスケアショートカット手順.md`「リング優先の設定手順」

1. SpO2 検索にフィルタ **ソース = MemoHealth**（すべて）  
2. POST を2つに分割  
   - A: `source=oramemo` + `spo2`（後で hrv / sleep_hours）  
   - B: `source=watch` + `respiratory_rate`（後で resting_hr）  
3. 再生して両方 `ok: true`  
4. Quiet Edge で同日の SpO2 がリング由来として見えることを確認  

## Quiet Edge 側の優先ルール

表示・日付ジョイン時: **`oramemo` → `watch` → `health_unknown`**  
（`apps/jarvis-dashboard/lib/quietEdgeContext.ts` の `preferVitalByDay`）

## 推奨運用

1. SpO2 / 睡眠 / HRV … Shortcuts で **データソース＝MemoHealth** ＋ `source: oramemo`  
2. 呼吸数 / 安静時心拍 … `source: watch`  
3. 生の `export.xml` は Downloads に置き、必要時だけ Jarvis が `rg` で集計（リポジトリにコピーしない）

## チャット引き継ぎの言い方

新しい Cursor チャットで:

> Quiet Edge Health の続き。`docs/Quiet_Edge_Healthソース引き継ぎ.md` を読んでから進めて。

このファイルを @ 指定してもよい。

関連: `docs/Quiet_Edge_運用.md` / `docs/Quiet_Edge_ヘルスケアショートカット手順.md`
