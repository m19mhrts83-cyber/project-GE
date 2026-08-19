import { DASHBOARD_URL, LOAN_TRACKER_URL } from "@/lib/format";

const NAV = [
  { href: "/", label: "ホーム" },
  { href: "/themes", label: "テーマ" },
  { href: "/money-ops", label: "資金移動" },
  { href: "/portfolio", label: "資産" },
  { href: "/consultations", label: "相談" },
  { href: "/lifeplan", label: "ライフプラン" },
  { href: "/realestate", label: "不動産賃貸" },
  { href: "/notion", label: "Notionタスク" },
  { href: "/mq", label: "MQ会計評価" },
  { href: "/roi", label: "ROI" },
  { href: "/tax", label: "確定申告" },
  { href: "/guide", label: "構成ガイド" },
  { href: "/jobs", label: "ジョブ" },
  { href: "/settings", label: "設定" },
  { href: "/research", label: "リサーチ" },
  { href: "/paper", label: "Lab" },
];

function NavLinks({
  items,
  active,
}: {
  items: typeof NAV;
  active: string;
}) {
  return (
    <>
      {items.map((n) => (
        <a
          key={n.href}
          href={n.href}
          className={`side-link${
            active === n.href ||
            (n.href !== "/" && active.startsWith(`${n.href}/`))
              ? " active"
              : ""
          }`}
        >
          {n.label}
        </a>
      ))}
    </>
  );
}

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
        <div className="side-brand-block">
          <div className="side-brand-mark">
            <svg
              className="side-brand-icon"
              viewBox="0 0 32 32"
              width="22"
              height="22"
              aria-hidden
            >
              <rect width="32" height="32" rx="7" fill="#1f4e79" />
              <path
                fill="#e8762a"
                d="M7.4 6.4h4.55v19.2H7.4zm5.35 8.55 10.85-8.55h-5.6L12.15 13.3zm.05 2.5 5.85 8.15h5.6L12.8 17.05z"
              />
            </svg>
            <div>
              <div className="side-brand">KURASHIFT</div>
              <div className="side-brand-ja">クラシフト</div>
            </div>
          </div>
          <p className="side-tagline">暮らしを整え、資産を動かす</p>
        </div>

        <div className="side-group-title">① 資産運用</div>
        <NavLinks
          active={active}
          items={NAV.filter((n) =>
            ["/", "/themes", "/money-ops", "/portfolio", "/consultations"].includes(
              n.href
            )
          )}
        />

        <div className="side-group-title side-group-title--rule">② 計画・税</div>
        <NavLinks
          active={active}
          items={NAV.filter((n) =>
            ["/lifeplan", "/roi", "/tax"].includes(n.href)
          )}
        />

        <div className="side-group-title side-group-title--rule">③ 事業</div>
        <NavLinks
          active={active}
          items={NAV.filter((n) =>
            ["/realestate", "/notion", "/mq"].includes(n.href)
          )}
        />
        <a
          className="side-link"
          href={LOAN_TRACKER_URL}
          target="_blank"
          rel="noopener noreferrer"
          title="ローン正本（Google: estate）"
        >
          借入残高トラッカー ↗
        </a>

        <div className="side-group-title side-group-title--rule">運用</div>
        <NavLinks
          active={active}
          items={NAV.filter((n) =>
            ["/guide", "/jobs", "/settings", "/research", "/paper"].includes(
              n.href
            )
          )}
        />

        <div className="side-footer">
          <a
            className="side-link"
            href={DASHBOARD_URL}
            target="_blank"
            rel="noopener noreferrer"
          >
            Jarvis ダッシュボード ↗
          </a>
          <div className="meta" style={{ margin: "12px 8px 0" }}>
            {email ?? "—"}
            <form action="/auth/signout" method="post">
              <button type="submit" className="btn" style={{ marginTop: 8 }}>
                ログアウト
              </button>
            </form>
          </div>
        </div>
      </aside>
      <main>{children}</main>
    </div>
  );
}
