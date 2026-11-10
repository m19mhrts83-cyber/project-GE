import assert from "node:assert/strict";
import test from "node:test";
import {
  RECOVERY_JOBS,
  acquireLock,
  actorForKey,
  bearerOf,
  decideRecovery,
  lockFree,
  jobById,
  parseActorKeys,
} from "../lib/jobRecovery.ts";

const K1 = "a".repeat(32);
const K2 = "b".repeat(32);

test("only the four allowed jobs exist", () => {
  assert.deepEqual(Object.keys(RECOVERY_JOBS).sort(), ["comm_reconcile", "comm_write", "partner_111", "reply_211"]);
  // 211 の手動実行は既定 dry_run=true なので、窓口は本番で回す
  assert.equal(RECOVERY_JOBS.reply_211.inputs.dry_run, "false");
  assert.equal(jobById("comm_write")?.workflow, "jarvis-dashboard-gmail-triage.yml");
  for (const bad of ["__proto__", "constructor", "toString", "zaim", 1, null]) assert.equal(jobById(bad), undefined);
});

test("actor keys: parse, identify, reject short or malformed", () => {
  const raw = `hawk:${K1}, banto:${K2}, bad, x:short, :${K1}`;
  assert.deepEqual(parseActorKeys(raw).map((x) => x.actor), ["hawk", "banto"]);
  assert.equal(actorForKey(K1, raw), "hawk");
  assert.equal(actorForKey(K2, raw), "banto");
  assert.equal(actorForKey("c".repeat(32), raw), null);
  assert.equal(actorForKey("", raw), null);
  assert.equal(actorForKey(K1, ""), null);
  assert.equal(bearerOf(`Bearer ${K1}`), K1);
});

const run = (status, conclusion) => ({ status, conclusion, created_at: "", html_url: "", event: "schedule" });

test("decideRecovery: running, two failures, otherwise ok", () => {
  assert.equal(decideRecovery([run("in_progress", null), run("completed", "success")]).ok, false);
  const two = decideRecovery([run("completed", "failure"), run("completed", "failure")]);
  assert.equal(two.ok, false);
  assert.equal(two.reason, "two_failures");
  // skipped / cancelled は数えない
  assert.equal(
    decideRecovery([run("completed", "failure"), run("completed", "skipped"), run("completed", "failure")]).ok,
    false,
  );
  assert.equal(decideRecovery([run("completed", "failure"), run("completed", "success")]).ok, true);
  assert.equal(decideRecovery([]).ok, true);
});

test("lockFree: 6 hours", () => {
  const now = new Date("2026-11-11T12:00:00Z");
  assert.equal(lockFree(null, now), true);
  assert.equal(lockFree("2026-11-11T07:00:00Z", now), false);
  assert.equal(lockFree("2026-11-11T06:00:00Z", now), true);
});

function fakeSupabase() {
  const rows = new Map();
  return {
    rows,
    from() {
      const q = { filters: [], op: null, payload: null, opts: null };
      const api = {
        upsert(row, opts) { q.op = "upsert"; q.payload = row; q.opts = opts; return api; },
        update(vals) { q.op = "update"; q.payload = vals; return api; },
        eq(c, v) { q.filters.push((r) => r[c] === v); return api; },
        lte(c, v) { q.filters.push((r) => String(r[c]) <= String(v)); return api; },
        async select() {
          if (q.op === "upsert") {
            if (rows.has(q.payload.key)) return { data: [], error: null };
            rows.set(q.payload.key, { ...q.payload });
            return { data: [{ key: q.payload.key }], error: null };
          }
          const hit = [...rows.values()].filter((r) => q.filters.every((f) => f(r)));
          hit.forEach((r) => Object.assign(r, q.payload));
          return { data: hit.map((r) => ({ key: r.key })), error: null };
        },
      };
      return api;
    },
  };
}

test("acquireLock: first wins, second within 6h refused, after 6h ok", async () => {
  const sb = fakeSupabase();
  const t0 = new Date("2026-11-11T03:00:00Z");
  assert.equal(await acquireLock(sb, "comm_write", "banto", t0), true);
  assert.equal(await acquireLock(sb, "comm_write", "hawk", new Date("2026-11-11T05:00:00Z")), false);
  assert.equal(await acquireLock(sb, "reply_211", "hawk", new Date("2026-11-11T05:00:00Z")), true);
  assert.equal(await acquireLock(sb, "comm_write", "hawk", new Date("2026-11-11T09:00:01Z")), true);
  assert.match(sb.rows.get("recovery_lock:comm_write").value, /"actor":"hawk"/);
});
