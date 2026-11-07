/** サイドバー／⌘K 共通のナビ定義 */

export type NavItem = {
  href: string;
  label: string;
  external?: boolean;
  /** components/Icon の名前（Personal Board の線アイコン） */
  icon?: string;
};
export type NavGroup = { title: string; items: NavItem[] };

/** 別アプリ。ダッシュボード内に /trade は置かない */
/** @deprecated 互換エイリアス — KURASHIFT_URL を使う */
export const TRADE_DESK_URL =
  process.env.NEXT_PUBLIC_KURASHIFT_URL ||
  process.env.NEXT_PUBLIC_TRADE_DESK_URL ||
  "https://jarvis-trade-desk.vercel.app";

export const KURASHIFT_URL = TRADE_DESK_URL;

/**
 * B+A: グループ見出し＋分かりやすい名前。
 * ホームはサイドバー最上段に固定（「見る」より前。他項目をホームより上に差し込まない）。
 * お金グループ先頭は Zaim Watch（収支・数値と同列の確認入口）。
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    title: "見る",
    items: [
      { href: "/queue", label: "処理キュー", icon: "queue" },
      { href: "/partner", label: "パートナー", icon: "partner" },
      { href: "/general", label: "その他メール", icon: "mail" },
      { href: "/openchat", label: "神大家オプチャ", icon: "chat" },
      { href: "/situation", label: "状況ウォッチ", icon: "watch" },
      { href: "/archive", label: "処理済み", icon: "archive" },
    ],
  },
  {
    title: "タスク",
    items: [
      { href: "/kamiooya", label: "神大家運営", icon: "users" },
      { href: "/kanji", label: "飲み会幹事", icon: "beer" },
      { href: "/glucon", label: "グルコン報告", icon: "file" },
      { href: "/properties", label: "所有物件", icon: "building" },
      { href: "/kodate", label: "戸建て購入", icon: "house" },
      { href: "/ai-raimo", label: "AI推進・Raimo", icon: "ai" },
      { href: "/kazoku", label: "家族タスク", icon: "heart" },
    ],
  },
  {
    title: "調べる・作る",
    items: [
      { href: "/materials", label: "資料ハブ", icon: "folder" },
      { href: "/kiso-transcripts", label: "基礎講座・文字起こし", icon: "book" },
      { href: "/purchase-compare", label: "購入比較", icon: "cart" },
      { href: "/apps", label: "アプリ・プロンプト集", icon: "grid" },
      { href: "/agent-team", label: "AIエージェントチーム", icon: "bolt" },
      { href: "/notebooklm", label: "NotebookLM", icon: "book" },
    ],
  },
  {
    title: "お金",
    items: [
      { href: "/zaim", label: "Zaim Watch", icon: "wallet" },
      { href: KURASHIFT_URL, label: "KURASHIFT", external: true, icon: "pie" },
      { href: "/etc", label: "ETC", icon: "car" },
      { href: "/vpoint", label: "Vポイント", icon: "gift" },
      { href: "/yen", label: "円動向", icon: "yen" },
      { href: "/rent-step", label: "家賃ステップ", icon: "trend" },
      { href: "/metrics", label: "収支・数値", icon: "chart" },
      { href: "/billing", label: "サブスク・課金", icon: "card" },
    ],
  },
  {
    title: "からだ",
    items: [
      { href: "/quiet-edge", label: "Quiet Edge", icon: "moon" },
      { href: "/performance/work", label: "仕事", icon: "briefcase" },
      { href: "/performance/move", label: "運動", icon: "run" },
    ],
  },
];

export const HOME_NAV: NavItem = { href: "/", label: "ホーム", icon: "home" };

export function flatNavItems(): NavItem[] {
  return [HOME_NAV, ...NAV_GROUPS.flatMap((g) => g.items)];
}
