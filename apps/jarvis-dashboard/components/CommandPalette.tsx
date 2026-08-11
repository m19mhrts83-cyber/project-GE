"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { flatNavItems, type NavItem } from "@/lib/nav";
import { useEscape, useToast } from "@/components/Toast";
import { setTriageStatus } from "@/app/actions/triage";
import {
  fetchFirstPartnerPendingId,
  searchCmdk,
  type CmdkSearchHit,
} from "@/app/actions/cmdkSearch";
import {
  SNOOZE_PRESET_LABEL,
  type SnoozePreset,
  snoozeUntilIso,
} from "@/lib/snoozePresets";

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
  /** `?` 起動時はヘルプを先頭に */
  preferHelp?: boolean;
};

function matchQuery(label: string, q: string): boolean {
  if (!q) return true;
  const n = (s: string) => s.toLowerCase().replace(/\s+/g, "");
  return n(label).includes(n(q));
}

const HELP_ACTIONS: Omit<Action, "run">[] = [
  {
    id: "help:keys",
    label: "ショートカット: j/k 前後 · e スキップ · s 後で · h 時間スヌーズ · z 戻す",
    hint: "パートナー／キュー",
    group: "ヘルプ",
  },
  {
    id: "help:cmdk",
    label: "⌘K / / でこのパレット、? でも開く（? はヘルプ優先）",
    hint: "どこでも",
    group: "ヘルプ",
  },
];

export default function CommandPalette({
  open,
  onClose,
  preferHelp = false,
}: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const toast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const [hits, setHits] = useState<CmdkSearchHit[]>([]);
  const [searching, setSearching] = useState(false);

  const go = useCallback(
    (href: string) => {
      router.push(href);
      onClose();
    },
    [router, onClose],
  );

  const mutateFocus = useCallback(
    (
      id: string,
      next: "skipped" | "snoozed",
      label: string,
      snoozeUntil?: string,
    ) => {
      void (async () => {
        const r = await setTriageStatus(
          id,
          next,
          pathname || "/partner",
          snoozeUntil ? { snoozeUntil } : undefined,
        );
        if (!r.ok) {
          toast.push(r.error, "err");
          return;
        }
        toast.push(label, {
          undo: async () => {
            await setTriageStatus(
              id,
              r.prevStatus || "pending",
              pathname || "/partner",
            );
            router.refresh();
          },
        });
        onClose();
        router.refresh();
      })();
    },
    [pathname, toast, onClose, router],
  );

  const nowActions: Action[] = useMemo(
    () => [
      {
        id: "now:queue",
        label: "処理キューを開く",
        hint: "/queue",
        group: "今やる",
        run: () => go("/queue"),
      },
      {
        id: "now:partner",
        label: "パートナー未読",
        hint: "/partner",
        group: "今やる",
        run: () => go("/partner"),
      },
      {
        id: "now:partner-first",
        label: "最初のパートナー未読（詳細）",
        hint: "mail",
        group: "今やる",
        run: () => {
          void (async () => {
            const id = await fetchFirstPartnerPendingId();
            if (id) go(`/mail/${encodeURIComponent(id)}`);
            else go("/partner");
          })();
        },
      },
      {
        id: "now:situation",
        label: "状況ウォッチ",
        hint: "/situation",
        group: "今やる",
        run: () => go("/situation"),
      },
      {
        id: "now:today",
        label: "ホーム（今日のキュー）",
        hint: "/",
        group: "今やる",
        run: () => go("/"),
      },
    ],
    [go],
  );

  const opActions: Action[] = useMemo(() => {
    const m = pathname?.match(/^\/mail\/([^/]+)/);
    if (m) {
      const id = decodeURIComponent(m[1]);
      return [
        {
          id: "op:detail",
          label: "この件の詳細を開く（現在）",
          hint: id.slice(0, 8),
          group: "操作",
          run: () => onClose(),
        },
        {
          id: "op:skip",
          label: "この件をスキップ",
          hint: "e",
          group: "操作",
          run: () => mutateFocus(id, "skipped", "スキップしました"),
        },
        {
          id: "op:snooze",
          label: "この件を後で（即）",
          hint: "s",
          group: "操作",
          run: () => mutateFocus(id, "snoozed", "後でにしました"),
        },
        ...(
          Object.keys(SNOOZE_PRESET_LABEL) as SnoozePreset[]
        ).map((preset) => ({
          id: `op:snooze-${preset}`,
          label: `この件を後で（${SNOOZE_PRESET_LABEL[preset]}）`,
          hint: "h",
          group: "操作",
          run: () =>
            mutateFocus(
              id,
              "snoozed",
              `後で（${SNOOZE_PRESET_LABEL[preset]}）`,
              snoozeUntilIso(preset),
            ),
        })),
      ];
    }
    return [
      {
        id: "op:first-open",
        label: "先頭のパートナー未読を開く",
        hint: "詳細",
        group: "操作",
        run: () => {
          void (async () => {
            const id = await fetchFirstPartnerPendingId();
            if (id) go(`/mail/${encodeURIComponent(id)}`);
            else {
              toast.push("パートナー未読はありません", "info");
              onClose();
            }
          })();
        },
      },
      {
        id: "op:first-skip",
        label: "先頭のパートナー未読をスキップ",
        hint: "e",
        group: "操作",
        run: () => {
          void (async () => {
            const id = await fetchFirstPartnerPendingId();
            if (!id) {
              toast.push("パートナー未読はありません", "info");
              onClose();
              return;
            }
            mutateFocus(id, "skipped", "スキップしました");
          })();
        },
      },
      {
        id: "op:first-snooze",
        label: "先頭のパートナー未読を後で",
        hint: "s",
        group: "操作",
        run: () => {
          void (async () => {
            const id = await fetchFirstPartnerPendingId();
            if (!id) {
              toast.push("パートナー未読はありません", "info");
              onClose();
              return;
            }
            mutateFocus(id, "snoozed", "後でにしました");
          })();
        },
      },
    ];
  }, [pathname, onClose, mutateFocus, go, toast]);

  const draftActions: Action[] = useMemo(() => {
    const m = pathname?.match(/^\/mail\/([^/]+)/);
    if (!m) return [];
    const id = decodeURIComponent(m[1]);
    return [
      {
        id: "draft:open-confirm",
        label: "送信確認モーダルを開く（ゲート維持・未送信）",
        hint: id.slice(0, 8),
        group: "下書き",
        run: () => {
          onClose();
          window.setTimeout(() => {
            document.getElementById("draft-send-open")?.click();
          }, 50);
        },
      },
    ];
  }, [pathname, onClose]);

  const navActions: Action[] = useMemo(() => {
    const items: NavItem[] = flatNavItems();
    return items.map((it) => ({
      id: `nav:${it.href}`,
      label: it.label,
      hint: it.href,
      group: "移動",
      run: () => go(it.href),
    }));
  }, [go]);

  const helpActions: Action[] = useMemo(
    () =>
      HELP_ACTIONS.map((a) => ({
        ...a,
        run: () => onClose(),
      })),
    [onClose],
  );

  useEffect(() => {
    if (!open) return;
    const t = window.setTimeout(() => {
      if (q.trim().length < 1) {
        setHits([]);
        setSearching(false);
        return;
      }
      setSearching(true);
      void searchCmdk(q).then((r) => {
        setHits(r);
        setSearching(false);
      });
    }, 180);
    return () => window.clearTimeout(t);
  }, [q, open]);

  const filtered = useMemo(() => {
    const baseStatic = preferHelp
      ? [
          ...helpActions,
          ...nowActions,
          ...opActions,
          ...draftActions,
          ...navActions,
        ]
      : [
          ...nowActions,
          ...opActions,
          ...draftActions,
          ...navActions,
          ...helpActions,
        ];

    const staticList = baseStatic.filter((a) =>
      matchQuery(`${a.label} ${a.hint || ""} ${a.group}`, q),
    );

    const searchActions: Action[] = hits.map((h) => ({
      id: h.id,
      label: h.title,
      hint: h.detail,
      group: h.kind === "mail" ? "検索・メール" : "検索・ウォッチ",
      run: () => go(h.href),
    }));

    if (q.trim()) {
      return [...searchActions, ...staticList];
    }
    return baseStatic;
  }, [
    preferHelp,
    nowActions,
    opActions,
    draftActions,
    navActions,
    helpActions,
    hits,
    q,
    go,
  ]);

  useEscape(onClose, open);

  useEffect(() => {
    if (!open) return;
    setQ("");
    setActive(0);
    setHits([]);
    const t = window.setTimeout(() => inputRef.current?.focus(), 10);
    return () => window.clearTimeout(t);
  }, [open]);

  useEffect(() => {
    setActive(0);
  }, [q, filtered.length]);

  const runActive = useCallback(() => {
    const item = filtered[active];
    if (item) item.run();
  }, [filtered, active]);

  if (!open) return null;

  let lastGroup = "";

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
          placeholder={
            preferHelp
              ? "ショートカットヘルプ…（入力で検索）"
              : "移動・検索・今やる・操作…（⌘K /）"
          }
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-autocomplete="list"
          aria-controls="cmdk-list"
        />
        <ul id="cmdk-list" className="cmdk-list" role="listbox">
          {filtered.length === 0 ? (
            <li className="cmdk-empty">
              {searching ? "検索中…" : "該当なし"}
            </li>
          ) : (
            filtered.map((a, i) => {
              const showGroup = a.group !== lastGroup;
              lastGroup = a.group;
              return (
                <li key={a.id} role="option" aria-selected={i === active}>
                  {showGroup ? (
                    <div className="cmdk-group">{a.group}</div>
                  ) : null}
                  <button
                    type="button"
                    className={`cmdk-item${i === active ? " is-active" : ""}`}
                    onMouseEnter={() => setActive(i)}
                    onClick={() => a.run()}
                  >
                    <span className="cmdk-item-label">{a.label}</span>
                    {a.hint ? (
                      <span className="cmdk-item-hint">{a.hint}</span>
                    ) : null}
                  </button>
                </li>
              );
            })
          )}
        </ul>
        <p className="cmdk-footer">
          <kbd>↑↓</kbd> 移動 <kbd>Enter</kbd> 実行 <kbd>Esc</kbd> 閉じる
        </p>
      </div>
    </div>
  );
}
