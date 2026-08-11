import { DASHBOARD_URL } from "@/lib/format";

const NAV = [
  { href: "/", label: "概要" },
  { href: "/portfolio", label: "資産" },
  { href: "/paper", label: "ペーパー" },
];

export default function Shell({
  active,
  email,
  children,
}: {
  active: string;
  email: string | null;
  children: React.ReactNode;
}) {
  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="side-brand">Trade Desk</div>
        {NAV.map((n) => (
          <a
            key={n.href}
            href={n.href}
            className={`side-link${active === n.href ? " active" : ""}`}
          >
            {n.label}
          </a>
        ))}
        <a
          className="side-link"
          href={DASHBOARD_URL}
          target="_blank"
          rel="noopener noreferrer"
        >
          Jarvis ダッシュボード ↗
        </a>
        <div className="meta" style={{ margin: "18px 8px 0" }}>
          {email ?? "—"}
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
