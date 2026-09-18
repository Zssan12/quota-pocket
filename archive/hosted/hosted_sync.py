"""Desktop publisher for the hosted snapshot service; disabled until enabled."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from icloud_sync import _private_json, quota_projection
from relay_server import https_origin

# Set by the release maintainer only after deploying and verifying the endpoint.
# Never invent a production domain or silently upload to an unverified service.
DEFAULT_SYNC_URL = ''


class SyncError(ValueError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HostedSync:
    def __init__(self, state_dir, snapshot_supplier, url=None, transport=None):
        self.path = Path(state_dir) / 'hosted-sync.json'
        self.supplier = snapshot_supplier
        self.lock = threading.RLock()
        self.io_lock = threading.Lock()
        self.changed = threading.Event()
        self.stopped = threading.Event()
        self.thread = None
        self.next_try = 0
        self.failures = 0
        self.transport = transport or self._request
        try:
            value = json.loads(self.path.read_text())
            self.state = value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            self.state = {}
        selected = url if url is not None else os.environ.get('QUOTA_POCKET_SYNC_URL') or DEFAULT_SYNC_URL or self.state.get('url', '')
        self.url = https_origin(selected) if selected else ''
        if self.state.get('url') not in (None, '', self.url):
            # Do not send an existing device's bearer credentials to another host.
            raise SyncError('同步地址已变化，请使用独立的状态目录迁移。')
        self.error = None

    def _save(self):
        _private_json(self.path, self.state)

    def _request(self, method, path, token=None, body=None):
        headers = {'Accept': 'application/json'}
        data = None
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if body is not None:
            data = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(self.url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=10) as response:
                raw = response.read(256001)
                if len(raw) > 256000:
                    raise SyncError('同步服务返回的数据过大。')
                result = json.loads(raw)
                if not isinstance(result, dict):
                    raise SyncError('同步服务返回格式无效。')
                return result
        except urllib.error.HTTPError as error:
            messages = {403: '同步身份无效，请检查部署或重新连接。', 429: '同步请求较多，稍后自动重试。',
                        503: '同步服务暂不可用或试用名额已满。'}
            raise SyncError(messages.get(error.code, '同步请求失败（HTTP %d），稍后自动重试。' % error.code)) from None
        except (OSError, ValueError):
            raise SyncError('暂时无法连接同步服务，稍后自动重试。') from None

    def status(self):
        with self.lock:
            return {'configured': bool(self.url), 'enabled': self.state.get('enabled') is True,
                    'ready': self.state.get('enabled') is True and bool(self.state.get('lastUploadedAt')),
                    'url': self.url, 'lastUploadedAt': self.state.get('lastUploadedAt'),
                    'disconnectPending': self.state.get('disconnectPending') is True,
                    'error': self.error}

    def configure(self, enabled):
        if not isinstance(enabled, bool):
            raise SyncError('同步开关无效。')
        if enabled and not self.url:
            raise SyncError('默认同步服务尚未部署，当前仍可使用 iCloud。')
        with self.io_lock, self.lock:
            if enabled and self.state.get('disconnectPending'):
                raise SyncError('正在撤销旧连接，请等待云端清除完成。')
            self.state.update(enabled=enabled, url=self.url)
            if enabled:
                self.state.setdefault('writerToken', secrets.token_urlsafe(32))
            else:
                self.state['disconnectPending'] = bool(self.state.get('room'))
            self._save()
            self.next_try = 0
            self.changed.set()
        return self.status()

    def wake(self):
        self.changed.set()

    def sync_once(self):
        with self.io_lock:
            with self.lock:
                state = dict(self.state)
            if not self.url or not (state.get('enabled') is True or state.get('disconnectPending')):
                return
            room, writer = state.get('room'), state.get('writerToken')
            if state.get('disconnectPending'):
                self.transport('POST', '/v2/rooms/' + room + '/disconnect', writer, {})
                with self.lock:
                    self.state.update(disconnectPending=False, lastUploadedAt=None, fingerprint=None)
                    self.error = None
                    self._save()
                return
            if not room:
                result = self.transport('POST', '/v2/enroll', body={'writerToken': writer})
                room = result.get('room')
                if result.get('protocol') != 'quota-pocket-hosted-v2' or not isinstance(room, str) or len(room) != 32 or any(c not in '0123456789abcdef' for c in room):
                    raise SyncError('同步服务的设备响应无效。')
                with self.lock:
                    self.state['room'] = room
                    self._save()
            snapshot = quota_projection(self.supplier())
            comparable = {k: v for k, v in snapshot.items() if k != 'generatedAt'}
            fingerprint = hashlib.sha256(json.dumps(comparable, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if fingerprint == state.get('fingerprint') and time.time() - state.get('lastUploadedAt', 0) < 300:
                return
            path = '/v2/rooms/' + room
            remote = self.transport('GET', path + '/status', writer)
            seq = remote.get('seq')
            if isinstance(seq, bool) or not isinstance(seq, int) or not 0 <= seq < 9007199254740991:
                raise SyncError('同步服务返回的版本无效。')
            self.transport('PUT', path + '/snapshot', writer, {'seq': seq + 1, 'snapshot': snapshot})
            with self.lock:
                self.state.update(lastUploadedAt=time.time(), fingerprint=fingerprint)
                self.error = None
                self._save()

    def pair(self):
        with self.io_lock:
            with self.lock:
                if not self.status()['ready']:
                    raise SyncError('请等待首次额度上传完成。')
                room, writer = self.state['room'], self.state['writerToken']
            result = self.transport('POST', '/v2/rooms/' + room + '/pair', writer, {})
            code = result.get('code')
            if not isinstance(code, str) or not 32 <= len(code) <= 100 or any(not (c.isascii() and (c.isalnum() or c in '_-')) for c in code):
                raise SyncError('同步服务返回的配对码无效。')
            return {'url': self.url + '/connect.html#' + urllib.parse.urlencode({'room': room, 'pair': code}),
                    'expiresIn': min(600, max(1, int(result.get('expiresIn', 600))))}

    def start(self):
        if self.thread:
            return
        self.thread = threading.Thread(target=self._loop, daemon=True, name='quota-pocket-upload')
        self.thread.start()

    def _loop(self):
        while not self.stopped.is_set():
            if time.monotonic() >= self.next_try:
                try:
                    self.sync_once()
                    self.failures = 0
                    self.next_try = time.monotonic() + 5
                except Exception as error:
                    with self.lock:
                        self.error = str(error) if isinstance(error, SyncError) else '上传暂未成功，保留原采集时间并自动重试。'
                    self.failures = min(6, self.failures + 1)
                    self.next_try = time.monotonic() + min(300, 5 * 2 ** self.failures)
            self.changed.wait(15)
            self.changed.clear()

    def close(self):
        self.stopped.set()
        self.changed.set()
        if self.thread:
            self.thread.join(timeout=12)
