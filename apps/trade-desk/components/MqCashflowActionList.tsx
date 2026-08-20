"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { fmtMqMan } from "@/lib/mqUnits";
import type { CashflowActionRow } from "@/lib/mqCashflowManual";
import { actionKindLabel } from "@/lib/mqCashflowManual";

type Props = {
  year: string;
  entity: "personal" | "corporate";
  businessLine?: string;
  actions: CashflowActionRow[];
};

export default function MqCashflowActionList(props: Props) {
  const { year, entity, businessLine = "realestate", actions } = props;
  const router = useRouter();
  const [busyId, setBusyId] = useState<string | null>(null);

  const yearActions = actions.filter((a) =>
    String(a.period_month).startsWith(`${year}-`)
  );
  if (yearActions.length === 0) return null;

  async function deactivate(id: string) {
    setBusyId(id);
    try {
      await fetch("/api/mq/cashflow/actions", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, isActive: false }),
      });
      router.refresh();
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="card" style={{ marginTop: 12 }}>
      <header>
        <span className="lvl">処置</span>
        <strong>{year}年の計画行</strong>
      </header>
      <ul className="mq-cashflow-action-list">
        {yearActions.map((a) => (
          <li key={a.id}>
            <span>
              {String(a.period_month).slice(0, 7)} ·{" "}
              {actionKindLabel(a.action_kind)} {fmtMqMan(Number(a.amount_man))}
              {a.label ? ` · ${a.label}` : ""}
            </span>
            {a.id ? (
              <button
                type="button"
                className="btn"
                disabled={busyId === a.id}
                onClick={() => deactivate(a.id!)}
              >
                無効化
              </button>
            ) : null}
          </li>
        ))}
      </ul>
      <p className="meta">事業線 {businessLine} · {entity}</p>
    </div>
  );
}
