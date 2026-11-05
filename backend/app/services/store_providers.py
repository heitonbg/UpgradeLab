"""Public markup adapters with no paid proxy or scraping service.
Challenges and unavailable pages are errors, never empty successful searches."""
import json
import re
from datetime import datetime
from urllib.parse import urlencode, urljoin, urlsplit
from bs4 import BeautifulSoup, SoupStrainer
import requests
import time
from threading import Lock
from pydantic import ValidationError
from app.schemas.offers import OfferInput
from app.core.stores import STORES
from app.services.search_time import remaining, request_timeout

_blocked_until = {}
_block_lock = Lock()


def source_blocked(source, product=False):
    with _block_lock:
        key = (source, 'product') if product else source
        return _blocked_until.get(key, 0) > time.monotonic()


def pause_source(source, product=False):
    with _block_lock:
        key = (source, 'product') if product else source
        _blocked_until[key] = time.monotonic() + 600


def search_url(source, query):
    store = STORES[source]
    if source == "nix":
        return store["search"] + "?section=video_cards_all#" + urlencode({"keywords": query})
    return store["search"] + "?" + urlencode({store["query"]: query})


def resolved_search_url(source, query, deadline=None):
    if source != "nix":
        return search_url(source, query)
    # This read-only search is the same operation used by NIX's public form.
    response = requests.post("https://www.nix.ru/scripts/action.php/FastSearch/fullTextSearch",
                             data={"keywords": query}, timeout=request_timeout(deadline), allow_redirects=False)
    response.raise_for_status()
    url = urljoin("https://www.nix.ru", response.json()["href"])
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ("www.nix.ru", "nix.ru") or parsed.username or parsed.password or parsed.port not in (None,443):
        raise RuntimeError("Некорректный адрес поиска НИКС")
    return url


def fetch(url, params=None, token=None, store=None, deadline=None, product=False, redirect_hosts=()):
    remaining(deadline, 5)
    # Some storefronts set a region/session cookie before redirecting to the
    # search page. Retain it for this request without sharing users' sessions.
    with requests.Session() as session:
        return _fetch_session(session, url, params, token, store, deadline, product, redirect_hosts)


def _fetch_session(session, url, params=None, token=None, store=None, deadline=None, product=False, redirect_hosts=()):
    # URLs originate only from fixed store hosts or administrator configuration.
    # Limit response size and do not follow redirects off the configured host.
    headers = {"User-Agent": "UpgradeLab/1.0", "Accept-Language": "ru-RU"}
    if store and source_blocked(store, product=product):
        raise RuntimeError('Площадка ранее ограничила доступ; повторные запросы приостановлены на 10 минут')
    if token:
        headers["Authorization"] = "Bearer " + token
    for _ in range(4):
        with session.get(url, params=params, timeout=request_timeout(deadline), stream=True,
                          headers=headers, allow_redirects=False) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                location = urljoin(url, response.headers.get("Location", ""))
                parsed = urlsplit(location)
                domain = STORES[store]["domain"] if store else ""
                host = parsed.hostname or ""
                allowed = (store and (host == domain or host.endswith('.'+domain))) or host in redirect_hosts
                if token or parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None,443) or not allowed:
                    raise RuntimeError("Источник перенаправил запрос за пределы площадки")
                url, params = location, None
                continue
            if response.status_code in (401, 403, 429, 439):
                if store:
                    pause_source(store, product=product)
                raise RuntimeError(f"Площадка ограничила доступ (HTTP {response.status_code})")
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_content(65536):
                remaining(deadline, 5)
                content.extend(chunk)
                if len(content) > 8 * 1024 * 1024:
                    raise RuntimeError("Ответ источника слишком большой")
            encoding = response.encoding if response.encoding and response.encoding.lower() not in ("iso-8859-1", "ascii") else "utf-8"
            return content.decode(encoding, errors="replace")
    raise RuntimeError("Слишком много перенаправлений площадки")


def money(value):
    if isinstance(value, (int, float)):
        return round(value)
    value = re.sub(r"[^0-9.,]", "", str(value))
    # Price markup uses a decimal dot/comma, no ambiguous thousands conversion.
    return round(float(value.replace(",", ".")))


def parse_html(source, html, category, page_url=None, require_single_price=False):
    # A link to a CAPTCHA script is not a challenge. Shops include those scripts
    # on ordinary product pages too; inspect visible text instead of JavaScript.
    visible = re.sub(r'<(script|style)\b[^>]*>.*?</\1\s*>', '', html, flags=re.I|re.S)
    visible = re.sub(r'<[^>]+>', ' ', visible).lower().replace('\xa0', ' ')[:5000]
    if any(marker in visible for marker in ("подтвердите, что вы не робот", "доступ ограничен", "доступ к сервису временно запрещ", "403 forbidden")):
        from app.schemas.offers import store_url
        pause_source(source, product=bool(page_url and store_url(source, page_url)))
        raise RuntimeError("Площадка запросила CAPTCHA; подключите выгрузку предложений")
    # Search pages often contain megabytes of layout and hydration markup.
    # Structured offers do not need that DOM in memory. Product confirmation
    # still reads every price representation below to reject contradictory prices.
    soup = BeautifulSoup(html, "html.parser", parse_only=SoupStrainer(['script', 'h1', 'meta']))
    main_title = soup.select_one('h1, meta[property="og:title"]')
    main_name = (main_title.get('content') or main_title.get_text(' ', strip=True)) if main_title else ''
    def same_page_name(name):
        left = re.sub(r'\W', '', str(name).lower())
        right = re.sub(r'\W', '', main_name.lower())
        return min(len(left), len(right)) >= 8 and (left in right or right in left)
    observed = datetime.utcnow()
    found = {}
    prices = {}

    def add(name, price, url, currency="RUB", availability="", description="", item_condition=""):
        if currency not in ("RUB", "RUR", "₽") or any(x in availability.lower() for x in ("outofstock", "soldout", "discontinued")):
            return
        url = urljoin(search_url(source, ""), url)
        try:
            condition = 'used' if source == 'avito' else 'new'
            explicit_new = re.search(r'состояние\s*[:\-]?\s*нов(?:ый|ая|ое)\b',str(description),re.I)
            if 'NewCondition' in str(item_condition) or source == 'avito' and (explicit_new or re.search(r'\bнов(?:ый|ая|ое)\b', str(name), re.I) and not re.search(r'как\s+нов', str(name), re.I)):
                condition = 'new'
            if source != 'avito' and any(value in str(item_condition) for value in ('UsedCondition', 'RefurbishedCondition', 'DamagedCondition')):
                return
            row = OfferInput(source=source, name=name, category=category,
                             price_rub=money(price), url=url, observed_at=observed,
                             condition=condition,
                             attributes={'description': str(description)[:2000]} if description else {})
            if row.url in found and not row.attributes:
                row.attributes = found[row.url].attributes
            prices.setdefault(row.url, set()).add(row.price_rub)
            found[row.url] = row
        except (ValidationError, ValueError, TypeError):
            pass

    def walk(node):
        if isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, dict):
            kind = node.get("@type", "")
            if kind == "Offer" and node.get("name") and node.get("url") and "price" in node:
                add(node["name"], node["price"], node["url"], node.get("priceCurrency", "RUB"), str(node.get("availability", "")), node.get('description', ''), node.get('itemCondition', ''))
            if kind == "Product" or isinstance(kind, list) and "Product" in kind:
                offers = node.get("offers", [])
                for offer in offers if isinstance(offers, list) else [offers]:
                    if not isinstance(offer, dict):
                        continue
                    # Aggregate lowPrice is not a purchasable offer.
                    if "price" in offer:
                        product_url = offer.get("url") or node.get("url") or (page_url if same_page_name(node.get('name')) else '')
                        add(node.get("name"), offer["price"], product_url or "",
                            offer.get("priceCurrency", "RUB"), str(offer.get("availability", "")), node.get('description', ''), offer.get('itemCondition') or node.get('itemCondition', ''))
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value)

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            walk(json.loads(script.get_text()))
        except (ValueError, TypeError):
            continue
    if found and not require_single_price:
        return list(found.values())
    soup = BeautifulSoup(html, 'html.parser')
    # Server-rendered store cards, isolated selectors avoid unrelated page prices.
    selectors = {"avito": '[data-marker="item"]', "yandex": '[data-auto="product-snippet"]',
                 "dns": '.catalog-product', "ozon": '[data-widget="searchResultsV2"] [data-index]',
                 "wb": '.product-card', "oldi": '.product-item', "regard": '[class*="Card_wrap__"]',
                 "kns": '.goods-item', "citilink": '[data-meta="ProductVerticalSnippet"]',
                 "xcom": '.product-card', "onlinetrade": '.indexGoods__item', "nix": '[itemtype$="Product"]'}
    for card in soup.select(selectors.get(source, '[itemtype$="Product"]')):
        name = card.select_one('[itemprop="name"], [data-marker="item-title"], [data-auto="snippet-title"], .catalog-product__name, .product-card__name, a.title, [class*="Card_title__"], [data-meta="ProductVerticalSnippet__title"]')
        price = card.select_one('[itemprop="price"], [data-marker="item-price"], [data-auto="snippet-price-current"], .product-buy__price, .price__lower-price, .price strong, [class*="CardPrice_price__"], [data-meta="ProductVerticalSnippet__price"]')
        # Bind the URL to the title itself before considering another card link.
        link = (name if name and name.get('href') else name.find_parent('a', href=True) if name else None)
        link = link or card.select_one('a[itemprop="url"], a[href*="/product"], a[href*="/catalog/"], a[data-marker="item-title"], a[href$=".html"]')
        if name and price and link:
            availability = card.select_one('[itemprop="availability"]')
            stock = (availability.get("content") or availability.get("href") or availability.get_text()) if availability else ""
            if re.search(r"нет в наличии|последняя цена|снят с производства", card.get_text(" ", strip=True), re.I):
                stock = "OutOfStock"
            description = card.select_one('[itemprop="description"], [data-marker="item-description"]')
            add(name.get("content") or name.get_text(" ", strip=True), price.get("content") or price.get_text(" ", strip=True), link.get("href", ""), availability=stock,
                description=description.get_text(' ', strip=True) if description else '')
    # Microdata is scoped to each Product to keep related goods, delivery fees,
    # credit instalments and an unavailable product's last price separate.
    for product in soup.select('[itemtype$="/Product"]'):
        title = product.select_one('[itemprop="name"]')
        offer = product.select_one('[itemtype$="/Offer"]')
        if not title or not offer:
            continue
        price = offer.select_one('[itemprop="price"]')
        currency = offer.select_one('[itemprop="priceCurrency"]')
        availability = offer.select_one('[itemprop="availability"]')
        link = offer.select_one('[itemprop="url"]')
        stock = (availability.get("content") or availability.get("href") or availability.get_text()) if availability else ""
        if price:
            add(title.get("content") or title.get_text(" ", strip=True), price.get("content") or price.get_text(),
                (link.get("href") or link.get("content")) if link else page_url or "",
                currency.get("content") or currency.get_text() if currency else "RUB", stock)
    # Product pages may publish OpenGraph/microdata instead of JSON-LD.
    title = soup.select_one('meta[property="og:title"], meta[itemprop="name"]')
    price = soup.select_one('meta[property="product:price:amount"], meta[itemprop="price"]')
    canonical = soup.select_one('link[rel="canonical"], meta[property="og:url"]')
    currency = soup.select_one('meta[property="product:price:currency"], meta[itemprop="priceCurrency"]')
    if title and price and canonical:
        availability = soup.select_one('[itemprop="availability"]')
        add(title.get("content"), price.get("content"), canonical.get("href") or canonical.get("content"),
            currency.get("content", "RUB") if currency else "RUB",
            (availability.get("content") or availability.get("href") or "") if availability else "")
    if not found:
        raise RuntimeError("Нет читаемых карточек с ценой: разметка изменилась, нужен JavaScript или выгрузка")
    if require_single_price:
        from urllib.parse import urlunsplit
        def canonical(url):
            parsed = urlsplit(url)
            return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip('/'), '', ''))
        exact = [row for row in found.values() if canonical(row.url) == canonical(page_url or '')]
        if len({price for row in exact for price in prices[row.url]}) != 1:
            raise RuntimeError('Страница не подтвердила единственную цену именно этого товара')
        return exact
    return list(found.values())


def search_public(source, query, category, deadline=None):
    url = resolved_search_url(source, query, deadline=deadline)
    return parse_html(source, fetch(url, store=source, deadline=deadline), category, url)
