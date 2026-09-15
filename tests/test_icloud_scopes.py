import json
from pathlib import Path
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from unittest.mock import patch
import icloud_sync

import adapters
from icloud_sync import ICloudSync, quota_projection
import server


class MobileScopeTests(unittest.TestCase):
    def setUp(self):
        self.root = adapters.ROOT / 'output/test-runs' / ('mobile-scope-' + uuid.uuid4().hex)
        self.store = server.Store(self.root / 'state')
        documents = self.root / 'Documents'
        documents.mkdir()
        self.store.icloud = ICloudSync(self.root / 'state', adapters.ROOT / 'widgets/Quota-Pocket.js', documents=documents)
        self.store.rows = [adapters.row(uid, uid, 'private source') for uid in ['a', 'b', 'c']]
        self.store.configure_widget({'providerIds': ['b', 'a']})
        self.store.icloud.configure(True, self.store.icloud_snapshot)

    def exported(self):
        return json.loads((self.store.icloud.documents / self.store.icloud.relative_snapshot_path).read_text())

    def test_existing_display_preserved_with_all_candidates_and_independent_https(self):
        packet = self.exported()
        self.assertEqual(packet['mobileSelectionVersion'], 1)
        self.assertEqual(packet['defaultProviderIds'], ['b', 'a'])
        self.assertEqual([r['id'] for r in packet['providers']], ['b', 'a'])
        self.assertEqual([r['id'] for r in packet['availableProviders']], ['a', 'b', 'c'])
        self.store.configure_icloud_accounts({'providerIds': ['c', 'b']})
        packet = self.exported()
        self.assertEqual([r['id'] for r in packet['availableProviders']], ['b', 'c'])
        self.assertEqual(packet['defaultProviderIds'], ['b'])
        self.assertEqual([r['id'] for r in packet['providers']], ['b'])
        self.assertEqual([r['id'] for r in self.store.snapshot(widget_only=True)['providers']], ['b', 'a'])

    def test_empty_scope_and_selection_are_intentional_and_persist(self):
        self.store.configure_icloud_accounts({'providerIds': []})
        packet = self.exported()
        for field in ('providers', 'availableProviders', 'defaultProviderIds'):
            self.assertEqual(packet[field], [])
        with patch.object(icloud_sync, 'SCRIPTABLE_DOCUMENTS', self.store.icloud.documents):
            self.assertEqual(server.Store(self.root / 'state').icloud_accounts()['providerIds'], [])
        self.store.configure_icloud_accounts({'providerIds': None})
        self.store.configure_widget({'providerIds': []})
        self.assertEqual(self.exported()['defaultProviderIds'], [])
        self.assertEqual(len(self.exported()['availableProviders']), 3)

    def test_candidates_are_sanitized_and_unknown_ids_rejected(self):
        self.store.rows[0]['name'] = {'token': 'NESTED_SECRET'}
        self.store.rows[1]['error'] = 'ERROR_SECRET'
        self.store.export_icloud()
        encoded = json.dumps(self.exported())
        self.assertNotIn('NESTED_SECRET', encoded)
        self.assertNotIn('ERROR_SECRET', encoded)
        for ids in (['missing'], ['a', 'a'], [True], 'all'):
            with self.assertRaises(ValueError): self.store.configure_icloud_accounts({'providerIds': ids})

    def test_projection_cannot_leak_legacy_rows_outside_scope(self):
        raw = self.store.icloud_snapshot()
        raw['availableProviders'] = [raw['availableProviders'][1]]
        packet = quota_projection(raw)
        self.assertEqual([r['id'] for r in packet['providers']], ['b'])
        self.assertEqual(packet['defaultProviderIds'], ['b'])

    def test_scope_endpoint_requires_admin_and_local_mutation(self):
        http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        http.store = self.store
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        def request(role, body=None, host=None):
            headers = {'Authorization': 'Bearer ' + self.store.keys[role], 'Content-Type': 'application/json'}
            if host: headers['Host'] = host
            req = urllib.request.Request('http://127.0.0.1:%d/api/icloud-accounts' % http.server_port,
                                         headers=headers, data=json.dumps(body).encode() if body is not None else None)
            try:
                with urllib.request.urlopen(req) as response: return response.status
            except urllib.error.HTTPError as error: return error.code
        try:
            self.assertEqual(request('viewer'), 403)
            self.assertEqual(request('viewer', {'providerIds': []}), 403)
            self.assertEqual(request('admin', {'providerIds': ['b']}), 200)
            self.store.config['publicUrl'] = 'https://quota.example'
            self.assertEqual(request('admin', {'providerIds': []}, 'quota.example'), 403)
            self.assertEqual(self.store.icloud_accounts()['providerIds'], ['b'])
        finally:
            http.shutdown(); http.server_close(); thread.join()
