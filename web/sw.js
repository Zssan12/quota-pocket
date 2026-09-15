const CACHE='quota-pocket-shell-v1';
const FILES=['/','/style.css','/app.js','/icloud.js','/runtime.js','/setup-state.js','/setup.js','/icon.svg','/icon-192.png','/icon-512.png','/manifest.webmanifest'];
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(FILES)));self.skipWaiting();});
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
self.addEventListener('fetch',event=>{const url=new URL(event.request.url);if(event.request.method!=='GET'||url.origin!==self.location.origin||url.pathname.startsWith('/api/')||url.pathname.startsWith('/downloads/'))return;
  event.respondWith(fetch(event.request).then(response=>{if(response.ok&&FILES.includes(url.pathname)){const copy=response.clone();caches.open(CACHE).then(cache=>cache.put(url.pathname,copy));}return response;}).catch(()=>caches.match(url.pathname==='/'?'/':event.request)));});
