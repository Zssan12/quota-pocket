import copy
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import uuid

import adapters
import icloud_sync
from icloud_sync import ICloudError, ICloudSync, quota_projection
import server


def fixture(name):
    path = adapters.ROOT / 'output/test-runs' / ('icloud-' + name + '-' + uuid.uuid4().hex)
    path.mkdir(parents=True)
    return path


def template(path):
    path.write_text('// Variables used by Scriptable.\n// icon-color: deep-green; icon-glyph: chart-pie;\nconst original = true;\n')
    return path


def snapshot(ids=('a', 'b')):
    providers = []
    for uid in ids:
        providers.append({
            'id': uid, 'name': 'Account ' + uid, 'app': 'codex', 'plan': 'Plus',
            'active': uid == 'a', 'source': 'private adapter description',
            'windows': [{'id': 'weekly', 'label': '每周额度', 'remainingPercent': 72,
                         'resetAt': '2026-09-20T00:00:00Z', 'secret': 'WINDOW_SECRET'}],
            'balances': [{'label': '余额', 'value': 18.2, 'unit': 'USD', 'raw': 'BALANCE_SECRET'}],
            'lastSuccessAt': '2026-09-13T01:02:03Z', 'lastAttemptAt': '2026-09-13T01:02:04Z',
            'status': 'stale', 'error': 'Bearer PROVIDER_SECRET', '_sourceId': 'cc-switch',
            'identity': {'email': 'private@example.com'},
        })
    return {'schemaVersion': 1, 'demo': False, 'generatedAt': '2026-09-13T01:02:05Z',
            'lastCollectionAt': '2026-09-13T01:02:03Z', 'intervalSeconds': 600,
            'staleAfterSeconds': 1230, 'sources': [{'path': '/private', 'error': 'SOURCE_SECRET'}],
            'ccSwitchMode': 'independent', 'providers': providers}


class ProjectionTests(unittest.TestCase):
    def test_explicit_projection_keeps_quota_and_original_times_only(self):
        value = quota_projection(snapshot(('a',)))
        provider = value['providers'][0]
        self.assertEqual(provider['lastSuccessAt'], '2026-09-13T01:02:03Z')
        self.assertEqual(provider['windows'][0]['remainingPercent'], 72)
        self.assertEqual(provider['balances'][0]['value'], 18.2)
        encoded = json.dumps(value)
        for forbidden in ('PROVIDER_SECRET', 'WINDOW_SECRET', 'BALANCE_SECRET', 'SOURCE_SECRET',
                          'private@example.com', '_sourceId', 'ccSwitchMode', 'sources', 'identity', 'error'):
            self.assertNotIn(forbidden, encoded)

    def test_nested_secrets_invalid_containers_and_nonfinite_numbers_are_rejected(self):
        malicious = {
            'generatedAt': {'secret': 'TOP_OBJECT_SECRET'},
            'lastCollectionAt': 'not-a-time',
            'intervalSeconds': {'secret': 'INTERVAL_OBJECT_SECRET'},
            'staleAfterSeconds': float('inf'),
            'providers': [{
                'id': 'safe-id', 'name': 'Safe name', 'app': {'secret': 'APP_OBJECT_SECRET'},
                'plan': ['PLAN_OBJECT_SECRET'], 'active': {'secret': 'ACTIVE_OBJECT_SECRET'},
                'status': {'secret': 'STATUS_OBJECT_SECRET'},
                'lastSuccessAt': {'secret': 'TIME_OBJECT_SECRET'},
                'lastAttemptAt': '2026-09-13T01:02:04',
                'windows': [
                    {'id': {'secret': 'WINDOW_ID_SECRET'}, 'label': '额度',
                     'remainingPercent': {'secret': 'PERCENT_OBJECT_SECRET'},
                     'resetAt': ['RESET_OBJECT_SECRET']},
                    {'label': '非有限值', 'remainingPercent': float('nan')},
                    {'label': {'secret': 'LABEL_OBJECT_SECRET'}, 'remainingPercent': 50},
                ],
                'balances': [
                    {'label': '余额', 'value': {'secret': 'VALUE_OBJECT_SECRET'}, 'unit': 'USD'},
                    {'label': '非有限余额', 'value': float('-inf'), 'unit': 'USD'},
                    {'label': '单位', 'value': 1, 'unit': {'secret': 'UNIT_OBJECT_SECRET'}},
                ],
            }],
        }
        result = quota_projection(malicious)
        encoded = json.dumps(result, allow_nan=False)
        self.assertEqual(result['providers'][0]['windows'], [
            {'label': '额度'}, {'label': '非有限值'}
        ])
        self.assertEqual(result['providers'][0]['balances'], [])
        for secret in ('OBJECT_SECRET', 'Infinity', 'NaN', 'not-a-time'):
            self.assertNotIn(secret, encoded)
        for key in ('generatedAt', 'lastCollectionAt', 'intervalSeconds', 'staleAfterSeconds'):
            self.assertNotIn(key, result)

    def test_non_list_collections_fail_closed(self):
        self.assertEqual(quota_projection({'providers': {'secret': 'PROVIDER_SECRET'}})['providers'], [])
        value = quota_projection({'providers': [{'id': 'a', 'name': 'A',
                                  'windows': {'secret': 'WINDOW_SECRET'},
                                  'balances': 'BALANCE_SECRET'}]})
        self.assertEqual(value['providers'][0]['windows'], [])
        self.assertEqual(value['providers'][0]['balances'], [])
        self.assertNotIn('SECRET', json.dumps(value))


class TransportTests(unittest.TestCase):
    def make_sync(self, root, documents=None):
        root.mkdir(parents=True, exist_ok=True)
        documents = documents or root / 'Documents'
        documents.mkdir(parents=True, exist_ok=True)
        return ICloudSync(root / 'state', template(root / 'widget.js'), documents=documents,
                          device_name='Test Mac')

    def test_explicit_destination_survives_store_reload_without_real_icloud(self):
        root = fixture('reload-isolation')
        sync = self.make_sync(root)
        sync.configure(True, lambda: snapshot())
        decoy = root / 'real-cloud-must-stay-empty'
        decoy.mkdir()
        with patch.object(icloud_sync, 'SCRIPTABLE_DOCUMENTS', decoy):
            store = server.Store(root / 'state')
            self.assertEqual(store.icloud.documents, sync.documents.resolve())
            self.assertEqual(list(decoy.iterdir()), [])
            self.assertTrue(store.export_icloud())
            self.assertEqual(list(decoy.iterdir()), [])

    def test_disabled_default_does_not_touch_documents_and_id_persists(self):
        root = fixture('disabled'); documents = root / 'Documents'; documents.mkdir()
        sync = ICloudSync(root / 'state', template(root / 'widget.js'), documents=documents)
        self.assertFalse(sync.status()['enabled'])
        self.assertEqual(list(documents.iterdir()), [])
        self.assertFalse(sync.export(lambda: snapshot()))
        again = ICloudSync(root / 'state', root / 'widget.js', documents=documents)
        self.assertEqual(again.status()['installationId'], sync.status()['installationId'])

    def test_enable_installs_owned_script_and_selected_snapshot(self):
        root = fixture('enable'); sync = self.make_sync(root)
        selected = snapshot(('b',))
        status = sync.configure(True, lambda: selected)
        self.assertTrue(status['enabled']); self.assertIsNotNone(status['lastExportAt'])
        script = (sync.documents / sync.script_name).read_text()
        self.assertTrue(script.startswith('// Variables used by Scriptable.\n// icon-color:'))
        self.assertIn('const ICLOUD_SOURCE = {installationId:', script)
        self.assertIn(sync.relative_snapshot_path, script)
        packet = json.loads((sync.documents / sync.relative_snapshot_path).read_text())
        self.assertEqual([item['id'] for item in packet['providers']], ['b'])
        sync.configure(False, lambda: snapshot())
        self.assertTrue((sync.documents / sync.relative_snapshot_path).is_file())

    def test_unchanged_managed_script_is_not_rewritten(self):
        root = fixture('unchanged'); sync = self.make_sync(root)
        sync.configure(True, lambda: snapshot(('a',)))
        script_target = sync.documents / sync.script_name
        with patch.object(icloud_sync, '_atomic_text', wraps=icloud_sync._atomic_text) as write:
            sync.export(lambda: snapshot(('b',)))
        written = [call.args[0] for call in write.call_args_list]
        self.assertNotIn(script_target, written)
        self.assertIn(sync.documents / sync.relative_snapshot_path, written)

    def test_installations_use_separate_paths(self):
        root = fixture('multi'); documents = root / 'Documents'; documents.mkdir()
        first = self.make_sync(root / 'one', documents); second = self.make_sync(root / 'two', documents)
        first.configure(True, lambda: snapshot(('a',))); second.configure(True, lambda: snapshot(('b',)))
        self.assertNotEqual(first.relative_snapshot_path, second.relative_snapshot_path)
        self.assertTrue((documents / first.relative_snapshot_path).is_file())
        self.assertTrue((documents / second.relative_snapshot_path).is_file())

    def test_short_name_collision_refuses_to_overwrite_other_installation(self):
        root = fixture('short-collision'); documents = root / 'Documents'; documents.mkdir()
        first = self.make_sync(root / 'one', documents); second = self.make_sync(root / 'two', documents)
        second.state['deviceId'] = first.state['deviceId'][:8] + '-0000-4000-8000-000000000000'
        first.configure(True, lambda: snapshot(('a',)))
        original = (documents / first.script_name).read_text()
        with self.assertRaises(ICloudError):
            second.configure(True, lambda: snapshot(('b',)))
        self.assertEqual((documents / first.script_name).read_text(), original)

    def test_collision_and_write_errors_do_not_overwrite_or_break_exporter(self):
        root = fixture('collision'); sync = self.make_sync(root)
        target = sync.documents / sync.script_name; target.write_text('const userScript = true;')
        with self.assertRaises(ICloudError): sync.configure(True, lambda: snapshot())
        self.assertEqual(target.read_text(), 'const userScript = true;')
        self.assertFalse(sync.status()['enabled'])
        sync.state['enabled'] = True
        sync.documents = root / 'missing-documents'
        self.assertFalse(sync.export(lambda: snapshot()))
        self.assertIn('不可用', sync.status()['error'])

    def test_store_exports_current_widget_selection(self):
        root = fixture('selection'); store = server.Store(root / 'state')
        store.icloud = self.make_sync(root / 'icloud')
        store.rows = [adapters.row(uid, uid, 'CC Switch') for uid in ('a', 'b')]
        store.icloud.configure(True, lambda: store.snapshot(widget_only=True))
        store.configure_widget({'providerIds': []})
        packet = json.loads((store.icloud.documents / store.icloud.relative_snapshot_path).read_text())
        self.assertEqual(packet['providers'], [])
        store.configure_widget({'providerIds': ['b']})
        packet = json.loads((store.icloud.documents / store.icloud.relative_snapshot_path).read_text())
        self.assertEqual([item['id'] for item in packet['providers']], ['b'])

    def test_queued_export_captures_selection_only_after_sync_lock(self):
        root = fixture('ordering'); store = server.Store(root / 'state')
        store.icloud = self.make_sync(root / 'icloud')
        store.rows = [adapters.row(uid, uid, 'CC Switch') for uid in ('a', 'b')]
        store.config['widgetProviderIds'] = ['a']
        store.icloud.configure(True, lambda: store.snapshot(widget_only=True))
        original_snapshot = store.snapshot
        called = threading.Event(); started = threading.Event()

        def observed_snapshot(*args, **kwargs):
            called.set()
            return original_snapshot(*args, **kwargs)

        store.snapshot = observed_snapshot
        store.icloud.lock.acquire()
        worker = threading.Thread(target=lambda: (started.set(), store.export_icloud()))
        try:
            worker.start(); self.assertTrue(started.wait(1))
            self.assertFalse(called.wait(0.1))
            with store.lock:
                store.config['widgetProviderIds'] = ['b']
        finally:
            store.icloud.lock.release()
        worker.join(2); self.assertFalse(worker.is_alive()); self.assertTrue(called.is_set())
        packet = json.loads((store.icloud.documents / store.icloud.relative_snapshot_path).read_text())
        self.assertEqual([item['id'] for item in packet['providers']], ['b'])


class ICloudHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = fixture('http'); cls.store = server.Store(cls.root / 'state')
        cls.store.icloud = ICloudSync(cls.root / 'state', template(cls.root / 'widget.js'),
                                     documents=cls.root / 'missing')
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.http.store = cls.store
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True); cls.thread.start()
        cls.base = 'http://127.0.0.1:%d' % cls.http.server_port

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown(); cls.http.server_close(); cls.thread.join()

    def request(self, method='GET', role='admin', body=None, host=None):
        headers = {'Authorization': 'Bearer ' + self.store.keys[role]}
        if host: headers['Host'] = host
        data = json.dumps(body).encode() if body is not None else None
        if data: headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(self.base + '/api/icloud', headers=headers, data=data, method=method)
        try:
            with urllib.request.urlopen(request) as response: return response.status, json.load(response)
        except urllib.error.HTTPError as error: return error.code, json.load(error)

    def test_admin_status_and_local_only_mutation(self):
        self.assertEqual(self.request(role='viewer')[0], 403)
        status, body = self.request()
        self.assertEqual(status, 200)
        required = ('available', 'enabled', 'installationId', 'scriptName', 'lastExportAt', 'error', 'directory')
        self.assertEqual(set(required) - set(body), set())
        self.store.config['publicUrl'] = 'https://quota.example'
        self.assertEqual(self.request('POST', body={'enabled': False}, host='quota.example')[0], 403)
        self.assertEqual(self.request('POST', body={'enabled': 'yes'})[0], 400)


if __name__ == '__main__':
    unittest.main()
