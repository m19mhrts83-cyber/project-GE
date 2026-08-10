"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

type ToastTone = "ok" | "err" | "info";

type ToastItem = {
  id: number;
  message: string;
  tone: ToastTone;
  undo?: () => void | Promise<void>;
  undoLabel?: string;
};

type PushOpts = {
  tone?: ToastTone;
  undo?: () => void | Promise<void>;
  undoLabel?: string;
  /** ms。Undo 付きは長めが既定 */
  durationMs?: number;
};

type ToastApi = {
  push: (message: string, toneOrOpts?: ToastTone | PushOpts) => void;
  /** 直近の Undo（z キー用） */
  undoLast: () => void;
  hasUndo: boolean;
};

const ToastContext = createContext<ToastApi | null>(null);

let seq = 0;

function normalizePush(
  toneOrOpts?: ToastTone | PushOpts,
): Required<Pick<PushOpts, "tone">> & PushOpts {
  if (!toneOrOpts || typeof toneOrOpts === "string") {
    return { tone: toneOrOpts || "ok" };
  }
  return { tone: "ok", ...toneOrOpts };
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const lastUndoRef = useRef<(() => void | Promise<void>) | null>(null);
  const [hasUndo, setHasUndo] = useState(false);

  const clearUndoSoon = useCallback(() => {
    window.setTimeout(() => {
      lastUndoRef.current = null;
      setHasUndo(false);
    }, 8000);
  }, []);

  const push = useCallback(
    (message: string, toneOrOpts?: ToastTone | PushOpts) => {
      const opts = normalizePush(toneOrOpts);
      const id = ++seq;
      const item: ToastItem = {
        id,
        message,
        tone: opts.tone || "ok",
        undo: opts.undo,
        undoLabel: opts.undoLabel || "元に戻す",
      };
      setItems((prev) => [...prev, item]);
      if (opts.undo) {
        lastUndoRef.current = opts.undo;
        setHasUndo(true);
        clearUndoSoon();
      }
      const ms = opts.durationMs ?? (opts.undo ? 5200 : 2800);
      window.setTimeout(() => {
        setItems((prev) => prev.filter((t) => t.id !== id));
      }, ms);
    },
    [clearUndoSoon],
  );

  const undoLast = useCallback(() => {
    const fn = lastUndoRef.current;
    if (!fn) return;
    lastUndoRef.current = null;
    setHasUndo(false);
    void Promise.resolve(fn());
    setItems((prev) => prev.filter((t) => !t.undo));
  }, []);

  const api = useMemo(
    () => ({ push, undoLast, hasUndo }),
    [push, undoLast, hasUndo],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-stack" aria-live="polite" aria-relevant="additions">
        {items.map((t) => (
          <div key={t.id} className={`toast toast-${t.tone}`} role="status">
            <span className="toast-msg">{t.message}</span>
            {t.undo ? (
              <button
                type="button"
                className="toast-undo"
                onClick={() => {
                  void Promise.resolve(t.undo?.());
                  lastUndoRef.current = null;
                  setHasUndo(false);
                  setItems((prev) => prev.filter((x) => x.id !== t.id));
                }}
              >
                {t.undoLabel || "元に戻す"}
              </button>
            ) : null}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    return {
      push: (message) => {
        if (typeof window !== "undefined") {
          console.info("[toast]", message);
        }
      },
      undoLast: () => {},
      hasUndo: false,
    };
  }
  return ctx;
}

/** Escape で閉じる系の補助（CommandPalette 等） */
export function useEscape(handler: () => void, enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") handler();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handler, enabled]);
}

/** グローバル z で直近 Undo（入力中は無視） */
export function GlobalUndoKey() {
  const { undoLast, hasUndo } = useToast();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
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
      if (e.key.toLowerCase() === "z" && hasUndo) {
        e.preventDefault();
        undoLast();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undoLast, hasUndo]);
  return null;
}
