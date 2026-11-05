"""Public search links, usable from any device without a third-party API."""
from urllib.parse import urlencode
from app.core.stores import STORES

ENGINES = (
    ('google', 'Google', 'https://www.google.com/search', 'q'),
    ('yandex', 'Яндекс', 'https://yandex.ru/search/', 'text'),
    ('bing', 'Bing', 'https://www.bing.com/search', 'q'),
    ('duckduckgo', 'DuckDuckGo', 'https://duckduckgo.com/', 'q'),
)


def web_search_links(source, query):
    text = f'{query} site:{STORES[source]["domain"]}'
    return [{'source': engine, 'label': label, 'url': base + '?' + urlencode({parameter: text})}
            for engine, label, base, parameter in ENGINES]
