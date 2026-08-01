import Link from "next/link";
import { createClient } from "@/lib/supabase/server";

const NAV = [
  { href: "/", label: "メール · 概要" },
  { href: "/partner", label: "パートナー" },
  { href: "/openchat", label: "オプチャ" },
  { href: "/general", label: "それ以外" },
  { href: "/situation", label: "状況ウォッチ" },
];

const PLACEHOLDERS = [
  "神大家運営",
  "3棟・物件",
  "戸建て",
  "AI・Raimo",
  "数値",
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

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="side-brand">Jarvis</div>
        {NAV.map((n) => (
          <Link
            key={n.href}
            href={n.href}
            className={`side-link${active === n.href ? " active" : ""}`}
          >
            {n.label}
          </Link>
        ))}
        {PLACEHOLDERS.map((p) => (
          <div key={p} className="side-link disabled">
            {p}
            <div className="side-note">Phase 2</div>
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
