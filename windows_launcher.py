"""Windows foreground launcher; no installation, login or cloud writes on its own."""
import os
from pathlib import Path
import subprocess
import sys


def main():
    if sys.platform != 'win32':
        raise SystemExit('This launcher is for Windows only.')
    if sys.version_info < (3, 9):
        raise SystemExit('Python 3.9+ is required.')
    root = Path(__file__).resolve().parent
    config = root / 'windows-icloud-path.txt'
    env = dict(os.environ, PYTHONUTF8='1')
    if config.is_file():
        destination = config.read_text(encoding='utf-8-sig').strip()
        if not Path(destination).is_absolute() or not Path(destination).is_dir():
            raise SystemExit('windows-icloud-path.txt must contain an existing absolute Scriptable container path.')
        env['QUOTA_POCKET_ICLOUD_DIR'] = destination
    print('Quota Pocket: keep this window open while collecting. Ctrl+C stops it.', flush=True)
    try:
        return subprocess.call([sys.executable, '-X', 'utf8', str(root / 'server.py'), '--open'], cwd=root, env=env)
    except KeyboardInterrupt:
        return 0


if __name__ == '__main__':
    sys.exit(main())
