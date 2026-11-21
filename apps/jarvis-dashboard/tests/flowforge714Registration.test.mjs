import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
test('714 registry projection and shares select the owned flow only',()=>{
 const team=JSON.parse(readFileSync(new URL('../data/agentTeam.json',import.meta.url),'utf8'));
 const shares=JSON.parse(readFileSync(new URL('../../../config/flowforge_share_urls.json',import.meta.url),'utf8'));
 const a=team.agents.filter(a=>a.id==='714');
 assert.equal(a.length,1);assert.equal(a[0].flowforge_id,'flow_q41qaFFwQ_pX4m6qg04oLb3H');
 assert.ok(a[0].flowforge_share_url.endsWith('/share/HI4KOYwORPb7ZG1d'));
 assert.equal(shares.by_agent_id['714'],a[0].flowforge_share_url);
 assert.equal(shares.by_flow_id[a[0].flowforge_id],a[0].flowforge_share_url);
 assert.equal(shares.by_flow_id.flow_714minutes_20261122,undefined);
 assert.equal(a[0].status,'設計中');
});
