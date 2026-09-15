#!/usr/bin/env python3
"""Install a fresh per-user runtime, or reopen an existing one. Never delete data."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import webbrowser


def existing_session(root, port):
    """Authenticate before attaching to any listener; never print the token."""
    address = 'http://127.0.0.1:%d/' % port
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=1):
            pass
    except ConnectionRefusedError:
        return None
    try:
        token = json.loads((root / '.state/access.json').read_text())['admin']
        request = urllib.request.Request(address + 'api/snapshot',
                                         headers={'Authorization': 'Bearer ' + token})
        # Local management must not go through an environment-configured HTTP proxy.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=3) as response:
            if json.load(response).get('schemaVersion') != 1:
                raise ValueError('Unexpected response')
    except (OSError, ValueError, KeyError):
        raise ValueError('本机端口 %d 已被其他服务占用；未停止它，也未更改账户。' % port) from None
    return address + '#access=' + token


def prepare_runtime(source, root):
    """Assemble and install dependencies before making a new runtime visible."""
    source, root = Path(source).resolve(), Path(root).resolve()
    if (root / 'server.py').is_file() and not (root / '.install-pending').exists():
        print('保留已有安装与账户；本命令只负责安装和打开，不自动升级。', flush=True)
        return
    stage = root / '.installer' / ('bundle-' + uuid.uuid4().hex)
    stage.mkdir(parents=True, mode=0o700)
    for item in source.glob('*.py'):
        shutil.copy2(item, stage / item.name)
    for name in ('sandbox.mjs', 'sync_crypto.mjs', 'package.json', 'package-lock.json'):
        shutil.copy2(source / name, stage / name)
    for name in ('web', 'widgets', 'vendor'):
        shutil.copytree(source / name, stage / name)
    print('[3/4] 安装查询组件，首次运行需要下载依赖……', flush=True)
    npm = shutil.which('npm')
    if not npm:
        raise ValueError('未找到 npm，请重新运行完整安装命令。')
    # Each bundle is fresh: no existing node_modules or account state to replace.
    subprocess.run([npm, 'ci', '--ignore-scripts', '--no-audit', '--no-fund'], cwd=stage, check=True)
    (root / '.install-pending').write_text('Installation in progress\n')
    for item in stage.iterdir():
        if item.is_dir():
            shutil.copytree(item, root / item.name, dirs_exist_ok=True)
        else:
            shutil.copy2(item, root / item.name)
    # Mark completion without deleting the retry marker.
    (root / '.install-pending').replace(root / '.install-complete')


def write_launcher(root, port):
    launcher = root / 'Start Quota Pocket.command'
    installed_helper = root / 'install.py'
    if not installed_helper.is_file():
        shutil.copy2(Path(__file__), installed_helper)
    script = ('#!/bin/bash\nset -e\nexport PATH=' + shlex.quote(os.environ['PATH']) + '\n')
    if os.environ.get('QUOTA_POCKET_FAKE_IP') == '1':
        script += 'export QUOTA_POCKET_FAKE_IP=1\n'
    script += 'exec ' + ' '.join(shlex.quote(value) for value in (
        sys.executable, str(installed_helper), '--install-dir', str(root),
        '--port', str(port), '--launch-only')) + '\n'
    launcher.write_text(script)
    launcher.chmod(0o700)
    return launcher


def launch(root, port=8931, open_browser=True):
    url = existing_session(root, port)
    if url is None:
        logs = root / '.state'
        logs.mkdir(mode=0o700, exist_ok=True)
        with (logs / 'startup.log').open('a') as log:
            proc = subprocess.Popen(
                [sys.executable, str(root / 'server.py'), '--port', str(port),
                 # Explicit spelling prevents server.py's old-checkout auto-redirect.
                 '--state-dir', str(logs) + '/.'],
                cwd=root, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                start_new_session=True)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise ValueError('启动失败。请检查 %s' % (logs / 'startup.log'))
            url = existing_session(root, port)
            if url:
                break
            time.sleep(0.2)
        else:
            # Only stop the process this installer just started.
            proc.terminate()
            proc.wait(timeout=15)
            raise ValueError('启动超时。请检查 %s' % (logs / 'startup.log'))
    if open_browser and not webbrowser.open(url):
        print('浏览器未自动打开。请稍后双击安装目录中的 Start Quota Pocket.command。')
    print('[4/4] 已启动。请在配置网页连接账户，再按引导添加 iPhone 小组件。')
    print('可以关闭终端。Mac 重启后请重新运行安装命令，或双击 Start Quota Pocket.command。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--install-dir', type=Path, default=Path.home() / 'Library/Application Support/QuotaPocket')
    parser.add_argument('--port', type=int, default=8931)
    parser.add_argument('--launch-only', action='store_true')
    parser.add_argument('--no-browser', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if sys.platform != 'darwin':
        parser.error('当前只支持 macOS。')
    os.umask(0o077)
    root = args.install_dir.expanduser().absolute()
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    with (root / '.installer.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.exit(1, '另一个安装正在运行，请等待完成。\n')
        try:
            # Fail on a conflicting listener before copying or installing anything.
            session = existing_session(root, args.port)
            if not args.launch_only and session is None:
                prepare_runtime(args.source, root)
            if not (root / 'server.py').is_file():
                raise ValueError('安装不完整，请重新运行安装命令。')
            launch(root, args.port, not args.no_browser)
            if not args.launch_only:
                # Keep bootstrap paths if reopening a pre-existing developer install.
                print('下次打开：%s' % write_launcher(root, args.port))
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
