import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from itsdangerous import URLSafeTimedSerializer
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app import create_app
import developer
import game


class DeveloperAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.database = str(Path(self.tmp.name) / 'developer.sqlite3')
        self.app = create_app({'TESTING':True,'DATABASE':self.database,'SECRET_KEY':'developer-test-secret'})
        self.client = self.app.test_client()
        self.csrf = self.register(self.client,'api-captain',True)['csrf']
        self.headers = {'X-CSRF-Token':self.csrf}
        response = self.client.post('/developer/keys',json={'name':'test script'},headers=self.headers)
        self.assertEqual(response.status_code,201)
        self.key_info = response.get_json()['key']
        self.key = self.key_info['value']
        self.auth = {'X-User-Key':self.key}
        self.serializer = URLSafeTimedSerializer('developer-test-secret',salt='abyssal-cookie-save-v1')

    def tearDown(self):
        self.tmp.cleanup()

    def register(self, client, username, plan):
        token=client.get('/auth/csrf').get_json()['csrf']
        response=client.post('/auth/register',json={'username':username,'password':'developer-password-123','developer_plan':plan},headers={'X-CSRF-Token':token})
        self.assertEqual(response.status_code,200)
        return response.get_json()

    def seed(self, client=None, **values):
        client=client or self.client
        p=game.new_player();p.update(values)
        client.set_cookie('abyss_save_1',self.serializer.dumps({'user':1,'game':p}))
        return p

    def test_registration_opt_in_and_existing_account_join(self):
        client=self.app.test_client()
        data=self.register(client,'regular-captain',False)
        self.assertEqual(data['redirect'],'/')
        token={'X-CSRF-Token':data['csrf']}
        self.assertEqual(client.get('/developer/docs').status_code,403)
        self.assertEqual(client.post('/developer/keys',json={'name':'no plan'},headers=token).status_code,403)
        self.assertEqual(client.post('/developer/join',json={}).status_code,403)
        self.assertEqual(client.post('/developer/join',json={},headers=token).status_code,200)
        self.assertEqual(client.get('/developer/docs').status_code,200)
        response=client.post('/developer/keys',json={'name':'joined'},headers=token)
        self.assertEqual(response.status_code,201)
        with sqlite3.connect(self.database) as db:
            self.assertEqual(db.execute('SELECT developer_enabled FROM accounts WHERE username_key=?',('regular-captain',)).fetchone()[0],1)
        another=self.app.test_client()
        self.assertEqual(self.register(another,'registered-developer',True)['redirect'],'/developer')

    def test_key_is_shown_once_and_only_hash_is_stored(self):
        self.assertTrue(self.key.startswith('ak_'))
        self.assertGreaterEqual(len(self.key),43)
        data=self.client.get('/developer/keys').get_json()
        self.assertNotIn(self.key,json.dumps(data))
        self.assertNotIn('value',data['keys'][0])
        with sqlite3.connect(self.database) as db:
            row=db.execute('SELECT key_hash,prefix FROM user_keys WHERE id=?',(self.key_info['id'],)).fetchone()
        self.assertEqual(row[0],hashlib.sha256(self.key.encode()).hexdigest())
        self.assertNotIn(self.key,row)
        self.assertTrue(row[1].endswith('…'))

    def test_all_game_endpoints_require_key_even_when_logged_in(self):
        for method,path,_,_ in developer.API_ROUTES:
            with self.subTest(path=path):
                response=self.client.open(path,method=method)
                self.assertEqual(response.status_code,401)
                self.assertFalse(response.get_json()['ok'])
                self.assertEqual(response.headers['Cache-Control'],'no-store')

    def test_bearer_auth_and_no_web_login_required(self):
        client=self.app.test_client()
        response=client.post('/fish',headers={'Authorization':'Bearer '+self.key})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.get_json()['state']['catches'],1)
        result=client.get('/getpays',headers=self.auth)
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.get_json()['data']['catches'],1)
        self.assertTrue(10<=result.get_json()['data']['gold']<=1e6)
        self.assertEqual(client.get('/api/state').status_code,401)

    def test_conflicting_query_and_invalid_keys_are_rejected(self):
        for headers in ({'X-User-Key':'wrong'}, {'Authorization':'Basic abc'},
                        {'X-User-Key':self.key,'Authorization':'Bearer ak_other'},
                        {'X-User-Key':'ak_中文','Authorization':'Bearer ak_other'}):
            self.assertEqual(self.client.get('/getpays',headers=headers).status_code,401)
        self.assertEqual(self.client.get('/getpays',query_string={'key':self.key}).status_code,401)

    def test_api_key_does_not_exempt_web_or_key_management_csrf(self):
        self.assertEqual(self.client.post('/api/catch',headers=self.auth).status_code,403)
        denied=self.client.post('/developer/keys',headers=self.auth,json={'name':'forbidden'})
        self.assertEqual(denied.status_code,403)
        self.assertFalse(denied.get_json()['ok'])
        path='/developer/keys/'+self.key_info['id']+'/revoke'
        self.assertEqual(self.client.post(path,headers=self.auth).status_code,403)

    def test_cookie_session_continues_and_can_be_shared_with_web(self):
        client=self.app.test_client()
        first=client.post('/fish',headers=self.auth).get_json()
        second=client.get('/getpays',headers=self.auth).get_json()
        self.assertEqual(second['data']['catches'],1)
        self.assertEqual(second['data']['gold'],first['state']['gold'])
        self.client.set_cookie('abyss_save_1',client.get_cookie('abyss_save_1').value)
        web=self.client.get('/api/state').get_json()['state']
        self.assertEqual(web['gold'],second['data']['gold'])
        self.assertEqual(web['catches'],1)
        self.assertNotIn(self.key,client.get_cookie('abyss_save_1').value)

    def test_independent_cookie_jars_have_independent_expeditions(self):
        first=self.app.test_client();second=self.app.test_client()
        first.post('/fish',headers=self.auth)
        self.assertEqual(first.get('/getpays',headers=self.auth).get_json()['data']['catches'],1)
        self.assertEqual(second.get('/getpays',headers=self.auth).get_json()['data']['catches'],0)

    def test_required_400_errors_do_not_change_resources(self):
        before=self.client.get('/getpays',headers=self.auth).get_json()['data']
        for path in ('/fish/enablenet','/fish/disablenet','/diamond25','/diamond50','/diamonds','/uphufu','/uptuowang'):
            with self.subTest(path=path):
                response=self.client.post(path,headers=self.auth)
                self.assertEqual(response.status_code,400)
                self.assertFalse(response.get_json()['ok'])
        after=self.client.get('/getpays',headers=self.auth).get_json()['data']
        self.assertEqual(before,after)

    def test_failed_upgrades_and_small_exchanges_preserve_save(self):
        for path, values in (
            ('/upshengna', {'gold':0.0}),
            ('/uphufu', {'level':30,'diamonds':9}),
            ('/uptuowang', {'level':5,'gold':0.0}),
            ('/diamonds', {'level':30,'gold':1e12-1}),
            ('/diamond50', {'level':30,'gold':1e12}),
            ('/diamond25', {'level':30,'gold':3e12}),
        ):
            with self.subTest(path=path):
                self.seed(**values)
                before=self.client.get_cookie('abyss_save_1').value
                self.assertEqual(self.client.post(path,headers=self.auth).status_code,400)
                self.assertEqual(self.client.get_cookie('abyss_save_1').value,before)
        for path, gear in (('/uphufu','charm'),('/upshengna','sonar'),('/uptuowang','net')):
            with self.subTest(maxed=gear):
                p=self.seed(level=30,gold=1e15,diamonds=1000)
                p['gear'][gear]=game.GEAR[gear]['max']
                token=self.serializer.dumps({'user':1,'game':p})
                self.client.set_cookie('abyss_save_1',token)
                self.assertEqual(self.client.post(path,headers=self.auth).status_code,400)
                self.assertEqual(self.client.get_cookie('abyss_save_1').value,token)

    def test_failed_action_keeps_pending_auto_income_for_next_success(self):
        now=time.time()
        p=self.seed(level=5,auto=True,auto_at=now-8)
        p['gear']['net']=1
        token=self.serializer.dumps({'user':1,'game':p})
        self.client.set_cookie('abyss_save_1',token)
        with patch('game.time.time',return_value=now):
            self.assertEqual(self.client.post('/diamonds',headers=self.auth).status_code,400)
            self.assertEqual(self.client.get_cookie('abyss_save_1').value,token)
            settled=self.client.get('/getpays',headers=self.auth).get_json()
            self.assertEqual(settled['auto_catches'],2)
            self.assertEqual(settled['data']['catches'],2)
            again=self.client.get('/getpays',headers=self.auth).get_json()
            self.assertEqual(again['auto_catches'],0)
            self.assertEqual(again['data'],settled['data'])

    def test_two_keys_for_one_account_share_cookie_progress(self):
        response=self.client.post('/developer/keys',json={'name':'second'},headers=self.headers)
        self.assertEqual(response.status_code,201)
        second_auth={'X-User-Key':response.get_json()['key']['value']}
        self.assertEqual(self.client.post('/fish',headers=self.auth).status_code,200)
        self.assertEqual(self.client.get('/getpays',headers=second_auth).get_json()['data']['catches'],1)

    def test_equipment_upgrades_and_net_switches(self):
        self.seed(level=30,gold=1e15,diamonds=1000)
        net=self.client.post('/uptuowang',headers=self.auth).get_json()['state']
        self.assertEqual(net['gear']['net']['rank'],1)
        self.assertTrue(net['auto'])
        disabled=self.client.post('/fish/disablenet',headers=self.auth)
        self.assertEqual(disabled.status_code,200)
        self.assertFalse(disabled.get_json()['state']['auto'])
        enabled=self.client.post('/fish/enablenet',headers=self.auth)
        self.assertTrue(enabled.get_json()['state']['auto'])
        for path,key in (('/uphufu','charm'),('/upshengna','sonar')):
            result=self.client.post(path,headers=self.auth)
            self.assertEqual(result.status_code,200)
            self.assertEqual(result.get_json()['state']['gear'][key]['rank'],1)
        self.assertEqual(result.get_json()['state']['diamonds'],'990')

    def test_main_upgrade_matches_web_and_continues_cookie_save(self):
        self.seed(level=4,gold=1e9)
        initial=self.client.get_cookie('abyss_save_1').value
        result=self.client.post('/upgrademain',headers=self.auth)
        self.assertEqual(result.status_code,200)
        api=result.get_json()
        self.assertEqual(api['data']['levels'],1)
        self.assertEqual(api['state']['level'],5)
        self.assertEqual(api['state']['gold'],1e9-game.level_cost(4))
        self.assertEqual(self.client.get('/getpays',headers=self.auth).get_json()['data']['gold'],api['state']['gold'])
        self.assertEqual(self.client.get('/api/state').get_json()['state']['level'],5)
        self.client.set_cookie('abyss_save_1',initial)
        web=self.client.post('/api/upgrade',json={'mode':'one'},headers=self.headers).get_json()
        for field in ('gold','level','diamonds','catches','collection','gear'):
            self.assertEqual(api['state'][field],web['state'][field])
        self.assertEqual(api['data'],web['result'])

    def test_main_upgrade_failure_preserves_resources_and_level(self):
        for values in ({'gold':0.0},{'level':game.MAX_LEVEL,'gold':game.GOLD_CAP}):
            with self.subTest(values=values):
                self.seed(**values)
                before=self.client.get_cookie('abyss_save_1').value
                response=self.client.post('/upgrademain',headers=self.auth)
                self.assertEqual(response.status_code,400)
                self.assertFalse(response.get_json()['ok'])
                self.assertEqual(self.client.get_cookie('abyss_save_1').value,before)

    def test_repeated_enable_is_idempotent(self):
        p=self.seed(level=5,auto=True,auto_at=time.time()-1)
        p['gear']['net']=1
        self.client.set_cookie('abyss_save_1',self.serializer.dumps({'user':1,'game':p}))
        response=self.client.post('/fish/enablenet',headers=self.auth)
        self.assertEqual(response.status_code,200)
        saved=self.serializer.loads(self.client.get_cookie('abyss_save_1').value)['game']
        self.assertAlmostEqual(saved['auto_at'],p['auto_at'],places=5)

    def test_three_exchange_fractions(self):
        for path,fraction in (('/diamond25',25),('/diamond50',50),('/diamonds',100)):
            with self.subTest(path=path):
                self.seed(level=30,gold=100e12)
                response=self.client.post(path,headers=self.auth)
                self.assertEqual(response.status_code,200)
                result=response.get_json()
                self.assertEqual(result['data']['spent'],fraction*1e12)
                self.assertEqual(result['state']['gold'],(100-fraction)*1e12)
                self.assertIsInstance(result['state']['diamonds'],str)

    def test_api_int64_saturation_is_exact(self):
        self.seed(level=30,gold=1e22,diamonds=123)
        response=self.client.post('/diamond25',headers=self.auth)
        self.assertEqual(response.status_code,200)
        result=response.get_json()
        self.assertTrue(result['data']['special'])
        self.assertEqual(result['data']['destroyed'],'123')
        self.assertEqual(result['state']['diamonds'],'9223372036854775807')
        pays=self.client.get('/getpays',headers=self.auth).get_json()['data']
        self.assertEqual(pays['diamonds'],'9223372036854775807')

    def test_collection_contains_both_locked_and_unlocked_entries(self):
        result=self.client.get('/tujian',headers=self.auth).get_json()['data']
        self.assertEqual(result['total'],8)
        self.assertEqual(len(result['locked']),8)
        self.assertEqual(result['unlocked'],[])
        self.assertTrue(any(f['available'] for f in result['locked']))
        fish=self.client.post('/fish',headers=self.auth).get_json()['data']['catch']['fish']
        result=self.client.get('/tujian',headers=self.auth).get_json()['data']
        self.assertEqual(len(result['unlocked']),1)
        self.assertEqual(result['unlocked'][0]['id'],fish)
        self.assertEqual(result['unlocked'][0]['caught'],1)
        self.assertEqual(len(result['locked']),7)
        self.assertNotEqual(result['unlocked'][0]['description'],'尚未捕获，完整档案未解锁')

    def test_manual_cooldown_and_405_json(self):
        self.assertEqual(self.client.post('/fish',headers=self.auth).status_code,200)
        response=self.client.post('/fish',headers=self.auth)
        self.assertEqual(response.status_code,429)
        self.assertFalse(response.get_json()['ok'])
        wrong=self.client.get('/fish',headers=self.auth)
        self.assertEqual(wrong.status_code,405)
        self.assertFalse(wrong.get_json()['ok'])

    def test_wrong_methods_return_uncached_json(self):
        for method,path,_,_ in developer.API_ROUTES:
            with self.subTest(path=path):
                wrong=self.client.open(path,method='GET' if method=='POST' else 'POST',headers=self.auth)
                self.assertEqual(wrong.status_code,405)
                self.assertFalse(wrong.get_json()['ok'])
                self.assertEqual(wrong.headers['Cache-Control'],'no-store')

    def test_revocation_takes_effect_immediately(self):
        path='/developer/keys/'+self.key_info['id']+'/revoke'
        self.assertEqual(self.client.get('/getpays',headers=self.auth).status_code,200)
        self.assertEqual(self.client.post(path,json={},headers=self.headers).status_code,200)
        self.assertEqual(self.client.get('/getpays',headers=self.auth).status_code,401)
        self.assertEqual(self.client.post('/fish',headers=self.auth).status_code,401)
        keys=self.client.get('/developer/keys').get_json()['keys']
        self.assertIsNotNone(keys[0]['revoked_at'])
        self.assertIsNotNone(keys[0]['last_used_at'])

    def test_account_isolation_for_keys_and_game_cookies(self):
        other=self.app.test_client();registered=self.register(other,'other-developer',True)
        self.assertEqual(other.post('/developer/keys/'+self.key_info['id']+'/revoke',json={},headers={'X-CSRF-Token':registered['csrf']}).status_code,404)
        p=game.new_player();p.update(gold=123456.0,catches=99)
        other.set_cookie('abyss_save_2',self.serializer.dumps({'user':2,'game':p}))
        result=other.get('/getpays',headers=self.auth).get_json()['data']
        self.assertEqual(result['catches'],0)
        self.assertEqual(result['gold'],0)
        self.assertEqual(other.get('/api/state').get_json()['state']['catches'],99)

    def test_key_limits_and_private_pages(self):
        for i in range(4):
            self.assertEqual(self.client.post('/developer/keys',json={'name':f'script {i}'},headers=self.headers).status_code,201)
        self.assertEqual(self.client.post('/developer/keys',json={'name':'sixth'},headers=self.headers).status_code,400)
        anonymous=self.app.test_client()
        self.assertEqual(anonymous.get('/developer/keys').status_code,401)
        self.assertEqual(anonymous.get('/developer/docs').status_code,401)
        self.assertEqual(self.client.post('/developer/keys',json={'name':' '*2},headers=self.headers).status_code,400)

    def test_revoking_key_frees_slot_and_disabled_plan_rejects_keys(self):
        for i in range(4):
            self.client.post('/developer/keys',json={'name':f'key {i}'},headers=self.headers)
        self.client.post('/developer/keys/'+self.key_info['id']+'/revoke',json={},headers=self.headers)
        response=self.client.post('/developer/keys',json={'name':'replacement'},headers=self.headers)
        self.assertEqual(response.status_code,201)
        auth={'X-User-Key':response.get_json()['key']['value']}
        self.assertEqual(self.client.get('/getpays',headers=auth).status_code,200)
        with sqlite3.connect(self.database) as db:
            db.execute('UPDATE accounts SET developer_enabled=0 WHERE id=1')
        self.assertEqual(self.client.get('/getpays',headers=auth).status_code,403)

    def test_developer_handbook_covers_all_endpoints_and_cookie_contract(self):
        response=self.client.get('/developer/docs')
        self.assertEqual(response.status_code,200)
        text=response.get_data(as_text=True)
        for method,path,_,_ in developer.API_ROUTES:
            self.assertIn(path,text)
        self.assertIn('X-User-Key',text)
        self.assertIn('CookieJar',text)
        self.assertNotIn(self.key,text)
        self.assertEqual(response.headers['Cache-Control'],'no-store')

    def test_developer_features_do_not_change_static_memory_edition(self):
        root=Path(__file__).resolve().parent.parent
        environment=Environment(loader=FileSystemLoader(root/'templates'),autoescape=select_autoescape())
        html=environment.get_template('index.html').render(fish=game.FISH,edition='memory',username=None,url_for=lambda _,filename:'./assets/'+filename)
        self.assertNotIn('/developer',html)
        self.assertNotIn('developer.css',html)
        self.assertNotIn('User Key',html)


class DeveloperMigrationTests(unittest.TestCase):
    def test_old_database_is_migrated_without_resetting_accounts(self):
        with tempfile.TemporaryDirectory() as directory:
            path=str(Path(directory)/'old.sqlite3')
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE accounts(id INTEGER PRIMARY KEY,username TEXT NOT NULL,username_key TEXT UNIQUE,password_hash TEXT NOT NULL,created_at REAL NOT NULL)')
                db.execute('INSERT INTO accounts VALUES(1,?,?,?,?)',('old captain','old captain','old-hash',1.0))
            for _ in range(2):
                create_app({'TESTING':True,'DATABASE':path,'SECRET_KEY':'migration-test-secret'})
            with sqlite3.connect(path) as db:
                row=db.execute('SELECT username,password_hash,developer_enabled FROM accounts').fetchone()
                self.assertEqual(row,('old captain','old-hash',0))
                self.assertEqual(db.execute('SELECT COUNT(*) FROM user_keys').fetchone()[0],0)


if __name__=='__main__':
    unittest.main()
