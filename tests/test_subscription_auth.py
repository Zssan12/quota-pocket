import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
import urllib.error
from unittest.mock import patch

import adapters as a
import server as s
import subscription_auth as auth
import test_quota as fixtures
workspace = fixtures.workspace


def wait_for(manager,kind,state,timeout=5):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        result=manager.statuses().get(kind,{})
        if result.get('state') in state:return result
        time.sleep(.02)
    raise AssertionError('Login did not reach expected state: '+str(manager.statuses()))


class IndependentLogins(unittest.TestCase):
    def test_environment_removes_shared_auth_and_helpers(self):
        with patch.dict(os.environ,{'CODEX_HOME':'/original','OPENAI_API_KEY':'SHARED_KEY','OPENAI_BASE_URL':'https://relay.example',
            'ANTHROPIC_API_KEY':'SHARED_CLAUDE','CLAUDE_CODE_OAUTH_TOKEN':'SHARED_OAUTH','CLAUDE_CONFIG_DIR':'/original-claude',
            'CLAUDE_SECURESTORAGE_CONFIG_DIR':'/shared-keychain','BASH_ENV':'/bad-helper','HTTPS_PROXY':'http://localhost:8888'}):
            for kind in ['codex','claude']:
                env=auth.isolated_env(kind,'/private/login')
                self.assertNotIn('SHARED',json.dumps(env));self.assertNotIn('BASH_ENV',env)
                self.assertEqual(env['HTTPS_PROXY'],'http://localhost:8888')
                if kind=='codex':self.assertEqual(env['CODEX_HOME'],'/private/login')
                else:self.assertEqual(env['CLAUDE_CONFIG_DIR'],env['CLAUDE_SECURESTORAGE_CONFIG_DIR'])

    def test_codex_success_uses_only_own_directory_and_account_rpcs(self):
        root=workspace();executable=root/'fake-codex'
        executable.write_text('''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
home=Path(os.environ['CODEX_HOME'])
assert Path.cwd()==home
assert 'OPENAI_API_KEY' not in os.environ
assert 'cli_auth_credentials_store="file"' in sys.argv
for line in sys.stdin:
 r=json.loads(line);method=r['method']
 if 'id' in r:assert 'params' in r
 if method=='initialized':continue
 result={}
 if method=='account/login/start':result={'type':'chatgpt','loginId':'job-1','authUrl':'https://auth.openai.com/oauth/authorize?state=TEST'}
 if method=='account/read':result={'account':{'type':'chatgpt','planType':'plus'}}
 print(json.dumps({'id':r['id'],'result':result}),flush=True)
 if method=='account/login/start':
  (home/'auth.json').write_text(json.dumps({'tokens':{'access_token':'PRIVATE_TEST'}}))
  print(json.dumps({'method':'account/login/completed','params':{'loginId':'job-1','success':True}}),flush=True)
''');executable.chmod(0o700)
        connections=[];manager=auth.SubscriptionLogins(root/'subscriptions',lambda k,c:connections.append((k,c)))
        with patch.object(auth.shutil,'which',return_value=str(executable)):
            manager.start('codex');state=wait_for(manager,'codex',{'connected','error'})
        manager.close();self.assertEqual(state['state'],'connected');self.assertEqual(len(connections),1)
        config=connections[0][1];self.assertTrue(config['managed']);self.assertTrue(Path(config['home']).is_relative_to(root/'subscriptions'))
        self.assertNotIn('PRIVATE_TEST',json.dumps(manager.statuses()))
        self.assertEqual((Path(config['home'])/'auth.json').stat().st_mode&0o777,0o600)

    def test_claude_manual_code_and_cancel_dont_activate(self):
        root=workspace();executable=root/'fake-claude'
        executable.write_text('''#!/usr/bin/env python3
import json,os,sys,time
from pathlib import Path
home=Path(os.environ['CLAUDE_CONFIG_DIR'])
assert os.environ['CLAUDE_SECURESTORAGE_CONFIG_DIR']==str(home)
assert Path.cwd()==home
assert 'ANTHROPIC_API_KEY' not in os.environ
print('If the browser did not open, visit: https://claude.com/cai/oauth/authorize?state=TEST_STATE',flush=True)
code=sys.stdin.readline().strip()
if code!='AUTH_CODE#TEST_STATE':sys.exit(1)
(home/'.credentials.json').write_text(json.dumps({'claudeAiOauth':{'accessToken':'TEST_SECRET_ACCESS','refreshToken':'TEST_SECRET_REFRESH','scopes':['user:profile'],'expiresAt':4102444800000}}))
''');executable.chmod(0o700)
        connections=[];manager=auth.SubscriptionLogins(root/'subscriptions',lambda k,c:connections.append((k,c)))
        with patch.object(auth.shutil,'which',return_value=str(executable)):
            first=manager.start('claude');waiting=wait_for(manager,'claude',{'waiting'})
            self.assertEqual(manager.start('claude')['id'],first['id'])
            for code in ['AUTH_CODE#WRONG','KEY','a\nb#TEST_STATE']:
                with self.assertRaises(auth.LoginError):manager.finish('claude',first['id'],code)
            manager.cancel('claude',first['id']);self.assertEqual(manager.statuses()['claude']['state'],'cancelled');self.assertEqual(connections,[])
            second=manager.start('claude');wait_for(manager,'claude',{'waiting'})
            with self.assertRaises(auth.LoginError):manager.finish('claude',first['id'],'AUTH_CODE#TEST_STATE')
            manager.finish('claude',second['id'],'AUTH_CODE#TEST_STATE')
            result=wait_for(manager,'claude',{'connected','error'})
        manager.close();self.assertEqual(result['state'],'connected')
        self.assertEqual(len(connections),1)
        self.assertNotIn('TEST_SECRET',json.dumps(manager.statuses()))
        self.assertEqual(auth.managed_claude_token(connections[0][1]['path']),'TEST_SECRET_ACCESS')

    def test_mac_keychain_is_exact_attempt_service(self):
        path=workspace()/'independent-cli';path.mkdir()
        data={'claudeAiOauth':{'accessToken':'TEST','scopes':['user:profile']}}
        with patch.object(auth.sys,'platform','darwin'),patch.object(auth.subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps(data),'')) as run:
            auth.read_claude_login_credentials(path)
        args=run.call_args.args[0]
        self.assertEqual(args[-1],'Claude Code-credentials-'+hashlib.sha256(str(path).encode()).hexdigest()[:8])
        self.assertNotEqual(args[-1],'Claude Code-credentials')

    def test_managed_claude_never_uses_environment_or_keychain(self):
        path=workspace()/'credentials.json'
        auth.private_json(path,{'claudeAiOauth':{'accessToken':'OWN_TOKEN','scopes':['user:profile']}})
        with patch.dict(os.environ,{'CLAUDE_QUOTA_OAUTH_TOKEN':'WRONG'}),patch.object(a,'fetch_json',return_value={'five_hour':{'utilization':30}}) as fetch,patch.object(auth.subprocess,'run') as keychain:
            result=a.claude_native({'managed':True,'path':str(path)})
            self.assertEqual(fetch.call_args.args[1]['Authorization'],'Bearer OWN_TOKEN');keychain.assert_not_called()
        self.assertEqual(result[0]['windows'][0]['remainingPercent'],70)
        with patch.object(a,'fetch_json',side_effect=a.SourceError('expired',status_code=401)):
            with self.assertRaisesRegex(a.SourceError,'独立 Claude 授权失效'):
                a.claude_native({'managed':True,'path':str(path)})

    def test_refresh_is_serialized_persisted_and_failure_keeps_token(self):
        path=workspace()/'credentials.json'
        old={'accessToken':'OLD','refreshToken':'REFRESH','scopes':['user:profile'],'expiresAt':1}
        auth.private_json(path,{'claudeAiOauth':old})
        updated=dict(old,accessToken='NEW',refreshToken='ROTATED',expiresAt=4102444800000)
        with patch.object(auth,'refresh_claude',return_value=updated) as refresh:
            threads=[threading.Thread(target=auth.managed_claude_token,args=(path,)) for _ in range(4)]
            for t in threads:t.start()
            for t in threads:t.join()
            self.assertEqual(refresh.call_count,1)
        self.assertEqual(json.loads(path.read_text())['claudeAiOauth']['refreshToken'],'ROTATED')
        self.assertEqual(path.stat().st_mode&0o777,0o600)
        auth.private_json(path,{'claudeAiOauth':old})
        with patch.object(auth,'refresh_claude',side_effect=auth.LoginError('temporary')):
            with self.assertRaises(auth.LoginError):auth.managed_claude_token(path)
        self.assertEqual(json.loads(path.read_text())['claudeAiOauth'],old)

    def test_reconnect_drops_old_quota_and_preserves_other_sources(self):
        store=s.Store(workspace());store.config['widgetProviderIds']=['native:codex']
        old=a.row('native:codex','Old','Codex');old['_sourceId']='codex'
        other=a.row('api','API','CC Switch');other['_sourceId']='cc-switch';store.rows=[old,other]
        before=copy.deepcopy(store.config['sources']['cc-switch'])
        with patch.object(store,'request_refresh'):
            store.connect_subscription('codex',{'managed':True,'home':str(workspace()),'enabled':True})
        self.assertEqual(store.rows,[other]);self.assertEqual(store.config['sources']['cc-switch'],before)
        self.assertEqual(store.config['widgetProviderIds'],['native:codex'])
        self.assertNotIn('Old',(store.directory/'snapshot.json').read_text())

    def test_managed_subscriptions_survive_legacy_source_exclusion(self):
        store=s.Store(workspace());store.config['sources']['codex'].update(managed=True,enabled=True)
        with patch.object(store,'request_refresh'):
            store.configure({'sources':{'cc-switch':True,'codex':True,'claude':True},'ccSwitchMode':'snapshot'})
        self.assertTrue(store.config['sources']['codex']['enabled']);self.assertFalse(store.config['sources']['claude']['enabled'])

    def test_only_trusted_auth_urls(self):
        for url in ['http://auth.openai.com/login','https://auth.openai.com.evil.example/login','https://user:pass@auth.openai.com/login','https://evil.example']:
            self.assertFalse(auth.trusted_auth_url('codex',url))
        self.assertTrue(auth.trusted_auth_url('codex','https://auth.openai.com/oauth/authorize?state=test'))


class SubscriptionHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.HTTPAccess.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):fixtures.HTTPAccess.tearDownClass.__func__(cls)
    request=fixtures.HTTPAccess.request

    def test_admin_only_and_private_status(self):
        self.assertEqual(self.request('/api/subscriptions')[0],401)
        self.assertEqual(self.request('/api/subscriptions','viewer')[0],403)
        for action in ('start','cancel','finish'):
            self.assertEqual(self.request('/api/subscriptions/claude/'+action,'viewer','POST',{})[0],403)
        status,body,headers=self.request('/api/subscriptions','admin')
        self.assertEqual(status,200);self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertNotIn(str(self.store.directory),body.decode())
        self.assertEqual(self.request('/api/subscriptions/codex/start','admin','POST',{}, {'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request('/api/subscriptions/claude/finish','admin','POST',[])[0],400)
        with patch.object(self.store.subscriptions,'start',return_value={}) as start:
            self.assertEqual(self.request('/api/subscriptions/codex/start','admin','POST')[0],202)
            start.assert_called_once_with('codex')
