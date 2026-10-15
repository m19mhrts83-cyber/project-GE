# 神大家1.基礎 — 文字起こしギャップと対応（2026-10-16）

コース: https://westudy.co.jp/course/kami-ooyasan-club  
集計: 全 **85** レッスン / VTT成功 **63** / 字幕不可→説明文フォールバック **22** / 未取得 **0**

## 課題（なぜ字幕が取れないか）

| 類型 | 内容 | 該当の目安 |
|---|---|---|
| A. Vimeo はあるが text track なし | 自動字幕がオフ／未生成。`<track>` も config `text_tracks` も空 | STEP2-1、補足・トラブル系、保険・Q&A 動画など多数 |
| B. 動画 iframe なし | スライド・PDF・外部リンク中心のページ | pop_board、consultant、金融機関セミナー一部 |
| C. 説明文もほぼ空 | ページ本文が薄い | kokoronokabe、zenku_taisaku、youtube2 等 |

## 対応策

| # | 策 | 実行状況 |
|---|---|---|
| 1 | Vimeo 自動字幕の再試行（track 待機・日本語優先・config API） | **実施済**（改善後も上記22は0） |
| 2 | レッスン説明文を MD にフォールバック保存 | **実施済**（22件） |
| 3 | 今村さん字幕（SRT等）を `imamura/inbox` → 確認後 canonical → ボット | **待ち**（本線の正） |
| 4 | Notta 等で動画ファイルから起こす（運営手順あり） | 動画配布があるもの向け。A類型 |
| 5 | スライド／セミナーは資料PDFを別ソース化 | B類型。文字起こし対象外として整理可 |

## 字幕0の slug 一覧

`kamiooya-kiso-step2_1`, `step3_2`, `step5-5`, `approach_chintaiheiyou`, `kokoronokabe`, `houtekikashi`, `qa_kaikata`, `_hosoku_trouble`, `yoheki_taisyo`, `zenku_taisaku`, `youtube2`, `pop_board`, `baikyaku`, `sisannseiri`, `qa_baikyaku`, `keiyakufutekigo_taisyo`, `kasaihoken_kisho`, `consultant`, `kasaihoken_henkou_youken`, `service_form`, `seminar-lf`, `seminar-orix`
