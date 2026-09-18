import io
import json
import time
import unittest
import urllib.error
from unittest.mock import MagicMock, patch
import subscription_auth as auth
from test_quota import workspace


class ClaudeRefreshErrors(unittest.TestCase):
    def failure(self, status, payload):
        root=workspace();path=root/'credentials.json'
        auth.private_json(path,{'claudeAiOauth':{'accessToken':'TEST_ACCESS','refreshToken':'TEST_REFRESH','expiresAt':0,'scopes':['user:profile']}})
        before=path.read_bytes()
        opener=MagicMock()
        opener.open.side_effect=urllib.error.HTTPError('https://platform.claude.com/v1/oauth/token',status,'failed',{},io.BytesIO(payload))
        with patch.object(auth.urllib.request,'build_opener',return_value=opener):
            with self.assertRaises(auth.LoginError) as error:auth.managed_claude_token(path)
        self.assertEqual(path.read_bytes(),before)
        self.assertNotIn('TEST_',str(error.exception))
        return str(error.exception)

    def test_cloudflare_403_is_not_token_revocation(self):
        message=self.failure(403,b'{"message":"Cloudflare blocked this request. Contact support."}')
        self.assertIn('403',message)
        self.assertNotIn('授权已失效',message)
        self.assertNotIn('重新连接',message)

    def test_invalid_grant_requires_reconnect(self):
        message=self.failure(400,b'{"error":"invalid_grant"}')
        self.assertIn('重新连接',message)

    def test_rate_limit_and_service_error_are_retryable(self):
        for status in [429,500,503]:
            self.assertIn('稍后重试',self.failure(status,b'{}'))

    def test_unknown_400_does_not_assert_revocation(self):
        self.assertNotIn('授权已失效',self.failure(400,b'{"error":"invalid_request"}'))

    def test_refresh_matches_cli_json_contract_and_saves_rotation(self):
        root=workspace();path=root/'credentials.json'
        oauth={'accessToken':'TEST_OLD','refreshToken':'TEST_REFRESH','expiresAt':0,'scopes':['user:profile','user:inference']}
        auth.private_json(path,{'claudeAiOauth':oauth})
        def send(request, timeout):
            self.assertEqual(request.full_url,'https://platform.claude.com/v1/oauth/token')
            self.assertEqual(request.get_header('Content-type'),'application/json')
            body=json.loads(request.data)
            self.assertEqual(body,{'grant_type':'refresh_token','refresh_token':'TEST_REFRESH','client_id':'9d1c250a-e61b-44d9-88ed-5944d1962f5e','scope':'user:profile user:inference'})
            return io.BytesIO(json.dumps({'access_token':'TEST_NEW','refresh_token':'TEST_ROTATED','expires_in':3600}).encode())
        opener=MagicMock();opener.open.side_effect=send
        with patch.object(auth.urllib.request,'build_opener',return_value=opener):
            self.assertEqual(auth.managed_claude_token(path),'TEST_NEW')
        saved=json.loads(path.read_text())['claudeAiOauth']
        self.assertEqual(saved['refreshToken'],'TEST_ROTATED')
        self.assertGreater(saved['expiresAt'],time.time()*1000)
