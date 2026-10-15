# フロー（AIオートメーション／Flowforge 写し）

第2段階（動きの作り込み）の正。編成は第1段階（ビルダー）で先に固める。  
作り方: [`06_社員の作り方_二段階_20261009.md`](../../06_社員の作り方_二段階_20261009.md)

- Flowforge 入口: https://flowforge-259747770348.asia-northeast1.run.app/
- **この体のフロー**: [flow_dCheumorewDolXnfpksSuWKu](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_dCheumorewDolXnfpksSuWKu)
- **Mac 本線**: `scripts/jarvis_vendor_outreach_stall_runner.py`（ノードはこれを呼ぶだけ）

## 型（Day2サンプルと同型）

1. 起動（合図）
2. 取得・確認
3. まとめ
4. Slack へ報告

## 手順メモ

1. **起動**
   - 時間: 朝（morning refresh 相乗り）／夕方 `--evening`
   - 届いたら: inbox poll 後フック（S2 再生成依頼）
   - 失敗見回り: `needs_refill` / stale marks / bridge NG
2. **取得・確認**
   - `kurashift_re_vendor_list.yaml` の pending/discovered 件数と日次枠
   - inbox に再生成依頼があれば archive
3. **まとめ（自律）**
   - 不足時: `--batch-week --grok-kickoff` 相当を `outbox_to_teams/re` へ `action: s2_batch`
   - `vendor_sync` + `sync_meta.vendor_outreach_stall`
   - 対外送信はしない
4. **Slack**
   - 日次: `#report`（件数・要フォロー・UI URL・refill 有無）
   - 障害: `#ops`
   - 要ボスのみ `#consult`

## やらないこと

- 部長ボックスへの「再生成して」再依頼の洪水（自律 refill に寄せる）
- FlowForge 内で YAML を手編集する二重経路
