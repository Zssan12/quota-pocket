import copy
import datetime as dt
import json
from pathlib import Path
import secrets
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import uuid

from hosted_server import HostedHTTPServer, HostedStore, RequestLimits
from hosted_sync import HostedSync, SyncError
from relay_server import RelayError, digest
from widgeto import widgeto_config, widgeto_data


def directory():
    path = Path(__file__).resolve().parents[1] / 'output/test-runs' / ('hosted-' + uuid.uuid4().hex)
    path.mkdir(parents=True)
    return path


def sample():
    captured = dt.datetime.now(dt.timezone.utc).isoformat()
    return {'schemaVersion': 1, 'generatedAt': captured, 'lastCollectionAt': captured,
            'intervalSeconds': 300, 'staleAfterSeconds': 630,
            'sources': [{'token': 'SOURCE_SECRET'}], 'admin': 'ADMIN_SECRET',
            'providers': [{'id': 'a', 'name': 'Example account', 'status': 'ok',
                           'lastSuccessAt': captured, 'lastAttemptAt': captured,
                           'error': 'PROVIDER_SECRET', 'identity': {'email': 'EMAIL_SECRET'},
                           'windows': [{'label': '每周', 'remainingPercent': 0, 'token': 'WINDOW_SECRET'},
                                       {'label': '5 小时', 'remainingPercent': None}],
                           'balances': [{'label': '余额', 'value': None, 'unit': 'USD'}]}]}


class HostedStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = HostedStore(directory(), 'https://sync.example.com', max_devices=2)
        self.writer = secrets.token_urlsafe(32)
        self.room = self.store.enroll({'writerToken': self.writer})['room']
        self.store.publish(self.room, self.writer, {'seq': 1, 'snapshot': sample()})

    def tearDown(self):
        self.store.close()

    def phone(self):
        code = self.store.pair(self.room, self.writer)['code']
        token = secrets.token_urlsafe(32)
        body = {'room': self.room, 'code': code, 'readerToken': token}
        result = self.store.exchange(body)
        return token, body, result

    def test_only_display_fields_leave_collector_and_enter_storage(self):
        token, _, _ = self.phone()
        value = self.store.snapshot(self.room, token)
        stored = self.store.db.execute('SELECT * FROM rooms').fetchone()
        encoded = json.dumps(value) + str(tuple(stored))
        for secret in ('SOURCE_SECRET', 'ADMIN_SECRET', 'PROVIDER_SECRET', 'EMAIL_SECRET', 'WINDOW_SECRET', self.writer, token):
            self.assertNotIn(secret, encoded)
        self.assertEqual(value['providers'][0]['windows'][0]['remainingPercent'], 0)

    def test_reader_cannot_write_pair_or_cross_device(self):
        token, _, _ = self.phone()
        other_writer = secrets.token_urlsafe(32)
        other_room = self.store.enroll({'writerToken': other_writer})['room']
        for operation in (
            lambda: self.store.publish(self.room, token, {'seq': 2, 'snapshot': sample()}),
            lambda: self.store.pair(self.room, token),
            lambda: self.store.snapshot(other_room, token),
            lambda: self.store.snapshot(self.room, self.writer),
        ):
            with self.assertRaises(RelayError) as error:
                operation()
            self.assertEqual(error.exception.status, 403)

    def test_pair_is_one_use_but_same_reader_can_retry_lost_response(self):
        token, body, result = self.phone()
        self.assertEqual(self.store.exchange(body), result)
        with self.assertRaises(RelayError) as error:
            self.store.exchange(dict(body, readerToken=secrets.token_urlsafe(32)))
        self.assertEqual(error.exception.status, 410)
        self.store.revoke(self.room, self.writer, result['readerId'])
        with self.assertRaises(RelayError):
            self.store.snapshot(self.room, token)

    def test_expired_pair_rejected_and_disconnect_invalidates_pending_pairs(self):
        code = self.store.pair(self.room, self.writer)['code']
        self.store.db.execute('UPDATE pairs SET expires=0 WHERE hash=?', (digest(code),))
        with self.assertRaises(RelayError):
            self.store.exchange({'room': self.room, 'code': code, 'readerToken': secrets.token_urlsafe(32)})
        token, _, _ = self.phone()
        pending = self.store.pair(self.room, self.writer)['code']
        self.store.disconnect(self.room, self.writer)
        self.assertIsNone(self.store.db.execute('SELECT envelope FROM rooms').fetchone()[0])
        with self.assertRaises(RelayError):
            self.store.snapshot(self.room, token)
        with self.assertRaises(RelayError):
            self.store.exchange({'room': self.room, 'code': pending, 'readerToken': secrets.token_urlsafe(32)})

    def test_registration_idempotent_and_capped(self):
        self.assertEqual(self.store.enroll({'writerToken': self.writer})['room'], self.room)
        self.store.enroll({'writerToken': secrets.token_urlsafe(32)})
        with self.assertRaises(RelayError) as error:
            self.store.enroll({'writerToken': secrets.token_urlsafe(32)})
        self.assertEqual(error.exception.status, 503)

    def test_versions_rate_limit_and_same_payload_retry(self):
        token, _, _ = self.phone()
        original = self.store.snapshot(self.room, token)
        self.assertEqual(self.store.publish(self.room, self.writer, {'seq': 1, 'snapshot': original}), {'seq': 1})
        for seq, expected in ((3, 409), (2, 429), (True, 400)):
            with self.assertRaises(RelayError) as error:
                self.store.publish(self.room, self.writer, {'seq': seq, 'snapshot': sample()})
            self.assertEqual(error.exception.status, expected)

    def test_stale_snapshot_expires_and_reading_never_rejuvenates_it(self):
        token, _, _ = self.phone()
        captured = self.store.snapshot(self.room, token)['providers'][0]['lastSuccessAt']
        old = dt.datetime.fromisoformat(captured).timestamp()
        table = widgeto_data(self.store.snapshot(self.room, token), current_time=old + 7200)
        self.assertTrue(table['items'][0]['stale'])
        self.assertEqual(table['items'][0]['lastSuccessAt'], captured)
        self.store.db.execute('UPDATE rooms SET uploaded=0')
        with self.assertRaises(RelayError) as error:
            self.store.snapshot(self.room, token)
        self.assertEqual(error.exception.status, 410)


class HostedHTTPTests(unittest.TestCase):
    def setUp(self):
        self.root = directory()
        self.store = HostedStore(self.root / 'remote', 'https://sync.example.com')
        self.server = HostedHTTPServer(('127.0.0.1', 0), self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.store.close()

    def request(self, method, path, token=None, body=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.origin + path, data=data, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=3) as response:
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            return json.load(response)

    def test_desktop_upload_pair_widgeto_and_revoke_end_to_end(self):
        local = self.root / 'desktop'; local.mkdir()
        publisher = HostedSync(local, sample, url='https://sync.example.com', transport=self.request)
        publisher.configure(True)
        publisher.sync_once()
        self.assertTrue(publisher.status()['ready'])
        from urllib.parse import parse_qs, urlsplit
        link = publisher.pair()['url']; fragment = parse_qs(urlsplit(link).fragment)
        self.assertNotIn(publisher.state['writerToken'], link)
        reader = secrets.token_urlsafe(32)
        result = self.request('POST', '/v2/pair/exchange', body={
            'room': fragment['room'][0], 'code': fragment['pair'][0], 'readerToken': reader})
        self.assertEqual(result['protocol'], 'quota-pocket-hosted-v2')
        base = '/v2/rooms/' + result['room']
        table = self.request('GET', base + '/widgeto', reader)
        self.assertIn('0%', table['items'][0]['quota'])
        self.assertIn('未知', table['items'][0]['quota'])
        config = self.request('GET', base + '/config', reader)
        self.assertEqual(config['api']['headers'][0]['value'], 'Bearer ' + reader)
        self.assertNotIn(reader, config['api']['url'])
        self.assertNotIn(publisher.state['writerToken'], json.dumps(config))
        publisher.configure(False); publisher.sync_once()
        self.assertFalse(publisher.status()['disconnectPending'])
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('GET', base + '/widgeto', reader)
        self.assertEqual(error.exception.code, 403)

    def test_no_anonymous_access_query_tokens_or_remote_admin(self):
        writer = secrets.token_urlsafe(32)
        room = self.request('POST', '/v2/enroll', body={'writerToken': writer})['room']
        for path, expected in [('/v2/rooms/' + room + '/snapshot', 403), ('/api/settings', 404),
                               ('/health?token=not-allowed', 400)]:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request('GET', path)
            self.assertEqual(error.exception.code, expected)


class PublisherTests(unittest.TestCase):
    def test_stays_disabled_without_registration_or_upload(self):
        calls = []
        sync = HostedSync(directory(), sample, url='https://sync.example.com', transport=lambda *a, **k: calls.append((a, k)))
        sync.sync_once()
        self.assertEqual(calls, [])
        self.assertFalse(sync.path.exists())

    def test_failure_keeps_local_data_and_pending_revoke_can_retry(self):
        sync = HostedSync(directory(), sample, url='https://sync.example.com', transport=lambda *a, **k: (_ for _ in ()).throw(SyncError('offline')))
        sync.configure(True)
        with self.assertRaises(SyncError): sync.sync_once()
        original_token = sync.state['writerToken']
        self.assertNotIn(original_token, json.dumps(sync.status()))
        self.assertIsNone(sync.status()['lastUploadedAt'])
        sync.state['room'] = 'a' * 32
        sync.configure(False)
        with self.assertRaises(SyncError): sync.sync_once()
        self.assertFalse(sync.status()['enabled'])
        self.assertTrue(sync.status()['disconnectPending'])
        with self.assertRaises(SyncError): sync.configure(True)
        sync.transport = lambda *a, **k: {'ok': True}
        sync.sync_once()
        self.assertFalse(sync.status()['disconnectPending'])

    def test_cannot_redirect_existing_device_credentials_to_new_service(self):
        root = directory()
        sync = HostedSync(root, sample, url='https://first.example.com')
        sync.configure(True)
        with self.assertRaises(SyncError):
            HostedSync(root, sample, url='https://other.example.com')

    def test_generated_at_and_null_are_not_misrepresented(self):
        value = sample(); value['providers'][0]['lastSuccessAt'] = None
        item = widgeto_data(value)['items'][0]
        self.assertTrue(item['stale'])
        self.assertIn('尚无有效采集时间', item['freshness'])
        template = widgeto_config('https://example.com/widgeto', 'reader-only')
        self.assertEqual(template['render']['table']['source'], "${api['items']}")
        self.assertNotIn('reader-only', template['api']['url'])

    def test_limiter_expires_without_unbounded_history(self):
        limiter = RequestLimits()
        with patch('hosted_server.time.monotonic', return_value=0):
            self.assertTrue(limiter.allow('a', 1, 60))
            self.assertFalse(limiter.allow('a', 1, 60))
        with patch('hosted_server.time.monotonic', return_value=61):
            self.assertTrue(limiter.allow('a', 1, 60))
