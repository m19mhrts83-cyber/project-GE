/** ホーム「モチベーション数値」用の手残り考察 */

export type CashflowSlice = {
  cashflow?: number;
  rent_income?: number;
  rental_expense?: number;
  expense_total?: number;
  income_total?: number;
  other_expense?: number;
  other_income?: number;
  salary?: number;
  repair_expense?: number;
};

export type CashflowInsight = {
  tone: "plus" | "watch" | "attention";
  headline: string;
  body: string;
  path: string;
};

function n(v: number | undefined): number | null {
  return v == null || Number.isNaN(v) ? null : v;
}

export function buildCashflowInsight(
  entity: "corporate" | "personal",
  cur: CashflowSlice,
  prev?: CashflowSlice | null,
): CashflowInsight {
  const label = entity === "corporate" ? "法人" : "個人";
  const cf = n(cur.cashflow);
  const rent = n(cur.rent_income) ?? 0;
  const rentalExp = n(cur.rental_expense) ?? 0;
  const otherExp = n(cur.other_expense) ?? 0;
  const otherInc = n(cur.other_income) ?? 0;
  const salary = n(cur.salary) ?? 0;
  const rentalGap = rent - rentalExp; // 家賃 − 賃貸支出
  const prevCf = prev ? n(prev.cashflow) : null;

  if (cf == null) {
    return {
      tone: "watch",
      headline: `${label}：データ待ち`,
      body: "この月の集計がまだありません。",
      path: "Zaim CSV 取込後に再表示されます。",
    };
  }

  if (cf >= 0) {
    const trend =
      prevCf != null && prevCf < 0
        ? "先月のマイナスからプラスへ転換しています。"
        : "手残りプラスを維持できています。";
    return {
      tone: "plus",
      headline: `${label}：手残りプラス`,
      body: trend,
      path: "この水準を基準に、空室ゼロと固定費の横ばいを続ければ習慣として定着しやすいです。",
    };
  }

  // マイナス時
  const spike =
    rent > 0 && (otherExp > rent * 2 || otherInc > rent * 2);
  const opsOk = rentalGap >= 0;
  const gapAbs = Math.abs(cf);

  let nature: string;
  let path: string;
  let tone: CashflowInsight["tone"] = "attention";

  if (spike) {
    tone = "watch";
    nature =
      "家賃に対して「その他収入／その他支出」が大きい月です。振替・税金・一括返済・借入返済などが月に載ると、恒久赤字に見えやすいです（一時的の可能性が高い）。";
    path =
      "まず Zaim の大口行を確認し、振替や一括が混ざっていないかを切り分けましょう。恒久の固定費と分かれば、そこだけ削減・借り換えの対象にできます。";
  } else if (opsOk) {
    tone = "watch";
    nature =
      entity === "corporate"
        ? "家賃は賃貸支出を上回っています。手残りマイナスは、賃貸外の会社費用や一時支出が押し下げている形です。"
        : "家賃（と給与）の側では賃貸支出をカバーできています。手残りマイナスは生活費・カード・その他支出の厚みが主因の可能性が高いです。";
    path =
      entity === "corporate"
        ? "道筋: ①会社費用の固定費を棚卸し ②修繕・一括のタイミングを分散 ③家賃入金タイミングのズレを翌月とセットで見る。"
        : "道筋: ①家賃＋給与で賄う固定費の上限を決める ②カード／サブスクを見直す ③空室があれば埋めて家賃側の上振れを狙う。";
  } else {
    tone = "attention";
    nature =
      "家賃より賃貸支出（ローン・管理・固定資産税などの賃貸カテゴリ）が大きく、物件側の月次が赤字寄りです。空室・賃料条件・ローン条件が効いている可能性があります。";
    path =
      "道筋: ①空室の早期成約（所有物件レーン） ②更新・条件の見直し ③ローン返済額と管理費の点検。家賃合計が賃貸支出を超える月を「黒字ライン」の目標にすると分かりやすいです。";
  }

  const trend =
    prevCf != null
      ? cf > prevCf
        ? `先月比では ${Math.round(cf - prevCf).toLocaleString("ja-JP")}円改善しています。`
        : cf < prevCf
          ? `先月比では ${Math.round(prevCf - cf).toLocaleString("ja-JP")}円悪化しています。`
          : "先月と同水準です。"
      : "";

  return {
    tone,
    headline: `${label}：手残りマイナス（${gapAbs.toLocaleString("ja-JP")}円）`,
    body: `${nature}${trend ? ` ${trend}` : ""}`,
    path,
  };
}
