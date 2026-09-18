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
