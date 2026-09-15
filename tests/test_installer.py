import json
from pathlib import Path
import socket
import subprocess
import unittest
import uuid
from unittest.mock import patch

import adapters
import install


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.root = adapters.ROOT / 'output/test-runs' / ('installer-' + uuid.uuid4().hex)
        self.root.mkdir(parents=True)

    def test_existing_install_preserves_code_and_accounts_without_npm(self):
        (self.root / 'server.py').write_text('existing version')
        (self.root / '.state').mkdir()
        files = {'access.json': {'admin': 'test-only'}, 'icloud.json': {'installationId': 'keep-me'},
                 'config.json': {'sources': {'codex': {'enabled': True}}}}
        for name, value in files.items():
            (self.root / '.state' / name).write_text(json.dumps(value))
        before = {p.name: p.read_bytes() for p in (self.root / '.state').iterdir()}
        with patch('install.subprocess.run') as run:
            install.prepare_runtime(adapters.ROOT, self.root)
        run.assert_not_called()
        self.assertEqual((self.root / 'server.py').read_text(), 'existing version')
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.root / '.state').iterdir()})

    def test_dependency_failure_leaves_runtime_and_state_unmodified(self):
        (self.root / '.state').mkdir()
        state = self.root / '.state/access.json'
        state.write_text('{"admin":"keep-test-token"}')
        with patch('install.shutil.which', return_value='/mock/npm'), patch(
                'install.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'npm')):
            with self.assertRaises(subprocess.CalledProcessError):
                install.prepare_runtime(adapters.ROOT, self.root)
        self.assertEqual(state.read_text(), '{"admin":"keep-test-token"}')
        self.assertFalse((self.root / 'server.py').exists())
        self.assertFalse((self.root / '.install-pending').exists())

    def test_foreign_listener_is_not_stopped_or_launched_over(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            with patch('install.subprocess.Popen') as spawn, self.assertRaisesRegex(ValueError, '端口'):
                install.launch(self.root, listener.getsockname()[1], open_browser=False)
            spawn.assert_not_called()

    def test_reopen_authenticated_session_never_spawns_second_process(self):
        with patch('install.existing_session', return_value='http://localhost/#access=test-only'), \
             patch('install.subprocess.Popen') as spawn, patch('install.webbrowser.open') as browser:
            install.launch(self.root)
        spawn.assert_not_called()
        browser.assert_called_once()

    def test_launcher_uses_installed_helper_and_quotes_paths(self):
        special = self.root / 'spaces and $(do-not-run)'
        special.mkdir()
        launcher = install.write_launcher(special, 18931)
        self.assertIn(str(special / 'install.py'), launcher.read_text())
        self.assertNotIn(str(adapters.ROOT / 'install.py'), launcher.read_text())
        self.assertTrue((special / 'install.py').is_file())
        subprocess.run(['/bin/bash', '-n', str(launcher)], check=True)
        self.assertEqual(launcher.stat().st_mode & 0o777, 0o700)

    def test_missing_python_fails_before_creating_installation(self):
        destination = self.root / 'not-created'
        # Export a failing python3 function to exercise the preflight without
        # changing the real machine's interpreter or PATH.
        script = 'python3() { return 1; }; export -f python3; /bin/bash "$1" --source "$2" --install-dir "$3"'
        result = subprocess.run(['/bin/bash', '-c', script, 'test', str(adapters.ROOT / 'install.sh'),
                                 str(adapters.ROOT), str(destination)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Python', result.stdout)
        self.assertFalse(destination.exists())


if __name__ == '__main__':
    unittest.main()
