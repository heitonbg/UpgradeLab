"""Known Russian stores. Product paths form an allowlist, not arbitrary URLs."""
STORES = {
    "ozon": {"name": "Ozon", "domain": "ozon.ru", "search": "https://www.ozon.ru/search/", "query": "text", "product": r"^/product/"},
    "avito": {"name": "Avito", "domain": "avito.ru", "search": "https://www.avito.ru/all/tovary_dlya_kompyutera", "query": "q", "product": r"/[^/]+_\d+/?$"},
    "wb": {"name": "Wildberries", "domain": "wildberries.ru", "search": "https://www.wildberries.ru/catalog/0/search.aspx", "query": "search", "product": r"^/catalog/\d+/detail\.aspx$"},
    "yandex": {"name": "Яндекс Маркет", "domain": "market.yandex.ru", "search": "https://market.yandex.ru/search", "query": "text", "product": r"^/(?:product|card|offer)"},
    "dns": {"name": "DNS", "domain": "dns-shop.ru", "search": "https://www.dns-shop.ru/search/", "query": "q", "product": r"^/product/"},
    "citilink": {"name": "Ситилинк", "domain": "citilink.ru", "search": "https://www.citilink.ru/search/", "query": "text", "product": r"^/product/"},
    "regard": {"name": "Регард", "domain": "regard.ru", "search": "https://www.regard.ru/catalog", "query": "search", "product": r"^/product/\d+/"},
    "oldi": {"name": "OLDI", "domain": "oldi.ru", "search": "https://www.oldi.ru/search/", "query": "q", "product": r"^/catalog/element/\d+/?$"},
    "kns": {"name": "KNS", "domain": "kns.ru", "search": "https://www.kns.ru/search.html", "query": "s_word", "product": r"^/product/"},
    "xcom": {"name": "XCOM-SHOP", "domain": "xcom-shop.ru", "search": "https://www.xcom-shop.ru/search/", "query": "q", "product": r"^/(?:product/|[^/?]+_\d+\.html$)"},
    "onlinetrade": {"name": "ОНЛАЙН ТРЕЙД", "domain": "onlinetrade.ru", "search": "https://www.onlinetrade.ru/sitesearch.html", "query": "query", "product": r"^/catalogue/.+\.html$"},
    "nix": {"name": "НИКС", "domain": "nix.ru", "search": "https://www.nix.ru/price/price_list.html", "query": "keywords", "product": r"^/autocatalog/.+\.html$"},
}
