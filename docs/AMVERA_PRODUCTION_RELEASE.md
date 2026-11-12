# UpgradeLab — ручная загрузка и одноразовый импорт на Amvera

Статус: проверено локально на изолированной SQLite; настоящий контейнер Amvera и публичный HTTPS пока не проверены. Приложение разворачивается **одним Docker-проектом**, а не отдельными backend/frontend проектами. Корневой Dockerfile собирает React и запускает один Uvicorn worker через scripts.startup на порту 80. amvera.yml монтирует постоянный Data в /data. [Официальная документация Amvera](https://docs.amvera.ru/applications/configuration/docker.html).

## 1. Что загрузить в Code

Распакуйте актуальный UpgradeLab-Amvera ZIP и загрузите **содержимое его корня** в Code существующего проекта Amvera. В корне Code должны лежать:

- Dockerfile
- amvera.yml
- .dockerignore
- frontend/
- backend/

Это один проект. Не загружайте ZIP как отдельный файл без распаковки, если интерфейс не подтверждает распаковку. Не загружайте frontend/dist, frontend/node_modules, backend/.venv, backend/.env, SQLite, XLSX, .artifacts, фотографии пользователей или .git.

### Backend: точный состав, который Dockerfile копирует в контейнер

- backend/requirements.txt
- backend/requirements-browser.txt
- backend/app/ — **все вложенные файлы и папки** приложения
- backend/scripts/ — **все вложенные файлы и папки**, в том числе startup.py, regard_sync.py, init_db.py
- backend/seed_data.json
- backend/price_data.json

backend/tests/ и локальные базы для запуска контейнера не нужны; .dockerignore исключает tests и *.db. В ZIP тесты могут присутствовать как исходники, но Docker их не копирует.

### Frontend: точный состав для сборки

- frontend/package.json
- frontend/package-lock.json
- frontend/index.html
- frontend/vite.config.js
- frontend/src/ — **все вложенные файлы и папки**
- frontend/public/ — **все вложенные файлы и папки**, если она присутствует

Dockerfile копирует frontend/ целиком и выполняет npm ci, затем npm run build. Готовый dist генерируется при сборке. Отдельный адрес или сервер для frontend не нужен.

## 2. Первый запуск

Используйте существующий Docker-проект и не создавайте новый платный экземпляр. Переменные среды:

- AMVERA=1
- DATABASE_URL=sqlite:////data/pc_upgrade.db
- REGARD_BOOTSTRAP_ON_START=false
- COOKIE_SECURE=true
- FRONTEND_URL=https://<фактический-домен>
- CORS_ORIGINS=https://<фактический-домен>
- REGARD_DOWNLOAD_ENABLED=false
- OPENROUTER_SEARCH_ENABLED=false
- OPENROUTER_ALLOW_PAID_WEB=false

Не задавайте VITE_API_BASE_URL на старый внешний backend: запросы уже идут на относительный /api того же origin. Секреты SMTP/других служб добавляются только через защищённую конфигурацию среды, если они требуются. Не копируйте backend/.env. После первого успешного развёртывания в интерфейсе появится постоянная папка Data; официальная документация Amvera указывает, что Data доступна после первого запуска.

## 3. Три файла в Data

В постоянную папку Data загрузите:

- /data/price.xlsx — официальный XLSX Регарда, не тестовую фикстуру.
- /data/regard-schema.json — операторскую схему существующего native Regard importer.
- /data/regard-rights.json — операторское подтверждение public-noncommercial права именно для этого источника; commercial и automatic_download не включать без отдельного разрешения.

Эти файлы не входят в ZIP исходников и не должны попадать в Code/Git. Исходная дата берётся из XLSX, время загрузки файла её не заменяет. Публичная витрина и предварительный подбор подчиняются прежнему окну свежести до 72 часов.

## 4. Включить импорт без терминала

В настройках среды измените REGARD_BOOTSTRAP_ON_START=true и перезапустите приложение в Amvera. Контейнер до запуска Uvicorn проверит файлы, права, структуру XLSX и исходную дату; сделает проверенный online backup существующей SQLite в /data/backups; вызовет существующий scripts.regard_sync с audience public-noncommercial. При ошибке старый каталог остаётся доступным, HTTP запускается, а /api/catalog/readiness сообщает об отсутствии готового каталога. Ни один публичный HTTP endpoint импорт не запускает.

В логах ищите `regard_bootstrap status=succeeded sha256=... published=... backup=... source_date=...`. `status=unchanged` означает, что тот же вход и состояние SQLite уже подтверждены журналом импорта; повторного изменения каталога нет. `status=failed code=...` означает, что импорт не состоялся; код ошибки не содержит секретов.

## 5. Проверить результат

Откройте `https://<домен>/api/health` — это только доступность HTTP. Отдельно откройте `https://<домен>/api/catalog/readiness`: ожидаются `ready: true`, положительные `products` и `usable_offers`. Откройте `/api/catalog/products?page_size=1` и обычную страницу каталога без admin token. Проверьте подбор ПК на 80 000 и 120 000 ₽ с разрешённым источником Regard и биржей UpgradeLab. После перезапуска проверьте, что счётчики и пользовательские данные сохранились.

Когда первоначальная настройка завершена, рекомендуется вернуть REGARD_BOOTSTRAP_ON_START=false. Для обновления перед демонстрацией загрузите новый официальный price.xlsx в Data, снова выставьте true и перезапустите приложение. Если SHA-256 совпадает с уже импортированным файлом и состояние SQLite не изменилось, импорт будет пропущен. Новая дата прайса остаётся исходной датой из файла.

## 6. Backup и rollback

Перед изменением существующей БД bootstrap создаёт SQLite online backup и проверяет PRAGMA integrity_check. Запуск рассчитан на один production контейнер; блокировка на /data предотвращает одновременные bootstrap попытки, существующая блокировка защищает сам importer. При откате приложения сохраняйте /data. Для восстановления БД сначала остановите писателей SQLite и используйте проверенную резервную копию; не копируйте .db поверх работающего процесса. Не удаляйте старую историю цен вручную.

## 7. Что ещё не подтверждено

Docker CLI локально отсутствует, поэтому сборка и рестарт именно в Amvera, публичный HTTPS, ресурсы тарифа и сохранение /data после облачного рестарта должны быть проверены по фактическому URL и логам. Локальная проверка нового bootstrap: официальный XLSX из изолированной тестовой папки, 3 006 опубликованных предложений, 5 968 карточек, повторный запуск пропущен, /api/catalog/readiness вернул ready=true. Это не свидетельство об успешном облачном импорте.

### Проверенные локальные файлы для Data

В этой рабочей копии локальный тест использовал следующие **не включённые в ZIP** файлы:

- `.artifacts/product-readiness-20261111/latest-download/price.xlsx` → переименовать при загрузке в `/data/price.xlsx`.
- `.artifacts/regard-real-iteration12-final/schema.json` → `/data/regard-schema.json`.
- `.artifacts/product-readiness-20261111/regard-public-demo-rights.json` → `/data/regard-rights.json`.

Исходная дата проверенного XLSX: `2026-11-11T14:30:00Z`. К моменту вашей загрузки она может выйти за окно 72 часов; тогда получите новый официальный XLSX и проверьте разрешение на его использование. Локальный файл прав не подменяет вашу проверку разрешения на публичный показ.

Production Vite теперь использует относительный /api на том же HTTPS origin. Ранее отслеживаемый frontend/.env.production содержал адрес старого отдельного backend; он удалён из сборочной конфигурации. Проверка production bundle: старый адрес отсутствует.

Перед применением нового файла bootstrap требует хотя бы одного пригодного публичного кандидата в подготовленном плане. Прайс с нулём таких кандидатов отклоняется до изменения прежнего каталога; `/api/catalog/readiness` проверяет наличие реальных StoreOffer и действующую свежесть. Эти проверки не продлевают TTL старого прайса.
