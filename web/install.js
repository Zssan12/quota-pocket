const copyButton=document.querySelector('#copy-script');
const copyStatus=document.querySelector('#copy-status');
const scriptText=document.querySelector('#script-text');
// Fragment is stripped before any request. Only short-lived codes are retained
// in this tab's sessionStorage; long-lived legacy tokens remain in memory.
const fragment=new URLSearchParams(location.hash.slice(1));
const legacyToken=fragment.get('access');
let pairingCode=fragment.get('pair');
if(fragment.has('access')||fragment.has('pair'))history.replaceState(null,'',location.pathname+location.search);
const validCode=value=>/^[A-Za-z0-9_-]{32,100}$/.test(value||'');
try{
  if(pairingCode){sessionStorage.setItem('qp-install',JSON.stringify({code:pairingCode,until:Date.now()+600000}));}
  else if(!legacyToken){const old=JSON.parse(sessionStorage.getItem('qp-install')||'null');if(old&&old.until>Date.now())pairingCode=old.code;}
}catch{}
if(validCode(pairingCode)&&location.protocol==='https:'){
  document.querySelector('#quick-pair').hidden=false;document.querySelector('#pairing-missing').hidden=true;
  const link=document.querySelector('#connect-script'), name=document.querySelector('#script-name');
  const update=()=>{link.href='scriptable:///run/'+encodeURIComponent(name.value.trim()||'Quota Pocket')+'?'+new URLSearchParams({url:location.origin,pair:pairingCode});};
  name.oninput=update;update();
  link.onclick=()=>{document.querySelector('#quick-status').textContent='连接成功后，回到此页完成第 3 步。链接过期或已使用时，在电脑重新生成。';};
}else if(legacyToken&&/^[A-Za-z0-9_-]{24,200}$/.test(legacyToken)&&location.protocol==='https:'){
  document.querySelector('#pairing-text').value=JSON.stringify({url:location.origin,token:legacyToken});
  document.querySelector('#pairing').hidden=false;document.querySelector('#pairing-missing').hidden=true;
}
fetch('/downloads/Quota-Pocket.js',{cache:'no-store'}).then(async response=>{
  if(!response.ok)throw new Error('download');
  const code=await response.text();if(!code.includes('Script.setWidget'))throw new Error('script');
  scriptText.value=code;copyButton.disabled=false;copyButton.textContent='复制组件脚本';
}).catch(()=>{copyStatus.textContent='脚本暂时无法加载，请刷新页面重试。';copyButton.textContent='暂时无法复制';});
copyButton.onclick=async()=>{
  try{await navigator.clipboard.writeText(scriptText.value);copyStatus.textContent='已复制。打开 Scriptable，新建脚本并粘贴；更新则替换原脚本代码。';copyButton.textContent='已复制 ✓';}
  catch{document.querySelector('#script-fallback').open=true;scriptText.focus();scriptText.select();copyStatus.textContent='请长按代码框，全选并复制。';}
};
document.querySelector('#copy-pairing').onclick=async()=>{
  const field=document.querySelector('#pairing-text'),status=document.querySelector('#pairing-status');
  try{await navigator.clipboard.writeText(field.value);status.textContent='已复制。回到 Scriptable，在连接弹窗里粘贴。';}
  catch{document.querySelector('#pairing-fallback').open=true;field.focus();field.select();status.textContent='请长按配对信息框，全选并复制。';}
};
