"""Servidor local do Controle Obras GrupoVax. Apenas biblioteca padrão Python."""
import base64
import binascii
import datetime as dt
import hashlib
import hmac
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
FIELDS = {'title', 'type', 'priority', 'urgency', 'what', 'why', 'where', 'when', 'who', 'how', 'cost', 'team', 'responsible', 'status', 'progress', 'pending'}
ENUMS = {'type': ['Manutenção', 'Obra'], 'priority': ['Baixa', 'Média', 'Alta'], 'urgency': ['Normal', 'Urgente', 'Imediata'], 'status': ['Aberta', 'Em andamento', 'Bloqueada', 'Concluída']}
REQUIRED = {'title', 'what', 'why', 'where', 'when', 'who', 'how', 'team', 'responsible'}
MAX_BODY = 7 * 1024 * 1024

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def validate(data):
    for key in FIELDS - {'cost', 'progress'}:
        if not isinstance(data.get(key), str):
            raise ValueError(f'Campo inválido: {key}.')
        data[key] = data[key].strip()
        if len(data[key]) > 5000:
            raise ValueError(f'Campo muito longo: {key}.')
    if any(not data.get(k) for k in REQUIRED):
        raise ValueError('Preencha os campos obrigatórios do cadastro e do 5W2H.')
    for key, values in ENUMS.items():
        if data.get(key) not in values:
            raise ValueError(f'Opção inválida: {key}.')
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', data['when']):
            raise ValueError()
        dt.date.fromisoformat(data['when'])
    except ValueError:
        raise ValueError('Informe o prazo como uma data válida (AAAA-MM-DD).')
    for key in ['cost', 'progress']:
        value = data.get(key)
        if type(value) not in (int, float) or value < 0 or value > 1e15 or not math.isfinite(value):
            raise ValueError(f'Número inválido: {key}.')
    if data['progress'] > 100 or int(data['progress']) != data['progress']:
        raise ValueError('O progresso deve ser inteiro entre 0 e 100.')
    if data['status'] == 'Concluída' and (data['progress'] != 100 or data['pending']):
        raise ValueError('Para concluir, informe progresso 100 e resolva as pendências.')
    return data

class App:
    def __init__(self, data_dir, admin_password, operator_password):
        if any(not isinstance(p, str) or len(p) < 10 for p in [admin_password, operator_password]):
            raise ValueError('Defina ADMIN_PASSWORD e OPERATOR_PASSWORD com pelo menos 10 caracteres.')
        if admin_password == operator_password:
            raise ValueError('Use senhas diferentes para administração e operação.')
        self.directory = Path(data_dir)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.database = self.directory / 'grupovax.sqlite3'
        self.salt = secrets.token_bytes(32)
        self.users = {'admin': (self.hash(admin_password), 'admin'), 'operacao': (self.hash(operator_password), 'operacao')}
        self.sessions = {}
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS demands(id INTEGER PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS updates(id INTEGER PRIMARY KEY, demand_id INTEGER NOT NULL REFERENCES demands(id), author TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS photos(id INTEGER PRIMARY KEY, demand_id INTEGER NOT NULL REFERENCES demands(id), name TEXT NOT NULL, mime TEXT NOT NULL, content BLOB NOT NULL, author TEXT NOT NULL, created_at TEXT NOT NULL);''')
    def hash(self, password):
        return hashlib.pbkdf2_hmac('sha256', password.encode(), self.salt, 200000)
    def connect(self):
        db = sqlite3.connect(self.database)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        return db

class Handler(BaseHTTPRequestHandler):
    server_version = 'GrupoVax/1.0'
    def log_message(self, *_):
        pass  # Não registrar credenciais ou conteúdo operacional.
    def respond(self, status, payload, headers=None):
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.security_headers()
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def security_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
    @property
    def app(self):
        return self.server.app
    def user(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            token = cookie['session'].value
        except (KeyError, ValueError, CookieError):
            return None
        session = self.app.sessions.get(token)
        if session and session['expires'] > time.time():
            return session
        self.app.sessions.pop(token, None)
        return None
    def body(self):
        if self.headers.get_content_type() != 'application/json':
            raise ValueError('Envie conteúdo JSON.')
        length = int(self.headers.get('Content-Length', '0'))
        if length < 1 or length > MAX_BODY:
            raise ValueError('Conteúdo vazio ou maior que o limite permitido.')
        value = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Número inválido.')))
        if not isinstance(value, dict):
            raise ValueError('Envie um objeto JSON.')
        return value
    def do_GET(self):
        self.dispatch('GET')
    def do_POST(self):
        self.dispatch('POST')
    def do_PATCH(self):
        self.dispatch('PATCH')
    def dispatch(self, method):
        try:
            host = self.headers.get('Host', '')
            allowed = {f'localhost:{self.server.server_port}', f'127.0.0.1:{self.server.server_port}'}
            if host not in allowed:
                return self.respond(403, {'error': 'Endereço de acesso não permitido.'})
            if method != 'GET':
                origin = self.headers.get('Origin')
                if origin and origin not in {f'http://{h}' for h in allowed}:
                    return self.respond(403, {'error': 'Origem não permitida.'})
                if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                    return self.respond(403, {'error': 'Origem não permitida.'})
            path = urlparse(self.path).path
            if method == 'POST' and path == '/api/login':
                data = self.body()
                name = data.get('username')
                password = data.get('password')
                record = self.app.users.get(name) if isinstance(name, str) else None
                if not isinstance(password, str) or len(password) > 1000 or not record or not hmac.compare_digest(self.app.hash(password), record[0]):
                    return self.respond(401, {'error': 'Usuário ou senha inválidos.'})
                token = secrets.token_urlsafe(32)
                self.app.sessions[token] = {'username': name, 'role': record[1], 'expires': time.time() + 28800}
                return self.respond(200, {'username': name, 'role': record[1]}, {'Set-Cookie': f'session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'})
            if path.startswith('/api/'):
                user = self.user()
                if not user:
                    return self.respond(401, {'error': 'Entre para continuar.'})
                if method == 'GET' and path == '/api/me':
                    return self.respond(200, {k: user[k] for k in ['username', 'role']})
                if method == 'POST' and path == '/api/logout':
                    cookie = SimpleCookie(self.headers.get('Cookie', ''))
                    self.app.sessions.pop(cookie['session'].value, None)
                    return self.respond(200, {'ok': True}, {'Set-Cookie': 'session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
                return self.api(method, path, user)
            if method != 'GET':
                return self.respond(404, {'error': 'Rota não encontrada.'})
            relative = 'index.html' if path == '/' else path.lstrip('/')
            file = (ROOT / 'web' / relative).resolve()
            if not file.is_relative_to((ROOT / 'web').resolve()) or not file.is_file():
                return self.respond(404, {'error': 'Página não encontrada.'})
            content = file.read_bytes()
            self.send_response(200)
            self.security_headers()
            self.send_header('Content-Type', mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except (ValueError, TypeError, binascii.Error) as error:
            self.respond(400, {'error': str(error) or 'Dados inválidos.'})
        except sqlite3.Error:
            self.respond(500, {'error': 'Não foi possível salvar. Tente novamente.'})
    def api(self, method, path, user):
        with self.app.connect() as db:
            if method == 'GET' and path == '/api/demands':
                result = []
                for row in db.execute('SELECT * FROM demands ORDER BY id DESC'):
                    item = json.loads(row['payload'])
                    item.update(id=row['id'], created_at=row['created_at'], updated_at=row['updated_at'])
                    item['updates'] = [dict(r) for r in db.execute('SELECT id, author, note, created_at FROM updates WHERE demand_id=? ORDER BY id DESC', (row['id'],))]
                    item['photos'] = [dict(r) | {'url': f"/api/photos/{r['id']}"} for r in db.execute('SELECT id, name, author, created_at FROM photos WHERE demand_id=? ORDER BY id DESC', (row['id'],))]
                    result.append(item)
                return self.respond(200, result)
            if method == 'POST' and path == '/api/demands':
                if user['role'] != 'admin':
                    return self.respond(403, {'error': 'Somente a administração pode cadastrar demandas.'})
                data = self.body()
                if set(data) - FIELDS:
                    raise ValueError('Campos desconhecidos no cadastro.')
                data = validate({'type': 'Manutenção', 'priority': 'Média', 'urgency': 'Normal', 'status': 'Aberta', 'progress': 0, 'pending': '', 'cost': 0} | data)
                stamp = now()
                ident = db.execute('INSERT INTO demands(payload,created_at,updated_at) VALUES(?,?,?)', (json.dumps(data, ensure_ascii=False), stamp, stamp)).lastrowid
                db.execute('INSERT INTO updates(demand_id,author,note,created_at) VALUES(?,?,?,?)', (ident, user['username'], f"Demanda cadastrada. Status: {data['status']}; progresso: {data['progress']}%.", stamp))
                db.commit()
                return self.respond(201, {'id': ident})
            photo_match = re.fullmatch(r'/api/photos/(\d+)', path)
            if method == 'GET' and photo_match:
                photo = db.execute('SELECT * FROM photos WHERE id=?', (photo_match[1],)).fetchone()
                if not photo:
                    return self.respond(404, {'error': 'Foto não encontrada.'})
                self.send_response(200)
                self.security_headers()
                self.send_header('Content-Type', photo['mime'])
                self.send_header('Content-Length', str(len(photo['content'])))
                self.end_headers()
                self.wfile.write(photo['content'])
                return
            match = re.fullmatch(r'/api/demands/(\d+)(?:/(updates|photos))?', path)
            if not match:
                return self.respond(404, {'error': 'Rota não encontrada.'})
            ident, action = match.groups()
            row = db.execute('SELECT * FROM demands WHERE id=?', (ident,)).fetchone()
            if not row:
                return self.respond(404, {'error': 'Demanda não encontrada.'})
            data = self.body()
            stamp = now()
            if method == 'POST' and action == 'photos':
                name, source = data.get('name'), data.get('data')
                if not isinstance(name, str) or not name.strip() or len(name) > 200 or not isinstance(source, str):
                    raise ValueError('Nome ou conteúdo da foto inválido.')
                image = re.fullmatch(r'data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=]+)', source)
                if not image:
                    raise ValueError('Envie uma foto JPEG, PNG ou WebP.')
                kind, encoded = image.groups()
                content = base64.b64decode(encoded, validate=True)
                valid = (kind == 'jpeg' and content.startswith(b'\xff\xd8\xff')) or (kind == 'png' and content.startswith(b'\x89PNG\r\n\x1a\n')) or (kind == 'webp' and content.startswith(b'RIFF') and content[8:12] == b'WEBP')
                if not valid or len(content) > 5 * 1024 * 1024:
                    raise ValueError('Foto inválida ou maior que 5 MB.')
                photo_id = db.execute('INSERT INTO photos(demand_id,name,mime,content,author,created_at) VALUES(?,?,?,?,?,?)', (ident, name.strip(), 'image/' + kind, content, user['username'], stamp)).lastrowid
                db.execute('UPDATE demands SET updated_at=? WHERE id=?', (stamp, ident))
                db.execute('INSERT INTO updates(demand_id,author,note,created_at) VALUES(?,?,?,?)', (ident, user['username'], 'Foto adicionada: ' + name.strip(), stamp))
                db.commit()
                return self.respond(201, {'id': photo_id})
            if (method == 'PATCH' and not action) or (method == 'POST' and action == 'updates'):
                allowed = FIELDS if user['role'] == 'admin' and not action else {'status', 'progress', 'pending'}
                if action == 'updates':
                    allowed = allowed | {'note'}
                if set(data) - allowed:
                    return self.respond(403, {'error': 'Seu perfil não permite alterar esses campos.'})
                note = data.pop('note', '')
                if not isinstance(note, str) or len(note) > 5000:
                    raise ValueError('Registro de andamento inválido.')
                if not data and not note.strip():
                    raise ValueError('Informe uma alteração ou um registro de andamento.')
                previous = json.loads(row['payload'])
                merged = validate(previous | data)
                db.execute('UPDATE demands SET payload=?,updated_at=? WHERE id=?', (json.dumps(merged, ensure_ascii=False), stamp, ident))
                changes = [f'{key}: {previous.get(key)} → {merged[key]}' for key in sorted(data) if previous.get(key) != merged[key]]
                detail = ('Alterações:\n' + '\n'.join(changes)) if changes else ''
                db.execute('INSERT INTO updates(demand_id,author,note,created_at) VALUES(?,?,?,?)', (ident, user['username'], (note.strip() + '\n' + detail).strip(), stamp))
                db.commit()
                return self.respond(200, {'ok': True})
            return self.respond(404, {'error': 'Rota não encontrada.'})

def make_server(app, port=8000):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.app = app
    return server

if __name__ == '__main__':
    try:
        app = App(ROOT / 'data', os.environ.get('ADMIN_PASSWORD'), os.environ.get('OPERATOR_PASSWORD'))
        server = make_server(app)
    except (ValueError, OSError) as error:
        raise SystemExit(str(error))
    print('Controle Obras GrupoVax: http://localhost:8000 (uso local)')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
