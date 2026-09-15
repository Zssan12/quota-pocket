"""Collector -> real export/installed script -> Scriptable API doubles.

Only upstream responses and Apple APIs are simulated. Fixtures are retained.
"""
import json
import subprocess
import unittest
import uuid
from unittest.mock import patch

import adapters
import server
from icloud_sync import ICloudSync


class ICloudPipeline(unittest.TestCase):
    def test_success_failure_recovery_and_scope_reach_installed_widget(self):
        root = adapters.ROOT / 'output/test-runs' / ('pipeline-' + uuid.uuid4().hex)
        store = server.Store(root / 'state')
        documents = root / 'Documents'
        documents.mkdir()
        store.icloud = ICloudSync(store.directory, adapters.ROOT / 'widgets/Quota-Pocket.js', documents=documents)
        for key, config in store.config['sources'].items():
            config['enabled'] = key in ('cc-switch', 'claude')

        def relay(_):
            item = adapters.cc_result({'remaining': 18.25, 'unit': 'USD'},
                                      adapters.row('relay', 'Relay', 'private'))
            item['identity'] = {'token': 'PIPELINE_SECRET'}
            return [item]

        def collect():
            store.refresh_lock.acquire()
            store.collect(manual=True)

        def packet():
            return json.loads((documents / store.icloud.relative_snapshot_path).read_text())

        with patch.dict(server.ADAPTERS, {'cc-switch': relay}), \
                patch.dict(adapters.os.environ, {'CLAUDE_QUOTA_OAUTH_TOKEN': 'PIPELINE_SECRET'}), \
                patch.object(adapters, 'fetch_json', return_value={'five_hour': {'utilization': 25}}) as fetch:
            collect()
            store.icloud.configure(True, store.icloud_snapshot)
            good = packet()
            fetch.side_effect = adapters.SourceError('PIPELINE_SECRET expired', status_code=401)
            collect()
            failed = packet()
            by_id = {r['id']: r for r in failed['providers']}
            self.assertEqual(by_id['native:claude']['status'], 'error')
            self.assertEqual(by_id['native:claude']['lastSuccessAt'],
                             next(r for r in good['providers'] if r['id'] == 'native:claude')['lastSuccessAt'])
            self.assertEqual(by_id['relay']['status'], 'ok')
            fetch.side_effect = None
            fetch.return_value = {'five_hour': {'utilization': 60}}
            collect()
            recovered = packet()
            store.configure_icloud_accounts({'providerIds': ['relay']})
            restricted = packet()
            store.configure_icloud_accounts({'providerIds': []})
            empty = packet()

        scenarios = {'good': good, 'failed': failed, 'recovered': recovered,
                     'restricted': restricted, 'empty': empty}
        encoded = json.dumps(scenarios)
        self.assertNotIn('PIPELINE_SECRET', encoded)
        self.assertNotIn('identity', encoded)
        fixture = root / 'scenarios.json'
        fixture.write_text(encoded)
        script = documents / store.icloud.script_name
        result = subprocess.run(['node', str(adapters.ROOT / 'tests/icloud_pipeline.mjs'),
                                 str(script), str(fixture)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
