// Variables used by Scriptable.
// icon-color: deep-green; icon-glyph: chart-pie;
// Quota Pocket v0.2.2 — read-only quota snapshot. No Provider credentials.
// Widget parameter: codex | claude | all (default). Add ",dark" for dark styling.
// Choose Small / Medium / Large in the iOS widget gallery; size is not a script parameter.

// An installer may prepend this constant after the Scriptable metadata:
// const ICLOUD_SOURCE = {relativePath:'QuotaPocket/<id>/snapshot.json', installationId:'<id>'};
const iCloudConfig = typeof ICLOUD_SOURCE === 'undefined' ? null : ICLOUD_SOURCE;
function validRelativeICloudPath(path) {
  return typeof path === 'string' && path.length <= 240 && !path.startsWith('/') && !path.includes('\\')
    && path.split('/').every(part => part && part !== '.' && part !== '..') && path.endsWith('/snapshot.json');
}
const validICloudConfig = iCloudConfig && typeof iCloudConfig.installationId === 'string'
  && /^[A-Za-z0-9_-]{6,100}$/.test(iCloudConfig.installationId) && validRelativeICloudPath(iCloudConfig.relativePath)
  && iCloudConfig.relativePath === 'QuotaPocket/' + iCloudConfig.installationId + '/snapshot.json';
const iCloudConfigError = iCloudConfig && !validICloudConfig;
// Different script names isolate HTTPS connections; iCloud installs use their stable installation id.
const slot = encodeURIComponent(validICloudConfig ? iCloudConfig.installationId : Script.name());
const key = 'quota-pocket.connection.v2.' + slot;
const fm = FileManager.local();
const cachePath = fm.joinPath(fm.documentsDirectory(), 'quota-pocket-cache-v2-' + slot + '.json');
let connection = validICloudConfig ? {mode:'icloud', cacheId:iCloudConfig.installationId, path:iCloudConfig.relativePath} : null;
let previewFamily = 'medium', showPreview = true;
const tappedFamily = ['small','medium','large'].includes(args.queryParameters?.preview) ? args.queryParameters.preview : null;
const editAccounts = args.queryParameters?.edit === 'accounts';
if (tappedFamily) previewFamily = tappedFamily;
try { if (!iCloudConfig && Keychain.contains(key)) connection = JSON.parse(Keychain.get(key)); } catch (_) {}

// Migrate the original installation without changing its connection.
if (!iCloudConfig && !connection && ['Quota Pocket', 'Quota-Pocket'].includes(Script.name())) {
  try { if (Keychain.contains('quota-pocket.connection.v1')) {
    connection = JSON.parse(Keychain.get('quota-pocket.connection.v1'));
    Keychain.set(key, JSON.stringify(connection));
  }} catch (_) {}
}
function validOrigin(url) {
  return typeof url === 'string' && /^https:\/\/[^\s/?#@:]+(?::[0-9]+)?\/?$/.test(url)
    && !/^https:\/\/(localhost|127\.[0-9.]+)(:|\/|$)/i.test(url);
}
async function connectLink() {
  const {url, pair:code} = args.queryParameters || {};
  if (!validOrigin(url) || !/^[A-Za-z0-9_-]{32,100}$/.test(code || '')) throw new Error('安装链接无效');
  const confirm = new Alert(); confirm.title = '连接这台电脑？';
  confirm.message = url; confirm.addAction('连接'); confirm.addCancelAction('取消');
  if (await confirm.presentAlert() < 0) return false;
  const request = new Request(url.replace(/\/$/, '') + '/api/pair/exchange');
  request.method = 'POST'; request.headers = {'Content-Type':'application/json'};
  request.body = JSON.stringify({code}); request.timeoutInterval = 15;
  const result = await request.loadJSON();
  if (request.response.statusCode !== 200 || !validOrigin(result.url) || result.url !== url.replace(/\/$/, '') || typeof result.token !== 'string' || result.token.length < 24)
    throw new Error('链接已使用或过期，请在电脑上重新生成');
  connection = {url:result.url, token:result.token, cacheId:UUID.string()};
  Keychain.set(key, JSON.stringify(connection));
  return true;
}
async function pair() {
  const prompt = new Alert();
  prompt.title = '连接额度口袋';
  prompt.message = '在电脑的“小组件”页面复制连接信息，粘贴下方。信息包含手机可访问的 HTTPS 地址和只读凭证。';
  prompt.addTextField('粘贴 {"url":"https://…","token":"…"}', '');
  prompt.addAction('连接'); prompt.addCancelAction('取消');
  if (await prompt.presentAlert() < 0) return false;
  try {
    const parsed = JSON.parse(prompt.textFieldValue(0));
    if (!validOrigin(parsed.url) || typeof parsed.token !== 'string' || parsed.token.length < 24) throw new Error('格式无效');
    connection = {url:parsed.url.replace(/\/$/, ''), token:parsed.token, cacheId:String(Date.now())};
    Keychain.set(key, JSON.stringify(connection));
    return true;
  } catch (_) {
    const alert = new Alert(); alert.title = '连接信息无效'; alert.message = '请粘贴电脑生成的完整 JSON。地址必须为 HTTPS，不能使用 localhost 或 127.0.0.1。'; alert.addAction('好'); await alert.presentAlert(); return false;
  }
}

if (!config.runsInWidget) {
  if (!iCloudConfig && args.queryParameters?.pair) {
    try { await connectLink(); } catch (error) {
      const alert = new Alert(); alert.title = '未能连接'; alert.message = String(error.message); alert.addAction('好'); await alert.presentAlert();
    }
  }
  if (!iCloudConfig && !connection && !args.queryParameters?.pair) await pair();
}

const options = String(args.widgetParameter || (tappedFamily ? args.queryParameters?.options : '') || 'all').toLowerCase().split(',').map(x=>x.trim());
const selected = options.find(x=>x==='codex'||x==='claude') || 'all';
const dark = options.includes('dark');
let family = config.runsInWidget ? (config.widgetFamily || 'medium') : previewFamily;
const palette = {bg:dark?'28392b':'f6f8ee', ink:dark?'f1f4e9':'30422e', muted:dark?'aab998':'8b977c', track:dark?'40523a':'e5ebd9', green:dark?'9dcb91':'397345', blue:dark?'93bce8':'326b9e', orange:dark?'efbf80':'996019', red:dark?'f29c98':'b53b38', unknown:dark?'b4b8b2':'747a71'};
// Home Screen widget sizes in points. Unknown/new screens use the nearest
// known width; iOS display zoom and iPad still require device validation.
function widgetDimensions(family) {
  const screen = Device.screenSize(); const width = Math.min(screen.width, screen.height);
  const resolution=Device.screenResolution(), scale=Device.screenScale();
  const pixelHeight=Math.max(resolution.width,resolution.height);
  const known={1136:[282,584,622],1334:[296,642,648],1792:[338,720,758],
    1920:[348,716,758],2208:[471,1044,1071],2340:[436,932,980],
    2436:[465,987,1035],2532:[474,1014,1062],2556:[474,1014,1062],
    2622:[486,1038,1086],2688:[507,1080,1137],2778:[510,1092,1146],
    2796:[510,1092,1146],2868:[510,1092,1146]};
  if(known[pixelHeight]){
    const [small,medium,large]=known[pixelHeight].map(x=>x/scale);
    return {width:family==='small'?small:medium,height:family==='large'?large:small};
  }
  const sizes = [[320,141,292,311],[375,155,329,345],[390,158,338,354],
    [393,158,338,354],[402,162,346,362],[414,169,360,379],
    [428,170,364,382],[430,170,364,382],[440,170,364,382]];
  let row = sizes.reduce((best,r)=>Math.abs(r[0]-width)<Math.abs(best[0]-width)?r:best);
  const small=row[1], medium=row[2], large=row[3];
  return {width:family==='small'?small:medium, height:family==='large'?large:small};
}
let dimensions = widgetDimensions(family);
let columns = family==='small'?1:2, rowCount=family==='large'?2:1;
const gap=12;let cellWidth=(dimensions.width-28-gap*(columns-1))/columns;
function validSnapshot(data, requireGeneratedAt=false) {
  if (!data || data.schemaVersion!==1 || data.demo || !Array.isArray(data.providers)) return false;
  if (requireGeneratedAt && (typeof data.generatedAt!=='string' || !Number.isFinite(Date.parse(data.generatedAt)))) return false;
  for (const field of ['generatedAt','lastCollectionAt']) if (data[field]!=null && (typeof data[field]!=='string'||!Number.isFinite(Date.parse(data[field])))) return false;
  const validRows=rows=>rows.every(r => r && typeof r==='object' && ['lastSuccessAt','lastAttemptAt'].every(field =>
    r[field]==null || (typeof r[field]==='string'&&Number.isFinite(Date.parse(r[field])))));
  return validRows(data.providers) && (data.mobileSelectionVersion!==1 || (Array.isArray(data.availableProviders)&&validRows(data.availableProviders)));
}
function mobileCandidates(data) {
  return data?.mobileSelectionVersion===1 && Array.isArray(data.availableProviders) ? data.availableProviders : null;
}
function validProviderRows(rows) {
  return Array.isArray(rows) && rows.every(r=>r&&typeof r==='object'&&typeof r.id==='string'&&typeof r.name==='string');
}
function cachedSnapshot() {
  try { const old=JSON.parse(fm.readString(cachePath)); return old && old.cacheId===connection.cacheId && validSnapshot(old.snapshot) ? old.snapshot : null; } catch (_) { return null; }
}

const preferencePath=fm.joinPath(fm.documentsDirectory(),'quota-pocket-mobile-selection-v1-'+slot+'.json');
function readMobileSelection(){
  try { const value=JSON.parse(fm.readString(preferencePath));return value?.version===1&&Array.isArray(value.providerIds)&&value.providerIds.every(id=>typeof id==='string')?value.providerIds:null; } catch(_){return null;}
}
function writeMobileSelection(providerIds){try{fm.writeString(preferencePath,JSON.stringify({version:1,providerIds}));return true;}catch(_){return false;}}
let candidates=null, mobileSelection=null;
function initializeMobileSelection(){
  candidates=mobileCandidates(snapshot);
  if(candidates&&validProviderRows(candidates)){
  mobileSelection=readMobileSelection();
  if(mobileSelection===null){
    const defaults=Array.isArray(snapshot.defaultProviderIds)&&snapshot.defaultProviderIds.every(id=>typeof id==='string')?snapshot.defaultProviderIds:[];
    mobileSelection=defaults.slice();if(candidates.length)writeMobileSelection(mobileSelection);
  }
  } else candidates=null;
}

function accountLabel(r){return r.name+' · '+({codex:'Codex',claude:'Claude Code',gemini:'Gemini CLI'}[r.app]||r.app||'API');}
async function editMobileAccounts(){
  if(!candidates){const a=new Alert();a.title='暂时无法调整';a.message='先成功读取一次支持手机选择的新快照。';a.addAction('好');await a.presentAlert();return;}
  let order=mobileSelection.slice();const table=new UITable();table.showSeparators=true;
  async function commit(next){if(!writeMobileSelection(next)){const a=new Alert();a.title='未能保存';a.message='本机存储暂不可写，展示账户没有改变。';a.addAction('好');await a.presentAlert();return false;}order=next;mobileSelection=next.slice();rebuild();table.reload();return true;}
  function rebuild(){table.removeAllRows();const info=new UITableRow();info.isHeader=true;info.addText('调整展示账户','点击勾选，用箭头排序；本机自动保存'+(selected==='all'?'':'。当前组件按 '+selected+' 筛选，跨工具展示请清空组件参数'));table.addRow(info);
    const selectedRows=order.map(id=>candidates.find(r=>r.id===id)).filter(Boolean),selectedIds=new Set(order);
    for(const provider of [...selectedRows,...candidates.filter(r=>!selectedIds.has(r.id))]){
      const index=order.indexOf(provider.id),row=new UITableRow();row.dismissOnSelect=false;
      row.height=60;const nameCell=row.addText((index<0?'○ ':index+1+'. ')+accountLabel(provider),index<0?'未展示':'正在展示');nameCell.widthWeight=6;
      row.onSelect=async()=>{const next=order.slice(),at=next.indexOf(provider.id);if(at<0)next.push(provider.id);else next.splice(at,1);await commit(next);};
      if(index>=0){if(index>0){const up=row.addButton('↑');up.widthWeight=1;up.dismissOnTap=false;up.onTap=async()=>{const next=order.slice();next.splice(index-1,0,next.splice(index,1)[0]);await commit(next);};}
        if(index<order.length-1){const down=row.addButton('↓');down.widthWeight=1;down.dismissOnTap=false;down.onTap=async()=>{const next=order.slice();next.splice(index+1,0,next.splice(index,1)[0]);await commit(next);};}}
      table.addRow(row);
    }}
  rebuild();await table.present(false);
}

async function handleScriptMenus(){
if(!config.runsInWidget&&connection&&!tappedFamily&&!editAccounts){
  const menu=new Alert();menu.title='额度口袋';menu.message='单格每组 1 个、2 格每组 2 个、4 格每组 4 个。选得更多时按 15 分钟时间段轮换，实际切换随 iOS 运行脚本。';
  menu.addAction('调整展示账户');menu.addAction('小号 · 1 个账户');menu.addAction('中号 · 2 个账户');menu.addAction('大号 · 4 个账户');menu.addAction(iCloudConfig?'同步诊断 / 重新读取':'重新配对');menu.addCancelAction('取消');
  const choice=await menu.presentSheet();
  if(choice===0){await editMobileAccounts();showPreview=false;}
  else if(choice===4&&iCloudConfig){await showSyncDiagnostics();showPreview=false;}
  else if(choice===4){await pair();showPreview=false;}
  else if(choice>=1&&choice<=3)previewFamily=['small','medium','large'][choice-1];
  else showPreview=false;
}
if(!config.runsInWidget&&editAccounts){await editMobileAccounts();showPreview=false;}
}
let snapshot = null, networkError = '', authError = false;
let readDiagnostics={source:'尚未读取',stage:'未开始'};
async function showSyncDiagnostics(){
  const time=value=>value?new Date(value).toLocaleString():'无';
  const show=()=>{
    const help=new Alert();help.title='iCloud 同步诊断';
    const rows=mobileCandidates(snapshot)||snapshot?.providers||[];
    help.message='读取来源：'+readDiagnostics.source+'\n读取阶段：'+readDiagnostics.stage+
      '\n快照生成：'+time(snapshot?.generatedAt)+'\nMac 采集完成：'+time(snapshot?.lastCollectionAt)+
      '\n'+rows.map(r=>r.name+'：'+time(r.lastSuccessAt)).join('\n')+
      '\n重新读取只检查已到达手机的数据，不能强制云同步或唤醒 Mac。';
    help.addAction('重新读取');help.addCancelAction('完成');return help;
  };
  while(await show().presentSheet()===0){await readICloudSnapshot();initializeMobileSelection();}
}

function saveSnapshot() {
  // A cache write failure must not discard a successfully read snapshot.
  try { fm.writeString(cachePath,JSON.stringify({cacheId:connection.cacheId,snapshot})); }
  catch (_) { if(!networkError)networkError='本机缓存未保存'; }
}
async function readICloudSnapshot() {
  let data=null;readDiagnostics={source:'无可用快照',stage:'读取文件'};
  try {
    const cloud=FileManager.iCloud(), path=cloud.joinPath(cloud.documentsDirectory(),connection.path);
    const read=()=>{
      let raw;
      try {raw=cloud.readString(path);}catch(_){readDiagnostics.stage='文件不可读或尚未下载';return null;}
      try{const value=JSON.parse(raw);if(!validSnapshot(value,true)){readDiagnostics.stage='快照格式无效';return null;}readDiagnostics.stage='读取成功';return value;}
      catch(_){readDiagnostics.stage='JSON 解析失败';return null;}
    };
    // iOS may let the app read iCloud while the widget cannot download. Read
    // the on-device file first; downloadFileFromiCloud only materializes files,
    // it does not force iCloud to fetch a newer remote version.
    data=read();
    if(!data){
      try { await cloud.downloadFileFromiCloud(path);data=read(); } catch (_) {readDiagnostics.stage='iCloud 下载失败';}
    }
  } catch (_) {readDiagnostics.stage='iCloud 容器不可用';}
  const cached=cachedSnapshot();
  if(!data){
    snapshot=cached;readDiagnostics.source=cached?'本机缓存':'无可用快照';
    networkError=cached?'iCloud 待同步 · 本机快照':'iCloud 暂不可读 · 请点开重试';
  } else if(cached&&Date.parse(cached.generatedAt)>Date.parse(data.generatedAt)){
    // An app preview may have cached a newer export than the widget's iCloud
    // container currently exposes. Never roll that export back.
    snapshot=cached;readDiagnostics.source='本机缓存（比 iCloud 文件新）';networkError='iCloud 同步中 · 本机快照';
  } else {
    snapshot=data;readDiagnostics.source='iCloud 文件';networkError='';saveSnapshot();
  }
}
if (connection) {
  if (connection.mode==='icloud') {
    await readICloudSnapshot();
  } else try {
      const request = new Request(connection.url + '/api/snapshot'); request.headers={Authorization:'Bearer '+connection.token};request.timeoutInterval=15;
      const data = await request.loadJSON();
      if (request.response.statusCode===401||request.response.statusCode===403){authError=true;throw new Error('凭证已撤销，请重新配对');}
      if (request.response.statusCode!==200||!validSnapshot(data)) throw new Error('无法读取真实额度');
      snapshot=data;readDiagnostics.source='iCloud 文件';networkError='';saveSnapshot();
    } catch(error) {
      networkError=authError?'凭证已撤销 · 请重新配对':'电脑暂不可达 · 旧快照';
      if(!authError)snapshot=cachedSnapshot();
    }
}

initializeMobileSelection();
await handleScriptMenus();
if(!config.runsInWidget){family=previewFamily;dimensions=widgetDimensions(family);columns=family==='small'?1:2;rowCount=family==='large'?2:1;cellWidth=(dimensions.width-28-gap*(columns-1))/columns;}
function text(stack,value,size=10,bold=false,color=palette.ink){const t=stack.addText(String(value));t.font=bold?Font.semiboldSystemFont(size):Font.systemFont(size);t.textColor=color instanceof Color?color:new Color(color);t.lineLimit=1;t.minimumScaleFactor=0.7;return t;}
function centered(stack, render) { const line=stack.addStack();line.size=new Size(cellWidth,0);line.centerAlignContent();line.addSpacer();render(line);line.addSpacer();return line; }
function centerText(stack,value,size=10,bold=false,color=palette.ink) {centered(stack,line=>text(line,value,size,bold,color).centerAlignText());}
// Freshness and collection failures are independent of remaining allowance.
function validPercent(value){return typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<=100;}
function quotaColor(percent){return !validPercent(percent)?palette.unknown:percent<=10?palette.red:percent<=30?palette.orange:percent<=60?palette.blue:palette.green;}
function readingColor(r,percent=null){
  const failed=r.status==='error'||r.status==='unknown'||!r.lastSuccessAt||!Number.isFinite(Date.parse(r.lastSuccessAt));
  return new Color(failed?palette.unknown:percent===null?palette.ink:quotaColor(percent),!failed&&isStale(r)?0.65:1);
}
function meter(stack,percent,color){const width=Math.min(112,cellWidth-16);const draw=new DrawContext();draw.size=new Size(width,4);draw.opaque=false;draw.respectScreenScale=true;draw.setFillColor(new Color(palette.track));draw.fillRect(new Rect(0,0,width,4));draw.setFillColor(color);draw.fillRect(new Rect(0,0,width*Math.max(0,Math.min(100,percent))/100,4));centered(stack,line=>{const image=line.addImage(draw.getImage());image.imageSize=new Size(width,4);});}
function isStale(r){return r.status==='error'||r.status==='stale'||!r.lastSuccessAt||!Number.isFinite(Date.parse(r.lastSuccessAt))||Date.now()-Date.parse(r.lastSuccessAt)>(snapshot.staleAfterSeconds||1230)*1000;}
// A widget can hold fewer cells than the phone selection. Rotate whole account
// groups on a fixed 15-minute wall-clock slot so every selected source appears
// without changing the saved order or the exported snapshot.
function rotateForCapacity(rows, capacity, now=Date.now()){
  if(rows.length<=capacity||capacity<=0)return rows.slice(0,capacity);
  const pages=Math.ceil(rows.length/capacity);
  const offset=(Math.floor(now/(15*60*1000))%pages)*capacity;
  return rows.slice(offset,offset+capacity);
}
function resetText(value){
  const stamp=typeof value==='string'?Date.parse(value):NaN;
  if(!Number.isFinite(stamp))return '重置时间未提供';
  const date=new Date(stamp),today=date.toDateString()===new Date().toDateString();
  const time=String(date.getHours()).padStart(2,'0')+':'+String(date.getMinutes()).padStart(2,'0');
  return (today?'今天':(date.getMonth()+1)+'/'+date.getDate())+' '+time+(stamp<=Date.now()?' 已到 · 待确认':' 重置');
}
function drawAccount(stack,r){
  stack.layoutVertically();stack.addSpacer();
  centerText(stack,r.name,12,true);stack.addSpacer(2);
  if(!r.windows?.length)centerText(stack,({codex:'Codex',claude:'Claude Code',gemini:'Gemini CLI'}[r.app]||r.app||'API'),7,false,palette.muted);stack.addSpacer(3);
  if(r.windows&&r.windows.length){for(const w of r.windows.slice(0,2)){
    const percent=validPercent(w.remainingPercent)?w.remainingPercent:null;
    const value=percent===null?null:Math.round(percent),color=percent===null?new Color(palette.unknown):readingColor(r,percent);
    centered(stack,line=>{text(line,w.label,8,false,palette.muted);line.addSpacer(5);text(line,value===null?'—':value+'%',11,true,color);});
    stack.addSpacer(1);if(percent!==null)meter(stack,percent,color);stack.addSpacer(1);
    centerText(stack,resetText(w.resetAt),7,false,palette.muted);stack.addSpacer(3);
  }}else if(r.balances&&r.balances.length){const b=r.balances[0];
    const validBalance=typeof b.value==='number'&&Number.isFinite(b.value);
    centerText(stack,validBalance?({CNY:'¥',USD:'$',EUR:'€'}[b.unit]||b.unit+' ')+b.value.toFixed(2):'额度未知',24,true,validBalance?readingColor(r):new Color(palette.unknown));
    stack.addSpacer(3);centerText(stack,b.label||'余额',8,false,palette.muted);stack.addSpacer(5);
  }else {centerText(stack,'额度未知',10,false,palette.muted);stack.addSpacer(5);}
  centered(stack,updated=>{
    text(updated,r.status==='error'?'采集失败 · ':r.status==='unknown'?'额度未知 · ':isStale(r)?'旧数据 · ':'采集于 ',7,false,palette.muted);
    if(r.lastSuccessAt&&Number.isFinite(Date.parse(r.lastSuccessAt))){const date=updated.addDate(new Date(r.lastSuccessAt));date.applyRelativeStyle();date.font=Font.systemFont(7);date.textColor=new Color(palette.muted);}else text(updated,'尚未成功',7,false,palette.muted);
  });
  stack.addSpacer();
}

function renderWidget(){const widget=new ListWidget();widget.backgroundColor=new Color(palette.bg);widget.setPadding(12,14,10,14);widget.refreshAfterDate=new Date(Date.now()+5*60*1000);
widget.url='scriptable:///run/'+encodeURIComponent(Script.name())+'?preview='+family+'&options='+encodeURIComponent(selected+(dark?',dark':''));
const head=widget.addStack();head.centerAlignContent();const title=head.addText('◈ 额度口袋');title.font=Font.semiboldSystemFont(11);title.textColor=new Color(palette.ink);head.addSpacer();
const label=head.addText('⚙ 调整');label.font=Font.systemFont(8);label.textColor=new Color(palette.muted);label.url='scriptable:///run/'+encodeURIComponent(Script.name())+'?edit=accounts&preview='+family+'&options='+encodeURIComponent(selected+(dark?',dark':''));widget.addSpacer(7);
const displaySource=candidates?mobileSelection.map(id=>candidates.find(r=>r.id===id)).filter(Boolean):(snapshot?.providers||[]);
const eligible=displaySource.filter(r=>selected==='all'||r.app===selected),capacity=family==='small'?1:family==='medium'?2:4;
const rows=rotateForCapacity(eligible,capacity);
const pages=Math.ceil(eligible.length/capacity);
if(pages>1){title.text='◈ '+(Math.floor(Date.now()/900000)%pages+1)+'/'+pages+' 组';} 
if(iCloudConfigError){text(widget,'iCloud 安装配置无效',11,true);widget.addSpacer(5);text(widget,'请在 Mac 上重新生成此安装脚本。',9,false,palette.muted);}
else if(!connection){text(widget,'在 Scriptable 中运行脚本',11,true);widget.addSpacer(5);text(widget,'配对后，把真实额度带到桌面。',9,false,palette.muted);}
else if(!rows.length){const noSelection=candidates&&candidates.length&&mobileSelection.length===0;text(widget,authError?'需要重新配对':noSelection?'尚未选择展示账户':'还没有可用的额度',11,true);widget.addSpacer(6);text(widget,networkError||(noSelection?'运行脚本 → 调整展示账户':candidates&&candidates.length?'检查手机选择与组件的工具筛选参数':snapshot?.sources?.find(s=>s.error)?.error||'在电脑上连接数据源后再刷新。'),9,false,palette.muted);}
else {
  // Equal boxes, including vacant slots: names and values never determine column width.
  const cellHeight=(dimensions.height-22-14-7-(networkError?14:0)-gap*(rowCount-1))/rowCount;
  for(let row=0;row<rowCount;row++){
    const line=widget.addStack();line.size=new Size(dimensions.width-28,cellHeight);
    for(let col=0;col<columns;col++){
      if(col)line.addSpacer(gap);
      const cell=line.addStack();cell.size=new Size(cellWidth,cellHeight);
      const account=rows[row*columns+col];if(account)drawAccount(cell,account);
    }
    if(row+1<rowCount)widget.addSpacer(gap);
  }
}
if(networkError&&rows.length){widget.addSpacer(4);text(widget,networkError,7,false,palette.orange);}
return widget;}

let widget=renderWidget();
Script.setWidget(widget);
if(!config.runsInWidget&&showPreview){if(family==='small')await widget.presentSmall();else if(family==='large')await widget.presentLarge();else await widget.presentMedium();
  if(tappedFamily){const after=new Alert();after.title='预览完成';after.addAction('调整展示账户');after.addCancelAction('完成');if(await after.presentSheet()===0){await editMobileAccounts();widget=renderWidget();Script.setWidget(widget);}}}
Script.complete();
