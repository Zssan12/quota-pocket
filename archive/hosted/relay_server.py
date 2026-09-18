#!/usr/bin/env python3
"""Quota Pocket ciphertext relay. Provisioning is operator CLI only, never public signup."""
import argparse
import base64
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
import urllib.parse

ROOT = Path(__file__).resolve().parent
TOKEN = re.compile(r'^[A-Za-z0-9_-]{32,128}$')
ROOM = re.compile(r'^[a-f0-9]{32}$')
MAX_BODY = 600_000


class RelayError(Exception):
    def __init__(self, status, message):
        super().__init__(message); self.status = status


def digest(value):
    if not isinstance(value, str) or not TOKEN.fullmatch(value): return ''
    return hashlib.sha256(value.encode()).hexdigest()


def https_origin(value, allow_local=False):
    if not isinstance(value, str): raise ValueError('需要固定 HTTPS 服务地址。')
    parsed = urllib.parse.urlsplit(value)
    if (not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment
        or not (parsed.scheme=='https' or (allow_local and parsed.scheme=='http' and parsed.hostname in ('127.0.0.1','localhost')))):
        raise ValueError('需要不含路径的 HTTPS 服务地址。')
    if parsed.port is not None and not 0 < parsed.port < 65536: raise ValueError('无效端口。')
    return value.rstrip('/')


class RelayStore:
    def __init__(self, directory, public_url, retention=7*86400):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        os.chmod(self.directory,0o700)
        self.public_url=public_url;self.retention=retention;self.lock=threading.RLock()
        self.db=sqlite3.connect(self.directory/'relay.sqlite3',check_same_thread=False,isolation_level=None)
        os.chmod(self.directory/'relay.sqlite3',0o600)
        self.db.row_factory=sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS rooms(id TEXT PRIMARY KEY, writer_hash TEXT NOT NULL, seq INTEGER NOT NULL DEFAULT 0, envelope TEXT, uploaded REAL, epoch INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS invites(hash TEXT PRIMARY KEY, expires REAL NOT NULL, room TEXT);
        CREATE TABLE IF NOT EXISTS pairs(hash TEXT PRIMARY KEY, room TEXT NOT NULL, expires REAL NOT NULL, epoch INTEGER NOT NULL, reader TEXT);
        CREATE TABLE IF NOT EXISTS readers(id TEXT PRIMARY KEY, room TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE, label TEXT NOT NULL, created REAL NOT NULL, epoch INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
        ''')

    def close(self):
        with self.lock:self.db.close()

    def invite(self):
        code=secrets.token_urlsafe(32)
        with self.lock:
            if self.db.execute('SELECT count(*) FROM invites WHERE expires>?',(time.time(),)).fetchone()[0]>=128:
                raise RelayError(429,'未过期的接入邀请过多。')
            self.db.execute('INSERT INTO invites(hash,expires) VALUES(?,?)',(digest(code),time.time()+86400))
        return {'protocol':'quota-pocket-sync-v1','url':self.public_url,'code':code}

    def enroll(self, body):
        code_hash=digest(body.get('code'));writer_hash=digest(body.get('writerToken'))
        if not code_hash or not writer_hash:raise RelayError(400,'接入信息无效。')
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                invite=self.db.execute('SELECT * FROM invites WHERE hash=?',(code_hash,)).fetchone()
                if not invite or invite['expires']<=time.time():raise RelayError(410,'接入邀请已过期。')
                if invite['room']:
                    room=self.writer(invite['room'],body['writerToken'])
                else:
                    uid=secrets.token_hex(16)
                    self.db.execute('INSERT INTO rooms(id,writer_hash) VALUES(?,?)',(uid,writer_hash))
                    self.db.execute('UPDATE invites SET room=? WHERE hash=?',(uid,code_hash))
                    room=self.writer(uid,body['writerToken'])
                self.db.execute('COMMIT')
                return {'room':room['id'],'seq':room['seq'],'protocol':'quota-pocket-sync-v1'}
            except Exception:self.db.execute('ROLLBACK');raise

    def writer(self, uid, token):
        row=self.db.execute('SELECT * FROM rooms WHERE id=?',(uid,)).fetchone()
        if not row or not digest(token) or not hmac.compare_digest(row['writer_hash'],digest(token)):
            raise RelayError(403,'没有此同步空间的管理权限。')
        return row

    def status(self, uid, token):
        with self.lock:
            row=self.writer(uid,token)
            return {'room':uid,'seq':row['seq'],'uploadedAt':row['uploaded'],'retentionSeconds':self.retention}

    def publish(self, uid, token, body):
        if set(body)!={'v','room','seq','nonce','ciphertext'} or body['v']!=1 or body['room']!=uid:
            raise RelayError(400,'密文格式无效。')
        seq=body['seq']
        if isinstance(seq,bool) or not isinstance(seq,int) or not 1<=seq<=9007199254740991:raise RelayError(400,'快照版本无效。')
        try:
            nonce=base64.b64decode(body['nonce'],validate=True);cipher=base64.b64decode(body['ciphertext'],validate=True)
            if len(nonce)!=24 or not 16<=len(cipher)<=400_000:raise ValueError()
        except (ValueError,TypeError):raise RelayError(400,'密文大小或编码无效。')
        with self.lock:
            row=self.writer(uid,token)
            if seq!=row['seq']+1:raise RelayError(409,'快照版本已变化，请重新读取版本后上传。')
            self.db.execute('UPDATE rooms SET seq=?,envelope=?,uploaded=? WHERE id=?',(seq,json.dumps(body,separators=(',',':')),time.time(),uid))
        return {'seq':seq}

    def pair(self, uid, token):
        with self.lock:
            row=self.writer(uid,token)
            if not row['envelope']:raise RelayError(409,'请先上传一次额度快照。')
            if self.db.execute('SELECT count(*) FROM readers WHERE room=? AND revoked=0 AND epoch=?',(uid,row['epoch'])).fetchone()[0]>=16:
                raise RelayError(409,'已达到 16 台手机上限，请先撤销旧设备。')
            if self.db.execute('SELECT count(*) FROM pairs WHERE room=? AND expires>? AND reader IS NULL',(uid,time.time())).fetchone()[0]>=8:
                raise RelayError(429,'待配对链接过多，请稍后再生成。')
            code=secrets.token_urlsafe(32)
            self.db.execute('INSERT INTO pairs(hash,room,expires,epoch) VALUES(?,?,?,?)',(digest(code),uid,time.time()+600,row['epoch']))
            return {'code':code,'seq':row['seq'],'expiresIn':600}

    def exchange(self, body):
        uid=body.get('room');pair_hash=digest(body.get('code'));reader_hash=digest(body.get('readerToken'))
        label=body.get('label','手机')
        if not isinstance(label,str) or not 1<=len(label)<=40 or not pair_hash or not reader_hash:
            raise RelayError(400,'配对请求无效。')
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                pair=self.db.execute('SELECT * FROM pairs WHERE hash=? AND room=?',(pair_hash,uid)).fetchone()
                room=self.db.execute('SELECT * FROM rooms WHERE id=?',(uid,)).fetchone()
                if not pair or not room or pair['expires']<=time.time() or pair['epoch']!=room['epoch']:raise RelayError(410,'配对链接已过期或撤销。')
                if pair['reader']:
                    reader=self.db.execute('SELECT * FROM readers WHERE id=?',(pair['reader'],)).fetchone()
                    if not reader or reader['revoked'] or reader['token_hash']!=reader_hash:raise RelayError(410,'此配对链接已被使用。')
                    rid=reader['id']
                else:
                    if self.db.execute('SELECT count(*) FROM readers WHERE room=? AND revoked=0 AND epoch=?',(uid,room['epoch'])).fetchone()[0]>=16:raise RelayError(409,'设备数量已达上限。')
                    rid=secrets.token_hex(16)
                    self.db.execute('INSERT INTO readers VALUES(?,?,?,?,?,?,0)',(rid,uid,reader_hash,label,time.time(),room['epoch']))
                    self.db.execute('UPDATE pairs SET reader=? WHERE hash=?',(rid,pair_hash))
                self.db.execute('COMMIT')
                return {'protocol':'quota-pocket-sync-v1','room':uid,'readerId':rid}
            except Exception:self.db.execute('ROLLBACK');raise

    def snapshot(self, uid, token):
        with self.lock:
            room=self.db.execute('SELECT * FROM rooms WHERE id=?',(uid,)).fetchone()
            reader=self.db.execute('SELECT * FROM readers WHERE room=? AND token_hash=?',(uid,digest(token))).fetchone()
            if not room or not reader or reader['revoked'] or reader['epoch']!=room['epoch']:raise RelayError(403,'手机连接已撤销，请重新扫码。')
            if not room['envelope']:raise RelayError(404,'尚无快照。')
            if room['uploaded']+self.retention<time.time():raise RelayError(410,'快照已过期，请让电脑重新同步。')
            return json.loads(room['envelope'])

    def readers(self, uid, token):
        with self.lock:
            room=self.writer(uid,token)
            return [dict(r) for r in self.db.execute('SELECT id,label,created FROM readers WHERE room=? AND revoked=0 AND epoch=?',(uid,room['epoch']))]

    def revoke(self, uid, token, reader):
        with self.lock:
            self.writer(uid,token)
            self.db.execute('UPDATE readers SET revoked=1 WHERE id=? AND room=?',(reader,uid))
        return {'ok':True}

    def expire(self):
        with self.lock:
            self.db.execute('UPDATE rooms SET envelope=NULL WHERE uploaded<?',(time.time()-self.retention,))
            # Metadata tombstones preserve consumed invitations; no credential plaintext exists.


class RelayHandler(BaseHTTPRequestHandler):
    server_version='QuotaPocketSync/1'
    def log_message(self,*args):pass
    def setup(self):
        super().setup();self.connection.settimeout(15)
    def send_json(self,status,body,mime='application/json; charset=utf-8'):
        data=body if isinstance(body,bytes) else json.dumps(body,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'")
        self.end_headers()
        try:self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError):pass
    def dispatch(self):
        try:
            store=self.server.store;path=urllib.parse.urlsplit(self.path).path
            if self.headers.get('Origin') not in (None,store.public_url):raise RelayError(403,'请求来源无效。')
            token=self.headers.get('Authorization','').removeprefix('Bearer ')
            body={}
            if self.command in ('POST','PUT'):
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=MAX_BODY or not self.headers.get('Content-Type','').startswith('application/json'):raise ValueError()
                    body=json.loads(self.rfile.read(length))
                    if not isinstance(body,dict):raise ValueError()
                except (ValueError,TypeError):raise RelayError(400,'请求格式或大小无效。')
            if self.command=='GET' and path=='/health':return self.send_json(200,{'ok':True,'service':'quota-pocket-sync','protocol':1})
            if self.command=='POST' and path=='/v1/enroll':return self.send_json(200,store.enroll(body))
            if self.command=='POST' and path=='/v1/pair/exchange':return self.send_json(200,store.exchange(body))
            match=re.fullmatch(r'/v1/rooms/([a-f0-9]{32})/(status|snapshot|pair|readers)(?:/([a-f0-9]{32})/revoke)?',path)
            if match:
                uid,action,reader=match.groups()
                if reader and action=='readers' and self.command=='POST':return self.send_json(200,store.revoke(uid,token,reader))
                if not reader:
                    if action=='status' and self.command=='GET':return self.send_json(200,store.status(uid,token))
                    if action=='snapshot' and self.command=='GET':return self.send_json(200,store.snapshot(uid,token))
                    if action=='snapshot' and self.command=='PUT':return self.send_json(200,store.publish(uid,token,body))
                    if action=='pair' and self.command=='POST':return self.send_json(200,store.pair(uid,token))
                    if action=='readers' and self.command=='GET':return self.send_json(200,store.readers(uid,token))
            assets={'/install.html':('web/install.html','text/html; charset=utf-8'),'/install.js':('web/install.js','application/javascript'),'/install.css':('web/install.css','text/css'),'/icon.svg':('web/icon.svg','image/svg+xml'),'/downloads/Quota-Pocket.js':('widgets/Quota-Pocket.js','text/plain; charset=utf-8')}
            if self.command=='GET' and path in assets:
                file,mime=assets[path];return self.send_json(200,(ROOT/file).read_bytes(),mime)
            raise RelayError(404,'接口不存在。')
        except RelayError as error:self.send_json(error.status,{'error':str(error)})
        except (sqlite3.Error,OSError,ValueError,TypeError):self.send_json(500,{'error':'同步服务暂不可用。'})
    do_GET=dispatch;do_POST=dispatch;do_PUT=dispatch


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['serve','invite']);parser.add_argument('--state-dir',default=os.environ.get('QP_RELAY_STATE','/data'))
    parser.add_argument('--public-url',default=os.environ.get('QP_RELAY_PUBLIC_URL',''))
    parser.add_argument('--bind',default='127.0.0.1');parser.add_argument('--port',type=int,default=8940)
    parser.add_argument('--out',help='Write a private desktop setup file for invite (recommended).')
    args=parser.parse_args()
    try:url=https_origin(args.public_url)
    except ValueError as e:parser.error(str(e))
    store=RelayStore(args.state_dir,url)
    if args.action=='invite':
        value=store.invite()
        if args.out:
            fd=os.open(args.out,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as f:json.dump(value,f)
            print('已生成私有接入文件，请交给电脑端导入。')
        else:print(json.dumps(value))
        store.close();return
    server=ThreadingHTTPServer((args.bind,args.port),RelayHandler);server.store=store;server.daemon_threads=True
    stop=threading.Event()
    def gc():
        while not stop.wait(3600):store.expire()
    store.expire();threading.Thread(target=gc,daemon=True).start()
    print('Quota Pocket encrypted relay listening on port '+str(args.port),flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:stop.set();server.server_close();store.close()


if __name__=='__main__':main()
