"""Renewal must use only the app-owned Claude CLI profile, never the user's default."""
import json
import os
import sys
import threading
import time
import unittest
from unittest.mock import patch
import subscription_auth as auth
from test_quota import workspace


class ClaudeCLIRefresh(unittest.TestCase):
    def setUp(self):
        self.root = workspace()
        self.path = self.root / 'credentials.json'
        self.cli = self.root / 'cli'
        self.cli.mkdir()
        self.old = {'accessToken': 'OLD', 'refreshToken': 'REFRESH', 'expiresAt': 1,
                    'scopes': ['user:profile']}
        self.new = dict(self.old, accessToken='NEW', refreshToken='ROTATED',
                        expiresAt=int((time.time()+3600)*1000))
        auth.private_json(self.path, {'claudeAiOauth': self.old})

    def test_expired_managed_profile_uses_cli_and_saves_rotation_once(self):
        with patch.object(auth.sys, 'platform', 'darwin'), \
             patch.object(auth.shutil, 'which', return_value='/test/claude'), \
             patch.object(auth, 'read_claude_login_credentials', side_effect=[self.old, self.new]) as read, \
             patch.object(auth, 'touch_claude_cli_auth') as touch, \
             patch.object(auth, 'refresh_claude') as direct:
            results = []
            threads = [threading.Thread(target=lambda: results.append(auth.managed_claude_token(self.path))) for _ in range(4)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
            self.assertEqual(results, ['NEW']*4)
            touch.assert_called_once_with('/test/claude', self.cli)
            self.assertEqual([c.args[0] for c in read.call_args_list], [self.cli, self.cli])
            direct.assert_not_called()
        saved = json.loads(self.path.read_text())['claudeAiOauth']
        self.assertEqual(saved['refreshToken'], 'ROTATED')
        if os.name != 'nt': self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_cli_failure_preserves_token_and_never_tries_a_second_refresh(self):
        before = self.path.read_bytes()
        with patch.object(auth.sys, 'platform', 'darwin'), \
             patch.object(auth.shutil, 'which', return_value='/test/claude'), \
             patch.object(auth, 'read_claude_login_credentials', return_value=self.old), \
             patch.object(auth, 'touch_claude_cli_auth'), \
             patch.object(auth, 'refresh_claude') as direct:
            with self.assertRaisesRegex(auth.LoginError, '官方 Claude CLI'):
                auth.managed_claude_token(self.path)
            direct.assert_not_called()
        self.assertEqual(before, self.path.read_bytes())

    def test_newer_cli_credentials_recover_interrupted_copy_without_refresh(self):
        with patch.object(auth.sys, 'platform', 'darwin'), \
             patch.object(auth.shutil, 'which', return_value='/test/claude'), \
             patch.object(auth, 'read_claude_login_credentials', return_value=self.new), \
             patch.object(auth, 'touch_claude_cli_auth') as touch:
            self.assertEqual(auth.managed_claude_token(self.path), 'NEW')
            touch.assert_not_called()

    def test_legacy_divergent_cli_token_does_not_replace_current_credentials(self):
        stale = dict(self.old, refreshToken='STALE_DIFFERENT', expiresAt=0)
        with patch.object(auth.sys, 'platform', 'darwin'), \
             patch.object(auth.shutil, 'which', return_value='/test/claude'), \
             patch.object(auth, 'read_claude_login_credentials', return_value=stale), \
             patch.object(auth, 'touch_claude_cli_auth') as touch, \
             patch.object(auth, 'refresh_claude', return_value=self.new) as direct:
            self.assertEqual(auth.managed_claude_token(self.path), 'NEW')
            direct.assert_called_once_with(self.old)
            touch.assert_not_called()

    def test_windows_keeps_existing_refresh_path_without_keychain(self):
        with patch.object(auth.sys, 'platform', 'win32'), \
             patch.object(auth, 'read_claude_login_credentials') as read, \
             patch.object(auth, 'touch_claude_cli_auth') as touch, \
             patch.object(auth, 'refresh_claude', return_value=self.new):
            self.assertEqual(auth.managed_claude_token(self.path), 'NEW')
            read.assert_not_called()
            touch.assert_not_called()

    def test_valid_token_never_touches_cli_or_keychain(self):
        auth.private_json(self.path, {'claudeAiOauth': self.new})
        with patch.object(auth, 'read_claude_login_credentials') as read, \
             patch.object(auth, 'touch_claude_cli_auth') as touch:
            self.assertEqual(auth.managed_claude_token(self.path), 'NEW')
            read.assert_not_called()
            touch.assert_not_called()

    def test_cli_command_cannot_inherit_tools_hooks_mcp_or_default_profile(self):
        command = auth.claude_refresh_command('/test/claude')
        self.assertEqual(command[-1], '/status')
        self.assertNotIn('--print', command)
        self.assertEqual(command[command.index('--tools')+1], '')
        self.assertEqual(command[command.index('--setting-sources')+1], '')
        self.assertTrue(json.loads(command[command.index('--settings')+1])['disableAllHooks'])
        self.assertIn('--strict-mcp-config', command)
        env = auth.isolated_env('claude', self.cli)
        self.assertEqual(env['CLAUDE_CONFIG_DIR'], str(self.cli))
        self.assertEqual(env['CLAUDE_SECURESTORAGE_CONFIG_DIR'], str(self.cli))

    @unittest.skipIf(os.name == 'nt', 'PTY driver is currently macOS only')
    def test_real_pty_driver_imports_fixture_cli_rotation(self):
        native = self.cli / '.credentials.json'
        auth.private_json(native, {'claudeAiOauth': self.old})
        executable = self.root / 'fixture-claude'
        executable.write_text('#!' + sys.executable + '\n' +
            'import json,os,sys\nfrom pathlib import Path\n' +
            'assert sys.argv[-1] == "/status"\n' +
            'assert os.environ["CLAUDE_CONFIG_DIR"] == os.environ["CLAUDE_SECURESTORAGE_CONFIG_DIR"]\n' +
            'assert Path.cwd().name == "quota-refresh"\n' +
            'target=Path(os.environ["CLAUDE_CONFIG_DIR"])/".credentials.json"\n' +
            'target.write_text(' + repr(json.dumps({'claudeAiOauth': self.new})) + ')\n' +
            'print("TEST_SECRET_OUTPUT_MUST_NOT_BE_FORWARDED")\n')
        executable.chmod(0o700)
        with patch.object(auth.sys, 'platform', 'darwin'), \
             patch.object(auth.shutil, 'which', return_value=str(executable)), \
             patch.object(auth, 'refresh_claude') as direct:
            self.assertEqual(auth.managed_claude_token(self.path), 'NEW')
            direct.assert_not_called()
        self.assertEqual(json.loads(self.path.read_text())['claudeAiOauth']['refreshToken'], 'ROTATED')
