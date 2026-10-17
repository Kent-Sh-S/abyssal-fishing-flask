import json
import math
from pathlib import Path
import random
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from itsdangerous import URLSafeTimedSerializer

from app import create_app
import game


class NumericalRulesTests(unittest.TestCase):
    def test_gold_cap_is_strict_predecessor(self):
        self.assertEqual(math.nextafter(game.GOLD_CAP, math.inf), game.F64_MAX)
        self.assertLess(game.GOLD_CAP, game.F64_MAX)
        self.assertEqual(game.add_gold(game.GOLD_CAP, game.GOLD_CAP), game.GOLD_CAP)
        self.assertEqual(game.add_gold(math.nextafter(game.GOLD_CAP, 0), game.GOLD_CAP / 2), game.GOLD_CAP)
        self.assertTrue(math.isfinite(game.from_log(99999)))
        with self.assertRaises(ValueError):
            game.bounded(float('nan'))

    def test_first_level_rewards_and_progression(self):
        p = game.new_player()
        rng = random.Random(108)
        for _ in range(1000):
            result = game.catch_fish(p, rng)
            self.assertTrue(10 <= result['gold'] <= 1_000_000)
        self.assertAlmostEqual(game.typical(30) / 5e13, 1.0, places=12)
        previous = game.typical(1)
        for level in range(2, game.MAX_LEVEL + 1):
            current = game.typical(level)
            self.assertGreaterEqual(current, previous)
            self.assertTrue(math.isfinite(current))
            self.assertLessEqual(current, game.GOLD_CAP)
            previous = current

    def test_endgame_catch_and_upgrade_remain_finite(self):
        p = game.new_player()
        p['level'] = game.MAX_LEVEL - 1
        p['gold'] = game.GOLD_CAP
        game.upgrade_player(p, 'max')
        self.assertEqual(p['level'], game.MAX_LEVEL)
        p['gear']['charm'] = 10
        result = game.catch_fish(p, random.Random(1))
        self.assertEqual(result['gold'], game.GOLD_CAP)
        self.assertEqual(p['gold'], game.GOLD_CAP)
        json.dumps(game.public_state(p), allow_nan=False)
        with self.assertRaises(game.RuleError):
            game.upgrade_player(p)

    def test_rate_probabilities_decrease(self):
        self.assertAlmostEqual(sum(prob for _, prob in game.RATES), 100)
        for (a, pa), (b, pb) in zip(game.RATES, game.RATES[1:]):
            self.assertLess(a, b)
            self.assertGreater(pa, pb)

    def test_exchange_unlock_and_fraction_validation(self):
        p = game.new_player()
        p['gold'] = 1e15
        with self.assertRaises(game.RuleError):
            game.exchange(p, 100)
        p['level'] = 30
        for bad in (0, -1, 101, '100', True, 50.0, None):
            with self.assertRaises(game.RuleError):
                game.exchange(p, bad)

    def test_exact_threshold_still_random_and_remainder_preserved(self):
        p = game.new_player()
        p.update(level=30, gold=float(game.EXCHANGE_THRESHOLD))
        result = game.exchange(p, 25, random.Random(1))
        self.assertFalse(result['special'])
        self.assertEqual(p['gold'], 7.5e20)
        p['gold'] = 3.5e12
        result = game.exchange(p, 50, random.Random(1))
        self.assertEqual(result['spent'], 1e12)
        self.assertEqual(p['gold'], 2.5e12)

    def test_strictly_above_threshold_mints_int64_and_burns_excess(self):
        p = game.new_player()
        p.update(level=30, gold=math.nextafter(float(game.EXCHANGE_THRESHOLD), math.inf), diamonds=123)
        result = game.exchange(p, 25)
        self.assertTrue(result['special'])
        self.assertEqual(p['gold'], 0.0)
        self.assertEqual(p['diamonds'], game.INT64_MAX)
        self.assertEqual(result['awarded'], str(game.INT64_MAX - 123))
        self.assertEqual(result['destroyed'], '123')

    def test_regular_exchange_also_saturates_diamonds(self):
        p = game.new_player()
        p.update(level=30, gold=5e12, diamonds=game.INT64_MAX - 2)
        result = game.exchange(p, 100, random.Random(1))
        self.assertEqual(p['diamonds'], game.INT64_MAX)
        self.assertEqual(result['awarded'], '2')
        self.assertEqual(int(result['destroyed']), int(result['minted']) - 2)

    def test_offline_net_has_one_hour_limit_and_preserves_remainder(self):
        p = game.new_player(now=0)
        p.update(auto=True, auto_at=0)
        p['gear']['net'] = 1
        with patch.object(game, 'catch_fish') as caught:
            count = game.settle_auto(p, now=10000)
            self.assertEqual(count, int(3600 // game.net_interval(p)))
            self.assertEqual(caught.call_count, count)
            self.assertEqual(game.settle_auto(p, now=10000), 0)
        p['auto_at'] = 10000
        with patch.object(game, 'catch_fish'):
            self.assertEqual(game.settle_auto(p, now=10004), 1)
        self.assertAlmostEqual(p['auto_at'], 10003.75)


class FlaskPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.database = str(Path(self.tmp.name) / 'test.sqlite3')
        self.app = create_app({'TESTING': True, 'DATABASE': self.database, 'SECRET_KEY': 'isolated-test-key'})
        self.client = self.app.test_client()
        self.csrf = self.client.get('/auth/csrf').get_json()['csrf']
        response = self.client.post('/auth/register', json={'username':'测试潜航员','password':'test-password-123'}, headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(response.status_code,200)
        self.initial = self.client.get('/api/state').get_json()
        self.headers = {'X-CSRF-Token': self.initial['csrf']}
        self.serializer = URLSafeTimedSerializer('isolated-test-key', salt='abyssal-cookie-save-v1')

    def tearDown(self):
        self.tmp.cleanup()

    def test_html_and_static_assets_serve(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        for path in ('style.css', 'fish.js', 'game.js', 'auth.js', 'favicon.svg'):
            response = self.client.get('/static/' + path)
            self.assertEqual(response.status_code, 200)
            response.close()

    def test_session_persistence_and_csrf(self):
        self.assertEqual(self.client.post('/api/catch', json={}).status_code, 403)
        response = self.client.post('/api/catch', json={'gold': 1e300, 'level': 870}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        saved = response.get_json()['state']
        self.assertEqual(saved['level'], 1)
        self.assertEqual(saved['catches'], 1)
        self.assertTrue(10 <= saved['gold'] <= 1e6)
        self.assertEqual(self.client.get('/api/state').get_json()['state'], saved)
        self.assertEqual(self.client.post('/api/catch', json={}, headers=self.headers).status_code, 429)

    def test_int64_round_trip_through_cookie_and_json(self):
        p=game.new_player(); p.update(level=30,gold=1e22,diamonds=123)
        self.client.set_cookie('abyss_save_1',self.serializer.dumps({'user':1,'game':p}))
        result = self.client.post('/api/exchange', json={'fraction': 100}, headers=self.headers).get_json()
        self.assertEqual(result['state']['diamonds'], str(game.INT64_MAX))
        self.assertEqual(result['result']['destroyed'], '123')
        data=self.serializer.loads(self.client.get_cookie('abyss_save_1').value)
        self.assertEqual(data['game']['diamonds'],game.INT64_MAX)
        self.assertIs(type(data['game']['diamonds']),int)
        self.assertIs(type(data['game']['gold']),float)

    def test_login_logout_and_cookie_save_restore(self):
        saved=self.client.post('/api/catch',json={},headers=self.headers).get_json()['state']
        self.assertEqual(self.client.post('/auth/logout',headers=self.headers).status_code,200)
        self.assertEqual(self.client.get('/api/state').status_code,401)
        csrf=self.client.get('/auth/csrf').get_json()['csrf']
        headers={'X-CSRF-Token':csrf}
        self.assertEqual(self.client.post('/auth/login',json={'username':'测试潜航员','password':'incorrect-password'},headers=headers).status_code,401)
        self.assertEqual(self.client.post('/auth/login',json={'username':'测试潜航员','password':'test-password-123'},headers=headers).status_code,200)
        self.assertEqual(self.client.get('/api/state').get_json()['state'],saved)

    def test_passwords_are_hashed_and_no_email_or_game_columns(self):
        with sqlite3.connect(self.database) as db:
            columns=[r[1] for r in db.execute('PRAGMA table_info(accounts)')]
            password_hash=db.execute('SELECT password_hash FROM accounts').fetchone()[0]
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn('email',columns)
        self.assertNotIn('players',tables)
        self.assertTrue(password_hash.startswith('scrypt:'))
        self.assertNotIn('test-password-123',password_hash)

    def test_account_cookie_separation_and_tampering(self):
        saved=self.client.post('/api/catch',json={},headers=self.headers).get_json()['state']
        self.client.post('/auth/logout',headers=self.headers)
        csrf=self.client.get('/auth/csrf').get_json()['csrf']
        self.client.post('/auth/register',json={'username':'second-captain','password':'another-password'},headers={'X-CSRF-Token':csrf})
        self.assertEqual(self.client.get('/api/state').get_json()['state']['catches'],0)
        cookie=self.client.get_cookie('abyss_save_1').value
        self.client.set_cookie('abyss_save_2',cookie)
        self.assertEqual(self.client.get('/api/state').get_json()['state']['catches'],0)
        self.client.set_cookie('abyss_save_2','forged-cookie')
        self.assertEqual(self.client.get('/api/state').get_json()['state']['gold'],0)
        self.assertEqual(saved['catches'],1)

    def test_cookie_size_and_login_throttling(self):
        p=game.new_player();p['level']=870
        rng=random.Random(2)
        for _ in range(100):game.catch_fish(p,rng)
        p['diamonds']=game.INT64_MAX
        self.client.set_cookie('abyss_save_1',self.serializer.dumps({'user':1,'game':p}))
        response=self.client.get('/api/state')
        for cookie in response.headers.getlist('Set-Cookie'):
            self.assertLess(len(cookie),4093)
            self.assertIn('HttpOnly',cookie)
            self.assertIn('SameSite=Lax',cookie)
        self.assertLessEqual(len(response.get_json()['state']['history']),20)
        self.client.post('/auth/logout',headers=self.headers)
        csrf=self.client.get('/auth/csrf').get_json()['csrf'];headers={'X-CSRF-Token':csrf}
        for _ in range(5):
            self.assertEqual(self.client.post('/auth/login',json={'username':'测试潜航员','password':'incorrect-password'},headers=headers).status_code,401)
        self.assertEqual(self.client.post('/auth/login',json={'username':'测试潜航员','password':'test-password-123'},headers=headers).status_code,429)

    def test_invalid_requests_and_reset_confirmation(self):
        self.assertEqual(self.client.post('/api/exchange', json=[], headers=self.headers).status_code, 400)
        self.assertEqual(self.client.post('/api/gear', json={'key': []}, headers=self.headers).status_code, 400)
        self.assertEqual(self.client.post('/api/auto', json={'enabled': 'yes'}, headers=self.headers).status_code, 400)
        self.assertEqual(self.client.post('/api/reset', json={'confirm': 'wrong'}, headers=self.headers).status_code, 400)
        response = self.client.post('/api/reset', json={'confirm': '深渊'}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['state']['gold'], 0.0)


if __name__ == '__main__':
    unittest.main()
