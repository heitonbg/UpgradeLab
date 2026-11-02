"""Deterministic store/browser extraction tests; no external network required."""
import base64
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.store_providers import parse_html, fetch
from app.services.browser_offers import discover_links, search_browser, allowed_navigation, challenge
from app.schemas.offers import SearchOffers
from app.services.offers import component_listing, signature
from pydantic import ValidationError


class StoreParsingTests(unittest.TestCase):
    def test_avito_direct_browser_search_confirms_the_listing_price(self):
        url='https://www.avito.ru/moskva/tovary_dlya_kompyutera/rtx_3060_123456789'
        def markup(price):
            return '<script type="application/ld+json">'+json.dumps({'@type':'Product','name':'GeForce RTX 3060 12GB',
                'url':url,'offers':{'price':price,'priceCurrency':'RUB','url':url}})+'</script>'
        def read(page,source,target,search=False):
            page.url=target
            return markup(17500 if target==url else 12000)
        with patch('app.services.browser_offers.browser_context') as context,patch('app.services.browser_offers.read_page',side_effect=read):
            page=Mock();context.return_value.__enter__.return_value.new_page.return_value=page
            rows,details=search_browser('avito','RTX 3060','GPU')
        self.assertEqual(rows[0].price_rub,17500)
        self.assertEqual(rows[0].attributes['price_verification']['method'],'browser_product_page')
        self.assertEqual(details['verified'],1)

    def test_gpu_is_not_whole_pc_laptop_or_ti_variant(self):
        self.assertFalse(component_listing('ПЭВМ OLDI HOME Ryzen 5800X RTX 5060 8GB'))
        self.assertFalse(component_listing('Lenovo LOQ i7 RTX 5060 8Gb KBD RU'))
        self.assertTrue(component_listing('Видеокарта Gigabyte GeForce RTX 5060 8Gb'))
        self.assertNotEqual(signature('RTX5060Ti','GPU'),signature('RTX 5060','GPU'))

    def test_regard_offer_catalog_skips_sold_out(self):
        offers = [{"@type":"Offer", "name":"GeForce RTX 5060 8GB", "url":f"https://www.regard.ru/product/{index}/gpu", "price":price,
                   "priceCurrency":"RUB", "availability":availability} for index,price,availability in [(100,50000,"InStock"),(101,1000,"OutOfStock")]]
        html='<script type="application/ld+json">'+json.dumps({"@type":"OfferCatalog","itemListElement":offers})+'</script>'
        rows=parse_html('regard',html,'GPU')
        self.assertEqual([(row.price_rub,row.url) for row in rows],[(50000,'https://www.regard.ru/product/100/gpu')])

    def test_oldi_scopes_card_price_not_cart_or_old_price(self):
        html='''<div class="price">0 р.</div><div class="product-item"><a class="title" href="/catalog/element/123456/">GeForce RTX 5060 8GB</a><span class="old-price">90000</span><div class="price"><strong>45 000 <span>c</span></strong></div></div>'''
        rows=parse_html('oldi',html,'GPU')
        self.assertEqual(rows[0].price_rub,45000)

    def test_kns_sold_out_last_price_is_not_available_offer(self):
        html='''<div itemscope itemtype="https://schema.org/Product"><h1 itemprop="name">RTX 5060</h1><div itemprop="offers" itemscope itemtype="https://schema.org/Offer"><meta itemprop="price" content="10000"><meta itemprop="priceCurrency" content="RUB"><meta itemprop="availability" content="https://schema.org/SoldOut"><link itemprop="url" href="https://www.kns.ru/product/test/"></div></div>'''
        with self.assertRaises(RuntimeError):
            parse_html('kns',html,'GPU')
        rows=parse_html('kns',html.replace('SoldOut','InStock'),'GPU')
        self.assertEqual(rows[0].price_rub,10000)

    def test_search_links_decode_bing_but_do_not_trust_snippet_prices(self):
        url='https://www.dns-shop.ru/product/123456/geforce-rtx-5060/'
        encoded=base64.urlsafe_b64encode(url.encode()).decode().rstrip('=')
        html='<a href="https://www.bing.com/ck/a?'+urlencode({'u':'a1'+encoded})+'">RTX 5060 от 1 ₽</a><a href="http://127.0.0.1/private">other</a>'
        self.assertEqual(discover_links('dns',html),[url])
        self.assertFalse(allowed_navigation('http://127.0.0.1/private','dns'))
        self.assertFalse(allowed_navigation('https://dns-shop.ru.evil.example/product/123/','dns'))

    def test_browser_discovery_reads_actual_product_and_excludes_related_offer(self):
        url='https://www.dns-shop.ru/product/123456/geforce-rtx-5060/'
        graph=[{"@type":"Product","name":"GeForce RTX 5060 8GB","url":link,"offers":{"price":price,"priceCurrency":"RUB","url":link}} for link,price in [(url,50000),('https://www.dns-shop.ru/product/999999/related/',100)]]
        def read(page,source,target,search=False):
            page.url=target
            return f'<a href="{url}">1 ₽</a>' if search else '<script type="application/ld+json">'+json.dumps(graph)+'</script>'
        with patch('app.services.browser_offers.browser_context') as context, patch('app.services.browser_offers.read_page',side_effect=read):
            page=Mock()
            context.return_value.__enter__.return_value.new_page.return_value=page
            rows,details=search_browser('dns','RTX 5060','GPU',True)
        self.assertEqual([row.price_rub for row in rows],[50000])
        self.assertEqual(rows[0].attributes['price_verification']['method'],'browser_product_page')
        self.assertEqual(details['discovered'],1)
        self.assertEqual(details['verified'],1)

    def test_challenge_and_browser_batch_are_explicit(self):
        self.assertTrue(challenge('<title>Доступ ограничен: проверка безопасности</title>'))
        self.assertFalse(challenge('<title>Магазин</title><script src="smartcaptcha.js"></script><h1>RTX 5060</h1>'))
        with self.assertRaises(ValidationError):
            SearchOffers(query='RTX 5060',category='GPU',method='browser')

    def test_redirects_only_within_store_and_no_feed_token_forwarding(self):
        first=Mock(status_code=302,headers={'Location':'https://www.regard.ru/catalog/1013?search=RTX+5060'})
        first.__enter__=Mock(return_value=first);first.__exit__=Mock(return_value=False)
        second=Mock(status_code=200,encoding='utf-8');second.iter_content.return_value=[b'<html>test</html>']
        second.__enter__=Mock(return_value=second);second.__exit__=Mock(return_value=False)
        with patch('app.services.store_providers.requests.get',side_effect=[first,second]) as request:
            self.assertEqual(fetch('https://www.regard.ru/catalog?search=test',store='regard'),'<html>test</html>')
            self.assertEqual(request.call_count,2)
        with patch('app.services.store_providers.requests.get',return_value=first) as request:
            with self.assertRaises(RuntimeError):
                fetch('https://feed.example/offers',token='secret')
            self.assertEqual(request.call_count,1)


if __name__=='__main__':
    unittest.main()
