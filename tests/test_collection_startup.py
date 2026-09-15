from pathlib import Path
import unittest
from unittest.mock import patch
import uuid

import server


class CollectionStartupTests(unittest.TestCase):
    def make_store(self):
        root = Path(__file__).resolve().parents[1] / 'output/test-runs' / ('startup-' + uuid.uuid4().hex)
        return server.Store(root)

    def test_first_request_at_clock_zero_runs_then_throttles(self):
        store = self.make_store()
        with patch.object(server.time, 'monotonic', return_value=0), \
                patch.object(server.threading, 'Thread') as thread:
            self.assertTrue(store.request_refresh())
            thread.return_value.start.assert_called_once()
            store.refresh_lock.release()  # The mocked worker does not collect.
            self.assertFalse(store.request_refresh())

    def test_loop_collects_immediately_at_clock_zero(self):
        store = self.make_store()
        with patch.object(server.time, 'monotonic', return_value=0), \
                patch.object(store, 'request_refresh') as refresh, \
                patch.object(store.stop, 'wait', side_effect=lambda _: store.stop.set()):
            store.loop()
        refresh.assert_called_once_with()

    def test_wake_resets_source_backoff_and_requests_fresh_collection(self):
        store = self.make_store()
        store.last_loop_at = 0
        store.source_retries = {'codex': {'failures': 4, 'due': 10000}}
        with patch.object(server.time, 'time', return_value=100), \
                patch.object(store, 'request_refresh') as refresh, \
                patch.object(store.stop, 'wait', side_effect=lambda _: store.stop.set()):
            store.loop()
        self.assertEqual(store.source_retries, {})
        refresh.assert_called_once_with()

    def test_scheduled_failures_back_off_but_manual_refresh_can_recover(self):
        from adapters import SourceError
        store = self.make_store()
        store.config['sources']['codex']['enabled'] = True
        with patch.dict(server.ADAPTERS, {'codex': lambda _: (_ for _ in ()).throw(SourceError('offline'))}), \
                patch.object(server.time, 'monotonic', return_value=100):
            store.refresh_lock.acquire(); store.collect()
        self.assertEqual(store.source_retries['codex']['due'], 400)
        attempts = list(store.source_status)
        with patch.dict(server.ADAPTERS, {'codex': lambda _: self.fail('Scheduled query ignored backoff')}), \
                patch.object(server.time, 'monotonic', return_value=101):
            store.refresh_lock.acquire(); store.collect()
        self.assertEqual(store.source_status, attempts)
        with patch.dict(server.ADAPTERS, {'codex': lambda _: []}), \
                patch.object(server.time, 'monotonic', return_value=102):
            store.refresh_lock.acquire(); store.collect(manual=True)
        self.assertEqual(store.source_retries, {})
