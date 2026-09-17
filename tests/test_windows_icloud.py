import json
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid

import icloud_sync
import service_manager
from icloud_sync import ICloudSync, scriptable_documents, ICloudError


class WindowsICloudTests(unittest.TestCase):
    def root(self):
        path = Path('output/test-runs') / ('windows-' + uuid.uuid4().hex)
        path.mkdir(parents=True)
        return path.resolve()

    def test_windows_container_has_no_documents_suffix(self):
        home = self.root()
        result = scriptable_documents('Windows', home, {})
        self.assertEqual(result, home / 'iCloudDrive/iCloud~dk~simonbs~Scriptable')
        self.assertFalse(result.exists())

    def test_custom_unicode_container_roundtrip_and_no_secret_export(self):
        root = self.root()
        dest = root / '自定义 云盘'; dest.mkdir()
        with patch.dict('os.environ', {'QUOTA_POCKET_ICLOUD_DIR': str(dest)}):
            sync = ICloudSync(root / 'state', Path('widgets/Quota-Pocket.js'))
            sync.configure(True, lambda: {'generatedAt': '2026-09-17T03:51:06Z', 'providers': [
                {'id': 'relay', 'name': '中转账户', 'balances': [{'label': '余额', 'value': 12.5, 'unit': 'CNY'}], 'token': 'SECRET'}]})
            content = (dest / sync.relative_snapshot_path).read_text(encoding='utf-8')
            self.assertIn('中转账户', content)
            self.assertNotIn('SECRET', content)
            self.assertEqual(json.loads(content)['providers'][0]['balances'][0]['value'], 12.5)
            self.assertIn(sync.relative_snapshot_path, (dest / sync.script_name).read_text(encoding='utf-8'))
            self.assertEqual(ICloudSync(root / 'state', Path('widgets/Quota-Pocket.js')).state['deviceId'], sync.state['deviceId'])

    def test_invalid_override_does_not_create_directory(self):
        root = self.root(); missing = root / 'missing'
        for value in ['relative', str(missing)]:
            with self.assertRaises(ICloudError):
                scriptable_documents('Windows', root, {'QUOTA_POCKET_ICLOUD_DIR': value})
        self.assertFalse(missing.exists())

    def test_windows_service_status_never_calls_launchctl(self):
        with patch.object(service_manager.sys, 'platform', 'win32'), patch.object(service_manager, 'run') as run:
            self.assertFalse(service_manager.status()['loaded'])
            run.assert_not_called()

    def test_windows_lock_uses_first_byte_and_releases_failed_handle(self):
        import server
        from types import SimpleNamespace
        from unittest.mock import Mock
        root = self.root()
        locking = Mock()
        backend = SimpleNamespace(locking=locking, LK_NBLCK=1)
        with patch.object(server.sys, 'platform', 'win32'), patch.dict('sys.modules', {'msvcrt': backend}):
            handle = server.instance_lock(root)
            locking.assert_called_once_with(handle.fileno(), 1, 1)
            handle.close()
            locking.side_effect = OSError('already locked')
            with self.assertRaises(ValueError):
                server.instance_lock(root)
