/**
 * ビジョン（/policy の一番上）。文面は個人的な内容なのでリポに置かず、
 * Mac の scripts/jarvis_vision.py が sync_meta `vision` に写した Markdown を読む。
 * 形式: 「V1. 見出し: 本文」の行 + 「  - 補足」の行。それ以外の行（## 行を除く）は末尾の注記。
 */
export type VisionItem = { id: string; text: string; sub: string[] };
export type Vision = { items: VisionItem[]; notes: string[] };

export function parseVision(raw: string | null | undefined): Vision | null {
  if (!raw || !raw.trim()) return null;
  const items: VisionItem[] = [];
  const notes: string[] = [];
  for (const line of raw.split(/\r?\n/)) {
    if (!line.trim() || /^#{1,6}\s/.test(line)) continue;
    const head = line.match(/^(V\d+)[.．]\s*(.*)$/);
    if (head) {
      items.push({ id: head[1], text: head[2].trim(), sub: [] });
      continue;
    }
    const sub = line.match(/^\s+[-・]\s*(.*)$/);
    if (sub && items.length) {
      items[items.length - 1].sub.push(sub[1].trim());
      continue;
    }
    notes.push(line.trim());
  }
  return items.length ? { items, notes } : null;
}
