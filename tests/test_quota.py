import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import uuid

import adapters as a
import server as s


def workspace():
    # Fixtures remain in the ignored output directory; never recursively remove files.
    path = a.ROOT / 'output/test-runs' / uuid.uuid4().hex
    path.mkdir(parents=True)
    return path


class QuotaSemantics(unittest.TestCase):
    def test_claude_reads_platform_windows_not_extra_spend(self):
        path=workspace()/'credentials.json'
        path.write_text(json.dumps({'claudeAiOauth':{'accessToken':'TEST_ONLY','scopes':['user:profile']}}))
        data={'five_hour':{'utilization':21,'resets_at':'2026-09-13T12:00:00Z'},'seven_day':{'utilization':None},'seven_day_opus':{'utilization':100},'extra_usage':{'used_credits':800}}
        with patch.dict(a.os.environ,{'CLAUDE_QUOTA_OAUTH_TOKEN':''}),patch.object(a,'fetch_json',return_value=data):
            result=a.claude_native({'path':str(path)})[0]
        self.assertEqual([w['remainingPercent'] for w in result['windows']],[79,None,0])
        self.assertEqual(result['balances'],[])
        self.assertNotIn('TEST_ONLY',json.dumps(result))

    def test_codex_rpc_contract_with_synthetic_cli(self):
        root=workspace();cli=root/'codex';calls=root/'calls.json'
        cli.write_text('#!/usr/bin/env python3\nimport sys,json\nfrom pathlib import Path\ncalls=[]\nfor line in sys.stdin:\n r=json.loads(line);calls.append(r["method"])\n Path('+repr(str(calls))+').write_text(json.dumps(calls))\n if "id" not in r:continue\n result={}\n if r["method"]=="account/read":result={"account":{"type":"chatgpt","planType":"plus"}}\n if r["method"]=="account/rateLimits/read":result={"rateLimits":{"primary":{"usedPercent":37,"windowDurationMins":300,"resetsAt":1800000000},"secondary":None}}\n print(json.dumps({"id":r["id"],"result":result}),flush=True)\n')
        cli.chmod(0o700)
        with patch.object(a.shutil,'which',return_value=str(cli)):
            result=a.codex_native({})[0]
        self.assertEqual(result['windows'][0]['remainingPercent'],63)
        self.assertEqual(result['windows'][0]['label'],'5 小时额度')
        self.assertEqual(json.loads(calls.read_text()),['initialize','initialized','account/read','account/rateLimits/read'])

    def test_unknown_is_not_zero(self):
        self.assertIsNone(a.window('周额度')['remainingPercent'])
        self.assertIsNone(a.window('周额度', used=True)['remainingPercent'])
        self.assertEqual(a.window('周额度', used=100)['remainingPercent'], 0)
        self.assertEqual(a.window('周额度', used=25)['remainingPercent'], 75)
        self.assertIsNone(a.number(float('nan')))

    def test_no_cost_or_identity_forwarding(self):
        packet = {'schemaVersion': 1, 'providers': [{'id': 'claude', 'identity': {'accountEmail': 'private@example.com'},
                   'cost': {'todayUSD': 9000}, 'windows': [{'label': '周额度', 'usedPercent': 28}],
                   'error': 'Authorization Bearer SUPER_SECRET', 'updatedAt': '2026-09-13T00:00:00Z'}]}
        result = a.normalize_codexbar(packet)
        self.assertEqual(result[0]['windows'][0]['remainingPercent'], 72)
        text = json.dumps(result)
        for secret in ['SUPER_SECRET', 'private@example.com', '9000', 'todayUSD']:
            self.assertNotIn(secret, text)
        self.assertEqual(result[0]['status'], 'error')

    def test_multiple_accounts_keep_scoped_windows(self):
        payload = {'schemaVersion': 1, 'providers': [{'id': 'claude', 'accounts': [
            {'id': '1', 'active': True, 'windows': [{'label': 'Opus 每周', 'remainingPercent': 0}]},
            {'id': '2', 'windows': [{'label': '当前窗口', 'remainingPercent': None}]}]}]}
        result = a.normalize_codexbar(payload)
        self.assertEqual(len(result), 2)
        self.assertNotEqual(result[0]['id'], result[1]['id'])
        self.assertEqual(result[0]['windows'][0]['remainingPercent'], 0)
        self.assertIsNone(result[1]['windows'][0]['remainingPercent'])

    def test_cc_balances_preserve_units_without_totals(self):
        item = a.cc_result([{'remaining': 18.2, 'unit': 'USD'}, {'remaining': 42.3, 'unit': 'CNY'}], a.row('id', 'Provider', 'CC Switch'))
        self.assertEqual([b['unit'] for b in item['balances']], ['USD', 'CNY'])
        self.assertEqual(item['windows'], [])
        self.assertNotIn('total', item)

    def test_disabled_source_and_unknown_schema(self):
        with self.assertRaises(a.SourceError): a.normalize_codexbar({'schemaVersion': 2, 'providers': []})


class ScriptIsolation(unittest.TestCase):
    def test_template_variables_do_not_become_code(self):
        code = "({request:{url:'{{baseUrl}}/balance',method:'GET',headers:{Authorization:'Bearer {{apiKey}}'}},extractor:r=>({remaining:r.balance,unit:'CNY'})})"
        key = "a';globalThis.compromised=true;//\n`$"
        request = a.sandbox(code, {'baseUrl':'https://example.com','apiKey':key}, 'request')
        self.assertEqual(request['headers']['Authorization'], 'Bearer ' + key)
        value = a.sandbox(code, {'baseUrl':'https://example.com','apiKey':key}, 'extract', {'balance': 42.3})
        self.assertEqual(value['remaining'], 42.3)

    def test_no_node_capabilities_and_bounded_loop(self):
        for code in ["({request:{url:process.env.HOME}})", '(()=>{while(true){};})()']:
            start = time.monotonic()
            with self.assertRaises(a.SourceError): a.sandbox(code, {}, 'request')
            self.assertLess(time.monotonic()-start, 6)

    def test_same_origin_and_https_required(self):
        for url, base in [('https://evil.example/balance','https://good.example/v1'), ('http://example.com/balance','http://example.com')]:
            with self.assertRaises(a.SourceError): a.validate_query(url, base)
        with self.assertRaises(a.SourceError): a.validate_query('http://192.168.1.5', local=True)
        with self.assertRaises(a.SourceError): a.validate_query('https://127.0.0.1')

    def test_fake_ip_option_does_not_allow_localhost_or_literal_targets(self):
        synthetic=[(2,1,6,'',('198.18.0.12',443))]
        with patch.object(a.socket,'getaddrinfo',return_value=synthetic):
            with self.assertRaises(a.SourceError):a.validate_query('https://example.com')
            a.validate_query('https://example.com',allow_fake_ip=True)
            with self.assertRaises(a.SourceError):a.validate_query('https://198.18.0.12',allow_fake_ip=True)
        private=[(2,1,6,'',('127.0.0.1',443))]
        with patch.object(a.socket,'getaddrinfo',return_value=private):
            with self.assertRaises(a.SourceError):a.validate_query('https://example.com',allow_fake_ip=True)

    def test_cc_query_keeps_database_unchanged(self):
        path = workspace() / 'cc.db'
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE providers (id TEXT, app_type TEXT, name TEXT, settings_config TEXT, meta TEXT, is_current BOOL, sort_index INT, created_at INT)')
            code = '({request:{url:"{{baseUrl}}/balance",method:"GET",headers:{Authorization:"Bearer {{apiKey}}"}},extractor:r=>({remaining:r.balance,unit:"USD"})})'
            meta = json.dumps({'usage_script': {'enabled': True, 'code': code}})
            settings = json.dumps({'env': {'ANTHROPIC_BASE_URL':'https://example.com','ANTHROPIC_AUTH_TOKEN':'SECRET'}})
            db.execute('INSERT INTO providers VALUES (?,?,?,?,?,?,?,?)', ('p','claude','Provider',settings,meta,True,1,1))
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        with patch.object(a, 'fetch_json', return_value={'balance': 12.5}):
            result = a.cc_switch({'path': str(path), 'mode': 'independent'})
        self.assertEqual(result[0]['balances'][0]['value'], 12.5)
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertEqual(before, hashlib.sha256(path.read_bytes()).hexdigest())


class SnapshotLifecycle(unittest.TestCase):
    def test_failure_keeps_success_time_and_old_balance(self):
        store = s.Store(workspace())
        store.config['sources']['cc-switch']['enabled'] = True
        item = a.row('p', 'Provider', 'CC Switch')
        item['balances'] = [{'label':'余额','value':0,'unit':'CNY'}]
        a.finish(item, '2026-09-12T00:00:00Z')
        with patch.dict(a.ADAPTERS, {'cc-switch': lambda _: [item]}):
            store.refresh_lock.acquire();store.collect()
        def fail(_): raise a.SourceError('凭证已过期')
        with patch.dict(a.ADAPTERS, {'cc-switch': fail}):
            store.refresh_lock.acquire();store.collect()
        actual = store.snapshot()['providers'][0]
        self.assertEqual(actual['balances'][0]['value'], 0)
        self.assertEqual(actual['lastSuccessAt'], '2026-09-12T00:00:00Z')
        self.assertEqual(actual['status'], 'error')
        self.assertNotIn('_sourceId', actual)

    def test_invalid_settings_are_atomic(self):
        store=s.Store(workspace());before=copy.deepcopy(store.config)
        with self.assertRaises(ValueError): store.configure({'intervalSeconds':600,'sources':{'codex':True,'claude':'bad'}})
        self.assertEqual(store.config,before)


class CCSwitchCacheBridge(unittest.TestCase):
    def fixture(self):
        root = workspace()
        db_path = root / 'cc.db'
        with sqlite3.connect(db_path) as db:
            db.execute('CREATE TABLE providers (id TEXT, app_type TEXT, name TEXT, is_current BOOL)')
            db.execute('INSERT INTO providers VALUES (?,?,?,?)', ('p', 'codex', 'My Provider', True))
        self.path = root / 'cache.json'
        self.config = {'mode': 'snapshot', 'path': str(db_path), 'snapshotPath': str(self.path)}
        self.captured = '2026-09-12T00:00:00Z'
        self.entry = {'kind': 'script', 'appType': 'codex', 'providerId': 'p',
                      'observedAt': self.captured, 'success': True,
                      'data': [{'remaining': 0, 'unit': 'CNY'}]}
        self.write([self.entry])

    def write(self, entries):
        self.path.write_text(json.dumps({'schemaVersion': 1, 'source': 'cc-switch-usage-cache',
                                        'exportedAt': a.now(), 'entries': entries}))

    def test_snapshot_never_queries_and_keeps_original_capture_time(self):
        self.fixture()
        with patch.object(a, 'fetch_json', side_effect=AssertionError('No HTTP')), patch.object(a, 'sandbox', side_effect=AssertionError('No scripts')):
            first = a.cc_switch(self.config)[0]
            # A new export timestamp cannot rejuvenate an unchanged provider.
            self.write([self.entry])
            again = a.cc_switch(self.config)[0]
        self.assertEqual(first['balances'][0]['value'], 0)
        self.assertEqual(again['lastSuccessAt'], self.captured)
        self.assertEqual(again['lastAttemptAt'], self.captured)
        self.assertEqual(first['id'], again['id'])

    def test_missing_or_invalid_snapshot_never_falls_back(self):
        self.fixture()
        missing = dict(self.config, snapshotPath=str(self.path.parent / 'missing.json'))
        with patch.object(a, 'cc_switch_query', side_effect=AssertionError('No fallback')):
            with self.assertRaises(a.SourceError): a.cc_switch(missing)
            self.path.write_text('{')
            with self.assertRaises(a.SourceError): a.cc_switch(self.config)
            self.path.write_text(json.dumps({'schemaVersion': 2, 'entries': []}))
            with self.assertRaises(a.SourceError): a.cc_switch(self.config)

    def test_subscription_projection_and_account_isolation(self):
        self.fixture()
        entries = [{'kind': 'codex_oauth', 'appType': 'codex', 'accountId': account,
                    'observedAt': self.captured, 'success': True,
                    'tiers': [{'name': 'five_hour', 'utilization': used, 'usedValueUsd': 999}],
                    'credentialMessage': 'SECRET', 'error': 'SECRET', 'email': 'private@example.com'}
                   for account, used in [('a', 25), ('b', 100)]]
        self.write(entries)
        result = a.cc_switch(self.config)
        self.assertEqual([r['windows'][0]['remainingPercent'] for r in result], [75, 0])
        self.assertNotEqual(result[0]['id'], result[1]['id'])
        for secret in ['SECRET', 'private@example.com', '999']:
            self.assertNotIn(secret, json.dumps(result))

    def test_empty_export_clears_removed_entries(self):
        self.fixture()
        store = s.Store(workspace())
        store.config['sources']['cc-switch'] = dict(self.config, enabled=True)
        store.refresh_lock.acquire(); store.collect()
        self.assertEqual(len(store.rows), 1)
        self.write([])
        store.refresh_lock.acquire(); store.collect(cached_only=True)
        self.assertEqual(store.rows, [])

    def test_bad_times_and_duplicate_entries_are_rejected(self):
        self.fixture()
        for timestamp in [None, 'bad', '2999-01-01T00:00:00Z']:
            self.write([dict(self.entry, observedAt=timestamp)])
            with self.assertRaises(a.SourceError): a.cc_switch(self.config)
        self.write([self.entry, self.entry])
        with self.assertRaises(a.SourceError): a.cc_switch(self.config)

    def test_failed_upstream_export_keeps_previous_success_value(self):
        self.fixture()
        store = s.Store(workspace())
        store.config['sources']['cc-switch'] = dict(self.config, enabled=True)
        store.refresh_lock.acquire(); store.collect()
        self.write([dict(self.entry, success=False, observedAt=a.now(), data=[], error='SECRET')])
        store.refresh_lock.acquire(); store.collect(cached_only=True)
        actual = store.snapshot()['providers'][0]
        self.assertEqual(actual['lastSuccessAt'], self.captured)
        self.assertEqual(actual['balances'][0]['value'], 0)
        self.assertEqual(actual['status'], 'error')
        self.assertNotIn('SECRET', json.dumps(actual))

    def test_cache_sync_does_not_poll_other_sources(self):
        self.fixture()
        store = s.Store(workspace())
        store.config['sources']['cc-switch'] = dict(self.config, enabled=True)
        store.config['sources']['codex']['enabled'] = True
        with patch.dict(a.ADAPTERS, {'codex': lambda _: self.fail('Cache update polled Codex')}):
            store.refresh_lock.acquire(); store.collect(cached_only=True)
        self.assertEqual(len(store.rows), 1)

    def test_default_and_explicit_compatibility_configuration(self):
        store = s.Store(workspace())
        self.assertEqual(store.config['intervalSeconds'], 300)
        self.assertEqual(store.config['sources']['cc-switch']['mode'], 'independent')
        with patch.object(store, 'request_refresh'):
            store.configure({'sources': {'cc-switch': True, 'codex': True, 'claude': True, 'codexbar': True}, 'ccSwitchMode': 'snapshot'})
        self.assertFalse(any(store.config['sources'][key]['enabled'] for key in ['codex', 'claude', 'codexbar']))
        before = copy.deepcopy(store.config)
        with self.assertRaises(ValueError):
            store.configure({'sources': {}, 'ccSwitchMode': 'auto-fallback'})
        self.assertEqual(store.config, before)

    def test_mode_change_discards_inflight_old_results(self):
        store = s.Store(workspace())
        store.config['sources']['cc-switch'].update(enabled=True, mode='independent')
        def delayed(_):
            with patch.object(store, 'request_refresh'):
                store.configure({'sources': {'cc-switch': True}, 'ccSwitchMode': 'snapshot'})
            return [a.finish(a.row('old', 'Old request', 'CC Switch'))]
        with patch.dict(a.ADAPTERS, {'cc-switch': delayed}):
            store.refresh_lock.acquire(); store.collect()
        self.assertEqual(store.rows, [])
        self.assertEqual(store.last_started, 0)


class SavedMobileConnection(unittest.TestCase):
    def test_unrelated_settings_preserve_saved_address_and_explicit_clear_works(self):
        store=s.Store(workspace())
        store.config['publicUrl']='https://saved.example'
        with patch.object(store,'request_refresh'):
            store.configure({'sources':{'cc-switch':True},'intervalSeconds':600})
            self.assertEqual(store.config['publicUrl'],'https://saved.example')
            self.assertEqual(s.Store(store.directory).config['publicUrl'],'https://saved.example')
            store.configure({'sources':{},'publicUrl':''})
            self.assertEqual(store.config['publicUrl'],'')


class WidgetSelection(unittest.TestCase):
    def store(self):
        store=s.Store(workspace())
        store.rows=[a.row(uid,uid,'CC Switch') for uid in ['a','b','c']]
        return store

    def test_order_persists_without_polling_and_admin_keeps_all(self):
        store=self.store()
        with patch.object(store,'request_refresh') as query:
            store.configure_widget({'providerIds':['c','a']})
            query.assert_not_called()
        self.assertEqual([r['id'] for r in store.snapshot(widget_only=True)['providers']],['c','a'])
        self.assertEqual([r['id'] for r in store.snapshot()['providers']],['a','b','c'])
        self.assertEqual(s.Store(store.directory).widget_settings()['providerIds'],['c','a'])

    def test_empty_selection_and_missing_accounts_do_not_fall_back(self):
        store=self.store()
        store.configure_widget({'providerIds':[]})
        self.assertEqual(store.snapshot(widget_only=True)['providers'],[])
        store.configure_widget({'providerIds':['b']})
        store.rows=[r for r in store.rows if r['id']!='b']
        self.assertEqual(store.snapshot(widget_only=True)['providers'],[])
        self.assertEqual(store.widget_settings()['providerIds'],['b'])

    def test_invalid_selection_is_atomic_and_new_accounts_stay_unselected(self):
        store=self.store()
        store.configure_widget({'providerIds':['a']})
        for ids in [['a','a'],['missing'],'a',[None]]:
            with self.assertRaises(ValueError):store.configure_widget({'providerIds':ids})
            self.assertEqual(store.widget_settings()['providerIds'],['a'])
        store.rows.append(a.row('new','New','CC Switch'))
        self.assertEqual([r['id'] for r in store.snapshot(widget_only=True)['providers']],['a'])


class HTTPAccess(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store=s.Store(workspace())
        cls.http=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);cls.http.store=cls.store
        cls.base='http://127.0.0.1:%d'%cls.http.server_port
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()

    @classmethod
    def tearDownClass(cls): cls.http.shutdown();cls.http.server_close();cls.thread.join()

    def request(self,path,role=None,method='GET',body=None,extra=None):
        headers=extra.copy() if extra else {}
        if role: headers['Authorization']='Bearer '+self.store.keys[role]
        data=json.dumps(body).encode() if body is not None else None
        if data: headers['Content-Type']='application/json'
        req=urllib.request.Request(self.base+path,headers=headers,data=data,method=method)
        try:
            with urllib.request.urlopen(req) as response:return response.status,response.read(),response.headers
        except urllib.error.HTTPError as error:return error.code,error.read(),error.headers

    def test_private_routes_require_authorization(self):
        self.assertEqual(self.request('/api/snapshot')[0],401)
        self.assertEqual(self.request('/api/snapshot?token='+self.store.keys['viewer'])[0],401)
        self.assertEqual(self.request('/api/snapshot','viewer')[0],200)
        self.assertEqual(self.request('/api/settings','viewer')[0],403)
        self.assertEqual(self.request('/api/connection','viewer')[0],403)

    def test_pairing_single_use_expiry_isolation_and_revoke(self):
        original_url=self.store.config.get('publicUrl')
        try:
            self.store.config['publicUrl']='https://quota.example'
            self.assertEqual(self.request('/api/pair',None,'POST')[0],401)
            self.assertEqual(self.request('/api/pair','viewer','POST')[0],403)
            def create():
                status,body,headers=self.request('/api/pair','admin','POST')
                self.assertEqual(status,200);self.assertEqual(headers['Cache-Control'],'no-store')
                data=json.loads(body)
                self.assertNotIn(self.store.keys['viewer'],data['url'])
                return data['url'].split('#pair=')[1]
            code=create()
            other=s.Store(workspace());other.config['publicUrl']='https://other.example'
            self.assertIsNone(other.exchange_pairing(code))
            status,body,_=self.request('/api/pair/exchange',None,'POST',{'code':code})
            self.assertEqual(status,200);self.assertEqual(json.loads(body)['token'],self.store.keys['viewer'])
            self.assertNotIn(self.store.keys['admin'],body.decode())
            self.assertEqual(self.request('/api/pair/exchange',None,'POST',{'code':code})[0],410)
            code=create()
            with patch.object(s.time,'monotonic',return_value=time.monotonic()+601):
                self.assertEqual(self.request('/api/pair/exchange',None,'POST',{'code':code})[0],410)
            code=create();self.request('/api/revoke','admin','POST')
            self.assertEqual(self.request('/api/pair/exchange',None,'POST',{'code':code})[0],410)
            code=create();self.store.config['publicUrl']='https://changed.example'
            self.assertEqual(self.request('/api/pair/exchange',None,'POST',{'code':code})[0],410)
        finally:
            self.store.config['publicUrl']=original_url;self.store.pairings.clear()

    def test_pairing_download_and_origin_safety(self):
        self.assertEqual(self.request('/api/pair/exchange',None,'POST',{'code':'x'*43}, {'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request('/api/pair/exchange',None,'POST',[])[0],400)
        self.assertEqual(self.request('/api/pair/exchange',None,'POST',{'code':[]} )[0],410)
        status,body,_=self.request('/downloads/Quota-Pocket.js')
        self.assertEqual(status,200)
        self.assertNotIn(self.store.keys['viewer'],body.decode())
        self.assertNotIn(self.store.keys['admin'],body.decode())

    def test_cross_origin_mutations_and_dns_rebinding_rejected(self):
        self.assertEqual(self.request('/api/refresh','viewer','POST',extra={'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request('/','viewer',extra={'Host':'evil.example'})[0],403)
        self.assertEqual(self.request('/.state/access.json')[0],404)

    def test_revoked_key_no_longer_reads(self):
        old=self.store.keys['viewer']
        self.assertEqual(self.request('/api/revoke','admin','POST')[0],200)
        self.assertEqual(self.request('/api/snapshot',extra={'Authorization':'Bearer '+old})[0],401)

    def test_demo_and_live_never_mix(self):
        demo=json.loads(self.request('/api/demo')[1]);live=json.loads(self.request('/api/snapshot','viewer')[1])
        self.assertTrue(demo['demo']);self.assertFalse(live['demo']);self.assertEqual(live['providers'],[])
        self.assertEqual(self.request('/api/snapshot','viewer')[2]['Cache-Control'],'no-store')

    def test_widget_selection_is_admin_only_and_applies_to_existing_viewer_route(self):
        rows=copy.deepcopy(self.store.rows);config=copy.deepcopy(self.store.config)
        try:
            self.store.rows=[a.row(uid,uid,'CC Switch') for uid in ['a','b','c']]
            self.assertEqual(self.request('/api/widget-settings','viewer','POST',{'providerIds':['c']})[0],403)
            self.assertEqual(self.request('/api/widget-settings','viewer')[0],403)
            self.assertEqual(self.request('/api/widget-settings','admin','POST',{'providerIds':['c','a']})[0],200)
            viewer=json.loads(self.request('/api/snapshot','viewer')[1])
            admin=json.loads(self.request('/api/snapshot','admin')[1])
            self.assertEqual([r['id'] for r in viewer['providers']],['c','a'])
            self.assertEqual([r['id'] for r in admin['providers']],['a','b','c'])
        finally:self.store.rows=rows;self.store.config=config


if __name__ == '__main__': unittest.main()
