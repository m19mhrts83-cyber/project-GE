/** 年次更新 (a)〜(d)。ジョブ id は既存 worker と揃える。 */

export const LIFEPLAN_ANNUAL_STEPS = [
  {
    n: 1,
    key: "a" as const,
    job: "lifeplan_ingest_actuals",
    title: "終了した年度の実績を反映する",
    desc: "Zaim 年度サマリーから実績を取り込み、αβγ と100歳計画の「実績」列の材料にする。",
  },
  {
    n: 2,
    key: "b" as const,
    job: "lifeplan_revise_budget",
    title: "実績を踏まえて当年度の予算を作る",
    desc: "過去3〜4年の推移を見ながら、月別予算（予算編成シート）を固める。",
  },
  {
    n: 3,
    key: "c" as const,
    job: "lifeplan_update_century",
    title: "予算を100歳計画に反映する",
    desc: "当年度予算をキャッシュフロー（〜100歳）へ載せる。現時点の書込は Numbers 正本＋Jarvis。",
  },
  {
    n: 4,
    key: "d" as const,
    job: "lifeplan_snapshot",
    title: "将来予測を修正し、計画全体を評価する",
    desc: "反映後の差分を確認し、スナップショットを残す。財務（Zaim）への月次反映は別ボタン。",
  },
];

export const LIFEPLAN_PUSH_ZAIM_JOB = "lifeplan_push_zaim";
