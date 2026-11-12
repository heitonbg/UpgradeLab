# Текущая архитектура

Аудит кода 2026-11-09. Монолит FastAPI/SQLAlchemy/SQLite и React 18/Vite. Отдельные workers, Redis и Celery отсутствуют и для первой итерации не нужны.

## Основные потоки

| Сценарий | Вход и API | Вычисления и внешние зависимости | Таблицы | Результат и ошибки |
| --- | --- | --- | --- | --- |
| Апгрейд | CalculateRequest → api/calculate.py:post_calculate | upgrade_prices → calculator → performance; при необходимости upgrade_platforms; внешние магазины/Avito для цен | hardware, hardware_prices, store_offers, offer_searches | Расчёт до/после, замена/альтернативы или отсутствие полезного апгрейда; неверный тип ID отклоняется; неизвестная продажа имеет отдельный статус |
| Полная ручная сборка | BuildRequest → services/builds.py:assemble | Проверка RAM/платформы, чтение offer_id на сервере, перебор CPU/GPU, build_options | hardware, hardware_prices, store_offers | 8 частей, сумма, FPS; 400 при отсутствии пары, 422 при неправильном вводе; часть характеристик неизвестна |
| Автоматическая сборка | BuildRequest(auto_parts=True) → assembly_search:assemble_resilient | adaptive_builds:solve_profiles → automatic_builds:assemble_auto; цены проверяются через price_verification | Те же таблицы + offer_searches | complete, draft или partial; общий сетевой бюджет 45 секунд, fallback по источникам |
| Предложения | /api/offers/search или /from-url | offers → store_providers / public_discovery / browser_offers; OfferInput и safe_offers | store_offers, offer_searches | Нормализованные цены/ссылки/статусы; подтверждение по конкретной странице; семафор на 3 поиска |
| Фоновый поиск | POST /api/search-jobs → create_job → run_job; GET /{id} | Один ThreadPoolExecutor worker; идемпотентность по kind, payload, client_request_id | search_jobs | queued/running/completed/failed; до 4 активных; результат сохраняется, running после рестарта становится failed |
| Аккаунт | api/account.py и recovery.py | scrypt, SHA256 токенов, cookie; SMTP только для восстановления | users, login_sessions, password_resets, reset_request_limits | Авторизация/срок сессии; смена пароля отзывает сессии; SMTP-ошибка не выдаётся за доставку |
| Сохранения | /api/builds | Повторный серверный расчёт, запись JSON-снимка, проверка owner | saved_builds | partial не сохраняется; GET отдаёт сохранённый снимок, DELETE только владельцу |
| Биржа | /api/listings и /my/listings | ListingCreate, CRUD, проверка владельца при удалении | listings, listing_owners | Продажа/обмен, фото, контакты; 401/404/422 при нарушениях |

## Frontend

App.jsx объединяет сценарии. CalculatorSection/CalculatorForm и BuildSection хранят параметры шагов и показывают варианты. api/searchJobs.js хранит ID и подпись запроса в sessionStorage, возобновляет polling и повторяет POST с тем же ключом. BuildChoices/UpgradeChoices показывают сравнение; AssemblyPartialResult рисует все восемь категорий без вымышленного итога. AssemblyPriceNotice предупреждает о draft. AccountBuilds отображает серверный снимок; useSavedBuilds обслуживает старые локальные сохранения.

## Ограничения эксплуатации

main.py:create_app выполняет create_all и три аддитивных ALTER TABLE для listings; формального журнала миграций нет. SQLite хранится в /data на Amvera согласно backend/amvera.yaml. Для очереди требуется одна реплика backend. /api/health сообщает живость и ревизию, но не проверяет источники, SMTP или доступность записи в БД.

## UTC и сроки цен — итерация 2, 2026-11-09

Единый источник настенного времени для цен — app/core/price_time.py:utc_now (aware UTC). В тестах подменяется именно эта функция; db_now/is_fresh/past_utc и места получения/подтверждения цен используют её. Сетевые deadlines по-прежнему измеряются time.monotonic и не зависят от настенных часов. Время авторизации и жизненный цикл search_jobs в этой итерации не менялись.

- as_utc разбирает календарные ISO timestamps с Z/offset, принимает datetime, переводит aware в UTC; исторические naive означают UTC.
- as_naive_utc применяется на границе записи/запроса SQLite. Типы DateTime БД не менялись; миграция и массовая перезапись данных не нужны.
- iso_utc сериализует корректный timestamp с одним Z. Некорректные/отсутствующие значения дают None, не текущее время.
- is_fresh проверяет обе границы возраста: будущий timestamp не должен становиться бесконечно свежим.
- current_verification требует status=verified и действительное время подтверждения младше 15 минут. Время поиска/кеша не заменяет checked_at подтверждения.
- quote_evidence сохраняет старое подтверждение как историю; невалидная/будущая метка не становится историческим доказательством. Legacy product_page без явной метаинформации использует время успешного чтения страницы.
- Ошибочный будущий observed_at не блокирует новое корректное наблюдение в upsert и импорте кеша.
- GET /api/builds выдаёт created_at в UTC с Z, не обновляет цены, подтверждение или JSON-снимок. Сохранение явно пишет created_at через db_now. Пересмотр отображения старого snapshot остаётся отдельной итерацией.

### Неизменённые TTL и границы

| Данные | Правило |
| --- | --- |
| Объявление для полной сборки | age <= 24 часа; сохранён допуск observed_at <= now + 5 минут |
| Подтверждение страницы | 0 <= age < 15 минут; на границе требуется повторная сверка |
| Кеш поиска | 0 <= age <= 10 минут; после границы повторный поиск |
| Отказ доступа/unavailable | 0 <= age < 10 минут; прежняя политика сохранена |
| HardwarePrice | <= 7 дней retail / <= 30 дней used; будущие наблюдения ограничены тем же 5-минутным допуском внешних наблюдений |
| Наблюдения рынка апгрейда | <= 7 дней и не позднее now, как раньше |
| Avito snapshot | <= 30 дней и не позднее now |

Пятиминутный допуск существовал в OfferInput и fresh до исправления: он оставлен для расхождения часов внешних источников и применён к импорту наблюдений. Для времени подтверждения/поиска, записываемого самим сервером, положительный допуск не обоснован и равен нулю.

Точки интеграции: schemas/offers.py; services/{offers,price_verification,prices,assembly_draft,assembly_search,upgrade_prices,upgrade_platforms}.py; только записи временных меток в {store_providers,browser_offers,public_discovery}.py; api/{offers,calculate,account}.py; scripts/refresh_prices.py. Адаптеры, парсинг товаров, формула FPS и оптимизатор не переписывались.

## Авторизация — итерация 3

services/auth_limits.py ограничивает валидные запросы до scrypt/SMTP. Существующая reset_request_limits переиспользуется для атомарных SQLite UPSERT-квот по IP, IP/email и аккаунту. Новая auth_challenges хранит краткоживущие одноразовые допуски для усиленной проверки при распределённой нагрузке; пользователи, пароли и сессии не меняют формат.

Обычный вход после квот продолжает прежний путь User → scrypt/compare_digest → sign_in. При общей нагрузке на аккаунт клиенту предлагается короткая работа SHA256 и один автоматический повтор. Это позволяет обойти жёсткую блокировку только по известному постороннему email; квоты IP при этом сохраняются. Счётчики и выдача/поглощение разрешений атомарны и общие только для одного SQLite-файла.

IP берётся из ASGI request.client; доверие к proxy-заголовкам — задача Uvicorn с подтверждённым FORWARDED_ALLOW_IPS. Фактические ingress-адреса Amvera пока не подтверждены. Полный контракт, параметры, пороги, конкурентность и ограничения: [AUTH_SECURITY.md](AUTH_SECURITY.md).


## Итерация 4 — SSRF (2026-11-09)

Все серверные web-загрузки идут через SafeSession → network_policy → numeric-IP HTTPS socket. Исходное имя сохраняется для TLS/Host, redirects повторяют проверку. Chromium/CDP заблокированы до OS egress isolation. Подробности: SSRF_SECURITY.md.


## Итерация 5 — источники после SSRF (2026-11-09)

Все 12 адаптеров классифицированы; полная матрица и план разрешённых интеграций: [SOURCE_READINESS.md](SOURCE_READINESS.md). Ни один источник не объявлен работающим live: прав на автоматический сбор для UpgradeLab не подтверждено, товарные запросы не выполнялись.

Исправлены подтверждённая регрессия декодирования явно указанного charset в SafeResponse и устаревшее предложение browser/discovery в UI. Добавлены признаки кеша/частичного результата и разделение даты наблюдения/подтверждения. API browser-импорта возвращает 503 с причиной изоляции; /offers/status не выдаёт наличие адаптера за live-доступность. Playwright/CDP остаются отключены, TTL и complete/draft/partial сохранены.

Проверки: 9 новых backend-тестов (включая 48 subtests 12×4); полная backend-регрессия — 269 обнаружено, 267 успешно, 2 отдельных сценария пропущены в discover и успешно выполнены standalone (smoke, recovery/stores). Frontend — 27/27, включая 3 новых теста диагностики; production build успешен; git diff --check успешен. Первичные тесты charset и отсутствующей cache-диагностики падали до исправления.

Реальная сеть магазинов/Amvera и полная детализация API за закрытыми порталами не проверены. Самый обоснованный кандидат для согласования — партнёрская сеть Яндекс Маркета, а не Seller API для собственного каталога. Коммит и следующая итерация не выполняются автоматически.


## Итерация 6 — сохранённые цены (2026-11-09)

UL-005 исправлен: старый result больше не показывается как новый расчёт с текущими ценами. Исторические JSON/created_at/status не меняются при чтении или проверке. Новое сохранение добавляет price_snapshot v1; GET возвращает динамическую price_review. POST /api/builds/{id}/prices проверяет владельца и выполняет только локальную сверку StoreOffer, без сети/пересчёта/записи. Неизвестные и удалённые предложения не подтверждают сумму; ручные оценки и предполагаемая продажа отделены от покупки.

Личный кабинет различает историческую стоимость, последнее наблюдение и актуальную сумму; истечение зависит от серверных UTC-часов и монотонного времени браузера. Исходные локальные снимки больше не удаляются при новом расчёте по старым настройкам. TTL, FPS, совместимость, авторизация, поиск и complete/draft/partial не изменены.

Проверки: 24 новых backend-теста и 10 frontend-тестов. Полная backend-регрессия: 291 успешно, 2 пропущены (293 обнаружено); standalone smoke/recovery успешны. Frontend: 37/37; production build и git diff --check успешны. Реальные магазины и визуальные/e2e сценарии не проверялись. Полный контракт, файлы и ограничения: [SAVED_PRICES.md](SAVED_PRICES.md).


## Итерация 7 — независимый блок A–B (2026-11-09)

Готовы аудит и улучшение биржи: офлайн-города, owner-only PATCH, обязательный город новых объявлений, совместимость legacy без города, модель Hardware, статусы, раздельные UTC-даты, явное заявление продавца, контакты и фото 4:3. Исторические сохранения и предыдущие механизмы безопасности сохранены.

Итерация 7 целиком не завершена: единый geo-контракт, разрешённые источники, внутренний адаптер оптимизатора, доставка, городские сборки и апгрейды — отдельные невключённые блоки C–E. Их нельзя считать готовыми по наличию городского CRUD. Подробности, миграция, файлы и критерии: [ITERATION_7.md](ITERATION_7.md).

Проверки блока: 23 новых backend-теста; 316 обнаружено, 314 успешно, 2 пропущены. Standalone smoke/recovery успешны. Frontend 47/47 (+10), production build успешен. Локальный Edge проверил фото и редактирование на 320/375/430/768/1280/1920 px с API-фикстурами; магазины и рабочая БД не использовались. git diff --check успешен.

Миграция аддитивная и проверена на временной legacy SQLite, рабочая БД в сессии не обновлялась. Новые заявления продавца действуют менее 24 часов; они не являются магазинной сверкой или гарантией и не подключены к финансовому подбору. Коммит/публикация не выполнялись.


## Исследование парсеров и диагностический контракт (2026-11-09)

Изучены 9 GitHub-репозиториев на зафиксированных HEAD, без выполнения стороннего кода и запросов к магазинам. Матрица, ссылки на файлы, лицензии и транспортные карты: [PARSER_RESEARCH.md](PARSER_RESEARCH.md); SHA/хеши: parser_research_manifest.json. Архитектура и граница фактической реализации: [SOURCE_ARCHITECTURE_PLAN.md](SOURCE_ARCHITECTURE_PLAN.md).

Реализована одна задача: outcome отдельно от legacy status/origin. Новый source_outcomes.py классифицирует известные отказы/успех/пустой feed/partial, измеряет elapsed_ms/result_count. collect_source сохраняет метаданные в OfferSearch.statuses, search/batch и /offers/status их выдают. Старый кеш не переписывается и не получает нового времени попытки/подтверждения. Неизвестный RuntimeError, дошедший до collect_source, не отражает raw URL/секрет; новый типизированный error не включает тело feed. Извлечение и финансовые правила сохранены.

Новые возможности/разрешения источников, адаптеры private API, XML/CSV/Excel, журнал истории, внутренний финансовый источник и геоподбор НЕ добавлены. Это план следующих независимых изменений. SafeSession/DNS pinning/TLS/redirect, отключённый browser, UTC/TTL, complete/draft/partial не менялись. Внешних live-проверок — 0; разрешения на данные не получены.

23 новых backend-теста. Полная регрессия: 339 обнаружено, 337 успешно, 2 пропущены при discover; standalone smoke/recovery успешны. Frontend 47/47. Frontend-код не менялся, повторная production-сборка не требовалась. git diff --check успешен.

Следующий рекомендуемый шаг: централизованный permission/capability gate и один согласованный feed с разрешёнными образцами. Avito после отказа не включать. Коммит/публикация не выполнялись.


## Итерация 9: локальные каталоги

CLI scripts.import_catalog использует CatalogSchema → ограниченный CSV/OpenXML reader → prepare_import → apply_import. Четыре новые таблицы в той же SQLite: CatalogAccess (права), CatalogProduct (staging/идентичность/связь со StoreOffer), CatalogObservation (история), CatalogImport (receipt). Hardware остаётся единственным справочником CPU/GPU. BEGIN IMMEDIATE обеспечивает атомарность. Публичные предложения имеют origin=catalog_import и не получают live-подтверждение. Поиск, ручные offer_id, сохранения и сверка страниц учитывают gate; fixture видим только в локальном контексте. API импорта/скачиватель не добавлены. Полный контракт: [PRICE_FEED_IMPORT.md](PRICE_FEED_IMPORT.md).


## Диагностика неполной сборки после аудита live-80000

assembly_diagnostics разделяет наличие безопасных кандидатов, прохождение quality/бюджетных фильтров и совместимость с выбранными деталями. Category budget в partial — оценочный план остатка. Flexible assemble_auto проверяет общий бюджет после совместного выбора; первый проход сохраняет доли категорий. NetworkTransportError дополняет NetworkPolicyError безопасным outcome без raw exceptions. Avito автоматический collector и product verifier не выполняют сеть. Цена с копейками в live-парсере не округляется и не проходит существующий integer-контракт. Полный аудит: LIVE_80000_DIAGNOSTIC.md.


## Итерация 10 — единый географический набор

GeoQuery объединяет SearchOffers/BuildRequest/CalculateRequest; ContextVar scope применяется к StoreOffer/ценам/ручным ID и апгрейду. internal_offers материализует только проверяемые CPU/GPU/RAM объявления из Listing/Owner/User, без HTTP. seller_declared не становится verified. ListingDelivery — единственная новая таблица; create_all проверен на старой копии. source_permissions по умолчанию запрещает внешнюю сеть; импортные и сетевые права независимы. technical_evidence возвращает compatible/incompatible/unknown, точные applies_to и provenance защищают от переноса профиля. Известная доставка включается в временную стоимость кандидата, исходный StoreOffer не переписывается. Неизвестная доставка/техника даёт draft, purchase_ready=false и nullable payable total. Cached jobs перепроверяют ID/права/состояние, revision учитывает изменения биржи. Контракт, demo и ограничения: [UNIFIED_GEO_OFFERS.md](UNIFIED_GEO_OFFERS.md).


## Итерация 11 — все категории собственной биржи

ListingDetails хранит отдельную JSON-декларацию продавца, восемь Pydantic-схем не вводят второго справочника Hardware. listing_specs отделяет declared/catalog/trusted/missing/contradictory и использует только доступные точные технические профили. internal_offers материализует все восемь категорий; search включает неполные записи, оптимизатор/апгрейд исключают их. Listing + Owner + Details + Delivery сохраняются одной транзакцией. DeliveryEvidence дополнен mode/terms с backward-compatible cities. Геофильтры учитывают pickup/cities/russia; исходная цена не меняется при добавлении доставки. physical_fit исключает известные конфликты, оставляя неизвестные размеры unknown. revision/fingerprint перепроверяют характеристики и доступность профиля; история сохранений неизменна. React использует единые характеристики и редактор доставки при создании/PATCH. Полный контракт и воспроизведение: [MARKETPLACE_ALL_CATEGORIES.md](MARKETPLACE_ALL_CATEGORIES.md). Рабочая БД не изменена, сеть магазинов не использовалась.


## Итерация 12 — native Regard и UI 2026

RegardFeedAdapter — bounded streaming OpenXML reader, подключённый к прежним prepare/apply/CatalogProduct/StoreOffer через schema.input_adapter. Реальные URL/остатки не подставляются. closed_catalog_analysis(engine) ограничивает real/private показ отдельной .analysis.db; HTTP не умеет включать этот контекст. Стабильный external_product_id, provenance SHA/version в receipt, история и private-only missing/shrink защищены транзакцией. Публичные/сетевые права остаются выключены; ежедневный local preview подготовлен, не активирован. Подробности: REGARD_REAL_FEED.md.

React SPA получил HomePage, горизонтальную навигацию и отдельный поиск; CategoryImage/PriceOriginBadge/FpsComparison/BuildSummary используют существующие данные/правила. Шесть дополнительных категорий можно перенести из поиска в прежнюю manual form с offer_id и geo scope; CPU/GPU остаются парным выбором. Декоративные local WebP отделены от фото SKU. Сохранения различают history/latest/confirmed и создают новый расчёт без изменения старого. Backend API/авторизация/TTL/FPS не переписаны. DESIGN_SYSTEM.md, REDESIGN_2026.md, ASSET_LICENSES.md, UI_VISUAL_AUDIT.md фиксируют реализацию и проверки.


## FPS v2 evidence gate и режимы цен (2026-11-10)

Новая модель не прошла проверку данных и не заменила performance.py. games.router предоставляет локальный /api/games и evidence-gated /api/fps/predict; game_catalog кеширует CC-BY названия отдельно от измерений. fps_validation исключает синтетику/несовместимые условия и разбивает по тестовым сериям; независимого test пока нет. build/automatic_builds передают CPU identity и используют единое RAM-правило. planning_prices ContextVar задаёт read-only inventory для reference/hybrid, существующий solver проверяет технические ограничения. Исторические цены маркируются reference и не получают verified; saved_prices не подтверждает их по URL. Явный offers исключает исторические HardwarePrice. Подробные права, данные, метрики и ограничения: FPS_ENGINE_V2.md.


## Offline FPS benchmark data (2026-11-10)

benchmark_data нормализует лицензированные per-run Open GPU и first-party TechFuel наблюдения, сохраняет неизвестные параметры, lineage/hashes, версии, OC и rendering modes. benchmark_calibration объединяет повторные конфигурации и строит held-out-publisher folds; production API не импортирует этот модуль и не использует экспериментальные кандидаты. prepare_fps_benchmarks / evaluate_fps --curated работают по локальным JSON без сети/SQLite. GPU/CPU с score<=0 исключены из обеих ветвей сборки и апгрейда. Offers/reference/hybrid и цены не менялись. См. FPS_BENCHMARK_DATA.md.


## Regard sync и внешнее обнаружение (10.11.2026)

Новые аддитивные SQLite-таблицы: catalog_daily_prices, catalog_price_corrections, catalog_sync_runs, external_search_jobs, ai_daily_budgets. Привилегированный CLI импортирует native XLSX в одной транзакции с 14-дневной историей; OS-lock исключает двух локальных исполнителей. Закрытый анализ остаётся на .analysis.db. JSON сохранённых сборок и TTL не меняются. Публичная история защищена правами источника.

OpenRouter используется только в отдельной авторизованной очереди внешнего обнаружения URL. Кандидаты строго привязаны к provider citations и существующим доменам/товарным путям; search_discovered, optimizer_eligible=false, неизвестная цена null. AI не пишет Hardware/StoreOffer и не участвует в matching, совместимости, FPS или подборе. Платный tool default-off, лимиты резервируются в SQLite до сети.

Hybrid сравнивает исходный вариант с расширенным пулом и показывает улучшенную справочную альтернативу отдельно. Независимые CPU/GPU locks, condition, workload gaming/cpu_work и objective поддерживаются ограниченным joint search; глобальный оптимум не обещается. Подробности: [daily sync](REGARD_DAILY_SYNC.md), [история](REGARD_PRICE_HISTORY.md), [AI search](OPENROUTER_PRODUCT_SEARCH.md), [builder](SMART_PC_BUILDER.md), [deployment](DEPLOYMENT_CHECKLIST.md).


## Официальный Regard download

SafeSession.get_to записывает ответ 200 в ограниченный файловый sink с прежними DNS pinning/TLS/redirect-проверками. Regard использует постоянные стандартные заголовки и прозрачный User-Agent. До атомарной замены проверяются HTTP/MIME/ZIP/native-структура/CRC; хеш считается на потоке. download() сохраняет все permission gates и передаёт файл прежнему sync/import pipeline. Worker scheduler и новые admin API не добавлены. См. [отчёт](REGARD_DOWNLOAD_DIAGNOSTICS.md).
## Frontend UI layer (2026-11-11)

Общие controls и визуальные токены определены в `frontend/src/components/ui`, `tokens.css` и `controls.css`. Combobox выбирает только явную опцию, ограничивает remote suggestions и использует portal для viewport-позиционирования; game/city loaders остаются клиентской логикой. `publicSources.js` фильтрует UI-запросы по Regard и бирже UpgradeLab, не меняя backend source grants. `buildPresentation.js` задаёт отображение доверия, совместимости и метрик на основе существующих признаков и не меняет расчёт FPS. Модальные формы и подтверждения используют общий `Modal`/`useConfirm`. Подробности: [PREMIUM_UI_UX_REVIEW.md](PREMIUM_UI_UX_REVIEW.md).

Локальный приватный каталог Regard использует отдельный read-only HTTP capability под `/api/admin/catalog/regard`: он требует loopback peer, токен владельца, отдельную SQLite `*.analysis.db` и валидный development grant. Публичные offers/history и user source grants не ослаблены; обычный `available_offers()` продолжает использовать TTL и `filter_catalog()`. Описание данных/прав и локальный запуск preview: [REGARD_PRIVATE_CATALOG.md](REGARD_PRIVATE_CATALOG.md).

## Gaming optimizer audit (2026-11-11)

Автоматический игровой подбор ранжирует полные конфигурации по catalog-percentile CPU Mark/G3D и объявленным ёмкости/числу модулей RAM; target FPS и legacy FPS не управляют выбором. `target_reached=null` означает, что полная конфигурация не подтверждена игровыми замерами. RAM shortlist сохраняет Pareto варианты до 32 позиций; двухмодульный кандидат из SKU допускается только при подтверждённом наличии двух единиц. Скорость памяти tie-breaker, каналы — potential при поддержке платы, без FPS бонуса. Balanced максимизирует weakest-link hardware proxy (минимум нормированных CPU/GPU/RAM), Performance максимизирует геометрический proxy, Economy минимизирует полную стоимость. Это прозрачная аппаратная эвристика, не доказательство игрового превосходства; `global_optimum_proven=false` остаётся. Ручной/legacy путь не менял target semantics. См. [optimizer implementation](OPTIMIZER_V2_IMPLEMENTATION.md), [gaming audit](GAMING_OPTIMIZER_AUDIT.md), [FPS research](FPS_ENGINE_V3_RESEARCH.md) и [evaluation](FPS_ENGINE_V3_EVALUATION.md).


## Каталог, TTL и реальный E2E — 2026-11-11

Эта запись уточняет прежние ограничения закрытого каталога: владелец разрешил публичный некоммерческий показ данного прайса, automatic_download/commercial остаются отдельными правами. Regard catalog_import использует отдельное CATALOG_PRELIMINARY_HOURS=72: fresh до 24 часов, stale до окна — только предварительная оценка, затем historical. imported_at не заменяет дату цены; live TTL/подтверждение не продлены. Поиск, ручной выбор, автоматический подбор, upgrade и saved review используют этот контракт. Публичная витрина не отправляет пустой category; frontend разделяет in-flight hardware запрос. Права и database-bound analysis проверяются один раз на выборку без глобального кеша. Подробные измерения, семь исправленных тестов, исходные даты, 12 реальных расчётов и инструкция Amvera: [FULL_PRODUCT_READINESS.md](FULL_PRODUCT_READINESS.md).


## Автоподбор V3 и FPS aggregation

Для `objective=performance` интерфейс и `/api/assemble` используют полный бюджет восьми деталей. CPU/GPU/RAM ранжируются по аппаратному bottleneck proxy; 1 ТБ/2 ТБ SSD выбирается среди совместимых предложений по цене за ГБ и полной стоимости. `target_reached=null` сохраняет границу между аппаратным выбором и неподтверждённым игровым FPS. Детали и ограничения: [GAMING_OPTIMIZER_V3.md](GAMING_OPTIMIZER_V3.md).

Измерения проходят офлайн `benchmark_data` → `benchmark_aggregation` → `aggregates.json`. Сырые записи и ссылки на источники сохраняются. Агрегаты пока не включены в production FPS из-за недостатка независимых сопоставимых серий: [BENCHMARK_AGGREGATION.md](BENCHMARK_AGGREGATION.md).
