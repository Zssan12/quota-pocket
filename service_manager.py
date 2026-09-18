#!/usr/bin/env python3
"""Per-user collector lifecycle. No file or directory deletion."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

if sys.platform != 'win32':
    import fcntl
import time
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parent
LABEL = 'app.quota-pocket.collector'


def runtime_root():
    return Path.home() / 'Library/Application Support/QuotaPocket'


def state_root(root=ROOT):
    installed = runtime_root() / '.state'
    return installed if (installed / 'access.json').is_file() else Path(root) / '.state'


def stage_runtime(root):
    root = Path(root).resolve()
    destination = runtime_root()
    if root == destination.resolve():
        return destination
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = destination / 'source-checkout.json'
    if marker.exists() and json.loads(marker.read_text()).get('path') != str(root):
        raise ValueError('后台运行目录属于其他项目副本。')
    # Copy only runtime assets; never sweep test output, history or credentials
    # into the code bundle. State is migrated once, then remains authoritative.
    for path in root.glob('*.py'):
        shutil.copy2(path, destination / path.name)
    for name in ('sandbox.mjs', 'package.json', 'package-lock.json'):
        shutil.copy2(root / name, destination / name)
    for name in ('web', 'widgets', 'node_modules'):
        if (root / name).is_dir():
            shutil.copytree(root / name, destination / name, dirs_exist_ok=True)
    old_state, new_state = root / '.state', destination / '.state'
    if not (new_state / 'access.json').exists():
        shutil.copytree(old_state, new_state, dirs_exist_ok=True)
        # Managed subscription files contain paths to their isolated login dirs.
        def migrate(value):
            if isinstance(value, str): return value.replace(str(old_state), str(new_state))
            if isinstance(value, list): return [migrate(v) for v in value]
            if isinstance(value, dict): return {k:migrate(v) for k,v in value.items()}
            return value
        for path in new_state.rglob('*.json'):
            try: value=json.loads(path.read_text())
            except (OSError, ValueError): continue
            path.write_text(json.dumps(migrate(value), ensure_ascii=False, indent=2))
            path.chmod(0o600)
    marker.write_text(json.dumps({'path': str(root)}))
    return destination


def run(*args):
    return subprocess.run(['launchctl', *args], capture_output=True, text=True, timeout=15)


def service_name():
    return 'gui/%s/%s' % (os.getuid(), LABEL)


def target_path():
    return Path.home() / 'Library/LaunchAgents' / (LABEL + '.plist')


def check_owned(root=ROOT):
    target = target_path()
    marker = runtime_root() / 'source-checkout.json'
    if Path(root).resolve() != runtime_root().resolve() and marker.is_file():
        if json.loads(marker.read_text()).get('path') != str(Path(root).resolve()):
            raise ValueError('Runtime belongs to another checkout.')
    if target.exists():
        if not target.is_file() or target.is_symlink():
            raise ValueError('后台配置不是普通文件。')
        old = plistlib.loads(target.read_bytes())
        if old.get('Label') != LABEL or not any(str(p / 'server.py') in old.get('ProgramArguments', []) for p in (Path(root).resolve(), runtime_root())):
            raise ValueError('同名后台服务属于其他项目，未做更改。')


def launch_agent(root=ROOT, python=None, environment=None):
    root = Path(root).resolve()
    environment = os.environ if environment is None else environment
    paths = list(dict.fromkeys(environment.get('PATH', '').split(':') +
                              ['/opt/homebrew/bin', '/usr/local/bin', '/usr/bin', '/bin']))
    env = {'PATH': ':'.join(p for p in paths if p), 'PYTHONUNBUFFERED': '1',
           'QUOTA_POCKET_MANAGED': 'launchd'}
    if environment.get('QUOTA_POCKET_FAKE_IP') == '1':
        env['QUOTA_POCKET_FAKE_IP'] = '1'
    return {'Label': LABEL, 'ProgramArguments': [python or sys.executable, '-u', str(root / 'server.py')],
            'WorkingDirectory': '/', 'EnvironmentVariables': env,
            'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 30,
            'ProcessType': 'Background', 'Umask': 0o077,
            'StandardOutPath': str(Path.home() / 'Library/Logs/QuotaPocket/collector.log'),
            'StandardErrorPath': str(Path.home() / 'Library/Logs/QuotaPocket/collector-error.log')}


def status(root=ROOT):
    if sys.platform != 'darwin':
        return {'loaded': False, 'enabled': False, 'details': ['当前平台请使用启动脚本运行采集器。']}
    check_owned(root)
    loaded = run('print', service_name())
    details = [l.strip() for l in loaded.stdout.splitlines()
               if l.strip().startswith(('state =', 'pid =', 'last exit code =', 'runs ='))]
    disabled = run('print-disabled', 'gui/' + str(os.getuid()))
    if disabled.returncode:
        raise ValueError('无法读取登录启动状态。')
    import re
    is_disabled = bool(re.search(r'"' + re.escape(LABEL) + r'"\s*=>\s*(?:true|disabled)\b', disabled.stdout))
    return {'loaded': loaded.returncode == 0, 'enabled': target_path().is_file() and not is_disabled,
            'details': details}


def request(path, root=ROOT, method='GET'):
    keys = json.loads((state_root(root) / 'access.json').read_text())
    req = urllib.request.Request('http://127.0.0.1:8931' + path,
                                 headers={'Authorization': 'Bearer ' + keys['admin']}, method=method)
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.load(response)


def stop_current(root=ROOT):
    # The authenticated endpoint belongs to this state. Never kill an arbitrary PID.
    try:
        request('/api/shutdown', root, 'POST')
    except (ConnectionResetError, ConnectionAbortedError):
        pass  # A service already exiting after bootout may reset the socket.
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise ValueError('运行的是旧版服务，请先在原终端停止它，再启用后台运行。') from None
        raise ValueError('无法验证当前服务，未停止进程。') from None
    except urllib.error.URLError as error:
        if isinstance(error.reason, ConnectionRefusedError):
            return
        raise ValueError('无法连接当前服务，请检查本机端口。') from None
    for _ in range(60):
        try:
            request('/api/snapshot', root)
        except (ConnectionResetError, ConnectionAbortedError):
            pass
        except urllib.error.URLError as error:
            if not isinstance(error, urllib.error.HTTPError) and isinstance(error.reason, ConnectionRefusedError):
                return
        time.sleep(0.25)
    raise ValueError('旧采集器尚未退出，请稍后重试。')


def disable(root=ROOT):
    check_owned(root)
    result = run('disable', service_name())
    if result.returncode:
        raise ValueError('未能禁用登录启动。')
    if run('print', service_name()).returncode == 0:
        if run('bootout', service_name()).returncode:
            raise ValueError('已禁用登录启动，但当前服务未能停止。')
    stop_current(root)
    return {'enabled': False, 'loaded': False}


def install(root=ROOT):
    if sys.platform != 'darwin':
        raise ValueError('后台服务仅支持 macOS。')
    root = Path(root).resolve()
    check_owned(root)
    if run('print', service_name()).returncode == 0:
        if run('bootout', service_name()).returncode:
            raise ValueError('未能停止已有后台服务。')
    stop_current(root)
    installed = stage_runtime(root)
    desired = launch_agent(installed)
    target = target_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    state = installed / '.state'
    state.mkdir(exist_ok=True, mode=0o700)
    logs = Path.home() / 'Library/Logs/QuotaPocket'
    logs.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in ('collector.log', 'collector-error.log'):
        fd = os.open(str(logs / name), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.close(fd)
    temporary = target.with_suffix('.plist.tmp')
    fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        plistlib.dump(desired, stream)
    os.replace(temporary, target)
    if run('enable', service_name()).returncode:
        raise ValueError('未能启用登录启动。')
    result = run('bootstrap', 'gui/' + str(os.getuid()), str(target))
    if result.returncode:
        raise ValueError('launchd 启动失败，请检查 macOS 对项目目录的访问权限。')
    for _ in range(40):
        try:
            value = request('/api/runtime', root)
            if value.get('managed'):
                if value.get('icloud', {}).get('enabled') and value['icloud'].get('error'):
                    raise ValueError('后台已启动，但 iCloud 文件不可读；请在 macOS 文件权限中授权后重试。')
                return {'enabled': True, 'loaded': True}
        except OSError:
            pass
        time.sleep(0.25)
    raise ValueError('后台进程尚未就绪；检查 collector-error.log 和项目目录访问权限。')


def trim_logs(directory, limit=2 * 1024 * 1024):
    # Keep the recent half in the same ordinary file; no recursive cleanup.
    for name in ('collector.log', 'collector-error.log'):
        path = Path(directory) / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size <= limit:
            continue
        with path.open('r+b') as stream:
            stream.seek(-limit // 2, os.SEEK_END)
            tail = stream.read()
            stream.seek(0)
            stream.write(tail)
            stream.truncate()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'status', 'stop', 'start', 'disable', 'restart'])
    args = parser.parse_args()
    if sys.platform != 'darwin':
        parser.exit(1, '后台服务管理目前仅支持 macOS；Windows 请使用 start-windows.cmd。\n')
    try:
        if args.action == 'status':
            print(json.dumps(status(), ensure_ascii=False))
            return
        (ROOT / '.state').mkdir(exist_ok=True, mode=0o700)
        with (ROOT / '.state/service-action.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            value = disable() if args.action in ('stop', 'disable') else install()
            print(json.dumps(value, ensure_ascii=False))
    except (ValueError, OSError, subprocess.SubprocessError, plistlib.InvalidFileException) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
