"""Read public store pages in an isolated browser context; discover product URLs
through a search engine, then verify prices at the store, never in snippets."""
import base64
import ipaddress
import time
from datetime import datetime
from contextlib import contextmanager
from threading import BoundedSemaphore
from urllib.parse import parse_qs, unquote, urlencode, urljoin, urlsplit
from bs4 import BeautifulSoup
from app.core.config import settings
from app.core.stores import STORES
from app.schemas.offers import store_url
from app.services.store_providers import parse_html, resolved_search_url
from app.services.search_time import remaining

browser_slots = BoundedSemaphore(2)
SEARCH_HOSTS = {"www.bing.com", "bing.com", "www.google.com", "google.com", "yandex.ru", "www.yandex.ru"}


def unwrap_search_link(href):
    url = urljoin("https://www.bing.com", href)
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
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


@contextmanager
def browser_context(deadline=None):
    if not settings.offers_browser_enabled:
        raise RuntimeError("Браузерный поиск отключён на сервере")
    if not browser_slots.acquire(timeout=remaining(deadline, 5 if deadline else 30)):
        raise RuntimeError("Браузер занят; повторите поиск выбранной площадки")
    try:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("Установите backend/requirements-browser.txt и браузер Edge/Chromium")
        with sync_playwright() as playwright:
            owned = not settings.offers_browser_cdp_url
            try:
                browser = (playwright.chromium.connect_over_cdp(settings.offers_browser_cdp_url, timeout=max(1,int(remaining(deadline,5)*1000)))
                           if not owned else playwright.chromium.launch(channel=settings.offers_browser_channel or None, headless=True,
                                timeout=max(1,int(remaining(deadline,8)*1000))))
            except Exception:
                raise RuntimeError("Не удалось запустить/подключить браузер; проверьте настройки Edge/Chromium")
            context = browser.new_context(locale="ru-RU", accept_downloads=False)

            def public_only(route):
                parsed = urlsplit(route.request.url)
                host = parsed.hostname or ""
                if parsed.scheme not in ("http", "https", "data", "blob") or host in ("localhost", "metadata.google.internal") or host.endswith(".local"):
                    return route.abort()
                try:
                    if ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_loopback:
                        return route.abort()
                except ValueError:
                    pass
                return route.continue_()

            context.route("**/*", public_only)
            try:
                yield context
            finally:
                context.close()
                if owned:
                    browser.close()
    finally:
        browser_slots.release()


def read_page(page, source, url, search=False, deadline=None):
    if not allowed_navigation(url, source, search):
        raise RuntimeError("Адрес не принадлежит выбранной площадке")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=max(1,int(remaining(deadline,settings.offers_browser_timeout_ms/1000)*1000)))
    except Exception:
        # A navigation timeout may still leave a readable document.
        if not allowed_navigation(page.url, source, search):
            raise RuntimeError("Браузер не открыл страницу площадки")
    if not allowed_navigation(page.url, source, search):
        raise RuntimeError("Площадка перенаправила браузер за пределы разрешённых адресов")
    poll_deadline = time.monotonic() + remaining(deadline,4)
    html = ""
    while time.monotonic() < poll_deadline:
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
        page.wait_for_timeout(min(500,max(1,int((poll_deadline-time.monotonic())*1000))))
    return html


def search_browser(source, query, category, discovery_only=False, deadline=None):
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
                                    'checked_at':datetime.utcnow().isoformat(),'method':'browser_product_page'}
                            verified.extend(products)
                        except Exception:
                            continue
                    rows=verified
                    if not rows:
                        raise RuntimeError('Карточки поиска Avito не дали подтвердить цену конкретных объявлений')
                details["verified"] = len(rows)
                return rows, details
            except Exception as error:
                direct_error = str(error)
        search_base, parameter = {"bing":("https://www.bing.com/search", "q"),
                                  "google":("https://www.google.com/search", "q"),
                                  "yandex":("https://yandex.ru/search/", "text")}[settings.offers_browser_search_engine]
        lookup = search_base + "?" + urlencode({parameter: f"{query} site:{STORES[source]['domain']}"})
        html = read_page(page, source, lookup, search=True,**kwargs)
        links = discover_links(source, html, min(settings.offers_browser_product_limit, 5))
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
                            'checked_at': datetime.utcnow().isoformat(), 'method': 'browser_product_page'}
                        verified[row.url] = row
            except Exception:
                continue
        details["verified"] = len(verified)
        if not verified:
            details["error"] = f"Поиск нашёл карточек: {len(links)}; подтвердить цену на площадке не удалось. " + direct_error
        return list(verified.values()), details


def read_browser_product(source, url, category, deadline=None):
    kwargs={'deadline':deadline} if deadline is not None else {}
    with browser_context(**kwargs) as context:
        page = context.new_page()
        html = read_page(page, source, url,**kwargs)
        rows = parse_html(source, html, category, page.url, require_single_price=True)
        for row in rows:
            row.attributes['price_verification'] = {'status': 'verified',
                'checked_at': datetime.utcnow().isoformat(), 'method': 'browser_product_page'}
        return rows
