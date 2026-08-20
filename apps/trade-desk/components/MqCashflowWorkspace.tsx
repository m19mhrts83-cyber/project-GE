"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import MqCashflowTable from "@/components/MqCashflowTable";
import MqCashflowTaxForm from "@/components/MqCashflowTaxForm";
import MqCashflowActionModal from "@/components/MqCashflowActionModal";
import MqCashflowActionList from "@/components/MqCashflowActionList";
import type { MqCashflowMonthRow } from "@/lib/mqCashflow";
import type { CashflowActionRow } from "@/lib/mqCashflowManual";

type Props = {
  title: string;
  year: string;
  rows: MqCashflowMonthRow[];
  grainHint?: string;
  unavailableReason?: string | null;
  originHint?: string | null;
  negativeMonths?: { month: string; cashEndMan: number }[];
  businessLine?: string;
  entity: string;
  interactive?: boolean;
  taxEntity: "personal" | "corporate" | null;
  interestMan: number | null;
  taxMan: number | null;
  taxAccrualMonth?: "december" | "payment";
  actions: CashflowActionRow[];
};

export default function MqCashflowWorkspace(props: Props) {
  const {
    taxEntity,
    interestMan,
    taxMan,
    taxAccrualMonth,
    actions,
    negativeMonths = [],
    year,
    businessLine = "realestate",
    ...tableProps
  } = props;
  const router = useRouter();
  const [modalOpen, setModalOpen] = useState(false);
  const firstNeg = negativeMonths[0]?.month;

  return (
    <>
      <MqCashflowTable
        {...tableProps}
        year={year}
        businessLine={businessLine}
        negativeMonths={negativeMonths}
        onAddAction={
          taxEntity ? () => setModalOpen(true) : undefined
        }
      />

      {taxEntity ? (
        <>
          <MqCashflowTaxForm
            year={year}
            entity={taxEntity}
            businessLine={businessLine}
            interestMan={interestMan}
            taxMan={taxMan}
            taxAccrualMonth={taxAccrualMonth}
          />
          <MqCashflowActionList
            year={year}
            entity={taxEntity}
            businessLine={businessLine}
            actions={actions}
          />
          <MqCashflowActionModal
            open={modalOpen}
            year={year}
            entity={taxEntity}
            businessLine={businessLine}
            defaultMonth={firstNeg?.slice(0, 7) || `${year}-08`}
            onClose={() => setModalOpen(false)}
            onSaved={() => {
              setModalOpen(false);
              router.refresh();
            }}
          />
        </>
      ) : (
        <p className="meta" style={{ marginTop: 12 }}>
          期末税金・処置の入力は、主体を「法人」または「個人」にしてください。
        </p>
      )}
    </>
  );
}
