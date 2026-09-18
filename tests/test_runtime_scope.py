"""The supported installation is iCloud-only, including upgrades from old config."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import adapters
import install
import server
from test_quota import workspace


class RuntimeScope(unittest.TestCase):
    def test_retired_hosted_configuration_cannot_break_icloud_startup(self):
        root = workspace()
        old = root / 'hosted-sync.json'
        old.write_text(json.dumps({'url': 'https://old.example', 'enabled': True}))
        before = old.read_bytes()
        with patch.dict(os.environ, {'QUOTA_POCKET_SYNC_URL': 'retired-invalid-url'}):
            store = server.Store(root)
            self.assertIn('icloud', store.runtime_status())
            self.assertNotIn('hosted', store.runtime_status())
        self.assertEqual(old.read_bytes(), before)

    def test_retired_hosted_endpoints_are_unavailable(self):
        store = server.Store(workspace())
        http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        http.store = store
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            for method, route in [('GET', '/api/hosted'), ('POST', '/api/hosted'), ('POST', '/api/hosted/pair')]:
                request = urllib.request.Request('http://127.0.0.1:%s%s' % (http.server_port, route),
                    data=b'{"enabled":false}' if method == 'POST' else None,
                    headers={'Authorization': 'Bearer ' + store.keys['admin'], 'Content-Type': 'application/json'}, method=method)
                with self.assertRaises(urllib.error.HTTPError) as error:
                    opener.open(request, timeout=3)
                self.assertEqual(error.exception.code, 404)
        finally:
            http.shutdown(); http.server_close(); thread.join()

    def test_fresh_runtime_starts_without_archived_assets(self):
        root = workspace() / 'installed'
        root.mkdir()
        with patch('install.shutil.which', return_value='/mock/npm'), patch('install.subprocess.run'):
            install.prepare_runtime(adapters.ROOT, root)
        for name in ('archive', 'docs', 'hosted_sync.py', 'relay_server.py', 'widgeto.py', 'sync_crypto.mjs', 'vendor', 'web/hosted.html'):
            self.assertFalse((root / name).exists(), name)
        self.assertTrue((root / 'web/vendor/qrcode.js').is_file())
        env = dict(os.environ)
        env.pop('PYTHONPATH', None)
        result = subprocess.run([sys.executable, str(root / 'server.py'), '--help'], cwd=root.parent,
                                env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
