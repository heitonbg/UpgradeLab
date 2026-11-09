"""Browser extraction helpers retained for fixtures and a future isolated runtime.
Native browser/CDP contexts are disabled until OS egress isolation is verified."""
import base64
import time
import sys
import logging
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError
from app.core.price_time import db_now, iso_utc
from contextlib import contextmanager
from urllib.parse import parse_qs, unquote, urlencode, urljoin, urlsplit
from bs4 import BeautifulSoup
from app.core.config import settings
from app.core.stores import STORES
from app.schemas.offers import store_url
from app.services.store_providers import parse_html, resolved_search_url
from app.services.search_time import remaining
from app.services.network_policy import NetworkPolicyError

last_launch_error = None
logger = logging.getLogger(__name__)
SEARCH_HOSTS = {"www.bing.com", "bing.com", "www.google.com", "google.com", "yandex.ru", "www.yandex.ru",
                "duckduckgo.com", "html.duckduckgo.com"}
BROWSER_SECURITY_MESSAGE = ('Браузерный поиск отключён: не подтверждена сетевая изоляция Chromium/CDP. '
                            'Используйте HTTP-поиск или HTTP-импорт; браузеру нужен проверенный изолированный egress.')
SEARCH_ENGINES = {"bing": ("https://www.bing.com/search", "q"),
                  "google": ("https://www.google.com/search", "q"),
                  "yandex": ("https://yandex.ru/search/", "text"),
                  "duckduckgo": ("https://html.duckduckgo.com/html/", "q")}


def unwrap_search_link(href):
    url = urljoin("https://www.bing.com", href)
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    if parsed.path in ('/l/', '/l') and query.get('uddg'):
        return query['uddg'][0]
    if parsed.hostname in {"bing.com", "www.bing.com"} and parsed.path == "/ck/a":
        encoded = query.get("u", [""])[0]
        if encoded.startswith("a1"):
            try:
                return base64.urlsafe_b64decode(encoded[2:] + "=" * (-len(encoded[2:]) % 4)).decode()
            except (ValueError, UnicodeError):
                return ""
    if parsed.hostname in SEARCH_HOSTS and parsed.path in ("/url", "/clck/jsredir"):
        return query.get("q", query.get("url", [""]))[0]
    return url


def discover_links(source, html, limit=3):
    soup = BeautifulSoup(html, "html.parser")
    found = []
    # Search output is used only for URLs. Deliberately never parse snippet prices.
    for anchor in soup.select("a[href]"):
        url = unwrap_search_link(anchor["href"])
        try:
            valid = len(url) <= 2000 and store_url(source, url)
        except ValueError:
            valid = False
        if valid and url not in found:
            found.append(url)
        if len(found) == limit:
            break
    return found


def challenge(html):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True).lower() if soup.title else ""
    text = soup.get_text(" ", strip=True).lower()[:5000]
    return (any(marker in title for marker in ("captcha", "не робот", "доступ ограничен", "403", "access denied")) or
            any(marker in text for marker in ("подтвердите, что вы не робот", "доступ к сайту", "unusual traffic", "verify you are human", "доступ ограничен: проверка")))


def allowed_navigation(url, source, search=False):
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    domain = STORES[source]["domain"]
    return parsed.scheme == "https" and not parsed.username and not parsed.password and parsed.port in (None,443) and (
        host == domain or host.endswith("." + domain) or search and host in SEARCH_HOSTS)


def browser_diagnostics():
    """Inspect installation without launching Chromium or exposing environment secrets."""
    info = {'enabled': False, 'configured_enabled': settings.offers_browser_enabled,
            'security_status': 'disabled_pending_network_isolation', 'security_message': BROWSER_SECURITY_MESSAGE,
            'configured_channel': settings.offers_browser_channel,
            'platform': sys.platform, 'package_version': None, 'bundled_installed': False}
    try:
        info['package_version'] = version('playwright')
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            info['bundled_installed'] = Path(playwright.chromium.executable_path).is_file()
    except (ImportError, PackageNotFoundError, OSError, RuntimeError):
        pass
    info['last_launch_error'] = last_launch_error
    for field, paths in {
        'memory_limit_bytes': ('/sys/fs/cgroup/memory.max', '/sys/fs/cgroup/memory/memory.limit_in_bytes'),
        'memory_current_bytes': ('/sys/fs/cgroup/memory.current', '/sys/fs/cgroup/memory/memory.usage_in_bytes'),
        'pids_limit': ('/sys/fs/cgroup/pids.max',), 'pids_current': ('/sys/fs/cgroup/pids.current',),
    }.items():
        for filename in paths:
            try:
                value = Path(filename).read_text().strip()
                info[field] = int(value) if value.isdigit() else value
                break
            except (OSError, ValueError):
                continue
    return info


def launch_browser(playwright, deadline):
    # Direct calls must respect the same fail-closed browser policy.
    remaining(deadline, 5)
    raise NetworkPolicyError(BROWSER_SECURITY_MESSAGE)


@contextmanager
def browser_context(deadline=None):
    # URL interception cannot constrain all native Chromium channels or pin
    # DNS. No browser or external CDP process is used without OS egress isolation.
    remaining(deadline,5)
    raise NetworkPolicyError(BROWSER_SECURITY_MESSAGE)
    yield  # A contextmanager generator; intentionally unreachable in this runtime.


def read_page(page, source, url, search=False, deadline=None):
    if not allowed_navigation(url, source, search):
        raise RuntimeError("Адрес не принадлежит выбранной площадке")
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=max(1,int(remaining(deadline,settings.offers_browser_timeout_ms/1000)*1000)))
    except Exception:
        # A navigation timeout may still leave a readable document.
        if not allowed_navigation(page.url, source, search):
            raise RuntimeError("Браузер не открыл страницу площадки")
        response = None
    if response is not None and response.status in (401, 403, 429, 439):
        raise RuntimeError(f"Браузер: площадка вернула HTTP {response.status}")
    if not allowed_navigation(page.url, source, search):
        raise RuntimeError("Площадка перенаправила браузер за пределы разрешённых адресов")
    # Navigation can time out after a usable search document is already drawn.
    # Inspect it once before enforcing the polling deadline; otherwise each
    # engine's whole result is thrown away merely because domcontentloaded was late.
    poll_deadline = min(deadline, time.monotonic()+4) if deadline is not None else time.monotonic()+4
    html = ""
    while True:
        html = page.content()
        if len(html) > 8 * 1024 * 1024:
            raise RuntimeError("Страница слишком большая")
        if challenge(html):
            raise RuntimeError("Браузер получил CAPTCHA или запрет доступа; требуется проверка площадки")
        if search:
            if discover_links(source, html):
                return html
        else:
            try:
                parse_html(source, html, "GPU", page.url)
                return html
            except RuntimeError:
                pass
        if time.monotonic() >= poll_deadline:
            break
        page.wait_for_timeout(min(500,max(1,int((poll_deadline-time.monotonic())*1000))))
    return html


def search_engine_links(page, source, query, deadline):
    """Merge product URLs from all engines, reserving time to read the products."""
    attempts, combined = [], []
    engines = list(dict.fromkeys([settings.offers_browser_search_engine, *SEARCH_ENGINES]))
    search_deadline = min(deadline - 4, time.monotonic() + 12)
    for index, engine in enumerate(engines):
        if time.monotonic() >= search_deadline:
            break
        base, parameter = SEARCH_ENGINES[engine]
        lookup = base + '?' + urlencode({parameter: f'{query} site:{STORES[source]["domain"]}'})
        try:
            engine_deadline = time.monotonic() + (search_deadline - time.monotonic()) / (len(engines) - index)
            html = read_page(page, source, lookup, search=True, deadline=engine_deadline)
            links = discover_links(source, html, min(settings.offers_browser_product_limit, 5))
            attempts.append({'engine': engine, 'links': len(links)})
            combined.extend(links)
        except (RuntimeError, TimeoutError) as error:
            attempts.append({'engine': engine, 'links': 0, 'message': str(error)[:160]})
    return list(dict.fromkeys(combined)), attempts


def search_browser(source, query, category, discovery_only=False, deadline=None):
    deadline = deadline or time.monotonic() + 45
    details = {"method": "discovery" if discovery_only else "browser", "discovered": 0, "verified": 0, "links": []}
    kwargs={'deadline':deadline} if deadline is not None else {}
    with browser_context(**kwargs) as context:
        page = context.new_page()
        direct_error = ""
        if not discovery_only:
            try:
                html = read_page(page, source, resolved_search_url(source, query,**kwargs),**kwargs)
                rows = parse_html(source, html, category, page.url)
                if source == 'avito':
                    # Read actual listings, so a former HTTP failure can be
                    # replaced by a successful browser confirmation of its price.
                    if category in ('CPU','GPU'):
                        from app.services.offers import signature,component_listing
                        model=signature(query,category)
                        rows=[row for row in rows if component_listing(row.name) and
                              (not model or signature(row.name,category)==model)]
                    verified=[]
                    for candidate in rows[:min(settings.offers_browser_product_limit,5)]:
                        try:
                            remaining(deadline,5)
                            product_html=read_page(page,source,candidate.url,**kwargs)
                            products=parse_html(source,product_html,category,page.url,require_single_price=True)
                            for product in products:
                                product.attributes['price_verification']={'status':'verified',
                                    'checked_at':iso_utc(db_now()),'method':'browser_product_page'}
                            verified.extend(products)
                        except Exception:
                            continue
                    rows=verified
                    if not rows:
                        raise RuntimeError('Карточки поиска Avito не дали подтвердить цену конкретных объявлений')
                details["found"] = len(rows)
                details["verified"] = sum(row.attributes.get('price_verification', {}).get('status') == 'verified' for row in rows)
                return rows, details
            except Exception as error:
                direct_error = str(error)
        links, engines = search_engine_links(page, source, query, deadline)
        details['search_engines'] = engines
        details["discovered"] = len(links)
        details["links"] = links
        verified = {}
        for url in links:
            try:
                remaining(deadline,5)
                html = read_page(page, source, url,**kwargs)
                for row in parse_html(source, html, category, page.url, require_single_price=True):
                    if row.url.rstrip('/').split('?')[0] == page.url.rstrip('/').split('?')[0]:
                        row.attributes['price_verification'] = {'status': 'verified',
                            'checked_at': iso_utc(db_now()), 'method': 'browser_product_page'}
                        verified[row.url] = row
            except Exception:
                continue
        details["verified"] = len(verified)
        if not verified:
            details["error"] = f"Поиск нашёл карточек: {len(links)}; подтвердить цену на площадке не удалось. " + direct_error
        return list(verified.values()), details


def read_browser_product(source, url, category, deadline=None):
    deadline = deadline or time.monotonic() + 20
    kwargs={'deadline':deadline} if deadline is not None else {}
    with browser_context(**kwargs) as context:
        page = context.new_page()
        html = read_page(page, source, url,**kwargs)
        rows = parse_html(source, html, category, page.url, require_single_price=True)
        for row in rows:
            row.attributes['price_verification'] = {'status': 'verified',
                'checked_at': iso_utc(db_now()), 'method': 'browser_product_page'}
        return rows
