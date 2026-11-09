"""Offline account-abuse regressions; only temporary SQLite and mocked SMTP."""
import hashlib
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.base import Base, get_db
from app.db.models import User
from app.api import account, recovery, offers
from app.core.config import settings

class AuthLimitTests(unittest.TestCase):
    def setUp(self):
        self.cleanup=ExitStack()
        self.addCleanup(self.cleanup.close)
        self.directory=self.cleanup.enter_context(tempfile.TemporaryDirectory())
        self.engine=create_engine('sqlite:///'+(Path(self.directory)/'auth.db').as_posix(),
                                  connect_args={'check_same_thread':False,'timeout':20})
        self.cleanup.callback(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.sessions=sessionmaker(bind=self.engine)
        salt='11'*16
        with self.sessions() as db:
            db.add(User(email='user@example.test',name='Fixture',
                        password_hash=salt+':'+account.password_hash('correct-password',salt)))
            db.commit()
        self.app=FastAPI()
        for router in (account.router,recovery.router,offers.router):
            self.app.include_router(router)
        def database():
            with self.sessions() as db:
                yield db
        self.app.dependency_overrides[get_db]=database
        self.cleanup.enter_context(patch.object(settings,'smtp_host','smtp.example.test'))
        self.cleanup.enter_context(patch.object(settings,'smtp_from','no-reply@example.test'))
        self.cleanup.enter_context(patch('app.services.mail.send_reset_email'))
        self.client=self.peer('198.51.100.10')

    def peer(self, ip, middleware=None):
        app=middleware(self.app) if middleware else self.app
        async def transport(scope, receive, send):
            scope={**scope,'client':(ip,12345)}
            await app(scope,receive,send)
        client=TestClient(transport)
        self.cleanup.callback(client.close)
        return client

    def login(self, client=None, email='user@example.test', password='wrong-password', **extra):
        return (client or self.client).post('/api/auth/login',
                    json={'email':email,'password':password,**extra})

    def test_successful_login_keeps_http_only_cookie_and_session(self):
        result=self.login(password='correct-password')
        self.assertEqual(result.status_code,200)
        cookie=result.headers['set-cookie'].lower()
        self.assertIn('httponly',cookie);self.assertIn('samesite=lax',cookie)
        self.assertEqual(self.client.get('/api/auth/me').status_code,200)
        self.assertEqual(self.client.post('/api/auth/logout').status_code,204)
        self.assertEqual(self.client.get('/api/auth/me').status_code,401)

    def test_three_typos_do_not_block_correct_login(self):
        for _ in range(3):
            self.assertEqual(self.login().status_code,401)
        self.assertEqual(self.login(password='correct-password').status_code,200)

    def test_repeated_wrong_password_reaches_limit_and_retry_after(self):
        with patch('app.api.account.password_hash',return_value='0'*128):
            replies=[self.login() for _ in range(11)]
        self.assertEqual(replies[-1].status_code,429)
        self.assertGreater(int(replies[-1].headers['Retry-After']),0)

    def test_forged_forwarding_headers_do_not_change_limit(self):
        with patch('app.api.account.password_hash',return_value='0'*128):
            for _ in range(10): self.login()
            response=self.client.post('/api/auth/login',headers={
                'X-Forwarded-For':'203.0.113.99','X-Real-IP':'203.0.113.98'},
                json={'email':'user@example.test','password':'wrong-password'})
        self.assertEqual(response.status_code,429)

    def test_known_and_unknown_accounts_have_identical_failure_and_limit_responses(self):
        results=[]
        with patch('app.api.account.password_hash',return_value='0'*128):
            for address in ('user@example.test','missing@example.test'):
                client=self.peer('198.51.100.'+('20' if address.startswith('user') else '21'))
                replies=[self.login(client,email=address) for _ in range(11)]
                results.append((replies[0].status_code,replies[0].json(),replies[-1].status_code,replies[-1].json()))
        self.assertEqual(results[0],results[1])
        self.assertEqual(results[0][2],429)

    def test_email_case_and_whitespace_cannot_reset_pair_limit(self):
        with patch('app.api.account.password_hash',return_value='0'*128):
            for _ in range(10): self.login(email='USER@EXAMPLE.TEST')
            response=self.login(email=' user@example.test ')
        self.assertEqual(response.status_code,429)

    def test_other_ip_can_log_in_after_pair_limit(self):
        with patch('app.api.account.password_hash',return_value='0'*128):
            for _ in range(11): self.login()
        self.assertEqual(self.login(self.peer('198.51.100.22'),password='correct-password').status_code,200)

    def test_same_ip_cannot_bypass_global_limit_using_many_accounts(self):
        with patch('app.api.account.password_hash',return_value='0'*128):
            replies=[self.login(email=f'missing{n}@example.test') for n in range(61)]
        self.assertEqual(replies[-1].status_code,429)

    def test_concurrent_pair_attempts_are_bounded(self):
        def attempt(number):
            return self.login(self.peer('198.51.100.30')).status_code
        with patch('app.api.account.password_hash',return_value='0'*128), ThreadPoolExecutor(max_workers=5) as executor:
            statuses=list(executor.map(attempt,range(20)))
        self.assertEqual(statuses.count(401),10)
        self.assertEqual(statuses.count(429),10)

    def test_recovery_limit_returns_retry_after_for_known_and_unknown_email(self):
        for address,ip in [('user@example.test','198.51.100.40'),('missing@example.test','198.51.100.41')]:
            client=self.peer(ip)
            replies=[client.post('/api/auth/forgot-password',json={'email':address}) for _ in range(4)]
            self.assertEqual([r.status_code for r in replies],[202,202,202,429])
            self.assertGreater(int(replies[-1].headers['Retry-After']),0)

    def test_mass_registration_is_limited(self):
        replies=[self.client.post('/api/auth/register',json={
            'name':'Fixture','email':f'new{n}@example.test','password':'long-password'}) for n in range(6)]
        self.assertEqual(replies[-1].status_code,429)

    def test_password_change_wrong_password_is_limited(self):
        self.assertEqual(self.login(password='correct-password').status_code,200)
        with patch('app.api.account.password_hash',return_value='0'*128):
            replies=[self.client.post('/api/auth/password',json={
                'current_password':'wrong-password','new_password':'new-long-password'}) for _ in range(11)]
        self.assertEqual(replies[-1].status_code,429)

    def test_url_import_requires_authentication_before_network(self):
        with patch('app.api.offers.fetch') as network:
            response=self.client.post('/api/offers/from-url',json={'source':'regard','category':'GPU',
                'url':'https://www.regard.ru/product/123456/fixture'})
        self.assertEqual(response.status_code,401)
        network.assert_not_called()

    def solve(self, challenge):
        for nonce in range(100000):
            value=int.from_bytes(hashlib.sha256((challenge['token']+':'+str(nonce)).encode()).digest(),'big')
            if value < (1 << (256-challenge['bits'])):
                return str(nonce)
        self.fail('Fixture work check could not be solved')

    def challenge_for(self, client, email='user@example.test'):
        response=self.login(client,email=email)
        self.assertEqual(response.status_code,429)
        return response.json()['detail']['challenge']

    def test_limit_expires_at_exact_boundary_and_rejections_do_not_extend_it(self):
        from datetime import datetime,timedelta
        current=datetime(2026,11,9,12)
        with patch('app.services.auth_limits.now',return_value=current), patch('app.api.account.password_hash',return_value='0'*128):
            for _ in range(10):self.login()
            first=self.login()
        self.assertEqual(first.status_code,429)
        self.assertEqual(int(first.headers['Retry-After']),900)
        with patch('app.services.auth_limits.now',return_value=current+timedelta(seconds=100)):
            blocked=self.login()
        self.assertEqual(int(blocked.headers['Retry-After']),800)
        with patch('app.services.auth_limits.now',return_value=current+timedelta(seconds=900)):
            self.assertEqual(self.login(password='correct-password').status_code,200)

    def test_distributed_attempts_require_work_before_password_hashing(self):
        with patch.object(settings,'auth_login_account_limit',2), patch.object(settings,'auth_challenge_bits',8), patch(
                'app.api.account.password_hash',return_value='0'*128) as hash_password:
            self.assertEqual(self.login(self.peer('203.0.113.1')).status_code,401)
            self.assertEqual(self.login(self.peer('203.0.113.2')).status_code,401)
            response=self.login(self.peer('203.0.113.3'))
            self.assertEqual(response.status_code,429)
            self.assertEqual(hash_password.call_count,2)
            self.assertEqual(response.json()['detail']['challenge']['bits'],8)

    def test_account_burst_does_not_lock_a_correct_login_from_new_ip(self):
        with patch.object(settings,'auth_login_account_limit',1), patch.object(settings,'auth_challenge_bits',8):
            self.login(self.peer('203.0.113.1'))
            client=self.peer('203.0.113.2')
            challenge=self.challenge_for(client)
            response=self.login(client,password='correct-password',challenge_token=challenge['token'],
                                challenge_nonce=self.solve(challenge))
        self.assertEqual(response.status_code,200)
        self.assertEqual(client.get('/api/auth/me').status_code,200)

    def test_unknown_account_has_same_work_policy_and_still_returns_generic_401(self):
        email='missing@example.test'
        with patch.object(settings,'auth_login_account_limit',1), patch.object(settings,'auth_challenge_bits',8):
            self.login(self.peer('203.0.113.1'),email=email)
            client=self.peer('203.0.113.2')
            challenge=self.challenge_for(client,email=email)
            response=self.login(client,email=email,challenge_token=challenge['token'],challenge_nonce=self.solve(challenge))
        self.assertEqual(response.status_code,401)
        self.assertEqual(response.json(),{'detail':'Неверный email или пароль'})

    def test_parallel_proof_redemption_allows_one_attempt(self):
        with patch.object(settings,'auth_login_account_limit',1), patch.object(settings,'auth_challenge_bits',8):
            self.login(self.peer('203.0.113.1'))
            client=self.peer('203.0.113.2')
            challenge=self.challenge_for(client);nonce=self.solve(challenge)
            def attempt(_):
                return self.login(self.peer('203.0.113.2'),password='correct-password',
                                  challenge_token=challenge['token'],challenge_nonce=nonce).status_code
            with ThreadPoolExecutor(max_workers=2) as executor:
                statuses=list(executor.map(attempt,range(2)))
        self.assertEqual(sorted(statuses),[200,429])

    def test_expired_work_ticket_cannot_be_reused(self):
        from datetime import datetime,timedelta
        current=datetime(2026,11,9,12)
        with patch.object(settings,'auth_login_account_limit',1), patch.object(settings,'auth_challenge_bits',8):
            with patch('app.services.auth_limits.now',return_value=current):
                self.login(self.peer('203.0.113.1'))
                client=self.peer('203.0.113.2')
                challenge=self.challenge_for(client);nonce=self.solve(challenge)
            with patch('app.services.auth_limits.now',return_value=current+timedelta(seconds=120)):
                response=self.login(client,password='correct-password',challenge_token=challenge['token'],challenge_nonce=nonce)
        self.assertEqual(response.status_code,429)

    def test_proof_is_bound_to_client_ip(self):
        with patch.object(settings,'auth_login_account_limit',1), patch.object(settings,'auth_challenge_bits',8):
            self.login(self.peer('203.0.113.1'))
            challenge=self.challenge_for(self.peer('203.0.113.2'))
            response=self.login(self.peer('203.0.113.3'),password='correct-password',
                                challenge_token=challenge['token'],challenge_nonce=self.solve(challenge))
        self.assertEqual(response.status_code,429)

    def test_ipv4_mapped_ipv6_cannot_reset_limit(self):
        with patch('app.api.account.password_hash',return_value='0'*128):
            for _ in range(10):self.login(self.peer('198.51.100.55'))
            response=self.login(self.peer('::ffff:198.51.100.55'))
        self.assertEqual(response.status_code,429)

    def test_ipv6_addresses_in_same_prefix_share_the_limit(self):
        with patch('app.api.account.password_hash',return_value='0'*128):
            for _ in range(10):self.login(self.peer('2001:db8:1:2::1'))
            response=self.login(self.peer('2001:0db8:0001:0002::99'))
        self.assertEqual(response.status_code,429)

    def test_untrusted_proxy_headers_are_ignored_by_uvicorn(self):
        from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
        client=self.peer('198.51.100.60',lambda app:ProxyHeadersMiddleware(app,trusted_hosts=['127.0.0.1']))
        with patch('app.api.account.password_hash',return_value='0'*128):
            for number in range(11):
                response=client.post('/api/auth/login',headers={'X-Forwarded-For':f'203.0.113.{number}'},
                                     json={'email':'user@example.test','password':'wrong-password'})
        self.assertEqual(response.status_code,429)

    def test_trusted_proxy_uses_last_untrusted_hop_not_forged_leftmost_ip(self):
        from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
        client=self.peer('127.0.0.1',lambda app:ProxyHeadersMiddleware(app,trusted_hosts=['127.0.0.1']))
        with patch('app.api.account.password_hash',return_value='0'*128):
            for number in range(11):
                response=client.post('/api/auth/login',headers={'X-Forwarded-For':f'192.0.2.{number}, 198.51.100.70'},
                                     json={'email':'user@example.test','password':'wrong-password'})
        self.assertEqual(response.status_code,429)
        other=client.post('/api/auth/login',headers={'X-Forwarded-For':'198.51.100.71'},
                          json={'email':'user@example.test','password':'correct-password'})
        self.assertEqual(other.status_code,200)

    def test_old_counters_and_expired_tickets_are_cleaned_without_raw_identifiers(self):
        from datetime import timedelta
        from app.services import auth_limits
        from app.db.models import ResetRequestLimit,AuthChallenge
        stale=hashlib.sha256(b'stale-counter').hexdigest()
        with self.sessions() as db:
            db.add(ResetRequestLimit(key_hash=stale,started_at=auth_limits.now()-timedelta(hours=2),attempts=999))
            db.add(AuthChallenge(token_hash='a'*64,subject_hash='b'*64,bits=8,expires_at=auth_limits.now()-timedelta(seconds=1)))
            db.commit()
        self.login()
        with self.sessions() as db:
            self.assertIsNone(db.get(ResetRequestLimit,stale))
            self.assertIsNone(db.get(AuthChallenge,'a'*64))
            from sqlalchemy import select
            for row in db.scalars(select(ResetRequestLimit)):
                self.assertRegex(row.key_hash,r'^[a-f0-9]{64}$')

    def test_recovery_ip_quota_covers_many_different_addresses(self):
        replies=[self.client.post('/api/auth/forgot-password',json={'email':f'missing{n}@example.test'}) for n in range(11)]
        self.assertEqual(replies[-1].status_code,429)
        self.assertGreater(int(replies[-1].headers['Retry-After']),0)

    def test_cookie_works_on_another_device_and_password_change_revokes_old_sessions(self):
        self.assertEqual(self.login(password='correct-password').status_code,200)
        other=self.peer('203.0.113.80')
        other.cookies.update(self.client.cookies)
        self.assertEqual(other.get('/api/auth/me').status_code,200)
        self.assertEqual(other.get('/api/builds').status_code,200)
        changed=self.client.post('/api/auth/password',json={'current_password':'correct-password',
                                                          'new_password':'new-correct-password'})
        self.assertEqual(changed.status_code,200)
        self.assertEqual(other.get('/api/auth/me').status_code,401)
        self.assertEqual(self.client.get('/api/auth/me').status_code,200)
        with self.sessions() as db:
            from sqlalchemy import select
            user=db.scalar(select(User).where(User.email=='user@example.test'))
            salt,expected=user.password_hash.split(':')
            self.assertEqual(account.password_hash('new-correct-password',salt),expected)

    def test_work_ticket_is_bound_to_normalized_account(self):
        with patch.object(settings,'auth_login_account_limit',1), patch.object(settings,'auth_challenge_bits',8):
            self.login(self.peer('203.0.113.1'))
            self.login(self.peer('203.0.113.1'),email='other@example.test')
            client=self.peer('203.0.113.2')
            challenge=self.challenge_for(client)
            response=self.login(client,email='other@example.test',
                                challenge_token=challenge['token'],challenge_nonce=self.solve(challenge))
        self.assertEqual(response.status_code,429)

    def test_existing_session_remains_usable_while_login_is_limited(self):
        self.assertEqual(self.login(password='correct-password').status_code,200)
        with patch('app.api.account.password_hash',return_value='0'*128):
            for _ in range(10):self.login()
        self.assertEqual(self.login().status_code,429)
        self.assertEqual(self.client.get('/api/auth/me').status_code,200)
        self.assertEqual(self.client.get('/api/builds').status_code,200)

    def test_proof_cannot_bypass_hard_ip_pair_quota(self):
        with patch.object(settings,'auth_login_account_limit',1), patch.object(settings,'auth_login_pair_limit',2), patch.object(settings,'auth_challenge_bits',8):
            self.login()
            challenge=self.challenge_for(self.client)
            response=self.login(password='correct-password',challenge_token=challenge['token'],
                                challenge_nonce=self.solve(challenge))
        self.assertEqual(response.status_code,429)
        self.assertIsInstance(response.json()['detail'],str)

    def test_limits_are_shared_with_another_engine_using_same_sqlite_file(self):
        with patch('app.api.account.password_hash',return_value='0'*128):
            for _ in range(10):self.login()
        other=create_engine(self.engine.url,connect_args={'check_same_thread':False})
        self.cleanup.callback(other.dispose)
        self.sessions=sessionmaker(bind=other)
        self.assertEqual(self.login().status_code,429)

    def test_concurrent_recovery_reserves_only_three_requests(self):
        def attempt(_):
            return self.peer('198.51.100.90').post('/api/auth/forgot-password',
                     json={'email':'missing@example.test'}).status_code
        with ThreadPoolExecutor(max_workers=4) as executor:
            statuses=list(executor.map(attempt,range(4)))
        self.assertEqual(sorted(statuses),[202,202,202,429])

    def test_reset_token_guessing_is_limited_before_password_update(self):
        replies=[self.client.post('/api/auth/reset-password',json={
            'token':'a'*32,'new_password':'new-long-password'}) for _ in range(21)]
        self.assertEqual([r.status_code for r in replies[:20]],[400]*20)
        self.assertEqual(replies[-1].status_code,429)
        self.assertGreater(int(replies[-1].headers['Retry-After']),0)

    def test_untrusted_non_store_url_is_rejected_without_network(self):
        with patch('app.api.offers.fetch') as network:
            response=self.client.post('/api/offers/from-url',json={'source':'regard','category':'GPU',
                'url':'https://127.0.0.1/product/123456/fixture'})
        self.assertIn(response.status_code,(401,422))
        network.assert_not_called()

if __name__=='__main__': unittest.main()
