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
    title: "不動産賃貸経営",
    intent: "保有の運用と、これから買う案件を混ぜずに進める",
    implemented: "不動産 ③-A〜D（ナビ分離）",
    href: "/realestate",
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

/** ③ 不動産の正式レーン（ナビに出るもの） */
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
    implemented: "deals一覧・運営経緯取込・Focus導線（案件通しは運用中）",
    href: "/realestate/deals",
  },
  {
    id: "3c",
    code: "③-C",
    title: "保有物件マスタ",
    intent: "所有物件の基本情報とレントロール。ローンは二重入力しない",
    implemented:
      "物件一覧・RR vs 月返済・借入残高トラッカー投影（読取のみ）",
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
