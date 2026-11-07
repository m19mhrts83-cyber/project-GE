"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import Icon from "./Icon";

const TABS = [
  { href: "/", label: "ハブ", icon: "bolt", match: (p: string) => p === "/" },
  {
    href: "/312",
    label: "312 入口",
    icon: "inbox",
    match: (p: string) => p.startsWith("/312"),
  },
  {
    href: "/313",
    label: "313 出口",
    icon: "done",
    match: (p: string) => p.startsWith("/313"),
  },
] as const;

export default function TabBar() {
  const path = usePathname() || "/";
  return (
    <nav className="tabbar" aria-label="メイン">
      {TABS.map((t) => (
        <Link
          key={t.href}
          href={t.href}
          className={t.match(path) ? "active" : ""}
          aria-current={t.match(path) ? "page" : undefined}
        >
          <Icon name={t.icon} size={22} />
          {t.label}
        </Link>
      ))}
    </nav>
  );
}
