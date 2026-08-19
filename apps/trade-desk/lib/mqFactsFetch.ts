/**
 * MQ period facts — PostgREST 1000件上限を超える全件取得
 */
import type { MqFactRow } from "./mqAggregate";
import { MQ_FACT_SELECT } from "./mqLeanSelect";

const PAGE = 1000;

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Sb = any;

async function fetchAllPages<T>(
  pageQuery: (
    from: number,
    to: number
  ) => Promise<{ data: T[] | null; error: { message: string } | null }>
): Promise<T[]> {
  const all: T[] = [];
  for (let from = 0; from < 200_000; from += PAGE) {
    const { data, error } = await pageQuery(from, from + PAGE - 1);
    if (error) throw new Error(error.message);
    const rows = data ?? [];
    all.push(...rows);
    if (rows.length < PAGE) break;
  }
  return all;
}

/** /mq 画面用 — 年度スライサーが古い年まで届くよう全ページ取得 */
export async function fetchAllMqPeriodFacts(sb: Sb): Promise<MqFactRow[]> {
  return fetchAllPages((from, to) =>
    sb
      .from("kurashift_mq_period_facts")
      .select(MQ_FACT_SELECT)
      .order("period_month", { ascending: false })
      .order("business_line", { ascending: true })
      .order("entity", { ascending: true })
      .order("scenario_kind", { ascending: true })
      .order("plan_variant_id", { ascending: true })
      .range(from, to)
  );
}
