# UpgradeLab: два проекта Amvera — frontend и backend

Дата подготовки: 2026-11-12. Публикация в Amvera не выполнена. Владелец подтвердил адреса:

- Frontend: https://frontendupgradelab-iwrawww.waw0.amvera.tech
- Backend: https://backendupgradelab-iwrawww.waw0.amvera.tech

Существующий корневой Dockerfile/amvera.yml относится к прежнему объединённому варианту и **не загружается ни в один из этих двух проектов**. Используйте два отдельных ZIP из текущего релиза, каждый распакуйте непосредственно в корень Code своего существующего проекта. Не загружайте ZIP как один файл без подтверждённой функции распаковки.

## Frontend: отдельный проект

Среда: Node.JS Browser. В корне Code frontend должны лежать `amvera.yml`, `package.json`, `package-lock.json`, `index.html`, `vite.config.js`, `postcss.config.js`, `tailwind.config.js`, папки `src/`, `public/` и `scripts/` (если есть). Dockerfile не нужен. `node_modules/` и `dist/` не загружать.

`frontend/amvera.yml` задаёт `build.additionalCommands: VITE_API_BASE_URL=https://backendupgradelab-iwrawww.waw0.amvera.tech npm run build` и `build.artifacts: "dist/*": /`. Это публичный URL, не секрет. Amvera не передаёт переменные из вкладки «Переменные» на этап сборки, поэтому установка только runtime-переменной `VITE_API_BASE_URL` не настроит уже собранный Vite bundle. При смене backend адреса измените `build.additionalCommands` и пересоберите frontend. `.env` и `.env.production` в пакет не включены. Frontend API client отправляет `credentials: 'include'`.

## Backend: отдельный проект

Среда: Docker. Dockerfile нужен для текущих Python-зависимостей и браузерного образа Playwright; frontend в этом образе не собирается. В корне Code backend должны лежать `amvera.yml`, `Dockerfile`, `.dockerignore`, `requirements.txt`, `requirements-browser.txt`, `seed_data.json`, `price_data.json`, папки `app/` и `scripts/`. `backend/amvera.yml` задаёт порт 80 и `persistenceMount: /data`. `backend/Dockerfile` запускает `python -m scripts.startup`, который вызывает опциональный импорт **до** одного Uvicorn worker.

В переменных backend-проекта установите:

```text
DATABASE_URL=sqlite:////data/pc_upgrade.db
FRONTEND_URL=https://frontendupgradelab-iwrawww.waw0.amvera.tech
BACKEND_URL=https://backendupgradelab-iwrawww.waw0.amvera.tech
CORS_ORIGINS=https://frontendupgradelab-iwrawww.waw0.amvera.tech
COOKIE_SECURE=true
COOKIE_SAMESITE=none
REGARD_BOOTSTRAP_ON_START=false
REGARD_DOWNLOAD_ENABLED=false
OPENROUTER_SEARCH_ENABLED=false
OPENROUTER_ALLOW_PAID_WEB=false
```

Dockerfile задаёт `AMVERA=1`; код при этом использует указанные HTTPS-адреса как безопасные значения по умолчанию, а неверный список CORS origins вызывает ошибку конфигурации. Указывайте **только один** frontend origin в CORS, без завершающего слэша и `*`. Cookie `upgrade_session` имеет `HttpOnly; Secure; SameSite=None; Path=/`; `credentials: include` уже настроен на frontend. Для авторизованных записей и входа/регистрации в production требуется корректный `Origin`, чужой или отсутствующий отклоняется. Некоторые политики браузера могут блокировать сторонние cookie даже при этих атрибутах; это нужно проверить на настоящих HTTPS-адресах после публикации.

SQLite, аккаунты, объявления, сборки, каталог, журнал импорта и backup находятся **только в backend Data (/data)**. Нельзя заменять открытую SQLite копированием. Секреты SMTP, admin token и платных служб задаются только через защищённую конфигурацию среды при необходимости; в ZIP их нет.

## Одноразовый импорт без терминала

1. Сначала разверните backend с `REGARD_BOOTSTRAP_ON_START=false`. После первого успешного развёртывания Amvera создаст Data.
2. Загрузите в **Data backend-проекта** три файла:
   - `/data/price.xlsx` — официальный свежий XLSX Регарда;
   - `/data/regard-schema.json` — схема штатного importer;
   - `/data/regard-rights.json` — подтверждённые права на публичный некоммерческий показ.
3. В backend включите `REGARD_BOOTSTRAP_ON_START=true` и перезапустите **backend**. Frontend перезапускать не требуется.
4. Ищите в логах `regard_bootstrap status=succeeded`, положительный `published`, SHA-256, исходную дату и имя backup. `status=unchanged` означает пропуск уже обработанного файла; `status=failed code=...` — импорт не выполнен.
5. Проверьте `https://backendupgradelab-iwrawww.waw0.amvera.tech/api/health` и отдельно `/api/catalog/readiness`: `ready: true`, положительные `products` и `usable_offers`. Затем `/api/catalog/products?page_size=1`, обычный frontend-каталог и сборку на 80 000/120 000 ₽. Проверяйте с обычным пользователем без admin token.
6. После завершения настройки рекомендуем вернуть `REGARD_BOOTSTRAP_ON_START=false`. Для обновления замените официальный `price.xlsx` в backend Data, включите флаг и перезапустите backend.

Существующий `regard_sync` выполняет разбор и транзакционный импорт. Startup проверяет файл, схему и права, создаёт проверенный SQLite online backup перед изменением, затем вызывает штатный importer. SHA-256, импортный журнал и состояние каталога в SQLite определяют идемпотентность; внешний marker не используется. Источником даты цены остаётся XLSX. Прайс с нулём пригодных публичных кандидатов отклоняется до изменения старого каталога. Сохраняется политика preliminary до 72 часов; после её истечения каталог может стать историческим и `ready` перейдёт в false без потери истории. Автоматическое скачивание выключено.

Для локальной проверки использовались **не включённые в ZIP** файлы `.artifacts/product-readiness-20261111/latest-download/price.xlsx`, `.artifacts/regard-real-iteration12-final/schema.json`, `.artifacts/product-readiness-20261111/regard-public-demo-rights.json`. Дата проверенного XLSX — `2026-11-11T14:30:00Z`; перед демонстрацией проверьте, что он ещё в окне свежести и что право использования распространяется на загружаемый файл.

## Проверки и ограничения

Изолированный локальный bootstrap: 3 006 StoreOffer, 5 968 публичных карточек, повторный запуск `unchanged`, подбор на 120 000 ₽ вернул восемь деталей на 115 740 ₽ со статусом draft. Раздельные HTTPS origin, CORS, Secure/SameSite cookie и сессия проверены детерминированным TestClient без настоящей сети. Frontend bundle локально содержит точный backend URL, старый единый-origin вариант больше не используется для этих двух пакетов. Docker CLI отсутствует; сборка Docker и работа реальных Amvera адресов из текущей среды не подтверждены. После ручной загрузки нужны реальные browser E2E, проверка Data после рестарта и логи обоих проектов.

Официальная документация: [Node.JS Browser](https://docs.amvera.ru/applications/environments/nodejs-browser.html), [Docker](https://docs.amvera.ru/applications/configuration/docker.html), [переменные и секреты](https://docs.amvera.ru/applications/configuration/variables.html), [Code и Data](https://docs.amvera.ru/applications/storage.html).
