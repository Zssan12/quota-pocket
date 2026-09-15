#!/usr/bin/env python3
"""Quota Pocket: local collector + authenticated mobile snapshot server."""
import argparse
import concurrent.futures
import copy
import datetime as dt
import hashlib
import fcntl
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser

from adapters import ADAPTERS, ROOT, SourceError, cc_snapshot_path, now, stamp
from icloud_sync import ICloudError, ICloudSync, quota_projection
from hosted_sync import HostedSync, SyncError
from subscription_auth import SubscriptionLogins, LoginError
import service_manager

VERSION = '0.1.3'


def build_id():
    digest = hashlib.sha256()
    paths = list(ROOT.glob('*.py')) + list((ROOT / 'web').glob('*.*')) + list((ROOT / 'widgets').glob('*.js'))
    for path in sorted(paths):
        if path.is_file():
            digest.update(str(path.relative_to(ROOT)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


RUNNING_BUILD = build_id()


def instance_lock(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle = (directory / 'collector.lock').open('a')
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise ValueError('此状态目录已有采集器运行。') from None
    return handle

DEFAULT_CONFIG = {'intervalSeconds': 300, 'publicUrl': '', 'widgetProviderIds': None, 'icloudProviderIds': None, 'sources': {
    'cc-switch': {'enabled': False, 'mode': 'independent'}, 'codexbar': {'enabled': False, 'mode': 'cli'},
    'codex': {'enabled': False}, 'claude': {'enabled': False}}}


def write_private(path, value):
    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(data)
    os.chmod(path, 0o600)


def load_json(path, fallback):
    try: return json.loads(path.read_text())
    except (ValueError, OSError): return copy.deepcopy(fallback)


def demo_snapshot():
    current = dt.datetime.now(dt.timezone.utc)
    def at(delta): return (current + dt.timedelta(seconds=delta)).isoformat().replace('+00:00', 'Z')
    def item(uid, name, app, plan, remaining, weekly, active=False):
        return {'id': uid, 'name': name, 'app': app, 'plan': plan, 'source': '示例数据', 'active': active,
                'windows': [{'id': 'five_hour', 'label': '5 小时额度', 'remainingPercent': remaining, 'resetAt': at(7800)},
                            {'id': 'weekly', 'label': '每周额度', 'remainingPercent': weekly, 'resetAt': at(248000)}],
                'balances': [], 'lastSuccessAt': at(-72), 'lastAttemptAt': at(-72), 'status': 'ok', 'error': None}
    providers = [item('demo-codex', 'Codex', 'codex', '个人订阅', 72, 41, False),
                 item('demo-claude', 'Claude', 'claude', 'Max 5×', 86, 58)]
    for uid, name, value, unit, active in [('demo-relay-a', 'North API', 42.3, 'CNY', True), ('demo-relay-b', 'Orbit Relay', 18.2, 'USD', False)]:
        providers.append({'id': uid, 'name': name, 'app': 'codex', 'plan': '按量付费', 'source': '示例数据', 'active': active,
                          'windows': [], 'balances': [{'label': '账户余额', 'value': value, 'unit': unit}],
                          'lastSuccessAt': at(-105), 'lastAttemptAt': at(-105), 'status': 'ok', 'error': None})
    slow = item('demo-stale', 'Cloud Relay', 'claude', '套餐额度', 13, 36)
    slow.update(status='stale', lastSuccessAt=at(-4300), error='最近一次查询超时，当前显示上次成功的额度。')
    providers.append(slow)
    return {'schemaVersion': 1, 'demo': True, 'generatedAt': at(0), 'lastCollectionAt': at(-72),
            'intervalSeconds': 600, 'staleAfterSeconds': 1230, 'refreshing': False, 'providers': providers,
            'sources': [], 'enabledCount': 0, 'widgetProviderIds': None}


class Store:
    def __init__(self, state_dir):
        self.directory = Path(state_dir)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.refresh_lock = threading.Lock()
        self.stop = threading.Event()
        # monotonic() has an unspecified origin; startup must be immediately due
        # even when the clock begins near zero.
        self.last_started = float('-inf')
        self.revision = 0
        self.cache_signature = None
        self.source_retries = {}
        self.last_loop_at = time.time()
        self.config = load_json(self.directory / 'config.json', DEFAULT_CONFIG)
        for key, value in DEFAULT_CONFIG.items(): self.config.setdefault(key, copy.deepcopy(value))
        for key, value in DEFAULT_CONFIG['sources'].items(): self.config['sources'].setdefault(key, value.copy())
        # Pre-bridge configurations used independent polling. Preserve that explicit
        # compatibility path; new installations also use unmodified CC Switch.
        self.config['sources']['cc-switch'].setdefault('mode', 'independent')
        if self.config['sources']['cc-switch'].get('enabled') and self.config['sources']['cc-switch']['mode'] == 'snapshot':
            for key in ('codex', 'claude', 'codexbar'):
                if not self.config['sources'][key].get('managed'): self.config['sources'][key]['enabled'] = False
        self.keys = load_json(self.directory / 'access.json', {})
        if not all(self.keys.get(k) for k in ('admin', 'viewer')):
            self.keys = {k: secrets.token_urlsafe(32) for k in ('admin', 'viewer')}
            write_private(self.directory / 'access.json', self.keys)
        cache = load_json(self.directory / 'snapshot.json', {})
        self.rows = cache.get('providers', [])
        self.last_collection = cache.get('lastCollectionAt')
        self.source_status = cache.get('sources', [])
        self.started = now()
        self.phone_refresh = load_json(self.directory / 'phone-refresh.json', {})
        self.pairings = {}  # Short-lived, single-use codes; never persisted or logged.
        self.subscriptions = SubscriptionLogins(self.directory / 'subscriptions', self.connect_subscription)
        self.hosted = HostedSync(self.directory, lambda: self.snapshot(widget_only=True))
        self.icloud = ICloudSync(self.directory, ROOT / 'widgets/Quota-Pocket.js')
        if self.icloud.status()['enabled']:
            self.export_icloud()

    def export_icloud(self):
        # Callers never hold Store.lock here. ICloudSync serializes first, then
        # invokes the supplier so a queued old export cannot capture stale state.
        try:
            return self.icloud.export(self.icloud_snapshot)
        finally:
            self.hosted.wake()

    def icloud_snapshot(self):
        with self.lock:
            packet = self.snapshot()
            scope = self.config['icloudProviderIds']
            available = packet['providers']
            if scope is not None:
                allowed = set(scope)
                available = [r for r in available if r['id'] in allowed]
            by_id = {r['id']: r for r in available}
            defaults = self.config['widgetProviderIds']
            defaults = list(by_id) if defaults is None else [uid for uid in defaults if uid in by_id]
            packet.update(mobileSelectionVersion=1, availableProviders=available,
                          defaultProviderIds=defaults, providers=[by_id[uid] for uid in defaults])
            if self.phone_refresh:
                packet['refreshRequest'] = copy.deepcopy(self.phone_refresh)
            return packet

    def icloud_accounts(self):
        with self.lock:
            return {'providerIds': copy.deepcopy(self.config['icloudProviderIds'])}

    def mobile_snapshot(self):
        # Phone clients receive only the same scalar allowlist as iCloud.
        # Never export source errors, local paths, credentials or configuration.
        with self.lock:
            packet = quota_projection(self.icloud_snapshot())
            packet.update(installationId=self.icloud.state['deviceId'],
                          refreshing=self.refresh_lock.locked(),
                          collectionId=self.last_collection)
            return packet

    def runtime_status(self):
        with self.lock:
            result = {'version': VERSION, 'build': RUNNING_BUILD, 'diskBuild': build_id(),
                    'managed': os.environ.get('QUOTA_POCKET_MANAGED') == 'launchd',
                    'pid': os.getpid(), 'startedAt': self.started,
                    'intervalSeconds': self.config['intervalSeconds'],
                    'refreshing': self.refresh_lock.locked(), 'lastCollectionAt': self.last_collection,
                    'sources': [{'id': key, 'failures': value['failures'],
                                 'retryInSeconds': max(0, int(value['due'] - time.monotonic()))}
                                for key, value in self.source_retries.items()]}
        # Same lock order as export_icloud: never hold Store.lock while waiting
        # for ICloudSync.lock, whose exporter may be waiting for Store.lock.
        result['icloud'] = self.icloud.status()
        result['hosted'] = self.hosted.status()
        result['serviceSupported'] = sys.platform == 'darwin' and self.directory.resolve() == (ROOT / '.state').resolve()
        if result['serviceSupported']:
            try:
                result['service'] = service_manager.status()
            except (ValueError, OSError, subprocess.SubprocessError):
                result['service'] = {'error': '无法读取后台服务状态。'}
        return result

    def check_phone_refresh(self):
        request = self.icloud.read_refresh_request()
        changed = False
        with self.lock:
            if request and request['id'] != self.phone_refresh.get('id'):
                self.phone_refresh = {'id': request['id'], 'state': 'waiting', 'receivedAt': now()}
                changed = True
            if self.phone_refresh.get('state') == 'waiting':
                started = self.request_refresh(manual=True)
                if started or self.refresh_lock.locked():
                    self.phone_refresh['state'] = 'collecting'
                    changed = True
            if changed:
                write_private(self.directory / 'phone-refresh.json', self.phone_refresh)
        if changed:
            self.export_icloud()

    def configure_icloud_accounts(self, data):
        if not isinstance(data, dict) or set(data) != {'providerIds'}:
            raise ValueError('需要同步账户列表。')
        ids = data['providerIds']
        if ids is not None:
            if not isinstance(ids, list) or len(ids) > 500 or any(not isinstance(uid, str) or not uid or len(uid) > 200 for uid in ids):
                raise ValueError('同步账户列表无效。')
            if len(set(ids)) != len(ids): raise ValueError('账户不能重复。')
        with self.lock:
            known = {r['id'] for r in self.rows} | set(self.config['icloudProviderIds'] or [])
            if ids is not None and set(ids) - known: raise ValueError('账户列表已变化，请重试。')
            updated = copy.deepcopy(self.config)
            updated['icloudProviderIds'] = copy.deepcopy(ids)
            write_private(self.directory / 'config.json', updated)
            self.config = updated
        self.export_icloud()
        return self.icloud_accounts()

    def connect_subscription(self, kind, config):
        with self.lock:
            self.config['sources'][kind] = dict(config)
            # A new account must never briefly display the previous account's quota.
            self.rows = [r for r in self.rows if r.get('_sourceId') != kind]
            self.source_status = [r for r in self.source_status if r.get('id') != kind]
            self.revision += 1
            self.last_started = 0
            write_private(self.directory / 'config.json', self.config)
            write_private(self.directory / 'snapshot.json', {'providers':self.rows,'sources':self.source_status,'lastCollectionAt':self.last_collection})
        self.export_icloud()
        self.request_refresh(force=True)

    def subscription_status(self):
        with self.lock:
            configs = copy.deepcopy(self.config['sources'])
            sources = copy.deepcopy(self.source_status)
        jobs = self.subscriptions.statuses()
        result = {}
        for kind in ('codex', 'claude'):
            config = configs[kind]
            credential = (Path(config['home'])/'auth.json') if kind=='codex' and config.get('home') else Path(config.get('path','/nonexistent'))
            connected = bool(config.get('managed') and credential.is_file())
            result[kind] = {'connected':connected, 'enabled':bool(config.get('enabled')), 'available':bool(shutil.which(kind)),
                            'state':'connected' if connected else 'disconnected', 'authUrl':None, 'id':None,
                            'message':'独立登录已保存。' if connected else '单独登录订阅，不影响桌面工具的 API Key 或 Provider。',
                            'quotaError':next((s.get('error') for s in sources if s['id']==kind),None)}
            result[kind].update(jobs.get(kind,{}))
        return result

    def create_pairing(self):
        with self.lock:
            url = self.config.get('publicUrl', '')
            if not url.startswith('https://'): raise ValueError('请先设置手机可访问的 HTTPS 地址。')
            current = time.monotonic()
            self.pairings = {k: v for k, v in self.pairings.items() if v['deadline'] > current}
            if len(self.pairings) >= 20: self.pairings.pop(next(iter(self.pairings)))
            code = secrets.token_urlsafe(32)
            self.pairings[hashlib.sha256(code.encode()).hexdigest()] = {'deadline': current + 600, 'url': url}
            return {'url': url + '/install.html#pair=' + code, 'expiresIn': 600}

    def exchange_pairing(self, code):
        if not isinstance(code, str) or not 32 <= len(code) <= 100: return None
        with self.lock:
            entry = self.pairings.pop(hashlib.sha256(code.encode()).hexdigest(), None)
            if not entry or entry['deadline'] <= time.monotonic() or entry['url'] != self.config.get('publicUrl'): return None
            return {'url': entry['url'], 'token': self.keys['viewer']}

    def role(self, token):
        if not isinstance(token, str) or len(token) > 200: return None
        with self.lock:
            for role, secret in self.keys.items():
                if hmac.compare_digest(token, secret): return role
        return None

    def settings(self):
        with self.lock:
            return {'intervalSeconds': self.config['intervalSeconds'], 'publicUrl': self.config.get('publicUrl', ''),
                    'ccSwitchMode': self.config['sources']['cc-switch']['mode'],
                    'ccSwitchSnapshotPath': str(cc_snapshot_path(self.config['sources']['cc-switch'])),
                    'ccSwitchSnapshotAvailable': cc_snapshot_path(self.config['sources']['cc-switch']).is_file(),
                    'sources': {k: {'enabled': bool(v.get('enabled')), 'managed':bool(v.get('managed'))} for k, v in self.config['sources'].items()},
                    'detected': {'cc-switch': Path('~/.cc-switch/cc-switch.db').expanduser().is_file(),
                                 'codexbar': bool(shutil.which('codexbar') or Path('/Applications/CodexBar.app').exists()),
                                 'codex': bool(shutil.which('codex')),
                                 'claude': bool(os.environ.get('CLAUDE_QUOTA_OAUTH_TOKEN') or Path('~/.claude/.credentials.json').expanduser().is_file())}}

    def configure(self, data):
        interval = data.get('intervalSeconds', self.config['intervalSeconds'])
        if isinstance(interval, bool) or not isinstance(interval, int) or not 60 <= interval <= 3600:
            raise ValueError('采集周期必须为 60–3600 秒。')
        sources = data.get('sources')
        if not isinstance(sources, dict) or set(sources) - set(ADAPTERS): raise ValueError('数据源配置无效。')
        if any(not isinstance(value, bool) for value in sources.values()): raise ValueError('数据源开关无效。')
        mode = data.get('ccSwitchMode', self.config['sources']['cc-switch']['mode'])
        if mode not in ('snapshot', 'independent'): raise ValueError('CC Switch 读取模式无效。')
        snapshot_path = data.get('ccSwitchSnapshotPath', str(cc_snapshot_path(self.config['sources']['cc-switch'])))
        if not isinstance(snapshot_path, str) or not snapshot_path or len(snapshot_path) > 1000 or '\x00' in snapshot_path:
            raise ValueError('快照文件路径无效。')
        if not Path(snapshot_path).expanduser().is_absolute(): raise ValueError('快照文件应使用绝对路径。')
        url = data.get('publicUrl', self.config.get('publicUrl', '')).strip().rstrip('/')
        if url:
            p = urllib.parse.urlsplit(url)
            if p.scheme != 'https' or not p.hostname or p.username or p.password or p.query or p.fragment or p.path not in ('', '/'):
                raise ValueError('手机连接地址应为不含路径和凭证的 HTTPS 地址。')
        with self.lock:
            self.config['intervalSeconds'] = interval
            self.config['publicUrl'] = url
            self.config['sources']['cc-switch'].update(mode=mode, snapshotPath=snapshot_path)
            for key, value in sources.items():
                self.config['sources'][key]['enabled'] = value
            # The bridge already includes native subscription caches.
            if mode == 'snapshot' and self.config['sources']['cc-switch']['enabled']:
                for key in ('codex', 'claude', 'codexbar'):
                    if not self.config['sources'][key].get('managed'): self.config['sources'][key]['enabled'] = False
            if self.config['sources']['codexbar']['enabled']:
                for key in ('codex', 'claude'):
                    if not self.config['sources'][key].get('managed'): self.config['sources'][key]['enabled'] = False
            enabled = {k for k, v in self.config['sources'].items() if v.get('enabled')}
            self.rows = [r for r in self.rows if r.get('_sourceId') in enabled]
            self.revision += 1
            self.last_started = 0
            self.cache_signature = None
            write_private(self.directory / 'config.json', self.config)
        self.export_icloud()
        self.request_refresh(force=True)

    def request_refresh(self, force=False, cached_only=False, manual=False):
        if self.stop.is_set(): return False
        if not force and not cached_only and time.monotonic() - self.last_started < 15: return False
        if not self.refresh_lock.acquire(blocking=False): return False
        if not cached_only: self.last_started = time.monotonic()
        threading.Thread(target=self.collect, kwargs={'cached_only': cached_only, 'manual': manual or force}, daemon=True).start()
        return True

    def widget_settings(self):
        with self.lock:
            return {'providerIds': copy.deepcopy(self.config['widgetProviderIds'])}

    def configure_widget(self, data):
        if not isinstance(data, dict) or set(data) != {'providerIds'}:
            raise ValueError('需要账户列表。')
        ids = data['providerIds']
        if ids is not None:
            if not isinstance(ids, list) or len(ids) > 500 or any(not isinstance(uid, str) or not uid or len(uid) > 200 for uid in ids):
                raise ValueError('账户列表无效。')
            if len(set(ids)) != len(ids): raise ValueError('账户不能重复。')
        with self.lock:
            known = {r['id'] for r in self.rows} | set(self.config['widgetProviderIds'] or [])
            if ids is not None and set(ids) - known: raise ValueError('账户列表已变化，请刷新后重试。')
            configuration = copy.deepcopy(self.config)
            configuration['widgetProviderIds'] = copy.deepcopy(ids)
            write_private(self.directory / 'config.json', configuration)
            self.config = configuration
        self.export_icloud()
        # Display preferences take effect on the next GET. Never poll a provider.
        return self.widget_settings()

    def collect(self, cached_only=False, manual=False):
        try:
            with self.lock:
                configuration = copy.deepcopy(self.config)
                revision = self.revision
                old = {r['id']: copy.deepcopy(r) for r in self.rows}
                old_status = {s['id']: copy.deepcopy(s) for s in self.source_status}
                retries = copy.deepcopy(self.source_retries)
            enabled = {k: v for k, v in configuration['sources'].items() if v.get('enabled')}
            if cached_only:
                enabled = {k: v for k, v in enabled.items() if k == 'cc-switch' and v.get('mode') == 'snapshot'}
            skipped = {k for k in enabled if not manual and not cached_only
                       and retries.get(k, {}).get('due', 0) > time.monotonic()}
            queried = {k: v for k, v in enabled.items() if k not in skipped}
            all_rows, statuses = [], []
            def query(pair):
                key, config = pair
                try: return key, ADAPTERS[key](config), None
                except SourceError as error: return key, [], str(error)
                except Exception: return key, [], '数据源读取失败，请检查本地配置和版本。'
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                for key, rows, error in pool.map(query, queried.items()):
                    statuses.append({'id': key, 'error': error, 'count': len(rows), 'attemptAt': now()})
                    failed = bool(error) or any(r.get('status') == 'error' for r in rows)
                    if failed:
                        failures = min(8, retries.get(key, {}).get('failures', 0) + 1)
                        delay = min(3600, configuration['intervalSeconds'] * 2 ** (failures - 1))
                        retries[key] = {'failures': failures, 'due': time.monotonic() + delay}
                    else:
                        retries.pop(key, None)
                    if error:
                        rows = [copy.deepcopy(r) for r in old.values() if r.get('_sourceId') == key]
                        for r in rows: r.update(status='error', error=error, lastAttemptAt=now())
                    for r in rows:
                        previous = old.get(r['id'])
                        if r.get('status') == 'error' and previous and previous.get('lastSuccessAt'):
                            r['windows'] = previous['windows']
                            r['balances'] = previous['balances']
                            r['lastSuccessAt'] = previous['lastSuccessAt']
                        r['_sourceId'] = key
                        all_rows.append(r)
            with self.lock:
                # Discard results from an old mode/configuration, including in-flight HTTP.
                if revision != self.revision: return
                all_rows += [r for r in old.values() if r.get('_sourceId') in skipped]
                statuses += [s for key, s in old_status.items() if key in skipped]
                if cached_only:
                    all_rows += [r for r in self.rows if r.get('_sourceId') not in enabled]
                    statuses += [s for s in self.source_status if s['id'] not in enabled]
                active = {k for k, v in self.config['sources'].items() if v.get('enabled')}
                self.source_retries = {k: v for k, v in retries.items() if k in active}
                self.rows = [r for r in all_rows if r['_sourceId'] in active]
                self.source_status = [s for s in statuses if s['id'] in active]
                self.last_collection = now()
                if self.phone_refresh.get('state') == 'collecting':
                    self.phone_refresh.update(state='complete', completedAt=self.last_collection)
                    write_private(self.directory / 'phone-refresh.json', self.phone_refresh)
                write_private(self.directory / 'snapshot.json', {'providers': self.rows, 'sources': self.source_status, 'lastCollectionAt': self.last_collection})
            self.export_icloud()
        finally:
            self.refresh_lock.release()

    def snapshot(self, widget_only=False):
        with self.lock:
            ttl = 2 * self.config['intervalSeconds'] + 30
            providers = copy.deepcopy(self.rows)
            for r in providers:
                r.pop('_sourceId', None)
                timestamp = stamp(r.get('lastSuccessAt'))
                if timestamp:
                    age = time.time() - dt.datetime.fromisoformat(timestamp.replace('Z', '+00:00')).timestamp()
                    # Preserve a confirmed collection failure across the cloud
                    # projection, which intentionally removes error messages.
                    if r.get('status') != 'error' and (age > ttl or r.get('error')):
                        r['status'] = 'stale'
            selection = self.config['widgetProviderIds']
            if widget_only and selection is not None:
                by_id = {r['id']: r for r in providers}
                providers = [by_id[uid] for uid in selection if uid in by_id]
            return {'schemaVersion': 1, 'demo': False, 'generatedAt': now(), 'lastCollectionAt': self.last_collection,
                    'widgetProviderIds': copy.deepcopy(selection),
                    'ccSwitchMode': self.config['sources']['cc-switch']['mode'],
                    'cacheOnly': self.config['sources']['cc-switch'].get('enabled', False) and self.config['sources']['cc-switch']['mode'] == 'snapshot' and not any(v.get('enabled') for k,v in self.config['sources'].items() if k!='cc-switch'),
                    'intervalSeconds': self.config['intervalSeconds'], 'staleAfterSeconds': ttl,
                    'refreshing': self.refresh_lock.locked(), 'providers': providers,
                    'sources': copy.deepcopy(self.source_status),
                    'enabledCount': sum(bool(v.get('enabled')) for v in self.config['sources'].values())}

    def loop(self):
        while not self.stop.is_set():
            if os.environ.get('QUOTA_POCKET_MANAGED') == 'launchd':
                try: service_manager.trim_logs(Path.home() / 'Library/Logs/QuotaPocket')
                except OSError: pass
            # macOS monotonic clocks need not advance while asleep. A wall-clock
            # gap lets a wake trigger fresh collection rather than wait again.
            wall = time.time()
            if wall - self.last_loop_at > 30:
                with self.lock:
                    self.last_started = float('-inf')
                    self.source_retries.clear()
            self.last_loop_at = wall
            self.check_phone_refresh()
            if time.monotonic() - self.last_started >= self.config['intervalSeconds']:
                self.request_refresh()
            with self.lock:
                cc = copy.deepcopy(self.config['sources']['cc-switch'])
            if cc.get('enabled') and cc.get('mode') == 'snapshot':
                try:
                    stat = cc_snapshot_path(cc).stat()
                    signature = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
                except OSError:
                    signature = ('missing',)
                if signature != self.cache_signature and self.request_refresh(cached_only=True):
                    self.cache_signature = signature
            self.stop.wait(5)


class Handler(BaseHTTPRequestHandler):
    server_version = 'QuotaPocket/0.1'

    def log_message(self, format, *args):
        pass  # Never put paths, tokens, or upstream error bodies into access logs.

    @property
    def store(self): return self.server.store

    def valid_host(self):
        raw = self.headers.get('Host', '')
        parsed = urllib.parse.urlsplit('http://' + raw)
        host = parsed.hostname
        allowed = {'127.0.0.1', 'localhost', '::1'}
        public = self.store.config.get('publicUrl')
        if public: allowed.add(urllib.parse.urlsplit(public).hostname)
        return host in allowed

    def authorized(self, admin=False):
        raw = self.headers.get('Authorization', '')
        token = raw[7:] if raw.startswith('Bearer ') else ''
        role = self.store.role(token)
        return role == 'admin' if admin else role in ('admin', 'viewer')

    def local_request(self):
        host = urllib.parse.urlsplit('http://' + self.headers.get('Host', '')).hostname
        return host in {'127.0.0.1', 'localhost', '::1'}

    def send(self, status, body, mime='application/json; charset=utf-8', private=True):
        if not isinstance(body, bytes): body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store' if private else 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'")
        self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError): pass

    def do_GET(self):
        if not self.valid_host(): return self.send(403, {'error': '不受信任的访问地址。'})
        path = urllib.parse.urlsplit(self.path).path
        if path == '/api/demo': return self.send(200, demo_snapshot())
        if path == '/health': return self.send(200, {'ok': True, 'version': VERSION, 'build': RUNNING_BUILD})
        if path.startswith('/api/'):
            if not self.authorized(): return self.send(401, {'error': '请连接此设备，或重新输入访问凭证。'})
            if path == '/api/subscriptions':
                if not self.authorized(admin=True): return self.send(403, {'error':'只有电脑管理端可以连接订阅。'})
                return self.send(200, self.store.subscription_status())
            if path == '/api/snapshot': return self.send(200, self.store.snapshot(widget_only=not self.authorized(admin=True)))
            if path == '/api/mobile/snapshot': return self.send(200, self.store.mobile_snapshot())
            if path == '/api/runtime':
                if not self.authorized(admin=True): return self.send(403, {'error': '需要电脑管理权限。'})
                return self.send(200, self.store.runtime_status())
            if path == '/api/hosted':
                if not self.authorized(admin=True): return self.send(403, {'error': '需要电脑管理权限。'})
                return self.send(200, self.store.hosted.status())
            if path == '/api/widget-settings':
                if not self.authorized(admin=True): return self.send(403, {'error': '只有管理端可以选择小组件账户。'})
                return self.send(200, self.store.widget_settings())
            if path == '/api/icloud':
                if not self.authorized(admin=True): return self.send(403, {'error': '只有电脑管理端可以查看 iCloud 同步。'})
                return self.send(200, self.store.icloud.status())
            if path == '/api/icloud-accounts':
                if not self.authorized(admin=True): return self.send(403, {'error': '需要电脑管理权限。'})
                return self.send(200, self.store.icloud_accounts())
            if path == '/api/settings':
                if not self.authorized(admin=True): return self.send(403, {'error': '只读设备不能修改数据源。'})
                return self.send(200, self.store.settings())
            if path == '/api/connection':
                if not self.authorized(admin=True): return self.send(403, {'error': '需要本机管理权限。'})
                with self.store.lock:
                    return self.send(200, {'url': self.store.config.get('publicUrl', ''), 'token': self.store.keys['viewer']})
            return self.send(404, {'error': '接口不存在。'})
        downloads = {'/downloads/Quota-Pocket.js': ROOT / 'widgets/Quota-Pocket.js', '/downloads/android.md': ROOT / 'widgets/android.md', '/downloads/tasker-format.js': ROOT / 'widgets/tasker-format.js'}
        if path in downloads:
            target = downloads[path]
            if target.is_file(): return self.send(200, target.read_bytes(), 'text/plain; charset=utf-8')
        web = ROOT / 'web'
        relative = 'index.html' if path == '/' else urllib.parse.unquote(path.lstrip('/'))
        target = (web / relative).resolve()
        if web.resolve() not in target.parents or not target.is_file(): return self.send(404, {'error': '页面不存在。'})
        mime = mimetypes.guess_type(str(target))[0] or 'application/octet-stream'
        if target.suffix == '.js': mime = 'application/javascript'
        return self.send(200, target.read_bytes(), mime, private=False)

    def do_POST(self):
        if not self.valid_host(): return self.send(403, {'error': '不受信任的访问地址。'})
        origin = self.headers.get('Origin')
        if origin:
            actual = urllib.parse.urlsplit(origin)
            allowed = {f'http://{self.headers.get("Host")}', self.store.config.get('publicUrl')}
            if origin not in allowed or actual.scheme not in ('http', 'https'):
                return self.send(403, {'error': '请求来源不匹配。'})
        path = urllib.parse.urlsplit(self.path).path
        if path == '/api/pair/exchange':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 1 <= length <= 1024 or not self.headers.get('Content-Type', '').startswith('application/json'): raise ValueError()
                body = json.loads(self.rfile.read(length))
                result = self.store.exchange_pairing(body.get('code'))
                return self.send(200, result) if result else self.send(410, {'error': '配对链接已过期或已使用，请在电脑上重新生成。'})
            except (ValueError, TypeError, AttributeError): return self.send(400, {'error': '配对请求无效。'})
        if not self.authorized(): return self.send(401, {'error': '访问凭证无效。'})
        if path in ('/api/refresh', '/api/mobile/refresh'):
            started = self.store.request_refresh(manual=True)
            with self.store.lock:
                return self.send(202, {'started': started, 'refreshing': self.store.refresh_lock.locked(),
                                      'collectionId': self.store.last_collection,
                                      'retryAfterSeconds': max(0, int(15 - (time.monotonic() - self.store.last_started)))})
        if not self.authorized(admin=True): return self.send(403, {'error': '只读设备不能修改设置。'})
        if path == '/api/shutdown':
            if not self.local_request(): return self.send(403, {'error': '仅允许本机操作。'})
            self.store.stop.set()
            self.send(202, {'stopping': True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if path == '/api/service':
            if not self.local_request(): return self.send(403, {'error': '仅允许本机操作。'})
            if sys.platform != 'darwin' or self.store.directory.resolve() != (ROOT / '.state').resolve():
                return self.send(400, {'error': '后台管理仅支持 Mac 默认状态目录。'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 1 <= size <= 256: raise ValueError()
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict) or set(body) != {'action'} or body['action'] not in ('start', 'disable', 'restart'):
                    raise ValueError()
                service_manager.check_owned()
                with (self.store.directory / 'service-action.log').open('w') as log:
                    subprocess.Popen([sys.executable, str(ROOT / 'service_manager.py'), body['action']],
                                     cwd=ROOT, stdout=log, stderr=log, start_new_session=True)
                return self.send(202, {'accepted': True, 'action': body['action']})
            except (ValueError, OSError):
                return self.send(400, {'error': '后台操作未启动，请检查配置和目录权限。'})
        if path in ('/api/hosted', '/api/hosted/pair'):
            try:
                if path == '/api/hosted/pair':
                    return self.send(200, self.store.hosted.pair())
                size = int(self.headers.get('Content-Length', '0'))
                if not 1 <= size <= 1000 or not self.headers.get('Content-Type', '').startswith('application/json'):
                    raise ValueError()
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict) or set(body) != {'enabled'}:
                    raise ValueError()
                return self.send(200, self.store.hosted.configure(body['enabled']))
            except SyncError as error:
                return self.send(400, {'error': str(error)})
            except (ValueError, TypeError):
                return self.send(400, {'error': '同步设置无效。'})
        if path.startswith('/api/subscriptions/'):
            parts = path.split('/')
            if len(parts) != 5 or parts[3] not in ('codex','claude') or parts[4] not in ('start','cancel','finish'):
                return self.send(404, {'error':'未知订阅操作。'})
            kind, action = parts[3:]
            try:
                if action == 'start':
                    self.store.subscriptions.start(kind)
                    return self.send(202, self.store.subscription_status())
                length = int(self.headers.get('Content-Length','0'))
                if not 1 <= length <= 5000 or not self.headers.get('Content-Type','').startswith('application/json'): raise ValueError()
                body = json.loads(self.rfile.read(length))
                if action == 'cancel': self.store.subscriptions.cancel(kind,body.get('id'))
                else: self.store.subscriptions.finish(kind,body.get('id'),body.get('code'))
                return self.send(200,self.store.subscription_status())
            except (LoginError,ValueError,TypeError,AttributeError) as error:
                return self.send(400, {'error':str(error) if isinstance(error,LoginError) else '订阅连接请求无效。'})
        if path == '/api/pair':
            try: return self.send(200, self.store.create_pairing())
            except ValueError as error: return self.send(400, {'error': str(error)})
        if path == '/api/widget-settings':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length < 1 or length > 64000: raise ValueError('请求大小无效。')
                if not self.headers.get('Content-Type', '').startswith('application/json'): raise ValueError('需要 JSON 请求。')
                result = self.store.configure_widget(json.loads(self.rfile.read(length)))
                return self.send(200, result)
            except (ValueError, TypeError):
                return self.send(400, {'error': '账户选择无效或列表已变化，请刷新后重试。'})
        if path == '/api/icloud':
            if not self.local_request():
                return self.send(403, {'error': '只能在这台电脑上修改 iCloud 同步。'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 1 <= length <= 1000 or not self.headers.get('Content-Type', '').startswith('application/json'):
                    raise ValueError()
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict) or set(body) != {'enabled'}: raise ValueError()
                result = self.store.icloud.configure(body['enabled'], self.store.icloud_snapshot)
                return self.send(200, result)
            except ICloudError as error:
                return self.send(400, {'error': str(error)})
            except (ValueError, TypeError, AttributeError):
                return self.send(400, {'error': 'iCloud 同步设置无效。'})
        if path == '/api/icloud-accounts':
            if not self.local_request(): return self.send(403, {'error': '只能在电脑端设置同步范围。'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 1 <= length <= 64000 or not self.headers.get('Content-Type', '').startswith('application/json'): raise ValueError()
                return self.send(200, self.store.configure_icloud_accounts(json.loads(self.rfile.read(length))))
            except (ValueError, TypeError): return self.send(400, {'error': '同步账户列表无效或已变化。'})
        if path == '/api/revoke':
            with self.store.lock:
                self.store.keys['viewer'] = secrets.token_urlsafe(32)
                self.store.pairings.clear()
                write_private(self.store.directory / 'access.json', self.store.keys)
            return self.send(200, {'ok': True})
        if path == '/api/settings':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length < 1 or length > 8000: raise ValueError('请求大小无效。')
                if not self.headers.get('Content-Type', '').startswith('application/json'): raise ValueError('需要 JSON 请求。')
                self.store.configure(json.loads(self.rfile.read(length)))
                return self.send(200, self.store.settings())
            except (ValueError, TypeError, AttributeError):
                return self.send(400, {'error': '配置无效：检查读取模式、快照绝对路径、60–3600 秒周期、HTTPS 地址和数据源开关。'})
        return self.send(404, {'error': '接口不存在。'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8931)
    parser.add_argument('--state-dir', default=str(ROOT / '.state'))
    parser.add_argument('--open', action='store_true', help='Open local management with an access token in the URL fragment')
    parser.add_argument('--pair', action='store_true', help='Print the read-only device connection JSON locally')
    args = parser.parse_args()
    if args.state_dir == str(ROOT / '.state') and service_manager.runtime_root().resolve() != ROOT.resolve():
        installed_state = service_manager.state_root(ROOT)
        if installed_state != ROOT / '.state':
            os.execv(sys.executable, [sys.executable, str(service_manager.runtime_root() / 'server.py'), *sys.argv[1:]])
    url = 'http://127.0.0.1:%d/' % args.port
    # Reopening must not instantiate Store or rewrite iCloud before the lock.
    if args.open:
        keys = load_json(Path(args.state_dir) / 'access.json', {})
        try:
            request = urllib.request.Request(url + 'api/snapshot', headers={'Authorization': 'Bearer ' + keys.get('admin', '')})
            with urllib.request.urlopen(request, timeout=3) as response:
                compatible = json.load(response).get('schemaVersion') == 1
            if compatible:
                webbrowser.open(url + '#access=' + keys['admin'])
                return
        except (OSError, ValueError):
            pass
    try:
        lock_handle = instance_lock(args.state_dir)
    except ValueError as error:
        parser.error(str(error))
    store = Store(args.state_dir)
    if args.pair:
        print(json.dumps({'url': store.config.get('publicUrl', ''), 'token': store.keys['viewer']}, indent=2))
        return
    url = 'http://127.0.0.1:%d/' % args.port
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    except OSError:
        if args.open:
            # Reopen the existing same-state instance, never blindly attach to another server.
            request = urllib.request.Request(url + 'api/snapshot', headers={'Authorization': 'Bearer ' + store.keys['admin']})
            try:
                with urllib.request.urlopen(request, timeout=3) as response:
                    compatible = json.load(response).get('schemaVersion') == 1
                if compatible:
                    webbrowser.open(url + '#access=' + store.keys['admin'])
                    print('Opened existing Quota Pocket management page.')
                    return
            except (OSError, ValueError):
                pass
        parser.error('端口已占用，请使用其他 --port 或检查现有服务。')
    server.store = store
    server.daemon_threads = True
    store.hosted.start()
    threading.Thread(target=store.loop, daemon=True).start()
    print('Quota Pocket: ' + url, flush=True)
    print('Preview: ' + url + '?demo=1', flush=True)
    print('Use --open to open local management. Sources are disabled until selected.', flush=True)
    if args.open: webbrowser.open(url + '#access=' + store.keys['admin'])
    def terminate(signum, frame):
        store.stop.set()
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, terminate)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        store.stop.set()
        store.hosted.close()
        store.subscriptions.close()
        # Finish an in-flight export before a replacement process can write.
        with store.refresh_lock:
            server.server_close()
        lock_handle.close()


if __name__ == '__main__': main()
