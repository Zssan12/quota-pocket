import os
import socket
import unittest
from unittest.mock import patch
import adapters as a


def dns(*ips):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443)) for ip in ips]


class ProxyFakeIPTests(unittest.TestCase):
    def test_default_error_is_actionable(self):
        with patch.object(a.socket, 'getaddrinfo', return_value=dns('198.18.0.12')):
            with self.assertRaisesRegex(a.SourceError, '代理 Fake-IP'):
                a.validate_query('https://example.com/quota')

    def test_opt_in_keeps_security_boundaries(self):
        with patch.object(a.socket, 'getaddrinfo', return_value=dns('198.18.0.12')):
            a.validate_query('https://example.com/quota', base='https://example.com', allow_fake_ip=True)
            for url in ['https://198.18.0.12/q', 'http://example.com/q', 'https://user:pass@example.com/q', 'https://other.example/q']:
                with self.subTest(url=url), self.assertRaises(a.SourceError):
                    a.validate_query(url, base='https://example.com', allow_fake_ip=True)
        for ip in ['127.0.0.1','10.0.0.1','172.16.0.1','192.168.0.1','169.254.169.254','169.254.1.1','192.0.2.1']:
            with patch.object(a.socket, 'getaddrinfo', return_value=dns('198.18.0.12', ip)):
                with self.subTest(ip=ip), self.assertRaises(a.SourceError):
                    a.validate_query('https://example.com', allow_fake_ip=True)

    def test_explicit_false_wins_over_environment(self):
        with patch.dict(os.environ, {'QUOTA_POCKET_FAKE_IP':'1'}):
            self.assertTrue(a.cc_fake_ip({}))
            self.assertFalse(a.cc_fake_ip({'allowProxyFakeIp': False}))
            self.assertTrue(a.cc_fake_ip({'allowProxyFakeIp': True}))
            self.assertFalse(a.cc_fake_ip({'allowProxyFakeIp': 'true'}))

    def test_other_fetches_do_not_inherit_environment(self):
        with patch.dict(os.environ, {'QUOTA_POCKET_FAKE_IP':'1'}), patch.object(a.socket, 'getaddrinfo', return_value=dns('198.18.0.12')):
            with self.assertRaises(a.SourceError):
                a.fetch_json('https://example.com')

    def test_settings_persist_and_invalid_types_return_400(self):
        import json
        import threading
        import urllib.request
        import urllib.error
        import server
        from test_quota import workspace
        root = workspace()
        store = server.Store(root)
        http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        http.store = store
        thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
        try:
            with patch.object(store, 'request_refresh'), patch.dict(os.environ, {'QUOTA_POCKET_FAKE_IP':'1'}):
                for value in ['true', 1, None, [], {}]:
                    request = urllib.request.Request('http://127.0.0.1:%d/api/settings' % http.server_port,
                        data=json.dumps({'sources': {}, 'ccSwitchAllowProxyFakeIp': value}).encode(),
                        headers={'Authorization':'Bearer '+store.keys['admin'], 'Content-Type':'application/json'})
                    with self.assertRaises(urllib.error.HTTPError) as failure:
                        urllib.request.urlopen(request)
                    self.assertEqual(failure.exception.code, 400)
                for enabled in [True, False]:
                    store.source_retries['cc-switch'] = {'failures': 3, 'due': 999999999}
                    store.configure({'sources': {}, 'ccSwitchAllowProxyFakeIp': enabled})
                    self.assertNotIn('cc-switch', store.source_retries)
                    reloaded = server.Store(root)
                    self.assertEqual(reloaded.settings()['ccSwitchAllowProxyFakeIp'], enabled)
                    self.assertEqual(reloaded.config['sources']['cc-switch']['allowProxyFakeIp'], enabled)
        finally:
            http.shutdown(); http.server_close(); thread.join()

    def test_cc_query_flag_reaches_transport_and_projection(self):
        import json
        import sqlite3
        from test_quota import workspace
        from icloud_sync import quota_projection
        root = workspace(); dbpath = root / 'cc.db'
        with sqlite3.connect(dbpath) as db:
            db.execute('CREATE TABLE providers(id,app_type,name,settings_config,meta,is_current,sort_index,created_at)')
            db.execute('INSERT INTO providers VALUES(?,?,?,?,?,?,?,?)', ('test','claude','Test', '{}', json.dumps({'usage_script':{'enabled':True,'code':'TEST_SCRIPT'}}),1,1,1))
        def sandbox(code, variables, stage, response=None):
            return {'url':'https://example.com/quota','headers':{'Authorization':'Bearer TEST_SECRET'}} if stage=='request' else {'remaining':response['balance'],'unit':'USD'}
        import io
        opener = unittest.mock.MagicMock()
        opener.open.return_value.__enter__.side_effect = lambda: io.BytesIO(b'{"balance":12.34}')
        with patch.object(a, 'sandbox', side_effect=sandbox), patch.object(a, 'cc_credentials', return_value={'baseUrl':'https://example.com'}), patch.object(a.socket,'getaddrinfo', return_value=dns('198.18.0.12')), patch.object(a.urllib.request,'build_opener',return_value=opener):
            for enabled in [False, True, False]:
                rows = a.cc_switch_query({'path':str(dbpath),'allowProxyFakeIp':enabled})
                self.assertEqual(rows[0]['status'], 'ok' if enabled else 'error')
                if enabled:
                    packet = quota_projection({'providers':rows})
                    self.assertEqual(packet['providers'][0]['balances'][0]['value'],12.34)
                    for forbidden in ['TEST_SECRET','TEST_SCRIPT','example.com','Authorization']:
                        self.assertNotIn(forbidden,json.dumps(packet))
