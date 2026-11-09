"""Pinned-transport security tests. Every DNS answer and socket is a fixture."""
import gzip
from io import BytesIO
import json
import socket
import ssl
import sys
import time
import unittest
from email.message import Message
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from requests.structures import CaseInsensitiveDict
from app.services.network_policy import Address, NetworkPolicyError, Policy, public_address, resolve_public, validate_url
from app.services.safe_http import PinnedHTTPSConnection, SafeResponse, SafeSession, tls_context
from app.services.store_providers import fetch, resolved_search_url
from app.schemas.offers import store_url
from app.services.browser_offers import browser_context, browser_diagnostics

PUBLIC='93.184.216.34'
URL='https://www.regard.ru/product/123456/fixture'
def dns(ip):
    family=socket.AF_INET6 if ':' in ip else socket.AF_INET
    return (family,socket.SOCK_STREAM,6,'',(ip,443,0,0) if family==socket.AF_INET6 else (ip,443))

class FakeResponse:
    def __init__(self,body=b'fixture',status=200,headers=None):
        self.status=status
        self.headers=Message()
        for key,value in (headers or {'Content-Type':'text/html'}).items():
            self.headers[key]=value
        self.body=BytesIO(body)
        self.closed=False
    def getheader(self,key):return self.headers.get(key)
    def getheaders(self):return list(self.headers.items())
    def info(self):return self.headers
    def read1(self,size):return self.body.read(size)
    def close(self):self.closed=True

class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.socket=patch('socket.socket',side_effect=AssertionError('No real socket in tests')).start()
        self.addCleanup(patch.stopall)

    def test_valid_store_url_normalizes_host_and_keeps_business_allowlist(self):
        target=validate_url('https://WWW.REGARD.RU.:443/product/123/?q=x',Policy(domains=('regard.ru',)))
        self.assertEqual(target.host,'www.regard.ru')
        self.assertTrue(store_url('regard',target.url))
        self.assertFalse(store_url('regard','https://regard.ru.evil.example/product/123/'))

    def test_invalid_url_schemes_credentials_ports_and_ambiguities(self):
        for value in (None,'','http://www.regard.ru/x','file:///etc/passwd','gopher://www.regard.ru',
                      'https://user:password@www.regard.ru/x','https://@www.regard.ru/x',
                      'https://www.regard.ru:8443/x','https://www.regard.ru:bad/x',
                      'https://www.regard.ru\\@evil.example/x','https://www.regard.ru/\nfoo',
                      'https://www.regard.ru/%zz','https://[::1','https://local-name/x',
                      'https://metadata.google.internal/x','https://localhost/x','https://foo.local/x'):
            with self.subTest(url=value):
                with self.assertRaises(NetworkPolicyError):validate_url(value)

    def test_all_non_public_ip_classes_and_mapped_addresses_are_rejected(self):
        for value in ('127.0.0.1','10.1.2.3','172.16.0.1','192.168.1.1','169.254.169.254',
                      '100.100.100.200','0.0.0.0','224.0.0.1','240.0.0.1','198.18.0.1',
                      '192.0.0.8','::1','::','fe80::1','fd00:ec2::254','ff02::1',
                      '::ffff:127.0.0.1','::ffff:10.0.0.1','64:ff9b::7f00:1','2002:7f00:1::'):
            with self.subTest(ip=value):
                with self.assertRaises(NetworkPolicyError):public_address(value)

    def test_public_ipv4_ipv6_and_mapped_public_address(self):
        self.assertEqual(str(public_address(PUBLIC)),PUBLIC)
        self.assertEqual(str(public_address('2606:4700:4700::1111')),'2606:4700:4700::1111')
        self.assertEqual(str(public_address('::ffff:8.8.8.8')),'8.8.8.8')

    def test_mixed_a_and_aaaa_fail_as_a_whole(self):
        for records in ([dns(PUBLIC),dns('::1')],[dns('2606:4700:4700::1111'),dns('10.0.0.1')]):
            with patch('socket.getaddrinfo',return_value=records):
                with self.assertRaises(NetworkPolicyError):
                    resolve_public(validate_url(URL),time.monotonic()+5)

    def test_numeric_legacy_loopback_formats_are_still_rejected_after_dns(self):
        for host in ('2130706433','0177.0.0.1','0x7f000001','127.1'):
            with self.subTest(host=host),patch('socket.getaddrinfo',return_value=[dns('127.0.0.1')]):
                try:target=validate_url('https://'+host+'/')
                except NetworkPolicyError:continue
                with self.assertRaises(NetworkPolicyError):resolve_public(target,time.monotonic()+5)

    def test_slow_dns_times_out_without_starting_a_socket(self):
        release,finished=Event(),Event()
        def lookup(*args):
            try:
                release.wait(2)
                return [dns(PUBLIC)]
            finally:finished.set()
        with patch('socket.getaddrinfo',side_effect=lookup):
            try:
                with self.assertRaises(TimeoutError):
                    resolve_public(validate_url(URL),time.monotonic()+.02)
            finally:
                release.set()
                self.assertTrue(finished.wait(2))
        self.socket.assert_not_called()

class TransportTests(unittest.TestCase):
    def setUp(self):
        self.socket=patch('socket.socket',side_effect=AssertionError('No real socket in tests')).start()
        self.dns=patch('socket.getaddrinfo',return_value=[dns(PUBLIC)]).start()
        self.addCleanup(patch.stopall)

    def connection(self,response):
        conn=Mock()
        conn.getresponse.return_value=response
        return conn

    def test_regular_https_preserves_expected_host_and_closes_response(self):
        response=FakeResponse(b'<html>fixture</html>')
        conn=self.connection(response)
        with patch('app.services.safe_http.PinnedHTTPSConnection',return_value=conn):
            result=SafeSession(Policy(domains=('regard.ru',))).get(URL)
        self.assertEqual(result.text,'<html>fixture</html>')
        self.assertEqual(conn.request.call_args.kwargs['headers']['Host'],'www.regard.ru')
        self.assertEqual(conn.request.call_args.args[:2],('GET','/product/123456/fixture'))
        self.assertTrue(response.closed)
        conn.abort.assert_called()

    def test_rebinding_cannot_replace_the_checked_ip_at_connect(self):
        self.dns.side_effect=[[dns(PUBLIC)],[dns('127.0.0.1')]]
        target=validate_url(URL);addresses=resolve_public(target,time.monotonic()+5)
        context=Mock();raw=Mock();raw.getpeername.return_value=(PUBLIC,443)
        with patch('app.services.safe_http.tls_context',return_value=context),patch('socket.socket',return_value=raw):
            conn=PinnedHTTPSConnection(target,addresses,time.monotonic()+5)
            conn.connect()
        self.assertEqual(self.dns.call_count,1)
        raw.connect.assert_called_once_with((PUBLIC,443))
        context.wrap_socket.assert_called_once_with(raw,server_hostname='www.regard.ru')

    def test_tls_context_requires_certificates_and_hostname_validation(self):
        context=tls_context()
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)

    def test_unexpected_peer_is_rejected_before_tls(self):
        raw=Mock();raw.getpeername.return_value=('10.0.0.1',443);context=Mock()
        with patch('socket.socket',return_value=raw),patch('app.services.safe_http.tls_context',return_value=context):
            conn=PinnedHTTPSConnection(validate_url(URL),(Address(socket.AF_INET,PUBLIC),),time.monotonic()+5)
            with self.assertRaises(NetworkPolicyError):conn.connect()
        context.wrap_socket.assert_not_called()
        raw.close.assert_called()

    def test_certificate_failure_is_not_bypassed(self):
        raw=Mock();raw.getpeername.return_value=(PUBLIC,443);context=Mock()
        context.wrap_socket.side_effect=ssl.SSLCertVerificationError('fixture certificate mismatch')
        with patch('socket.socket',return_value=raw),patch('app.services.safe_http.tls_context',return_value=context):
            conn=PinnedHTTPSConnection(validate_url(URL),(Address(socket.AF_INET,PUBLIC),),time.monotonic()+5)
            with self.assertRaises(ssl.SSLCertVerificationError):conn.connect()
        raw.close.assert_called()

    def test_redirect_to_private_address_never_connects(self):
        reply=SafeResponse(302,CaseInsensitiveDict({'Location':'https://169.254.169.254/latest/meta-data'}),b'',URL)
        with patch.object(SafeSession,'_once',return_value=reply) as network:
            with self.assertRaises(NetworkPolicyError):SafeSession(Policy(domains=('regard.ru',))).get(URL)
        self.assertEqual(network.call_count,1)

    def test_dns_is_rechecked_on_each_redirect_hop(self):
        reply=SafeResponse(302,CaseInsensitiveDict({'Location':'/product/123456/other'}),b'',URL)
        self.dns.side_effect=[[dns(PUBLIC)],[dns('10.0.0.1')]]
        with patch.object(SafeSession,'_once',return_value=reply) as network:
            with self.assertRaises(NetworkPolicyError):SafeSession(Policy(domains=('regard.ru',))).get(URL)
        self.assertEqual(network.call_count,1)
        self.assertEqual(self.dns.call_count,2)

    def test_redirect_chain_has_three_transition_limit(self):
        reply=SafeResponse(302,CaseInsensitiveDict({'Location':'/again'}),b'',URL)
        with patch.object(SafeSession,'_once',return_value=reply) as network:
            with self.assertRaisesRegex(NetworkPolicyError,'перенаправлений'):SafeSession().get(URL)
        self.assertEqual(network.call_count,4)

    def test_authorization_is_never_forwarded_even_to_same_host_redirect(self):
        reply=SafeResponse(302,CaseInsensitiveDict({'Location':'/again'}),b'',URL)
        with patch.object(SafeSession,'_once',return_value=reply) as network:
            with self.assertRaises(NetworkPolicyError):SafeSession().get(URL,headers={'Authorization':'Bearer fixture'})
        self.assertEqual(network.call_count,1)

    def test_system_proxy_variables_cannot_redirect_the_transport(self):
        conn=self.connection(FakeResponse())
        with patch.dict('os.environ',{'HTTPS_PROXY':'http://127.0.0.1:8888','ALL_PROXY':'http://10.0.0.1:8080'}),patch(
                'requests.Session') as requests_session,patch('app.services.safe_http.PinnedHTTPSConnection',return_value=conn):
            SafeSession().get(URL)
        requests_session.assert_not_called()
        self.assertFalse(SafeSession.trust_env)

    def test_regional_cookie_survives_allowed_redirect_without_sharing_session(self):
        first=FakeResponse(b'',302,{'Location':'/product/123456/other','Set-Cookie':'PHPSESSID=fixture; Path=/; Secure'})
        second=FakeResponse(b'ok')
        connections=[self.connection(first),self.connection(second)]
        with patch('app.services.safe_http.PinnedHTTPSConnection',side_effect=connections):
            SafeSession(Policy(domains=('regard.ru',))).get(URL)
        self.assertIn('PHPSESSID=fixture',connections[1].request.call_args.kwargs['headers']['Cookie'])
        self.assertEqual(len(list(SafeSession().cookies)),0)

    def test_large_content_length_is_rejected_before_read(self):
        response=FakeResponse(b'not-read',headers={'Content-Length':'99999999'})
        conn=self.connection(response)
        with patch('app.services.safe_http.PinnedHTTPSConnection',return_value=conn):
            with self.assertRaises(NetworkPolicyError):SafeSession().get(URL)
        self.assertEqual(response.body.tell(),0);self.assertTrue(response.closed)

    def test_stream_without_length_is_bounded(self):
        response=FakeResponse(b'x'*100)
        with patch('app.services.safe_http.PinnedHTTPSConnection',return_value=self.connection(response)):
            with self.assertRaises(NetworkPolicyError):SafeSession().get(URL,max_bytes=16)
        self.assertTrue(response.closed)

    def test_compression_bomb_is_bounded_after_decompression(self):
        body=gzip.compress(b'x'*10000)
        self.assertLess(len(body),256)
        response=FakeResponse(body,headers={'Content-Encoding':'gzip','Content-Type':'text/plain'})
        with patch('app.services.safe_http.PinnedHTTPSConnection',return_value=self.connection(response)):
            with self.assertRaisesRegex(NetworkPolicyError,'Распакованный'):SafeSession().get(URL,max_bytes=256)
        self.assertTrue(response.closed)

    def test_normal_gzip_is_decoded(self):
        response=FakeResponse(gzip.compress(b'fixture'),headers={'Content-Encoding':'gzip','Content-Type':'text/plain'})
        with patch('app.services.safe_http.PinnedHTTPSConnection',return_value=self.connection(response)):
            self.assertEqual(SafeSession().get(URL).text,'fixture')

    def test_unsupported_binary_content_type_is_rejected_before_read(self):
        response=FakeResponse(b'not-read',headers={'Content-Type':'image/png'})
        with patch('app.services.safe_http.PinnedHTTPSConnection',return_value=self.connection(response)):
            with self.assertRaises(NetworkPolicyError):SafeSession().get(URL)
        self.assertEqual(response.body.tell(),0);self.assertTrue(response.closed)

    def test_read_timeout_closes_the_response_and_connection(self):
        response=FakeResponse()
        response.read1=Mock(side_effect=socket.timeout())
        conn=self.connection(response)
        with patch('app.services.safe_http.PinnedHTTPSConnection',return_value=conn):
            with self.assertRaises(TimeoutError):SafeSession().get(URL)
        self.assertTrue(response.closed);conn.abort.assert_called()

    def test_expired_deadline_starts_no_dns_or_socket(self):
        with self.assertRaises(TimeoutError):SafeSession().get(URL,deadline=time.monotonic()-1)
        self.socket.assert_not_called();self.dns.assert_not_called()

    def test_nix_lookup_uses_the_guarded_post_and_rejects_external_href(self):
        reply=SafeResponse(200,CaseInsensitiveDict({'Content-Type':'application/json'}),
                           json.dumps({'href':'/search/results'}).encode(),'https://www.nix.ru')
        with patch.object(SafeSession,'_once',return_value=reply) as network:
            self.assertEqual(resolved_search_url('nix','RTX 3060'),'https://www.nix.ru/search/results')
        self.assertEqual(network.call_args.args[0],'POST')
        reply.content=json.dumps({'href':'https://127.0.0.1/secret'}).encode()
        with patch.object(SafeSession,'_once',return_value=reply):
            with self.assertRaises(RuntimeError):resolved_search_url('nix','RTX 3060')

    def test_browser_diagnostics_exposes_security_disable(self):
        with patch('app.services.browser_offers.version',side_effect=ModuleNotFoundError),patch(
                'app.services.browser_offers.Path.read_text',side_effect=OSError):
            # package metadata is optional; no Chromium is launched.
            from importlib.metadata import PackageNotFoundError
            with patch('app.services.browser_offers.version',side_effect=PackageNotFoundError):
                result=browser_diagnostics()
        self.assertFalse(result['enabled'])
        self.assertEqual(result['security_status'],'disabled_pending_network_isolation')

    def test_browser_subresources_popups_and_cdp_cannot_start_without_isolation(self):
        from app.core.config import settings
        with patch.object(settings,'offers_browser_enabled',True),patch.object(settings,'offers_browser_cdp_url','http://127.0.0.1:9225'),patch(
                'app.services.browser_offers.launch_browser') as launch:
            with self.assertRaisesRegex(NetworkPolicyError,'изоляция'):
                with browser_context():pass
        launch.assert_not_called();self.socket.assert_not_called()

    def test_watchdog_prevents_a_request_after_its_deadline_fires(self):
        conn=self.connection(FakeResponse())
        class ExpiredTimer:
            def __init__(self,seconds,callback):self.callback=callback
            def start(self):self.callback()
            def cancel(self):pass
        with patch('app.services.safe_http.PinnedHTTPSConnection',return_value=conn),patch(
                'app.services.safe_http.Timer',ExpiredTimer):
            with self.assertRaises(TimeoutError):SafeSession().get(URL)
        conn.request.assert_not_called()
        conn.abort.assert_called()

    def test_timeout_after_tls_handshake_closes_the_tls_socket(self):
        raw=Mock();raw.getpeername.return_value=(PUBLIC,443);context=Mock()
        secure=context.wrap_socket.return_value
        with patch('socket.socket',return_value=raw),patch('app.services.safe_http.tls_context',return_value=context),patch(
                'app.services.safe_http.remaining',side_effect=[3,3,TimeoutError('deadline fixture')]):
            conn=PinnedHTTPSConnection(validate_url(URL),(Address(socket.AF_INET,PUBLIC),),time.monotonic()+5)
            with self.assertRaises(TimeoutError):conn.connect()
        secure.close.assert_called()

    def test_product_price_verification_runs_through_the_pinned_transport(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from app.db.base import Base
        from app.db.models import StoreOffer
        from app.core.price_time import db_now
        from app.services.price_verification import verify_build_prices
        engine=create_engine('sqlite://');Base.metadata.create_all(engine)
        try:
            with Session(engine) as db:
                row=StoreOffer(id=1,source='regard',name='DeepCool AG400',category='cooler',
                               price_rub=846,url=URL,condition='new',observed_at=db_now(),origin='public_page',attributes='{}')
                db.add(row);db.commit()
                body='<script type="application/ld+json">'+json.dumps({'@type':'Product','name':row.name,
                      'url':URL,'offers':{'price':1752,'priceCurrency':'RUB'}})+'</script>'
                conn=self.connection(FakeResponse(body.encode()))
                with patch('app.services.safe_http.PinnedHTTPSConnection',return_value=conn):
                    self.assertTrue(verify_build_prices(db,{'parts':[{'offer_id':1}]}))
                self.assertEqual(row.price_rub,1752)
                self.assertEqual(json.loads(row.attributes)['price_verification']['status'],'verified')
                self.assertEqual(conn.request.call_args.kwargs['headers']['Host'],'www.regard.ru')
        finally:engine.dispose()


if __name__=='__main__':unittest.main()
