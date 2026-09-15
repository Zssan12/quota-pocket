// Desktop-only setup. A local write cannot prove that iPhone has received it.
let icloudState = null, icloudBusy = false, icloudSequence = 0;
let icloudScope = null, scopeLoaded = false, scopeDirty = false, scopeSaving = false;
function renderICloudAccounts() {
  const local = ['127.0.0.1','localhost','[::1]'].includes(location.hostname);
  const allowed = !demo && local && scopeLoaded && !scopeSaving;
  $('#icloud-scope-all').checked = icloudScope === null;
  $('#icloud-scope-all').disabled = !allowed;
  const rows = snapshot?.providers || [], byId = new Map(rows.map(row => [row.id, row]));
  const ids = [...new Set([...rows.map(row => row.id), ...(icloudScope || [])])];
  $('#icloud-scope-list').innerHTML = ids.map(id => {
    const row = byId.get(id);
    return `<label><input type="checkbox" data-icloud-account="${escape(id)}" ${icloudScope === null || icloudScope.includes(id) ? 'checked' : ''} ${allowed ? '' : 'disabled'}><span>${escape(row?.name || '暂不可用的账户')}<small>${escape(row?.app || '账户已移除或数据源停用')}</small></span></label>`;
  }).join('');
  $('#save-icloud-scope').disabled = !allowed || !scopeDirty;
  if(typeof renderSetup==='function')renderSetup();
  $('#icloud-scope-note').textContent = demo ? '演示模式不修改同步范围。' : !scopeLoaded ? '连接电脑管理端后可设置。' : scopeDirty ? '尚未保存。' : icloudScope === null ? '允许所有已连接账户；展示哪些由手机决定。' : `允许 ${icloudScope.length} 个账户。手机收到新快照后生效。`;
}
function renderICloud() {
  const state = icloudState;
  const local = ['127.0.0.1','localhost','[::1]'].includes(location.hostname);
  const allowed = !demo && local && !!state;
  $('#enable-icloud').disabled = icloudBusy || !allowed || !state?.available;
  $('#enable-icloud').textContent = icloudBusy ? '正在写入…' : state?.enabled ? '重新写入脚本与额度' : '启用 iCloud 同步';
  $('#disable-icloud').hidden = !allowed || !state?.enabled;
  $('#disable-icloud').disabled = icloudBusy;
  $('#icloud-installed').hidden = !state?.lastExportAt || demo;
  $('#icloud-script-name').textContent = state?.scriptName?.replace(/\.js$/, '') || '';
  $('#icloud-local-path').textContent = state ? '电脑上的文件夹：' + state.directory : '';
  $('#icloud-export-time').textContent = state?.lastExportAt ? '电脑最后写入：' + new Date(state.lastExportAt).toLocaleString('zh-CN') + '。此时间不代表手机已收到。' : '';
  $('#icloud-status').textContent = demo ? '演示模式不会写入 iCloud。连接真实数据后即可启用。'
    : !local ? '请在 Mac 上打开电脑管理页面启用 iCloud。'
    : !state ? '请用电脑管理凭证连接后重试。'
    : state.error ? '写入失败：' + state.error
    : !state.available ? '未找到 Scriptable 的 iCloud 文件夹。请先在 iPhone 打开 Scriptable、允许 iCloud，并确认 Mac 已开启 iCloud Drive。'
    : state.enabled ? '已写入 Scriptable 的 iCloud 文件夹，等待 Apple 同步到手机。'
    : state.lastExportAt ? '已停止写入。手机和 iCloud 中保留上次文件，旧数据会标记过期。'
    : '已找到 Scriptable 文件夹。同步额度后，在手机勾选展示账户；登录凭证留在电脑。';
  renderICloudAccounts();if(typeof renderSetup==='function')renderSetup();
}
async function loadICloud() {
  const sequence = ++icloudSequence, expectedToken = token;
  if (demo || !token) { icloudState = null; scopeLoaded = false; scopeDirty = false; icloudScope = null; renderICloud(); return; }
  try {
    const [state, scope] = await Promise.all([api('/api/icloud'), api('/api/icloud-accounts')]);
    if (sequence !== icloudSequence || expectedToken !== token || demo) return;
    icloudState = state;
    if (!scopeDirty) icloudScope = scope.providerIds;
    scopeLoaded = true;
  } catch { if (sequence === icloudSequence) { icloudState = null; scopeLoaded = false; } }
  renderICloud();
}
async function configureICloud(enabled) {
  if (icloudBusy || demo) return;
  icloudBusy = true; ++icloudSequence; renderICloud();
  try {
    icloudState = await api('/api/icloud', {method:'POST', body:JSON.stringify({enabled})});
    toast(enabled ? '已写入 iCloud 文件夹。请在 iPhone 的 Scriptable 中等待脚本出现。' : '已停止写入，现有文件与手机缓存保留。');
  } catch (error) { toast(error.message); }
  finally { icloudBusy = false; await loadICloud(); }
}
$('#enable-icloud').onclick = () => configureICloud(true);
$('#disable-icloud').onclick = () => configureICloud(false);
$('#icloud-scope-all').onchange = event => {
  icloudScope = event.target.checked ? null : (snapshot?.providers || []).map(row => row.id);
  scopeDirty = true; renderICloudAccounts();
};
$('#icloud-scope-list').onchange = event => {
  const control = event.target.closest('[data-icloud-account]');
  if (!control || control.disabled) return;
  const ids = icloudScope ?? (snapshot?.providers || []).map(row => row.id);
  icloudScope = ids.filter(id => id !== control.dataset.icloudAccount);
  if (control.checked) icloudScope.push(control.dataset.icloudAccount);
  scopeDirty = true; renderICloudAccounts();
};
$('#save-icloud-scope').onclick = async () => {
  if (!scopeLoaded || !scopeDirty || scopeSaving || demo) return;
  scopeSaving = true; renderICloudAccounts();
  try {
    const result = await api('/api/icloud-accounts', {method:'POST', body:JSON.stringify({providerIds:icloudScope})});
    icloudScope = result.providerIds; scopeDirty = false;
    toast('同步范围已保存。手机收到新快照后生效，展示顺序仍由手机决定。');
  } catch (error) { toast(error.message); }
  finally { scopeSaving = false; renderICloudAccounts(); }
};
$$('[data-view="widget"]').forEach(button => button.addEventListener('click', loadICloud));
$('#mode-toggle').addEventListener('click', loadICloud);
$('#exit-demo').addEventListener('click', loadICloud);
setInterval(() => { if ((view === 'widget' || view === 'setup') && !document.hidden && !icloudBusy) loadICloud(); }, 10000);
loadICloud();
