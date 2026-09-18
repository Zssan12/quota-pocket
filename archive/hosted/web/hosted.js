'use strict';
const el = id => document.getElementById(id);
const key = 'qp-hosted-pair';
const fragment = new URLSearchParams(location.hash.slice(1));
history.replaceState(null, '', location.pathname);
const valid = value => /^[A-Za-z0-9_-]{32,100}$/.test(value || '');
let session = null, config = null;
try {
  const saved = JSON.parse(sessionStorage.getItem(key) || 'null');
  if (saved?.until > Date.now() && /^[a-f0-9]{32}$/.test(saved.room) && valid(saved.readerToken)) session = saved;
} catch {}
if (/^[a-f0-9]{32}$/.test(fragment.get('room') || '') && valid(fragment.get('pair'))) {
  const random = crypto.getRandomValues(new Uint8Array(32));
  const readerToken = Array.from(random, byte => byte.toString(16).padStart(2, '0')).join('');
  session = {room: fragment.get('room'), code: fragment.get('pair'), readerToken, until: Date.now() + 600000};
  try { sessionStorage.setItem(key, JSON.stringify(session)); } catch {}
}
async function request(path, body) {
  const response = await fetch(path, {method: body ? 'POST' : 'GET', cache: 'no-store',
    headers: {'Authorization': 'Bearer ' + session.readerToken, ...(body ? {'Content-Type': 'application/json'} : {})},
    ...(body ? {body: JSON.stringify(body)} : {})});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '连接暂未成功，请重试。');
  return result;
}
async function connect() {
  el('connect').disabled = true;
  el('status').textContent = '正在连接…';
  try {
    if (!session || session.until <= Date.now()) throw new Error('安装链接已过期，请在电脑重新生成二维码。');
    if (session.code) {
      await request('/v2/pair/exchange', {room: session.room, code: session.code, readerToken: session.readerToken, label: 'Widgeto'});
      session.code = null;
      session.until = Date.now() + 1800000;
      try { sessionStorage.setItem(key, JSON.stringify(session)); } catch {}
    }
    const base = '/v2/rooms/' + session.room;
    const results = await Promise.all([request(base + '/widgeto'), request(base + '/config')]);
    const data = results[0]; config = results[1];
    el('accounts').replaceChildren();
    for (const item of data.items) {
      const node = document.createElement('div'); node.className = 'account';
      for (const [tag, value] of [['strong', item.account], ['span', item.quota], ['small', item.freshness]]) {
        const child = document.createElement(tag); child.textContent = value; node.append(child);
      }
      el('accounts').append(node);
    }
    el('status').textContent = '连接成功，继续导入 Widgeto。';
    el('preview').hidden = false; el('install').hidden = false;
    el('connect').textContent = '重新读取最新快照';
  } catch (error) {
    el('status').textContent = error.message || '连接失败，请稍后重试。';
  } finally { el('connect').disabled = false; }
}
function file() { return new File([JSON.stringify(config, null, 2)], 'Quota-Pocket.widgeto.json', {type: 'application/json'}); }
function download() {
  if (!config) return;
  const url = URL.createObjectURL(file()), anchor = document.createElement('a');
  anchor.href = url; anchor.download = 'Quota-Pocket.widgeto.json'; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
el('download').onclick = download;
el('share').onclick = async () => {
  if (!config) return;
  const files = [file()];
  if (!navigator.canShare?.({files})) { download(); return; }
  try { await navigator.share({files, title: '额度口袋'}); }
  catch (error) { if (error.name !== 'AbortError') el('status').textContent = '分享暂不可用，可以下载配置文件后导入。'; }
};
if (session) {
  el('connect').hidden = false;
  el('connect').onclick = connect;
  el('status').textContent = '点击连接，为这台手机建立独立的额度读取权限。';
}
