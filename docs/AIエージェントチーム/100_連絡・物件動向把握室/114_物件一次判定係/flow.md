# フロー — 物件一次判定係（114）

1. **起動** — Grok 取込後／手動 `--scan`
2. **取得** — deals の score・聞く価値・inquiry_action・inquiry_status・To
3. **振分** — A / B / C（正本 `23_物件進行ゲート_…`）
4. **報告** — B=`#consult`、A/C=`#report`
5. **B の後続** — 松野 Yes/No → 511（本係は送らない）
