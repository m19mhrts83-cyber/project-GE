"use client";

import type { CSSProperties, ReactNode } from "react";
import { openInGoogleChrome } from "@/lib/openInChrome";

type Props = {
  href: string;
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  title?: string;
  /** btn 見た目（既定）か、インラインリンク風 */
  variant?: "btn" | "link";
};

/** 外部 http(s) を Mac の Google Chrome で開く（Cursor 中央ブラウザ回避） */
export default function ChromeExternalLink({
  href,
  children,
  className,
  style,
  title,
  variant = "btn",
}: Props) {
  const url = String(href || "").trim();
  if (!url) return null;

  return (
    <button
      type="button"
      className={variant === "btn" ? className || "btn" : className}
      title={title || "Google Chrome で開く"}
      style={
        variant === "link"
          ? {
              background: "none",
              border: "none",
              padding: 0,
              margin: 0,
              color: "inherit",
              textDecoration: "underline",
              cursor: "pointer",
              font: "inherit",
              ...style,
            }
          : style
      }
      onClick={() => {
        void openInGoogleChrome(url);
      }}
    >
      {children}
    </button>
  );
}
