# Локальный импорт товарных прайс-листов — итерация 9

## Статус и границы

Работают локальные CSV (UTF-8/UTF-8 BOM/явный Windows-1251) и XLSX без макросов. Новый HTTP endpoint не добавлен: импорт запускает оператор с доступом к файловой системе и SQLite. Зависимости не добавлены. Авторизация, FPS, правила совместимости и TTL не переписаны.

На момент итерации 9 реального прайса Регарда среди локальных файлов проекта не было. В итерации 12 получен настоящий XLSX: native reader, закрытый анализ, реальные результаты и ежедневный local-only workflow описаны в [REGARD_REAL_FEED.md](REGARD_REAL_FEED.md). Публичные права и автоматическая загрузка по-прежнему не включены. Файлы demo — **синтетические fixture**, включая названия колонок, цены и ссылки-заглушки с сегментом `fixture-not-a-real-offer`. Они не доказывают работу Регарда. Автоматического скачивания и обращений к магазинам нет. Avito запрещён для apply.

## Быстрая воспроизводимая демонстрация

PowerShell из `C:\vscode\upgradeLab\backend` (существующее окружение проекта):

```powershell
.\.venv\Scripts\python.exe -m scripts.catalog_demo --output ../.artifacts/catalog-demo
```

Каталог назначения должен быть новым: demo не перезаписывает существующую БД. Скрипт создаёт изолированную `demo.fixture.db`, пять тестовых Hardware, CSV/XLSX, две JSON-схемы, fixture-rights.json, preview-планы и demo-result.json. Рабочая БД не используется. Дата наблюдения задаётся генератором тестового файла явно.

Результат для каждого формата: 11 строк, 10 принятых, 1 отклонена (`price_missing`). Из принятых 3 строки однозначно сопоставлены с Hardware (две разные модели CPU/GPU), 6 распознаны существующими правилами остальных категорий (`structured`), 1 GPU неоднозначна без VRAM. Ещё одна сопоставленная CPU-строка не имеет URL. В StoreOffer попадает 8 строк; публично опубликовано 0. Поиск RTX 5060 возвращает 1 предложение, существующий подбор собирает 8 деталей за 54 500 ₽ в статусе `draft`. Повторный apply идемпотентен. Второй формат не создаёт повторных товаров.

Отдельные команды после demo (plan-файл не должен существовать):

```powershell
.\.venv\Scripts\python.exe -m scripts.import_catalog --database ../.artifacts/catalog-demo/demo.fixture.db preview --file ../.artifacts/catalog-demo/fixture.csv --schema ../.artifacts/catalog-demo/csv-fixture-schema.json --plan ../.artifacts/catalog-demo/manual-plan.json
.\.venv\Scripts\python.exe -m scripts.import_catalog --database ../.artifacts/catalog-demo/demo.fixture.db apply --file ../.artifacts/catalog-demo/fixture.csv --schema ../.artifacts/catalog-demo/csv-fixture-schema.json --plan ../.artifacts/catalog-demo/manual-plan.json --rights ../.artifacts/catalog-demo/fixture-rights.json --confirm-owner-rights --fixture --allow-rejected
.\.venv\Scripts\python.exe -m scripts.import_catalog --database ../.artifacts/catalog-demo/demo.fixture.db search --query 'RTX 5060' --category GPU --source regard --fixture
```

CLI search всегда локальный, без сетевого fallback. Без `--fixture` эти данные не видны. Fixture-контекст доступен только из Python/CLI; API не принимает параметр обхода. Имя БД для CLI fixture должно заканчиваться `.fixture.db`. Не используйте fixture-флаг на пользовательской БД.

## Контракт и конфигурация

`CatalogSchema` — JSON с запретом неизвестных полей. Смотрите исполняемый пример, который генерирует demo; он **не является схемой Регарда**. Обязательны `source` из существующих источников, `version`, `format`, `columns`, `categories`, `availability`. `columns` отображает логическое поле в фактический заголовок, а не наоборот. Обязательные логические поля: title и price. Для безопасной идентичности нужен external_product_id, sku, vendor_code или валидный фактический product_url.

Поддерживаются source_id, external_product_id, sku, vendor_code, brand, title, category, model, description, price, currency, availability, quantity, product_url, image_url, source_updated_at. imported_at записывается сервером при apply, а не берётся на веру из файла. Исходное title и normalized_title хранятся отдельно. Дополнительные проверяемые характеристики через `attributes`: socket, ram_type, capacity_gb, modules, watts, form_factor, interface, sockets, board_formats, psu_formats. Значения нескольких форматов/сокетов разделяются `|`.

Параметры: header_row (1–100), sheet (обязателен при нескольких листах), encoding, delimiter, decimal_separator, thousands_separator, currency, date_format, complete, fixture. `categories` отображает исходные категории в CPU/GPU/motherboard/memory/storage/psu/case/cooler. `availability` явно отображает строку в in_stock/out_of_stock/unknown. Ключи наличия задавайте в нижнем регистре. Без признака наличия товар остаётся в закрытом отчёте. quantity=0 означает out_of_stock.

Цена разбирается Decimal, не float: только положительная конечная обычная цена, максимум 100 млн ₽, до двух знаков после запятой, строгая группировка тысяч. Например `12 345,67` при decimal_separator="," и thousands_separator=" " даёт ровно 12345.67. Валюта должна быть явно задана в строке или схеме, поддержаны только RUB/RUR/₽. Рассрочка, доставка и условные скидки не интерпретируются; оператор обязан сопоставить именно обычную цену (`price_basis=ordinary`). Отсутствующая цена не заменяется нулём.

**Существующий StoreOffer/оптимизатор использует целые рубли.** Цена с копейками сохраняется точно в закрытом CatalogProduct/CatalogObservation, но не материализуется в StoreOffer: причина fractional_price_not_supported_by_optimizer. Округления нет. Поддержка копеек во всём финансовом тракте требует отдельной итерации.

CPU/GPU связываются только с существующими Hardware: сохраняются суффиксы Ti, VRAM, модель и производитель CPU; мобильные версии отбрасываются. Несколько кандидатов — ambiguous, неизвестная модель — unmatched. Остальные шесть категорий используют существующие правила распознавания характеристик/качества, затем обычные проверки совместимости оптимизатора; это `structured`, а не выдуманная связь с Hardware. Несопоставленные и неоднозначные строки не участвуют в подборе.

## Preview, apply, история и откат

prepare_import читает файл и снимок Hardware/импортированных данных без записи. Отчёт содержит read/accepted/rejected/publishable, категории, matching, new/updated/unchanged, min/max точной цены, причины ошибок и staged-строк. Изменение цены более чем на 50% выводится как предупреждение. accepted включает закрытые staged-строки; publishable — техническая пригодность, а не юридическое разрешение.

План содержит SHA-256 файла, схемы, Hardware и текущего состояния импорта, а также собственный digest. Apply повторно читает входы. Изменённый файл/схема/план/каталог требует нового preview; ошибка не вызывает частичной записи. `--allow-rejected` — явное согласие применить только принятые строки после просмотра отчёта. Без него apply при ошибочных строках отклоняется. Отмена после preview ничего не меняет.

Одна SQLite-транзакция `BEGIN IMMEDIATE` пишет CatalogAccess, CatalogProduct, CatalogObservation, StoreOffer и CatalogImport. Исключение в середине откатывает **все** изменения, сохраняя прежние предложения. Конкурентный идентичный импорт сериализуется; повтор возвращает receipt с idempotent=true. Конкурентное изменение другого состояния требует нового preview. Таймаут SQLite — 15 секунд в CLI; ошибки отображаются без локальных путей/traceback.

Ключ товара = SHA-256(source + тип стабильного идентификатора + идентификатор); при отсутствии ID используется hash фактического URL. Изменение вида идентификатора требует предварительной проверки: это новая идентичность. Дубли ID/URL внутри файла исключаются целиком; конфликт URL с чужой существующей записью отклоняет транзакцию. Один товар обновляет тот же StoreOffer, изменения нормализованных данных добавляют CatalogObservation; история сохранённых сборок не переписывается.

Ни частичная, ни complete-выгрузка не удаляет отсутствующие товары. complete сохраняется как информация, а не команда удаления. Явный out_of_stock скрывает товар из выдачи через состояние CatalogProduct, сохраняя StoreOffer и историю. Более старое наблюдение не перезаписывает более свежую цену StoreOffer. Для истории импорта отдельный срок очистки ещё не введён; объём нужно контролировать оператору.

## Время и достоверность

source_updated_at — время наблюдения из файла, received_at — необязательное явно заданное время получения файла, imported_at — реальное серверное время транзакции. ISO8601 Z/смещения нормализуются существующим price_time в UTC; legacy naive и Excel serial трактуются как UTC согласно существующей политике. Если источник использует локальную зону, нужна дата с offset; не считайте локальное время UTC без проверки. Excel даты поддерживают эпохи 1900/1904; фиктивный день 1900-02-29 запрещён. Будущие даты ограничены существующим OBSERVATION_SKEW (5 минут).

Нет даты — нет подстановки «сейчас»: строка остаётся staged. Нет URL — ссылка не строится из артикула. observed_at StoreOffer равен source_updated_at. Origin = catalog_import, **не feed/live**. Импорт не создаёт price_verification.checked_at, не обновляет OfferSearch.checked_at и не продлевает TTL. Подтверждение страницы сохраняется только для точно той же цены и даты наблюдения, если оно уже реально существовало. Новая цена не наследует старое подтверждение.

Поиск показывает «Цена по прайс-листу», дату и отсутствие подтверждения страницы. Сборка показывает такой же источник цены и остаётся draft без настоящей сверки. Сохранённые сборки используют существующий read-only review, исторический JSON не меняется. Устаревшие импортированные данные исключаются существующими TTL. Никаких фиктивных цен при недоступности магазина нет.

## Права и настоящие данные

Для нового реального файла создайте `.catalog-imports/regard/` в корне проекта (игнорируется Git) и поместите туда исходный CSV/XLSX, подтверждение прав и схему, составленную **по реальным заголовкам**. Файлы, отчёты и права не следует публиковать в репозитории. Не меняйте fixture-схему в «реальный формат» без проверки образца.

Перед рабочим apply сделайте резервную копию SQLite при остановленной записи приложения. CLI требует явный существующий путь --database, production default отсутствует. `init` создаёт только четыре импортные таблицы в существующей БД с Hardware:

```powershell
.\.venv\Scripts\python.exe -m scripts.import_catalog --database <явный-путь-к-копии-БД> init
```

Обычный startup также создаёт эти новые таблицы через существующий Base.metadata.create_all. Рабочая БД в этой итерации не открывалась для миграции. Для нового источника из существующего списка создаётся новая JSON-схема; новый магазин вне списка требует отдельной проверки домена и существующего source-контракта, не обхода allowlist.

CatalogRights требует source, development, public_display, commercial, automatic_download, basis (зафиксированное основание), owner_confirmed_by и confirmed_at. Все разрешения по умолчанию false. Чтение preview не публикует данные и не предоставляет лицензии. Для apply нужен development=true и явный CLI-флаг --confirm-owner-rights; для public-noncommercial дополнительно public_display=true; для public-commercial также commercial=true. Выбор коммерческого режима — ответственность владельца проекта. Технический gate хранит подтверждение, но не проверяет юридическую действительность документа.

По умолчанию audience=development: данные сохраняются только в закрытом staging, без StoreOffer. Fixture materializes StoreOffer только для изолированной демонстрации, скрытой вне fixture-контекста. Обычные API, ручной выбор offer_id и открытие сохранений учитывают gate. Для реальных данных в тестовой среде публичного приложения требуется разрешение public_display либо работа с закрытым staging; не обходите gate fixture-флагом.

Реальная публикация требует нового preview реального файла, подтверждения основания использования/показа/коммерции при необходимости, корректной схемы и явного --audience. Никаких настоящих публичных прав не включено. Development-apply существующего источника консервативно выключает его импортную публичную выдачу. Прочие магазины и их flags не изменены. Отозвать импортную публикацию можно операторским изменением CatalogAccess.public_enabled=0; отдельного публичного управления правами нет.

Для локального просмотра уже импортированных development-данных владельцем добавлен отдельный loopback-only admin API. Он требует секретный `REGARD_CATALOG_ADMIN_TOKEN`, файл `*.analysis.db` и действующее development право; UI показывает приватные строки с явной оговоркой, что цены/наличие не подтверждены. Этот просмотр не включает `public_display`, не публикует предложения и не открывает их обычному `/api/offers/search`. См. [диагностику и результаты](REGARD_PRIVATE_CATALOG.md).

automatic_download отдельно управляет допустимостью существующих онлайн-сверок импортированных предложений; сам импортёр ничего не скачивает даже при true. При false/fixture/private проверка страниц пропускается без записи checked_at. Для автоматического получения настоящего Регарда всё ещё необходимы разрешение владельца данных и отдельная проверка разрешённого канала; downloader в этой итерации не реализован. Avito apply жёстко запрещён.

## Защита файлов

Максимум 8 MiB на файл, 20 000 строк, 64 колонки, 4096 символов на значение, 8 листов. XLSX: максимум 512 ZIP-записей, 32 MiB распакованных данных, степень сжатия не более 150, XML-файл до 8 MiB; UTF-8 XML, запрет DTD/entities, внешних связей, embedded/ActiveX/VBA, макросов и любых формул даже с cached value. Необычные workbook MIME, .xls/.xlsm и повреждённые архивы отклоняются. В CLI нет HTTP-upload MIME, проверяются расширение и внутренняя структура. ZIP не извлекается на диск.

CSV не исполняется. HTML и формулоподобный текст отвергаются; выгрузки пользовательского CSV нет (отчёты JSON). URL валидируются существующей сетевой политикой/allowlist без загрузки страницы. SKU ограничены безопасным алфавитом; пути вывода задаёт оператор, файл их не контролирует. SQL передаётся через SQLAlchemy, данные не интерполируются в запросы. Чтение больших файлов/опасных архивов завершается до DB-транзакции. Это ограниченный табличный reader, не полный Excel: неподдерживаемые типы, формулы или экзотические расширения необходимо исправить в исходном прайсе.

## Проверки

Новые детерминированные тесты: `python -m unittest tests.test_catalog_import -q`. Все они запрещают socket.socket; реальных магазинов, SMTP и иных внешних запросов нет. Проверяются оба формата, деньги, модель/VRAM/RAM, некорректные данные/URL, ограничения ZIP/XML, права, приватные offer_id, изменение файла/схемы, транзакционный откат вставки и обновления, конкуренция, идемпотентность, поиск и полный demo.

Результаты финальной регрессии фиксируются в CHANGELOG_DEV.md и отчёте итерации. Реальный прайс Регарда, его лицензия, реальные ссылки/остатки и работа магазина остаются непроверенными.


## Изменённые файлы

- `.gitignore`
- `backend/app/db/models.py`
- `backend/app/schemas/catalog.py`
- `backend/app/schemas/offers.py`
- `backend/app/services/catalog_files.py`
- `backend/app/services/catalog_import.py`
- `backend/app/services/catalog_access.py`
- `backend/app/services/offers.py`
- `backend/app/services/assembly_draft.py`
- `backend/app/services/builds.py`
- `backend/app/services/price_verification.py`
- `backend/app/services/saved_prices.py`
- `backend/app/services/upgrade_prices.py`
- `backend/scripts/import_catalog.py`
- `backend/scripts/catalog_demo.py`
- `backend/scripts/catalog_fixture.py`
- `backend/tests/test_catalog_import.py`
- `frontend/src/components/StoreOffers.jsx`
- `frontend/src/components/calculator/AssemblySearchSummary.jsx`
- `docs/PRICE_FEED_IMPORT.md`
- `docs/ARCHITECTURE.md`
- `docs/TECHNICAL_AUDIT.md`
- `docs/TODO.md`
- `docs/CHANGELOG_DEV.md`


## Дополнение итерации 10

CatalogSchema поддерживает operator-owned geography (GeoEvidence) и technical с только storage_slots/power_connectors/system_connector_requirements. Профили требуют provenance и applies_to точного товара, требования GPU — модель и VRAM. Поля price_verification через technical запрещены. Эти записи не предоставляют разрешения на сеть и не создают live-подтверждение цены. См. UNIFIED_GEO_OFFERS.md.
