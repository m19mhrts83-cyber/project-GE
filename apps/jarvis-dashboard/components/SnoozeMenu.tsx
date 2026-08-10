"use client";

import { useEffect, useRef, useState } from "react";
import {
  SNOOZE_PRESET_LABEL,
  type SnoozePreset,
  snoozeUntilIso,
} from "@/lib/snoozePresets";

type Props = {
  disabled?: boolean;
  onPick: (preset: SnoozePreset, untilIso: string) => void;
  /** 即スヌーズ（期限なし） */
  onInstant?: () => void;
  /** 外部から開く（h キー） */
  openSignal?: number;
};

export default function SnoozeMenu({
  disabled,
  onPick,
  onInstant,
  openSignal = 0,
}: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (openSignal > 0) setOpen(true);
  }, [openSignal]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const presets = Object.keys(SNOOZE_PRESET_LABEL) as SnoozePreset[];

  return (
    <div className="snooze-menu" ref={rootRef}>
      <button
        type="button"
        className="btn"
        style={{ padding: "4px 10px", fontSize: "0.78rem", color: "var(--ink)" }}
        disabled={disabled}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        後で ▾
      </button>
      {open ? (
        <ul className="snooze-menu-list" role="menu">
          {presets.map((p) => (
            <li key={p} role="none">
              <button
                type="button"
                role="menuitem"
                className="snooze-menu-item"
                onClick={() => {
                  setOpen(false);
                  onPick(p, snoozeUntilIso(p));
                }}
              >
                {SNOOZE_PRESET_LABEL[p]}
              </button>
            </li>
          ))}
          {onInstant ? (
            <li role="none">
              <button
                type="button"
                role="menuitem"
                className="snooze-menu-item"
                onClick={() => {
                  setOpen(false);
                  onInstant();
                }}
              >
                期限なし
              </button>
            </li>
          ) : null}
        </ul>
      ) : null}
    </div>
  );
}
