"""Private iCloud Drive transport for the Scriptable widget.

Only the quota projection passed by Store is written. Provider credentials and
collector configuration never enter this module.
"""
import datetime as dt
import json
import math
import os
from pathlib import Path
import platform
import re
import socket
import threading
import uuid


SCRIPTABLE_DOCUMENTS = Path.home() / 'Library/Mobile Documents/iCloud~dk~simonbs~Scriptable/Documents'
MANAGED_MARKER = '// Quota Pocket managed iCloud script:'


class ICloudError(ValueError):
    pass


def scriptable_documents(system=None, home=None, environment=None):
    """Resolve exact container paths only; never create or scan a cloud root."""
    environment = os.environ if environment is None else environment
    override = environment.get('QUOTA_POCKET_ICLOUD_DIR')
    if override:
        path = Path(override).expanduser()
        if not path.is_absolute() or not path.is_dir():
            raise ICloudError('QUOTA_POCKET_ICLOUD_DIR 必须是已存在的 Scriptable 容器绝对路径。')
        return path
    system = platform.system() if system is None else system
    if system == 'Windows':
        home = Path(home) if home is not None else Path.home()
        return home / 'iCloudDrive/iCloud~dk~simonbs~Scriptable'
    return SCRIPTABLE_DOCUMENTS


def _private_json(path, value):
    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    temporary = path.with_name(path.name + '.tmp')
    fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    os.chmod(path, 0o600)


def _atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '.quota-pocket.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _text(value, limit):
    return value[:limit] if isinstance(value, str) and value else None


def _number(value, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    if minimum is not None and value < minimum:
        return None
    if maximum is not None and value > maximum:
        return None
    return value


def _timestamp(value):
    if not isinstance(value, str) or not value or len(value) > 64:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return value if parsed.tzinfo is not None else None


def quota_projection(snapshot):
    """Return the complete, explicit set of fields allowed to leave the Mac."""
    if not isinstance(snapshot, dict):
        snapshot = {}
    result = {'schemaVersion': 1, 'demo': False, 'providers': []}
    for key in ('generatedAt', 'lastCollectionAt'):
        value = _timestamp(snapshot.get(key))
        if value is not None:
            result[key] = value
    for key in ('intervalSeconds', 'staleAfterSeconds'):
        value = _number(snapshot.get(key), 0)
        if value is not None:
            result[key] = value
    refresh = snapshot.get('refreshRequest')
    if isinstance(refresh, dict) and isinstance(refresh.get('id'), str) and re.fullmatch(r'[A-Za-z0-9_-]{16,100}', refresh['id']):
        if refresh.get('state') in ('waiting', 'collecting', 'complete'):
            clean_refresh = {'id': refresh['id'], 'state': refresh['state']}
            for key in ('receivedAt', 'completedAt'):
                timestamp = _timestamp(refresh.get(key))
                if timestamp is not None:
                    clean_refresh[key] = timestamp
            result['refreshRequest'] = clean_refresh
    providers = snapshot.get('providers')
    if not isinstance(providers, list):
        return result
    for provider in providers[:500]:
        if not isinstance(provider, dict):
            continue
        identifier, name = _text(provider.get('id'), 200), _text(provider.get('name'), 200)
        if identifier is None or name is None:
            continue
        clean = {'id': identifier, 'name': name, 'windows': [], 'balances': []}
        for key, limit in (('app', 32), ('plan', 100)):
            value = _text(provider.get(key), limit)
            if value is not None:
                clean[key] = value
        if isinstance(provider.get('active'), bool):
            clean['active'] = provider['active']
        status = provider.get('status')
        if status in ('ok', 'unknown', 'error', 'stale'):
            clean['status'] = status
        for key in ('lastSuccessAt', 'lastAttemptAt'):
            value = _timestamp(provider.get(key))
            if value is not None:
                clean[key] = value
        windows = provider.get('windows')
        if isinstance(windows, list):
            for item in windows[:20]:
                if not isinstance(item, dict):
                    continue
                label = _text(item.get('label'), 100)
                if label is None:
                    continue
                window = {'label': label}
                identifier = _text(item.get('id'), 100)
                if identifier is not None:
                    window['id'] = identifier
                remaining = item.get('remainingPercent')
                if remaining is None:
                    window['remainingPercent'] = None
                else:
                    remaining = _number(remaining, 0, 100)
                    if remaining is not None:
                        window['remainingPercent'] = remaining
                reset = _timestamp(item.get('resetAt'))
                if reset is not None:
                    window['resetAt'] = reset
                clean['windows'].append(window)
        balances = provider.get('balances')
        if isinstance(balances, list):
            for item in balances[:20]:
                if not isinstance(item, dict):
                    continue
                label = _text(item.get('label'), 100)
                value = _number(item.get('value'))
                unit = _text(item.get('unit'), 32)
                if label is not None and value is not None and unit is not None:
                    clean['balances'].append({'label': label, 'value': value, 'unit': unit})
        result['providers'].append(clean)
    if type(snapshot.get('mobileSelectionVersion')) is int and snapshot['mobileSelectionVersion'] == 1:
        # Project candidates independently through the same scalar allowlist.
        candidates = quota_projection({'providers': snapshot.get('availableProviders')})['providers']
        allowed = {p['id'] for p in candidates}
        defaults = snapshot.get('defaultProviderIds')
        defaults = defaults if isinstance(defaults, list) else []
        defaults = list(dict.fromkeys(uid for uid in defaults if isinstance(uid, str) and uid in allowed))
        result.update(mobileSelectionVersion=1, availableProviders=candidates, defaultProviderIds=defaults)
        result['providers'] = [p for p in result['providers'] if p['id'] in allowed]
    return result


class ICloudSync:
    def __init__(self, state_dir, template_path, documents=None, device_name=None):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.template_path = Path(template_path)
        self.documents = Path(documents) if documents is not None else scriptable_documents()
        self.state_path = self.state_dir / 'icloud.json'
        self.lock = threading.RLock()
        self.state = self._load_state(device_name)
        # An explicit transport destination belongs to this installation state.
        # Reloading a test installation must never fall back to real iCloud.
        saved_documents = self.state.get('documentsDirectory')
        if documents is not None:
            self.documents = Path(documents).resolve()
            self.state['documentsDirectory'] = str(self.documents)
            _private_json(self.state_path, self.state)
        elif saved_documents and not os.environ.get('QUOTA_POCKET_ICLOUD_DIR'):
            self.documents = Path(saved_documents)

    def _load_state(self, device_name):
        try:
            saved = json.loads(self.state_path.read_text(encoding='utf-8'))
        except (OSError, ValueError, TypeError):
            saved = {}
        identifier = saved.get('deviceId')
        try:
            identifier = str(uuid.UUID(identifier))
        except (ValueError, TypeError, AttributeError):
            identifier = str(uuid.uuid4())
        name = saved.get('deviceName')
        if not isinstance(name, str) or not name.strip():
            name = device_name or platform.node() or socket.gethostname() or 'Computer'
        enabled = saved.get('enabled', False)
        # Invalid state must fail closed; strings such as "false" are truthy.
        if not isinstance(enabled, bool):
            enabled = False
        state = {
            'enabled': enabled,
            'deviceId': identifier,
            'deviceName': name.strip()[:100],
            'lastExportAt': saved.get('lastExportAt') if isinstance(saved.get('lastExportAt'), str) else None,
            'error': None,
        }
        saved_documents = saved.get('documentsDirectory')
        if isinstance(saved_documents, str) and Path(saved_documents).is_absolute():
            state['documentsDirectory'] = saved_documents
        _private_json(self.state_path, state)
        return state

    @property
    def relative_snapshot_path(self):
        return 'QuotaPocket/%s/snapshot.json' % self.state['deviceId']

    @property
    def script_name(self):
        return 'Quota Pocket iCloud %s.js' % self.state['deviceId'][:8]

    def available(self):
        return self.documents.is_dir() and self.template_path.is_file()

    def read_refresh_request(self):
        # The phone can request only a rate-limited read, never change sources,
        # credentials or providers. Ignore malformed/expired cloud files.
        with self.lock:
            if not self.state['enabled']:
                return None
            path = self.documents / 'QuotaPocket' / self.state['deviceId'] / 'refresh-request.json'
            try:
                if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024:
                    return None
                value = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(value, dict) or value.get('schemaVersion') != 1:
                    return None
                if value.get('installationId') != self.state['deviceId']:
                    return None
                if not isinstance(value.get('id'), str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,100}', value['id']):
                    return None
                issued = _timestamp(value.get('issuedAt'))
                if issued is None:
                    return None
                age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(issued.replace('Z', '+00:00'))).total_seconds()
                return value if -60 <= age <= 600 else None
            except (OSError, ValueError, TypeError):
                return None

    def status(self):
        with self.lock:
            return {
                'available': self.available(),
                'enabled': self.state['enabled'],
                'installationId': self.state['deviceId'],
                'deviceId': self.state['deviceId'],
                'deviceName': self.state['deviceName'],
                'scriptName': self.script_name,
                'lastExportAt': self.state['lastExportAt'],
                'error': self.state['error'],
                'directory': str(self.documents),
            }

    def _script_text(self):
        source = self.template_path.read_text(encoding='utf-8')
        declaration = (
            "const ICLOUD_SOURCE = {installationId: %s, relativePath: %s};\n" %
            (json.dumps(self.state['deviceId']), json.dumps(self.relative_snapshot_path))
        )
        marker = '%s %s\n' % (MANAGED_MARKER, self.state['deviceId'])
        lines = source.splitlines(keepends=True)
        insert_at = 0
        while insert_at < len(lines) and insert_at < 2 and lines[insert_at].lstrip().startswith('//'):
            insert_at += 1
        lines[insert_at:insert_at] = [marker, declaration]
        return ''.join(lines)

    def _install_script(self):
        target = self.documents / self.script_name
        desired = self._script_text()
        if target.exists():
            if not target.is_file():
                raise ICloudError('同名 Scriptable 项目不是普通文件，未做覆盖。')
            try:
                existing = target.read_text(encoding='utf-8')
            except OSError as error:
                raise ICloudError('无法检查已有 Scriptable 脚本。') from error
            expected = '%s %s' % (MANAGED_MARKER, self.state['deviceId'])
            if expected not in existing.splitlines()[:6]:
                raise ICloudError('同名 Scriptable 脚本不属于 Quota Pocket，未做覆盖。')
            if existing == desired:
                return
        _atomic_text(target, desired)

    def configure(self, enabled, snapshot_supplier):
        if not isinstance(enabled, bool):
            raise ICloudError('iCloud 开关无效。')
        if not callable(snapshot_supplier):
            raise ICloudError('额度快照来源无效。')
        with self.lock:
            if enabled:
                if not self.available():
                    raise ICloudError('未找到 Scriptable 的 iCloud Drive 文件夹。')
                try:
                    self._install_script()
                    self._export(snapshot_supplier())
                except (ICloudError, OSError, ValueError, TypeError) as error:
                    self.state['error'] = str(error) or 'iCloud 写入失败。'
                    _private_json(self.state_path, self.state)
                    raise ICloudError(self.state['error']) from error
            self.state['enabled'] = enabled
            self.state['error'] = None
            _private_json(self.state_path, self.state)
            return self.status()

    def _export(self, snapshot):
        target = self.documents / self.relative_snapshot_path
        packet = quota_projection(snapshot)
        _atomic_text(target, json.dumps(packet, ensure_ascii=False, indent=2, allow_nan=False))
        self.state['lastExportAt'] = dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00', 'Z')

    def export(self, snapshot_supplier):
        """Best-effort export: collection must keep working if iCloud is unavailable."""
        if not callable(snapshot_supplier):
            return False
        with self.lock:
            if not self.state['enabled']:
                return False
            try:
                if not self.available():
                    raise ICloudError('Scriptable 的 iCloud Drive 文件夹当前不可用。')
                self._install_script()
                self._export(snapshot_supplier())
                self.state['error'] = None
                _private_json(self.state_path, self.state)
                return True
            except (ICloudError, OSError, ValueError, TypeError) as error:
                self.state['error'] = str(error) or 'iCloud 写入失败。'
                _private_json(self.state_path, self.state)
                return False
