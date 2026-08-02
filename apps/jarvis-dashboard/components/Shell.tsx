import { createClient } from "@/lib/supabase/server";

type NavItem = { href: string; label: string };
type NavGroup = { title: string; items: NavItem[] };

/** B+A: グループ見出し＋分かりやすい名前。ホームは「見る」の上に独立配置 */
const NAV_GROUPS: NavGroup[] = [
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
];

export default async function Shell({
  children,
  active,
}: {
  children: React.ReactNode;
  active: string;
}) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const homeActive = active === "/";

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="side-brand">Jarvis</div>
        <a
          href="/"
          className={`side-link side-link-home${homeActive ? " active" : ""}`}
        >
          ホーム
        </a>
        {NAV_GROUPS.map((g) => (
          <div key={g.title} className="side-group">
            <div className="side-group-title">{g.title}</div>
            {g.items.map((n) => (
              <a
                key={n.href}
                href={n.href}
                className={`side-link${
                  active === n.href ||
                  (n.href !== "/" && active.startsWith(n.href))
                    ? " active"
                    : ""
                }`}
              >
                {n.label}
              </a>
            ))}
          </div>
        ))}
        <div className="side-note">
          {user?.email ?? "—"}
          <br />
          <form action="/auth/signout" method="post">
            <button type="submit" className="btn" style={{ marginTop: 8 }}>
              ログアウト
            </button>
          </form>
        </div>
      </aside>
      <main>{children}</main>
    </div>
  );
}
