"""Quota adapters. No inference requests, transcript scans, or cost estimates."""
import concurrent.futures
import datetime as dt
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import queue
import re
import shutil
import socket
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from subscription_auth import LoginError, isolated_env, codex_command, managed_claude_token

ROOT = Path(__file__).resolve().parent
MAX_RESPONSE = 2_000_000


class SourceError(Exception):
    """Only sanitized, user-facing messages cross the adapter boundary."""

    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00', 'Z')


def stamp(value):
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return dt.datetime.fromtimestamp(value, dt.timezone.utc).isoformat().replace('+00:00', 'Z')
        if isinstance(value, str):
            parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is not None:
                return parsed.astimezone(dt.timezone.utc).isoformat().replace('+00:00', 'Z')
    except (ValueError, OverflowError, OSError):
        pass
    return None


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def short(value, default='', limit=80):
    return str(value if value is not None else default)[:limit]


def window(label, used=None, remaining=None, reset=None, key=None):
    used, remaining = number(used), number(remaining)
    if remaining is None and used is not None:
        remaining = 100 - used
    if remaining is not None:
        remaining = max(0, min(100, remaining))
    return {'id': short(key or label), 'label': short(label), 'remainingPercent': remaining,
            'resetAt': stamp(reset)}


def row(identity, name, source, app='', plan='', active=False):
    return {'id': identity, 'name': short(name), 'source': source, 'app': app,
            'plan': short(plan), 'active': bool(active), 'windows': [], 'balances': [],
            'lastSuccessAt': None, 'lastAttemptAt': now(), 'error': None, 'status': 'unknown'}


def finish(item, timestamp=None):
    has_value = any(w.get('remainingPercent') is not None for w in item['windows']) or bool(item['balances'])
    item['lastSuccessAt'] = stamp(timestamp) if timestamp is not None else now()
    item['status'] = 'ok' if has_value else 'unknown'
    if not has_value:
        item['error'] = '数据源没有返回可显示的额度；不会用消费金额推算。'
    return item


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def origin(url):
    p = urllib.parse.urlsplit(url)
    if p.username or p.password or not p.hostname:
        raise SourceError('查询地址不能包含账号密码，且必须是完整 URL。')
    try:
        port = p.port or (443 if p.scheme == 'https' else 80)
    except ValueError:
        raise SourceError('查询地址端口无效。')
    return p.scheme, p.hostname.lower(), port


def validate_query(url, base=None, local=False, allow_fake_ip=False):
    target = origin(url)
    if local:
        if target[0] not in ('http', 'https'):
            raise SourceError('数据源仅支持 HTTP / HTTPS。')
        if target[0] == 'http' and target[1] not in ('127.0.0.1', 'localhost', '::1'):
            raise SourceError('远端数据源必须使用 HTTPS。')
        return
    if target[0] != 'https':
        raise SourceError('Provider 额度查询仅支持 HTTPS。')
    if base is not None and origin(base) != target:
        raise SourceError('查询地址与配置的 Base URL 不同源；请在 CC Switch 中设置正确的查询 Base URL。')
    # A proxy's synthetic DNS range is opt-in and only valid for domain names.
    # Literal IP targets, loopback, metadata endpoints and RFC1918 stay blocked.
    try:
        literal = ipaddress.ip_address(target[1])
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        raise SourceError('Provider 查询不允许访问本地、内网或保留地址。')
    try:
        addresses = socket.getaddrinfo(target[1], target[2], type=socket.SOCK_STREAM)
        def accepted(address):
            ip = ipaddress.ip_address(address)
            synthetic = isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.ip_network('198.18.0.0/15')
            return ip.is_global or (allow_fake_ip and literal is None and synthetic)
        if not addresses or any(not accepted(a[4][0]) for a in addresses):
            raise SourceError('Provider 查询不允许访问本地、内网或保留地址。')
    except socket.gaierror:
        raise SourceError('无法解析 Provider 地址，请检查网络。')


def fetch_json(url, headers=None, base=None, local=False):
    validate_query(url, base=base, local=local, allow_fake_ip=os.environ.get('QUOTA_POCKET_FAKE_IP') == '1')
    clean = {'Accept': 'application/json', 'User-Agent': 'QuotaPocket/0.1'}
    for k, v in (headers or {}).items():
        if not isinstance(k, str) or not isinstance(v, str) or '\n' in k + v or '\r' in k + v:
            raise SourceError('查询请求头格式无效。')
        if k.lower() in ('host', 'connection', 'content-length', 'transfer-encoding', 'proxy-authorization'):
            raise SourceError('查询脚本包含不支持的请求头。')
        clean[k] = v
    try:
        request = urllib.request.Request(url, headers=clean)
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=12) as response:
            data = response.read(MAX_RESPONSE + 1)
        if len(data) > MAX_RESPONSE:
            raise SourceError('数据源响应过大。')
        return json.loads(data)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise SourceError('认证失效或权限不足，请在原工具中重新登录 / 检查查询凭证。', status_code=error.code)
        if error.code == 429:
            raise SourceError('数据源限流，稍后会重试。')
        if 300 <= error.code < 400:
            raise SourceError('数据源要求重定向；为防止凭证跨站转发，本次查询已停止。')
        raise SourceError('数据源返回 HTTP %s。' % error.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise SourceError('网络连接失败或超时；保留上次成功数据。')
    except (ValueError, UnicodeError):
        raise SourceError('数据源未返回有效 JSON。')


def sandbox(code, variables, stage, response=None):
    if not shutil.which('node') or not (ROOT / 'node_modules/quickjs-emscripten').exists():
        raise SourceError('查询脚本需要 Node.js 和依赖，请在项目目录运行 npm install --ignore-scripts。')
    for k, v in variables.items():
        escaped = json.dumps(str(v or ''), ensure_ascii=True)[1:-1].replace("'", '\\u0027').replace('`', '\\u0060').replace('$', '\\u0024')
        code = code.replace('{{' + k + '}}', escaped)
    try:
        result = subprocess.run([shutil.which('node'), str(ROOT / 'sandbox.mjs')],
                                input=json.dumps({'code': code, 'stage': stage, 'response': response}),
                                text=True, capture_output=True, timeout=5, cwd=str(ROOT))
        data = json.loads(result.stdout)
        if data.get('error') or 'result' not in data:
            raise SourceError('CC Switch 查询脚本执行失败或超过资源限制。')
        return data['result']
    except (subprocess.TimeoutExpired, ValueError, OSError):
        raise SourceError('CC Switch 查询脚本执行失败或超过资源限制。')


def cc_credentials(settings, script, app):
    env = settings.get('env') or {}
    options = settings.get('options') or {}
    base = settings.get('baseUrl') or settings.get('base_url') or options.get('baseURL') or env.get('ANTHROPIC_BASE_URL') or env.get('GOOGLE_GEMINI_BASE_URL') or ''
    key = settings.get('apiKey') or settings.get('api_key') or options.get('apiKey') or next((env.get(k) for k in ('ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_API_KEY', 'GEMINI_API_KEY', 'OPENROUTER_API_KEY') if env.get(k)), '')
    if app == 'codex':
        key = (settings.get('auth') or {}).get('OPENAI_API_KEY') or key
        config = settings.get('config') or ''
        # Use the selected TOML section; never take a different provider's URL.
        selected = re.search(r'^\s*model_provider\s*=\s*["\']([^"\']+)["\']', config, re.M)
        if selected:
            section = re.search(r'^\[model_providers\.' + re.escape(selected.group(1)) + r'\]\s*\n([^\[]*)', config, re.M)
            config = section.group(1) if section else ''
        match = re.search(r'^\s*base_url\s*=\s*["\']([^"\']+)["\']', config, re.M)
        base = match.group(1) if match else base
    return {'baseUrl': (script.get('baseUrl') or base).rstrip('/'), 'apiKey': script.get('apiKey') or key,
            'accessToken': script.get('accessToken') or '', 'userId': script.get('userId') or ''}


def cc_result(values, item):
    if isinstance(values, dict) and 'success' in values:
        if values.get('success') is False:
            raise SourceError('CC Switch 查询返回失败，请在原工具中测试查询。')
        values = values.get('data')
    values = values if isinstance(values, list) else [values]
    for entry in values:
        if not isinstance(entry, dict):
            continue
        if entry.get('isValid') is False:
            raise SourceError('Provider 报告账户或套餐不可用，请在原工具中检查。')
        value = number(entry.get('remaining'))
        unit = short(entry.get('unit'), 'credits', 16)
        label = short(entry.get('planName'), '账户余额')
        if unit == '%':
            item['windows'].append(window(label, remaining=value))
        elif value is not None:
            item['balances'].append({'label': label, 'value': value, 'unit': unit})
    return finish(item)


def cc_switch(config):
    mode = config.get('mode', 'independent')
    if mode == 'snapshot':
        return cc_snapshot(config)
    if mode == 'independent':
        return cc_switch_query(config)
    raise SourceError('未知的 CC Switch 读取模式；不会自动发起平台查询。')


def cc_snapshot_path(config):
    return Path(config.get('snapshotPath', '~/.cc-switch/quota-pocket.json')).expanduser()


def cc_snapshot(config):
    """Read an opt-in CC Switch cache export. Never execute scripts or HTTP here."""
    path = cc_snapshot_path(config)
    try:
        with path.open('rb') as stream:
            raw = stream.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError()
        packet = json.loads(raw)
        if (not isinstance(packet, dict) or packet.get('schemaVersion') != 1
                or packet.get('source') != 'cc-switch-usage-cache'
                or not isinstance(packet.get('entries'), list)):
            raise ValueError()
    except FileNotFoundError:
        raise SourceError('等待 CC Switch 导出快照。官方版尚无此入口，需要安装随项目提供的源码补丁；不会自动改为独立查询。')
    except (OSError, ValueError):
        raise SourceError('CC Switch 快照不可读或版本不兼容；保留原时间，不请求 Provider。')
    # Read only display metadata, never credentials or executable scripts.
    db_path = Path(config.get('path', '~/.cc-switch/cc-switch.db')).expanduser().resolve()
    metadata = {}
    try:
        with sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True, timeout=3) as db:
            for pid, app, name, active in db.execute('SELECT id, app_type, name, is_current FROM providers'):
                metadata[(app, pid)] = (name, active)
    except sqlite3.Error:
        raise SourceError('无法读取 CC Switch 展示配置；未查询平台或读取凭证。')
    result, seen = [], set()
    for entry in packet['entries']:
        if not isinstance(entry, dict):
            raise SourceError('CC Switch 快照条目格式无效。')
        kind, app = entry.get('kind'), entry.get('appType')
        captured = stamp(entry.get('observedAt'))
        if not captured or dt.datetime.fromisoformat(captured.replace('Z', '+00:00')).timestamp() > time.time() + 60:
            raise SourceError('CC Switch 快照缺少有效采集时间；不会将读取时间当作采集时间。')
        if not isinstance(app, str) or not isinstance(entry.get('success'), bool):
            raise SourceError('CC Switch 快照条目格式无效。')
        if kind == 'script':
            pid = entry.get('providerId')
            if not isinstance(pid, str):
                raise SourceError('CC Switch 快照缺少 Provider 标识。')
            if (app, pid) not in metadata:
                continue  # A removed provider must not survive in an old file.
            name, active = metadata[(app, pid)]
            uid = 'cc:' + hashlib.sha256((app + ':' + pid).encode()).hexdigest()[:16]
            item = row(uid, name, 'CC Switch · 缓存', app, active=active)
            data = entry.get('data')
            if not isinstance(data, list):
                raise SourceError('CC Switch 快照额度格式无效。')
            if entry['success']:
                try:
                    item = cc_result(data, item)
                except SourceError:
                    item.update(status='error', error='CC Switch 报告额度查询失败，请在原工具中检查。')
        elif kind in ('subscription', 'codex_oauth'):
            account = entry.get('accountId', '')
            if not isinstance(account, str):
                raise SourceError('CC Switch 快照账户标识无效。')
            uid = 'cc-sub:' + hashlib.sha256((kind + ':' + app + ':' + account).encode()).hexdigest()[:16]
            item = row(uid, {'claude': 'Claude', 'codex': 'Codex'}.get(app, app) + (' 托管订阅' if kind == 'codex_oauth' else ' 订阅'), 'CC Switch · 缓存', app)
            tiers = entry.get('tiers')
            if not isinstance(tiers, list) or any(not isinstance(t, dict) for t in tiers):
                raise SourceError('CC Switch 快照额度窗口无效。')
            labels = {'five_hour': '5 小时额度', 'seven_day': '每周额度', 'seven_day_opus': 'Opus 每周', 'seven_day_sonnet': 'Sonnet 每周'}
            item['windows'] = [window(labels.get(t.get('name'), short(t.get('name'), '额度窗口')), used=t.get('utilization'), reset=t.get('resetsAt')) for t in tiers]
            finish(item, captured)
        else:
            raise SourceError('CC Switch 快照包含不支持的条目类型。')
        if uid in seen:
            raise SourceError('CC Switch 快照包含重复账户。')
        seen.add(uid)
        item['lastAttemptAt'] = captured
        item['lastSuccessAt'] = captured if entry['success'] and item['status'] != 'error' else None
        if not entry['success']:
            item.update(status='error', error='CC Switch 报告额度查询失败，请在原工具中检查。')
        result.append(item)
    return result


def cc_switch_query(config):
    path = Path(config.get('path', '~/.cc-switch/cc-switch.db')).expanduser().resolve()
    if not path.is_file():
        raise SourceError('未找到 CC Switch 数据库。请先安装并配置 CC Switch。')
    try:
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=3) as db:
            db.row_factory = sqlite3.Row
            records = [dict(r) for r in db.execute('SELECT id, app_type, name, settings_config, meta, is_current FROM providers ORDER BY sort_index, created_at')]
    except sqlite3.Error:
        raise SourceError('CC Switch 数据库结构不兼容或暂时被锁定；未修改原数据库。')
    jobs = []
    for entry in records:
        try:
            meta = json.loads(entry.get('meta') or '{}')
            script = meta.get('usage_script') or meta.get('usageScript') or {}
            if not script.get('enabled'):
                continue
            uid = hashlib.sha256((entry['app_type'] + ':' + entry['id']).encode()).hexdigest()[:16]
            item = row('cc:' + uid, entry['name'], 'CC Switch', entry['app_type'], active=entry['is_current'])
            jobs.append((entry, script, item))
        except (ValueError, TypeError):
            continue
    def query(job):
        entry, script, item = job
        try:
            code = script.get('code') or ''
            if not code:
                raise SourceError('此 Provider 使用原生模板，尚无可复用脚本；请用 CodexBar 或配置 CC Switch 查询脚本。')
            variables = cc_credentials(json.loads(entry['settings_config']), script, entry['app_type'])
            req = sandbox(code, variables, 'request')
            if not isinstance(req, dict) or str(req.get('method', 'GET')).upper() != 'GET':
                raise SourceError('第一版仅执行只读 GET 额度查询。')
            if not variables['baseUrl']:
                raise SourceError('请在 CC Switch 的查询配置中填写 Base URL，以校验请求来源。')
            result = fetch_json(req.get('url', ''), req.get('headers'), base=variables['baseUrl'])
            return cc_result(sandbox(code, variables, 'extract', result), item)
        except SourceError as error:
            item.update(status='error', error=str(error))
        except Exception:
            item.update(status='error', error='查询配置格式不兼容；请在 CC Switch 中检查。')
        return item
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        return list(pool.map(query, jobs))


def normalize_codexbar(payload):
    dashboard = isinstance(payload, dict) and 'providers' in payload
    if dashboard and payload.get('schemaVersion') != 1:
        raise SourceError('CodexBar 快照版本不兼容，需要 schemaVersion 1。')
    entries = payload.get('providers', []) if dashboard else payload
    if not isinstance(entries, list):
        raise SourceError('CodexBar 返回了不支持的数据结构。')
    output = []
    for index, provider in enumerate(entries):
        if not isinstance(provider, dict):
            continue
        kind = provider.get('id') or provider.get('provider') or 'unknown'
        # Subscription quotas only. Deliberately never project cost, pace or transcripts.
        if kind not in ('claude', 'codex'):
            continue
        accounts = provider.get('accounts') or [provider]
        for ai, account in enumerate(accounts):
            usage = account if dashboard else (account.get('usage') or {})
            identity = account.get('identity') or usage.get('identity') or {}
            identifier = short(account.get('id') or account.get('account') or ai)
            rid = 'bar:' + kind + ':' + hashlib.sha256((str(index) + ':' + identifier).encode()).hexdigest()[:12]
            item = row(rid, 'Claude' if kind == 'claude' else 'Codex', 'CodexBar', kind,
                       identity.get('plan') or identity.get('planName') or '', account.get('active', False))
            raw_windows = usage.get('windows') if dashboard else None
            if raw_windows is None:
                raw_windows = []
                for k, label in [('primary', '当前窗口'), ('secondary', '每周额度'), ('tertiary', '额外窗口')]:
                    v = usage.get(k)
                    if isinstance(v, dict):
                        raw_windows.append(dict(v, kind=k, label=label))
                raw_windows.extend(usage.get('extraRateWindows') or [])
            for w in raw_windows:
                if isinstance(w, dict) and not w.get('idle'):
                    item['windows'].append(window(w.get('label') or w.get('title') or w.get('kind') or '额度', w.get('usedPercent'), w.get('remainingPercent'), w.get('resetAt') or w.get('resetsAt'), w.get('kind')))
            credit = account.get('credits') or {}
            amount = number(credit.get('remaining', credit.get('balance')))
            if amount is not None:
                item['balances'].append({'label': '额外额度', 'value': amount, 'unit': short(credit.get('unit'), 'credits', 16)})
            finish(item, account.get('updatedAt') or usage.get('updatedAt') or (payload.get('generatedAt') if dashboard else None))
            if account.get('error') or provider.get('error'):
                item.update(status='error', error='CodexBar 查询失败；请在 CodexBar 中检查登录状态。')
            output.append(item)
    return output


def codexbar(config):
    mode = config.get('mode', 'cli')
    if mode == 'http':
        base = config.get('url', 'http://127.0.0.1:8080').rstrip('/')
        token = os.environ.get(config.get('tokenEnv', 'CODEXBAR_DASHBOARD_TOKEN'), '')
        if not token:
            raise SourceError('请设置 CODEXBAR_DASHBOARD_TOKEN 环境变量，再启动采集器。')
        payload = fetch_json(base + '/dashboard/v1/snapshot', {'Authorization': 'Bearer ' + token}, local=True)
        return normalize_codexbar(payload)
    executable = shutil.which('codexbar')
    if not executable:
        candidate = Path('/Applications/CodexBar.app/Contents/Helpers/CodexBarCLI')
        executable = str(candidate) if candidate.is_file() else None
    if not executable:
        raise SourceError('未检测到 CodexBar CLI。请先安装 CodexBar，并在设置中安装 CLI。')
    output = []
    for kind in ('codex', 'claude'):
        try:
            # Explicit OAuth avoids browser-cookie harvesting and PTY session side effects.
            result = subprocess.run([executable, 'usage', '--provider', kind, '--source', 'oauth', '--format', 'json'], capture_output=True, timeout=25, text=True)
            if len(result.stdout) > MAX_RESPONSE:
                raise ValueError()
            output.extend(normalize_codexbar(json.loads(result.stdout)))
        except (OSError, ValueError, subprocess.TimeoutExpired, SourceError):
            item = row('bar-error:' + kind, kind.title(), 'CodexBar', kind)
            item.update(status='error', error='CodexBar 未返回订阅额度，请在原应用中检查 OAuth 登录或 CLI 版本。')
            output.append(item)
    return output


def codex_native(config):
    executable = shutil.which('codex')
    if not executable:
        raise SourceError('未检测到 Codex CLI。请先安装并登录 ChatGPT 订阅。')
    env = isolated_env('codex', config['home']) if config.get('managed') else os.environ.copy()
    if config.get('home'):
        env['CODEX_HOME'] = str(Path(config['home']).expanduser())
    command = codex_command(executable) if config.get('managed') else [executable, 'app-server']
    process = subprocess.Popen(command, cwd=config.get('home') if config.get('managed') else None, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env)
    inbox = queue.Queue(maxsize=1024)
    def read():
        try:
            while True:
                line = process.stdout.readline(MAX_RESPONSE + 1)
                if not line:
                    break
                if len(line) > MAX_RESPONSE:
                    break
                try:
                    inbox.put(json.loads(line), timeout=1)
                except (ValueError, queue.Full):
                    pass
        finally:
            try: inbox.put(None, timeout=1)
            except queue.Full: pass
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    deadline = time.monotonic() + 20
    def call(method, identifier, params=None):
        request = {'method': method, 'id': identifier, 'params': params if params is not None else {}}
        process.stdin.write(json.dumps(request) + '\n')
        process.stdin.flush()
        while True:
            timeout = deadline - time.monotonic()
            if timeout <= 0:
                raise SourceError('Codex 额度读取超时。')
            try: message = inbox.get(timeout=timeout)
            except queue.Empty: raise SourceError('Codex 额度读取超时。')
            if message is None:
                raise SourceError('Codex App Server 已退出，请检查 CLI 版本和登录。')
            if message.get('id') == identifier:
                if message.get('error'):
                    if config.get('managed'): raise SourceError('独立 ChatGPT 订阅额度读取失败，请在电脑端重新连接订阅；若持续失败，请检查 Codex CLI 版本。')
                    raise SourceError('Codex 无法读取订阅额度，请确认当前是 ChatGPT 登录而非 API Key 模式。')
                return message.get('result') or {}
    try:
        call('initialize', 1, {'clientInfo': {'name': 'quota_pocket', 'version': '0.1.0'}})
        process.stdin.write('{"method":"initialized"}\n'); process.stdin.flush()
        account = call('account/read', 2).get('account') or {}
        if account.get('type') != 'chatgpt':
            if config.get('managed'): raise SourceError('独立 ChatGPT 登录已失效，请在电脑端点击“连接 ChatGPT 订阅”。')
            raise SourceError('当前 Codex 使用 API Key 或未登录订阅。请在“连接数据源”点击“连接 ChatGPT 订阅”独立授权；勾选采集开关不会完成登录。')
        payload = call('account/rateLimits/read', 3)
        item = row('native:codex', 'ChatGPT 订阅', '独立订阅' if config.get('managed') else 'Codex CLI', 'codex', account.get('planType', ''))
        buckets = payload.get('rateLimitsByLimitId') or {'codex': payload.get('rateLimits') or {}}
        for bucket, values in buckets.items():
            for key in ('primary', 'secondary'):
                w = values.get(key)
                if not isinstance(w, dict): continue
                duration = number(w.get('windowDurationMins'))
                label = ('每周额度' if duration == 10080 else '5 小时额度' if duration == 300 else '%g 分钟额度' % duration if duration else '额度窗口')
                if bucket != 'codex': label = short(values.get('limitName') or bucket) + ' · ' + label
                item['windows'].append(window(label, w.get('usedPercent'), reset=w.get('resetsAt'), key=bucket + ':' + key))
        return [finish(item)]
    except (BrokenPipeError, OSError):
        raise SourceError('Codex App Server 启动失败。')
    finally:
        try: process.stdin.close()
        except OSError: pass
        try: process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.terminate()
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
        reader.join(timeout=1)
        process.stdout.close()


def claude_native(config):
    if config.get('managed'):
        try: token = managed_claude_token(config['path'])
        except LoginError as error: raise SourceError(str(error))
    else: token = os.environ.get('CLAUDE_QUOTA_OAUTH_TOKEN', '')
    if not token:
        path = Path(config.get('path', '~/.claude/.credentials.json')).expanduser()
        if not path.is_file():
            raise SourceError('尚未连接可读取的 Claude 订阅。请在“连接数据源”点击“连接 Claude 订阅”独立授权；勾选采集开关不会完成登录。已有 CodexBar 用户也可启用该数据源。')
        try:
            oauth = json.loads(path.read_text()).get('claudeAiOauth') or {}
            token = oauth.get('accessToken') or ''
            scopes = oauth.get('scopes') or []
            if scopes and 'user:profile' not in scopes:
                raise SourceError('Claude OAuth 缺少 user:profile 权限，不能读取订阅额度。')
        except (ValueError, OSError):
            raise SourceError('Claude 凭证文件无法读取。')
    if not token:
        raise SourceError('没有可用的 Claude 订阅 OAuth Token。API Key 不适用于此接口。')
    try:
        payload = fetch_json('https://api.anthropic.com/api/oauth/usage', {'Authorization': 'Bearer ' + token, 'anthropic-beta': 'oauth-2025-04-20'})
    except SourceError as error:
        if config.get('managed') and error.status_code in (401,403):
            raise SourceError('独立 Claude 授权失效或权限不足，请在电脑端点击“连接 Claude 订阅”，无需更改 Claude Code。')
        raise
    item = row('native:claude', 'Claude 订阅', '独立订阅' if config.get('managed') else 'Claude OAuth', 'claude')
    for key, value in payload.items():
        if isinstance(value, dict) and (key == 'five_hour' or key.startswith('seven_day')):
            label = {'five_hour': '5 小时额度', 'seven_day': '每周额度', 'seven_day_sonnet': 'Sonnet · 每周', 'seven_day_opus': 'Opus · 每周'}.get(key, key)
            item['windows'].append(window(label, value.get('utilization'), reset=value.get('resets_at'), key=key))
    return [finish(item)]


ADAPTERS = {'cc-switch': cc_switch, 'codexbar': codexbar, 'codex': codex_native, 'claude': claude_native}
