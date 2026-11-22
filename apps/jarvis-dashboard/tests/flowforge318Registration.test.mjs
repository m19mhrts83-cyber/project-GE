import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {findFlowRef} from '../lib/flowforgeAgentRef.ts';
test('318 registry projection and shares resolve to the flow', () => {
  const team = JSON.parse(readFileSync(new URL('../data/agentTeam.json', import.meta.url), 'utf8'));
  const shares = JSON.parse(readFileSync(new URL('../../../config/flowforge_share_urls.json', import.meta.url), 'utf8'));
  const a = team.agents.filter((x) => x.id === '318');
  assert.equal(a.length, 1);
  assert.equal(a[0].flowforge_id, 'flow_HMy15MUxWiSpw5QgAPYa_8e4');
  assert.ok(a[0].flowforge_share_url.endsWith('/share/DJc5DtKvcq5ZgjiV'));
  assert.equal(shares.by_agent_id['318'], a[0].flowforge_share_url);
  assert.equal(shares.by_flow_id[a[0].flowforge_id], a[0].flowforge_share_url);
  const ref = findFlowRef(team.agents, '318');
  assert.equal(ref?.flowId ?? ref?.flowforge_id, 'flow_HMy15MUxWiSpw5QgAPYa_8e4');
});
