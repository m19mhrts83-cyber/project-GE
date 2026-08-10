"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function SiteHeader({ admin }: { admin?: boolean }) {
  return (
    <header className="site-header">
      <div className="container inner">
        <Link href="/" className="brand">
          Prompt Share
        </Link>
        <nav className="nav">
          <Link href="/">一覧</Link>
          {admin ? (
            <Link href="/admin">管理</Link>
          ) : (
            <Link href="/admin/login">管理者ログイン</Link>
          )}
        </nav>
      </div>
    </header>
  );
}

export function AdminNav() {
  const path = usePathname();
  const items = [
    { href: "/admin", label: "ダッシュボード" },
    { href: "/admin/prompts", label: "プロンプト" },
    { href: "/admin/groups", label: "グループ" },
    { href: "/admin/stats", label: "統計" }
  ];
  return (
    <aside className="card admin-nav">
      {items.map((it) => (
        <Link
          key={it.href}
          href={it.href}
          className={path === it.href || (it.href !== "/admin" && path.startsWith(it.href)) ? "active" : ""}
        >
          {it.label}
        </Link>
      ))}
      <button
        className="btn secondary"
        style={{ marginTop: "0.75rem" }}
        onClick={async () => {
          await fetch("/api/auth/logout", { method: "POST" });
          window.location.href = "/admin/login";
        }}
      >
        ログアウト
      </button>
    </aside>
  );
}
