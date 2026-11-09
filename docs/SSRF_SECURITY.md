# SSRF: карта путей и решение (итерация 4)

Дата: 2026-11-09. Исходный аудит и итог исправлений. Все проверки сетевого поведения — с моками.

| Путь | Источник URL / влияние пользователя | Текущий транспорт / редиректы | Риск |
| --- | --- | --- | --- |
| /offers/from-url | Авторизованный пользователь; store_url уже ограничивает HTTPS/host/path магазина | store_providers.fetch → Requests.Session, ручные редиректы | DNS назначения не проверяется, соединение разрешает hostname самостоятельно |
| /offers/search, search-jobs, refresh цены | Запрос/категория пользователя → фиксированный поиск или URL в БД | Тот же fetch | Первая URL не проверяется самим fetch, DNS/системный proxy не ограничены |
| public_discovery | Фиксированный поисковик, затем allowlist ссылок магазинов | fetch с redirect_hosts, затем fetch store | Та же DNS/connection проблема |
| NIX resolver | Фиксированная HTTPS URL, query в форме | Прямой requests.post без stream/лимита тела | Обходит общий транспорт, нет DNS/размера |
| Администраторский feed | HTTPS URL в конфигурации, возможен bearer token | fetch store=None | Частный DNS/прямой IP, proxy; токен уже не пересылается в redirect |
| Playwright browser_context | Store/search URL; подресурсы/скрипты/новые окна | Native Chromium; route.continue_ проверяет только literal IP/имя | Частный DNS, rebinding; сетевые каналы вне обычного HTTP routing |
| CDP | Администраторский localhost URL | connect_over_cdp к внешнему процессу | Нет подтверждённого контроля egress управляемого браузера |
| scripts/parser.py | Фиксированные PassMark страницы; функция принимает page_url | Requests.Session с auto redirects, неограниченное .text/.json | DNS, proxy, размеры; источник не проверяется внутри helper |
| scripts/refresh_prices.py | Фиксированный CBR HTTPS URL и PassMark helper | requests.get CBR, parser session | Те же риски |
| Фото объявлений | HTTPS/data URL хранится в JSON/БД и показывается img в браузере пользователя | Backend не загружает изображение | Серверного SSRF-пути не найдено |
| SMTP / SQLite | Администраторский SMTP config / локальные файлы | Не загрузка пользовательского web URL | В этой итерации не меняются |

План: единая политика HTTPS/443/нормализация, проверка всех A/AAAA, numeric-IP socket с исходным hostname в TLS SNI/сертификате/Host; каждый redirect проходит полный цикл. Тайм-ауты, размеры wire и распакованного тела, ограниченный DNS/HTTP параллелизм; без системных proxy. HTTP интерфейсы адаптеров сохраняются.

Playwright: фактическую изоляцию сети Chromium/существующего CDP на уровне OS в текущем проекте подтвердить нельзя. URL routing не принимается за DNS pinning. Небезопасный браузерный запуск должен быть отключён с диагностикой до реализации и проверки изолированного egress. HTTP fallback остаётся.


## Реализованная граница защиты

network_policy.py — единая нормализация HTTPS/443, IDNA, allowlist доменов и проверка всех A/AAAA. Userinfo, управляющие символы, неоднозначные URL и локальные имена запрещены. Private, loopback, link-local, reserved, multicast, unspecified, metadata и переходные IPv6-сети запрещены; mapped IPv4 проверяется как IPv4. Смешанный публичный/частный DNS-ответ отклоняется целиком.

safe_http.py создаёт socket непосредственно к проверенному числовому IP, сверяет peer, передаёт исходное имя в SNI, Host и проверку сертификата. Повторного разрешения hostname транспортом нет. TLS verification не отключается. Каждый redirect заново проходит URL/DNS/pinning; максимум 3 перехода. Bearer-запросы не перенаправляются вообще. CookieJar ограничивает cookies доменом/путём и отдельной сессией. Переменные proxy окружения не используются.

Лимиты: connect 3 с, read 5 с, вся цепочка не более 30 с (или меньшего deadline вызывающего кода), 4 параллельных HTTP-загрузки и 4 DNS-задачи на процесс. Watchdog закрывает активный сокет; finally закрывает ответ и TLS даже после ошибки handshake. Не более 8 MiB переданных и распакованных данных; проверяются Content-Length, поток и ограниченная распаковка gzip/deflate. Бинарные MIME-типы отклоняются. Тайм-ауты старых вызовов могут только уменьшить общий бюджет.

Транспорт подключён к магазинам, поисковикам, фидам, NIX POST, PassMark и CBR-скриптам. Поисковые правила и оптимизатор не переписаны. Сервер не загружает фотографии объявлений; SMTP остаётся администраторской конфигурацией.

## Chromium и CDP

browser_context и прямой launch_browser отказывают до запуска процесса или подключения CDP, независимо от флага. Диагностика /api/offers/status сообщает enabled=false, configured_enabled и security_status=disabled_pending_network_isolation с причиной. Поэтому подресурсы, JavaScript, popup, WebSocket, service workers и прочие каналы Chromium не получают сетевого доступа через этот путь.

Для будущего включения нужна отдельная проверенная OS/container-изоляция: отсутствие прямого egress, контролируемый шлюз с аналогичной политикой назначения, запрет внутренних/metadata IPv4 и IPv6 и обхода через UDP/WebRTC. Общий внешний CDP и checkbox конфигурации не доказывают изоляцию. Наличие таких гарантий на Amvera не подтверждено; параметры платформы не выдумывались. Routing Playwright сам по себе этой гарантии не даёт.

HTTP fallback сохранён. Источник только с JavaScript может стать недоступным; это отражается в ошибках источника и draft/partial, без вымышленных цен и повышения неподтверждённых предложений. TTL и правила complete/draft/partial не изменены.

## Проверка и ограничения

Тесты полностью локальные: DNS, socket, TLS и ответы — фикстуры. До исправления 6 тестов test_ssrf_original воспроизводили дефекты; отдельно выявлены и исправлены пограничные ошибки watchdog и закрытия TLS после handshake. test_safe_http содержит 31 проверку, включая pinning при rebinding, все DNS-ответы, SNI/сертификат/peer, redirect, proxy, cookies, gzip/размеры/тайм-ауты и повторную сверку изменившейся цены через транспорт.

Нативный getaddrinfo нельзя принудительно отменить из Python: ожидание вызывающего кода ограничено, зависшие задачи занимают максимум 4 слота до возврата системного resolver. Это ограничивает доступность, а не разрешает небезопасный fallback; зависший системный resolver также может задержать завершение процесса. Несколько backend-процессов имеют отдельные лимиты. Доверяем маршрутизации и TLS/CA ОС; вредоносную конфигурацию хоста, NAT и скомпрометированный публичный сервис приложение не изолирует.

Реальные магазины, SMTP, Amvera firewall/маршрутизация, публичный DNS и живые TLS-сервера в этой итерации не проверялись. Live-интеграция не объявляется подтверждённой.

Основание решений: [Python SSL](https://docs.python.org/3/library/ssl.html), [http.client](https://docs.python.org/3/library/http.client.html), [Playwright network](https://playwright.dev/python/docs/network).


## Итог проверок итерации 4

- Новые SSRF-тесты: 37/37 (31 test_safe_http, 6 test_ssrf_original).
- Полная backend-регрессия: 260 обнаружено, 258 успешно, 2 пропущено.
- Frontend: 24/24; интерфейс в этой итерации не изменён, production build повторно не требовался.
- Standalone smoke и recovery/stores: успешно, внешние зависимости подменены.
- git diff --check: успешно. В регрессии остались предупреждения datetime.utcnow из существующего кода/фикстур; их переработка не входит в SSRF.

Изменённые в этой итерации файлы: backend/app/services/network_policy.py, safe_http.py (новые); store_providers.py, browser_offers.py; backend/app/schemas/offers.py, core/config.py, api/offers.py; backend/scripts/parser.py, refresh_prices.py; backend/tests/test_safe_http.py, test_ssrf_original.py (новые), test_browser_offers.py, test_public_discovery.py, test_search_outages.py; backend/.env.example, .env.amvera.example; README.md; docs/SSRF_SECURITY.md, TECHNICAL_AUDIT.md, ARCHITECTURE.md, DECISIONS.md, REQUIREMENTS.md, TODO.md, CHANGELOG_DEV.md, browser-price-search.md, free-search.md.

Рабочее дерево также содержит сохранённые изменения итераций 1–3. Коммит и публикация не выполнялись.
