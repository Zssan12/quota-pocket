let setupStep=0, setupKind='codex', setupEntered=false, setupAutoOpened=false;
// Reuse the existing controls and their event handlers; one set of account state.
$('#setup-subscriptions').append($('#subscription-connectors'),$('#subscription-note'));
$('#setup-advanced-sources').append($('#settings-form'),$('.source-boundaries'));
$('#setup-icloud').append($('.icloud-setup'));
$('#setup-background').append($('.runtime-panel'));
$('#ios-steps').hidden=true;
const setupLink=document.createElement('p');setupLink.className='setup-return';
setupLink.innerHTML='<button type="button" class="button primary">继续一步步配置 →</button>';
$('.setup-panel').prepend(setupLink);setupLink.querySelector('button').onclick=()=>showView('setup');
function phoneConfirmationKey(){return icloudState?.installationId?'qp-setup-phone-'+icloudState.installationId:null;}
function currentSetup(){
  const key=phoneConfirmationKey();
  return setupProgress({snapshot:offline?null:snapshot,subscriptions:subscriptionStates,icloud:icloudState,scope:icloudScope,
    phoneConfirmed:!!key&&readStorage(key)==='yes'});
}
function renderSetup(){
  const progress=currentSetup(),limit=progress.next<0?3:progress.next;
  const connected=!demo&&!!token;
  $$('[data-setup-step]').forEach((button,i)=>{
    button.disabled=i>limit;
    button.setAttribute('aria-current',i===setupStep?'step':'false');
    button.querySelector('small').textContent=progress.done[i]?'已完成':i===setupStep?'进行中':'待完成';
  });
  $$('[data-setup-panel]').forEach((panel,i)=>panel.hidden=i!==setupStep);
  $$('[data-subscription]').forEach(card=>card.hidden=card.dataset.subscription!==setupKind);
  $('#setup-relay').hidden=setupKind!=='relay';
  $$('[data-setup-kind]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.setupKind===setupKind)));
  $('#setup-connect-relay').disabled=!connected;
  const rows=snapshot?.providers||[];
  $('#setup-quotas').innerHTML=rows.length?rows.map(r=>`<div class="setup-quota"><div><strong>${escape(r.name)}</strong><small>${escape(r.app||'API')} · ${escape(r.lastSuccessAt?'上次成功 '+clock(r.lastSuccessAt):'尚未成功')}</small></div><span class="${progress.fresh.includes(r.id)?'ready':'waiting'}">${progress.fresh.includes(r.id)?'已读到额度':r.status==='error'?'查询失败':'等待新额度'}</span></div>`).join(''):'<p class="setup-hint">正在等待第一个账户的额度。请先完成账户连接。</p>';
  $('#setup-refresh').disabled=!connected||!!snapshot?.refreshing;
  $('#setup-refresh').textContent=snapshot?.refreshing?'正在查询…':'重新查询额度';
  $('#setup-quota-note').textContent=progress.fresh.length?'已确认 '+progress.fresh.length+' 个账户，可以继续。':'还没有新鲜的成功结果，请稍等或重新查询。';
  $('#setup-script-name').textContent=icloudState?.scriptName?.replace(/\.js$/,'')||'完成上一步后显示脚本名称';
  $('#setup-phone-confirm').checked=progress.done[3];
  $('#setup-phone-confirm').disabled=!connected||!progress.done[2];
  $('#setup-back').hidden=setupStep===0;
  $('#setup-next').disabled=!connected||!progress.done[setupStep];
  $('#setup-next').textContent=setupStep===3?'完成，查看我的额度':'下一步：'+['确认额度','同步到 iCloud','添加手机组件'][setupStep];
  $('#setup-next-note').textContent=!connected?'先连接本机管理端，才能保存配置。':progress.done[setupStep]?'这一步已完成。':['连接一个账户后继续。','等至少一个账户查到真实额度。',icloudScope?.length===0?'请在高级选项中允许至少一个账户同步。':'成功写入 iCloud 后继续。','请在手机添加组件并勾选确认。'][setupStep];
  // First use lands on setup; returning users with usable data keep the overview.
  if(!setupAutoOpened&&snapshot&&!demo){setupAutoOpened=true;if(!rows.length&&view==='overview')showView('setup');}
}
async function enterSetup(){
  await Promise.allSettled([loadSubscriptions(),loadSettings(),loadICloud()]);
  if(!setupEntered){const state=currentSetup();setupStep=state.next<0?3:state.next;setupEntered=true;}
  if(setupStep===3)loadRuntime();
  renderSetup();
}
function selectSetupStep(step){setupStep=step;renderSetup();if(step===3)loadRuntime();$(`[data-setup-panel="${step}"] h2`).focus({preventScroll:true});window.scrollTo({top:0,behavior:'instant'});}
$$('[data-setup-step]').forEach(button=>button.onclick=()=>selectSetupStep(Number(button.dataset.setupStep)));
$$('[data-setup-kind]').forEach(button=>button.onclick=()=>{setupKind=button.dataset.setupKind;renderSetup();});
$('#setup-back').onclick=()=>selectSetupStep(Math.max(0,setupStep-1));
$('#setup-next').onclick=()=>{if(!currentSetup().done[setupStep])return;if(setupStep===3){toast('配置完成，额度会通过 iCloud 更新。');showView('overview');}else selectSetupStep(setupStep+1);};
$('#setup-check-icloud').onclick=()=>loadICloud();
$('#setup-refresh').onclick=async()=>{try{await api('/api/refresh',{method:'POST'});await load();}catch(e){$('#setup-quota-note').textContent=e.message;}};
$('#setup-phone-confirm').onchange=event=>{const key=phoneConfirmationKey();if(key)writeStorage(key,event.target.checked?'yes':'no');renderSetup();};
$('#setup-connect-relay').onclick=async()=>{
  const button=$('#setup-connect-relay');button.disabled=true;
  try{
    const settings=await api('/api/settings');
    if(!settings.detected['cc-switch'])throw new Error('还没找到 CC Switch。请先在这台 Mac 安装并添加账户，再点一次检测。');
    const sources=Object.fromEntries(Object.entries(settings.sources).map(([key,value])=>[key,!!value.enabled]));sources['cc-switch']=true;
    await api('/api/settings',{method:'POST',body:JSON.stringify({sources})});
    $('#setup-relay-status').textContent='已连接，正在查询余额。点击下一步确认结果。';await load();
  }catch(e){$('#setup-relay-status').textContent=e.message;}
  finally{button.disabled=false;}
};
$('#setup-background').addEventListener('toggle',()=>{if($('#setup-background').open)loadRuntime();});
renderSetup();
