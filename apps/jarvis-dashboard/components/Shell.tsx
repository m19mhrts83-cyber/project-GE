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
  { href: "/billing", label: "課金" },
  { href: "/notebooklm", label: "NotebookLM" },
];

/** 外部動線（レイアウト整理は後で相談可） */
const EXTERNAL: { href: string; label: string }[] = [];

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
        {EXTERNAL.length > 0 ? (
          <>
            <div
              className="side-brand"
              style={{ marginTop: 16, fontSize: 12, opacity: 0.7 }}
            >
              外部
            </div>
            {EXTERNAL.map((n) => (
              <a
                key={n.href}
                href={n.href}
                className="side-link"
                target="_blank"
                rel="noopener noreferrer"
              >
                {n.label} ↗
              </a>
            ))}
          </>
        ) : null}
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
