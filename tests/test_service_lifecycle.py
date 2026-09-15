import json
from pathlib import Path
import subprocess
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import uuid

import server
import service_manager as service


class ServiceLifecycle(unittest.TestCase):
    def setUp(self):
        self.root = server.ROOT / 'output/test-runs' / ('service-' + uuid.uuid4().hex)
        self.root.mkdir(parents=True)

    def test_single_instance_prevents_second_writer_then_releases(self):
        first = server.instance_lock(self.root)
        try:
            with self.assertRaises(ValueError): server.instance_lock(self.root)
        finally:
            first.close()
        server.instance_lock(self.root).close()

    def test_plist_has_only_allowlisted_environment(self):
        value = service.launch_agent(self.root, environment={'PATH': '/test/bin', 'API_KEY': 'SECRET', 'QUOTA_POCKET_FAKE_IP': '1'})
        self.assertNotIn('SECRET', json.dumps(value))
        self.assertTrue(value['RunAtLoad'])
        self.assertTrue(value['KeepAlive'])
        self.assertEqual(value['EnvironmentVariables']['QUOTA_POCKET_FAKE_IP'], '1')

    def test_disable_persists_launchctl_override_before_stopping(self):
        completed = subprocess.CompletedProcess([], 0, '', '')
        with patch.object(service, 'check_owned'), patch.object(service, 'run', return_value=completed) as run, patch.object(service, 'stop_current') as stop:
            result = service.disable(self.root)
        self.assertFalse(result['enabled'])
        self.assertEqual(run.call_args_list[0].args, ('disable', service.service_name()))
        self.assertIn(('bootout', service.service_name()), [call.args for call in run.call_args_list])
        stop.assert_called_once_with(self.root)

    def test_disable_failure_does_not_stop_running_collector(self):
        with patch.object(service, 'check_owned'), patch.object(service, 'run', return_value=subprocess.CompletedProcess([], 1, '', '')), patch.object(service, 'stop_current') as stop:
            with self.assertRaises(ValueError): service.disable(self.root)
        stop.assert_not_called()

    def test_log_retains_recent_bytes_without_deleting_file(self):
        log = self.root / 'collector.log'
        log.write_bytes(b'a' * 100 + b'z' * 100)
        inode = log.stat().st_ino
        service.trim_logs(self.root, 100)
        self.assertEqual(log.read_bytes(), b'z' * 50)
        self.assertEqual(log.stat().st_ino, inode)

    def test_shutdown_is_local_admin_only_and_rejects_new_collection(self):
        store = server.Store(self.root / 'state')
        http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        http.store = store
        worker = threading.Thread(target=http.serve_forever, daemon=True)
        worker.start()
        def request(role='admin', host=None, method='POST', path='/api/shutdown'):
            headers = {'Authorization': 'Bearer ' + store.keys[role]}
            if host: headers['Host'] = host
            req = urllib.request.Request('http://127.0.0.1:%s%s' % (http.server_port, path), method=method, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=3) as response: return response.status, json.load(response)
            except urllib.error.HTTPError as error: return error.code, json.load(error)
        try:
            self.assertEqual(request(role='viewer')[0], 403)
            store.config['publicUrl'] = 'https://quota.example'
            self.assertEqual(request(host='quota.example')[0], 403)
            with patch.object(server, 'build_id', return_value='changed'):
                status, value = request(method='GET', path='/api/runtime')
            self.assertEqual(status, 200)
            self.assertEqual(value['diskBuild'], 'changed')
            self.assertEqual(value['build'], server.RUNNING_BUILD)
            self.assertFalse(value['serviceSupported'])
            self.assertEqual(request()[0], 202)
            self.assertTrue(store.stop.is_set())
            self.assertFalse(store.request_refresh(force=True))
        finally:
            http.shutdown(); http.server_close(); worker.join(3)

    def test_service_status_observes_disabled_override(self):
        target = self.root / 'agent.plist'; target.write_text('test')
        def run(*args):
            return subprocess.CompletedProcess([], 0 if args[0] == 'print-disabled' else 1,
                                               '"%s" => disabled' % service.LABEL, '')
        with patch.object(service, 'check_owned'), patch.object(service, 'target_path', return_value=target), patch.object(service, 'run', side_effect=run):
            self.assertEqual(service.status()['enabled'], False)

    def test_runtime_migration_preserves_identity_and_does_not_reset_later_state(self):
        source=self.root/'source'; source.mkdir()
        for name in ('sandbox.mjs','sync_crypto.mjs','package.json','package-lock.json','server.py'):
            (source/name).write_text('{}')
        state=source/'.state'; state.mkdir()
        (state/'access.json').write_text(json.dumps({'admin':'TEST_ONLY'}))
        (state/'icloud.json').write_text(json.dumps({'deviceId':'unchanged'}))
        (state/'config.json').write_text(json.dumps({'path':str(state/'subscriptions/one')}))
        destination=self.root/'runtime'
        with patch.object(service,'runtime_root',return_value=destination):
            service.stage_runtime(source)
            migrated=json.loads((destination/'.state/config.json').read_text())
            self.assertEqual(migrated['path'],str(destination/'.state/subscriptions/one'))
            self.assertEqual(json.loads((destination/'.state/icloud.json').read_text())['deviceId'],'unchanged')
            (destination/'.state/config.json').write_text('{"updated":true}')
            service.stage_runtime(source)
            self.assertEqual(json.loads((destination/'.state/config.json').read_text()),{'updated':True})
        self.assertTrue((state/'access.json').is_file())
