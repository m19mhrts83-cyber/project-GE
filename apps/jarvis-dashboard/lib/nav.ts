/** サイドバー／⌘K 共通のナビ定義 */

export type NavItem = { href: string; label: string };
export type NavGroup = { title: string; items: NavItem[] };

/**
 * B+A: グループ見出し＋分かりやすい名前。
 * ホームはサイドバー最上段に固定（「見る」より前。他項目をホームより上に差し込まない）。
 * お金グループ先頭は Zaim Watch（収支・数値と同列の確認入口）。
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    title: "見る",
    items: [
      { href: "/partner", label: "パートナー" },
      { href: "/general", label: "その他メール" },
      { href: "/openchat", label: "神大家オプチャ" },
      { href: "/situation", label: "状況ウォッチ" },
      { href: "/archive", label: "処理済み" },
    ],
  },
  {
    title: "タスク",
    items: [
      { href: "/kamiooya", label: "神大家運営" },
      { href: "/properties", label: "所有物件" },
      { href: "/kodate", label: "戸建て購入" },
      { href: "/ai-raimo", label: "AI推進・Raimo" },
      { href: "/kazoku", label: "家族タスク" },
    ],
  },
  {
    title: "調べる・作る",
    items: [
      { href: "/materials", label: "資料ハブ" },
      { href: "/apps", label: "アプリ・プロンプト集" },
      { href: "/notebooklm", label: "NotebookLM" },
    ],
  },
  {
    title: "お金",
    items: [
      { href: "/zaim", label: "Zaim Watch" },
      { href: "/etc", label: "ETC" },
      { href: "/vpoint", label: "Vポイント" },
      { href: "/rent-step", label: "家賃ステップ" },
      { href: "/metrics", label: "収支・数値" },
      { href: "/billing", label: "サブスク・課金" },
    ],
  },
  {
    title: "からだ",
    items: [{ href: "/quiet-edge", label: "Quiet Edge" }],
  },
];

export const HOME_NAV: NavItem = { href: "/", label: "ホーム" };

export function flatNavItems(): NavItem[] {
  return [HOME_NAV, ...NAV_GROUPS.flatMap((g) => g.items)];
}
