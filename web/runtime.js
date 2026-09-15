let serviceBusy=false;
async function loadRuntime(){
  const buttons=['service-start','service-restart','service-disable'];
  buttons.forEach(id=>$('#'+id).disabled=true);
  if(demo||!token){$('#runtime-status').textContent=demo?'演示模式不操作后台服务。':'请先连接本机管理端。';$('#runtime-version').textContent='';return;}
  try{
    const r=await api('/api/runtime');
    $('#runtime-status').textContent=(r.managed?'后台采集器运行中':'当前为手动启动的采集器')+' · '+(r.service?.enabled?'已启用登录启动':'未启用登录启动')+' · 每 '+r.intervalSeconds/60+' 分钟采集';
    $('#runtime-version').textContent='版本 '+r.version+' · '+r.build+' · 启动于 '+new Date(r.startedAt).toLocaleString()+(r.build!==r.diskBuild?' · 文件已更新，请重启采集器':' · 与磁盘版本一致');
    const allowed=r.serviceSupported&&!r.service?.error&&!serviceBusy;
    buttons.forEach(id=>$('#'+id).disabled=!allowed);
    if(r.service?.error)$('#runtime-status').textContent+=' · '+r.service.error;
    if(r.icloud?.error)$('#runtime-status').textContent+=' · iCloud 写入失败：'+r.icloud.error;
  }catch(e){$('#runtime-status').textContent=e.status===404?'正在运行旧版服务。请在原终端停止，再使用启动命令运行新版。':'无法连接采集器；停止后需重新运行启动命令。';}
}
async function changeService(action){
  serviceBusy=true;
  ['service-start','service-restart','service-disable'].forEach(id=>$('#'+id).disabled=true);
  try{
    await api('/api/service',{method:'POST',body:JSON.stringify({action})});
    $('#service-note').textContent=action==='disable'?'正在停止并禁用登录启动，页面连接将断开。额度与配置保留。':'正在切换后台进程，请稍候…';
    if(action!=='disable'){
      let ready=false;
      for(let i=0;i<20;i++){
        await new Promise(resolve=>setTimeout(resolve,1000));
        try{const r=await api('/api/runtime');if(r.managed&&r.build===r.diskBuild&&(!r.icloud?.enabled||!r.icloud?.error)){ready=true;break;}}catch(_){}
      }
      $('#service-note').textContent=ready?'后台已就绪，关闭浏览器后继续采集。':'后台尚未就绪。请检查运行目录 .state/service-action.log；macOS 可能限制后台访问 iCloud 文件。';
    }
  }catch(e){$('#service-note').textContent=e.message;}
  finally{serviceBusy=false;await loadRuntime();}
}
$('#service-start').onclick=()=>changeService('start');
$('#service-restart').onclick=()=>changeService('restart');
$('#service-disable').onclick=()=>changeService('disable');
setInterval(()=>{if(view==='sources'&&!document.hidden&&!serviceBusy)loadRuntime();},30000);
