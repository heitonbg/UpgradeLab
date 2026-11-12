# Полная интеграция продукта: каталог, TTL и настоящие E2E

Дата: 2026-11-11. Проверка локальная, обычный frontend без admin preview, реальная staging SQLite. Commit, push и deployment не выполнялись.

## Причины и исправления

1. Общая SQL-граница 24 часа отбрасывала catalog_import до предварительного подбора. Для Regard введён CATALOG_PRELIMINARY_HOURS=72 (диапазон настройки 24–168). До 24 часов включительно — fresh, далее до 72 часов включительно — stale и только предварительный расчёт; старше окна — historical. Отсчёт ведётся от исходной даты прайса, не от импорта. Неправильные/отсутствующие даты и будущее свыше прежнего допуска 5 минут исключаются. Live-подтверждения и TTL 15 минут не продлены.
2. Frontend посылал category= для «Все категории», что давало 422 и пустые карточки. Пустой enum теперь не отправляется; исправление закреплено frontend-тестом.
3. Локальная ветка автоматически понижала доверенный feed/проверенные страницы до draft. Быстрая draft-ветка теперь применяется при отсутствии подтверждённых предложений; наличие реального подтверждения обрабатывает прежний solver. Импорт с неизвестным наличием остаётся draft.
4. Path.resolve и валидация одних и тех же прав повторялись для каждой строки каталога. Теперь разрешения и привязка private-analysis к SQLite вычисляются один раз на выборку, без кеша между запросами. Границы прав/базы сохранены.
5. Скрытые панели React дублировали параллельный /api/hardware. Они разделяют только незавершённый запрос; готовые цены не кешируются.
6. Staging Origin не совпадал с портом нового Vite: публикация давала 403. Для проверок выставлены FRONTEND_URL=http://127.0.0.1:5177 и CORS_ORIGINS с тем же адресом. Проверка Origin не отключена. Vite фактически читает API_PROXY_TARGET; VITE_API_TARGET не используется.

## Контракт данных

- source_price_at: исходная UTC-дата прайса (наследуемое source_updated_at/observed_at сохранено).
- imported_at: фактическая серверная дата импорта, отдельно в provenance. Повтор того же файла идемпотентен и не обновляет цену.
- price_freshness: fresh / stale / historical. fresh здесь означает возраст наблюдения, а не live-подтверждение.
- stock_status / availability: известное отсутствие исключается; unknown допускает предварительный расчёт.
- optimizer_eligibility: временной и предметный допуск; API каталога также проверяет сопоставление модели, материализацию, права и снятие из прайса.
- preliminary_candidate: товар разрешён к выбору в предварительный расчёт. Поля технической совместимости и цены не смешиваются.
- purchase_ready: неизвестные наличие, цена, доставка или технические параметры не превращаются в готовую покупку. Реальный импорт не создаёт price_verification.

available_offers, ручной offer_id, автоматический подбор и upgrade используют единое предварительное окно каталога. fresh() остаётся строгой 24-часовой проверкой для подтверждений. В сохранении историческая сумма неизменяема; review сообщает последние наблюдения/их возраст, current_total требует прежних настоящих доказательств. /offers/status различает fresh_offers и preliminary_offers.

## Настоящий файл и база

Существующий fetch_official выполнил один GET официального endpoint, HTTP 200, без cookies/CAPTCHA/прокси-обхода. Получен regard_price_111126_17.xlsx, 4 785 300 байт, SHA256 6ed8b103103abac133212dddc6f4e32f02a9506a39086b9a13b06f3f7022ee5c. Исходная дата: 2026-11-11T14:30:00Z; timezone +03:00 — явная конфигурация, XLSX сам часовой пояс не сообщает.

Пути относительно корня проекта:

- Резервная копия прежней staging: .artifacts/product-readiness-20261111/before-latest-sync.db (SQLite online backup).
- Текущая проверочная БД: .artifacts/product-readiness-20261111/pc_upgrade_e2e.db.
- Предыдущий настоящий прайс/БД сохранены; рабочую БД для тестирования не использовали.
- 5 968 активных товаров через обычный API; 6 157 CatalogProduct с историческими/снятыми; 3 006 материализованных допущенных предложений последнего прайса; 11 959 дневных наблюдений; 2 237 записей Hardware.
- CatalogAccess: public_display=true, public_enabled=true, fixture=false; commercial=false, automatic_download=false. Эти отдельные ограничения не обходились.
- Настоящих фото в XLSX нет; CategoryImage — явная иллюстрация категории. Наличие unknown. Product URL выведен только из numeric external_product_id.

Sync выполнен synchronize(..., audience='public-noncommercial') на отдельной копии с блокировкой и транзакцией. Новые, изменившиеся и пропавшие товары обрабатываются существующим механизмом; старые снимки сохранений не переписываются.

## Реальные расчёты

Игра Red Dead Redemption 2, 1080p high, RAM не менее 16 GB, offers, без подключения иных площадок, разрешена смена платформы. В смешанном режиме выиграли те же предложения Регарда; выгодное полное сочетание только из существующей биржи не нашлось. Недостающие детали справочником не заменяли.

| Бюджет | Источники | Итог ₽ | Деталей | Статус | Время, с |
|---:|---|---:|---:|---|---:|
| 50000 | regard | 47620 | 8/8 | draft | 7.81 |
| 80000 | regard | 76700 | 8/8 | draft | 5.56 |
| 120000 | regard | 89700 | 8/8 | draft | 5.55 |
| 150000 | regard | 93970 | 8/8 | draft | 6.58 |
| 50000 | upgradelab | неизвестен | 0/8 | partial | 8.88 |
| 80000 | upgradelab | неизвестен | 0/8 | partial | 8.5 |
| 120000 | upgradelab | неизвестен | 1/8 | partial | 8.48 |
| 150000 | upgradelab | неизвестен | 1/8 | partial | 10.78 |
| 50000 | regard, upgradelab | 47620 | 8/8 | draft | 7.94 |
| 80000 | regard, upgradelab | 76700 | 8/8 | draft | 5.08 |
| 120000 | regard, upgradelab | 89700 | 8/8 | draft | 5.45 |
| 150000 | regard, upgradelab | 93970 | 8/8 | draft | 6.58 |

Получено 8 полных предварительных сборок из 12 расчётов (по четыре для Regard и смешанного режима). Для одной биржи 0–1 деталь, partial; это фактическое покрытие локальной базы, не подтверждение рыночной доступности.

Отдельный настоящий прайс от 2026-11-10T14:30:00Z проверен на реальных текущих часах после 24 часов: 8 деталей, 76 770 ₽, draft, все price_freshness=stale, purchase_ready=false. Raw результат: .artifacts/product-readiness-20261111/actual-stale-build.json. Дату прайса не меняли.

### Выбранные товары по каждому результату

#### 50000 ₽ · regard

| Категория | Товар | Цена ₽ | Источник | Исходная дата |
|---|---|---:|---|---|
| CPU | AMD Ryzen 3 3200G | 4940 | Регард | 2026-11-11T14:30:00Z |
| GPU | GeForce GT 1030 | 5870 | Регард | 2026-11-11T14:30:00Z |
| motherboard | Материнская плата CBR B450M-F | 5260 | Регард | 2026-11-11T14:30:00Z |
| memory | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) | 9730 | Регард | 2026-11-11T14:30:00Z |
| storage | Накопитель SSD 480GB Kingston A400 (SA400S37/480G) | 9720 | Регард | 2026-11-11T14:30:00Z |
| case | Корпус Zalman I3 Neo ARGB V2 Black | 5750 | Регард | 2026-11-11T14:30:00Z |
| psu | Блок питания 650W MSI MAG A650BN | 5140 | Регард | 2026-11-11T14:30:00Z |
| cooler | Кулер DeepCool AG300 | 1210 | Регард | 2026-11-11T14:30:00Z |

Технический статус: unknown. Неизвестные размеры/разъёмы, BIOS, доставка и наличие требуют проверки; совместимость CPU/socket/RAM проверяется сервером.
#### 80000 ₽ · regard

| Категория | Товар | Цена ₽ | Источник | Исходная дата |
|---|---|---:|---|---|
| CPU | AMD Ryzen 5 4500 | 7870 | Регард | 2026-11-11T14:30:00Z |
| GPU | GeForce RTX 2060 SUPER | 30990 | Регард | 2026-11-11T14:30:00Z |
| motherboard | Материнская плата MSI A520M-A PRO | 5570 | Регард | 2026-11-11T14:30:00Z |
| memory | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) | 9730 | Регард | 2026-11-11T14:30:00Z |
| storage | Накопитель SSD 500GB Netac NV3000 (NT01NV3000-500-E4X) | 10050 | Регард | 2026-11-11T14:30:00Z |
| case | Корпус Zalman I3 Neo ARGB V2 Black | 5750 | Регард | 2026-11-11T14:30:00Z |
| psu | Блок питания 650W MSI MAG A650BN | 5140 | Регард | 2026-11-11T14:30:00Z |
| cooler | Кулер ID-COOLING SE-214-XT BASIC | 1600 | Регард | 2026-11-11T14:30:00Z |

Технический статус: unknown. Неизвестные размеры/разъёмы, BIOS, доставка и наличие требуют проверки; совместимость CPU/socket/RAM проверяется сервером.
#### 120000 ₽ · regard

| Категория | Товар | Цена ₽ | Источник | Исходная дата |
|---|---|---:|---|---|
| CPU | AMD Ryzen 5 4500 | 7870 | Регард | 2026-11-11T14:30:00Z |
| GPU | GeForce RTX 3060 Ti | 43990 | Регард | 2026-11-11T14:30:00Z |
| motherboard | Материнская плата MSI A520M-A PRO | 5570 | Регард | 2026-11-11T14:30:00Z |
| memory | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) | 9730 | Регард | 2026-11-11T14:30:00Z |
| storage | Накопитель SSD 500GB Netac NV3000 (NT01NV3000-500-E4X) | 10050 | Регард | 2026-11-11T14:30:00Z |
| case | Корпус Zalman I3 Neo ARGB V2 Black | 5750 | Регард | 2026-11-11T14:30:00Z |
| psu | Блок питания 650W MSI MAG A650BN | 5140 | Регард | 2026-11-11T14:30:00Z |
| cooler | Кулер ID-COOLING SE-214-XT BASIC | 1600 | Регард | 2026-11-11T14:30:00Z |

Технический статус: unknown. Неизвестные размеры/разъёмы, BIOS, доставка и наличие требуют проверки; совместимость CPU/socket/RAM проверяется сервером.
#### 150000 ₽ · regard

| Категория | Товар | Цена ₽ | Источник | Исходная дата |
|---|---|---:|---|---|
| CPU | AMD Ryzen 5 4500 | 7870 | Регард | 2026-11-11T14:30:00Z |
| GPU | GeForce RTX 3070 | 48260 | Регард | 2026-11-11T14:30:00Z |
| motherboard | Материнская плата MSI A520M-A PRO | 5570 | Регард | 2026-11-11T14:30:00Z |
| memory | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) | 9730 | Регард | 2026-11-11T14:30:00Z |
| storage | Накопитель SSD 500GB Netac NV3000 (NT01NV3000-500-E4X) | 10050 | Регард | 2026-11-11T14:30:00Z |
| case | Корпус Zalman I3 Neo ARGB V2 Black | 5750 | Регард | 2026-11-11T14:30:00Z |
| psu | Блок питания 650W MSI MAG A650BN | 5140 | Регард | 2026-11-11T14:30:00Z |
| cooler | Кулер ID-COOLING SE-214-XT BASIC | 1600 | Регард | 2026-11-11T14:30:00Z |

Технический статус: unknown. Неизвестные размеры/разъёмы, BIOS, доставка и наличие требуют проверки; совместимость CPU/socket/RAM проверяется сервером.
#### 50000 ₽ · upgradelab

| Категория | Товар | Цена ₽ | Источник | Исходная дата |
|---|---|---:|---|---|

Технический статус: unknown. Неизвестные размеры/разъёмы, BIOS, доставка и наличие требуют проверки; совместимость CPU/socket/RAM проверяется сервером.

Нет категорий: CPU, GPU, motherboard, memory, storage, psu, case, cooler.

- CPU: no_offers.
- GPU: candidates_rejected.
- motherboard: no_offers.
- memory: no_offers.
- storage: no_offers.
- psu: no_offers.
- case: no_offers.
- cooler: no_offers.
#### 80000 ₽ · upgradelab

| Категория | Товар | Цена ₽ | Источник | Исходная дата |
|---|---|---:|---|---|

Технический статус: unknown. Неизвестные размеры/разъёмы, BIOS, доставка и наличие требуют проверки; совместимость CPU/socket/RAM проверяется сервером.

Нет категорий: CPU, GPU, motherboard, memory, storage, psu, case, cooler.

- CPU: no_offers.
- GPU: candidates_rejected.
- motherboard: no_offers.
- memory: no_offers.
- storage: no_offers.
- psu: no_offers.
- case: no_offers.
- cooler: no_offers.
#### 120000 ₽ · upgradelab

| Категория | Товар | Цена ₽ | Источник | Исходная дата |
|---|---|---:|---|---|
| GPU | GeForce RTX 5060 8GB | 50000 | Биржа UpgradeLab | 2026-11-10T18:19:33.219960Z |

Технический статус: unknown. Неизвестные размеры/разъёмы, BIOS, доставка и наличие требуют проверки; совместимость CPU/socket/RAM проверяется сервером.

Нет категорий: CPU, motherboard, memory, storage, psu, case, cooler.

- CPU: no_offers.
- motherboard: no_offers.
- memory: no_offers.
- storage: no_offers.
- psu: no_offers.
- case: no_offers.
- cooler: no_offers.
#### 150000 ₽ · upgradelab

| Категория | Товар | Цена ₽ | Источник | Исходная дата |
|---|---|---:|---|---|
| GPU | GeForce RTX 5060 8GB | 50000 | Биржа UpgradeLab | 2026-11-10T18:19:33.219960Z |

Технический статус: unknown. Неизвестные размеры/разъёмы, BIOS, доставка и наличие требуют проверки; совместимость CPU/socket/RAM проверяется сервером.

Нет категорий: CPU, motherboard, memory, storage, psu, case, cooler.

- CPU: no_offers.
- motherboard: no_offers.
- memory: no_offers.
- storage: no_offers.
- psu: no_offers.
- case: no_offers.
- cooler: no_offers.
#### 50000 ₽ · regard, upgradelab

| Категория | Товар | Цена ₽ | Источник | Исходная дата |
|---|---|---:|---|---|
| CPU | AMD Ryzen 3 3200G | 4940 | Регард | 2026-11-11T14:30:00Z |
| GPU | GeForce GT 1030 | 5870 | Регард | 2026-11-11T14:30:00Z |
| motherboard | Материнская плата CBR B450M-F | 5260 | Регард | 2026-11-11T14:30:00Z |
| memory | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) | 9730 | Регард | 2026-11-11T14:30:00Z |
| storage | Накопитель SSD 480GB Kingston A400 (SA400S37/480G) | 9720 | Регард | 2026-11-11T14:30:00Z |
| case | Корпус Zalman I3 Neo ARGB V2 Black | 5750 | Регард | 2026-11-11T14:30:00Z |
| psu | Блок питания 650W MSI MAG A650BN | 5140 | Регард | 2026-11-11T14:30:00Z |
| cooler | Кулер DeepCool AG300 | 1210 | Регард | 2026-11-11T14:30:00Z |

Технический статус: unknown. Неизвестные размеры/разъёмы, BIOS, доставка и наличие требуют проверки; совместимость CPU/socket/RAM проверяется сервером.
#### 80000 ₽ · regard, upgradelab

| Категория | Товар | Цена ₽ | Источник | Исходная дата |
|---|---|---:|---|---|
| CPU | AMD Ryzen 5 4500 | 7870 | Регард | 2026-11-11T14:30:00Z |
| GPU | GeForce RTX 2060 SUPER | 30990 | Регард | 2026-11-11T14:30:00Z |
| motherboard | Материнская плата MSI A520M-A PRO | 5570 | Регард | 2026-11-11T14:30:00Z |
| memory | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) | 9730 | Регард | 2026-11-11T14:30:00Z |
| storage | Накопитель SSD 500GB Netac NV3000 (NT01NV3000-500-E4X) | 10050 | Регард | 2026-11-11T14:30:00Z |
| case | Корпус Zalman I3 Neo ARGB V2 Black | 5750 | Регард | 2026-11-11T14:30:00Z |
| psu | Блок питания 650W MSI MAG A650BN | 5140 | Регард | 2026-11-11T14:30:00Z |
| cooler | Кулер ID-COOLING SE-214-XT BASIC | 1600 | Регард | 2026-11-11T14:30:00Z |

Технический статус: unknown. Неизвестные размеры/разъёмы, BIOS, доставка и наличие требуют проверки; совместимость CPU/socket/RAM проверяется сервером.
#### 120000 ₽ · regard, upgradelab

| Категория | Товар | Цена ₽ | Источник | Исходная дата |
|---|---|---:|---|---|
| CPU | AMD Ryzen 5 4500 | 7870 | Регард | 2026-11-11T14:30:00Z |
| GPU | GeForce RTX 3060 Ti | 43990 | Регард | 2026-11-11T14:30:00Z |
| motherboard | Материнская плата MSI A520M-A PRO | 5570 | Регард | 2026-11-11T14:30:00Z |
| memory | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) | 9730 | Регард | 2026-11-11T14:30:00Z |
| storage | Накопитель SSD 500GB Netac NV3000 (NT01NV3000-500-E4X) | 10050 | Регард | 2026-11-11T14:30:00Z |
| case | Корпус Zalman I3 Neo ARGB V2 Black | 5750 | Регард | 2026-11-11T14:30:00Z |
| psu | Блок питания 650W MSI MAG A650BN | 5140 | Регард | 2026-11-11T14:30:00Z |
| cooler | Кулер ID-COOLING SE-214-XT BASIC | 1600 | Регард | 2026-11-11T14:30:00Z |

Технический статус: unknown. Неизвестные размеры/разъёмы, BIOS, доставка и наличие требуют проверки; совместимость CPU/socket/RAM проверяется сервером.
#### 150000 ₽ · regard, upgradelab

| Категория | Товар | Цена ₽ | Источник | Исходная дата |
|---|---|---:|---|---|
| CPU | AMD Ryzen 5 4500 | 7870 | Регард | 2026-11-11T14:30:00Z |
| GPU | GeForce RTX 3070 | 48260 | Регард | 2026-11-11T14:30:00Z |
| motherboard | Материнская плата MSI A520M-A PRO | 5570 | Регард | 2026-11-11T14:30:00Z |
| memory | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) | 9730 | Регард | 2026-11-11T14:30:00Z |
| storage | Накопитель SSD 500GB Netac NV3000 (NT01NV3000-500-E4X) | 10050 | Регард | 2026-11-11T14:30:00Z |
| case | Корпус Zalman I3 Neo ARGB V2 Black | 5750 | Регард | 2026-11-11T14:30:00Z |
| psu | Блок питания 650W MSI MAG A650BN | 5140 | Регард | 2026-11-11T14:30:00Z |
| cooler | Кулер ID-COOLING SE-214-XT BASIC | 1600 | Регард | 2026-11-11T14:30:00Z |

Технический статус: unknown. Неизвестные размеры/разъёмы, BIOS, доставка и наличие требуют проверки; совместимость CPU/socket/RAM проверяется сервером.

## Семь исходных падений

| Тест | Ожидание / факт и причина | Решение |
|---|---|---|
| FreeBatchSearchTests.test_one_store_failure_does_not_discard_other_store_quotes | Ждал один оффер, получал 0: mocked transport был отключён внешней настройкой offers_live_search | Тестовый grant_network явно включает только mocked live transport с cleanup; production-настройки не меняет |
| LiveBuildDiagnosticTests.test_9920_ssd_fits_whole_budget | Ждал prices_confirmed=true для настоящего feed, получал false | Убрано безусловное понижение доверенного локального feed в draft shortcut |
| LiveBuildDiagnosticTests.test_flexible_ssd_is_not_cut_before_total_budget_check | Та же регрессия локального shortcut | То же исправление, полная бюджетная проверка сохранена |
| TransportDiagnosticTests.test_typed_failure_reaches_public_source_diagnostics | Ждал certificate_error mocked запроса, получал disabled | Фикстура явно включает live transport; TLS-правила сохранены |
| PublicCatalogApiTests.test_public_endpoint_paginates_and_keeps_unknown_availability_explicit | Ждал допуска при фиксированной дате, но время шло и дата устаревала | Фиксированные UTC-часы и отдельная действительно старая запись |
| ClosedRegardImportTests.test_private_search_needs_database_bound_context | Ждал внутреннюю ссылку, но XLSX теперь имеет проверяемый исходный ID | Обновлён контракт URL на /product/123; проверки изоляции/прав и отсутствия verification сохранены |
| UnifiedGeoTests.test_known_local_prices_complete_but_unknown_connectors_draft | Ждал complete для настоящей mocked проверки и известных размеров, получал принудительный draft | Shortcut больше не перехватывает подтверждённые цены; неизвестные разъёмы по-прежнему дают draft |

Дополнительно проверены 24/72-часовые границы, missing/invalid/future даты, отдельный live TTL, видимость каталога после 48 часов и исключение после 72 часов, одно разрешение private-analysis на выборку и пустой category query. Тесты не удалялись и не помечались skip ради результата.

## Воспроизведение

Из backend: `DATABASE_URL` задаётся в окружении на отдельную SQLite до импорта app. Реальный backend/.env не редактируется и не выводится. Для локальной пары 8006/5177:

```powershell
# backend, отдельный терминал
$env:DATABASE_URL='sqlite:///C:/vscode/upgradeLab/.artifacts/product-readiness-20261111/pc_upgrade_e2e.db'
$env:FRONTEND_URL='http://127.0.0.1:5177'
$env:CORS_ORIGINS='http://127.0.0.1:5177'
$env:OFFERS_LIVE_SEARCH='false'
$env:REGARD_DOWNLOAD_ENABLED='false'
$env:OPENROUTER_SEARCH_ENABLED='false'
$env:OPENROUTER_ALLOW_PAID_WEB='false'
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8006
# frontend, другой терминал
$env:API_PROXY_TARGET='http://127.0.0.1:8006'
npm.cmd run dev -- --host 127.0.0.1 --port 5177 --strictPort
```

Обычный сайт http://127.0.0.1:5177, API http://127.0.0.1:8006/api/health, Swagger http://127.0.0.1:8006/docs. Из корня `backend/.venv/Scripts/python.exe tools/full_product_matrix.py` и `backend/.venv/Scripts/python.exe tools/full_product_e2e.py`. Они обращаются только к выделенным локальным портам; E2E использует установленный Edge. Никакие frontend API responses не подменяются. Тестовая регистрация/объявление выполняются штатным API в изолированной БД; объявление и сохранение удаляются после проверки. Артефакты локальные, игнорируются Git.

## Ссылки Регарда

Проверено три исходных ID разных категорий, без массового обхода. CPU 343790 и GPU 792596 ответили HTTP 200. Для motherboard 368290 безопасный транспорт вернул NetworkPolicyError. HTTP 200 не доказывает соответствие модели; API явно возвращает product_url_status=derived_source_id_not_checked, не «verified». Подробности в .artifacts/product-readiness-20261111/product-links.json. ID 733527 ранее подтверждён владельцем. SQLite ID и выдуманные slug не используются.

## Amvera

Корневые Dockerfile/amvera.yml собирают React и обслуживают его тем же FastAPI origin. SQLite: DATABASE_URL=sqlite:////data/pc_upgrade.db, один backend worker, persistenceMount=/data; данные и operator schema/rights/backup лежат в Data, не /app. Официальная документация проверена: [постоянное хранилище](https://docs.amvera.ru/applications/storage.html), [SQLite](https://docs.amvera.ru/databases/sqlite.html), [YAML](https://docs.amvera.ru/applications/configuration/config-file.html).

Перед запуском существующей базы остановить писателей, сделать sqlite3.Connection.backup в новый файл и проверить PRAGMA integrity_check; существующая scripts/migrate_catalog_intelligence.py подготавливает аддитивные таблицы с резервной копией, migrate_listings выполняет аддитивные колонки. Схему старой рабочей базы надо проверить на staging до запуска: приложение вызывает create_all/migrate_listings при старте. Прайс загружается оператором в Data и импортируется существующим `python -m scripts.regard_sync --database /data/pc_upgrade.db --schema /data/regard-schema.json --rights /data/regard-rights.json --file /data/price.xlsx --audience public-noncommercial`. Первый импорт выполняется контролируемо, без scheduler. Права не хранятся в публичном запросе.

BACKUP/restore: остановить писателей; сделать online backup; открыть отдельную восстановленную копию, проверить integrity/counts; заменить целевой файл только при остановленном приложении, не смешивая WAL/SHM от другой версии. После рестарта проверять те же количества/историю/сохранения. Staging-копия содержит пользовательские данные: её нельзя включать в Docker/image или автоматически отправлять на Amvera. Начальный production-каталог импортировать в целевую собственную БД, не загружать эту E2E-копию.

FRONTEND_URL и CORS_ORIGINS должны совпасть с фактическим HTTPS origin. При едином контейнере /api относительный, Vite proxy в production не нужен. HTTPS и доверенный proxy/IP требуется проверить в конкретном аккаунте Amvera; произвольным forwarded-заголовкам не доверять. Недоступный XLSX не удаляет прошлый успешный каталог: within-window stale доступен как draft, после окна цены остаются только историей. Двухдневная демонстрация может использовать 72-часовое окно без scheduler.

Локальная Docker-сборка недоступна: Docker CLI не установлен. Реальный volume, HTTPS, ограничения тарифа, сетевой доступ и рестарт Amvera не проверены; deployment не выполнялся. До публичного запуска нужны именно эти проверки. Оплачиваемый AI-поиск выключен.


## Технические проверки в матрице

Полное совпадение socket/DDR проверено сервером, поддержка конкретной версии BIOS не заявляется. В API отдельно представлены накопитель, мощность/разъёмы БП и физические размеры:

| Бюджет / источники | Платформа | Накопитель | БП | Неизвестные физические параметры |
|---|---|---|---|---|
| 50000 / regard | {'socket': 'AM4', 'ram_type': 'DDR4', 'ram_capacity_gb': 16} | unknown: storage_slot_evidence_missing | unknown: psu_connectors_unknown | case_board_format, case_psu_format, case_gpu_length, case_cooler_height |
| 80000 / regard | {'socket': 'AM4', 'ram_type': 'DDR4', 'ram_capacity_gb': 16} | compatible: existing_reviewed_nvme_evidence | unknown: psu_connectors_unknown | case_board_format, case_psu_format, case_gpu_length, case_cooler_height |
| 120000 / regard | {'socket': 'AM4', 'ram_type': 'DDR4', 'ram_capacity_gb': 16} | compatible: existing_reviewed_nvme_evidence | unknown: psu_connectors_unknown | case_board_format, case_psu_format, case_gpu_length, case_cooler_height |
| 150000 / regard | {'socket': 'AM4', 'ram_type': 'DDR4', 'ram_capacity_gb': 16} | compatible: existing_reviewed_nvme_evidence | unknown: psu_connectors_unknown | case_board_format, case_psu_format, case_gpu_length, case_cooler_height |
| 50000 / upgradelab | {} | unknown: не найден | unknown: не найден | physical_dimensions_missing |
| 80000 / upgradelab | {} | unknown: не найден | unknown: не найден | physical_dimensions_missing |
| 120000 / upgradelab | {} | unknown: не найден | unknown: не найден | physical_dimensions_missing |
| 150000 / upgradelab | {} | unknown: не найден | unknown: не найден | physical_dimensions_missing |
| 50000 / regard,upgradelab | {'socket': 'AM4', 'ram_type': 'DDR4', 'ram_capacity_gb': 16} | unknown: storage_slot_evidence_missing | unknown: psu_connectors_unknown | case_board_format, case_psu_format, case_gpu_length, case_cooler_height |
| 80000 / regard,upgradelab | {'socket': 'AM4', 'ram_type': 'DDR4', 'ram_capacity_gb': 16} | compatible: existing_reviewed_nvme_evidence | unknown: psu_connectors_unknown | case_board_format, case_psu_format, case_gpu_length, case_cooler_height |
| 120000 / regard,upgradelab | {'socket': 'AM4', 'ram_type': 'DDR4', 'ram_capacity_gb': 16} | compatible: existing_reviewed_nvme_evidence | unknown: psu_connectors_unknown | case_board_format, case_psu_format, case_gpu_length, case_cooler_height |
| 150000 / regard,upgradelab | {'socket': 'AM4', 'ram_type': 'DDR4', 'ram_capacity_gb': 16} | compatible: existing_reviewed_nvme_evidence | unknown: psu_connectors_unknown | case_board_format, case_psu_format, case_gpu_length, case_cooler_height |

## Файлы текущего исправления

- backend/app/core/config.py, backend/.env.example, backend/.env.amvera.example — конфигурация отдельного окна.
- backend/app/services/catalog_freshness.py — единая политика возраста прайса.
- backend/app/services/offers.py, prices.py, upgrade_prices.py, saved_prices.py — поиск, аппаратные оценки, upgrade и сохранённые наблюдения.
- backend/app/services/builds.py, assembly_draft.py, assembly_search.py — ручной/автоматический допуск, evidence и сохранение смысла draft/complete.
- backend/app/services/catalog_access.py, catalog_import.py — разрешения без повторного разбора на каждой строке, точный счётчик предварительных кандидатов.
- backend/app/api/catalog_public.py, offers.py; backend/app/schemas/hardware.py — даты, freshness, stock, отдельные счётчики, статус ссылки.
- backend/tests/test_catalog_freshness.py, test_catalog_import.py, test_public_catalog_api.py, test_regard_feed.py, test_assembly_fallback.py, source_grants.py — регрессии и корректные mocked network настройки.
- frontend/src/api/hardware.js — дедупликация незавершённого запроса.
- frontend/src/components/RegardCatalog.jsx, calculator/AssemblySearchSummary.jsx — пустой фильтр, предупреждение о stale и исходная дата.
- frontend/src/lib/catalogView.js, catalogView.test.js — регрессия API query.
- tools/full_product_e2e.py, full_product_matrix.py — воспроизводимые настоящие сценарии.
- .dockerignore — исключение всех локальных БД/артефактов.
- docs/FULL_PRODUCT_READINESS.md, ARCHITECTURE.md, TECHNICAL_AUDIT.md, REGARD_DAILY_SYNC.md, DEPLOYMENT_CHECKLIST.md, CHANGELOG_DEV.md, REQUIREMENTS.md, TODO.md — контракт, ограничения, результаты.

В worktree также есть большой объём изменений прошлых итераций. Они не сбрасывались; git diff относительно HEAD включает их и не является списком исключительно этой задачи.

## Проверки и браузерные артефакты

Backend: 592 запущено, 590 успешно, 2 штатных пропуска, 0 падений. Все семь исходных падений устранены. Frontend: 100/100, production build успешен (107 modules). Полный настоящий Edge E2E: 10 сценариев; дополнительный прогон заполненной ручной формы успешен. В тесте выбора игры используется реальный каталог: отсутствие неизвестной игры не заменяется фиктивным FPS. Регистрация ранее проверена через штатный API; повторные E2E входят в собственный сохранённый тестовый аккаунт, не отключая лимит 429. Сохранение удаляется после проверки, прежние 13 результатов неизменны.

Online backup и пробное восстановление дали PRAGMA integrity_check=ok, одинаковые количества. После настоящего рестарта backend все 13 исходных SavedBuild.data совпали с первоначальной копией; каталог, дневная история и объявления сохранены. Production SPA, health, Swagger и Vite API proxy отвечают HTTP 200. Это локальная проверка устойчивости, не испытание Amvera volume.

Локальные доказательства (содержат данные staging и не включаются в Git):

- [каталог](../.artifacts/product-readiness-20261111/e2e/catalog-real.png), [мобильный каталог](../.artifacts/product-readiness-20261111/e2e/catalog-mobile-real.png).
- [настоящая сборка](../.artifacts/product-readiness-20261111/e2e/build-detail-real.png), [варианты](../.artifacts/product-readiness-20261111/e2e/build-real.png).
- [ручной конфигуратор](../.artifacts/product-readiness-20261111/e2e/manual-filled-real.png), [ручной результат](../.artifacts/product-readiness-20261111/e2e/manual-result-real.png).
- [апгрейд](../.artifacts/product-readiness-20261111/e2e/upgrade-real.png).
- [биржа](../.artifacts/product-readiness-20261111/e2e/after-listing-detail.png).
- [история](../.artifacts/product-readiness-20261111/e2e/history-real.png).
- [сохранённый результат после перезагрузки](../.artifacts/product-readiness-20261111/e2e/saved-reopened-real.png).

Viewport: 320, 375, 390, 768, 1024, 1440, 1920 px; проверены ширина документа, каталог/биржа/подбор и границы редактора/выпадающих списков. В первоначальном stress-прогоне полные страницы сменялись до завершения предыдущих запросов, возникало исчерпание SQLite connection pool. Ненужные дубли hardware исправлены, приёмка теперь явно ждёт реальный ответ каждой страницы. Это не нагрузочная сертификация для нескольких одновременных пользователей; массовые прерванные загрузки/лимиты тарифа требуют отдельного профилирования перед публичным запуском.

Предлагаемый commit: `fix(catalog): separate estimate freshness and complete real staging E2E`.


### Финальная фиксация после рестарта

Окончательный запуск tools/full_product_e2e.py: 10/10 успешно, 158.515 с, без API fixtures и без ошибок backend в журнале; заполненная ручная сборка включена в этот полный прогон. Backend 592 total / 590 pass / 2 skip; frontend 100 pass; production build и git diff --check — успешно. Запуски подтверждены локальными backend-final.log, frontend-final.log, frontend-build-final.log, e2e-final.log и persistence-check.json в .artifacts/product-readiness-20261111.

Оставлены работающими: backend PID 21028 (127.0.0.1:8006), Vite PID 15400 (127.0.0.1:5177). На backend также проверена production SPA с FRONTEND_DIST. Промежуточные процессы этой задачи на 8005/5176 остановлены. Остановка текущей пары в PowerShell: `Stop-Process -Id 21028,15400` (перед остановкой при более позднем запуске сверить актуальные PID через Get-NetTCPConnection). Коммит, push и deployment не выполнялись.
