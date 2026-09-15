// Contract checks with Scriptable API doubles; this does not emulate iOS rendering.
import vm from 'node:vm';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const code=fs.readFileSync(new URL('../widgets/Quota-Pocket.js',import.meta.url),'utf8');
const token='TEST_ONLY_'.repeat(4), key='quota-pocket.connection.v2.Quota%20Pocket';
const snapshot={schemaVersion:1,demo:false,generatedAt:new Date().toISOString(),providers:Array.from({length:4},(_,i)=>({id:String(i),name:'Provider '+i,app:i%2?'claude':'codex',balances:[{unit:'USD',value:42}],lastSuccessAt:new Date().toISOString()}))};
async function run({family='large',name='Quota Pocket',status=200,legacy=false,pair=false,tap=null,tapOptions='all',edit=false,icloud=null,cloudData=snapshot,networkData=cloudData,cloudError=false,cloudReadError=cloudError,cloudDownloaded=true,cacheWriteError=false,initialFiles,sheetChoices=[],preferenceWriteError=false,onTablePresent,installedCode=null,now=Date.parse('2026-09-14T00:00:00Z')}={}){
 const secrets=new Map([[legacy?'quota-pocket.connection.v1':key,JSON.stringify({url:'https://quota.example',token,cacheId:'test'})]]),files=initialFiles||new Map(),cloudDownloads=[],requests=[];
 let widget, menus=0; const previews=[],alerts=[],tables=[],setWidgets=[];
 class Stack{
  constructor(){this.children=[];}
  addStack(){const c=new Stack();this.children.push(c);return c;}
  addText(value){const t={value,centerAlignText(){this.centered=true;}};this.children.push(t);return t;}
  addDate(){return {applyRelativeStyle(){}};}
  addSpacer(length){this.children.push({spacer:length??'flex'});}
  addImage(image){const child={image};this.children.push(child);return child;}
  layoutVertically(){}centerAlignContent(){}setPadding(){}
 }
 class Widget extends Stack{constructor(){super();widget=this;}async presentSmall(){previews.push('small');}async presentMedium(){previews.push('medium');}async presentLarge(){previews.push('large');}}
 class Request{constructor(url){this.url=url;this.response={statusCode:status};requests.push(this);}async loadJSON(){return this.url.endsWith('/exchange')?{url:'https://quota.example',token}:networkData;}}
 class Alert{constructor(){this.actions=[];alerts.push(this);}addAction(x){this.actions.push(x);}addCancelAction(){}async presentAlert(){return 0;}async presentSheet(){menus++;return sheetChoices.length?sheetChoices.shift():2;}}
 class UITable{constructor(){this.rows=[];tables.push(this);}addRow(r){this.rows.push(r);}removeAllRows(){this.rows=[];}reload(){this.reloads=(this.reloads||0)+1;}async present(){if(onTablePresent)await onTablePresent(this);}}
 class UITableRow{constructor(){this.buttons=[];}addText(title,subtitle){this.title=title;this.subtitle=subtitle;return {};}addButton(title){const b={title};this.buttons.push(b);return b;}}
 const local={documentsDirectory:()=>'/test',joinPath:(a,b)=>a+'/'+b,writeString:(p,s)=>{if((preferenceWriteError&&p.includes('mobile-selection'))||(cacheWriteError&&p.includes('cache-v2')))throw new Error('readonly');files.set(p,s);},readString:p=>files.get(p)};
 const cloud={documentsDirectory:()=>'/icloud',joinPath:(a,b)=>a+'/'+b,async downloadFileFromiCloud(path){cloudDownloads.push(path);if(cloudError)throw new Error('offline');cloudDownloaded=true;},readString:()=>{if(cloudReadError||!cloudDownloaded)throw new Error('unavailable');return JSON.stringify(cloudData);}};
 const query=pair?{url:'https://quota.example',pair:'x'.repeat(43)}:tap?{preview:tap,options:tapOptions}:edit?{edit:'accounts'}:{};
 class TestDate extends Date {constructor(...args){super(...(args.length?args:[now]));}static now(){return now;}}
 const context={Date:TestDate,console,config:{runsInWidget:!pair&&!tap&&!edit,widgetFamily:family},args:{queryParameters:query,widgetParameter:''},Script:{name:()=>name,setWidget(w){setWidgets.push(w);},complete(){}},FileManager:{local:()=>local,iCloud:()=>cloud},Keychain:{contains:k=>secrets.has(k),get:k=>secrets.get(k),set:(k,v)=>secrets.set(k,v)},ListWidget:Widget,Request,Alert,UITable,UITableRow,UUID:{string:()=> 'unique'},Color:class{constructor(hex,alpha=1){this.hex=hex;this.alpha=alpha;}},DrawContext:class{constructor(){this.fills=[];}setFillColor(color){this.color=color;}fillRect(rect){this.fills.push({color:this.color,rect});}getImage(){return {fills:this.fills};}},Rect:class{constructor(x,y,width,height){Object.assign(this,{x,y,width,height});}},Size:class{constructor(width,height){this.width=width;this.height=height;}},Device:{screenSize:()=>({width:393,height:852}),screenResolution:()=>({width:1179,height:2556}),screenScale:()=>3},Font:{semiboldSystemFont:()=>'',systemFont:()=>''}};
 const injected=icloud?`const ICLOUD_SOURCE = ${JSON.stringify(icloud)};\n`:'';
 await vm.runInNewContext('(async()=>{'+injected+(installedCode??code)+'})()',context);
 return {widget,secrets,files,cloudDownloads,requests,menus,previews,alerts,tables,setWidgets};
}

export {run, snapshot, token, key};
