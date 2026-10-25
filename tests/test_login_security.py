"""Persistent lockout, CAPTCHA replay, policy validation and scoped sessions."""
import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
from hw_agent import auth,config,db,login_security
from hw_agent.app import app


class LoginSecurityTests(unittest.TestCase):
    def setUp(self):
        db.init();login_security.init()
        with db.connect() as c:
            for table in ('auth','login_failures','login_challenges'):c.execute('DELETE FROM '+table)
            c.execute("DELETE FROM state WHERE key='login_policy'")

    def captcha(self,ip='testclient',identifier='fixture',expires=None):
        with db.connect() as c:
            c.execute('INSERT OR REPLACE INTO login_challenges VALUES(?,?,?,?,?)',
                      (identifier,login_security.client_key(ip,'public'),login_security.answer_hash(identifier,'TEST23'),expires or time.time()+180,time.time()))
        return identifier,'TEST23'

    def test_lockout_survives_initialization_and_expires(self):
        db.set_state('login_policy',json.dumps({'max_failures':2,'block_minutes':1,'window_minutes':10}))
        for expected in (401,429):
            with self.assertRaises(HTTPException) as error:auth.login('wrong','wrong','lock-test')
            self.assertEqual(error.exception.status_code,expected)
        login_security.init()
        with self.assertRaises(HTTPException) as error:auth.login(config.USERNAME,config.PASSWORD,'lock-test')
        self.assertEqual(error.exception.headers['Retry-After'],'60')
        with patch.object(login_security.time,'time',return_value=time.time()+61):
            self.assertTrue(auth.login(config.USERNAME,config.PASSWORD,'lock-test'))

    def test_captcha_required_single_use_client_bound_and_expiring(self):
        with self.assertRaises(HTTPException):auth.login(config.USERNAME,config.PASSWORD,'testclient','public')
        identifier,answer=self.captcha()
        self.assertTrue(auth.login(config.USERNAME,config.PASSWORD,'testclient','public',identifier,answer))
        with self.assertRaises(HTTPException):auth.login(config.USERNAME,config.PASSWORD,'testclient','public',identifier,answer)
        identifier,answer=self.captcha()
        with self.assertRaises(HTTPException):auth.login(config.USERNAME,config.PASSWORD,'another','public',identifier,answer)
        identifier,answer=self.captcha(expires=time.time()-1)
        with self.assertRaises(HTTPException):auth.login(config.USERNAME,config.PASSWORD,'testclient','public',identifier,answer)

    def test_internal_cookie_cannot_authenticate_public_port(self):
        token,_=auth.login(config.USERNAME,config.PASSWORD,'scope-test')
        self.assertIsNone(auth.session(SimpleNamespace(headers={},cookies={'alter_session':token,'alter_public_session':token})))

    def test_settings_require_auth_csrf_and_validate_range(self):
        client=TestClient(app,base_url="http://127.0.0.1")
        self.assertEqual(client.get('/api/settings/security').status_code,401)
        client.headers['X-Alter-Exposure']='internal'
        response=client.post('/api/login',json={'username':config.USERNAME,'password':config.PASSWORD})
        self.assertEqual(response.status_code,200)
        value={'max_failures':3,'block_minutes':7,'window_minutes':4}
        self.assertEqual(client.put('/api/settings/security',json=value).status_code,403)
        client.headers['X-CSRF-Token']=response.json()['csrf']
        self.assertEqual(client.put('/api/settings/security',json={**value,'max_failures':0}).status_code,422)
        self.assertEqual(client.put('/api/settings/security',json=value).json(),value)
        login_security.init()
        self.assertEqual(client.get('/api/settings/security').json(),value)

    def test_public_login_fixture_and_challenge_contract(self):
        client=TestClient(app,base_url="http://127.0.0.1")
        response=client.get('/api/login/challenge')
        self.assertTrue(response.json()['required'])
        self.assertTrue(response.json()['image'].startswith('data:image/png;base64,'))
        self.assertNotIn('answer',response.json())
        identifier,answer=self.captcha()
        response=client.post('/api/login',json={'username':config.USERNAME,'password':config.PASSWORD,'challenge_id':identifier,'captcha':answer})
        self.assertEqual(response.status_code,200)
        self.assertIn('alter_public_session',response.cookies)
        self.assertEqual(client.get('/api/me').status_code,200)
        client.headers['X-Alter-Exposure']='internal'
        self.assertEqual(client.get('/api/me').status_code,401)


if __name__=='__main__':unittest.main()
