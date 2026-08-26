/** 不動産 ③-A〜D レーンナビ */

import { LOAN_TRACKER_URL } from "@/lib/format";

export type ReLaneId =
  | "a"
  | "b-plan"
  | "b-funnel"
  | "b-vendors"
  | "b-mgmt"
  | "b-repair"
  | "c"
  | "d";

const LANES: {
  id: ReLaneId;
  href: string;
  short: string;
  label: string;
}[] = [
  { id: "a", href: "/realestate", short: "A", label: "運用・進捗" },
  {
    id: "b-plan",
    href: "/realestate/buy-plan",
    short: "B計",
    label: "買い進めプラン",
  },
  {
    id: "b-funnel",
    href: "/realestate/deals",
    short: "B実",
    label: "千三つ",
  },
  {
    id: "b-vendors",
    href: "/realestate/vendors",
    short: "B開",
    label: "業者開拓",
  },
  {
    id: "b-mgmt",
    href: "/realestate/mgmt-vendors",
    short: "管理",
    label: "管理会社",
  },
  {
    id: "b-repair",
    href: "/realestate/repair-vendors",
    short: "修繕",
    label: "修繕業者",
  },
  { id: "c", href: "/realestate/properties", short: "C", label: "保有マスタ" },
  {
    id: "d",
    href: "/realestate/finance-pack",
    short: "D",
    label: "融資パック",
  },
];

export default function RealEstateLaneNav({ active }: { active: ReLaneId }) {
  return (
    <nav
      aria-label="不動産レーン"
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 8,
        marginBottom: 16,
        alignItems: "center",
      }}
    >
      <span className="meta" style={{ marginRight: 4 }}>
        レーン
      </span>
      <a
        href="/guide#re-lanes"
        className="meta"
        style={{ marginRight: 4, textDecoration: "underline" }}
        title="記号の意味・実装メモ"
      >
        説明
      </a>
      {LANES.map((l) => {
        const on = l.id === active;
        return (
          <a
            key={l.id}
            href={l.href}
            className={on ? "btn" : undefined}
            style={
              on
                ? undefined
                : {
                    padding: "4px 10px",
                    border: "1px solid var(--border, #ccc)",
                    borderRadius: 6,
                    textDecoration: "none",
                    fontSize: 13,
                  }
            }
          >
            <strong>{l.short}</strong> {l.label}
          </a>
        );
      })}
      <a
        href={LOAN_TRACKER_URL}
        target="_blank"
        rel="noopener noreferrer"
        title="ローン正本（Google: estate）"
        style={{
          marginLeft: 4,
          padding: "4px 10px",
          border: "1px solid var(--border, #ccc)",
          borderRadius: 6,
          textDecoration: "none",
          fontSize: 13,
        }}
      >
        借入残高トラッカー ↗
      </a>
    </nav>
  );
}
