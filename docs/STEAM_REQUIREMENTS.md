# Steam Requirements Enrichment

Реализация от 16.11.2026. Steam дополняет требования игр, а не поставляет измеренные FPS. Измерения сохраняют прежний приоритет. Рабочая SQLite не изменялась: импорт, миграции и нагрузочные проверки выполнены на копиях.

## Поток данных

Выбор подтверждённой локальной игры → POST /api/games/requirements → локальный кеш либо одна durable-задача → отдельный worker → Steam appdetails → разбор и строгие Hardware ID → SQLite → существующий FPS Engine v4. GET /api/games/requirements?game=... только читает состояние. API не ждёт Steam. Поиск `33 expedition` локально находит Clair Obscur: Expedition 33, AppID 1903340; перестановка токенов не запускает сеть.

Изменены backend config/models/migrations/main, game_catalog, adaptive_fps, requirements_anchored_fps, frontend GamePicker/CalculatorSection/BuildSection/FpsEvidence и package.json. Добавлены steam_http.py, steam_parser.py, steam_storage.py, API steam_requirements.py, workers/steam_requirements_worker.py, slim steam_game_index.json и scripts/build_steam_index.py, тесты test_steam_http_parser.py/test_steam_queue.py и frontend steamRequirements.js/.test.js, useSteamRequirements.js. Неиспользовавшийся прототип ai_fps удалён; существующая продуктовая интеграция OpenRouter не переписана.

## Настройки и Amvera

STEAM_REQUIREMENTS_ENABLED=true. STEAM_WORKER_ENABLED=true для backend Amvera (по умолчанию true при AMVERA=1; локально false). Остальные начальные значения: STEAM_REQUEST_INTERVAL_SECONDS=4, STEAM_REQUEST_TIMEOUT_SECONDS=10, STEAM_CACHE_DAYS=30, STEAM_NEGATIVE_CACHE_DAYS=7, STEAM_MAX_ATTEMPTS=3, STEAM_MAX_PENDING=500.

Backend после создания новых таблиц запускает `python -m app.workers.steam_requirements_worker`. Один OS lock на каталог SQLite допускает только один worker. Второй проверенный процесс завершился с another_worker. Очередь, cooldown, lease и кеш находятся в SQLite /data backend. Перед добавлением отсутствующих таблиц существующей SQLite создаётся online backup в backups с integrity_check. Аккаунты, объявления, сборки, PassMark-баллы не перезаписываются. Frontend собирается обычной командой npm run build, дополнительных секретов нет. Не загружайте локальную тестовую БД вместо /data.

На одном хосте несколько Uvicorn-процессов используют один worker и SQLite; независимые контейнеры с раздельными /data не разделяют кеш/лимит. Сетевой SQLite не рекомендуется. Проверить переносимость OS lock и завершение child-процесса на целевой Linux Amvera после загрузки; deployment в этой итерации не выполнялся.

## HTTP и безопасность

Переиспользуемый HTTPX AsyncClient, httpcore pool 1, connect 5 s, общий timeout 10 s, 2 MiB максимум. Только HTTPS store.steampowered.com:443 и фиксированные appdetails/storesearch; произвольные URL не принимаются. DNS проверяется существующей SSRF-политикой, соединение закрепляется за публичным IP, peer проверяется, TLS/SNI остаётся доменным. trust_env=false, редиректы и compressed responses отключены. Проверяются статус, JSON, AppID, type game и точное название. Storesearch вызывается лишь при неизвестном AppID: уникальное точное название/алиас, не первый результат. DLC, demo, soundtrack не подменяют основную игру.

4 секунды — собственная политика ограничения нагрузки, не обещанный Steam лимит. 429 учитывает Retry-After; 403 даёт суточный cooldown; 5xx/timeout имеют максимум 3 попытки с задержками. Нет inline retries или бесконечного ожидания. Durable lease 120 s, stale worker не может записать результат после перехвата задачи. 100 одинаковых выборов дедуплицируются. Отрицательный кеш на 7 дней; успешные требования на 30 дней; пустой результат не уничтожает более качественный прежний кеш. Очередь ограничена 500 задачами.

## Парсинг и математическая интеграция

Сохраняются исходные HTML minimum/recommended, очищенный текст, OS/DX/notes/VRAM, все CPU/GPU альтернативы, Hardware ID/существующие scores, даты UTC, SHA-256 и версия парсера. Неизвестные модели не выдумываются; 5600/5600X, Ti/SUPER/XTX и mobile различаются. Если SKU известен, но каталог не содержит достоверного VRAM-варианта, хранится unknown_in_catalog; это не подтверждённая ёмкость памяти. Конфликт известного VRAM не обходится.

Recommended не означает 60 FPS. Явно опубликованные FPS/разрешение/пресет хранятся как developer_stated_target_not_measurement. Использование такого workload target допускается только при полностью явных совпадающих условиях: preset/resolution, native, без RT и FG; иначе прежняя GPU-кривая остаётся опорой. Требования дополняют существующий CPU/GPU-сценарий, RAM не входит в формулу. Для 1440p/4K при отсутствии замеров возможен явно маркированный перенос GPU-нагрузки по числу пикселей: это приближение, не измерение и не универсальный закон игры. 1% Low не выдумывается. Steam не повышает estimated до measured.

Frontend отправляет задачу только после выбора игры; максимум 12 опросов по 5 s, дедупликация одновременных запросов, ограниченный локальный кеш. Версия новых требований запускает однократное обновление текущего результата без нового поиска цен и без сброса конфигурации. При недоступном worker остаётся прежний FPS fallback.

## Реальная проверка

22/22 appdetails: HTTP 200, валидный JSON. Recommended присутствует у 14/22, явные CPU и GPU у 13/22. Среднее время HTTPX 0.306 s; отдельный запрос нового pinned-клиента 0.772 s. Ответы и размеры по каждой игре — steam_requirements_validation.json. Минимальные реальные fixtures Expedition 33/Portal 2 приложены к тестам. Полная массовая выгрузка 16 тысяч игр не выполнялась.

Для Expedition 33 рекомендованы i7-12700K (Hardware 84, CPU Mark 34230), Ryzen 7 5800X (130, 27656), RTX 3060 Ti (1502, G3D 20210), RX 6800 XT (1472, 25118). Legacy-каталог не подтверждает VRAM последних двух SKU. Для Ryzen 5 5600 + RTX 3060 Ti, 1080p High: до обогащения 55.0 FPS, после 51.7 FPS, requirements_scenario_available false → true. Это сравнение двух прогнозов; оно не доказывает меньшую ошибку против реальной игры. Издатель указывает 60 FPS 1080p High, но не все условия RT/апскейла/FG — этот target сохранён, не принят за измерение.

Одна новая игра с известным AppID требует 1 HTTP; с неизвестным — до 2 (search + details), каждый с pacing. Повторный выбор из кеша — 0 HTTP. В реальной проверке 100 параллельных cached POST дали 100 HTTP 200, всего сохранилась 1 задача и 1 выполненный Steam-запрос. Unit-тест отдельно проверяет 100 одновременных первичных постановок → 1 задача.

Локальные Windows-замеры, не обещание Amvera: SQLite status median 0.373 ms / p95 0.425 ms; cached API median 2.26 ms / p95 2.521 ms; 100 конкурентных cached POST median 37.869 ms; enqueue 13.895 ms. Worker working set 112.43 MiB (peak 117.53), backend 184.58 MiB (peak 230.81). Замер включает загруженный локальный Hardware, но не Chromium. При выключенном worker новая игра возвращает queued, API продолжает отвечать и FPS использует fallback. Для небольшого VPS это существенно легче браузера, но реальный запас памяти проверяется вместе с Regard и оптимизатором на хостинге.

## Воспроизведение

Используйте тестовую DATABASE_URL, AMVERA=0 и STEAM_WORKER_ENABLED=false. Backend: `.venv/Scripts/python -m unittest discover -s tests -q`; профильные: `-p test_steam*.py`. Frontend: `npm test`, `npm run build`. Компиляция: `python -m compileall -q app`. Для живой проверки на копии SQLite запустить worker отдельно и выбрать игру API. Не повторять все 22 запросa при каждом CI-прогоне; fixtures и MockTransport проверяют HTTP без сети.

## Условия источника и ограничения

[Steam Web API Terms](https://steamcommunity.com/dev/apiterms), [robots.txt](https://store.steampowered.com/robots.txt), [официальный IStoreService](https://partner.steamgames.com/doc/webapi/IStoreService). robots.txt не является лицензией. Store appdetails/storesearch проверены без API key, но не имеют гарантированного публичного контракта; официальный GetAppList не используется. На исходный текст требований не заявляется открытая лицензия или право массового распространения. Производный локальный индекс PCGameBenchmarks сохраняет имеющуюся CC BY 4.0 атрибуцию. Изменения условий/403 останавливают источник, обхода защиты нет.

Не все игры Steam имеют recommended; некоторые SKU/VRAM не разрешаются, Linux/Amvera пока не проверены, реальные FPS-ошибки по этим требованиям не измерены. Автоматического полного сканирования каталога нет. Дальнейшее расширение — контролируемая выборка реальных измерений и проверка ошибки, а не приписывание требований к measured FPS.

## Итог проверок

Backend: 817 тестов, 815 успешно, 2 пропущены, 199.666 s. Профильные Steam: 45/45 успешно. Frontend: 129/129 успешно. Production build, compileall и git diff --check завершились успешно. В suite остались прежние DeprecationWarning datetime.utcnow, они не исправлялись в этой итерации. Браузерный E2E новой auto-refresh цепочки не выполнялся: проверены frontend orchestration unit-тесты и реальный backend HTTP на копии БД. Полный git diff --stat содержит изменения предыдущих итераций; см. steam_worktree_diffstat.txt, новые untracked файлы перечислены отдельно выше.

Предлагаемый коммит: `feat: enrich game requirements through a durable Steam worker`. Коммит не создан.


## Финальная проверка lifecycle Amvera — 16.11.2026

Конфигурация backend/amvera.yml: Docker, containerPort 80, persistenceMount /data. Docker CMD: `python -m scripts.startup`. Entrypoint выполняет exec:

```sh
uvicorn app.main:app --host 0.0.0.0 --port 80 --workers 1 --timeout-graceful-shutdown 30
```

Проверяется абсолютный SQLite DATABASE_URL внутри /data: `sqlite:////data/pc_upgrade.db`. Хранение /app для Amvera отклоняется. API после миграций запускает SteamSupervisor, захватывающий отдельный OS lock для этой БД. Он создаёт `python -m app.workers.steam_requirements_worker`, передавая эффективный DATABASE_URL явно в окружении. Worker дополнительно держит собственный OS lock. Ни второй Uvicorn-процесс, ни ручной запуск второго worker не создают второго обработчика общей очереди. Не нужно создавать отдельный Amvera-проект для worker: SQLite принадлежит backend-проекту.

Supervisor проверяет только состояние дочернего процесса раз в 15 s и перезапускает упавший процесс. Ошибка Popen логируется, сайт продолжает запуск и повторяет попытку через 15 s. Нет горячего restart loop. При остановке FastAPI останавливается supervisor, worker получает SIGTERM, ожидание до 20 s, затем принудительное завершение. Linux worker обрабатывает SIGTERM/SIGINT через asyncio.Event. В Windows исправлено завершение дерева venv launcher → настоящий Python, чтобы не оставлять worker с удерживаемым lock.

Очередь проверяется раз в STEAM_WORKER_IDLE_SECONDS=10 (2..60), когда пуста; supervisor не опрашивает SQLite. Небольшая задержка до 10 s перед новой задачей — сознательный компромисс CPU. После аварии running-задачу можно забрать после lease 120 s, не более установленного числа попыток. Durable task/cache/lease/cooldown находятся в /data; после пересборки меняется Code, а Data по документации Amvera сохраняется.

### Journal mode

Удалено безусловное PRAGMA journal_mode=WAL при каждом соединении: тип файловой системы и межпроцессные блокировки реального тома Amvera не проверены. Новые файлы используют SQLite DELETE; synchronous=FULL, busy_timeout=30000. Все 20 queue-тестов теперь выполняются на DELETE, включая 100 первичных конкурентных запросов. Уже существующая WAL-БД автоматически не конвертируется и не удаляется: сохранность данных важнее скрытой смены режима. Если существующая Amvera-БД использует WAL, до подтверждения поддержки хранилища следует остановить все её процессы, сделать проверенный online backup и только затем отдельно выполнить checkpoint/смену режима на отключённой копии с integrity_check; не удалять -wal/-shm вручную.

### Реальные результаты этой итерации

Браузер Edge через локальный Playwright, настоящий React UI и FastAPI на разных origin (5174/8005), копия SQLite, fixture-client worker. Поиск `33 expedition` → выбор игры → fallback 55 FPS → выполнение durable-задачи → один автоматический POST calculate → 52 FPS, без перезагрузки и JS-ошибок. Сохранённая fixture — реальный ответ Steam, но HTTP в E2E заменён детерминированным клиентом. Сетевая часть отдельно проверена настоящим worker на тестовой БД: задача завершилась available, attempts=1. При 100 конкурентных cached POST все 100 успешны, единственная задача не дублировалась.

Проверены Portal 2 без Recommended и повторное открытие отрицательного кеша; положительный кеш Expedition 33 при повторном открытии; HTTP 503; выключенный worker; смена игры во время ожидания. В ошибочных сценариях ровно 12 GET polling, затем тишина; при смене игры поле осталось Portal 2. Для ускорения только ошибочных E2E ожидание 5 s заменено тестовым таймером на 100 ms, production-интервалы не менялись.

Проверка реального процесса: одновременный второй worker завершается another_worker; аварийное завершение первого и запуск замены; sentinel SQLite сохранён, integrity_check=ok. `/api/health` оставался HTTP 200 во время принудительного завершения работающего сетевого worker; supervisor запустил замену (17800 → 10144). Lease recovery проверен детерминированным тестом, без ожидания 120 s в CI. Удаление Code/пересборка контейнера и настоящий том Amvera не испытывались.

Windows-замеры (один Uvicorn, без Regard, без FPS optimizer workload): API 122.84 MiB, worker 112.59 MiB, venv launcher 4.11 MiB; суммарно 239.54 MiB. CPU за 10 s простоя: 0 по дискретному счётчику Windows, это не доказательство абсолютного нулевого потребления. Одна новая задача: 6.781 s включая ожидание очереди и обработку, CPU worker +0.10938 s. После задачи API 123.71 MiB, worker 114.72 MiB. Cached API median 12.185 ms / p95 22.599 ms; 100 cached POST/20 потоков — 100 available, median 44.325 ms; enqueue 32.729 ms. Это локальные измерения, не SLA дешёвого Amvera.

Эксперимент с Worker.run в одном процессе после прогрева локального API: 114.94 → 115.09 MiB, +0.15 MiB; CPU простоя +0.01562 s/10 s. Это только импорт/пустая очередь, без тяжёлого parse и без проверки задержек API при HTTP+разборе. Меньший RAM ожидаем, но production оставлен отдельным процессом: SQLite/BS4/сопоставление синхронны, перенос их на основной event loop пока не доказан безопасным для latency; изоляция падений и уже проверенный lifecycle важнее смены схемы в этой итерации. Для сервера с 256 MiB общего лимита текущая схема слишком тесная; запас нужно оценивать вместе с FPS/Regard и памятью frontend-проекта отдельно. Нельзя обещать работу при таком лимите по этим замерам.

### Воспроизведение browser E2E

Только локально, не включать support server в deployment. Из backend:

```sh
python tests/support/steam_e2e_server.py
```

Он создаёт отдельную .artifacts/steam-e2e/steam-amvera-e2e.db и не открывает рабочую SQLite. Из frontend: `VITE_API_BASE_URL=http://127.0.0.1:8005 npm run dev -- --host 127.0.0.1 --port 5174 --strictPort` (в PowerShell задать переменную через `$env:VITE_API_BASE_URL=...`). Затем из корня:

```sh
python tools/steam_browser_e2e.py
python tools/steam_browser_errors_e2e.py
```

Требуется локальный Playwright с Chromium либо STEAM_E2E_BROWSER с путём к браузеру; production-парсер его не использует. Результаты и скриншоты сохраняются в .artifacts/steam-e2e. Тестовые управляющие endpoints присутствуют только в support server, не в приложении app.main.

### Linux/container smoke: подготовлен, НЕ выполнен

В среде разработки отсутствует Docker; WSL сообщает, что Linux subsystem не установлен. Поэтому сигналы Linux, flock на Linux и блокировки настоящего persistent volume пока не подтверждены. После сборки backend-образа можно выполнить:

```sh
docker run --rm --entrypoint python <backend-image> -m scripts.steam_linux_smoke
```

Для проверки именно примонтированного хранилища нужен этот же smoke внутри окружения с /data, без запуска production API. Скрипт создаёт только собственную временную БД, проверяет DELETE, duplicate worker, SIGTERM/SIGINT, конкурирующую запись и rollback после аварии, integrity_check; не включает сеть и не открывает production pc_upgrade.db. Успешный запуск контейнера без mounted /data проверит только локальный слой контейнера, а не хранилище Amvera. Это остаётся обязательной проверкой на хостинге перед заявлением полной готовности.

Документация источника: [Amvera storage](https://docs.amvera.ru/applications/storage.html), [SQLite](https://docs.amvera.ru/databases/sqlite.html), [Docker](https://docs.amvera.ru/applications/configuration/docker.html). Документация подтверждает /data, но не является подтверждением WAL/flock для конкретного проекта. Текущий существующий Docker image включает browser dependencies для прежних функций Regard; Steam не запускает браузер и не добавляет новые browser dependencies.

Машинный отчёт: steam_amvera_validation.json. Production-БД, commit/push/deployment не выполнялись.


### Итог проверок lifecycle

- Полная backend-регрессия: 821 тест, 819 успешно, 2 пропущены, 210.351 s; профильные Steam/lifecycle 49 успешно.
- Frontend: 129 успешно, production build успешно; compileall и git diff --check успешно.
- Повторно выполнены сохранённые tools/steam_browser_e2e.py и tools/steam_browser_errors_e2e.py. Дополнительно проверено отображение обновлённых 52 FPS в DOM, не только JSON ответа.
- После завершения всего тестового дерева API+worker новый процесс API открыл ту же тестовую SQLite: кеш available, integrity_check=ok.
- Временные серверы 5174/8005/8006 остановлены. Production и пользовательские серверы не изменялись.
- Linux smoke и фактическая пересборка/рестарт Amvera не выполнены; поэтому полной проверкой именно на хостинге этот отчёт не является.

Файлы этой итерации: backend/app/core/config.py, backend/app/db/base.py, backend/app/main.py, backend/app/workers/steam_requirements_worker.py, backend/app/services/steam_lifecycle.py, backend/scripts/startup.py, backend/scripts/steam_linux_smoke.py, backend/tests/test_steam_lifecycle.py, backend/tests/test_steam_queue.py, backend/tests/support/steam_e2e_server.py, backend/.env.amvera.example; tools/steam_browser_e2e.py и tools/steam_browser_errors_e2e.py; документация STEAM_REQUIREMENTS/ARCHITECTURE/TECHNICAL_AUDIT/CHANGELOG_DEV/TODO/AMVERA_PRODUCTION_RELEASE, steam_amvera_validation.json. Dockerfile и amvera.yml проверены, формат deployment не менялся. Дизайн и FPS-формулы в этой итерации не изменялись.

Предлагаемое сообщение коммита: `fix: harden Steam worker lifecycle and verify browser enrichment flow`. Коммит не создан.
