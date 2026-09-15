// Scriptable contract tests; real iOS rendering requires an iPhone.
import assert from 'node:assert/strict';
import {run,snapshot,token,key} from './scriptable_harness.mjs';
for(const [family,cols,rows] of [['small',1,1],['medium',2,1],['large',2,2]]){
 const {widget}=await run({family});const lines=widget.children.filter(c=>c instanceof Object&&c.size?.height>0);
 assert.equal(lines.length,rows);const cells=lines.flatMap(line=>line.children.filter(c=>c.size));assert.equal(cells.length,cols*rows);
 assert(cells.every(c=>c.size.width===cells[0].size.width&&c.size.height===cells[0].size.height));
 for(const c of cells){assert.equal(c.children[0].spacer,'flex');assert.equal(c.children.at(-1).spacer,'flex');}
}
const migration=await run({legacy:true});assert(migration.secrets.has(key));
const isolated=await run({name:'Another computer'});assert.equal(isolated.requests.length,0);assert.equal(isolated.files.size,0);
const denied=await run({status:401});assert.equal(denied.files.size,0);assert(JSON.stringify(denied.widget).includes('需要重新配对'));
const paired=await run({pair:true});assert.equal(paired.requests[0].method,'POST');assert.equal(paired.requests[0].url,'https://quota.example/api/pair/exchange');assert.equal(paired.requests[1].headers.Authorization,'Bearer '+token);
console.log('Scriptable contracts passed: equal cells, centered groups, isolation, migration, revoked access, link exchange. Native rendering still needs iPhone validation.');

for(const family of ['small','medium','large']){
 const launched=await run({tap:family,tapOptions:'claude,dark'});
 assert.equal(launched.menus,1);assert.deepEqual(launched.previews,[family]);
 assert(launched.widget.url.startsWith('scriptable:///run/Quota%20Pocket?'));
 const query=new URL(launched.widget.url).searchParams;
 assert.equal(query.get('preview'),family);assert.equal(query.get('options'),'claude,dark');
 assert(!launched.widget.url.includes(token));assert(!launched.widget.url.includes('quota.example'));
 assert.equal(launched.requests[0].headers.Authorization,'Bearer '+token);
}
console.log('Widget tap preserves size/filter/theme, skips the launch menu, offers local editing after preview, and carries no endpoint or credentials.');

const cloudConfig={relativePath:'QuotaPocket/install_123/snapshot.json',installationId:'install_123'};
const cloudRead=await run({icloud:cloudConfig});
assert.equal(cloudRead.requests.length,0);assert(JSON.stringify(cloudRead.widget).includes('Provider 0'));
assert.deepEqual(cloudRead.cloudDownloads,[]);
assert([...cloudRead.files.keys()].some(path=>path.includes('install_123')));
const cloudIgnoresPair=await run({icloud:cloudConfig,pair:true});
assert.equal(cloudIgnoresPair.requests.length,0);

const cachedFiles=new Map([['/test/quota-pocket-cache-v2-install_123.json',JSON.stringify({cacheId:'install_123',snapshot})]]);
const cloudOffline=await run({icloud:cloudConfig,cloudError:true,initialFiles:cachedFiles});
assert.equal(cloudOffline.requests.length,0);assert(JSON.stringify(cloudOffline.widget).includes('iCloud 待同步 · 本机快照'));
assert(!JSON.stringify(cloudOffline.widget).includes('旧数据 · '));
const wrongCache=new Map([['/test/quota-pocket-cache-v2-install_123.json',JSON.stringify({cacheId:'another_install',snapshot})]]);
const isolatedCloud=await run({icloud:cloudConfig,cloudError:true,initialFiles:wrongCache});
assert(!JSON.stringify(isolatedCloud.widget).includes('Provider 0'));

for(const malformed of [
 {...snapshot,demo:true}, {...snapshot,schemaVersion:2}, {...snapshot,providers:{}},
 {...snapshot,generatedAt:'not-a-date'}, {...snapshot,providers:[{...snapshot.providers[0],lastSuccessAt:'bad'}]}
]) {
 const result=await run({icloud:cloudConfig,cloudData:malformed});
 assert.equal(result.requests.length,0);assert(!JSON.stringify(result.widget).includes('Provider 0'));
}
const traversal=await run({icloud:{...cloudConfig,relativePath:'QuotaPocket/../snapshot.json'}});
assert.equal(traversal.requests.length,0);assert(JSON.stringify(traversal.widget).includes('iCloud 安装配置无效'));
const staleSnapshot={...snapshot,providers:snapshot.providers.map(r=>({...r,lastSuccessAt:'2020-01-01T00:00:00Z'}))};
const stale=await run({icloud:cloudConfig,cloudData:staleSnapshot});
assert(JSON.stringify(stale.widget).includes('旧数据 · '));
// App and widget can see different iCloud download availability. A download
// failure must not discard a readable file or label a fresh local cache stale.
const readableWithoutDownload=await run({icloud:cloudConfig,cloudError:true,cloudReadError:false});
assert(JSON.stringify(readableWithoutDownload.widget).includes('Provider 0'));
assert(!JSON.stringify(readableWithoutDownload.widget).includes('iCloud 待同步'));
assert.equal(readableWithoutDownload.cloudDownloads.length,0);
const needsDownload=await run({icloud:cloudConfig,cloudDownloaded:false});
assert.equal(needsDownload.cloudDownloads.length,1);
assert(JSON.stringify(needsDownload.widget).includes('Provider 0'));

const olderSnapshot={...staleSnapshot,generatedAt:'2020-01-01T00:00:00Z',providers:staleSnapshot.providers.map(r=>({...r,name:'Old '+r.name}))};
const cacheFile='/test/quota-pocket-cache-v2-install_123.json';
const freshSnapshot={...snapshot,providers:snapshot.providers.map(r=>({...r,name:'Fresh '+r.name}))};
const savedFresh=()=>new Map([[cacheFile,JSON.stringify({cacheId:'install_123',snapshot:freshSnapshot})]]);
const cloudBehindFiles=savedFresh();
const cloudBehind=await run({icloud:cloudConfig,cloudData:olderSnapshot,initialFiles:cloudBehindFiles});
assert(JSON.stringify(cloudBehind.widget).includes('Fresh Provider 0'));
assert(!JSON.stringify(cloudBehind.widget).includes('Old Provider 0'));
assert.equal(JSON.parse(cloudBehindFiles.get(cacheFile)).snapshot.generatedAt,freshSnapshot.generatedAt);

const cacheUnwritable=await run({icloud:cloudConfig,cloudData:freshSnapshot,cacheWriteError:true,
 initialFiles:new Map([[cacheFile,JSON.stringify({cacheId:'install_123',snapshot:olderSnapshot})]])});
assert(JSON.stringify(cacheUnwritable.widget).includes('Fresh Provider 0'));
assert(JSON.stringify(cacheUnwritable.widget).includes('本机缓存未保存'));
assert(!JSON.stringify(cacheUnwritable.widget).includes('旧数据 · '));
assert(!JSON.stringify(cacheUnwritable.widget).includes('iCloud 暂不可读'));

const appThenWidgetFiles=new Map();
await run({icloud:cloudConfig,cloudData:freshSnapshot,tap:'medium',initialFiles:appThenWidgetFiles});
const afterApp=await run({icloud:cloudConfig,cloudError:true,initialFiles:appThenWidgetFiles});
assert(JSON.stringify(afterApp.widget).includes('Fresh Provider 0'));
assert(!JSON.stringify(afterApp.widget).includes('旧数据 · '));
const offlineOld=await run({icloud:cloudConfig,cloudError:true,
 initialFiles:new Map([[cacheFile,JSON.stringify({cacheId:'install_123',snapshot:olderSnapshot})]])});
assert(JSON.stringify(offlineOld.widget).includes('旧数据 · '));
console.log('iCloud contracts passed: validated read-only snapshots, zero HTTP requests, isolated offline cache, malformed/traversal rejection, and source-timestamp staleness.');

const mobileSnapshot=(defaults=['0','1'],available=snapshot.providers)=>({...snapshot,
 mobileSelectionVersion:1,availableProviders:available,defaultProviderIds:defaults});
const preference=id=>'/test/quota-pocket-mobile-selection-v1-'+encodeURIComponent(id)+'.json';

const firstMobileFiles=new Map();
const firstMobile=await run({icloud:cloudConfig,cloudData:mobileSnapshot(),initialFiles:firstMobileFiles});
assert.deepEqual(JSON.parse(firstMobileFiles.get(preference('install_123'))).providerIds,['0','1']);
assert(JSON.stringify(firstMobile.widget).includes('Provider 0'));
assert(!JSON.stringify(firstMobile.widget).includes('Provider 2'));

const changedDefaults=await run({icloud:cloudConfig,cloudData:mobileSnapshot(['3']),initialFiles:firstMobileFiles});
assert.deepEqual(JSON.parse(firstMobileFiles.get(preference('install_123'))).providerIds,['0','1']);
assert(JSON.stringify(changedDefaults.widget).includes('Provider 0'));
assert(!JSON.stringify(changedDefaults.widget).includes('Provider 3'));

const emptyFiles=new Map([[preference('install_123'),JSON.stringify({version:1,providerIds:[]})]]);
const explicitlyEmpty=await run({icloud:cloudConfig,cloudData:mobileSnapshot(['0']),initialFiles:emptyFiles});
assert.deepEqual(JSON.parse(emptyFiles.get(preference('install_123'))).providerIds,[]);
assert(!JSON.stringify(explicitlyEmpty.widget).includes('Provider 0'));

const restrictedFiles=new Map([[preference('install_123'),JSON.stringify({version:1,providerIds:['restricted','2']})]]);
const restrictedRows=await run({icloud:cloudConfig,cloudData:mobileSnapshot([],snapshot.providers.slice(2)),initialFiles:restrictedFiles});
assert(JSON.stringify(restrictedRows.widget).includes('Provider 2'));
assert(!JSON.stringify(restrictedRows.widget).includes('restricted'));
assert.deepEqual(JSON.parse(restrictedFiles.get(preference('install_123'))).providerIds,['restricted','2']);

const otherConfig={relativePath:'QuotaPocket/install_456/snapshot.json',installationId:'install_456'};
await run({icloud:otherConfig,cloudData:mobileSnapshot(['3']),initialFiles:firstMobileFiles});
assert.deepEqual(JSON.parse(firstMobileFiles.get(preference('install_123'))).providerIds,['0','1']);
assert.deepEqual(JSON.parse(firstMobileFiles.get(preference('install_456'))).providerIds,['3']);

const oldFormatFiles=new Map();await run({icloud:cloudConfig,cloudData:snapshot,initialFiles:oldFormatFiles});
assert(!oldFormatFiles.has(preference('install_123')));
const failedFirstFiles=new Map();await run({icloud:cloudConfig,cloudError:true,initialFiles:failedFirstFiles});
assert(!failedFirstFiles.has(preference('install_123')));

const cachedMobileFiles=new Map([
 ['/test/quota-pocket-cache-v2-install_123.json',JSON.stringify({cacheId:'install_123',snapshot:mobileSnapshot(['1'])})],
 [preference('install_123'),JSON.stringify({version:1,providerIds:['2','0']})]
]);
const offlineMobile=await run({icloud:cloudConfig,cloudError:true,initialFiles:cachedMobileFiles});
assert(JSON.stringify(offlineMobile.widget).indexOf('Provider 2')<JSON.stringify(offlineMobile.widget).indexOf('Provider 0'));

const duplicateApps=snapshot.providers.map((r,i)=>({...r,name:i<2?'Work':r.name}));
const editorFiles=new Map([[preference('install_123'),JSON.stringify({version:1,providerIds:['0','1','2']})]]);
const editor=await run({icloud:cloudConfig,cloudData:mobileSnapshot([],duplicateApps),initialFiles:editorFiles,edit:true});
assert.equal(editor.tables.length,1);assert.equal(editor.tables[0].rows.length,5);
assert(editor.tables[0].rows[1].title.includes('Work · Codex'));
assert(editor.tables[0].rows[2].title.includes('Work · Claude Code'));
assert(editor.tables[0].rows.slice(1).every(row=>row.dismissOnSelect===false));
await editor.tables[0].rows[2].onSelect();
assert.deepEqual(JSON.parse(editorFiles.get(preference('install_123'))).providerIds,['0','2']);
await editor.tables[0].rows[3].onSelect();
assert.deepEqual(JSON.parse(editorFiles.get(preference('install_123'))).providerIds,['0','2','1']);
assert(editor.tables[0].rows[3].buttons.every(button=>button.dismissOnTap===false));
await editor.tables[0].rows[3].buttons[0].onTap();
await editor.tables[0].rows[1].buttons[0].onTap();
assert.deepEqual(JSON.parse(editorFiles.get(preference('install_123'))).providerIds,['1','0','2']);
assert(editor.tables[0].reloads>=4);

const writeFailureFiles=new Map([[preference('install_123'),JSON.stringify({version:1,providerIds:['0','1']})]]);
const writeFailure=await run({icloud:cloudConfig,cloudData:mobileSnapshot([],duplicateApps),initialFiles:writeFailureFiles,edit:true,preferenceWriteError:true});
await writeFailure.tables[0].rows[1].onSelect();
assert.deepEqual(JSON.parse(writeFailureFiles.get(preference('install_123'))).providerIds,['0','1']);
assert(writeFailure.alerts.some(alert=>alert.title==='未能保存'));assert.equal(writeFailure.tables[0].reloads||0,0);
const initialWriteFailure=await run({icloud:cloudConfig,cloudData:mobileSnapshot(['0']),initialFiles:new Map(),preferenceWriteError:true});
assert(JSON.stringify(initialWriteFailure.widget).includes('Provider 0'));

const rerenderFiles=new Map([[preference('install_123'),JSON.stringify({version:1,providerIds:['0','1']})]]);
const rerendered=await run({icloud:cloudConfig,cloudData:mobileSnapshot([],snapshot.providers),initialFiles:rerenderFiles,tap:'medium',sheetChoices:[0],onTablePresent:async table=>{await table.rows[1].buttons[0].onTap();}});
assert.equal(rerendered.setWidgets.length,2);
const rendered=JSON.stringify(rerendered.setWidgets.at(-1));assert(rendered.indexOf('Provider 1')<rendered.indexOf('Provider 0'));
assert.deepEqual(JSON.parse(rerenderFiles.get(preference('install_123'))).providerIds,['1','0']);
const gear=rerendered.widget.children[0].children.find(child=>child.url)?.url;
assert(new URL(gear).searchParams.get('preview')==='medium');assert(new URL(gear).searchParams.get('options')==='all');

console.log('Mobile account contracts passed: one-time defaults, persistent order and empty selection, restricted filtering, install isolation, offline cache, and UITable actions.');

const pendingSourceFiles=new Map();
await run({icloud:cloudConfig,cloudData:mobileSnapshot([],[]),initialFiles:pendingSourceFiles});
assert(!pendingSourceFiles.has(preference('install_123')));
await run({icloud:cloudConfig,cloudData:mobileSnapshot(['0']),initialFiles:pendingSourceFiles});
assert.deepEqual(JSON.parse(pendingSourceFiles.get(preference('install_123'))).providerIds,['0']);
console.log('First sync before source collection does not freeze an unintended empty choice.');

// Assert the rendered text and bar, not only a mapping helper.
function descendants(node){return [node,...(node.children||[]).flatMap(descendants)];}
async function quotaRender(percent, overrides={}, dark=false){
 const row={...snapshot.providers[0],status:'ok',windows:[{label:'本周',remainingPercent:percent}],...overrides};
 const result=await run({icloud:cloudConfig,cloudData:{...snapshot,providers:[row]},...(dark?{tap:'small',tapOptions:'all,dark'}:{})});
 return {result,nodes:descendants(result.widget)};
}
for(const dark of [false,true]){
 const colors=dark?['f29c98','efbf80','93bce8','9dcb91']:['b53b38','996019','326b9e','397345'];
 for(const [percent,index] of [[0,0],[10,0],[10.1,1],[30,1],[30.1,2],[60,2],[60.1,3],[100,3]]){
  const {nodes}=await quotaRender(percent,{},dark);
  const label=nodes.find(n=>n.value===Math.round(percent)+'%');
  assert.equal(label.textColor.hex,colors[index]);assert.equal(label.textColor.alpha,1);
  const bar=nodes.find(n=>n.image)?.image.fills[1];
  assert.equal(bar.color.hex,colors[index]);assert.equal(bar.color.alpha,1);
  assert.equal(bar.rect.width,112*percent/100);
 }
}
for(const percent of [null,'0',-1,101]){
 const {nodes}=await quotaRender(percent);
 assert.equal(nodes.find(n=>n.value==='—').textColor.hex,'747a71');
 assert(!nodes.some(n=>n.image));
}
const aged=await quotaRender(5,{lastSuccessAt:'2020-01-01T00:00:00Z'});
assert.equal(aged.nodes.find(n=>n.value==='5%').textColor.hex,'b53b38');
assert.equal(aged.nodes.find(n=>n.value==='5%').textColor.alpha,0.65);
assert(aged.nodes.some(n=>n.value==='旧数据 · '));
for(const overrides of [{status:'error'},{status:'unknown'},{lastSuccessAt:null}]){
 const {nodes}=await quotaRender(80,overrides);
 assert.equal(nodes.find(n=>n.value==='80%').textColor.hex,'747a71');
 assert.equal(nodes.find(n=>n.image).image.fills[1].color.hex,'747a71');
}
for(const value of [0,42]){
 const {nodes}=await quotaRender(null,{windows:[],balances:[{unit:'USD',value}]});
 assert.equal(nodes.find(n=>n.value==='$'+value.toFixed(2)).textColor.hex,'30422e');
}
const invalidBalance=await quotaRender(null,{windows:[],balances:[{unit:'USD',value:null}]});
assert(invalidBalance.nodes.some(n=>n.value==='额度未知'));
assert(!invalidBalance.nodes.some(n=>n.value==='$0.00'));
console.log('Quota colors passed: light/dark thresholds, fractional boundaries, matching bars and text, stale opacity, failure/unknown gray, and neutral amount-only balances.');

const diagnostic=await run({icloud:cloudConfig,pair:true,sheetChoices:[4,-1]});
const diagnosticAlert=diagnostic.alerts.find(a=>a.title==='iCloud 同步诊断');
assert(diagnosticAlert.message.includes('读取来源：iCloud 文件'));
assert(diagnosticAlert.message.includes('读取阶段：读取成功'));
assert(diagnosticAlert.message.includes(snapshot.generatedAt.slice(0,4)));
const diagnosticOffline=await run({icloud:cloudConfig,pair:true,cloudError:true,initialFiles:savedFresh(),sheetChoices:[4,-1]});
assert(diagnosticOffline.alerts.find(a=>a.title==='iCloud 同步诊断').message.includes('iCloud 下载失败'));
assert(diagnosticOffline.alerts.find(a=>a.title==='iCloud 同步诊断').message.includes('本机缓存'));
const diagnosticRetry=await run({icloud:cloudConfig,pair:true,sheetChoices:[4,0,-1]});
assert.equal(diagnosticRetry.alerts.filter(a=>a.title==='iCloud 同步诊断').length,2);
assert.equal(diagnosticRetry.requests.length,0);
console.log('Sync diagnostics passed: source, failure stage, timestamps and local reread.');

for(const family of ['small','medium','large']){
  const quota={...snapshot.providers[0],balances:[],windows:[
    {label:'五小时额度',remainingPercent:65,resetAt:'2099-09-20T12:34:00Z'},
    {label:'每周额度',remainingPercent:40,resetAt:'2099-09-27T13:45:00Z'}]};
  const result=await run({family,icloud:cloudConfig,cloudData:{...snapshot,providers:[quota]}});
  const values=descendants(result.widget).map(n=>n.value).filter(v=>typeof v==='string');
  for(const w of quota.windows){const date=new Date(w.resetAt);const expected=(date.getMonth()+1)+'/'+date.getDate()+' '+String(date.getHours()).padStart(2,'0')+':'+String(date.getMinutes()).padStart(2,'0')+' 重置';assert(values.includes(expected),family+' must show each reset');}
  const missing=await run({family,icloud:cloudConfig,cloudData:{...snapshot,providers:[{...quota,windows:[{...quota.windows[0],resetAt:null},{...quota.windows[1],resetAt:'2020-01-01T00:00:00Z'}]}]}});
  const text=JSON.stringify(missing.widget);assert(text.includes('重置时间未提供'));assert(text.includes('已到 · 待确认'));assert(text.includes('40%'));
}
console.log('All widget sizes show each subscription window reset, including missing and elapsed states.');

for(const [family,capacity] of [['small',1],['medium',2],['large',4]]){
 for(const count of [0,1,2,3,4,5,7,8,11]){
  const providers=Array.from({length:count},(_,i)=>({...snapshot.providers[0],id:'rotation-'+i,name:'Rotate '+i,app:i%2?'claude':'codex'}));
  const data={...snapshot,mobileSelectionVersion:1,availableProviders:providers,providers,defaultProviderIds:providers.map(r=>r.id)};
  const files=new Map(),pages=Math.max(1,Math.ceil(count/capacity)),seen=[];
  for(let slot=0;slot<=pages;slot++){
   const now=slot*900000,expected=providers.slice((slot%pages)*capacity,(slot%pages+1)*capacity).map(r=>r.name);
   const output=await run({family,icloud:cloudConfig,cloudData:data,initialFiles:files,now});
   const names=descendants(output.widget).map(n=>n.value).filter(v=>typeof v==='string'&&v.startsWith('Rotate '));
   assert.deepEqual(names,expected);assert.equal(new Set(names).size,names.length);
   if(slot<pages)seen.push(...names);
   if(pages>1)assert(JSON.stringify(output.widget).includes((slot%pages+1)+'/'+pages+' 组'));
   const offline=await run({family,icloud:cloudConfig,cloudError:true,initialFiles:files,now:now+1000});
   assert.deepEqual(descendants(offline.widget).map(n=>n.value).filter(v=>typeof v==='string'&&v.startsWith('Rotate ')),expected);
   assert.equal(output.requests.length,0);
  }
  assert.deepEqual(seen,providers.map(r=>r.name));
  if(count)assert.deepEqual(JSON.parse(files.get(preference('install_123'))).providerIds,providers.map(r=>r.id));
 }
}
console.log('Rotation passed: exact groups, full coverage, wraparound, partial last group, offline and unchanged selection in all sizes.');
