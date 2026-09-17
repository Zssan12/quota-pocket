const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const readStorage = key => { try { return localStorage.getItem(key); } catch { return null; } };
const writeStorage = (key, value) => { try { localStorage.setItem(key, value); } catch {} };
let demo = new URLSearchParams(location.search).get('demo') === '1';
let token = readStorage('qp-access') || '';
const fragment = new URLSearchParams(location.hash.slice(1));
if (fragment.has('access')) { token = fragment.get('access'); writeStorage('qp-access', token); history.replaceState(null, '', location.pathname + location.search); }
let snapshot = null, view = 'overview', filter = 'all', offline = false, timer, admin = false, loadSequence = 0;
let subscriptionStates={}, subscriptionAdmin=false, subscriptionPolling=false;
let widgets = {platform:'ios', theme:'light', filter:'all', size:'medium'};
let widgetDraft = null, widgetDirty = false, widgetAdmin = false, widgetSaving = false;
const names = {'cc-switch':'CC Switch',codex:'ChatGPT 订阅',claude:'Claude 订阅',codexbar:'CodexBar'};
function toast(message) { $('#toast').textContent = message; $('#toast').hidden = false; clearTimeout(timer); timer = setTimeout(() => $('#toast').hidden = true, 4800); }
function age(timestamp) { if (!timestamp || !Number.isFinite(Date.parse(timestamp))) return '尚未采集'; const seconds = Math.max(0,(Date.now()-Date.parse(timestamp))/1000); if(seconds<60)return '刚刚'; if(seconds<3600)return `${Math.floor(seconds/60)} 分钟前`; if(seconds<86400)return `${Math.floor(seconds/3600)} 小时前`; return `${Math.floor(seconds/86400)} 天前`; }
function clock(timestamp) { if(!timestamp || !Number.isFinite(Date.parse(timestamp)))return '—'; return new Date(timestamp).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit',hour12:false}); }
function resetLabel(timestamp) { if(!timestamp || !Number.isFinite(Date.parse(timestamp)))return '平台未提供重置时间'; const date=new Date(timestamp); const delta=date-Date.now(); if(delta<0)return '重置时间已到 · 等待平台确认'; const today=date.toDateString()===new Date().toDateString(); return `${today?'今天':date.toLocaleDateString('zh-CN',{month:'numeric',day:'numeric'})} ${clock(timestamp)} 重置`; }
function stale(r) { return offline || r.status==='stale' || r.status==='error' || (!!r.lastSuccessAt && Date.now()-Date.parse(r.lastSuccessAt) > (snapshot?.staleAfterSeconds||1230)*1000); }
function remaining(w) { return typeof w?.remainingPercent==='number' ? Math.round(w.remainingPercent) : null; }
function amount(balance) { const symbols={CNY:'¥',USD:'$',EUR:'€',GBP:'£'}; const unit=symbols[balance.unit]||balance.unit; const value=Number(balance.value).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}); return {unit,value}; }
async function api(path, options={}) { const response=await fetch(path,{...options,headers:{'Authorization':`Bearer ${token}`,...(options.body?{'Content-Type':'application/json'}:{}),...options.headers},cache:'no-store'}); const body=await response.json(); if(!response.ok){ const error=new Error(body.error||'请求失败'); error.status=response.status; throw error; } return body; }
function renderCard(r, wallet=false) { const icon=r.app==='claude'?'✳':r.windows?.length?'◈':'↗'; const bad=stale(r); let body='';
  for(const w of r.windows||[]){const value=remaining(w); body+=`<div class="quota-window ${value!==null&&value<=20?'low':''}"><div class="window-label"><span>${escape(w.label)}</span><b>${value===null?'—':value}<small>${value===null?'未知':'%'}</small></b></div>${value===null?'':`<progress value="${value}" max="100" aria-label="${escape(w.label)}剩余 ${value}%"></progress>`}<div class="window-note">${escape(resetLabel(w.resetAt))}</div></div>`;}
  for(const [i,b] of (r.balances||[]).entries()){ const a=amount(b); body+=`<div class="${i===0?'balance-main':'balance-extra'}"><small>${escape(a.unit)}</small>${escape(a.value)}</div><div class="balance-label">${escape(b.label)}</div>`; }
  if(!body) body='<p class="unknown-line">暂未获取到额度</p>';
  return `<article class="quota-card ${wallet?'balance-card':''} ${r.app==='claude'?'claude':''} ${bad?'stale':''}"><div class="card-heading"><span class="source-logo ${r.app==='claude'?'claude-logo':'codex-logo'}">${icon}</span><div><div class="card-name">${escape(r.name)}${r.plan?`<small>${escape(r.plan)}</small>`:''}</div><div class="card-subtitle">${escape(r.source)}${r.app?' · '+escape(r.app):''}</div></div>${r.active?'<span class="active-badge">已配置</span>':''}</div>${body}${r.error?`<p class="card-error">${escape(r.error)}</p>`:''}<div class="card-footer"><span><span class="tiny-dot"></span>${offline?'离线快照':bad?'上次成功数据':'平台额度'}</span><span>${escape(age(r.lastSuccessAt))}</span></div></article>`;
}
function widgetMarkup(rows) { const chosen=rotateWidgetRows(rows.filter(r=>widgets.filter==='all'||r.app===widgets.filter).filter(r=>r.windows?.length||r.balances?.length),2); let text=`<div class="widget-brand"><span>◈ 额度口袋</span><span>${demo?'示例':'只读'}</span></div>`;
  if(!chosen.length) return text+'<div class="widget-line"><small>暂无选中的账户</small></div>';
  for(const r of chosen){const w=r.windows?.[0]; const value=remaining(w); const balance=r.balances?.[0]; const a=balance?amount(balance):null; text+=`<div class="widget-line"><div>${escape(r.name)}<small>${escape(w?.label||balance?.label||'额度')}${stale(r)?' · 旧数据':''}</small></div><b>${w?value===null?'—':value+'%':escape(a.unit+a.value)}</b></div>${value!==null&&w?`<progress value="${value}" max="100"></progress>`:''}`;}
  const dates=chosen.map(r=>r.lastSuccessAt).filter(Boolean).sort();return text+`<div class="widget-time"><span>${chosen.some(stale)?'△ 含旧数据':'平台返回'}</span><span>采集 ${clock(dates[0])}</span></div>`;
}
function widgetResetLabel(value){
  const stamp=typeof value==='string'?Date.parse(value):NaN;
  if(!Number.isFinite(stamp))return '重置时间未提供';
  const date=new Date(stamp),today=date.toDateString()===new Date().toDateString();
  const time=String(date.getHours()).padStart(2,'0')+':'+String(date.getMinutes()).padStart(2,'0');
  return (today?'今天':(date.getMonth()+1)+'/'+date.getDate())+' '+time+(stamp<=Date.now()?' 已到 · 待确认':' 重置');
}
function rotateWidgetRows(rows,capacity,now=Date.now()) {
  if(rows.length<=capacity||capacity<=0)return rows.slice(0,capacity);
  const pages=Math.ceil(rows.length/capacity);
  const offset=(Math.floor(now/(15*60*1000))%pages)*capacity;
  return rows.slice(offset,offset+capacity);
}
function phoneWidgetMarkup(rows) {
  const limits={small:1,medium:2,large:4};
  const eligible=rows.filter(r=>widgets.filter==='all'||r.app===widgets.filter);
  const chosen=rotateWidgetRows(eligible,limits[widgets.size]);
  const pages=Math.ceil(eligible.length/limits[widgets.size]);
  const pageLabel=pages>1?' · '+(Math.floor(Date.now()/900000)%pages+1)+'/'+pages+' 组':'';
  const cards=chosen.map(r=>{
    const windows=(r.windows||[]).slice(0,2);
    let body=windows.map(w=>{const value=remaining(w);return `<div class="size-window"><span>${escape(w.label)}</span><b>${value===null?'—':value+'%'}</b></div>${value===null?'':`<progress value="${value}" max="100"></progress>`}<small class="size-reset">${escape(widgetResetLabel(w.resetAt))}</small>`;}).join('');
    if(!windows.length&&r.balances?.length){const a=amount(r.balances[0]);body=`<b class="size-balance">${escape(a.unit+a.value)}</b><small>${escape(r.balances[0].label)}</small>`;}
    return `<div class="size-account"><strong title="${escape(r.name)}">${escape(r.name)}</strong><small class="size-app">${escape(({codex:"Codex",claude:"Claude Code",gemini:"Gemini CLI"}[r.app]||r.app||"API"))}</small>${body||'<small>额度未知</small>'}<small class="size-capture ${stale(r)?'size-warning':''}">${stale(r)?'旧数据 · ':'采集于 '}${escape(age(r.lastSuccessAt))}</small></div>`;
  }).join('');
  const dates=chosen.map(r=>r.lastSuccessAt).filter(Boolean).sort();
  return `<div class="size-brand">◈ 额度口袋${demo?' · 示例':''}${pageLabel}</div><div class="size-accounts">${cards||'<small>暂无选中的账户</small>'}</div>`;
}
function selectedWidgetIds() {
  return widgetDirty ? widgetDraft : (snapshot?.widgetProviderIds ?? (snapshot?.providers||[]).map(r=>r.id));
}
function selectedWidgetRows(rows) {
  const byId=new Map(rows.map(r=>[r.id,r]));
  return selectedWidgetIds().map(id=>byId.get(id)).filter(Boolean);
}
function renderWidgetSelection() {
  const rows=snapshot?.providers||[], byId=new Map(rows.map(r=>[r.id,r])), chosen=selectedWidgetIds();
  const ordered=[...chosen,...rows.map(r=>r.id).filter(id=>!chosen.includes(id))];
  const enabled=(demo||widgetAdmin)&&!widgetSaving;
  $('#widget-accounts').innerHTML=ordered.map(id=>{
    const r=byId.get(id), index=chosen.indexOf(id), checked=index>=0;
    const name=r?.name||'暂不可用的已选账户';
    return `<div class="widget-choice"><label><input type="checkbox" data-widget-account="${escape(id)}" ${checked?'checked':''} ${enabled?'':'disabled'}><span><b>${escape(name)}</b><small>${r?escape((r.app||'')+' · '+r.source):'当前数据源中未找到；可取消选择'}</small></span></label><span class="widget-order">${checked?index+1:'—'}</span><div class="widget-moves"><button type="button" data-widget-id="${escape(id)}" data-widget-move="up" aria-label="上移 ${escape(name)}" ${enabled&&index>0?'':'disabled'}>↑</button><button type="button" data-widget-id="${escape(id)}" data-widget-move="down" aria-label="下移 ${escape(name)}" ${enabled&&checked&&index<chosen.length-1?'':'disabled'}>↓</button></div></div>`;
  }).join('')||'<p class="widget-selection-note">连接真实数据源后，这里会列出可选账户。</p>';
  $('#widget-selection-status').textContent=demo?'演示选择只改变预览，不会发送到手机。':!widgetAdmin?'请用电脑端管理凭证连接，手机只读凭证不能修改。':widgetDirty?`已选 ${chosen.length} 个，尚未保存；左侧为待保存预览。`:`已选 ${chosen.length} 个；作为首次默认 / HTTPS 顺序，不覆盖手机选择。`;
  $('#save-widget-selection').disabled=demo||!widgetAdmin||!widgetDirty||widgetSaving;
  $('#save-widget-selection').textContent=widgetSaving?'正在保存…':'保存电脑默认值';
  $('#widget-select-all').disabled=!enabled;$('#widget-select-none').disabled=!enabled;
}
function editWidgetSelection(ids) {widgetDraft=ids;widgetDirty=true;render();}
async function loadWidgetPermission() {
  widgetAdmin=false;renderWidgetSelection();
  if(demo||!token)return;
  const expectedToken=token;
  try{await api('/api/widget-settings');if(!demo&&token===expectedToken)widgetAdmin=true;}catch{}
  renderWidgetSelection();if(typeof renderSetup==='function')renderSetup();
}
function render(){
  $('#demo-note').hidden=!demo;$('#mode-badge').textContent=demo?'演示模式':offline?'离线快照':'本机模式';$('#mode-toggle').textContent=demo?'使用真实数据':'查看演示';
  const all=snapshot?.providers||[];const rows=all.filter(r=>filter==='all'||r.app===filter);$('#stat-accounts').textContent=all.length||'0';$('#stat-attention').textContent=all.filter(r=>stale(r)||(r.windows||[]).some(w=>remaining(w)!==null&&remaining(w)<=20)).length+(snapshot?.sources||[]).filter(s=>s.error).length;$('#stat-interval').innerHTML=snapshot?.cacheOnly?'跟随 <small>CC Switch</small>':`${Math.round((snapshot?.intervalSeconds||300)/60)} <small>分钟</small>`;$('#stat-updated').textContent=clock(snapshot?.lastCollectionAt);$('#provider-count').textContent=all.length;
  const subscriptions=rows.filter(r=>r.windows?.length||!r.balances?.length);const balances=rows.filter(r=>!r.windows?.length&&r.balances?.length);$('#providers').innerHTML=subscriptions.map(r=>renderCard(r)).join('')+(balances.length?'<div class="group-label">API PROVIDERS</div><div class="balance-grid">'+balances.map(r=>renderCard(r,true)).join('')+'</div>':'');
  if(all.length&&!rows.length)$('#providers').innerHTML='<div class="no-match">这个工具还没有已连接的额度。</div>';
  $('#empty').hidden=!snapshot||!!all.length;$('#source-errors').innerHTML=(snapshot?.sources||[]).filter(s=>s.error).map(s=>`<div class="source-error"><b>${escape(names[s.id]||s.id)}</b>${escape(s.error)}</div>`).join('');
  if(offline)$('#source-errors').insertAdjacentHTML('afterbegin',demo?'<div class="source-error">示例暂时不可用，请稍后重试。</div>':'<div class="source-error">暂时无法连接电脑，当前为本机缓存，不代表实时额度。</div>');
  const widgetRows=selectedWidgetRows(all);$('#mini-widget').innerHTML=widgetMarkup(widgetRows);$('#phone-widget').innerHTML=phoneWidgetMarkup(widgetRows);$('#phone-widget').className=`phone-widget size-${widgets.size}${widgets.theme==='dark'?' dark':''}`;$('.phone').dataset.widgetSize=widgets.size;
  renderWidgetSelection();if(typeof renderSetup==='function')renderSetup();
  if(typeof renderICloudAccounts==='function')renderICloudAccounts();
  $('#widget-size-note').textContent=({small:'单格 · 1 个账户，每个窗口都有重置时间',medium:'2 格 · 2 个账户并排，每个窗口都有重置时间',large:'4 格 · 最多 4 个账户，每个窗口都有重置时间'})[widgets.size];
  $('#access-note').hidden=demo||!!token;
  if(!snapshot){for(const id of ['stat-accounts','stat-attention','stat-interval','provider-count'])$('#'+id).textContent='—';}
  const busy=!!snapshot?.refreshing;$('#refresh').classList.toggle('refreshing',busy);$('#refresh').disabled=busy||(!demo&&!token);$('#refresh span:last-child').textContent=busy?'正在采集':'刷新额度';
}
async function load(){
  const sequence=++loadSequence; const wasDemo=demo;
  try { if(!demo&&!token){snapshot=null;render();return;}
    const incoming=wasDemo?await (await fetch('/api/demo')).json():await api('/api/snapshot');if(sequence!==loadSequence||wasDemo!==demo)return;snapshot=incoming;offline=false;if(!demo)writeStorage('qp-snapshot',JSON.stringify(snapshot));render();
    if(snapshot.refreshing)setTimeout(load,1500);
  }catch(error){if(sequence!==loadSequence||wasDemo!==demo)return;if(error.status===401){token='';writeStorage('qp-access','');writeStorage('qp-snapshot','');snapshot=null;toast('连接凭证已失效，请重新连接。');}else{offline=true;if(demo){if(!snapshot?.demo)snapshot=null;}else{try{snapshot=JSON.parse(readStorage('qp-snapshot'));}catch{snapshot=null;}}}render();}
}
function setDemo(value){demo=value;offline=false;snapshot=null;widgetDraft=null;widgetDirty=false;widgetAdmin=false;render();history.replaceState(null,'',location.pathname+(demo?'?demo=1':''));load();if((view==='sources'||view==='setup')){loadSettings();loadSubscriptions();}if(view==='widget')loadWidgetPermission();}
function showView(name){if(name==='sources')name='setup';view=name;$$('.view').forEach(el=>el.hidden=el.id!==`view-${name}`);$$('.nav-item').forEach(el=>el.classList.toggle('selected',el.dataset.view===name));$('#crumb').textContent={overview:'额度总览',widget:'组件预览',setup:'一步步配置',sources:'连接数据源'}[name];if(name==='sources'){loadSettings();loadSubscriptions();if(typeof loadRuntime==='function')loadRuntime();}if(name==='setup'&&typeof enterSetup==='function')enterSetup();if(name==='widget')loadWidgetPermission();window.scrollTo({top:0,behavior:'instant'});}
$$('[data-view]').forEach(el=>el.addEventListener('click',()=>showView(el.dataset.view)));
$$('[data-filter]').forEach(el=>el.addEventListener('click',()=>{filter=el.dataset.filter;$$('[data-filter]').forEach(b=>b.classList.toggle('active',b===el));render();}));
$('#mode-toggle').onclick=()=>setDemo(!demo);$('#exit-demo').onclick=()=>{setDemo(false);showView('sources');};$('#try-demo').onclick=()=>setDemo(true);
$('#connect-button').onclick=()=>$('#connect-dialog').showModal();$('#connect-inline').onclick=()=>$('#connect-dialog').showModal();$('.dialog-close').onclick=()=>$('#connect-dialog').close();
$('#connect-form').onsubmit=async event=>{event.preventDefault();const candidate=$('#access-token').value.trim();const previous=token;token=candidate;try{await api('/api/snapshot');writeStorage('qp-access',token);$('#access-token').value='';$('#connect-dialog').close();setDemo(false);toast('设备已连接');if((view==='sources'||view==='setup'))loadSettings();}catch(error){token=previous;toast(error.message);}};
$('#refresh').onclick=async()=>{if(demo){await load();toast('示例已刷新；没有查询真实账户。');return;}if(!token){$('#connect-dialog').showModal();return;}try{const result=await api('/api/refresh',{method:'POST'});toast(result.started?'正在向数据源读取最新额度…':'采集已在进行，或刚刚完成，请稍后查看。');await load();}catch(error){toast(error.message);}};
async function loadSettings(){const form=$('#settings-form');admin=false;try{if(demo)throw Object.assign(new Error('演示模式不修改数据源，点击“连接我的额度”开始。'),{demo:true});if(!token)throw new Error('请先点击右上角 Q，输入本机管理凭证。');const settings=await api('/api/settings');admin=true;form.dataset.managedCodex=String(!!settings.sources.codex?.managed);form.dataset.managedClaude=String(!!settings.sources.claude?.managed);for(const key of Object.keys(names)){form.elements.namedItem(key).checked=!!settings.sources[key]?.enabled;$('#detect-'+key).textContent=settings.sources[key]?.managed?'请在上方账号列表逐个管理':settings.detected[key]?'已检测到本机数据源':'未检测到 · 可配置后再启用';}form.elements.ccSwitchMode.value=settings.ccSwitchMode;form.elements.ccSwitchAllowProxyFakeIp.checked=settings.ccSwitchAllowProxyFakeIp===true;form.elements.ccSwitchSnapshotPath.value=settings.ccSwitchSnapshotPath;form.dataset.snapshotAvailable=String(settings.ccSwitchSnapshotAvailable);form.elements.intervalSeconds.value=String(settings.intervalSeconds);form.elements.publicUrl.value=settings.publicUrl;$('#mobile-connection-status').textContent=settings.publicUrl?(settings.publicUrl.includes('.trycloudflare.com')?'已保存临时连接 · 直接生成二维码即可；隧道重建换址后需重新配对。':'已保存连接 · 直接生成二维码即可，无需重复输入地址。'):'尚未设置 HTTPS 入口 · iCloud 模式无需配置。';$('#settings-note').textContent='保存后读取所选数据源，不修改原工具配置。';}catch(error){$('#settings-note').textContent=error.message;$('#mobile-connection-status').textContent=demo?'演示模式无需配置手机连接。':'连接管理端后显示已保存的手机连接。';}form.querySelector('button[type=submit]').disabled=!admin;syncSourceToggles();}
function syncSourceToggles(){
 const form=$('#settings-form');const cached=form.elements.ccSwitchMode.value==='snapshot';$('#cc-fake-ip-label').hidden=cached||!form.elements.namedItem('cc-switch').checked;form.elements.ccSwitchAllowProxyFakeIp.disabled=!admin;const bridge=cached&&form.elements.namedItem('cc-switch').checked;const barControl=form.elements.namedItem('codexbar');barControl.disabled=bridge;if(bridge)barControl.checked=false;
 for(const key of ['codex','claude']){const control=form.elements.namedItem(key);const managed=form.dataset[key==='codex'?'managedCodex':'managedClaude']==='true';control.disabled=managed||bridge||barControl.checked;if(!managed&&control.disabled)control.checked=false;}
 $('#cc-path-label').hidden=!cached;$('#cc-mode-note').textContent=cached?(form.dataset.snapshotAvailable==='true'?'已发现快照文件；每 5 秒检查本地文件变化，额度时间沿用 CC Switch 原始记录。':'等待快照：官方 CC Switch 尚无导出入口，需要随项目提供的源码补丁。此模式不会请求 Provider，也不会自动回退。'):'新配置默认每 5 分钟重新请求平台。若 CC Switch 自身也在查询，会重复请求；建议只保留一个查询方。';
} 
for(const key of ['codexbar','cc-switch','ccSwitchMode'])$('#settings-form').elements.namedItem(key).onchange=syncSourceToggles;
$('#settings-form').onsubmit=async event=>{event.preventDefault();if(!admin)return;const form=event.currentTarget;const sources=Object.fromEntries(Object.keys(names).map(k=>[k,form.elements.namedItem(k).checked]));const button=form.querySelector('button[type=submit]');button.disabled=true;try{await api('/api/settings',{method:'POST',body:JSON.stringify({sources,ccSwitchAllowProxyFakeIp:form.elements.ccSwitchAllowProxyFakeIp.checked,ccSwitchMode:form.elements.ccSwitchMode.value,ccSwitchSnapshotPath:form.elements.ccSwitchSnapshotPath.value,intervalSeconds:Number(form.elements.intervalSeconds.value),})});toast('设置已保存，开始读取额度。');showView('setup');await load();}catch(error){toast(error.message);}finally{button.disabled=false;}};
$$('[data-platform]').forEach(el=>el.onclick=()=>{widgets.platform=el.dataset.platform;$$('[data-platform]').forEach(b=>b.classList.toggle('active',b===el));$('#ios-steps').hidden=widgets.platform!=='ios';$('#android-steps').hidden=widgets.platform!=='android';$('#setup-title').textContent=widgets.platform==='ios'?'添加到 iPhone 桌面':'添加到 Android 桌面';});
$('#widget-filter').onchange=event=>{widgets.filter=event.target.value;render();};$('#widget-theme').onchange=event=>{widgets.theme=event.target.value;render();};
$('#widget-size').onchange=event=>{widgets.size=event.target.value;render();};
$('#widget-select-all').onclick=()=>editWidgetSelection((snapshot?.providers||[]).map(r=>r.id));
$('#widget-select-none').onclick=()=>editWidgetSelection([]);
$('#widget-accounts').onchange=event=>{
  const input=event.target.closest('[data-widget-account]');if(!input||(!demo&&!widgetAdmin))return;
  const ids=selectedWidgetIds().filter(id=>id!==input.dataset.widgetAccount);
  if(input.checked)ids.push(input.dataset.widgetAccount);editWidgetSelection(ids);
};
$('#widget-accounts').onclick=event=>{
  const button=event.target.closest('[data-widget-move]');if(!button||button.disabled||(!demo&&!widgetAdmin))return;
  const ids=[...selectedWidgetIds()], index=ids.indexOf(button.dataset.widgetId), next=index+(button.dataset.widgetMove==='up'?-1:1);
  if(index<0||next<0||next>=ids.length)return;[ids[index],ids[next]]=[ids[next],ids[index]];editWidgetSelection(ids);
};
$('#save-widget-selection').onclick=async()=>{
  if(demo||!widgetAdmin||widgetSaving)return;widgetSaving=true;renderWidgetSelection();
  try{const result=await api('/api/widget-settings',{method:'POST',body:JSON.stringify({providerIds:selectedWidgetIds()})});widgetDraft=null;widgetDirty=false;if(snapshot)snapshot.widgetProviderIds=result.providerIds;toast('已保存电脑默认值。手机已有选择不受影响；在 Scriptable 中调整展示账户。');await load();}
  catch(error){toast(error.message);}finally{widgetSaving=false;render();}
};
let installLink='', installExpiry=0;
$('#create-install').onclick=async()=>{
  if(demo){toast('演示模式不能配对，请先连接真实数据。');return;}
  const button=$('#create-install');button.disabled=true;
  try{
    const result=await api('/api/pair',{method:'POST'});installLink=result.url;installExpiry=Date.now()+result.expiresIn*1000;
    const qr=qrcode(0,'M');qr.addData(installLink);qr.make();
    $('#install-qr').src=qr.createDataURL(4,16);$('#install-share').hidden=false;
    $('#install-expiry').textContent='用 iPhone 相机扫码。10 分钟内有效，只能连接一次；请勿公开分享此二维码。';
    $('#copy-install-link').disabled=false;
    toast('安装二维码已生成，手机扫码即可继续。');
  }catch(error){toast(error.message);}finally{button.disabled=false;}
};
$('#copy-install-link').onclick=async()=>{
  if(Date.now()>=installExpiry){toast('链接已过期，请重新生成。');return;}
  try{await navigator.clipboard.writeText(installLink);toast('已复制安装链接，发到自己的手机打开。');}catch{toast('复制失败，请用手机相机扫描二维码。');}
};
setInterval(()=>{if(installExpiry && Date.now()>=installExpiry){$('#install-share').hidden=true;installLink='';installExpiry=0;}},1000);
$('#copy-connection').onclick=async()=>{if(demo){toast('演示模式没有手机访问凭证，请先连接真实数据。');return;}try{const info=await api('/api/connection');if(!info.url){$('#connection-hint').textContent='尚未设置 HTTPS 地址。请在“连接数据源”页面填写手机可访问的地址。';toast('先配置手机可访问的 HTTPS 地址。');return;}const text=JSON.stringify(info);await navigator.clipboard.writeText(text);$('#connection-hint').textContent='已复制只读连接信息。在 Scriptable 首次运行时粘贴即可。';toast('已复制；请只粘贴到自己的手机，不要公开分享。');}catch(error){toast(error.message||'无法复制，请使用本机 --pair 命令。');}};
$('#revoke').onclick=async()=>{if(demo){toast('演示模式没有连接设备。');return;}if(!confirm('撤销当前手机只读凭证？已连接手机需要重新配对。'))return;try{await api('/api/revoke',{method:'POST'});$('#install-share').hidden=true;installLink='';installExpiry=0;toast('旧凭证已撤销，可重新复制连接信息。');}catch(error){toast(error.message);}};
function renderSubscriptions(){
  for(const kind of ['codex','claude']){
    const state=subscriptionStates[kind]||{}, busy=['starting','waiting','saving'].includes(state.state), accounts=state.accounts||[];
    const start=$(`[data-subscription-start="${kind}"]`),cancel=$(`[data-subscription-cancel="${kind}"]`),link=$(`#subscription-${kind}-link`);
    start.disabled=demo||!subscriptionAdmin||busy;
    start.textContent=busy?'正在授权…':'添加 '+(kind==='codex'?'ChatGPT':'Claude')+' 账号';
    $(`#subscription-${kind}-name`).disabled=demo||!subscriptionAdmin||busy;
    cancel.hidden=!busy;cancel.disabled=!subscriptionAdmin;
    const count=accounts.filter(a=>a.connected).length, enabled=accounts.filter(a=>a.enabled).length;
    $(`#subscription-${kind}-badge`).textContent=busy?'等待授权':accounts.length?`${count} 个已连接 · ${enabled} 个采集`:'未连接';
    $(`#subscription-${kind}-status`).textContent=demo?'演示模式不会启动真实登录。':!subscriptionAdmin?'请在电脑管理端连接。':(busy&&state.accountName?'正在授权「'+state.accountName+'」。':'')+(state.message||'添加账号不会替换已有账号。');
    const list=$(`#subscription-${kind}-accounts`),signature=JSON.stringify([accounts,demo,subscriptionAdmin,busy]);
    if(list.dataset.state!==signature){
    list.innerHTML=accounts.length?accounts.map(account=>{
      const locked=demo||!subscriptionAdmin||busy, disabled=locked?'disabled':'';
      const status=!account.connected?'登录凭证不可用，请重新授权':!account.enabled?'已停用，凭证保留':account.quotaError?'查询失败：'+account.quotaError:'已启用采集';
      return `<div class="subscription-account"><div class="subscription-account-info"><strong>${escape(account.name)}</strong><small>${escape(status)}</small></div><div class="subscription-account-actions"><button type="button" class="text-button" data-account-action="rename" data-account-id="${escape(account.id)}" ${disabled}>修改备注</button><button type="button" class="text-button" data-account-action="toggle" data-account-id="${escape(account.id)}" ${disabled}>${account.enabled?'停用':'启用'}</button><button type="button" class="text-button" data-account-action="reauthorize" data-account-id="${escape(account.id)}" ${disabled}>重新授权</button></div></div>`;
    }).join(''):'<p class="subscription-empty">还没有账号。点击下方按钮添加第一个账号。</p>';
    list.dataset.state=signature;
    }
    let safe=false;try{const u=new URL(state.authUrl);safe=u.protocol==='https:'&&!u.username&&!u.password&&(kind==='codex'?['auth.openai.com']:['claude.ai','claude.com','platform.claude.com','console.anthropic.com']).includes(u.hostname);}catch{}
    link.hidden=!busy||!safe;if(safe)link.href=state.authUrl;else link.removeAttribute('href');
  }
  $('#claude-code-entry').hidden=!subscriptionAdmin||subscriptionStates.claude?.state!=='waiting';
}
async function loadSubscriptions(){
  if(subscriptionPolling)return;
  if(demo||!token){subscriptionStates={};subscriptionAdmin=false;renderSubscriptions();return;}
  const expectedToken=token;subscriptionPolling=true;
  try{
    const incoming=await api('/api/subscriptions');if(demo||token!==expectedToken)return;
    const newlyConnected=['codex','claude'].some(k=>incoming[k].state==='connected'&&subscriptionStates[k]?.state!=='connected');
    subscriptionStates=incoming;subscriptionAdmin=true;renderSubscriptions();
    if(newlyConnected){await loadSettings();await load();}
  }catch(error){if(token===expectedToken){subscriptionAdmin=false;renderSubscriptions();$('#subscription-note').textContent=error.message;}}
  finally{subscriptionPolling=false;}
}
$$('[data-subscription-start]').forEach(button=>button.onclick=async()=>{
  if(demo||!subscriptionAdmin)return;button.disabled=true;
  const kind=button.dataset.subscriptionStart;
  try{subscriptionStates=await api(`/api/subscriptions/${kind}/start`,{method:'POST',body:JSON.stringify({name:$(`#subscription-${kind}-name`).value.trim()})});$(`#subscription-${kind}-name`).value='';$('#claude-auth-code').value='';renderSubscriptions();await loadSubscriptions();}
  catch(error){toast(error.message);renderSubscriptions();}
});
for(const kind of ['codex','claude'])$(`#subscription-${kind}-accounts`).onclick=async event=>{
  const button=event.target.closest('[data-account-action]');if(!button||button.disabled||demo||!subscriptionAdmin)return;
  const account=(subscriptionStates[kind]?.accounts||[]).find(a=>a.id===button.dataset.accountId);if(!account)return;
  const action=button.dataset.accountAction;let endpoint='update',body={accountId:account.id};
  if(action==='rename'){
    const name=prompt('账号备注（会同步到手机，请勿填密钥）',account.name);if(name===null)return;body.name=name.trim();
  }else if(action==='toggle')body.enabled=!account.enabled;
  else if(action==='reauthorize'){endpoint='start';$('#claude-auth-code').value='';}else return;
  button.disabled=true;
  try{
    subscriptionStates=await api(`/api/subscriptions/${kind}/${endpoint}`,{method:'POST',body:JSON.stringify(body)});
    renderSubscriptions();await loadSettings();await load();
    if(endpoint==='update')toast(action==='rename'?'备注已保存':body.enabled?'账号已启用':'账号已停用，登录凭证保留');
  }catch(error){toast(error.message);}
  finally{button.disabled=false;renderSubscriptions();}
};
$$('[data-subscription-cancel]').forEach(button=>button.onclick=async()=>{
  const kind=button.dataset.subscriptionCancel;button.disabled=true;
  try{subscriptionStates=await api(`/api/subscriptions/${kind}/cancel`,{method:'POST',body:JSON.stringify({id:subscriptionStates[kind]?.id})});$('#claude-auth-code').value='';renderSubscriptions();}
  catch(error){toast(error.message);renderSubscriptions();}
});
$('#submit-claude-code').onclick=async()=>{
  const button=$('#submit-claude-code'),field=$('#claude-auth-code');button.disabled=true;
  try{subscriptionStates=await api('/api/subscriptions/claude/finish',{method:'POST',body:JSON.stringify({id:subscriptionStates.claude?.id,code:field.value.trim()})});field.value='';renderSubscriptions();toast('已提交授权码，正在等待登录完成。');}
  catch(error){field.value='';toast(error.message);}finally{button.disabled=false;}
};
setInterval(()=>{if((view==='sources'||view==='setup')&&!document.hidden)loadSubscriptions();},2500);
renderSubscriptions();
if(!demo){try{snapshot=JSON.parse(readStorage('qp-snapshot'));if(snapshot)offline=true;}catch{}}
render();load();setInterval(()=>{if(!document.hidden)load();},30000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)load();});
if(['widget','sources'].includes(new URLSearchParams(location.search).get('view')))showView(new URLSearchParams(location.search).get('view'));
if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
