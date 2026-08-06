export type NavCounts = {
  partnerUnread: number;
  otherUnread: number;
  watchAttention: number;
};

export function badgeForHref(
  href: string,
  counts: NavCounts,
): number | null {
  if (href === "/partner") return counts.partnerUnread || null;
  if (href === "/general") return counts.otherUnread || null;
  if (href === "/situation") return counts.watchAttention || null;
  return null;
}
