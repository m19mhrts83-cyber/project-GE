import assert from "node:assert/strict";
import test from "node:test";
import { MAX_ITEMS, enqueue, validateBody, validateItem } from "../lib/commIntake.ts";
import { actorForKey } from "../lib/jobRecovery.ts";

const now = new Date("2026-11-11T09:00:00Z");
const ok = {
  bot: "grok",
  bot_item_id: "bucho-20261111-01",
  kind: "property",
  occurred_at: "2026-11-11T08:30:00+09:00",
  title: "東郷町 戸建て 新着",
  summary: "要確認",
  refs: { url: "https://example.com/x" },
  source: "Grok部長日報",
};

test("intake keys use the same verification as the recovery endpoint", () => {
  const raw = `grok:${"g".repeat(32)}`;
  assert.equal(actorForKey("g".repeat(32), raw), "grok");
  assert.equal(actorForKey("h".repeat(32), raw), null);
});

test("validateItem accepts a good item and normalizes occurred_at", () => {
  const v = validateItem(ok, "grok", now);
  assert.equal(v.ok, true);
  assert.equal(v.value.payload.occurred_at, "2026-11-10T23:30:00.000Z");
  assert.equal(validateItem({ ...ok, bot: undefined }, "grok", now).ok, true);
});

test("validateItem keeps topic and needs_action only when given", () => {
  const v = validateItem({ ...ok, kind: "agent", topic: "Repair_Vendor", needs_action: true }, "grok", now);
  assert.equal(v.ok, true);
  assert.equal(v.value.payload.topic, "repair_vendor");
  assert.equal(v.value.payload.needs_action, true);
  const w = validateItem(ok, "grok", now);
  assert.equal("topic" in w.value.payload, false);
  assert.equal("needs_action" in w.value.payload, false);
});

test("validateItem rejects bad shapes", () => {
  const bad = [
    { ...ok, bot: "hawk" }, // 鍵の送り手と違う
    { ...ok, bot_item_id: "has space" },
    { ...ok, bot_item_id: "" },
    { ...ok, kind: "bank" },
    { ...ok, occurred_at: "yesterday" },
    { ...ok, occurred_at: "2026-11-20T00:00:00Z" }, // 未来
    { ...ok, title: "" },
    { ...ok, title: "x".repeat(301) },
    { ...ok, summary: "x".repeat(4001) },
    { ...ok, refs: [] },
    { ...ok, refs: { a: "x".repeat(5000) } },
    { ...ok, topic: "Bad Topic" },
    { ...ok, topic: "x".repeat(41) },
    { ...ok, needs_action: "yes" },
    null,
    [ok],
  ];
  for (const b of bad) assert.equal(validateItem(b, "grok", now).ok, false, JSON.stringify(b)?.slice(0, 60));
});

test("validateBody: single, batch, limit, all-or-nothing, in-batch duplicates collapse", () => {
  assert.equal(validateBody(ok, "grok", now).items.length, 1);
  const two = validateBody({ items: [ok, { ...ok, bot_item_id: "b2" }, ok] }, "grok", now);
  assert.equal(two.items.length, 2);
  const mixed = validateBody({ items: [ok, { ...ok, kind: "x" }] }, "grok", now);
  assert.equal(mixed.ok, false);
  assert.equal(mixed.index, 1);
  const many = Array.from({ length: MAX_ITEMS + 1 }, (_, i) => ({ ...ok, bot_item_id: `i${i}` }));
  assert.equal(validateBody({ items: many }, "grok", now).ok, false);
  assert.equal(validateBody({ items: [] }, "grok", now).ok, false);
});

function fakeSupabase() {
  const rows = [];
  return {
    rows,
    from() {
      const q = { op: null, payload: null, f: [] };
      const api = {
        upsert(p) { q.op = "upsert"; q.payload = p; return api; },
        select() {
          if (q.op === "upsert") {
            const created = [];
            for (const r of q.payload) {
              if (rows.some((x) => x.source_bot === r.source_bot && x.bot_item_id === r.bot_item_id)) continue;
              const row = { ...r, id: `id-${rows.length + 1}` };
              rows.push(row);
              created.push({ id: row.id });
            }
            return Promise.resolve({ data: created, error: null });
          }
          q.op = "select";
          return api;
        },
        eq(c, v) { q.f.push((r) => r[c] === v); return api; },
        in(c, vs) { q.f.push((r) => vs.includes(r[c])); return api; },
        then(res) { return res({ data: rows.filter((r) => q.f.every((f) => f(r))), error: null }); },
      };
      return api;
    },
  };
}

test("enqueue is idempotent: duplicates are accepted with the existing id", async () => {
  const sb = fakeSupabase();
  const items = validateBody({ items: [ok, { ...ok, bot_item_id: "b2" }] }, "grok", now).items;
  const a = await enqueue(sb, "grok", items);
  assert.deepEqual(a, { accepted: 2, created: 2, ids: ["id-1", "id-2"] });
  const b = await enqueue(sb, "grok", items.slice(0, 1));
  assert.deepEqual(b, { accepted: 1, created: 0, ids: ["id-1"] });
  assert.equal(sb.rows.length, 2);
  assert.equal(sb.rows[0].source_bot, "grok");
});
