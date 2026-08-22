/**
 * KURASHIFT 構成マップ（運用中に読める正本）
 * docs/Trade_Desk.md / docs/KURASHIFT_検証プラン.md / docs/KURASHIFT_不動産賃貸経営.md と同期
 */

export type MapItem = {
  id: string;
  code: string;
  title: string;
  intent: string;
  implemented: string;
  href?: string;
};

/** 大きな3本 */
export const PILLARS: MapItem[] = [
  {
    id: "p1",
    code: "①",
    title: "資産運用",
    intent: "全体を把握し、提案→相談→承認→実行まで回す",
    implemented: "ホーム・テーマ・資金移動・資産・相談",
    href: "/",
  },
  {
    id: "p2",
    code: "②",
    title: "暮らしの計画と税",
    intent: "年数回のライフプラン更新と個人確定申告のネタ整理",
    implemented: "ライフプラン・ROI・確定申告",
    href: "/lifeplan",
  },
  {
    id: "p3",
    code: "③",
    title: "事業",
    intent: "不動産賃貸とAIなど事業の粗利・運用を見る（MQ会計評価）",
    implemented: "不動産賃貸 ③-A〜D · MQ会計評価",
    href: "/mq",
  },
];

/** ③ 事業の横断メニュー（サイドバーと同じ粒度） */
export const BUSINESS_LANES: MapItem[] = [
  {
    id: "3-re",
    code: "不動産賃貸",
    title: "保有・買い進め",
    intent: "物件条件・CF・千三つ。MQの代わりではない",
    implemented: "③-A〜D（/realestate）",
    href: "/realestate",
  },
  {
    id: "3-mq",
    code: "MQ会計評価",
    title: "粗利構造（直接原価）",
    intent:
      "実績は月次（年額Fは÷12按分）、計画は年次。個人／法人／合算・不動産／AI",
    implemented: "/mq · facts/map/bs · スライサー · 比較",
    href: "/mq",
  },
];

/**
 * ① 資産運用の中身（ホームの「①-C」はこのうち日常回し）
 * A=把握 / B=提案・相談・実行 / C=日常の短い回し
 */
export const ASSET_LANES: MapItem[] = [
  {
    id: "1a",
    code: "①-A",
    title: "全体把握（週次）",
    intent: "Core口座・保険借入・ホーム合計で「いまの状態」を見る",
    implemented:
      "週次スナップ（日曜自動＋Mac起動）／資産ページ／ホーム合計（貸付は合計外）",
    href: "/portfolio",
  },
  {
    id: "1b",
    code: "①-B",
    title: "提案 → 相談 → 承認 → 実行準備",
    intent: "大きな判断だけテーマ化し、確認してから完走アシストへ",
    implemented:
      "テーマ提案・相談確認・承認／資金移動オペ（送金アシストは Preview→Go。無人記帳なし）",
    href: "/themes",
  },
  {
    id: "1c",
    code: "①-C",
    title: "日常の短い回し方",
    intent: "平日はホーム＋週次だけで足りるようにする（毎日LPを触らない）",
    implemented:
      "ホームの①-Cカード／いまやること1行／週次自動。大きな判断だけ①-B",
    href: "/",
  },
];

/**
 * ① サイドバー各メニューの役割（記号①-A/B/C との対応つき）
 * 「この画面は何用？」をガイドで一望する用
 */
export const ASSET_NAV_ITEMS: MapItem[] = [
  {
    id: "nav-home",
    code: "ホーム",
    title: "日常の入口（①-C）",
    intent: "いまやること1行と鮮度。平日はここだけで足りるようにする",
    implemented: "①-Cカード・次アクション・週次失敗の目安",
    href: "/",
  },
  {
    id: "nav-themes",
    code: "テーマ",
    title: "大きな判断の箱（①-B）",
    intent: "提案をテーマ化し、相談→承認まで進める。日次の細かい送金はここではない",
    implemented: "テーマ一覧・相談確認・承認ゲート",
    href: "/themes",
  },
  {
    id: "nav-money",
    code: "資金移動",
    title: "寄せ・送金オペ（①-Bの実行側）",
    intent:
      "カード引落バッファなど資金移動の計画承認とレール進捗。無人記帳はしない",
    implemented:
      "money-ops／レール status／プラン承認→Jarvis実行→最終確認→OTP",
    href: "/money-ops",
  },
  {
    id: "nav-portfolio",
    code: "資産",
    title: "いまの残高把握（①-A）",
    intent: "Core・保険借入など「いまいくらあるか」を見る。毎日いじる画面ではない",
    implemented: "週次スナップ投影・貸付表示（合計外）・利率メモ",
    href: "/portfolio",
  },
  {
    id: "nav-household-bs",
    code: "家計B/S",
    title: "キヨサキ4象限（①-A）",
    intent: "収入/支出/資産/負債の見分け。MQ合算・契約者貸付は二重計上しない",
    implemented: "/household-bs · portfolio/MQ/loan-tracker 合成",
    href: "/household-bs",
  },
  {
    id: "nav-consult",
    code: "相談",
    title: "例外・迷ったときの記録（①-B）",
    intent: "ルールに載らない判断や Jarvis 相談の履歴を残す",
    implemented: "相談スレッド一覧",
    href: "/consultations",
  },
];

/** ② 計画・税の各メニュー */
export const PLAN_TAX_LANES: MapItem[] = [
  {
    id: "2-lifeplan",
    code: "ライフプラン",
    title: "年次の暮らし計画",
    intent: "Numbers 正本の軌道をアプリで眺める・年数回の更新きっかけ",
    implemented: "LPレーン・年末お知らせ。毎日触らない",
    href: "/lifeplan",
  },
  {
    id: "2-roi",
    code: "ROI",
    title: "買い物ごとの評価",
    intent:
      "物件・ペーパーを1購入ずつ振り返る（利回り・返済比率・CoC）。号室現況は③-C、運用進捗は③-A",
    implemented: "ROI 画面",
    href: "/roi",
  },
  {
    id: "2-tax",
    code: "確定申告",
    title: "個人の申告ネタ整理",
    intent: "個人確定申告の下準備（弥生CSV等）。法人は税理士側",
    implemented: "申告レーン・未承認の本登録はしない",
    href: "/tax",
  },
];

/** ③ 不動産賃貸の正式レーン（ナビ「不動産賃貸」配下） */
export const RE_LANES: MapItem[] = [
  {
    id: "3a",
    code: "③-A",
    title: "運用・進捗",
    intent: "今持っている物件が、年間計画に対してどこまで来ているかを見る",
    implemented:
      "CF・DSCR・名義切替・年計画vs YTD・計画補正ジョブ（dry-run→承認）",
    href: "/realestate",
  },
  {
    id: "3b-plan",
    code: "③-B計",
    title: "買い進めプラン（長期）",
    intent: "目標CFから逆算した長期年表と「今狙う」条件を見る",
    implemented: "Excel投影・KPI・年表・Focus・想定vs実績チャート",
    href: "/realestate/buy-plan",
  },
  {
    id: "3b-funnel",
    code: "③-B実",
    title: "千三つ（実行）",
    intent: "候補→内見→買付→融資→購入の実行ファネルを回す",
    implemented:
      "deals一覧・候補タブ・詳細ドロワー・判断履歴・運営経緯取込",
    href: "/realestate/deals",
  },
  {
    id: "3b-vendors",
    code: "③-B開",
    title: "業者開拓ウォッチ",
    intent: "地場リストへの Web 問合せ送信状況を一覧で把握する",
    implemented: "YAML 投影・要フォローフィルタ・deals 紐付け件数",
    href: "/realestate/vendors",
  },
  {
    id: "3c",
    code: "③-C",
    title: "保有物件マスタ",
    intent: "所有物件の基本情報とレントロール。ローンは二重入力しない",
    implemented:
      "物件一覧・郵便番号・鍵番号・RR vs 月返済・借入残高トラッカー投影（読取のみ）",
    href: "/realestate/properties",
  },
  {
    id: "3d",
    code: "③-D",
    title: "融資提出パック",
    intent: "銀行へ出す書類を一覧化し、不足確認・下書きまで（送信はしない）",
    implemented: "商品×名義のチェックリスト・コピー用下書き",
    href: "/realestate/finance-pack",
  },
];

/**
 * サイドバー「運用」— 本線①②③の外側。地図・ジョブ・設定・実験
 */
export const OPS_LANES: MapItem[] = [
  {
    id: "ops-guide",
    code: "構成ガイド",
    title: "このアプリの地図",
    intent:
      "①②③や各メニューの役割を、運用中に自分で読み返す。本線メニューではない",
    implemented: "この画面（/guide）。ナビは「運用」グループ",
    href: "/guide",
  },
  {
    id: "ops-jobs",
    code: "ジョブ",
    title: "Mac への作業キュー",
    intent: "週次取込・再計算などを Mac worker に投げる。判断画面ではない",
    implemented: "ジョブ一覧・キュー状態",
    href: "/jobs",
  },
  {
    id: "ops-settings",
    code: "設定",
    title: "ログイン情報などの入口",
    intent: "秘密は Mac の .env へ。DB にパスワードを残さない",
    implemented: "設定画面 → worker → jarvis_private",
    href: "/settings",
  },
  {
    id: "ops-research",
    code: "リサーチ",
    title: "調べ物の置き場",
    intent: "本線判断の前のメモ・調査。承認フローの代替ではない",
    implemented: "リサーチ画面",
    href: "/research",
  },
  {
    id: "ops-lab",
    code: "Lab",
    title: "実験（本線外）",
    intent: "平均回帰など小額実験。利回り本線・日常寄せには使わない",
    implemented: "paper 画面。後回しでよい",
    href: "/paper",
  },
];

/**
 * 画面に出る短い見出し（レーンではない）
 * 「A,B,K,P,J,C,D」のように見えたときの読み替え用
 */
export const SCREEN_LABELS: MapItem[] = [
  {
    id: "lbl-kpi",
    code: "KPI / K",
    title: "スピード感・指標ブロック",
    intent: "レーン内の数字サマリー。別レーンではない",
    implemented: "③-B計の KPI、③-A の Portfolio KPI など",
    href: "/realestate/buy-plan",
  },
  {
    id: "lbl-portfolio",
    code: "Portfolio / P",
    title: "Portfolio KPI",
    intent: "保有全体の家賃・返済・DSCRを一望する見出し",
    implemented: "③-A 先頭カード",
    href: "/realestate",
  },
  {
    id: "lbl-jobs",
    code: "Jobs / J",
    title: "ジョブ／取込ボタン",
    intent: "Mac worker にキューを投げる操作。レーンではない",
    implemented: "③-B実の Jobs、サイドバー「ジョブ」、買い進め再取込など",
    href: "/jobs",
  },
  {
    id: "lbl-focus",
    code: "Focus",
    title: "今狙う条件",
    intent: "買い進め条件の要約。③-B計／③-B実の中の見出し",
    implemented: "Notion要約＋Excel criteria の補助表示",
    href: "/realestate/buy-plan",
  },
  {
    id: "lbl-brate",
    code: "B-RATE",
    title: "利回り・利率表示",
    intent: "返済判断用の％表示。本線レーンとは別枠バックログ由来",
    implemented: "③-A／③-C の合算金利・正味％、資産の貸付利率",
    href: "/realestate",
  },
];

export const MAP_DOCS = [
  { label: "全体方針", path: "docs/Trade_Desk.md" },
  { label: "検証（①-A/B/C）", path: "docs/KURASHIFT_検証プラン.md" },
  { label: "不動産4レーン", path: "docs/KURASHIFT_不動産賃貸経営.md" },
];
