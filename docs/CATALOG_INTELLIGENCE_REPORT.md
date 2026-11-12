# Итог проверки: Regard Daily Sync / AI Search / Smart Builder

Проверка 10.11.2026. Изменения подготовлены локально; рабочая SQLite и настоящий backend/.env не изменялись. Commit, push, deployment и включение расписания не выполнялись. Существующий большой незакоммиченный набор предыдущих итераций сохранён.

## Что исправлено и реализовано

- Не было компактной календарной истории native-прайса: добавлены дневная цена в копейках, same-day correction audit, retention 14 дней в успешной транзакции и публичный API с проверкой прав. Исторический JSON сохранённых сборок не меняется.
- Повтор/параллельный daily-sync требовали отдельной защиты: OS-lock, BEGIN IMMEDIATE, журнал succeeded/unchanged/failed/interrupted, контроль уменьшения каталога/старой исходной даты и пропуск идентичного входа при совпадении всех зависимостей. Ручной CLI сохранён.
- Hybrid раньше исключал справочную GPU, если имелась любая реальная GPU: теперь выполняется отдельное сравнение расширенного пула. Исходный вариант сохраняется, улучшение помечается как справочное/гибридное. Вложенные необработанные alternatives не включаются в сравнительный вариант.
- Схема требовала одновременно CPU и GPU: теперь фиксации независимы и соблюдаются всеми вариантами. Добавлены condition, ограниченный CPU-рабочий профиль, три цели, candidate caps, Pareto-отсечение новых objective-веток и диагностика времени. Глобальный оптимум не обещается.
- Добавлен opt-in AI discovery без участия в технических решениях: строгий JSON, provider citations, программный SKU-фильтр, jobs владельца, bounded queue, TTL, атомарный бюджет и cooldown. Успех сбрасывает счётчик последовательных ошибок. Неизвестные расходы fallback не отображаются как нулевые.
- Защищённый HTTP-транспорт сохраняет явный JSON Content-Type; XLSX MIME разрешён только явной настройкой downloader. DNS pinning, HTTPS и запреты SSRF сохранены.

Новые регрессии воспроизводили запрет одиночной CPU-фиксации, отсутствие сброса ошибок провайдера, недоступность XLSX MIME, ошибку отсутствующих прав истории, нарушение фильтра used для reference и вложенные hybrid alternatives. Проверены rollback, конкурентный бюджет, owner isolation, idempotency, источник даты, граница 14 дней и сохранность legacy-строк при миграции.

## Фактические данные

| Проверка | Результат |
| --- | --- |
| Настоящий локальный XLSX | 4 571 355 байт; 83 719 товарных строк; 4991 выбранная строка |
| Matching | matched 247; structured 2088; ambiguous 74; unmatched 2582 |
| Приватная материализация | 2335 предложений; публичная публикация 0 |
| Реальная история | 4991 наблюдение за один исходный день; 14 реальных дней не имитировались |
| Итоговый первый импорт | 40.86 с; peak working set 163.89 MiB; SQLite 20 197 376 байт |
| Повтор | 1.54 с; xlsx_parse_skipped=true; receipt idempotent=true |
| Ёмкость 14 дней | отдельная synthetic fixture: 4991 × 14 = 69 874 строки; SQLite 16 379 904 байта (15.62 MiB) |
| Закрытая сборка 80 000 ₽ | reference и hybrid: восемь деталей, 74 850 ₽; CPU Ryzen 5 4500, GPU RTX 2060 SUPER |
| Достоверность этой сборки | draft; purchase_ready=false; compatibility_status=unknown; все цены reference; магазин не запрашивался |
| Время закрытого расчёта | reference 1.31 с, hybrid 2.19 с; не SLA production |

Время импорта измерено на Windows параллельно с регрессией, поэтому это ориентир ресурсов, не чистое сравнение производительности. Исходный реальный файл не изменён. Для закрытого расчёта sockets заблокированы тестовым guard. Технические размеры/BIOS/разъёмы, наличие и доставка независимо не подтверждены. Это не покупаемая сборка и не измеренный игровой FPS.

Локальные артефакты (игнорируются Git): `.artifacts/regard-daily-profile-final/profile.json`, `.artifacts/catalog-intelligence/closed-builds.json`, `history-capacity.json`, `openrouter-probe.json`. Воспроизводимые CLI описаны в профильных документах.

## Реальные интеграции: что не подтверждено

Официальная ссылка прайса Regard найдена, но вернула 403. Подтверждённого автоматического download/public-display разрешения нет; robots-проверка не завершена. Автоимпорт выключен. URL товара по ID и фото не угадываются, используются существующие заглушки.

В Models API перечислены три запрошенные free-модели. Минимальные пробы без tools: Lightning 200, Gemma 429, Ultra 200. Успешные пробы сообщили cost=0. Это проверка доступности, не качества поиска/JSON/SKU. Основная/резервная модель не назначены без сравнительного теста.

Платные Web Search/Fetch не вызывались. Для Avito, DNS, Citilink, Ozon и WB фактический AI-поиск не запускался: импортировано 0 предложений, подтверждено 0 цен, precision/recall/стоимость карточки неизвестны. Это не свидетельство отсутствия товаров. Нет отдельного разрешения на расход и настроенного положительного бюджета. Web Fetch account support/тариф не подтверждены; инструмент не включён. Прямая автоматизация Avito остаётся отключённой.

FPS Engine не заменён и не перекалиброван без данных. Сохранена прежняя лицензированная база 81 наблюдение / 72 конфигурации / 4 игры / 3 CPU / 3 GPU / 2 издателя / 4 серии. Новых измерений и X3D-бонуса нет. Production promotion=false.

## Проверки

- Полная backend-регрессия окончательной версии: **564 теста, 562 успешных, 2 пропущены**, 139.97 с. До итерации: 531 тест, 529 успешных, 2 пропущены. Добавлено 33 теста; существующие проверки выбранной пары/hybrid обновлены под новые требования.
- Frontend: **77/77**.
- Production frontend build: успешно, 99 модулей, JS около 351 kB до gzip.
- Компиляция backend/scripts: успешно.
- `git diff --check`: успешно.
- Отдельные новые проверки запускались до и после исправлений. Финальный лог: `.artifacts/catalog-intelligence/backend-verified.txt`; frontend: `frontend-final.txt`, `build-final.txt`.

Не выполнялись: интерактивный browser E2E новых компонентов, deployment/smoke из сети Amvera, восстановление настоящей production-копии, многосерверный тест с отдельными дисками, платный реальный поиск, разрешённый импорт канонических карточек/фото. Миграция и backup проверены только на временной legacy-БД. SQLite-бюджет общий лишь для одной общей БД, внешний биллинг exactly-once не гарантирован. CPU-work — узкий proxy, не универсальная оценка рабочих приложений. Полный SLA всех профилей и memory hard limit обеспечиваются инфраструктурой, не обещаются эвристикой.

## Файлы этой итерации

Перечислены файлы, которых касается эта итерация; их общий git diff также может содержать сохранённую работу предыдущих итераций.

| Область | Файлы |
| --- | --- |
| Конфигурация/схема | backend/app/core/config.py; backend/app/db/models.py; backend/app/main.py; backend/.env.example; backend/.env.amvera.example |
| API/валидация | backend/app/api/catalog_history.py; backend/app/api/product_discovery.py; backend/app/schemas/product_discovery.py |
| Импорт/история/поиск | backend/app/services/catalog_import.py; catalog_history.py; regard_sync.py; product_discovery.py; safe_http.py; offers.py |
| Подбор/география | backend/app/services/builds.py; automatic_builds.py; adaptive_builds.py; planning_prices.py; offer_geography.py |
| CLI | backend/scripts/regard_sync.py; profile_regard_sync.py; measure_history_capacity.py; migrate_catalog_intelligence.py; import_catalog.py |
| Тесты | backend/tests/test_catalog_intelligence.py; test_catalog_intelligence_api.py; test_catalog_migration.py; test_regard_daily_sync.py; test_smart_builder.py; test_build_variants.py; test_benchmark_data.py; test_safe_http.py |
| Frontend | frontend/src/components/ExternalProductSearch.jsx; PriceHistory.jsx; StoreOffers.jsx; calculator/BuildSection.jsx |
| Эксплуатация | tools/regard_daily.example.json |
| Документация | docs/REGARD_DAILY_SYNC.md; REGARD_PRICE_HISTORY.md; OPENROUTER_PRODUCT_SEARCH.md; SMART_PC_BUILDER.md; DEPLOYMENT_CHECKLIST.md; CATALOG_INTELLIGENCE_REPORT.md; ARCHITECTURE.md; TODO.md; CHANGELOG_DEV.md; TECHNICAL_AUDIT.md |

Предлагаемый commit после отдельного подтверждения: `feat(catalog): add daily Regard history and guarded product discovery`.
