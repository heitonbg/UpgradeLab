# UpgradeLab: два проекта Amvera — frontend и backend

## Текущий пакет: подбор по целевому FPS, общие снимки, импорт frametime

Пакеты `UpgradeLab-Backend-Amvera-ready.zip` и `UpgradeLab-Frontend-Amvera-ready.zip` создаются `tools/package_amvera.py --output <директория>`. Каждый содержит корень собственного Code-проекта и AMVERA_SETUP.md. Backend не содержит frontend, вложенные ZIP, .env, SQLite или XLSX; frontend не содержит backend. SHA-256 и число файлов записаны в manifest.json. Прежние пакеты с датами ниже относятся к предыдущим версиям.

Перед обновлением backend сделайте backup SQLite в Data; каталог /data сохраняется. В релизе добавляются таблицы shared_configurations, benchmark_captures и benchmark_quotas; существующие аккаунты/объявления/сборки не заменяются. BENCHMARK_REVIEWER_EMAILS задаёт проверяющие аккаунты; без него новые пользовательские результаты остаются pending. Формат захватов и ограничения описаны в ARCHITECTURE.md. Backend следует обновить перед frontend из того же релиза.

Ежедневный worker Регарда реализован в scripts.startup: REGARD_DAILY_SYNC_ENABLED=true, REGARD_DAILY_SYNC_INTERVAL_SECONDS=86400, существующие права и REGARD_DOWNLOAD_ENABLED обязательны. Первоначальная загрузка выполняется при REGARD_BOOTSTRAP_ON_START=true, затем синхронизации повторяются. Упоминания отсутствующего таймера в исторических разделах ниже больше не описывают текущий релиз. SHA-256 предотвращает повторный импорт; скачивание неизменённого ответа без подтверждённых HTTP validators не исключается.

## История предыдущих пакетов

Если backend успешно запущен, но Регард пуст: проверьте значение `REGARD_BOOTSTRAP_ON_START`. Значение `false` полностью пропускает локальный импорт; `REGARD_DOWNLOAD_ENABLED=false` оставляйте без изменений. После загрузки **всех трёх файлов** в Data backend установите `REGARD_BOOTSTRAP_ON_START=true` и перезапустите backend. Успех подтверждают строка `regard_bootstrap status=succeeded` и `/api/catalog/readiness` с `ready: true`, положительными `products` и `usable_offers`. Один `/api/health` подтверждает лишь запуск API. Если `status=not_imported`, проверьте Code-пакет, Data и переменную; если `not_authorized`, проверьте файл прав. После 72 часов от исходной даты XLSX статус станет `empty_or_historical` даже при сохранённых карточках.

Пакеты `UpgradeLab-Backend-Amvera-20261112.zip` и `UpgradeLab-Frontend-Amvera-20261112.zip` пересобраны со страницей «Бенчмарки» и графиком цен. Бенчмарки хранятся в backend Code как проверенные JSON, а история цен — в SQLite backend Data. В Data не загружаются бенчмарки и не создаются фиктивные цены. График цен с несколькими точками появится после импорта прайсов с разными исходными датами.

Для пустой Data подготовлен отдельный локальный пакет `UpgradeLab-Regard-Data-20261112.zip`. Он **не является Code-пакетом**: распакуйте его на компьютере и загрузите три файла по отдельности в Data backend-проекта после первого развёртывания. Прайс внутри пакета скачан штатным клиентом 12 ноября 2026 года: HTTP 200, SHA-256 `a7ae1760b26ef0a13c1e4319946b9095b0dce27774c25930d1a21f99e7a065e2`, исходная дата 2026-11-12 10:30 UTC. По действующему 72-часовому правилу он перестанет быть свежим для предварительного подбора после 2026-11-15 10:30 UTC. При более поздней загрузке замените только `price.xlsx` на свежий официальный файл. Backend Code и frontend Code предоставляются отдельными ZIP.

Дата подготовки: 2026-11-12. Публикация в Amvera не выполнена. Владелец подтвердил адреса:

- Frontend: https://frontendupgradelab-iwrawww.waw0.amvera.tech
- Backend: https://backendupgradelab-iwrawww.waw0.amvera.tech

Существующий корневой Dockerfile/amvera.yml относится к прежнему объединённому варианту и **не загружается ни в один из этих двух проектов**. Используйте два отдельных ZIP из текущего релиза, каждый распакуйте непосредственно в корень Code своего существующего проекта. Не загружайте ZIP как один файл без подтверждённой функции распаковки.

## Frontend: отдельный проект

Среда: Node.JS Browser. В корне Code frontend должны лежать `amvera.yml`, `package.json`, `package-lock.json`, `index.html`, `vite.config.js`, `postcss.config.js`, `tailwind.config.js`, папки `src/`, `public/images/` и `scripts/` (если есть); служебный `public/scripts/run.bat` не нужен. Dockerfile не нужен. `node_modules/` и `dist/` не загружать.

`frontend/amvera.yml` задаёт `build.additionalCommands: VITE_API_BASE_URL=https://backendupgradelab-iwrawww.waw0.amvera.tech npm run build` и `build.artifacts: "dist/*": /`. Это публичный URL, не секрет. Amvera не передаёт переменные из вкладки «Переменные» на этап сборки, поэтому установка только runtime-переменной `VITE_API_BASE_URL` не настроит уже собранный Vite bundle. При смене backend адреса измените `build.additionalCommands` и пересоберите frontend. `.env` и `.env.production` в пакет не включены. Frontend API client отправляет `credentials: 'include'`.

## Backend: отдельный проект

Среда: Docker. Dockerfile нужен для текущих Python-зависимостей и браузерного образа Playwright; frontend в этом образе не собирается. В корне Code backend должны лежать `amvera.yml`, `Dockerfile`, `.dockerignore`, `requirements.txt`, `requirements-browser.txt`, `seed_data.json`, `price_data.json`, папку `app/` и Python-модули из `scripts/` без локальных диагностических `scripts/price_data/`. `backend/amvera.yml` задаёт порт 80 и `persistenceMount: /data`. `backend/Dockerfile` запускает `python -m scripts.startup`: HTTP-сервер поднимается до долгого импорта, который выполняется в отдельном потоке одного Uvicorn worker.

Если браузер пишет «CORS: No Access-Control-Allow-Origin», сначала откройте backend `/api/health` напрямую. При ответе **503** это не отказ CORS внутри FastAPI: HTTP-приложение не ответило, и заголовки сформировал внешний прокси. 12 ноября 2026 года публичный backend отвечал 503 на `/api/health`, `/api/hardware`, `/api/auth/me` и `/api/catalog/readiness` даже при правильном `Origin`. Порт 80 и адрес `0.0.0.0` в коде совпадают с `amvera.yml`; новая версия убирает длительный импорт из пути до запуска HTTP. Если после загрузки она всё ещё даёт 503, проверьте статус контейнера, логи запуска, память/CPU и соответствие загруженного Code-пакета; без логов нельзя утверждать, что именно импорт был единственной причиной. [Справка Amvera по 502/503](https://docs.amvera.ru/general/FAQ/502-503-error.html).

В переменных backend-проекта установите:

```text
DATABASE_URL=sqlite:////data/pc_upgrade.db
FRONTEND_URL=https://frontendupgradelab-iwrawww.waw0.amvera.tech
BACKEND_URL=https://backendupgradelab-iwrawww.waw0.amvera.tech
CORS_ORIGINS=https://frontendupgradelab-iwrawww.waw0.amvera.tech
COOKIE_SECURE=true
COOKIE_SAMESITE=none
REGARD_BOOTSTRAP_ON_START=true
REGARD_DOWNLOAD_ENABLED=true
REGARD_PRICE_URL=https://www.regard.ru/api/site/pricelist
SOURCE_PERMISSIONS={"regard":{"automatic_network":true,"public_display":true,"basis":"UpgradeLab project owner confirmed authorized automatic download and public non-commercial display of official Regard XLSX on 2026-11-12","confirmed_by":"UpgradeLab project owner","confirmed_at":"2026-11-12T00:00:00Z"}}
OPENROUTER_SEARCH_ENABLED=false
OPENROUTER_ALLOW_PAID_WEB=false
```

Dockerfile задаёт `AMVERA=1`; код при этом использует указанные HTTPS-адреса как безопасные значения по умолчанию, а неверный список CORS origins вызывает ошибку конфигурации. Указывайте **только один** frontend origin в CORS, без завершающего слэша и `*`. Cookie `upgrade_session` имеет `HttpOnly; Secure; SameSite=None; Path=/`; `credentials: include` уже настроен на frontend. Для авторизованных записей и входа/регистрации в production требуется корректный `Origin`, чужой или отсутствующий отклоняется. Некоторые политики браузера могут блокировать сторонние cookie даже при этих атрибутах; это нужно проверить на настоящих HTTPS-адресах после публикации.

SQLite, аккаунты, объявления, сборки, каталог, журнал импорта и backup находятся **только в backend Data (/data)**. Нельзя заменять открытую SQLite копированием. Секреты SMTP, admin token и платных служб задаются только через защищённую конфигурацию среды при необходимости; в ZIP их нет.

## Локальный старт и проверка сетевой загрузки

1. Сначала разверните backend с `REGARD_BOOTSTRAP_ON_START=false`. После первого успешного развёртывания Amvera создаст Data.
2. Загрузите в **Data backend-проекта** три файла:
   - `/data/price.xlsx` — официальный свежий XLSX Регарда;
   - `/data/regard-schema.json` — схема штатного importer;
   - `/data/regard-rights.json` — новая запись с `automatic_download: true` и разрешением публичного некоммерческого показа. Старый файл с `automatic_download: false` не включает сеть.
3. В backend установите переменные из блока выше и перезапустите **backend**. HTTP должен стать доступен первым; фоновый процесс импортирует локальный XLSX, что создаёт запись прав в SQLite. Затем тот же штатный импортёр получает свежий XLSX с фиксированного HTTPS endpoint во временный каталог, проверяет и импортирует его. Только после успешного импорта файл атомарно заменяет `/data/price.xlsx`. Пока он работает, `/api/catalog/readiness` может отвечать `not_imported` или показывать прежний каталог. Frontend перезапускать не требуется.
4. Ищите в логах `regard_bootstrap status=succeeded` или `unchanged`, затем `regard_download` с HTTP 200 и `regard_network status=succeeded`. При 403/429, тайм-ауте или другом отказе будет `regard_network status=failed code=...`; старый каталог и файл остаются. Защиту источника не обходить.
5. Проверьте `https://backendupgradelab-iwrawww.waw0.amvera.tech/api/health` и отдельно `/api/catalog/readiness`: `ready: true`, положительные `products` и `usable_offers`. Затем `/api/catalog/products?page_size=1`, обычный frontend-каталог и сборку на 80 000/120 000 ₽. Проверяйте с обычным пользователем без admin token.
6. Для повторной сетевой проверки оставьте три разрешения включёнными и перезапустите backend. Текущая реализация проверяет сеть **при старте**, но не запускает ежедневный фоновый таймер; для регулярного обновления нужен отдельный механизм рестарта или планировщик.

Существующий `regard_sync` выполняет разбор и транзакционный импорт. Startup проверяет файл, схему и права, создаёт проверенный SQLite online backup перед изменением, затем вызывает штатный importer. SHA-256, импортный журнал и состояние каталога в SQLite определяют идемпотентность; внешний marker не используется. Источником даты цены остаётся XLSX. Прайс с нулём пригодных публичных кандидатов отклоняется до изменения старого каталога. Сохраняется политика preliminary до 72 часов; после её истечения каталог может стать историческим и `ready` перейдёт в false без потери истории. Сеть включается только совокупностью флага, точного URL, записи прав в SQLite и `SOURCE_PERMISSIONS`.

В Data-пакет включены `price.xlsx` из нового прямого скачивания, схема штатного импортёра и обновлённая запись прав владельца. Диагностика скачивания находится вне Code-пакетов: `C:\vscode\chumahack\regard-live-20261112-unrestricted\diagnostics.json`. Файл XLSX содержит 83 158 товарных строк, из них 5 832 строки выбранных категорий ПК. Часовой пояс +03:00 остаётся явной конфигурацией оператора, поскольку XLSX сам его не сообщает.

## Проверки и ограничения

Изолированный локальный bootstrap: 3 006 StoreOffer, 5 968 публичных карточек, повторный запуск `unchanged`, подбор на 120 000 ₽ вернул восемь деталей на 115 740 ₽ со статусом draft. Раздельные HTTPS origin, CORS, Secure/SameSite cookie и сессия проверены детерминированным TestClient без настоящей сети. Frontend bundle локально содержит точный backend URL, старый единый-origin вариант больше не используется для этих двух пакетов. Docker CLI отсутствует; сборка Docker и работа реальных Amvera адресов из текущей среды не подтверждены. После ручной загрузки нужны реальные browser E2E, проверка Data после рестарта и логи обоих проектов.

Официальная документация: [Node.JS Browser](https://docs.amvera.ru/applications/environments/nodejs-browser.html), [Docker](https://docs.amvera.ru/applications/configuration/docker.html), [переменные и секреты](https://docs.amvera.ru/applications/configuration/variables.html), [Code и Data](https://docs.amvera.ru/applications/storage.html).
### Как проверить дату прайса после импорта

`GET /api/catalog/readiness` в новой backend-версии возвращает `latest_source_price_at`. Это дата, заявленная в XLSX, в UTC; время `imported_at` в карточках означает лишь момент переноса в SQLite. Если сегодня 12 ноября, а `latest_source_price_at` остаётся 11 ноября, сервер использует старый файл `/data/price.xlsx` либо загрузка нового файла не завершилась. Обновите три файла в Data backend-проекта из отдельного Regard Data ZIP и перезапустите backend с разрешённым `REGARD_BOOTSTRAP_ON_START=true`. Для сети дополнительно нужны `REGARD_DOWNLOAD_ENABLED=true`, точный `REGARD_PRICE_URL` и право `automatic_download` в `/data/regard-rights.json`; сеть проверяется только при запуске. Не считайте импорт успешным по одному `ready=true`: сравните `latest_source_price_at` с ожидаемой датой XLSX и проверьте историю конкретного товара.


## 2026-11-16 — Regard recovery release

Live readiness inspection found 5,832 stored products, zero usable offers and source date 2026-11-12T10:30:00Z. All bootstrap/download/scheduler flags were enabled. An expired local file could fail bootstrap and prevent the subsequent network refresh. The backend now attempts authorized network refresh even when local bootstrap fails, using the validated /data/regard-rights.json without creating new permissions or overwriting the database before a successful import.

The fixed official downloader fetched an XLSX dated 2026-11-15T14:30:00Z. Offline import into a separate copy of the local SQLite produced 5,965 CatalogProduct records and 2,966 usable preliminary offers; readiness=true. Repeated bootstrap returned unchanged. These are price-list offers, not store-confirmed stock. Production has not been modified by this verification.

Upload the updated separate backend and frontend Code ZIPs. Preserve backend /data and the schema/rights files. REGARD_BOOTSTRAP_ON_START, REGARD_DOWNLOAD_ENABLED and REGARD_DAILY_SYNC_ENABLED must be true; explicit Amvera variables override Docker defaults. After restart verify /api/catalog/readiness and that latest_source_price_at advances. Do not extend TTL to hide failed synchronization.


## Steam requirements — 16.11.2026

Реализованы SQLite-кеш, durable очередь, отдельный HTTPX worker и интеграция с FPS Engine без LLM/Chromium. На Amvera включается STEAM_WORKER_ENABLED=true (автоматически при AMVERA=1). Проверки и ограничения: [STEAM_REQUIREMENTS.md](STEAM_REQUIREMENTS.md). Остаётся проверка Linux lifecycle и точности прогнозов на независимых измерениях; deployment не выполнялся.


### Steam lifecycle hardening, 16.11.2026

Один Uvicorn --workers 1, supervised дочерний worker, общий явный DATABASE_URL /data, restart check 15 s, idle queue 10 s. Новые SQLite используют DELETE/FULL вместо принудительного WAL. Реальные browser E2E и Windows crash/restart пройдены. Linux/container и фактический storage Amvera не проверены из-за отсутствия Docker/WSL; подготовлен scripts.steam_linux_smoke. Подробности, RAM и команды: [STEAM_REQUIREMENTS.md](STEAM_REQUIREMENTS.md), steam_amvera_validation.json.
