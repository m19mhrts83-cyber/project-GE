import { DASHBOARD_URL } from "@/lib/format";

const NAV = [
  { href: "/", label: "ホーム" },
  { href: "/themes", label: "テーマ" },
  { href: "/portfolio", label: "資産" },
  { href: "/lifeplan", label: "ライフプラン" },
  { href: "/roi", label: "ROI" },
  { href: "/tax", label: "個人申告" },
  { href: "/consultations", label: "相談" },
  { href: "/jobs", label: "ジョブ" },
  { href: "/settings", label: "設定" },
  { href: "/research", label: "リサーチ" },
  { href: "/paper", label: "Lab" },
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
        <div className="side-brand">KURASHIFT</div>
        <div className="meta" style={{ margin: "0 8px 14px", fontSize: 12 }}>
          暮らしを整え、資産を動かす
        </div>
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
