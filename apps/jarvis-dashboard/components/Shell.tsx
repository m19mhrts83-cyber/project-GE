import Link from "next/link";
import { createClient } from "@/lib/supabase/server";

const NAV = [
  { href: "/", label: "メール · 概要" },
  { href: "/partner", label: "パートナー" },
  { href: "/openchat", label: "オプチャ" },
  { href: "/general", label: "それ以外" },
  { href: "/situation", label: "状況ウォッチ" },
  { href: "/kamiooya", label: "神大家運営" },
  { href: "/properties", label: "3棟・物件" },
  { href: "/kodate", label: "戸建て" },
  { href: "/ai-raimo", label: "AI・Raimo" },
  { href: "/metrics", label: "数値" },
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
