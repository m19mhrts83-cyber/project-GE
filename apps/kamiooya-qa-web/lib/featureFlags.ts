// 改善機能の段階公開スイッチ（2026-11-10）。
// 段階: off（誰にも出さない）→ owner（松野さんだけ）→ reviewers（指定した確認者も）→ all（会員全員）。
// 「管理者かどうか」では判定しない。了承前は同じ管理者の運営にも見せないため、名指しの一覧だけで決める。
// 判定は必ずサーバー側。画面の表示は /features の結果に従うだけで、機能の API も requireFeature で止める。
export const FEATURE_STAGES = ['off', 'owner', 'reviewers', 'all'] as const;
export type FeatureStage = typeof FEATURE_STAGES[number];
export type FeatureFlag = { feature: string; stage: string; owner_ids?: unknown; reviewer_ids?: unknown };
export type FeatureUser = { id: string; email: string };

const list = (v: unknown): string[] => Array.isArray(v) ? v.map(x => String(x).trim().toLowerCase()).filter(Boolean) : [];
const named = (ids: unknown, u: FeatureUser) => {
  const names = list(ids);
  return names.includes(String(u.id).toLowerCase()) || (!!u.email && names.includes(String(u.email).trim().toLowerCase()));
};

// 知らない段階・壊れた行は「オフ」扱い（安全側に倒す）。
export function featureAllowed(flag: FeatureFlag | undefined, u: FeatureUser): boolean {
  if (!flag || !(FEATURE_STAGES as readonly string[]).includes(flag.stage)) return false;
  if (flag.stage === 'all') return true;
  if (flag.stage === 'off') return false;
  if (named(flag.owner_ids, u)) return true;
  return flag.stage === 'reviewers' && named(flag.reviewer_ids, u);
}

// 画面に渡すのは「その人に見えている機能」と、比べるための「会員にも出ているか」だけ。
// 一覧（誰が確認者か）や段階名は、見えない人には返さない。
export function featuresFor(flags: FeatureFlag[], u: FeatureUser) {
  const features: Record<string, { members: boolean }> = {};
  for (const f of flags) if (/^[a-z0-9_]{1,40}$/.test(f.feature) && featureAllowed(f, u)) features[f.feature] = { members: f.stage === 'all' };
  return { features };
}

export class FeatureDisabledError extends Error {
  code = 'feature_not_available'; status = 404;
  constructor() { super('feature_not_available'); }
}

// 機能の API の入口で呼ぶ。見えない人には「存在しない」と同じ 404 を返す。
export function requireFeature(flags: FeatureFlag[], name: string, u: FeatureUser): void {
  if (!featureAllowed(flags.find(f => f.feature === name), u)) throw new FeatureDisabledError();
}
