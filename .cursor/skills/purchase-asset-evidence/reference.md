# purchase-asset-evidence — 詳細・自動化

## 関連パス

| 役割 | パス |
|---|---|
| 借入 JSON | OneDrive `240_融資/loan_tracker_export/loans.json` |
| ローン同期 | `scripts/jarvis_kurashift_loan_tracker_sync.py` |
| オーケストレータ | `scripts/jarvis_purchase_asset_evidence.py` |
| アクサ | `scripts/jarvis_axa_balance.py` |
| SBI投信 | `scripts/jarvis_sbi_index_balance.py` |
| Bloomo（MF） | `scripts/jarvis_mf_bloomo_balance.py` |
| SMTB／NEOBANK | `scripts/jarvis_sbi_net_transfer.py`（ログイン流用） |
| PayPay | `scripts/jarvis_paypay_bank_transfer.py`（ログイン流用） |
| あかつき／ソニー等 | `215_kamiooya/C1_cursor/finance/` |
| 滋賀IB設定 | `config/kurashift_ib_shiga.yaml` |
| 京都IB設定 | `config/kurashift_ib_kyoto.yaml` |
| 秘密 | `.env.jarvis_private` のみ |

## 2026-11 P424 で分かった詰まり

| 口座 | 結果 | 次の改善 |
|---|---|---|
| 借入トラッカーUI | Googleパスキーで自動困難 | `loans.json`→PNG を本線に（鮮度は sync で保つ） |
| Olive／SMBC銀行 | `VPASS_*` はあるが**銀行ログインID無し** | env に `SMBC_DIRECT_*` 等を足すかスキップ継続 |
| 名古屋銀行 | 口座メモのみ・IB無し | スキップ |
| 京都銀行 | 会員番号で B33（契約なし） | 正しい会員番号／別契約パスを確認 |
| 三菱UFJ真治 | あんしんパス（スマホQR） | 人手 or セッション保存の検討 |
| ソニー生命 | お客さまWEB停止あり | 直近debug PNG＋日付をファイル名に |
| プルデンシャル | OTP可・一覧遷移がモーダルで不安定 | マイページ成功 or env評価メモ画像 |
| SBI証券サイト | セレクタ／ログイン不安定 | Zaim連携の保有HTML→PNG（出所明記） |

## 下書きテンプレ（スクショ同梱）

```
件名: （スレッドに合わせる）

〇〇様

お世話になっております。
松野です。

ご案内の必要書類について、以下を添付にてお送りします。

【税務関係】（ある場合）
・…

【借入残債】
・借入残高トラッカー（残高一覧画面）

【金融資産（スクショ）】
・銀行口座残高（取得できた口座名を列挙）
・生命保険の評価・積立（…）
・証券・投信等（SBI／Bloomo 等）
・外国債券（あかつき証券）

※取得できなかった口座はログイン制約のため省略している旨を1行。
※サイト停止等で日付が古いスクショは日付を明記。

ご確認のほど、よろしくお願いいたします。

松野
```

## 自動化（ロードマップ）

### いま（Phase 1・済）

- Cursor スキル＋`/purchase-asset-evidence`
- `scripts/jarvis_purchase_asset_evidence.py`（`--out`／`--only`）
- 既存残高スクリプトの headed＋debug PNG 流用

### Phase 2（次に足すと効く）

1. **口座レジストリ YAML**（`config/purchase_asset_evidence_accounts.yaml`）  
   id／提出ファイル名／script／envキー／skip理由の正本
2. **ローン JSON 鮮度チェック**（`updatedAt` が N 日超なら sync を促す）
3. **提出用／skip の振り分けをスクリプト内で固定**
4. **パートナー指定** `--partner P424` で OneDrive パス解決＋下書き追記オプション（`--draft-append` は dry-run 既定）

### Phase 3（任意）

- セッション保存（Playwright storage）で再ログイン回数を減らす（銀行・保険ごと）
- MUFGあんしんパス／Olive銀行IDは人手ゲートを明示した半自動
- 収集サマリを Slack `#ops` に短報（秘密なし）

### やらない自動化

- 了承なしのメール送信
- Zaim残高の偽造スクショを提出用に生成
- 秘密の Git コミット
