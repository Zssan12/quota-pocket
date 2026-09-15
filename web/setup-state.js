// Data-driven gates: a local export never proves delivery to an iPhone.
function setupProgress({snapshot,subscriptions={},icloud,phoneConfirmed=false,scope=null,now=Date.now()}){
  const rows=snapshot?.providers||[];
  const connected=rows.length>0||(snapshot?.enabledCount||0)>0||Object.values(subscriptions).some(s=>s.connected);
  const fresh=rows.filter(r=>r.status==='ok'&&typeof r.lastSuccessAt==='string'&&Number.isFinite(Date.parse(r.lastSuccessAt))&&now-Date.parse(r.lastSuccessAt)<=(snapshot.staleAfterSeconds||1230)*1000&&
    ((r.windows||[]).some(w=>typeof w.remainingPercent==='number'&&Number.isFinite(w.remainingPercent))||(r.balances||[]).some(b=>typeof b.value==='number'&&Number.isFinite(b.value))));
  const cloud=!!(icloud?.enabled&&icloud.available&&icloud.lastExportAt&&!icloud.error&&fresh.some(r=>scope===null||scope.includes(r.id)));
  const done=[connected,fresh.length>0,cloud,cloud&&fresh.length>0&&phoneConfirmed];
  return {done,fresh:fresh.map(r=>r.id),next:done.findIndex(v=>!v)};
}
