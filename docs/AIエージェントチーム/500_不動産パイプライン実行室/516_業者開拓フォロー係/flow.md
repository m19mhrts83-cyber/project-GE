# フロー（AIオートメーション／Flowforge 写し）

第2段階（動きの作り込み）の正。編成は第1段階（ビルダー）で先に固める。  
作り方: [`06_社員の作り方_二段階_20261009.md`](../../06_社員の作り方_二段階_20261009.md)

- Flowforge 入口: https://flowforge-259747770348.asia-northeast1.run.app/
- **この体のフロー**: [業者開拓 見守り（516／GHA16:00）](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_dCheumorewDolXnfpksSuWKu)（設計図。実行エンジンではない）
- **役割分担（B'）**: 実行=Grok（S2/S4/S9）／見守り=516（検知・報告）。二重実行しない
- **見守り本線**: GHA `kurashift-vendor-outreach-stall.yml`（平日16:00 JST・`--skip-refill`）
- **補給保険（Mac）**: `scripts/jarvis_vendor_outreach_stall_runner.py --lane all`（Drive outbox）

## 型（Day2サンプルと同型）

1. 起動（合図）
2. 取得・確認
3. まとめ
4. Slack へ報告

## 手順メモ

1. **起動**
   - 時間: **GHA 平日16:00**（見守り・Slack／sync_meta）／Mac 朝 soft-fail・夕方 `--evening`（補給＋日次）
   - 届いたら: inbox poll 後フック（S2/S4/S9 再生成依頼）
   - 失敗見回り: `needs_refill` / stale marks / bridge NG
2. **取得・確認**
   - S2/S4/S9 各 YAML の pending/discovered と日次枠
   - GHA は Secrets（gzip|B64）から YAML materialize。inbox 消化は Mac
3. **まとめ**
   - **GHA**: `--skip-refill`（Drive 書かない）。sync_meta＋Slack のみ
   - **Mac**: 不足時 outbox_to_teams/re:
     - S2 → `action: s2_batch`
     - S4 → `action: s4_queue`
     - S9 → `action: s9_precheck`
   - 対外送信はしない（定型送信は Grok）
4. **Slack**
   - 日次: `#report`（レーン横断・要フォロー・UI URL・refill 有無）
   - 障害: `#ops`
   - 要ボスのみ `#consult`

## やらないこと

- FlowForge を実行エンジンにする（設計図・ラベル用）
- GHA から Drive outbox を書く
- 部長ボックスへの「再生成して」再依頼の洪水（Mac 自律 refill に寄せる）
- FlowForge 内で YAML を手編集する二重経路
