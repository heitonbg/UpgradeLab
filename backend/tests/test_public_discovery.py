import sys
import time
import json
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.public_discovery import rss_links, discover_public_offers
from app.services.store_providers import parse_html, pause_source, source_blocked


class PublicDiscoveryTests(unittest.TestCase):
    url = 'https://www.avito.ru/moskva/tovary_dlya_kompyutera/ryzen_7_5700x3d_123456789'

    def test_rss_extracts_only_real_store_urls_and_never_uses_snippet_price(self):
        xml = f'<rss><channel><item><link>{self.url}</link><description>CPU за 1 рубль</description></item><item><link>https://avito.ru.evil.example/item_123</link></item></channel></rss>'
        self.assertEqual(rss_links('avito', xml), [self.url])

    def test_discovery_uses_product_page_price_and_deduplicates_search_links(self):
        html = '<script type="application/ld+json">'+json.dumps({'@type':'Product','name':'AMD Ryzen 7 5700X3D',
            'url':self.url,'offers':{'price':18000,'priceCurrency':'RUB','url':self.url}})+'</script>'
        with patch('app.services.public_discovery.public_links',return_value=([self.url],[])),patch(
                'app.services.public_discovery.fetch',return_value=html):
            rows, details = discover_public_offers('avito','5700X3D','CPU',time.monotonic()+10)
        self.assertEqual([row.price_rub for row in rows],[18000])
        self.assertEqual(details['verified'],1)
        self.assertEqual(rows[0].attributes['price_verification']['method'],'http_discovered_product')

    def test_blocked_product_returns_urls_but_does_not_invent_an_offer(self):
        with patch('app.services.public_discovery.public_links',return_value=([self.url],[])),patch(
                'app.services.public_discovery.fetch',side_effect=RuntimeError('HTTP 403')):
            rows, details = discover_public_offers('avito','5700X3D','CPU',time.monotonic()+10)
        self.assertEqual(rows,[])
        self.assertEqual(details['links'],[self.url])
        self.assertIn('403',details['error'])

    def test_included_captcha_script_does_not_discard_a_real_product_price(self):
        html = '<script src="/showcaptcha.js"></script><script>const text="доступ ограничен"</script>'
        html += '<script type="application/ld+json">'+json.dumps({'@type':'Product','name':'AMD Ryzen 7 5700X3D',
            'url':self.url,'offers':{'price':18000,'url':self.url}})+'</script>'
        rows = parse_html('avito',html,'CPU',self.url,require_single_price=True)
        self.assertEqual(rows[0].price_rub,18000)

    def test_explicit_challenge_is_not_a_product_even_if_cached_metadata_has_price(self):
        with self.assertRaisesRegex(RuntimeError,'CAPTCHA'):
            parse_html('kns','<h1>Доступ ограничен</h1>','CPU')

    def test_search_cooldown_does_not_claim_that_product_pages_were_also_checked(self):
        with patch('app.services.store_providers._blocked_until',{}):
            pause_source('avito')
            self.assertTrue(source_blocked('avito'))
            self.assertFalse(source_blocked('avito',product=True))
            pause_source('avito',product=True)
            self.assertTrue(source_blocked('avito',product=True))

    def test_http_search_can_follow_only_its_explicit_search_engine_domains(self):
        from app.services.store_providers import fetch
        from app.services.safe_http import SafeSession,SafeResponse
        from app.services.network_policy import Address
        from requests.structures import CaseInsensitiveDict
        import socket
        first=SafeResponse(302,CaseInsensitiveDict({'Location':'https://www.google.com/search?q=test&gbv=1'}),b'','https://google.com')
        second=SafeResponse(200,CaseInsensitiveDict(),b'<html>results</html>','https://www.google.com')
        with patch('app.services.safe_http.resolve_public',return_value=(Address(socket.AF_INET,'93.184.216.34'),)),patch.object(
                SafeSession,'_once',side_effect=[first,second]):
            self.assertEqual(fetch('https://google.com/search?q=test',redirect_hosts={'www.google.com'}),'<html>results</html>')
        first.headers['Location']='https://unrelated.example/search'
        with patch('app.services.safe_http.resolve_public',return_value=(Address(socket.AF_INET,'93.184.216.34'),)),patch.object(
                SafeSession,'_once',return_value=first):
            with self.assertRaises(RuntimeError):
                fetch('https://google.com/search?q=test',redirect_hosts={'www.google.com'})
