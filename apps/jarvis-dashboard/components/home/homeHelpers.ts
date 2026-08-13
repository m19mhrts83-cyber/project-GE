import { formatJstMmDdHm } from "@/lib/formatJst";

export function fmtYenSigned(n: number | null | undefined, sign: "+" | "-"): string {
  if (n == null) return "—";
  const abs = `${Math.round(Math.abs(n)).toLocaleString("ja-JP")}円`;
  if (n === 0) return abs;
  return sign === "-" ? `−${abs}` : `＋${abs}`;
}

export function fmtSync(v: string | undefined) {
  return formatJstMmDdHm(v, "—");
}

export function watchHref(
  id: string,
  payload?: Record<string, unknown> | null
): { href: string; external: boolean } {
  if (id === "card_debit_watch") {
    // 気づきは状況ウォッチ。ホーム一覧からも詳細へ（処置CTAはカード内）
    return {
      href: `/situation?watch=${encodeURIComponent(id)}#watch-${encodeURIComponent(id)}`,
      external: false,
    };
  }
  if (id === "zaim_quality") return { href: "/zaim", external: false };
  if (id === "openchat_threads") return { href: "/openchat", external: false };
  if (id === "cursor_pro_plus_downgrade") {
    return { href: "https://www.cursor.com/settings", external: true };
  }
  void payload;
  return {
    href: `/situation?watch=${encodeURIComponent(id)}#watch-${encodeURIComponent(id)}`,
    external: false,
  };
}
