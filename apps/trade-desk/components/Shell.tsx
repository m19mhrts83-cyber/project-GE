import TermGlossary from "@/components/TermGlossary";
import Icon from "@/components/Icon";
import { DASHBOARD_URL, LOAN_TRACKER_URL, LOOPWARE_DESK_URL } from "@/lib/format";

const NAV = [
  { href: "/", label: "ホーム", icon: "home" },
  { href: "/themes", label: "テーマ", icon: "trend" },
  { href: "/stock-watch", label: "株式ウォッチ", icon: "watch" },
  { href: "/money-ops", label: "資金移動", icon: "transfer" },
  { href: "/decisions", label: "判断ログ", icon: "decide" },
  { href: "/portfolio", label: "資産", icon: "wallet" },
  { href: "/household-bs", label: "家計B/S", icon: "pie" },
  { href: "/consultations", label: "相談", icon: "chat" },
  { href: "/lifeplan", label: "ライフプラン", icon: "calendar" },
  { href: "/realestate", label: "不動産賃貸", icon: "building" },
  { href: "/notion", label: "Notionタスク", icon: "queue" },
  { href: "/mq", label: "MQ会計評価", icon: "chart" },
  { href: "/roi", label: "ROI", icon: "spark" },
  { href: "/tax", label: "確定申告", icon: "file" },
  { href: "/guide", label: "構成ガイド", icon: "book" },
  { href: "/jobs", label: "ジョブ", icon: "refresh" },
  { href: "/settings", label: "設定", icon: "shield" },
  { href: "/research", label: "リサーチ", icon: "search" },
  { href: "/paper", label: "Lab", icon: "ai" },
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
          <Icon name={n.icon} />
          <span>{n.label}</span>
        </a>
      ))}
    </>
  );
}

function activeLabel(active: string): string {
  const hit = NAV.filter(
    (n) => active === n.href || (n.href !== "/" && active.startsWith(`${n.href}/`))
  ).sort((a, b) => b.href.length - a.href.length)[0];
  return hit?.label ?? "メニュー";
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
            <span className="pb-logo" aria-hidden>
              <Icon name="yen" size={18} />
            </span>
            <div>
              <div className="side-brand">KURASHIFT</div>
              <div className="side-brand-ja">クラシフト</div>
            </div>
          </div>
          <p className="side-tagline">暮らしを整え、資産を動かす</p>
        </div>

        {/* スマホ幅ではメニューを畳む（JS 不要のチェックボックス開閉） */}
        <input
          type="checkbox"
          id="side-nav-toggle"
          className="side-nav-toggle"
          aria-hidden
        />
        <label htmlFor="side-nav-toggle" className="side-nav-button">
          <span className="side-nav-current">{activeLabel(active)}</span>
          <span className="side-nav-button-text">メニュー ☰</span>
        </label>

        <nav className="side-nav" aria-label="メインメニュー">

        <div className="side-group-title">① 資産運用</div>
        <NavLinks
          active={active}
          items={NAV.filter((n) =>
            [
              "/",
              "/themes",
              "/stock-watch",
              "/money-ops",
              "/portfolio",
              "/household-bs",
              "/consultations",
            ].includes(n.href)
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
          <Icon name="file" />
          <span>借入残高トラッカー ↗</span>
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
            <Icon name="bolt" />
            <span>Jarvis ダッシュボード ↗</span>
          </a>
          <a
            className="side-link"
            href={LOOPWARE_DESK_URL}
            target="_blank"
            rel="noopener noreferrer"
          >
            <Icon name="check" />
            <span>判断デスク（ループウェア） ↗</span>
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
        </nav>
      </aside>
      <main>
        <TermGlossary />
        {children}
      </main>
    </div>
  );
}
