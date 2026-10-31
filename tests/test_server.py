import base64
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import App, make_server

class FlowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = App(self.temp.name, 'admin-password-test', 'operacao-password-test')
        self.server = make_server(self.app, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()
    def request(self, method, path, payload=None, cookie=None, origin=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        headers = {'Content-Type': 'application/json'}
        if cookie:
            headers['Cookie'] = cookie
        if origin:
            headers['Origin'] = origin
        connection.request(method, path, json.dumps(payload) if payload is not None else None, headers)
        response = connection.getresponse()
        content = response.read()
        result = (response.status, json.loads(content) if response.getheader('Content-Type', '').startswith('application/json') else content, response.getheader('Set-Cookie'))
        connection.close()
        return result
    def login(self, name='admin'):
        status, _, cookie = self.request('POST', '/api/login', {'username': name, 'password': 'admin-password-test' if name == 'admin' else 'operacao-password-test'})
        self.assertEqual(status, 200)
        self.assertIn('HttpOnly', cookie)
        return cookie.split(';')[0]
    def demand(self):
        return {'title': 'Corrigir vazamento', 'type': 'Manutenção', 'priority': 'Alta', 'urgency': 'Urgente', 'what': 'Trocar vedação', 'why': 'Infiltração', 'where': 'Galpão', 'when': '2026-11-02', 'who': 'Equipe manutenção', 'how': 'Inspeção e troca', 'cost': 120, 'team': 'Manutenção', 'responsible': 'Fernando', 'status': 'Aberta', 'progress': 0, 'pending': ''}
    def test_complete_flow_roles_and_persistence(self):
        self.assertEqual(self.request('GET', '/api/demands')[0], 401)
        admin, operator = self.login(), self.login('operacao')
        self.assertEqual(self.request('POST', '/api/demands', self.demand(), operator)[0], 403)
        status, created, _ = self.request('POST', '/api/demands', self.demand(), admin)
        self.assertEqual(status, 201)
        path = '/api/demands/' + str(created['id'])
        self.assertEqual(self.request('PATCH', path, {'cost': 1}, operator)[0], 403)
        self.assertEqual(self.request('POST', path + '/updates', {'status': 'Em andamento', 'progress': 50, 'pending': 'Comprar vedação', 'note': 'Inspeção concluída'}, operator)[0], 200)
        self.assertEqual(self.request('POST', path + '/updates', {'status': 'Concluída', 'progress': 100}, operator)[0], 400)
        self.assertEqual(self.request('POST', path + '/updates', {'status': 'Concluída', 'progress': 100, 'pending': '', 'note': 'Serviço executado'}, operator)[0], 200)
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=')
        status, photo, _ = self.request('POST', path + '/photos', {'name': 'evidencia.png', 'data': 'data:image/png;base64,' + base64.b64encode(png).decode()}, operator)
        self.assertEqual(status, 201)
        self.assertEqual(self.request('GET', '/api/photos/' + str(photo['id']))[0], 401)
        self.assertEqual(self.request('GET', '/api/photos/' + str(photo['id']), cookie=admin)[1], png)
        demands = self.request('GET', '/api/demands', cookie=operator)[1]
        self.assertEqual(demands[0]['status'], 'Concluída')
        self.assertEqual(len(demands[0]['updates']), 4)
        self.assertIn('status: Aberta → Em andamento', demands[0]['updates'][2]['note'])
        self.assertIn('progress: 0 → 50', demands[0]['updates'][2]['note'])
        self.assertEqual(len(demands[0]['photos']), 1)
        reopened = App(self.temp.name, 'admin-password-test', 'operacao-password-test')
        with reopened.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM demands').fetchone()[0], 1)
        self.assertEqual(self.request('POST', '/api/logout', {}, admin)[0], 200)
        self.assertEqual(self.request('GET', '/api/me', cookie=admin)[0], 401)
    def test_validation_and_origin(self):
        admin = self.login()
        for changes in [{'cost': -1}, {'cost': True}, {'progress': 101}, {'progress': 2.5}, {'when': '2026-02-30'}, {'title': '   '}, {'priority': 'Inventada'}]:
            self.assertEqual(self.request('POST', '/api/demands', self.demand() | changes, admin)[0], 400)
        self.assertEqual(self.request('POST', '/api/demands', self.demand(), admin, 'https://evil.example')[0], 403)
        self.assertEqual(self.request('POST', '/api/login', {'username': 'admin', 'password': 'errada'})[0], 401)
        status, created, _ = self.request('POST', '/api/demands', self.demand(), admin)
        self.assertEqual(status, 201)
        self.assertEqual(self.request('POST', f"/api/demands/{created['id']}/photos", {'name': 'falsa.png', 'data': 'data:image/png;base64,YWJj'}, admin)[0], 400)
        self.assertEqual(self.request('GET', '/api/photos/999', cookie=admin)[0], 404)
    def test_password_configuration(self):
        with self.assertRaises(ValueError):
            App(self.temp.name, None, None)
        with self.assertRaises(ValueError):
            App(self.temp.name, 'same-password', 'same-password')

if __name__ == '__main__':
    unittest.main()
