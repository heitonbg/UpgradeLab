# UpgradeLab: выпуск на Amvera

Статус: публичное развёртывание не подтверждено. Локальный Git содержит только GitHub remote; Amvera remote и адрес существующего проекта отсутствуют. Docker CLI локально отсутствует.

## Проверенная конфигурация

Корневой Dockerfile собирает React/Vite и обслуживает SPA через FastAPI на порту 80. amvera.yml задаёт containerPort 80 и persistenceMount /data. При AMVERA=1 SQLite находится в /data/pc_upgrade.db; запускается один Uvicorn worker.

## Перед выпуском

1. Получить адрес существующего проекта Amvera и доступ к нему без передачи паролей в чат.
2. Проверить переменные среды и право публичного показа каталога Регарда.
3. Сохранить прежнюю версию и создать проверенный online backup существующей production SQLite.
4. Выполнить backend/frontend регрессию, production build, browser E2E и git diff --check.
5. Исключить из commit .env, SQLite, XLSX, фотографии и локальные артефакты.
6. После фактической сборки проверить HTTPS, /api/health, каталог, подбор, регистрацию, биржу, сохранение после рестарта и логи.

## Rollback

Остановить писателей SQLite. Вернуть предыдущий проверенный образ, сохранив /data. Восстанавливать БД из проверенного online backup только при необходимости. Не заменять открытую SQLite копированием поверх работающего приложения.

Commit hash, публичный URL, количество товаров и production E2E фиксируются только после настоящего развёртывания.

## Ручная загрузка владельцем в Amvera

Загружать **корень одного репозитория UpgradeLab** как одно Docker-приложение: корневые `Dockerfile`, `amvera.yml`, `.dockerignore`, папки `backend/` и `frontend/`. Отдельно загружать backend и frontend не требуется: Dockerfile собирает React и затем раздаёт его через FastAPI с одного HTTPS origin. Порт контейнера 80. В Amvera надо выбрать существующий проект и Docker-сборку по корневому Dockerfile; не создавать два платных приложения. `frontend/dist` и `node_modules` не загружать — они собираются в контейнере.

В переменных среды Amvera задать `AMVERA=1`, `DATABASE_URL=sqlite:////data/pc_upgrade.db`, `COOKIE_SECURE=true`, `CORS_ORIGINS` и `FRONTEND_URL` под фактический HTTPS origin, `REGARD_DOWNLOAD_ENABLED=false`, `OPENROUTER_SEARCH_ENABLED=false`, `OPENROUTER_ALLOW_PAID_WEB=false`. Секреты SMTP и другие ключи заполнять только через защищённую конфигурацию Amvera, если функция нужна. `backend/.env` не загружать. Ожидается один Uvicorn worker.

После первого успешного запуска Data (/data) использовать для чистой SQLite и контролируемого импорта официального XLSX. Схему и файл прав положить туда же вне Code. Команда из существующей документации: `python -m scripts.regard_sync --database /data/pc_upgrade.db --schema /data/regard-schema.json --rights /data/regard-rights.json --file /data/price.xlsx --audience public-noncommercial`. Если прайс старше 72 часов, импорт не сделает предложения актуальными: потребуется новый разрешённый официальный файл. Загрузку файлов и команду импорта выполнять только в существующем проекте после проверки полномочий и backup, не с тестовой SQLite.

Проверить в браузере `https://<фактический-домен>/` и `/api/health`, затем каталог, подбор, регистрацию, объявление и повторный вход после рестарта. Статус остаётся непроверенным до получения реального URL и логов сборки.
