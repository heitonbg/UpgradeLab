"""Free HTTP discovery: search engines supply URLs, shops supply prices.

RSS is a public Bing search format. No paid API, user browser, proxy account,
CAPTCHA token, or third-party copy of a product price is involved.
"""
import time
from concurrent.futures import ThreadPoolExecutor
from app.core.price_time import db_now, iso_utc
from urllib.parse import urlencode
from xml.etree import ElementTree
from app.core.stores import STORES
from app.schemas.offers import store_url
from app.services.store_providers import fetch, parse_html
from app.services.browser_offers import discover_links, challenge

ENGINES = {
    'bing_rss': ('https://www.bing.com/search', 'q'),
    'duckduckgo': ('https://html.duckduckgo.com/html/', 'q'),
    'google': ('https://www.google.com/search', 'q'),
    'yandex': ('https://yandex.ru/search/', 'text'),
}
REDIRECT_HOSTS = {
    'bing_rss': {'www.bing.com', 'bing.com'},
    'duckduckgo': {'html.duckduckgo.com', 'duckduckgo.com', 'www.duckduckgo.com'},
    'google': {'www.google.com', 'google.com', 'consent.google.com'},
    'yandex': {'yandex.ru', 'www.yandex.ru', 'yandex.com', 'www.yandex.com', 'ya.ru'},
}


def rss_links(source, body):
    if '<!DOCTYPE' in body.upper() or '<!ENTITY' in body.upper():
        raise RuntimeError('Небезопасный формат поисковой выдачи')
    root = ElementTree.fromstring(body)
    result = []
    for node in root.findall('.//item/link'):
        url = (node.text or '').strip()
        try:
            valid = store_url(source, url)
        except ValueError:
            valid = False
        if valid and url not in result:
            result.append(url)
    return result[:5]


def public_links(source, query, deadline):
    search_deadline = min(deadline-3, time.monotonic()+7)
    if time.monotonic() >= search_deadline:
        return [], []
    def lookup(engine):
        base, parameter = ENGINES[engine]
        params = {parameter: f'{query} site:{STORES[source]["domain"]}'}
        if engine == 'bing_rss':
            params['format'] = 'rss'
        try:
            if time.monotonic() >= search_deadline:
                raise TimeoutError('Время поиска ссылок истекло')
            body = fetch(base+'?'+urlencode(params), deadline=min(search_deadline, time.monotonic()+3),
                         redirect_hosts=REDIRECT_HOSTS[engine])
            if challenge(body):
                raise RuntimeError('Поисковик ограничил доступ')
            links = rss_links(source, body) if engine == 'bing_rss' else discover_links(source, body, 5)
            return links, {'engine': engine, 'links': len(links), 'method': 'http'}
        except Exception as error:
            return [], {'engine': engine, 'links': 0, 'method': 'http', 'message': str(error)[:160]}
    with ThreadPoolExecutor(max_workers=2) as executor:
        attempts = list(executor.map(lookup, ENGINES))
    links = list(dict.fromkeys(url for urls, _ in attempts for url in urls))
    return links[:5], [info for _, info in attempts]


def discover_public_offers(source, query, category, deadline):
    links, engines = public_links(source, query, deadline)
    details = {'method': 'web', 'links': links, 'discovered': len(links), 'verified': 0,
               'search_engines': engines}
    found, errors = {}, []
    for url in links:
        if time.monotonic() >= deadline:
            break
        try:
            body = fetch(url, store=source, deadline=min(deadline, time.monotonic()+4), product=True)
            rows = parse_html(source, body, category, url, require_single_price=True)
            for row in rows:
                row.attributes['price_verification'] = {'status': 'verified',
                    'checked_at': iso_utc(db_now()), 'method': 'http_discovered_product'}
                found[row.url] = row
        except Exception as error:
            errors.append(str(error)[:160])
    details['verified'] = len(found)
    if not found:
        details['error'] = (f'HTTP-поиск нашёл ссылок: {len(links)}; цена товара не подтверждена.'+
                            (' '+errors[-1] if errors else ''))
    return list(found.values()), details
