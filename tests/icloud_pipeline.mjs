import fs from 'node:fs';
import assert from 'node:assert/strict';
import {run} from './scriptable_harness.mjs';

const installedCode=fs.readFileSync(process.argv[2],'utf8');
const packets=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
const files=new Map();
async function render(cloudData,extra={}) {
  const result=await run({installedCode,cloudData,initialFiles:files,...extra});
  assert.equal(result.requests.length,0,'iCloud installation must never call HTTP');
  return JSON.stringify(result.widget);
}
for(const family of ['small','medium','large']) {
  const view=await render(packets.good,{family});
  assert(view.includes('$18.25'));
  if(family!=='small') assert(view.includes('75%'));
}
const failed=await render(packets.failed);
assert(failed.includes('75%'));
assert(failed.includes('采集失败'));
assert(failed.includes('$18.25'));
assert((await render(packets.recovered)).includes('40%'));
assert((await render(packets.good)).includes('40%'),'older cloud must not roll cache back');
assert((await render(null,{cloudError:true})).includes('40%'),'offline must retain data');
assert(!(await render(packets.restricted)).includes('Claude 订阅'));
assert(!(await render(packets.empty)).includes('$18.25'));
assert(!(await render(null,{cloudError:true})).includes('$18.25'),'revoked scope must remain empty offline');
console.log('Installed iCloud pipeline passed.');
