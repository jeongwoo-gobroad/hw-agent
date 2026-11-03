import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

os.environ['DATA_DIR'] = tempfile.mkdtemp()
os.environ.setdefault('DASHBOARD_USERNAME', 'test')
os.environ.setdefault('DASHBOARD_PASSWORD', 'test-password')
os.environ.setdefault('SESSION_SECRET', 'x' * 48)
from hw_agent.i18n import gettext, language, request_language
from hw_agent import photo_search, chat

ROOT = Path(__file__).resolve().parents[1]


class LanguageTests(unittest.TestCase):
    def tearDown(self):
        language.set('ko')

    def test_cookie_overrides_browser_language(self):
        request = SimpleNamespace(cookies={'alter_language':'ko'}, headers={'accept-language':'en-US'})
        self.assertEqual(request_language(request), 'ko')
        request.cookies = {}
        self.assertEqual(request_language(request), 'en')

    def test_parallel_requests_do_not_share_language(self):
        def message(code):
            language.set(code)
            return gettext('로그인이 필요합니다.')
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(message, ['en','ko'] * 20))
        self.assertTrue(all(results[i] == results[i % 2] for i in range(40)))
        self.assertNotEqual(results[0], results[1])

    def test_named_photo_query_keeps_person_name(self):
        language.set('en')
        with patch.object(photo_search.photos, 'people', return_value=[{'id':7,'name':'Alex'}]), \
             patch.object(photo_search.photos, 'items', return_value={'total':1,'items':[{'id':3}]}) as items:
            result = photo_search.search('Show photos of Alex', {})
        self.assertEqual(items.call_args.kwargs['person'], 7)
        self.assertIn('Alex', result['text'])
        self.assertNotIn('찾았습니다', result['text'])

    def test_english_topic_and_dates(self):
        self.assertTrue(photo_search.requested('Find photos of buildings'))
        with patch.object(photo_search.photos, 'people', return_value=[]), \
             patch.object(photo_search.photos, 'items', return_value={'total':0,'items':[]}) as items:
            photo_search.search('Find photos of buildings', {})
        self.assertEqual(items.call_args.kwargs['topic'], 'buildings')
        plan = {}
        plan = chat.explicit_filters('Find PDF files from yesterday', plan)
        self.assertEqual(plan['after'], plan['before'])

    def test_frontend_catalogs_keep_interpolation_arguments(self):
        import re
        catalogs = {code:json.loads((ROOT/f'src/hw_agent/web/static/locales/{code}.json').read_text('utf8')) for code in ('en','ko')}
        self.assertEqual(catalogs['en'].keys(), catalogs['ko'].keys())
        for key, value in catalogs['en'].items():
            self.assertCountEqual(re.findall(r'{{(.*?)}}', key), re.findall(r'{{(.*?)}}', value), key)


class DeploymentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('render', ROOT/'scripts/render-deployment.py')
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_templates_follow_install_account_and_network(self):
        for user, uid, subnet in [('alice',1001,'10.0.0.0/24'),('bob',2000,'192.168.1.0/24')]:
            values = dict(user=user,group=user,home='/home/'+user,root='/home/'+user+'/hw-agent',uid=uid,gid=uid,lan=subnet)
            for path in (ROOT/'deploy').iterdir():
                output = self.module.render(path.read_text(), **values)
                self.assertNotRegex(output, r'@[A-Z_]+@')
            output = self.module.render('@USER@ @UID@ @LAN@ @NGROK@', **values)
            self.assertEqual(output, f'{user} {uid} {subnet} /usr/bin/ngrok')
            for bad in ['bad;command', 'name with spaces']:
                with self.assertRaises(ValueError):
                    self.module.render('@USER@', **(values | {'user':bad}))


if __name__ == '__main__':
    unittest.main()
