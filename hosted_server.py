#!/usr/bin/env python3
"""Small hosted JSON snapshot service, behind an HTTPS reverse proxy.

This is a separate v2 protocol/database from the experimental ciphertext relay.
Only display data reaches this process; it never runs adapters or provider scripts.
"""
import argparse
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
import urllib.parse

from icloud_sync import quota_projection
from relay_server import RelayError, RelayHandler, RelayStore, digest, https_origin
from widgeto import widgeto_config, widgeto_data

ROOT = Path(__file__).resolve().parent
MAX_BODY = 256_000


def display_snapshot(value):
    if not isinstance(value, dict) or value.get('schemaVersion') != 1 or not isinstance(value.get('providers'), list):
        raise RelayError(400, '需要有效的额度快照。')
    if len(value['providers']) > 100:
        raise RelayError(413, '最多同步 100 个账户。')
    # Do not carry iCloud selection metadata or a legacy refresh command.
    allowed = ('schemaVersion', 'generatedAt', 'lastCollectionAt', 'intervalSeconds', 'staleAfterSeconds', 'providers')
    clean = quota_projection({k: value[k] for k in allowed if k in value})
    if len(json.dumps(clean, ensure_ascii=False).encode()) > MAX_BODY - 1000:
        raise RelayError(413, '额度快照过大。')
    return clean


class HostedStore(RelayStore):
    def __init__(self, directory, public_url, max_devices=200, retention=7 * 86400):
        super().__init__(directory, public_url, retention)
        self.max_devices = max_devices
        self.db.execute('CREATE UNIQUE INDEX IF NOT EXISTS unique_writer ON rooms(writer_hash)')

    def enroll(self, body):
        hashed = digest(body.get('writerToken'))
        if not hashed:
            raise RelayError(400, '设备身份无效。')
        with self.lock:
            # A lost response may be retried without consuming another device slot.
            existing = self.db.execute('SELECT id FROM rooms WHERE writer_hash=?', (hashed,)).fetchone()
            if existing:
                return {'room': existing['id'], 'protocol': 'quota-pocket-hosted-v2'}
            if self.db.execute('SELECT count(*) FROM rooms').fetchone()[0] >= self.max_devices:
                raise RelayError(503, '试用设备名额已满，请稍后重试。')
            room = secrets.token_hex(16)
            self.db.execute('INSERT INTO rooms(id,writer_hash) VALUES(?,?)', (room, hashed))
            return {'room': room, 'protocol': 'quota-pocket-hosted-v2'}

    def publish(self, uid, token, body):
        with self.lock:
            row = self.writer(uid, token)
            seq = body.get('seq')
            if isinstance(seq, bool) or not isinstance(seq, int) or not 1 <= seq <= 9007199254740991:
                raise RelayError(400, '快照版本无效。')
            encoded = json.dumps(display_snapshot(body.get('snapshot')), ensure_ascii=False, separators=(',', ':'))
            if seq == row['seq'] and encoded == row['envelope']:
                return {'seq': seq}  # Idempotent network retry.
            if seq != row['seq'] + 1:
                raise RelayError(409, '快照版本已变化。')
            if row['uploaded'] and time.time() - row['uploaded'] < 5:
                raise RelayError(429, '同步过于频繁，请稍后重试。')
            self.db.execute('UPDATE rooms SET seq=?,envelope=?,uploaded=? WHERE id=?',
                            (seq, encoded, time.time(), uid))
        return {'seq': seq}

    def exchange(self, body):
        result = super().exchange(body)
        result['protocol'] = 'quota-pocket-hosted-v2'
        return result

    def disconnect(self, uid, token):
        with self.lock:
            self.writer(uid, token)
            # Keep an identity tombstone; no filesystem deletion or token reuse.
            self.db.execute('UPDATE rooms SET envelope=NULL,uploaded=NULL,epoch=epoch+1 WHERE id=?', (uid,))
        return {'ok': True}


class RequestLimits:
    def __init__(self):
        self.lock = threading.Lock()
        self.windows = {}

    def allow(self, key, limit, seconds):
        with self.lock:
            current = time.monotonic()
            if len(self.windows) >= 10000:
                self.windows = {k: v for k, v in self.windows.items() if v[0] > current}
                if len(self.windows) >= 10000 and key not in self.windows:
                    return False
            deadline, count = self.windows.get(key, (current + seconds, 0))
            if deadline <= current:
                deadline, count = current + seconds, 0
            if count >= limit:
                return False
            self.windows[key] = (deadline, count + 1)
            return True


class HostedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, store, trust_proxy=False):
        self.store = store
        self.trust_proxy = trust_proxy
        self.limits = RequestLimits()
        self.slots = threading.BoundedSemaphore(32)
        super().__init__(address, HostedHandler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        # Do not log request objects, bodies, pairing codes or credentials.
        pass


class HostedHandler(RelayHandler):
    server_version = 'QuotaPocketHosted/2'

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def body(self):
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if self.headers.get('Transfer-Encoding') or not 0 < size <= MAX_BODY:
                raise ValueError()
            if not self.headers.get('Content-Type', '').startswith('application/json'):
                raise ValueError()
            value = json.loads(self.rfile.read(size))
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, TypeError, UnicodeError):
            raise RelayError(400, '请求格式或大小无效。')

    def dispatch(self):
        try:
            store = self.server.store
            parsed = urllib.parse.urlsplit(self.path)
            if parsed.query:
                raise RelayError(400, '访问凭证只能放在请求头中。')
            path = parsed.path
            origin = self.headers.get('Origin')
            if origin not in (None, store.public_url):
                raise RelayError(403, '请求来源无效。')
            ip = self.client_address[0]
            if self.server.trust_proxy:
                ip = self.headers.get('X-Real-IP', ip)[:64]
            if not self.server.limits.allow(('request', ip), 120, 60):
                raise RelayError(429, '请求过于频繁，请稍后重试。')
            raw = self.headers.get('Authorization', '')
            token = raw[7:] if raw.startswith('Bearer ') else ''
            if self.command == 'GET' and path == '/health':
                return self.send_json(200, {'ok': True, 'protocol': 'quota-pocket-hosted-v2'})
            if self.command == 'POST' and path == '/v2/enroll':
                if not self.server.limits.allow(('enroll', ip), 10, 3600):
                    raise RelayError(429, '设备接入过于频繁，请稍后重试。')
                return self.send_json(200, store.enroll(self.body()))
            if self.command == 'POST' and path == '/v2/pair/exchange':
                return self.send_json(200, store.exchange(self.body()))
            match = re.fullmatch(r'/v2/rooms/([a-f0-9]{32})/(status|snapshot|widgeto|config|pair|readers|disconnect)(?:/([a-f0-9]{32})/revoke)?', path)
            if match:
                room, action, reader = match.groups()
                if reader and action == 'readers' and self.command == 'POST':
                    return self.send_json(200, store.revoke(room, token, reader))
                if not reader:
                    if self.command == 'GET' and action in ('snapshot', 'widgeto', 'config'):
                        snapshot = store.snapshot(room, token)
                        result = snapshot if action == 'snapshot' else widgeto_data(snapshot)
                        if action == 'config':
                            result = widgeto_config(store.public_url + '/v2/rooms/' + room + '/widgeto', token)
                        return self.send_json(200, result)
                    if self.command == 'GET' and action == 'status':
                        return self.send_json(200, store.status(room, token))
                    if self.command == 'GET' and action == 'readers':
                        return self.send_json(200, store.readers(room, token))
                    if self.command == 'POST' and action == 'pair':
                        return self.send_json(200, store.pair(room, token))
                    if self.command == 'POST' and action == 'disconnect':
                        return self.send_json(200, store.disconnect(room, token))
                    if self.command == 'PUT' and action == 'snapshot':
                        with store.lock:
                            store.writer(room, token)
                        return self.send_json(200, store.publish(room, token, self.body()))
            assets = {'/': ('hosted.html', 'text/html; charset=utf-8'),
                      '/connect.html': ('hosted.html', 'text/html; charset=utf-8'),
                      '/hosted.js': ('hosted.js', 'application/javascript'),
                      '/hosted.css': ('hosted.css', 'text/css; charset=utf-8')}
            if self.command == 'GET' and path in assets:
                name, mime = assets[path]
                return self.send_json(200, (ROOT / 'web' / name).read_bytes(), mime)
            raise RelayError(404, '接口不存在。')
        except RelayError as error:
            self.send_json(error.status, {'error': str(error)})
        except Exception:
            self.send_json(500, {'error': '同步服务暂不可用。'})

    do_GET = dispatch
    do_POST = dispatch
    do_PUT = dispatch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8941)
    parser.add_argument('--state-dir', default=os.environ.get('QP_HOSTED_STATE', '.state/hosted'))
    parser.add_argument('--public-url', default=os.environ.get('QP_HOSTED_PUBLIC_URL', ''))
    parser.add_argument('--max-devices', type=int, default=200)
    parser.add_argument('--trust-proxy', action='store_true')
    args = parser.parse_args()
    try:
        url = https_origin(args.public_url)
    except ValueError as error:
        parser.error(str(error))
    store = HostedStore(args.state_dir, url, args.max_devices)
    server = HostedHTTPServer((args.bind, args.port), store, args.trust_proxy)
    stop = threading.Event()
    def expire():
        while not stop.wait(3600):
            store.expire()
    store.expire()
    threading.Thread(target=expire, daemon=True).start()
    print('Quota Pocket hosted sync listening on port ' + str(args.port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
        store.close()


if __name__ == '__main__':
    main()
