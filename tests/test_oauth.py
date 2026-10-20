"""OAuth security boundaries without contacting Samsung."""
import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch, MagicMock
os.environ["DATA_DIR"]=tempfile.mkdtemp()+"/state"
os.environ["DASHBOARD_USERNAME"]="test"
os.environ["DASHBOARD_PASSWORD"]="test-password"
os.environ["SESSION_SECRET"]="a"*48
from fastapi import HTTPException
from fastapi.testclient import TestClient
from hw_agent import auth, config, db, oauth, oauth_gateway

class OAuthTests(unittest.TestCase):
    def setUp(self):
        db.init(); oauth.initialize()
        with db.connect() as conn:
            for table in ("state","oauth_states","auth"):
                conn.execute("DELETE FROM "+table)
        self.settings=patch.multiple(oauth,CLIENT_ID="test-client",CLIENT_SECRET="test-secret",REDIRECT_URI="https://callback.example/oauth/callback")
        self.settings.start()
        token,_=auth.login(config.USERNAME,config.PASSWORD,"oauth-test")
        self.session=auth.session(SimpleNamespace(cookies={"alter_session":token}))
    def tearDown(self): self.settings.stop()
    def start(self):
        url=oauth.begin(self.session)
        ticket=parse_qs(urlparse(url).query)["ticket"][0]
        destination,binding=oauth.start(ticket)
        state=parse_qs(urlparse(destination).query)["state"][0]
        return ticket,state,binding
    def test_wrong_binding_and_replay(self):
        ticket,state,binding=self.start()
        with self.assertRaises(HTTPException): oauth.start(ticket)
        with self.assertRaises(HTTPException): oauth.finish(state,"wrong",error="denied")
        self.assertFalse(oauth.finish(state,binding,error="denied"))
        with self.assertRaises(HTTPException): oauth.finish(state,binding,error="denied")
    def test_expired_and_logged_out_session(self):
        ticket,state,binding=self.start()
        with db.connect() as conn: conn.execute("DELETE FROM auth")
        with self.assertRaises(HTTPException): oauth.finish(state,binding,error="denied")
    def test_encryption_refresh_and_disconnect(self):
        oauth.save_tokens({"access_token":"secret-access","refresh_token":"old-refresh","expires_at":1})
        self.assertNotIn("secret-access",db.state("st_tokens"))
        mocked=MagicMock(); mocked.__enter__.return_value=mocked
        mocked.refresh_token.return_value={"access_token":"new-access","refresh_token":"new-refresh","expires_in":3600}
        with patch.object(oauth,"client",return_value=mocked):
            self.assertEqual(oauth.access_token(),"new-access")
            self.assertEqual(oauth.access_token(),"new-access")
        self.assertEqual(mocked.refresh_token.call_count,1)
        self.assertEqual(oauth.load_tokens()["refresh_token"],"new-refresh")
        oauth.disconnect();self.assertIsNone(oauth.load_tokens())
    def test_gateway_exposes_no_dashboard(self):
        with TestClient(oauth_gateway.app,base_url="https://callback.example") as client:
            self.assertEqual(client.get("/health").status_code,200)
            self.assertEqual(client.get("/api/devices").status_code,404)
            self.assertEqual(client.get("/oauth/callback?state=bad&code=bad").status_code,400)
            self.assertEqual(client.get("/health",headers={"host":"evil.example"}).status_code,400)

if __name__=="__main__": unittest.main()
