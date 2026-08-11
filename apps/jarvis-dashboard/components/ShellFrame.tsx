"use client";

import { useCallback, useEffect, useState } from "react";
import CommandPalette from "@/components/CommandPalette";
import { GlobalUndoKey, ToastProvider } from "@/components/Toast";
import type { NavCounts } from "@/lib/navBadges";
import { badgeForHref } from "@/lib/navBadges";
import { HOME_NAV, NAV_GROUPS } from "@/lib/nav";

type Props = {
  active: string;
  email: string | null;
  counts: NavCounts;
  children: React.ReactNode;
};

function isActive(active: string, href: string): boolean {
  if (href === "/") return active === "/";
  if (active === href) return true;
  return active.startsWith(href.endsWith("/") ? href : `${href}/`);
}

export default function ShellFrame({
  active,
  email,
  counts,
  children,
}: Props) {
  const [navOpen, setNavOpen] = useState(false);
  const [cmdOpen, setCmdOpen] = useState(false);
  const [cmdPreferHelp, setCmdPreferHelp] = useState(false);

  const closeNav = useCallback(() => setNavOpen(false), []);
  const openCmd = useCallback((preferHelp = false) => {
    setCmdPreferHelp(preferHelp);
    setCmdOpen(true);
  }, []);
  const closeCmd = useCallback(() => {
    setCmdOpen(false);
    setCmdPreferHelp(false);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const meta = e.metaKey || e.ctrlKey;
      if (meta && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCmdPreferHelp(false);
        setCmdOpen((v) => !v);
        return;
      }
      // 入力中はグローバルショートカットを無視
      const t = e.target as HTMLElement | null;
      const tag = t?.tagName;
      if (
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "SELECT" ||
        t?.isContentEditable
      ) {
        return;
      }
      if (e.key === "/" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        openCmd(false);
        return;
      }
      if (e.key === "?" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        openCmd(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openCmd]);

  useEffect(() => {
    closeNav();
  }, [active, closeNav]);

  const renderBadge = (href: string) => {
    const n = badgeForHref(href, counts);
    if (!n) return null;
    return (
      <span className="nav-badge" aria-label={`${n}件`}>
        {n > 99 ? "99+" : n}
      </span>
    );
  };

  return (
    <ToastProvider>
      <GlobalUndoKey />
      <div className={`layout${navOpen ? " nav-open" : ""}`}>
        <button
          type="button"
          className="nav-toggle"
          aria-label={navOpen ? "メニューを閉じる" : "メニューを開く"}
          aria-expanded={navOpen}
          onClick={() => setNavOpen((v) => !v)}
        >
          <span className="nav-toggle-bars" aria-hidden />
        </button>

        {navOpen ? (
          <button
            type="button"
            className="nav-scrim"
            aria-label="メニューを閉じる"
            onClick={closeNav}
          />
        ) : null}

        <aside className="sidebar" id="app-sidebar">
          <div className="side-brand-row">
            <div className="side-brand">Jarvis</div>
            <button
              type="button"
              className="side-cmd-btn"
              onClick={() => openCmd(false)}
              title="コマンドパレット (⌘K)"
            >
              ⌘K
            </button>
          </div>
          <a
            href={HOME_NAV.href}
            className={`side-link side-link-home${
              isActive(active, HOME_NAV.href) ? " active" : ""
            }`}
            onClick={closeNav}
          >
            {HOME_NAV.label}
          </a>
          {NAV_GROUPS.map((g) => (
            <div key={g.title} className="side-group">
              <div className="side-group-title">{g.title}</div>
              {g.items.map((n) => (
                <a
                  key={n.href}
                  href={n.href}
                  className={`side-link${
                    isActive(active, n.href) ? " active" : ""
                  }`}
                  onClick={closeNav}
                >
                  <span className="side-link-label">{n.label}</span>
                  {renderBadge(n.href)}
                </a>
              ))}
            </div>
          ))}
          <div className="side-note">
            {email ?? "—"}
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
      <CommandPalette
        open={cmdOpen}
        onClose={closeCmd}
        preferHelp={cmdPreferHelp}
      />
    </ToastProvider>
  );
}
