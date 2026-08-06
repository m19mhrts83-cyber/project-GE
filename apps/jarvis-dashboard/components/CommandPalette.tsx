"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { flatNavItems, type NavItem } from "@/lib/nav";
import { useEscape } from "@/components/Toast";

type Action = {
  id: string;
  label: string;
  hint?: string;
  group: string;
  run: () => void;
};

type Props = {
  open: boolean;
  onClose: () => void;
  /** 追加アクション（スキップ等は画面側で渡す） */
  extraActions?: Omit<Action, "run"> & { href?: string; run?: () => void }[];
};

function matchQuery(label: string, q: string): boolean {
  if (!q) return true;
  const n = (s: string) => s.toLowerCase().replace(/\s+/g, "");
  return n(label).includes(n(q));
}

export default function CommandPalette({ open, onClose }: Props) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);

  const navActions: Action[] = useMemo(() => {
    const items: NavItem[] = flatNavItems();
    return items.map((it) => ({
      id: `nav:${it.href}`,
      label: it.label,
      hint: it.href,
      group: "移動",
      run: () => {
        router.push(it.href);
        onClose();
      },
    }));
  }, [router, onClose]);

  const filtered = useMemo(() => {
    const list = navActions.filter((a) => matchQuery(`${a.label} ${a.hint || ""}`, q));
    return list;
  }, [navActions, q]);

  useEscape(onClose, open);

  useEffect(() => {
    if (!open) return;
    setQ("");
    setActive(0);
    const t = window.setTimeout(() => inputRef.current?.focus(), 10);
    return () => window.clearTimeout(t);
  }, [open]);

  useEffect(() => {
    setActive(0);
  }, [q]);

  const runActive = useCallback(() => {
    const item = filtered[active];
    if (item) item.run();
  }, [filtered, active]);

  if (!open) return null;

  return (
    <div
      className="cmdk-backdrop"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="cmdk"
        role="dialog"
        aria-modal="true"
        aria-label="コマンドパレット"
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((i) => Math.min(i + 1, Math.max(filtered.length - 1, 0)));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((i) => Math.max(i - 1, 0));
          } else if (e.key === "Enter") {
            e.preventDefault();
            runActive();
          }
        }}
      >
        <input
          ref={inputRef}
          className="cmdk-input"
          placeholder="画面へ移動…（⌘K）"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-autocomplete="list"
          aria-controls="cmdk-list"
        />
        <ul id="cmdk-list" className="cmdk-list" role="listbox">
          {filtered.length === 0 ? (
            <li className="cmdk-empty">該当なし</li>
          ) : (
            filtered.map((a, i) => (
              <li key={a.id} role="option" aria-selected={i === active}>
                <button
                  type="button"
                  className={`cmdk-item${i === active ? " is-active" : ""}`}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => a.run()}
                >
                  <span className="cmdk-item-label">{a.label}</span>
                  {a.hint ? <span className="cmdk-item-hint">{a.hint}</span> : null}
                </button>
              </li>
            ))
          )}
        </ul>
        <p className="cmdk-footer">
          <kbd>↑↓</kbd> 移動 <kbd>Enter</kbd> 開く <kbd>Esc</kbd> 閉じる
        </p>
      </div>
    </div>
  );
}
