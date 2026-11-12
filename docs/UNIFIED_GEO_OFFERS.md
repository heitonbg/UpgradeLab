# Единый поиск предложений по городу — итерация 10

## Результат и границы

Реализован один путь `React → SearchOffers / BuildRequest / CalculateRequest → существующие search_jobs → StoreOffer → существующий подбор`. В общий набор входят локальная биржа, разрешённые импортированные каталоги и сохранённые магазинные наблюдения. Сетевые адаптеры запускаются только с отдельным разрешением. Нового оптимизатора, Hardware-каталога, сервиса или очереди нет; FPS/bottleneck не переписаны. Новых библиотек не добавлено.

Все новые проверки и демонстрации офлайн. Настоящие магазины в этой итерации не запрашивались. Работоспособность внешних источников, лицензии, цены/остатки и доставка **не подтверждены локальными тестами**. Незакоммиченная итерация 9 и аудит 80 000 сохранены; commit/push/deployment не выполнялись.

## Запрос и города

Общий GeoQuery используется SearchOffers, BuildRequest и CalculateRequest:

| Поле | Смысл / default |
|---|---|
| city_id | Стабильный UpgradeLab ID из существующего cities.json; default null |
| geo_mode | all / local / delivery; default all |
| max_price | Верхняя граница цены одной детали в целых RUB, без неизвестной доставки; default null |
| limit | 1–200 результатов поиска; default 100; не усекание всех восьми категорий оптимизатора |
| sources | В SearchOffers — выбранные источники; в существующих Build/Calculate сохранено имя price_sources |

local/delivery без известного city_id отклоняются с 422. Старые запросы без географии валидны и означают all. Город никогда не выводится из домена, названия магазина, IP или часового пояса пользователя.

- **all**: все допустимые предложения, включая неизвестную географию (`location_unknown`). Это не обещание доставки в произвольный город.
- **local**: точный city_id, свежее доказательство: store_stock + in_stock либо seller_declared + seller_declared. Город частника не превращается в подтверждённый магазинный остаток.
- **delivery**: локальные предложения плюс явная свежая доставка в выбранный city_id. Неизвестная или просроченная доставка исключается. Заявление частника помечено seller_declared, не независимая логистическая проверка.

GeoEvidence хранится в StoreOffer.attributes.geography: city_id, location_kind, availability, checked_at, basis и optional delivery {city_ids,cost_rub,checked_at,kind,basis}. Для географии/доставки срок доказательства 24 часа через общий UTC clock; TTL цен и 15-минутное подтверждение страницы не изменены. Недопустимая география читается как unknown. Явное unavailable не участвует в поиске. Старые записи без новых metadata остаются unknown и видны только в all.

`cost_rub=null` — неизвестная стоимость, `0` — явно заявленная нулевая. Для local речь о самовывозе, стоимость пересылки не требуется; затраты на поездку пользователя не рассчитываются.

## Общий контракт предложения

Физическая модель StoreOffer сохранена. Поисковый JSON дополнен:

- source/source_label, offer_type (`store`, `catalog`, `seller`), seller_type;
- id, url, category, hardware_id, name, condition;
- price_rub — цена товара; total_known_cost_rub — товар + известная доставка в режиме delivery;
- price_trust / price_status: verified, catalog_import, seller_declared, unconfirmed; observed_at и price_verified_at;
- geography: исходный город, target_city_id, location_status, availability_status, local_match, delivery_match/status/cost_rub и delivery_cost_unknown.

Ничего не сливается по похожему названию: одинаковый товар у двух источников — два предложения. Магазинный upsert использует существующий уникальный URL; импорт дополнительно использует (source + стабильный внешний ID). Внутренний URL привязан к одному Listing ID и обновляет тот же StoreOffer. Ti/VRAM/суффиксы сохраняются. Поиск `RTX 5060 Ti 16GB` не включает 8GB; объявление CPU+GPU не получает Hardware одной детали.

При фильтрации неизвестное не повышается до подтверждённого. Унаследованный StoreOffer/JSON feed остаётся историческим операторским наблюдением с прежними TTL; он не является доказательством нового разрешения на сеть. Перед production владелец должен отдельно проверить права показа старых данных. Закрытые CSV/XLSX-импорты и fixture не становятся такими legacy feeds: их CatalogAccess проверяется по связанному ID всегда.

## Собственная биржа

Источник `upgradelab` добавлен в общий Source/LABELS (12 прежних + биржа). Это не сетевой store adapter. internal_offers читает Listing, ListingOwner и User через SQLAlchemy, без HTTP к своему backend. Материализуются только:

- active sale, положительная целая цена, не неисправное;
- существующий владелец и профиль;
- свежее подтверждение продавца;
- однозначная связь CPU/GPU/RAM с существующим Hardware и соответствующее название.

GPU требует явного совпадающего VRAM. Несуществующие Hardware, другой тип, сочетание CPU+GPU, mobile, Ti/VRAM-конфликты не проходят. Для RAM сверяется каталог и используются его ram_type/capacity/channels. **Биржа пока надёжно связывает только CPU/GPU/RAM.** Пользовательские объявления плат/SSD/PSU/корпусов/кулеров не притворяются проверенными и не дополняют оптимизатор произвольными профилями.

В attrs сохраняются listing_id, публичное имя/ID владельца, даты публикации/изменения/подтверждения и seller geography. Email, password_hash и приватные данные профиля не выдаются. Origin всегда seller_declared; клиент не может записать магазинное verified. Статус sold/withdrawn, удаление, просроченное подтверждение и изменение модели/цены/города немедленно проверяются при выдаче, включая прямой offer_id. Старые материализованные StoreOffer не удаляют историю, но перестают быть пригодными.

Существующий API редактирования уже сбрасывает подтверждение наличия при существенных изменениях. Дополнительно сбрасывается заявление доставки. Владелец может заявить доставку через:

```http
PUT /api/listings/{listing_id}/delivery
Content-Type: application/json

{"city_ids":["ru:kemerovo"],"cost_rub":null}
```

Требуется cookie-сессия владельца. Проверены чужой ID, неизвестный город и отрицательная цена. checked_at и kind=seller_declared устанавливает сервер. Отдельной формы редактирования маршрутов доставки в React пока нет; API используется без превращения заявления в независимое подтверждение.

Прямой URL `/?tab=marketplace&listing=<id>` открывает существующую биржу и модальное окно объявления. Sold/withdrawn/удалённые записи не возвращаются публичным списком и не открываются как пригодные товары.

## Права и сеть

1. CatalogAccess сохраняет раздельные development/public_display/commercial/automatic_download, основание и подтверждение владельца. Публичная выдача и просмотр по ID/сохранению/заданию фильтруют закрытый импорт. Fixture виден только внутри локального Python-контекста, не через HTTP-флаг.
2. Новый source_permissions.network_allowed — централизованный технический gate для collect_source (включая HTTP/web/feed), page verification и authenticated from-url. Без записи — запрет, attempted=false, outcome=access_not_permitted. Импортное разрешение само по себе не включает сеть; обе применимые проверки должны разрешить операцию.
3. Настройка SOURCE_PERMISSIONS — серверная JSON-строка. Формат одной записи:

```json
{
  "regard": {
    "automatic_network": false,
    "public_display": false,
    "basis": "Ссылка/описание документально подтверждённого основания",
    "confirmed_by": "Владелец проекта",
    "confirmed_at": "2026-11-09T00:00:00Z"
  }
}
```

Это **пример с запретом**, не полученное разрешение. Подтверждение должно быть не из будущего. Env/config — техническая запись, не юридическое доказательство. В этой итерации реальные разрешения не выдавались. Grant не передаётся из браузера. Тесты старых транспортов получили явные synthetic grants, внешние socket при этом остаются mocked.

Avito исключён независимо от grants и браузерной настройки: автоматический collector и verifier не обращаются к нему, новый UI не выбирает его по умолчанию и показывает запрет. Ранее сохранённые исторические данные не удаляются. HTTP 401/429/498, CAPTCHA, WAF не обходятся. SafeSession, TLS verification, Host/SNI, DNS pinning, SSRF/redirect caps сохранены. source_outcomes не заменяются фиктивным success: deny имеет отдельный исход; внутренняя биржа имеет attempted=false и свой фактический result_count.

## Техническая совместимость

Отдельный technical_evidence возвращает **compatible / incompatible / unknown** с причиной. Unknown не становится доказанной несовместимостью и не разрешает гарантированную покупку.

### M.2 и SSD

StorageSlots: applies_to — точное название предложения, slots [{kind: M.2/SATA, interfaces: NVMe/SATA, sizes, available, sockets}], basis и source_url. Учитываются свободные слоты, интерфейс, 2280 и заявленные ограничения сокета. Неизвестный/невалидный или относящийся к другой плате профиль — unknown. Явно другой интерфейс/размер, ноль свободных слотов и nvme_2280=false — incompatible. B450 сам по себе не доказывает M.2 PCIe.

Существующие точные reviewed-профили nvme_board_evidence и явное legacy evidence сохранены. Для SATA без данных о слотах статус unknown; явное противоречие исключает комбинацию. Для NVMe отсутствие положительного evidence по-прежнему блокирует полную комбинацию — не подменяем его догадкой.

### PSU

Существующие manufacturer profiles качества не расширены придуманными сериями. PF550/PL550D не получают свойства PK550D; V2/другая ревизия не наследует старый профиль. Различаются psu_model_unknown, psu_revision_unknown, psu_insufficient_power, psu_connectors_unknown, несовпадение профиля разъёмов и недостаточные разъёмы.

Connectors привязан через applies_to к точному названию, требует atx24, eps_4plus4, pcie_6plus2, basis/source_url. Отдельное system_connector_requirements содержит явные gpu_model + gpu_vram, число PCIe и основание. Требования другой GPU/VRAM не доказывают совместимость. Модель PSU/мощность и разъёмы — разные проверки. Наличие профиля производителя не доказывает подлинность товара продавца.

Импортная technical-конфигурация допускает только storage_slots/power_connectors/system_connector_requirements с валидацией и происхождением. Через неё нельзя внедрить price_verification или произвольные attrs. Технические характеристики не получаются из условий цены. Новые разъёмы/слоты в demo — явно **synthetic fixture specification**, не подтверждённые факты о реальных магазинах.

## Подбор, деньги и статусы

Используется прежний assemble_auto/solve_profiles: восемь категорий, совместимость платформы, мощность, качество, полный бюджет; первоначальные доли и flexible перераспределение сохранены. География применяется к общему available_offers, ручным ID, price_map и upgrade_market_rows. SearchOffers внутри full/upgrade получают те же city/geo/max_price/limit. Неизвестные разъёмы или доставка не заменяются вымышленными товарами.

В delivery цена для оптимизации включает **известную** доставку на уровне предложения; это временная проекция, цена StoreOffer в БД не переписывается. API сохраняет goods_price_rub/delivery_cost_rub и total_known_cost. При неизвестной стоимости рассчитывается только сумма товаров/известных расходов, payable_total_rub=null, purchase_ready=false. Доставка разных товаров считается отдельно: скидки за общую посылку/объединение заказов не придуманы.

- complete: полный набор и допустимые подтверждения цены; финансовые/технические неизвестности по итоговой проверке понижают до draft.
- draft: восемь предложений, но цена продавца/прайса, техническое evidence или доставка не позволяют обещать покупку.
- partial: недостающие/неподтверждённо совместимые категории; сумма относится к найденным частям, не полному ПК.

prices_confirmed отдельно сохраняет факт прохождения прежней проверки цен. Он не равен purchase_ready. Для старых all-запросов форма ответа совместима, но неизвестная доставка/разъёмы теперь честно делают результат draft вместо прежнего чрезмерного complete. В React это явно предварительный результат, а не скрытое изменение суммы.

Денежная схема не мигрировалась: price_rub и доставка пока целые RUB, bool/отрицательные/дробные объявления не превращаются в ноль, hidden rounding нет. Decimal прайс-листа сохранён точно в staging; дробные строки не попадают в integer-оптимизатор. Это **не** сквозная поддержка копеек.

План отдельной финансовой миграции: добавить nullable integer *_kopecks (не float); целые исторические RUB преобразовать ×100 без изменения исторических JSON; Decimal из staging переводить ×100 только при точно двух знаках; валюта явная; одновременное чтение старого/нового формата с версией и конфликт-check; транзакционная миграция на копии с backup/rollback, тестами границ/TTL/истории/доставки; после проверки переключить API с обратной совместимостью и затем отдельно отказаться от старых полей. Ни один из этих шагов на рабочей БД не выполнен.

Диагностика partial отделяет no_offers, model_unconfirmed, insufficient_characteristics, incompatible, outside_budget, availability_unknown, delivery_unknown. Unknown наличия/доставки объясняет отсутствие подходящего географического предложения, а не отсутствие товара в стране. Пользователь видит человеческие тексты; внутренние reason codes остаются в JSON.

## Кеши, задания и история

search_key включает query/category/sources/method + city_id/geo_mode/max_price/limit. Разные города не делят кеш. Кеш хранит статусы поиска, а список биржи каждый раз строится из текущих Listing/Owner/User. Проданные/снятые/удалённые не остаются в результатах из-за старого кеша.

Request key существующего SearchJob дополнен revision объявлений, владельцев, доставки и импортных прав. Цена/модель/город/статус меняют revision. При чтении готового job проверяются связанные offer_id и текущие права; изменённый/закрытый результат целиком не выдаётся, клиенту предлагается повторить поиск. Это не обход прав через старый capability URL. Потерянный повтор POST при неизменном состоянии остаётся идемпотентным.

SavedBuild JSON не переписывается. Прежний price review остаётся read-only, приватные ID и неактивные объявления скрыты. Если историческая часть включает доставку или её стоимость неизвестна, новая подтверждённая сумма не выводится простым сравнением с ценой товара: состояние unconfirmed. Иначе старое сохранение могло бы принять стоимость товара за полный delivered total.

## Модели и миграция

Одна новая таблица **listing_delivery**: listing_id FK/PK, evidence JSON. Колонок в существующих таблицах не добавлено, финансовой/Hardware миграции нет. Обычный Base.metadata.create_all создаёт новую таблицу при следующем штатном старте, как и существующие таблицы проекта. Самостоятельно рабочий startup/миграции не запускались.

Проверены создание новой таблицы поверх старой схемы с сохранением данных и create_all на копии старой live SQLite. Для production перед запуском сделать backup SQLite при согласованной остановке записи, проверить разрешения/конфигурацию и доступность каталога. Старые объявления без доставки остаются unknown, а не получают default free shipping.

## Воспроизводимая демонстрация и replay

Из backend:

```powershell
.\.venv\Scripts\python.exe -m scripts.unified_geo_demo --output ../.artifacts/unified-geo-example
.\.venv\Scripts\python.exe -W ignore::DeprecationWarning -m unittest tests.test_unified_geo_offers -q
```

Каталог назначения новый: demo отказывается перезаписывать существующую SQLite. Создаются отдельная unified.fixture.db, synthetic CSV/schema/rights/result.json, два объявления в Кемерово/Москве, закрытый для HTTP fixture-прайс и отдельное магазинное fixture-предложение. Внутренний fixture-контекст открывает прайс только локальному сценарию. Все socket в demo запрещены.

Фактический результат: RTX 5060 — all 3, local Кемерово 2, delivery Кемерово 2. Московское объявление без подтверждения доставки исключается. 8 частей **52 000 ₽**, статус **draft**, источник продавца сохранён; магазины/биржа/прайс комбинируются. Закрытый прайс вне контекста не виден. У SSD/PSU явные локальные provenance; отсутствующие характеристики отдельно дают unknown. В unit-тесте полный набор с допустимыми подтверждениями цены, локальным наличием и техническими доказательствами даёт complete; удаление данных о разъёмах понижает его до draft.

Replay старого live выполнялся на новой копии с фиксированным UTC-временем исходного наблюдения и запретом socket/fetch/search. Результат остаётся **partial: 6 деталей, 65 488 ₽**. SSD: insufficient_characteristics, у плат нет evidence M.2 PCIe; PSU: единственный распознанный профиль 55 251 ₽, нет подходящей цены, разъёмы неизвестны. Исходные report.json/check.db/verification.json не переписаны, синтетические товары в replay не добавлены. Артефакт: `.artifacts/live-80000/iteration10-replay-result.json`.

## Проверки и известные ограничения

Полные числа окончательной регрессии фиксируются в CHANGELOG_DEV.md и отчёте. Frontend проверен в локальном Edge с перехваченными API на 320/375/430/768/1280/1920 px: географические поля доступны, scrollWidth соответствует viewport, ошибок JS нет; перехвачен POST с ru:kemerovo/local/max_price=25000/budget=80000. Это проверка UI, не внешних магазинов. Снимки/JSON — `.artifacts/iteration10-ui/`.

Ограничения для production:

- Настоящие feed/schema/разрешения и географические доказательства ещё нужны. Источники без network grant не запускаются; прежние 401/429/498 и generic HTTPS/parse failures не перепроверялись, их точная причина не выдумана (см. LIVE_80000_DIAGNOSTIC.md).
- Старая публичная база наблюдений требует владельческого аудита прав показа; новый gate не предоставляет права задним числом. CSV/XLSX закрытые данные защищены независимо от этого.
- Биржа надёжно нормализует CPU/GPU/RAM; остальные категории объявлений остаются вне автоматического набора. Seller delivery API есть, отдельный редактор маршрутов в UI не добавлен.
- City directory — существующий ограниченный список, не полный ФИАС. Общероссийские логистические тарифы, реальные остатки и персональные условия не подключены.
- Профили слотов/разъёмов ограничены явным evidence; корпуса/габариты/BIOS и индивидуальные SKU требуют дополнительных подтверждений. Новых manufacturer-спецификаций из сети не получали.
- Сохранены ограничения кандидатов и ранние бюджетные проверки прежнего решателя; крупномасштабная нагрузочная проверка на десятках тысяч моделей отдельно не выполнена. Marketplace sync выполняется в текущей SQLAlchemy session, не в network workers.
- Целые RUB, доставка по каждому предложению, нет расчёта объединённых заказов и скрытой поддержки копеек.

Предлагаемый коммит: `feat: unify geographic offers and integrate marketplace with evidence-based builds`. Коммит/публикация не выполнялись.


## Итоговые проверки

- Backend: **424 обнаружено, 422 успешно, 2 прежних пропуска**, 66.951 с; в том числе **32/32 новых теста** единого поиска.
- Frontend: **54/54**, включая четыре новых теста представления происхождения/доставки/совместимости; production build успешен.
- Проверены миграция новой таблицы поверх старой схемы и replay на копии live БД. Все 160 StoreOffer копии совпали с исходными значениями; новая таблица появилась в копии и отсутствует в исходном снимке.
- UI Edge: 320/375/430/768/1280/1920 px, без горизонтального переполнения и ошибок JS, проверен фактический POST геопараметров.
- git diff --check и проверка whitespace новых файлов — без ошибок.

Проекция биржи синхронизируется и сохраняется в search/build/calculate entry points до возврата ID; cache hit не выдаёт ID откатившейся вставки. Изменение города также снимает подтверждение текущей суммы сохранения, не меняя историческую стоимость. Это проверено отдельными регрессиями.

## Файлы итерации 10

Предыдущие незакоммиченные файлы итерации 9/аудита остаются в рабочем дереве; ниже — файлы, затронутые текущей работой.

- `backend/app/api/calculate.py`
- `backend/app/api/listings.py`
- `backend/app/api/offers.py`
- `backend/app/api/search_jobs.py`
- `backend/app/core/config.py`
- `backend/app/db/models.py`
- `backend/app/schemas/geography.py`
- `backend/app/schemas/offers.py`
- `backend/app/schemas/calculate.py`
- `backend/app/schemas/catalog.py`
- `backend/app/services/internal_offers.py`
- `backend/app/services/offer_geography.py`
- `backend/app/services/source_permissions.py`
- `backend/app/services/technical_evidence.py`
- `backend/app/services/result_access.py`
- `backend/app/services/offers.py`
- `backend/app/services/builds.py`
- `backend/app/services/assembly_search.py`
- `backend/app/services/assembly_diagnostics.py`
- `backend/app/services/automatic_builds.py`
- `backend/app/services/storage_compatibility.py`
- `backend/app/services/component_quality.py`
- `backend/app/services/prices.py`
- `backend/app/services/upgrade_prices.py`
- `backend/app/services/catalog_import.py`
- `backend/app/services/catalog_access.py`
- `backend/app/services/offer_safety.py`
- `backend/app/services/price_verification.py`
- `backend/app/services/saved_prices.py`
- `backend/app/services/search_jobs.py`
- `backend/app/services/store_providers.py`
- `backend/scripts/unified_geo_demo.py`
- `backend/tests/test_unified_geo_offers.py`
- `backend/tests/source_grants.py`
- `backend/tests/test_adaptive_builds.py`
- `backend/tests/test_assembly_fallback.py`
- `backend/tests/test_build_variants.py`
- `backend/tests/test_free_search.py`
- `backend/tests/test_price_time.py`
- `backend/tests/test_price_verification.py`
- `backend/tests/test_safe_http.py`
- `backend/tests/test_source_outcomes.py`
- `backend/tests/test_source_readiness.py`
- `backend/tests/test_live_80000_diagnostics.py`
- `frontend/package.json`
- `frontend/src/App.jsx`
- `frontend/src/components/GeoControls.jsx`
- `frontend/src/components/StoreOffers.jsx`
- `frontend/src/components/calculator/BuildSection.jsx`
- `frontend/src/components/calculator/BuildChoices.jsx`
- `frontend/src/components/calculator/CalculatorForm.jsx`
- `frontend/src/components/calculator/CalculatorSection.jsx`
- `frontend/src/components/calculator/AssemblySearchSummary.jsx`
- `frontend/src/components/calculator/UpgradeChoices.jsx`
- `frontend/src/components/marketplace/MarketplaceSection.jsx`
- `frontend/src/lib/offerEvidence.js`
- `frontend/src/lib/offerEvidence.test.js`
- `frontend/src/lib/sourceDiagnostics.js`
- `docs/UNIFIED_GEO_OFFERS.md`
- `docs/PRICE_FEED_IMPORT.md`
- `docs/ARCHITECTURE.md`
- `docs/TECHNICAL_AUDIT.md`
- `docs/TODO.md`
- `docs/CHANGELOG_DEV.md`
