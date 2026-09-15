// The default service URL is configured by the release, never typed on the phone.
const hostedPanel = document.createElement('section');
hostedPanel.className = 'icloud-setup';
hostedPanel.hidden = true;
hostedPanel.innerHTML = `<div class="icloud-heading"><h3>连接 Widgeto</h3><span class="pill">Windows / Mac + iPhone</span></div>
<p>电脑自动上传你在“电脑默认展示账户”中选择的额度，手机通过同步服务读取。无需配置电脑地址或 VPN。</p>
<p>服务能够读取账户名称、额度和采集时间；平台密钥及订阅凭证留在电脑。需要 iOS 18 以上，Widgeto 导入效果尚待真机验证。</p>
<p id="hosted-status" role="status">正在检查同步服务…</p>
<div class="icloud-actions"><button id="hosted-enable" type="button" class="button primary" disabled>启用并连接手机</button><button id="hosted-pair" type="button" class="button light" hidden>生成手机二维码</button><button id="hosted-disable" type="button" class="text-button" hidden>停止同步并撤销手机</button></div>
<div id="hosted-share" hidden><img id="hosted-qr" alt="手机配对二维码" width="240" height="240"><p>用 iPhone 相机扫码，连接后导入 Widgeto，再添加桌面组件。二维码 10 分钟有效，请勿公开分享。</p><button id="hosted-copy" type="button" class="button light">复制安装链接</button></div>`;
document.getElementById('ios-steps').prepend(hostedPanel);
const legacyICloud = document.createElement('details');
legacyICloud.className = 'https-fallback'; legacyICloud.open = true;
const legacySummary = document.createElement('summary'); legacySummary.textContent = '使用自己的 iCloud / Scriptable';
legacyICloud.append(legacySummary);
legacyICloud.append(document.querySelector('.phone-selection-guide'));
for (const child of [...document.getElementById('ios-steps').children]) {
  if (child !== hostedPanel) legacyICloud.append(child);
}
document.getElementById('ios-steps').append(legacyICloud);
document.querySelector('.desktop-selection > summary').textContent = '选择 Widgeto 展示账户 / Scriptable 默认账户';
document.querySelector('.widget-selection > .widget-selection-note').textContent = '勾选并调整顺序，托管同步只上传这些账户。Scriptable 将其作为首次默认值，不覆盖手机上已有的选择。左侧尺寸预览为 Scriptable 示意，Widgeto 使用表格布局。';
let hostedState = null, hostedLink = '', hostedUntil = 0, hostedBusy = false, hostedAutoPair = false, hostedModeInitialized = false;
function clearHostedLink() {
  hostedLink = ''; hostedUntil = 0; document.getElementById('hosted-share').hidden = true;
  document.getElementById('hosted-qr').removeAttribute('src');
}
async function loadHosted() {
  const status = document.getElementById('hosted-status');
  const enable = document.getElementById('hosted-enable');
  const pair = document.getElementById('hosted-pair');
  const disable = document.getElementById('hosted-disable');
  if (demo || !token) {
    hostedPanel.hidden = true;
    hostedState = null; clearHostedLink(); enable.disabled = true; pair.hidden = true; disable.hidden = true;
    status.textContent = demo ? '演示模式不上传或建立手机连接。' : '请先连接电脑管理端。';
    return;
  }
  try {
    const currentToken = token;
    const state = await api('/api/hosted');
    if (demo || token !== currentToken) return;
    hostedState = state;
    hostedPanel.hidden = !state.configured && !state.enabled && !state.disconnectPending;
    if (!hostedModeInitialized) { legacyICloud.open = !state.configured; hostedModeInitialized = true; }
    enable.hidden = state.enabled; enable.disabled = hostedBusy || !state.configured || state.disconnectPending;
    pair.hidden = !state.ready; pair.disabled = hostedBusy;
    disable.hidden = !state.enabled; disable.disabled = hostedBusy;
    if (!state.enabled) clearHostedLink();
    status.textContent = !state.configured ? '默认同步服务尚未部署，当前可继续使用下方 iCloud。' :
      state.disconnectPending ? '已停止上传，正在清除云端快照并撤销手机；服务暂不可达时会自动重试。' :
      state.error || (state.enabled ? (state.lastUploadedAt ? '最近上传：' + new Date(state.lastUploadedAt * 1000).toLocaleString() : '正在建立连接并上传首次快照…') : '可以启用同步。停止后将清除云端快照并撤销原手机连接。');
    if (state.ready && hostedAutoPair && !hostedBusy) { hostedAutoPair = false; await generateHostedPair(); }
  } catch { enable.disabled = true; pair.hidden = true; disable.hidden = true; status.textContent = '请连接电脑管理端后设置同步。'; }
}
async function changeHosted(enabled) {
  if (demo || hostedBusy) return;
  hostedBusy = true;
  hostedAutoPair = enabled;
  try { await api('/api/hosted', {method:'POST', body:JSON.stringify({enabled})}); }
  catch (error) { hostedAutoPair = false; toast(error.message); }
  finally { hostedBusy = false; await loadHosted(); }
}
document.getElementById('hosted-enable').onclick = () => changeHosted(true);
document.getElementById('hosted-disable').onclick = () => changeHosted(false);
async function generateHostedPair() {
  if (demo || hostedBusy || !hostedState?.ready) return;
  hostedBusy = true;
  try {
    const result = await api('/api/hosted/pair', {method:'POST'});
    hostedLink = result.url; hostedUntil = Date.now() + result.expiresIn * 1000;
    const qr = qrcode(0, 'M'); qr.addData(hostedLink); qr.make();
    document.getElementById('hosted-qr').src = qr.createDataURL(4, 16);
    document.getElementById('hosted-share').hidden = false;
  } catch (error) { toast(error.message); }
  finally { hostedBusy = false; }
}
document.getElementById('hosted-pair').onclick = generateHostedPair;
document.getElementById('hosted-copy').onclick = async () => {
  if (Date.now() >= hostedUntil) { clearHostedLink(); toast('请重新生成二维码。'); return; }
  try { await navigator.clipboard.writeText(hostedLink); toast('已复制。请仅发送到自己的手机。'); }
  catch { toast('复制失败，请使用相机扫码。'); }
};
loadHosted();
setInterval(() => {
  if (hostedUntil && Date.now() >= hostedUntil) clearHostedLink();
  if (view === 'widget' && !document.hidden) loadHosted();
}, 5000);
