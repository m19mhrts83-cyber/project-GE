import test from "node:test";
import assert from "node:assert/strict";
import { workTotals, parseWorkHistory, appendWorkEntry } from "../lib/kamiooyaWorkHistory.ts";

test("confirmed correction replaces estimated time without counting agent time as owner work", () => {
  const event = { id: "old", item_id: "a", at: "2026-11-01T12:00:00+09:00", actor: "Chappy", summary: "記録", kind: "log", minutes: 30, time_kind: "estimated", evidence: [] };
  const events = [event, { ...event, id: "confirmed", time_kind: "owner_confirmed", minutes: 20, supersedes: "old" }, { ...event, id: "agent", time_kind: "agent_elapsed", minutes: 60 }, { ...event, id: "unknown", time_kind: "unrecorded", minutes: null }];
  assert.deepEqual(workTotals(events), { confirmed: 20, estimated: 0, agent: 60, unrecorded: 1 });
});

test("missing history and malformed history are distinguishable", () => {
  assert.equal(parseWorkHistory(null), null);
  assert.throws(() => parseWorkHistory('{"version":1,"projects":[{"id":"p"}]}'));
});

const history = { version: 1, updated_at: null, projects: [{id:"p",title:"案件",estimate_minutes:null,items:[{id:"a",title:"項目",status:"running"}],events:[]}] };
const input = { projectId:"p",itemId:"a",eventId:"original",summary:"実行",minutes:"30",timeKind:"estimated",workDate:"2026-11-01",evidence:"",supersedes:"",questionId:"",status:"",correctionReason:"本人確認" };

test("manual correction preserves original and replaces estimated with confirmed time", () => {
  const original = appendWorkEntry(history, input);
  const corrected = appendWorkEntry(original, {...input,eventId:"correction",supersedes:"original",minutes:"20",timeKind:"owner_confirmed",summary:"本人確認で20分に訂正"});
  assert.equal(original.projects[0].events.length, 1);
  assert.equal(corrected.projects[0].events.length, 2);
  assert.equal(workTotals(corrected.projects[0].events).confirmed, 20);
  assert.equal(workTotals(corrected.projects[0].events).estimated, 0);
  assert.equal(appendWorkEntry(corrected, {...input,eventId:"correction",supersedes:"original",minutes:"20",timeKind:"owner_confirmed",summary:"本人確認で20分に訂正"}).projects[0].events.length, 2);
  assert.throws(() => appendWorkEntry(corrected, {...input,eventId:"correction"}), /保存済み/);
  assert.throws(() => appendWorkEntry(corrected,{...input,eventId:"stale",supersedes:"original"}), /訂正済み/);
});

test("manual input validates time, dates, links, and the target item", () => {
  for (const fields of [{minutes:"-1"},{minutes:"NaN"},{minutes:"1.5"},{minutes:"1441"},{workDate:"2026-02-30"},{evidence:"javascript:alert(1)"},{evidence:"https://user:pass@example.com"},{summary:" "},{itemId:"missing"}]) {
    assert.throws(() => appendWorkEntry(history,{...input,...fields}));
  }
  const unknown = appendWorkEntry(history,{...input,minutes:""});
  assert.equal(unknown.projects[0].events[0].minutes,null);
  assert.equal(unknown.projects[0].events[0].time_kind,"unrecorded");
});

test("a question can be answered once and is tied to the correct item", () => {
  const h = structuredClone(history);
  h.projects[0].events.push({id:"question",at:"2026-11-01T00:00:00Z",item_id:"a",kind:"ask",summary:"時間？",actor:"Chappy",minutes:null,time_kind:"unrecorded",evidence:[]});
  const answered = appendWorkEntry(h,{...input,questionId:"question"});
  assert.equal(answered.projects[0].events[1].kind,"answer");
  assert.throws(() => appendWorkEntry(answered,{...input,eventId:"second",questionId:"question"}),/回答済み/);
});
