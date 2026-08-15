/**
 * mqRefreshPolicy.selftest.ts
 * Run: npx tsx lib/mqRefreshPolicy.selftest.ts
 */
import { decideMqRefreshYears } from "./mqRefreshPolicy";

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg);
}

// 1月 → 前年+当年
{
  const d = decideMqRefreshYears({
    now: new Date("2026-01-08T03:00:00+09:00"),
    force: true,
  });
  assert(d.yearsToRefresh.join(",") === "2025,2026", "jan years");
  assert(d.yearsToSeal.length === 0, "jan no seal");
  assert(d.shouldRunMonthly, "jan force run");
}

// 2月 → 前年確定候補
{
  const d = decideMqRefreshYears({
    now: new Date("2026-02-10T03:00:00+09:00"),
    force: true,
  });
  assert(d.yearsToRefresh.join(",") === "2025,2026", "feb years");
  assert(d.yearsToSeal.join(",") === "2025", "feb seal");
}

// 8月 → 当年のみ
{
  const d = decideMqRefreshYears({
    now: new Date("2026-08-16T03:00:00+09:00"),
    force: true,
  });
  assert(d.yearsToRefresh.join(",") === "2026", "aug years");
}

// 確定スキップ
{
  const d = decideMqRefreshYears({
    now: new Date("2026-03-10T03:00:00+09:00"),
    sealedYears: [2026],
    force: true,
  });
  assert(d.yearsToRefresh.length === 0, "sealed skip");
  assert(d.sealedSkipped.join(",") === "2026", "sealed listed");
}

// reopen: 確定済み前年を明示再開
{
  const d = decideMqRefreshYears({
    now: new Date("2026-03-10T03:00:00+09:00"),
    sealedYears: [2025],
    reopenYears: [2025],
    force: true,
  });
  assert(d.yearsToRefresh.includes(2025), "reopen includes sealed year");
  assert(d.yearsToRefresh.includes(2026), "still has current");
}

// 月次ゲート: 4日はスキップ
{
  const d = decideMqRefreshYears({
    now: new Date("2026-08-04T03:00:00+09:00"),
  });
  assert(!d.shouldRunMonthly, "before day 5");
}

// 月次ゲート: 5日・未実施
{
  const d = decideMqRefreshYears({
    now: new Date("2026-08-05T03:00:00+09:00"),
  });
  assert(d.shouldRunMonthly, "day 5 run");
  assert(d.cycleMonth === "2026-08", "cycle");
}

// 当月済み
{
  const d = decideMqRefreshYears({
    now: new Date("2026-08-12T03:00:00+09:00"),
    lastSuccessCycleMonth: "2026-08",
  });
  assert(!d.shouldRunMonthly, "already done");
}

console.log("mqRefreshPolicy.selftest: ok");
