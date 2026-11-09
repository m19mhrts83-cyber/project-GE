// node --experimental-strip-types --test tests/decideStore.test.ts
// 共有DBへの保存（成功・失敗・送り直し・判断の変更）を偽の Supabase で確かめる。ネットワーク不要。
import { test } from "node:test";
import assert from "node:assert/strict";
import { persistDecision, DEDUPE_313_MS } from "../lib/decideStore.ts";

type Row = Record<string, unknown>;

function fakeSb(fail: Record<string, string> = {}) {
  const db: Record<string, Row[]> = {
    task_loop_topics: [],
    task_loop_proposals: [],
    task_loop_decisions: [],
    owner_decisions: [],
  };
  let seq = 0;
  function q(table: string) {
    let rows = () => db[table];
    const filters: [string, unknown][] = [];
    let orderCol: string | null = null;
    let desc = false;
    let lim = Infinity;
    let pendingInsert: Row[] | null = null;
    const api: Record<string, unknown> = {};
    const result = () => {
      const err = fail[table] ? { message: fail[table] } : null;
      if (pendingInsert) {
        if (err) return { data: null, error: err };
        for (const r of pendingInsert) {
          r.id ??= `${table}-${++seq}`;
          r.created_at ??= new Date().toISOString();
          if (table === "owner_decisions") r.decided_at ??= new Date().toISOString();
          db[table].push(r);
        }
        return { data: pendingInsert, error: null };
      }
      if (err) return { data: null, error: err };
      let out = rows().filter((r) => filters.every(([k, v]) => r[k] === v));
      if (orderCol) {
        const c = orderCol;
        out = [...out].sort((a, b) => String(a[c]).localeCompare(String(b[c])) * (desc ? -1 : 1));
      }
      return { data: out.slice(0, lim), error: null };
    };
    Object.assign(api, {
      select: () => api,
      eq: (k: string, v: unknown) => (filters.push([k, v]), api),
      order: (c: string, o?: { ascending?: boolean }) => ((orderCol = c), (desc = o?.ascending === false), api),
      limit: (n: number) => ((lim = n), Promise.resolve(result())),
      single: () => {
        const r = result();
        return Promise.resolve({ data: r.data ? (r.data as Row[])[0] : null, error: r.error });
      },
      insert: (r: Row | Row[]) => {
        pendingInsert = (Array.isArray(r) ? r : [r]).map((x) => ({ ...x }));
        // await insert(...) でも insert(...).select().single() でも 1 回だけ書く
        return {
          then: (ok: (v: unknown) => unknown, ng?: (e: unknown) => unknown) =>
            Promise.resolve(result()).then(ok, ng),
          select: () => ({ single: api.single }),
        };
      },
      update: (patch: Row) => ({
        eq: (k: string, v: unknown) => {
          if (fail[table]) return Promise.resolve({ error: { message: fail[table] } });
          for (const y of db[table]) if (y[k] === v) Object.assign(y, patch);
          return Promise.resolve({ error: null });
        },
      }),
      upsert: (r: Row | Row[], o?: { onConflict?: string }) => {
        if (fail[table]) return Promise.resolve({ error: { message: fail[table] } });
        const keys = (o?.onConflict || "id").split(",");
        for (const x of Array.isArray(r) ? r : [r]) {
          const i = db[table].findIndex((y) => keys.every((k) => y[k] === x[k]));
          if (i >= 0) db[table][i] = { ...db[table][i], ...x };
          else db[table].push({ id: `${table}-${++seq}`, created_at: new Date().toISOString(), ...x });
        }
        return Promise.resolve({ error: null });
      },
    });
    return api;
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return { sb: { from: q } as any, db };
}

const d312 = (choice: string, chosenIndex?: number, tags: string[] = []) => ({
  agentId: "312",
  topicText: "青葉の催促",
  seedId: "seed-aoba",
  proposals: [{ index: 1, label: "既存へ追記", body: "…" }],
  decision: { choice, chosenIndex, reasonTags: tags, decidedVia: "app" },
});

test("312: 保存できたら persisted:true、topic・proposal・decision が1件ずつ", async () => {
  const { sb, db } = fakeSb();
  const r = await persistDecision(sb, d312("use", 1));
  assert.equal(r.persisted, true);
  assert.equal(r.via, "task_loop");
  assert.equal(db.task_loop_topics.length, 1);
  assert.equal(db.task_loop_proposals.length, 1);
  assert.equal(db.task_loop_decisions.length, 1);
});

test("312: 同じ判断の送り直しは増やさない（deduped）", async () => {
  const { sb, db } = fakeSb();
  await persistDecision(sb, d312("use", 1, ["既にある"]));
  const r = await persistDecision(sb, d312("use", 1, ["既にある"]));
  assert.equal(r.deduped, true);
  assert.equal(db.task_loop_topics.length, 1);
  assert.equal(db.task_loop_proposals.length, 1);
  assert.equal(db.task_loop_decisions.length, 1);
});

test("312: 判断を変えたら1行のまま、前の判断は history に残る", async () => {
  const { sb, db } = fakeSb();
  await persistDecision(sb, d312("use", 1));
  const r = await persistDecision(sb, d312("none_of_above", undefined, ["違う"]));
  assert.equal(r.persisted, true);
  assert.equal(r.deduped, undefined);
  assert.equal(db.task_loop_topics.length, 1);
  assert.equal(db.task_loop_decisions.length, 1);
  const row = db.task_loop_decisions[0];
  assert.equal(row.choice, "none_of_above");
  const h = row.history as Row[];
  assert.equal(h.length, 1);
  assert.equal(h[0].choice, "use");
});

test("312 本物のお題: id で引き、3案は上書きせず、決めたら status=decided", async () => {
  const { sb, db } = fakeSb();
  db.task_loop_topics.push({ id: "t-live", agent_id: "312", topic_text: "[Slack] 315健全化", status: "open", source_kind: "slack" });
  db.task_loop_proposals.push({ id: "p1", topic_id: "t-live", proposal_index: 3, label: "別タスクを作る", body: "タイトル：315健全化", prompt_version: "rule-v1" });
  const r = await persistDecision(sb, {
    agentId: "312",
    topicDbId: "t-live",
    topicText: "（画面の文と違っても id で引く）",
    proposals: [{ index: 3, label: "別タスクを作る", body: "上書きしない" }],
    decision: { choice: "use", chosenIndex: 3, finalText: "タイトル：315健全化", decidedVia: "app" },
  });
  assert.equal(r.persisted, true);
  assert.equal(r.topicId, "t-live");
  assert.equal(db.task_loop_topics.length, 1);
  assert.equal(db.task_loop_topics[0].status, "decided");
  assert.equal(db.task_loop_proposals[0].body, "タイトル：315健全化");
  assert.equal(db.task_loop_proposals[0].prompt_version, "rule-v1");
  assert.equal(db.task_loop_decisions[0].reflected_todoist_id, null);
});

test("312 本物のお題: 見つからない id は persisted:false", async () => {
  const { sb } = fakeSb();
  const r = await persistDecision(sb, { agentId: "312", topicDbId: "nope", decision: { choice: "use", chosenIndex: 1 } });
  assert.equal(r.persisted, false);
});

test("312: 反映済みの Todoist id は決め直しても残し、「反映しない」印は空に戻す", async () => {
  const { sb, db } = fakeSb();
  await persistDecision(sb, d312("use", 1));
  db.task_loop_decisions[0].reflected_todoist_id = "-";
  await persistDecision(sb, d312("use", 3));
  assert.equal(db.task_loop_decisions[0].reflected_todoist_id, null);
  db.task_loop_decisions[0].reflected_todoist_id = "todo-123";
  await persistDecision(sb, d312("edit_use", 3));
  assert.equal(db.task_loop_decisions[0].reflected_todoist_id, "todo-123");
});

test("312: 書き込み失敗は persisted:false（成功に見せない）", async () => {
  const { sb } = fakeSb({ task_loop_decisions: "permission denied" });
  const r = await persistDecision(sb, d312("use", 1));
  assert.equal(r.persisted, false);
  assert.match(String(r.reason), /permission denied/);
});

test("312: 表が無いときも persisted:false", async () => {
  const { sb } = fakeSb({ task_loop_topics: "PGRST205" });
  const r = await persistDecision(sb, d312("use", 1));
  assert.equal(r.persisted, false);
});

const d313 = (choice: string, tags: string[] = []) => ({
  agentId: "313",
  topicText: "保険の更新",
  seedId: "7001",
  todoistTaskId: "7001",
  decision: { choice, reasonTags: tags, decidedVia: "app" },
});

test("313: 1判断1行、payload に理由タグと todoist_applied:false", async () => {
  const { sb, db } = fakeSb();
  const r = await persistDecision(sb, d313("close", ["済んだ"]));
  assert.equal(r.persisted, true);
  assert.equal(db.owner_decisions.length, 1);
  const p = db.owner_decisions[0].payload as Row;
  assert.deepEqual(p.reason_tags, ["済んだ"]);
  assert.equal(p.todoist_applied, false);
  assert.equal(db.owner_decisions[0].target_id, "7001");
});

test("313: 10分以内の同じ判断は増やさない／別の判断は残す", async () => {
  const { sb, db } = fakeSb();
  const t0 = new Date();
  await persistDecision(sb, d313("close"), t0);
  const again = await persistDecision(sb, d313("close"), new Date(t0.getTime() + 1000));
  assert.equal(again.deduped, true);
  assert.equal(db.owner_decisions.length, 1);
  await persistDecision(sb, d313("reschedule"), new Date(t0.getTime() + 2000));
  assert.equal(db.owner_decisions.length, 2);
});

test("313: 10分を過ぎた同じ判断は新しい行（意図した再判断）", async () => {
  const { sb, db } = fakeSb();
  await persistDecision(sb, d313("close"));
  const later = new Date(Date.now() + DEDUPE_313_MS + 1000);
  const r = await persistDecision(sb, d313("close"), later);
  assert.equal(r.deduped, undefined);
  assert.equal(db.owner_decisions.length, 2);
});

test("313: 書き込み失敗は persisted:false", async () => {
  const { sb } = fakeSb({ owner_decisions: "PGRST205 no table" });
  const r = await persistDecision(sb, d313("close"));
  assert.equal(r.persisted, false);
});

test("decision が無ければ ok:false", async () => {
  const { sb } = fakeSb();
  const r = await persistDecision(sb, { agentId: "312" });
  assert.equal(r.ok, false);
});
