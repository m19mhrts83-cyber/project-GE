// (4) の拡張: LINEオープンチャットの質問ランキング（2026-11-16）。段階公開スイッチ openchat_ranking が見える管理者だけ。
// 週次の Actions（scripts/course_theme/openchat_ranking.py）が qa_openchat_rankings に入れた回を、画面向けに整える。
// 件数・人数・返信数はスクリプトが数えた値。投稿者の名前は元から持たない。
const str = (v: unknown, n: number) => String(v ?? '').slice(0, n);
const num = (v: unknown) => { const x = Number(v); return Number.isFinite(x) && x >= 0 ? Math.round(x) : 0; };
const arr = (v: unknown): any[] => Array.isArray(v) ? v : [];

export function shapeOpenchatRound(r: any) {
  const ranking = arr(r?.ranking).slice(0, 30).map((x: any) => ({
    topic: str(x?.topic, 80), count: num(x?.count), people: num(x?.people), replies: num(x?.replies), recent: num(x?.recent),
    chats: arr(x?.chats).slice(0, 8).map((c: any) => ({ chat: str(c?.chat, 40), n: num(c?.n) })),
    examples: arr(x?.examples).slice(0, 3).map((e: any) => ({ chat: str(e?.chat, 40), d: str(e?.d, 10), text: str(e?.text, 140) })),
  }));
  const by_chat = arr(r?.by_chat).slice(0, 40).map((c: any) => ({
    chat: str(c?.chat, 40), questions: num(c?.questions), people: num(c?.people),
    top: arr(c?.top).slice(0, 10).map((t: any) => ({ topic: str(t?.topic, 80), count: num(t?.count), people: num(t?.people),
      examples: arr(t?.examples).slice(0, 2).map((e: unknown) => str(e, 140)) })),
  }));
  const s = r?.stats && typeof r.stats === 'object' ? r.stats : {};
  return { id: str(r?.id, 40), created_at: r?.created_at ?? null, period_days: num(r?.period_days), ranking, by_chat,
    stats: { posts: num(s.posts), questions: num(s.questions), people: num(s.people), chats: num(s.chats) } };
}
