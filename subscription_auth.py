"""Isolated subscription login. Never opens the desktop tools' credential stores."""
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request


class LoginError(Exception):
    pass


def private_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.pending-' + secrets.token_hex(6))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False)
    os.replace(temporary, path)


def isolated_env(kind, directory):
    # Keep OS and network settings, not inherited API keys, alternate providers,
    # credential helpers, CLI sessions, or project-specific environment.
    allowed = {'PATH', 'HOME', 'USER', 'LOGNAME', 'TMPDIR', 'TEMP', 'TMP', 'SYSTEMROOT',
               'APPDATA', 'LOCALAPPDATA', 'LANG', 'LC_ALL', 'SSL_CERT_FILE', 'SSL_CERT_DIR',
               'NODE_EXTRA_CA_CERTS', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
               'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'}
    env = {k: v for k, v in os.environ.items() if k in allowed}
    env.update(NO_COLOR='1', TERM='dumb')
    if kind == 'codex': env['CODEX_HOME'] = str(directory)
    else:
        env['CLAUDE_CONFIG_DIR'] = str(directory)
        env['CLAUDE_SECURESTORAGE_CONFIG_DIR'] = str(directory)
        env['CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC'] = '1'
    return env


def codex_command(executable):
    return [executable, '-c', 'cli_auth_credentials_store="file"',
            '-c', 'forced_login_method="chatgpt"', '-c', 'model_provider="openai"', 'app-server']


def trusted_auth_url(kind, value):
    if not isinstance(value, str) or len(value) > 12000: return False
    p = urllib.parse.urlsplit(value)
    hosts = {'auth.openai.com'} if kind == 'codex' else {'claude.ai', 'claude.com', 'platform.claude.com', 'console.anthropic.com'}
    return p.scheme == 'https' and p.hostname in hosts and not p.username and not p.password and p.port in (None, 443)


class CodexSession:
    def __init__(self, executable, directory):
        self.process = subprocess.Popen(codex_command(executable), cwd=directory,
            env=isolated_env('codex', directory), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True)
        self.inbox = queue.Queue(maxsize=1024)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            for line in self.process.stdout:
                if len(line) > 2_000_000: break
                try: self.inbox.put(json.loads(line), timeout=1)
                except (ValueError, queue.Full): pass
        finally:
            try: self.inbox.put(None, timeout=1)
            except queue.Full: pass

    def send(self, method, identifier=None, params=None):
        message = {'method': method}
        if identifier is not None: message['id'] = identifier
        if params is not None or identifier is not None: message['params'] = params if params is not None else {}
        self.process.stdin.write(json.dumps(message) + '\n'); self.process.stdin.flush()

    def receive(self, timeout):
        try: value = self.inbox.get(timeout=timeout)
        except queue.Empty: raise LoginError('登录响应超时，请重试。')
        if value is None: raise LoginError('Codex 登录进程已退出，请检查 CLI 版本或网络。')
        return value

    def call(self, method, identifier, params=None):
        self.send(method, identifier, params)
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            value = self.receive(max(.01, deadline-time.monotonic()))
            if value.get('id') == identifier:
                if value.get('error'): raise LoginError('Codex 登录接口未成功响应，请检查 CLI 版本；若正在启动浏览器登录，也请检查 1455 端口是否被占用。')
                return value.get('result') or {}
        raise LoginError('Codex 登录响应超时。')

    def close(self):
        stop_process(self.process)
        self.reader.join(timeout=1)
        if self.process.stdout: self.process.stdout.close()


def stop_process(process):
    if process is None: return
    if process.poll() is None:
        process.terminate()
        try: process.wait(timeout=3)
        except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=3)
    if process.stdin:
        try: process.stdin.close()
        except OSError: pass


def read_claude_login_credentials(directory):
    """Called only after this app's explicit login, never from a quota poll."""
    path = Path(directory) / '.credentials.json'
    if path.is_file():
        data = json.loads(path.read_text())
    elif sys.platform == 'darwin':
        suffix = hashlib.sha256(unicodedata.normalize('NFC', str(directory)).encode()).hexdigest()[:8]
        service = 'Claude Code-credentials-' + suffix
        result = subprocess.run(['/usr/bin/security', 'find-generic-password', '-w', '-s', service],
                                capture_output=True, text=True, timeout=30)
        if result.returncode: raise LoginError('请允许读取额度口袋专属的 Claude 登录凭证，然后重新连接。不会读取默认 Claude Code 条目。')
        data = json.loads(result.stdout)
    else:
        raise LoginError('Claude CLI 没有在独立目录保存可读取的订阅凭证，请更新 CLI 后重试。')
    oauth = data.get('claudeAiOauth') or {}
    if not isinstance(oauth.get('accessToken'), str) or not oauth['accessToken']:
        raise LoginError('Claude 未返回订阅登录凭证，请选择 Claude 订阅账户。')
    if 'user:profile' not in (oauth.get('scopes') or []):
        raise LoginError('Claude 登录缺少 user:profile 权限，无法读取订阅额度。请使用订阅登录，不要使用 setup-token。')
    return {k: oauth[k] for k in ('accessToken', 'refreshToken', 'expiresAt', 'scopes', 'subscriptionType') if k in oauth}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None


def refresh_claude(oauth):
    body = urllib.parse.urlencode({'grant_type':'refresh_token', 'refresh_token':oauth['refreshToken'],
                                 'client_id':'9d1c250a-e61b-44d9-88ed-5944d1962f5e'}).encode()
    request = urllib.request.Request('https://platform.claude.com/v1/oauth/token', data=body,
                                    headers={'Content-Type':'application/x-www-form-urlencoded', 'Accept':'application/json'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
            raw = response.read(1_000_001)
            if len(raw) > 1_000_000: raise ValueError()
            result = json.loads(raw)
        if not isinstance(result.get('access_token'), str) or not result['access_token']: raise ValueError()
        seconds = float(result.get('expires_in', 0))
        if not 0 < seconds < 366*86400: raise ValueError()
        updated = dict(oauth, accessToken=result['access_token'], expiresAt=int((time.time()+seconds)*1000))
        if isinstance(result.get('refresh_token'), str) and result['refresh_token']: updated['refreshToken'] = result['refresh_token']
        if isinstance(result.get('scope'), str): updated['scopes'] = result['scope'].split()
        if 'user:profile' not in updated.get('scopes', []): raise LoginError('Claude 授权缺少额度读取权限，请重新连接订阅。')
        return updated
    except urllib.error.HTTPError as error:
        if error.code in (400, 401, 403): raise LoginError('Claude 订阅授权已失效，请在电脑端重新连接。')
        raise LoginError('Claude 登录续期服务暂不可达，稍后重试。')
    except (OSError, ValueError, TypeError): raise LoginError('Claude 登录续期失败，稍后重试或重新连接。')


_credential_locks = {}
_credential_guard = threading.Lock()


def managed_claude_token(path):
    with _credential_guard: lock = _credential_locks.setdefault(str(path), threading.Lock())
    with lock:
        try: oauth = json.loads(Path(path).read_text()).get('claudeAiOauth') or {}
        except (ValueError, OSError): raise LoginError('独立 Claude 凭证不可读取，请重新连接订阅。')
        if not oauth.get('accessToken'): raise LoginError('尚未连接 Claude 订阅。')
        if 'user:profile' not in oauth.get('scopes', []): raise LoginError('Claude 授权缺少额度读取权限，请重新连接订阅。')
        expires = oauth.get('expiresAt')
        if isinstance(expires, (int, float)) and expires <= (time.time()+60)*1000:
            if not oauth.get('refreshToken'): raise LoginError('Claude 登录已过期，请重新连接订阅。')
            oauth = refresh_claude(oauth)
            private_json(path, {'claudeAiOauth':oauth})
        return oauth['accessToken']


class SubscriptionLogins:
    def __init__(self, directory, on_connected):
        self.directory = Path(directory).resolve()
        self.on_connected = on_connected
        self.lock = threading.RLock()
        self.jobs = {}

    def statuses(self):
        with self.lock:
            return {k:{field:job.get(field) for field in ('id','state','authUrl','message')} for k,job in self.jobs.items()}

    def start(self, kind):
        if kind not in ('codex','claude'): raise LoginError('未知订阅类型。')
        executable = shutil.which(kind)
        if not executable: raise LoginError('请先安装 ' + ('Codex CLI' if kind=='codex' else 'Claude Code') + '，然后再连接订阅。')
        with self.lock:
            old = self.jobs.get(kind)
            if old and old['state'] in ('starting','waiting','saving'): return self.statuses()[kind]
            attempt = self.directory / kind / secrets.token_hex(12)
            attempt.mkdir(parents=True, mode=0o700)
            for p in (attempt, attempt.parent, self.directory): os.chmod(p, 0o700)
            job = {'id':secrets.token_urlsafe(24), 'state':'starting', 'message':'正在启动独立登录…',
                   'authUrl':None, 'directory':attempt, 'cancel':threading.Event(), 'process':None}
            self.jobs[kind] = job
            threading.Thread(target=self._run, args=(kind,executable,job), daemon=True).start()
            return self.statuses()[kind]

    def _set(self, kind, job, **values):
        with self.lock:
            if self.jobs.get(kind) is job and not job['cancel'].is_set(): job.update(values)

    def _run(self, kind, executable, job):
        try:
            if kind == 'codex': config = self._codex(executable,job)
            else: config = self._claude(executable,job)
            with self.lock:
                if job['cancel'].is_set() or self.jobs.get(kind) is not job: return
                self.on_connected(kind, config)
                job.update(state='connected', authUrl=None, message='独立订阅已连接，正在读取额度。可到“手机小组件”勾选展示。')
        except Exception as error:
            message = str(error) if isinstance(error, LoginError) else '登录未完成，请重试。原有工具的登录与 Provider 配置未更改。'
            self._set(kind,job,state='error',authUrl=None,message=message)
        finally:
            stop_process(job.get('process'))

    def _codex(self, executable, job):
        directory=job['directory']
        session = CodexSession(executable,directory);job['process']=session.process
        try:
            session.call('initialize',1,{'clientInfo':{'name':'quota_pocket','version':'0.1.0'}})
            session.send('initialized')
            result=session.call('account/login/start',2,{'type':'chatgpt'})
            url=result.get('authUrl');login_id=result.get('loginId')
            if not trusted_auth_url('codex',url) or not login_id: raise LoginError('Codex 未返回有效的官方授权链接，请更新 CLI 后重试。')
            self._set('codex',job,state='waiting',authUrl=url,message='打开官方登录页，使用 ChatGPT 订阅账户授权。请在这台电脑的浏览器完成。')
            deadline=time.monotonic()+600
            while time.monotonic()<deadline and not job['cancel'].is_set():
                try: value=session.receive(1)
                except LoginError:
                    if session.process.poll() is not None: raise
                    continue
                if value.get('method')=='account/login/completed' and value.get('params',{}).get('loginId')==login_id:
                    if not value['params'].get('success'): raise LoginError('ChatGPT 授权未完成，请重新连接。')
                    account=session.call('account/read',3).get('account') or {}
                    if account.get('type')!='chatgpt' or not (directory/'auth.json').is_file(): raise LoginError('没有收到独立的 ChatGPT 订阅凭证，请重试。')
                    os.chmod(directory/'auth.json',0o600)
                    return {'managed':True,'home':str(directory),'enabled':True}
            raise LoginError('登录已取消或超过 10 分钟，请重新开始。')
        finally: session.close()

    def _claude(self, executable, job):
        directory=job['directory'];cli=directory/'cli';cli.mkdir(mode=0o700)
        process=subprocess.Popen([executable,'auth','login','--claudeai'],cwd=cli,
            env=isolated_env('claude',cli),stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,text=True,bufsize=1)
        job['process']=process
        def read():
            for line in iter(lambda:process.stdout.readline(16384),''):
                # CLI output is inspected in memory only. Never relay raw stdout/stderr.
                for url in re.findall(r'https://[^\s\x1b\x07<>"\']+',line):
                    try: valid=trusted_auth_url('claude',url)
                    except ValueError: valid=False
                    if valid:
                        self._set('claude',job,state='waiting',authUrl=url,message='在官方页面登录 Claude 订阅。浏览器若显示授权码，可粘贴到下方完成。')
        reader=threading.Thread(target=read,daemon=True);reader.start()
        deadline=time.monotonic()+600
        try:
            while process.poll() is None and time.monotonic()<deadline and not job['cancel'].wait(.25): pass
            if job['cancel'].is_set() or process.poll() is None: raise LoginError('登录已取消或超过 10 分钟，请重新开始。')
            if process.returncode: raise LoginError('Claude 登录未成功。请确认使用订阅账户并检查网络后重试。')
            self._set('claude',job,state='saving',authUrl=None,message='正在保存独立凭证；macOS 如有提示，请允许访问本次登录的专属钥匙串条目。')
            oauth=read_claude_login_credentials(cli)
            destination=directory/'credentials.json';private_json(destination,{'claudeAiOauth':oauth})
            return {'managed':True,'path':str(destination),'enabled':True}
        finally:
            stop_process(process);reader.join(timeout=1);process.stdout.close()

    def finish(self, kind, identifier, code):
        if kind!='claude' or not isinstance(code,str) or not re.fullmatch(r'[A-Za-z0-9_.~-]{1,3000}#[A-Za-z0-9_-]{1,500}',code):
            raise LoginError('请粘贴完整授权码（包含 # 后的部分），不要粘贴 API Key。')
        with self.lock:
            job=self.jobs.get(kind)
            if not job or job['id']!=identifier or job['state']!='waiting': raise LoginError('这次登录已结束，请重新连接。')
            state=urllib.parse.parse_qs(urllib.parse.urlsplit(job['authUrl']).query).get('state',[''])[0]
            if not state or not secrets.compare_digest(code.split('#')[1],state): raise LoginError('授权码不属于这次登录，请重新复制当前页面提供的完整授权码。')
            try: job['process'].stdin.write(code+'\n');job['process'].stdin.flush()
            except (OSError,ValueError): raise LoginError('登录进程已结束，请重新连接。')

    def cancel(self, kind, identifier):
        with self.lock:
            job=self.jobs.get(kind)
            if not job or job['id']!=identifier: raise LoginError('登录会话已变化，请刷新页面。')
            if job['state'] not in ('starting','waiting','saving'): return
            job['cancel'].set();job.update(state='cancelled',authUrl=None,message='本次登录已取消，原有连接保留。')
            process=job.get('process')
        stop_process(process)

    def close(self):
        with self.lock: jobs=list(self.jobs.items())
        for kind,job in jobs:
            if job['state'] in ('starting','waiting','saving'): self.cancel(kind,job['id'])
