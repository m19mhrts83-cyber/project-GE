import Link from "next/link";
import {
  buildHouseholdAdvice,
  formatAdviceAmount,
} from "@/lib/householdBsAdvice";
import type { HouseholdBsView } from "@/lib/householdBsCompose";

export default function HouseholdBsAdvicePanel({
  view,
}: {
  view: HouseholdBsView;
}) {
  const items = buildHouseholdAdvice(view);

  return (
    <div className="card" style={{ marginTop: 12 }}>
      <header>
        <span className="lvl">助言</span>
        <strong>余った現金の優先（参考）</strong>
      </header>
      <p className="meta" style={{ marginTop: 6 }}>
        防衛→次物件キープ→NISA月9万→Theme。SBIコア売却は提案しません。
      </p>
      <ol style={{ margin: "10px 0 0", paddingLeft: 20 }}>
        {items.map((it) => (
          <li key={it.order} style={{ marginBottom: 8 }}>
            <strong>{it.label}</strong>
            {" · "}
            {formatAdviceAmount(it.amountJpy)}
            {it.note ? (
              <span className="meta" style={{ display: "block" }}>
                {it.note}
              </span>
            ) : null}
            {it.href ? (
              <>
                {" "}
                <Link href={it.href}>→</Link>
              </>
            ) : null}
          </li>
        ))}
      </ol>
    </div>
  );
}
