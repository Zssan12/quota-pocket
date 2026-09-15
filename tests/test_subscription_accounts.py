import copy
import json
import threading
import time
import unittest
from unittest.mock import patch

import adapters
import server
import subscription_auth
from test_quota import workspace
import test_quota as fixtures


class MultipleAccounts(unittest.TestCase):
    def setUp(self):
        self.root = workspace()
        self.store = server.Store(self.root / 'state')
        self.refresh_patch = patch.object(self.store, 'request_refresh')
        self.refresh_patch.start()
        self.addCleanup(self.refresh_patch.stop)
        self.addCleanup(self.store.subscriptions.close)

    def account(self, kind, suffix='', name=None):
        identifier = kind + (':' + suffix * 24 if suffix else '')
        directory = self.root / identifier.replace(':', '-')
        directory.mkdir(exist_ok=True)
        if kind == 'codex':
            (directory / 'auth.json').write_text('{"tokens":{"access_token":"TEST_ONLY"}}')
            config = {'home': str(directory)}
        else:
            path = directory / 'credentials.json'
            path.write_text(json.dumps({'claudeAiOauth': {'accessToken': identifier, 'scopes': ['user:profile']}}))
            config = {'path': str(path)}
        self.store.connect_subscription(kind, dict(config, accountId=identifier, name=name or identifier, enabled=True, managed=True))
        return identifier

    def collect(self, query, manual=False):
        with patch.dict(server.ADAPTERS, {'codex': query, 'claude': query}):
            self.store.refresh_lock.acquire()
            self.store.collect(manual=manual)

    @staticmethod
    def query(config):
        row = adapters.row(config['providerId'], config['name'], 'test', server.subscription_kind(config['providerId'][7:]))
        row['windows'] = [adapters.window('5h', remaining=70, reset='2030-01-01T00:00:00Z')]
        return [adapters.finish(row)]

    def test_four_accounts_keep_unique_rows_and_project_without_credentials(self):
        ids = [self.account('codex', name='Personal'), self.account('codex', 'a', 'Work'),
               self.account('claude', name='Claude Personal'), self.account('claude', 'b', 'Claude Work')]
        self.collect(self.query)
        self.assertEqual({r['id'] for r in self.store.rows}, {'native:' + key for key in ids})
        self.assertEqual(len(self.store.subscription_status()['codex']['accounts']), 2)
        packet = self.store.mobile_snapshot()
        self.assertEqual(len(packet['availableProviders']), 4)
        public = json.dumps(packet) + json.dumps(self.store.subscription_status())
        self.assertNotIn(str(self.root), public)
        self.assertNotIn('TEST_ONLY', public)
        self.assertNotIn('accessToken', public)

    def test_old_state_load_keeps_credentials_ids_and_phone_selection(self):
        key = self.account('codex')
        self.collect(self.query)
        self.store.config['sources'][key].pop('name', None)
        self.store.config['widgetProviderIds'] = ['native:codex']
        self.store.config['icloudProviderIds'] = ['native:codex']
        server.write_private(self.store.directory / 'config.json', self.store.config)
        before = (self.root / 'codex/auth.json').read_bytes()
        reloaded = server.Store(self.store.directory)
        account = reloaded.subscription_status()['codex']['accounts'][0]
        self.assertEqual(account['id'], key)
        self.assertEqual(account['providerId'], 'native:codex')
        self.assertTrue(account['connected'])
        self.assertEqual(reloaded.widget_settings()['providerIds'], ['native:codex'])
        self.assertEqual(reloaded.icloud_accounts()['providerIds'], ['native:codex'])
        self.assertEqual(before, (self.root / 'codex/auth.json').read_bytes())
        self.assertEqual(reloaded.rows[0]['id'], 'native:codex')

    def test_failure_and_backoff_are_per_account(self):
        first = self.account('codex')
        second = self.account('codex', 'a')
        self.collect(self.query)
        original = next(r['lastSuccessAt'] for r in self.store.rows if r['_sourceId'] == first)
        def failing(config):
            if config['providerId'] == 'native:' + first: raise adapters.SourceError('test failure')
            return self.query(config)
        self.collect(failing, manual=True)
        rows = {r['_sourceId']: r for r in self.store.rows}
        self.assertEqual(rows[first]['status'], 'error')
        self.assertEqual(rows[first]['lastSuccessAt'], original)
        self.assertEqual(rows[second]['status'], 'ok')
        self.assertEqual(set(self.store.source_retries), {first})
        called = []
        def subsequent(config):
            called.append(config['providerId'])
            return self.query(config)
        self.collect(subsequent)
        self.assertEqual(called, ['native:' + second])
        self.assertEqual(len(self.store.rows), 2)

    def test_rename_disable_enable_keeps_credentials_and_other_accounts(self):
        first = self.account('codex')
        second = self.account('codex', 'a')
        self.collect(self.query)
        self.store.config['widgetProviderIds'] = ['native:' + first, 'native:' + second]
        credentials = (self.root / 'codex/auth.json').read_bytes()
        self.store.update_subscription('codex', {'accountId': first, 'name': 'Personal renamed'})
        self.assertEqual(next(r['name'] for r in self.store.rows if r['_sourceId'] == first), 'Personal renamed')
        self.store.update_subscription('codex', {'accountId': first, 'enabled': False})
        self.assertEqual([r['_sourceId'] for r in self.store.rows], [second])
        self.assertEqual([r['id'] for r in self.store.icloud_snapshot()['availableProviders']], ['native:' + second])
        self.assertEqual(self.store.widget_settings()['providerIds'], ['native:' + first, 'native:' + second])
        self.store.update_subscription('codex', {'accountId': first, 'enabled': True})
        self.collect(self.query)
        self.assertEqual(len(self.store.rows), 2)
        self.assertEqual(credentials, (self.root / 'codex/auth.json').read_bytes())

    def test_reauthorization_affects_only_target_and_preserves_disabled_state(self):
        first = self.account('claude')
        second = self.account('claude', 'a')
        self.collect(self.query)
        other = copy.deepcopy(next(r for r in self.store.rows if r['_sourceId'] == first))
        self.store.update_subscription('claude', {'accountId': second, 'enabled': False})
        self.store.connect_subscription('claude', {'accountId': second, 'name': 'new login', 'path': '/test-only/new-credentials'})
        self.assertEqual(self.store.rows, [other])
        self.assertFalse(self.store.config['sources'][second]['enabled'])
        self.assertEqual(self.store.config['sources'][first]['path'], str(self.root / 'claude/credentials.json'))

    def test_unrelated_settings_do_not_toggle_account_list(self):
        first = self.account('codex')
        second = self.account('codex', 'a')
        self.store.update_subscription('codex', {'accountId': first, 'enabled': False})
        self.store.configure({'sources': {'codex': True, 'claude': False, 'codexbar': True}})
        self.assertFalse(self.store.config['sources'][first]['enabled'])
        self.assertTrue(self.store.config['sources'][second]['enabled'])
        self.assertEqual(set(self.store.settings()['sources']), set(server.ADAPTERS))
        self.assertTrue(self.store.settings()['sources']['codex']['enabled'])

    def test_reconfiguration_discards_inflight_old_account_results(self):
        key = self.account('codex')
        started, release = threading.Event(), threading.Event()
        def delayed(config):
            started.set()
            self.assertTrue(release.wait(5))
            return self.query(config)
        with patch.dict(server.ADAPTERS, {'codex': delayed}):
            self.store.refresh_lock.acquire()
            thread = threading.Thread(target=self.store.collect)
            thread.start()
            self.assertTrue(started.wait(5))
            self.store.update_subscription('codex', {'accountId': key, 'enabled': False})
            release.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.store.rows, [])

    def test_target_validation_and_busy_login_protection(self):
        key = self.account('codex')
        for data in ({'accountId': 'claude', 'name': 'Wrong type'}, {'accountId': key, 'home': '/tmp'},
                     {'accountId': key, 'enabled': 'false'}, {'accountId': key, 'name': 'x\ny'},
                     {'accountId': 'codex:../../bad', 'enabled': True}):
            with self.assertRaises(subscription_auth.LoginError): self.store.update_subscription('codex', data)
        self.store.subscriptions.jobs['codex'] = {'accountId': key, 'state': 'waiting'}
        with self.assertRaises(subscription_auth.LoginError):
            self.store.update_subscription('codex', {'accountId': key, 'enabled': False})
        self.store.subscriptions.jobs.clear()

    def test_second_login_appends_and_uses_distinct_credential_directory(self):
        first = self.account('codex')
        old = copy.deepcopy(self.store.config['sources'][first])
        def fake_login(_executable, job):
            path = job['directory']; (path / 'auth.json').write_text('{"test":"separate"}')
            return {'managed': True, 'enabled': True, 'home': str(path)}
        with patch.object(subscription_auth.shutil, 'which', return_value='/test/codex'), \
             patch.object(self.store.subscriptions, '_codex', side_effect=fake_login):
            self.store.start_subscription('codex', {'name': 'Second account'})
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                state = self.store.subscriptions.statuses().get('codex', {})
                if state.get('state') in ('connected', 'error'): break
                time.sleep(.02)
        self.assertEqual(state['state'], 'connected')
        accounts = self.store.subscription_status()['codex']['accounts']
        self.assertEqual(len(accounts), 2)
        self.assertEqual(self.store.config['sources'][first], old)
        second = next(a for a in accounts if a['id'] != first)
        self.assertEqual(second['name'], 'Second account')
        self.assertNotEqual(self.store.config['sources'][second['id']]['home'], old['home'])

    def test_failed_new_authorization_preserves_existing_account(self):
        key = self.account('codex')
        original = copy.deepcopy(self.store.config)
        with patch.object(subscription_auth.shutil, 'which', return_value='/test/codex'), \
             patch.object(self.store.subscriptions, '_codex', side_effect=subscription_auth.LoginError('test login failure')):
            self.store.start_subscription('codex', {'name': 'Will fail'})
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                state = self.store.subscriptions.statuses().get('codex', {})
                if state.get('state') == 'error': break
                time.sleep(.02)
        self.assertEqual(state['state'], 'error')
        self.assertEqual(self.store.config, original)
        self.assertEqual(len(self.store.subscription_status()['codex']['accounts']), 1)

    def test_two_codex_queries_read_their_own_login_directories(self):
        first = self.account('codex')
        second = self.account('codex', 'a')
        for identifier, remaining in [(first, 91), (second, 22)]:
            path = self.root / identifier.replace(':', '-') / 'auth.json'
            path.write_text(json.dumps({'remaining': remaining}))
        executable = self.root / 'fake-codex'
        executable.write_text("#!/usr/bin/env python3\nimport json, os, sys\nfrom pathlib import Path\nhome = Path(os.environ['CODEX_HOME'])\nassert Path.cwd() == home\nassert 'OPENAI_API_KEY' not in os.environ\nremaining = json.loads((home / 'auth.json').read_text())['remaining']\nfor line in sys.stdin:\n    request = json.loads(line)\n    if 'id' not in request: continue\n    result = {}\n    if request['method'] == 'account/read': result = {'account': {'type': 'chatgpt'}}\n    if request['method'] == 'account/rateLimits/read': result = {'rateLimits': {'primary': {'usedPercent': 100 - remaining, 'windowDurationMins': 300}}}\n    print(json.dumps({'id': request['id'], 'result': result}), flush=True)\n")
        executable.chmod(0o700)
        with patch.object(adapters.shutil, 'which', return_value=str(executable)):
            self.store.refresh_lock.acquire(); self.store.collect()
        rows = {r['_sourceId']: r for r in self.store.rows}
        self.assertEqual(rows[first]['windows'][0]['remainingPercent'], 91)
        self.assertEqual(rows[second]['windows'][0]['remainingPercent'], 22)

    def test_two_claude_queries_use_their_own_tokens(self):
        first = self.account('claude')
        second = self.account('claude', 'a')
        seen = []
        def fetch(_url, headers):
            token = headers['Authorization'][7:]; seen.append(token)
            return {'five_hour': {'utilization': 10 if token == first else 75}}
        with patch.object(adapters, 'fetch_json', side_effect=fetch):
            self.store.refresh_lock.acquire(); self.store.collect()
        self.assertCountEqual(seen, [first, second])
        rows = {r['_sourceId']: r for r in self.store.rows}
        self.assertEqual(rows[first]['windows'][0]['remainingPercent'], 90)
        self.assertEqual(rows[second]['windows'][0]['remainingPercent'], 25)


class MultipleAccountHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixtures.HTTPAccess.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls): fixtures.HTTPAccess.tearDownClass.__func__(cls)
    request = fixtures.HTTPAccess.request

    def test_account_updates_require_local_admin_and_validate_target(self):
        path = '/api/subscriptions/codex/update'
        self.assertEqual(self.request(path, None, 'POST', {})[0], 401)
        self.assertEqual(self.request(path, 'viewer', 'POST', {})[0], 403)
        self.assertEqual(self.request(path, 'admin', 'POST', {'accountId': 'claude', 'enabled': True})[0], 400)
        self.assertEqual(self.request('/api/subscriptions/codex/start', 'admin', 'POST', {'home': '/tmp'})[0], 400)
        with patch.object(self.store.subscriptions, 'start', return_value={}):
            self.assertEqual(self.request('/api/subscriptions/codex/start', 'admin', 'POST', {'name': 'Work'})[0], 202)
