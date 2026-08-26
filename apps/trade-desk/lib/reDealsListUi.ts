/** 千三つ案件一覧 — 件名検索とページング（クライアント／テスト共用） */

export const DEALS_PAGE_SIZE = 20;

export function normalizeDealTitleQuery(query: string): string {
  return query.replace(/\s+/g, " ").trim().toLowerCase();
}

export function dealTitleMatches(
  title: string | null | undefined,
  query: string
): boolean {
  const needle = normalizeDealTitleQuery(query);
  if (!needle) return true;
  return String(title || "").toLowerCase().includes(needle);
}

export function filterDealsByTitle<T extends { title?: string | null }>(
  deals: T[],
  query: string
): T[] {
  if (!normalizeDealTitleQuery(query)) return deals;
  return deals.filter((d) => dealTitleMatches(d.title, query));
}

export function paginateDeals<T>(
  deals: T[],
  page: number,
  pageSize = DEALS_PAGE_SIZE
): {
  page: number;
  pageCount: number;
  slice: T[];
  from: number;
  to: number;
} {
  const size = Math.max(1, pageSize);
  const pageCount = Math.max(1, Math.ceil(deals.length / size));
  const p = Math.min(Math.max(1, Math.floor(page) || 1), pageCount);
  const start = (p - 1) * size;
  const slice = deals.slice(start, start + size);
  return {
    page: p,
    pageCount,
    slice,
    from: deals.length === 0 ? 0 : start + 1,
    to: start + slice.length,
  };
}

export function pageForDealId<T extends { id: string }>(
  deals: T[],
  id: string | null | undefined,
  pageSize = DEALS_PAGE_SIZE
): number {
  if (!id) return 1;
  const idx = deals.findIndex((d) => d.id === id);
  if (idx < 0) return 1;
  return Math.floor(idx / Math.max(1, pageSize)) + 1;
}
