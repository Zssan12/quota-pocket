import json
from pathlib import Path
import uuid
from contextlib import contextmanager
import unittest
from unittest.mock import patch

import adapters as a


@contextmanager
def retained_fixture():
    root = Path(__file__).resolve().parents[1] / "output/test-runs" / ("subscription-display-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    yield root


class SubscriptionDisplay(unittest.TestCase):
    def test_codex_official_multi_bucket_response_reaches_native_windows(self):
        with retained_fixture() as directory:
            root = Path(directory)
            cli = root / 'codex'
            cli.write_text(
                '#!/usr/bin/env python3\n'
                'import json,sys\n'
                'for line in sys.stdin:\n'
                ' request=json.loads(line)\n'
                ' if "id" not in request: continue\n'
                ' result={}\n'
                ' if request["method"]=="account/read":\n'
                '  result={"account":{"type":"chatgpt","email":"test@example.com","planType":"plus"},"requiresOpenaiAuth":True}\n'
                ' if request["method"]=="account/rateLimits/read":\n'
                '  result={"rateLimits":{},"rateLimitsByLimitId":{\n'
                '   "codex":{"limitId":"codex","limitName":None,"primary":{"usedPercent":25,"windowDurationMins":300,"resetsAt":1800000000},"secondary":{"usedPercent":40,"windowDurationMins":10080,"resetsAt":1800600000}},\n'
                '   "codex_other":{"limitId":"codex_other","limitName":"Other models","primary":{"usedPercent":100,"windowDurationMins":60,"resetsAt":1800003600},"secondary":None}}}\n'
                ' print(json.dumps({"id":request["id"],"result":result}),flush=True)\n'
            )
            cli.chmod(0o700)
            with patch.object(a.shutil, 'which', return_value=str(cli)):
                item = a.codex_native({})[0]

        self.assertEqual(item['id'], 'native:codex')
        self.assertEqual(item['plan'], 'plus')
        self.assertEqual(
            [(window['label'], window['remainingPercent']) for window in item['windows']],
            [('5 小时额度', 75), ('每周额度', 60), ('Other models · 60 分钟额度', 0)],
        )
        self.assertEqual(item['status'], 'ok')
        self.assertNotIn('test@example.com', json.dumps(item))

    def test_claude_official_usage_windows_reach_native_without_extra_usage(self):
        payload = {
            'five_hour': {'utilization': 0, 'resets_at': '2026-09-13T12:00:00Z'},
            'seven_day': {'utilization': 100, 'resets_at': '2026-09-20T12:00:00Z'},
            'seven_day_sonnet': {'utilization': None, 'resets_at': None},
            'extra_usage': {'is_enabled': True, 'used_credits': 1234},
        }
        with patch.dict(a.os.environ, {'CLAUDE_QUOTA_OAUTH_TOKEN': 'TEST_ONLY_TOKEN'}), \
                patch.object(a, 'fetch_json', return_value=payload) as fetch:
            item = a.claude_native({})[0]

        self.assertEqual(
            [(window['id'], window['remainingPercent']) for window in item['windows']],
            [('five_hour', 100), ('seven_day', 0), ('seven_day_sonnet', None)],
        )
        self.assertEqual(item['balances'], [])
        self.assertNotIn('TEST_ONLY_TOKEN', json.dumps(item))
        self.assertEqual(fetch.call_args.args[0], 'https://api.anthropic.com/api/oauth/usage')
        self.assertEqual(fetch.call_args.args[1]['anthropic-beta'], 'oauth-2025-04-20')


if __name__ == '__main__':
    unittest.main()
