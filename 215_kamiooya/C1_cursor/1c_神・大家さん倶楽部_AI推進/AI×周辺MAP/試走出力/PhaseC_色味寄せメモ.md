# Phase C 色味寄せ（実行メモ）

- 日付: 2026-07-24
- 工程: 範囲確定 → ピンなしクリーン下地 → **C0**（ベージュ紙面）→ coords 再合成 → Canva
- 入力: `基準_下地_Grandole_クリーン.png`
- C0: `jarvis_shuhen_recompose_decor.py`（彩度下げ＋ベージュ紙色＋軽いスムース）
  → `基準_下地_Grandole_PhaseC.png` → `基準_骨格図_Grandole_PhaseC.png`
- C1（任意）: `10c` 強化プロンプトで Gemini／ChatGPT にピンなし下地＋見本PDF。
  合否 OK なら PhaseC 下地を差し替え、本スクリプトを再実行。
- 合否: 道路が追える／北＝志賀本通・南＝尼ケ坂／焼き込みピンなし
