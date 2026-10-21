from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from interfaces.admin import security


class AdminBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=patch.object(security,'AUTH_FILE',Path(self.tmp.name)/'auth.json');self.path.start()
        self.app=FastAPI();self.app.add_middleware(security.AdminBoundary)
        self.app.get('/api/panneau/test')(lambda:{'ok':True})
        self.app.get('/panneau')(lambda:{'panel':True})
        self.client=TestClient(self.app,base_url='http://127.0.0.1',client=('127.0.0.1',48000))
    def tearDown(self):self.path.stop();self.tmp.cleanup()

    def test_origin_host_forwarded_and_remote_are_rejected(self):
        for headers in ({'Origin':'https://example.org'},{'Host':'evil.example'},{'Forwarded':'for=1.2.3.4'},{'Sec-Fetch-Site':'cross-site'}):
            self.assertEqual(self.client.get('/api/panneau/test',headers=headers).status_code,403)
        remote=TestClient(self.app,base_url='http://127.0.0.1',client=('192.168.1.1',1))
        self.assertEqual(remote.get('/api/panneau/test').status_code,403)

    def test_password_cookie_logout_and_no_hash_in_response(self):
        security.set_password('mot de passe de test')
        self.assertEqual(self.client.get('/api/panneau/test').status_code,401)
        self.assertIn('password',self.client.get('/panneau').text)
        self.assertEqual(self.client.post('/api/panneau/session/login',json={'password':'incorrect'}).status_code,401)
        r=self.client.post('/api/panneau/session/login',json={'password':'mot de passe de test'})
        self.assertTrue(r.json()['ok']);self.assertIn('HttpOnly',r.headers['set-cookie']);self.assertIn('SameSite=strict',r.headers['set-cookie'])
        self.assertEqual(self.client.get('/api/panneau/test').status_code,200)
        self.assertNotIn('argon2',r.text)
        self.client.post('/api/panneau/session/logout',json={})
        self.assertEqual(self.client.get('/api/panneau/test').status_code,401)

    def test_disabled_admin_routes_are_absent(self):
        from core import config,serveur
        with patch.object(config,'_CONFIG',{'admin':{'enabled':False}}),patch.object(serveur,'_APP',None):
            routes=[r.path for r in serveur.app().routes]
        self.assertNotIn('/panneau',routes);self.assertNotIn('/cockpit',routes)
