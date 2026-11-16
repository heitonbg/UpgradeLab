# FPS Engine v2: аудит, проверка данных и безопасная интеграция

Дата: 2026-11-10. Итерация выполнена поверх предыдущих незакоммиченных изменений. Commit, push и deployment не выполнялись. Рабочая SQLite не изменялась.

## Результат и границы

**Новую откалиброванную FPS-модель в production не включали. Улучшение точности не доказано.** Реализованы локальный каталог игр, строгий отбор измерений и оценочный отчёт, безопасный FPS API с отказом при неподдерживаемых условиях, три режима цен и исправления двух подтверждённых дефектов сборщиков. Полноценное обучение по CPU Single Thread/архитектуре/L3/VRAM/RAM и игровой калибровке остаётся заблокировано качеством исходных данных.

Исправления CPU и RAM воспроизведены падающими тестами: сборщики не передавали cpu_name и использовали общий 1.07 RAM-множитель даже для CS2, тогда как апгрейд использовал отдельное правило. Теперь оба сборщика передают имя CPU и вызывают общий ram_performance_factor. Это исправление согласованности расчётов; оно не является измеренным снижением MAE.

## Источники, лицензии и фактический импорт

| Источник | Доступ / формат / лицензия | Использовано |
| --- | --- | --- |
| [PC Game FPS Dataset](https://github.com/emilioagustin83/pc-game-fps-dataset) | CSV получен; CC BY 4.0, атрибуция PCGameBenchmarks. Текст лицензии сохранён в PCGAMEBENCHMARKS_LICENSE.txt | 16 623 строки названий, год, исходная ссылка; **0 чужих расчётных FPS**. После нормализации, удаления повторов и объединения с 19 поддерживаемыми играми — 16 447 элементов поиска. Требования Steam также не копировались |
| [Wikidata](https://www.wikidata.org/wiki/Wikidata:Licensing) | Структурированные данные CC0. Проверен JSON Q17452, revision записан | 1 существующая игра GTA V проверена; en/ru aliases пусты, новых псевдонимов из Wikidata — 0. Локальные ручные aliases CS2/GTA/танков отделены от импорта |
| [Open GPU Benchmarks](https://opengpubenchmarks.com/benchmarks/), [лицензия](https://opengpubenchmarks.com/license/) | JSON dashboard получен, CC BY 4.0. Сохранены _license, _source, schema/release/commit, условия, даты, источник и CPU/RAM/драйвер | Архив 85 записей: 64 игровых, 21 синтетическая нагрузка. В строгую выборку native Windows desktop без RT/FG/upscaling прошли **3 измерения** одной пары CPU/GPU и одной тестовой серии Cyberpunk 2077 |
| [FPSHQ Data](https://fpshq.com/data/), [API](https://fpshq.com/api-docs/) | Публикует CC BY 4.0 и атрибуцию; прогнозы и замеры нужно разделять. Прямое получение страницы завершилось timeout; web-open также давал 403 | 0 импортированных строк; runtime API не подключён. Индексированное описание не считается полученным датасетом или подтверждённым набором независимых замеров |
| [BenchPress Data](https://github.com/sturimcode/benchpress-data) | README и Cyberpunk JSON доступны; данные CC BY 4.0, код MIT. Baselines обозначены как estimates | В дереве reports только .gitkeep; 0 измерений для калибровки. Оценки настроек не принимались за эксперименты |
| Existing PassMark / seed_data / price_data | Использованы уже имеющиеся CPU Mark, GPU G3D Mark и датированные цены; новые PassMark данные не скачивались | Права на дополнительную загрузку/распространение PassMark не объявлены подтверждёнными этой итерацией |

Источник: PCGameBenchmarks — https://pcgamebenchmarks.com, CC BY 4.0. Источник измерений: Open GPU Benchmarks — https://opengpubenchmarks.com, CC BY 4.0. Происхождение отражено в локальных JSON. Полный raw CSV исследовательского скачивания — `.artifacts/fps-v2/games_csv.raw`; SHA-256 зафиксирован в game_catalog.json. Raw dashboard сохранён целиком как app/data/fps_measurements.json, его hash исследовательского снимка: `61219f37b96ba54e1672357c8f08da85debc8c10c690bd4aa2ee7a60370a00ba`.

Наличие названия в каталоге не означает наличие измерений. Прогнозы другого сервиса не используются как ground truth.

## Каталог игр

GET /api/games?q=Counter-Strike%202&limit=50 читает локальный game_catalog.json, добавляет существующие игровые профили и aliases. Нормализация NFKC/casefold, поиск по имени и альтернативным названиям. Каталог загружается один раз на процесс; LRU хранит 256 поисков. Frontend делает debounce 200 ms, кеширует до 100 запросов к **своему backend**; внешних запросов на ввод нет. Twitch/IGDB и регистрация не требуются.

GamePicker сохраняет текущий выбор. Найденные игры без модели показаны disabled с объяснением. Основные 19 игр доступны при сбое расширенного каталога. Серверный enum существующего расчёта не расширялся произвольными названиями, для которых пришлось бы выдумать коэффициент.

Офлайн-обновление после самостоятельной проверки лицензии скачанного CSV:

```powershell
cd C:\vscode\upgradeLab\backend
.\.venv\Scripts\python.exe -m scripts.import_game_catalog path-to-games.csv
```

Перезапуск backend очищает кеш. Импортёр не выполняет HTTP и не пишет в SQLite.

## Математика сохранённой модели

Для game/mode заданы коэффициенты a_cpu, a_gpu и overhead:

`FPS = round(max(1, min(CPU_capacity, GPU_capacity) * overhead))`.

Обычный CPU_capacity = CPU Mark × a_cpu × RAM factor. GPU_capacity — опубликованная GPU-опора/интерполяция, если есть подходящий набор, иначе G3D Mark × a_gpu. Текущие игровые коэффициенты заданы в constants.py вручную; процедуры их обучения в репозитории нет. Девять старых наборов GPU-опор не содержат достаточной полной информации о каждой CPU/RAM/версии игры для обучения общей модели пар.

Для CS2 Low существующая модель использует отдельные относительные CPU-опоры и GPU Medium-результаты с явным отличием пресета. Для отсутствующего CPU — смягчённая кривая CPU Mark. Legacy CS2 содержит приближения для родственных CPU, включая 5600X3D/5700X3D от 5800X3D; это **не измерения этих моделей**. Они не были добавлены или объявлены доказанной моделью v2 этой итерацией. Для 5500X3D отдельной опоры нет. Его различие с 5600X в старом расчёте может происходить от CPU Mark, а не подтверждённого эффекта кеша. Постоянный новый X3D-бонус не вводился.

Общий RAM factor сохранён: CS2 использует отдельное правило каналов; другие игры — существующие DDR/канальные коэффициенты. Их эмпирическая точность не доказана. Объём RAM, Single Thread Rating, архитектура, частоты и L3 не получают вымышленных значений; нет откалиброванного влияния VRAM, RT, DLSS/FSR/XeSS или FG.

POST /api/fps/predict принимает hardware IDs, игру, resolution/preset и известную RAM. Возвращает legacy_estimate, отдельные CPU/GPU ceilings, limiting_component, метод, источники, признаки и предупреждения. Для неизвестной игры, отсутствующих положительных scores, неподдерживаемого режима, RT/upscaling/FG — insufficient_data и average_fps=null. 4K, Medium/Ultra не экстраполируются без опор. 1% Low всегда null: отдельной модели нет. Существующий calculator API сохраняет прежний контракт.

Диапазон legacy эвристический и возвращается с calibrated=false; это не статистический доверительный интервал. Неизвестный CPU/GPU с известным синтетическим score может получить только явно помеченную legacy-оценку; измерением она не становится.

## Валидация и измеренная ошибка

Отбор требует game_type=game, nonsynthetic, native, FG=false, Windows, Desktop, Low/Medium/High/Ultra, известные CPU/GPU/source_file/date/game_version и положительный конечный FPS. Синтетический OpenBenchmarker не становится игрой из-за общего поля benchmark_type. Условия сохраняются, разные ОС и RT не смешиваются.

Split группирует publisher + testbench_source_id + GPU + game + game_version. Все разрешения, пресеты и повторы серии остаются вместе. Имеется только одна допустимая группа: train=3, независимый test=0. Делить три разрешения одной серии на train/test было бы утечкой. Поэтому обучение и promotion новой модели не выполнялись.

| Проверка | n | MAE | MAPE | Покрытие интервала |
| --- | --- | --- | --- | --- |
| Независимый train/test новой модели | 0 test | n/a | n/a | n/a |
| Внешняя диагностика legacy (одна связка, Cyberpunk 2.31, native High) | 2 | 86.385 FPS | 46.559% | 0/2 |
| Новая откалиброванная модель | не обучена | n/a | n/a | n/a |

Диагностика сопоставляет две поддерживаемые настройки для RTX 5080 / Ryzen 9 9950X3D: 1080p High — измерено 193.64, legacy 114; 1440p High — 179.13 против 86. Для 4K старого режима нет, модель воздерживается. Это внешние наблюдения, не использованные для новой калибровки; они демонстрируют проблему переноса старой формулы на эту связку. **Два результата одной серии не оценивают глобальную точность** и не являются независимым train/test сравнением нового движка. Отчёт хранит prediction coverage отдельно (2/3 подходящих измерений поддержаны legacy).

MAE = mean(abs(predicted−measured)); MAPE = 100×mean(abs(error)/measured); interval coverage = доля замеров внутри [low,high]. Пустая выборка даёт null, а не 0 ошибок. Полный воспроизводимый отчёт: `.artifacts/fps-v2/evaluation.json`.

```powershell
cd C:\vscode\upgradeLab\backend
.\.venv\Scripts\python.exe -m scripts.evaluate_fps
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_fps_v2.py
```

CS2, X3D vs non-X3D, слабая GPU и слабый CPU покрыты логическими тестами, но независимой выборки измерений CS2/X3D из разрешённых полученных источников нет. Это не доказательство точности. Для обучения нужны разные CPU (включая сопоставимые X3D), GPU, игры, пресеты и независимые источники/серии с зафиксированными условиями.

## Примеры ответа (сохранённый legacy, не замеры)

RTX 4060, CS2 1080p Low, DDR4 dual-channel 16 GB. CPU/GPU scores взяты из существующего seed_data, а не подобраны для красивого результата:

| CPU | Центральный FPS | Эвристический диапазон |
| --- | --- | --- |
| AMD Ryzen 5 5600X | 406 | 260–550 |
| AMD Ryzen 5 5500X3D | 430 | 275–585 |
| AMD Ryzen 7 5800X3D | 434 | 280–590 |

Сравнение 5500X3D и 5600X в этой таблице не подтверждает эффект кеша: у 5500X3D нет CPU-измерения в модели. Эти числа не следует использовать как доказательство преимуществ CPU при покупке.

## Три режима цен и оптимизатор

BuildRequest.pricing_mode: offers / reference / hybrid; старые клиенты могут не передавать поле. UI выбирает offers явно. Существующий технический solver и complete/draft/partial сохранены.

- **offers**: существующий поиск по допустимым источникам, география, доставка и проверка цен. В явном режиме не подставляются исторические HardwarePrice. Текущая доступность магазина не обещается; seller-declared не превращается в verified.
- **reference**: без сети; технические детали и цены берутся из публично допустимых локальных наблюдений и существующих датированных CPU/GPU HardwarePrice только passmark/avito_snapshot. Hardware сам по себе не содержит цен всех восьми категорий, поэтому при отсутствии исходных цен полной сборки возвращается понятная причина. Числа не дорисовываются. Это плановая стоимость по прошлым наблюдениям, а не актуальное наличие.
- **hybrid**: сначала пригодные кешированные предложения выбранных источников; категории без пригодных позиций дополняются reference. Этот режим не запускает отдельный сетевой поиск и не гарантирует глобальную оптимальность при наличии слишком дорогой или неполной реальной категории.

Reference использует request-local ContextVar inventory и копии исходных наблюдений; записи не вставляются в StoreOffer, даты не освежаются. Источники каталога проходят существующий filter_catalog; закрытый Регард не открывается. Справочный результат сохраняет исходный offer_id внутри reference_basis для текущих проверок прав. Это внутренняя provenance-ссылка, а не возможность купить по старой цене. Публичных источников по-прежнему 13, reference в список магазинов не добавлен.

Справочная позиция: price_basis/reference, price_origin/reference, price_status/reference, исходная дата и source/url, price_verified_at=null, внешний purchase offer_id отсутствует. UI показывает «Справочная цена». Результат с reference всегда draft, purchase_ready=false, prices_confirmed=false. В сохранениях reference_basis не повышается до подтверждённой цены при совпадении URL; история остаётся неизменной.

Solver перебирает полные CPU/GPU + supporting parts, учитывает весь бюджет и FPS вместо одного максимального PassMark; после исправления CPU identity работает общая CS2-логика. Сохраняются сокет/чипсет/BIOS-ограничения, RAM, SSD, PSU, охлаждение и physical_fit; неизвестные параметры дают предупреждение, известные конфликты запрещают вариант. Это ограниченный эвристический solver с shortlist, не доказанный глобальный оптимум. Поддерживается прежний выбор пары selected_cpu_id/selected_gpu_id, а не независимое закрепление только одного CPU.

Пример существующего запроса:

```json
{"scenario":"build","auto_parts":true,"pricing_mode":"reference","budget":80000,"target_fps":60,"game":"CS2","mode":"1080p_low","socket":"AM4","ram_type":"DDR4","ram_capacity_gb":16}
```

В синтетическом тестовом ассортименте все три режима вернули 8 деталей на 48 500 ₽ при лимите 80 000 ₽. Это проверка алгоритма, **не реальная цена ПК и не найденный магазин**. Отдельно протестированы старое наблюдение, гибрид с отсутствующим свежим кулером, недоступный магазин, нехватка категории, неизменность БД и отказ при закрытом каталоге. На другом старом fixture наборе API корректно отказал из-за отсутствующей публично допустимой CPU-цены; её не подменяли закрытым прайсом.

## Проверки, файлы и ограничения

Новые backend-тесты: 23. Полная backend-регрессия и frontend-тесты выполняются офлайн, в отдельных тестовых SQLite. Frontend: 77 тестов; production build успешен. Браузерный smoke: реальный локальный API, поиск Hades (disabled без модели), alias Counter-Strike 2, три режима подбора и FPS unavailable; screenshot 375/1440, без JS errors/overflow. Подробные логи: `.artifacts/fps-v2/`. Полная регрессия: 510 тестов, 508 успешных, 2 пропущены; последние целевые 23/23 также успешны. git diff --check — успешно. Два пропуска существовали до этой итерации.

Основные изменённые файлы:

- backend/app/services/{game_catalog,fps_validation,fps_v2,planning_prices}.py; api/games.py; main.py.
- backend/app/services/{builds,automatic_builds,offers,prices,saved_prices}.py — интеграция и регрессии.
- backend/app/data/{game_catalog,game_aliases,fps_measurements}.json; scripts/{import_game_catalog,evaluate_fps}.py; tests/test_fps_v2.py.
- frontend/src/components/calculator/{GamePicker,BuildSection,AssemblySearchSummary}.jsx; lib/catalogView.js и catalogView.test.js.
- docs/FPS_ENGINE_V2.md, PCGAMEBENCHMARKS_LICENSE.txt; ARCHITECTURE.md, TECHNICAL_AUDIT.md, CHANGELOG_DEV.md, TODO.md.

Не проверялись и не заявлены работающими: реальные магазины/права на новый закрытый Регард, Amvera deployment, физические PC-бенчмарки, реальный X3D cache effect, статистически откалиброванные интервалы/1% Low, RT/FG/upscaling, полноценные 4K/Medium/Ultra модели. Дизайн/CSS не менялись. Нужны новые независимые разрешённые измерения; подгонка под два имеющихся числа не выполнялась.

Предлагаемый коммит: `feat(performance): add evidence-gated FPS API and explicit build pricing modes`.


## Продолжение: Benchmark Data & Calibration (2026-11-10)

Новый отчёт — [FPS_BENCHMARK_DATA.md](FPS_BENCHMARK_DATA.md). Curated dataset использует per-GPU raw records вместо dashboard summaries: 73 игровых прогона Open GPU + 8 уникальных точек нового TechFuelHQ = 81 наблюдение, 72 конфигурации, 4 игры, 2 издателя/4 серии. Повторы не увеличивают независимый test; игровые версии summary не предполагаются одинаковыми. Строгая Windows-когорта — 4 прогона/3 конфигурации; legacy по-прежнему оценим на 2. Новая модель не включена. Добавлен --curated к evaluate_fps, а неположительные hardware scores исключены из подбора/апгрейда. Политика hybrid сохранена; её tradeoff подтверждён контрпримером.

## Продолжение: evidence-backed FPS Engine v2 — 2026-11-13

Сохранённый legacy остаётся production baseline. Добавлен отдельный эмпирический candidate из лицензированного snapshot: точная пара/настройки возвращают опубликованные средний FPS и 1% Low; разрешение между двумя замерами той же пары может быть оценено линейной интерполяцией времени кадра по pixel count. Экстраполяции PassMark → игровой FPS нет. Candidate и его тип данных возвращаются отдельно от baseline через POST /api/fps/predict и показываются в результате калькулятора.

Текущие данные дают 4 native Windows прогона одной пары CPU/GPU в одной серии Cyberpunk 2077. Leave-one-resolution-out для 1440p: candidate MAE 28.97 FPS (n=1), baseline MAE 56.13 FPS (n=1). Это внутрисерийная диагностика, не независимая валидация. Engine не promoted. CPU/GPU curves, bottleneck attribution по измерениям, X3D и ML не подтверждены: независимых вариаций и holdout нет.

Добавлены additive SQLite tables benchmark_sources/benchmark_measurements, нормализованные keys, хеши, полный payload, безопасный идемпотентный импорт и API чтения. BENCHMARK_IMPORT_ON_START по умолчанию выключен локально; в Amvera example он включён, чтобы исходные 87 наблюдений добавлялись в persistent SQLite при запуске. Пользовательские submissions остаются отдельно.

## FPS Engine v4 Universal (2026-11-14)

Выбор игры теперь доступен для всех названий локального каталога; доступность выбора отделена от покрытия FPS. `GET /api/games/coverage` возвращает покрытие каталога и бенчмарков. `POST /api/fps/predict` дополняет прежний production baseline результатом `candidate_v4`, сохраняя старый baseline и `candidate_v3` для совместимости.

Общий resolver `app.services.fps_engine_v4.resolve_fps_v4` подключён к вариантам Builder и ответам Upgrader. Он действует в таком порядке:

1. Лицензированное точное измерение CPU/GPU/игры/настроек или интерполяция разрешения для той же связки, если её допускают измерения.
2. Явно помеченный ориентир существующего профиля прежней модели.
3. В остальных случаях — отказ от прогноза: `average_fps: null` и перечень недостающих данных.

Builder может вернуть совместимый состав деталей и для игры без игровой модели. Тогда он ранжирует комплектующие по отдельным процентилям PassMark CPU и GPU, не показывая FPS или достижение цели. CPU Mark и G3D Mark не сравниваются друг с другом и не переводятся в FPS. RAM не является входом FPS v4; характеристики памяти остаются только частью происхождения опубликованного измерения.

Текущее покрытие локальных данных:

| Покрытие | Количество |
| --- | ---: |
| Уникальные выбираемые игры | 16 447 |
| Профили прежней модели | 19 |
| Игры со строгими нативными парными измерениями | 1 |
| Нативные наблюдения этой модели | 4 |
| Независимые игра / CPU / GPU / связка | 1 / 1 / 1 / 1 |
| Steam AppID / минимальные / рекомендуемые требования | 0 / 0 / 0 |
| Жанры или теги | 0 |

The curated archive contains 87 total rows, but only 4 pass the native-measurement filter. The exact Cyberpunk 2077 + Ryzen 9 9950X3D + RTX 5080 result is 179.13 average FPS and 136.21 1% Low from two records in one independent series. This is a published reference for that test setup, not a repeat measurement of the user's PC. The available independent-series count is too small for a defensible held-out MAE/MdAPE or for CPU/GPU transfer curves. v4 has therefore not replaced the production legacy calculation.

Steam enrichment was not run. This catalog has no Steam IDs to join on. Valve's current documented `IStoreService/GetAppList` requires a Web API key; the older `ISteamApps/GetAppList` is documented as deprecated. No broad automated retrieval of store-page requirements was attempted without stable IDs, an approved metadata feed, and a source-use basis. See [Steam IStoreService](https://partner.steamgames.com/doc/webapi/IStoreService) and [Steam ISteamApps](https://partner.steamgames.com/doc/webapi/ISteamApps).

## Universal GPU estimate coverage — 2026-11-15

A separate CC BY 4.0 PCGameBenchmarks snapshot now supplies per-game GPU-oriented estimates for 16,441 of the 16,447 selectable titles (12 reference GPUs per game; 197,292 points). This is a distinct external model-estimate channel, not measured data and not full-system FPS. FPS Engine v4 interpolates each game's source curve by GPU G3D score only at 1080p High native settings. It does not infer CPU contribution, bottlenecks, 1% Low, RAM uplift, or FPS at other settings. Unsupported GPU classes/scores or settings abstain. Exact pair measurements, then explicitly labeled legacy profiles, retain priority. See PCGAMEBENCHMARKS_IMPORT.md for source revision, match audit, algorithm, and coverage.

The previous v2 evaluation is unchanged: four strict native runs from one CPU/GPU pair and one test series cannot validate universal transfer accuracy. No MAE/accuracy claim is made for the external source model.

## FPS Engine v4 — current behavior and validation (2026-11-15)

The shared `resolve_fps_v4` is used by the FPS API, Builder, and Upgrader. Its source order is: a matching licensed full-system CPU/GPU measurement, a clearly labeled legacy game-profile estimate, then a separately labeled external GPU-oriented estimate. It never turns a GPU-only number into full-system FPS. PassMark CPU/GPU scores remain separate indices, not FPS conversion factors. RAM is absent from the v4 formula; recorded memory details are measurement provenance only.

The pair-measurement path accepts exact tested configurations and frame-time interpolation only between measured resolutions for the same CPU/GPU/game/settings cohort. Resolution aliases including `4K`, `2160p`, `3840x2160`, and `3840×2160` are normalized to one UTC-independent canonical key. The 4K exact API case now returns 91.48 average FPS and 76.80 1% low for the single Cyberpunk 2077 / Ryzen 9 9950X3D / RTX 5080 series row. This is a published reference result, not a test of a user's own PC.

The external PCGameBenchmarks snapshot contains 16,441 game profiles and 197,292 GPU-oriented model estimates (12 reference GPUs per profile), under CC BY 4.0. It supports only native 1080p High for an eligible GPU class and score range. It does not provide system FPS, CPU bottlenecks, 1% Low, or estimates for other settings. GPU scores are interpolated within the source's per-game curve; unsupported classes, conflicts, and out-of-range scores abstain.

Current local coverage: 16,447 selectable games; 19 legacy-profile games; 16,441 external GPU-profile games; 4 strict native measurement rows from one game, one CPU/GPU pair, and one publisher series. The 1,434 CPU and 785 GPU PassMark rows are hardware-rank data. CPU requirements can be resolved against the local catalog for at least one requirement in 4,771 games and both minimum/recommended references in 2,864 games; this is CPU Mark adequacy, not CPU FPS or bottleneck calibration.

A leakage-safe leave-one-resolution-out comparison has one common scored point. At Cyberpunk 2077 1440p High, the v2/v4 pair interpolation predicts 150.16 FPS against 179.13 measured: MAE 28.97 FPS, MdAPE 16.17%, P90 APE 16.17%, bias −28.97 FPS. The retained legacy baseline predicts 123 FPS at that same point: MAE 56.13 FPS, MdAPE/P90 APE 31.33%, bias −56.13 FPS. This is one within-series diagnostic, with only one of three eligible resolution holdouts supported; it is not independent validation and does not justify promotion of a general model. FPS v3 correctly abstains because no calibrated workload anchors exist. The external GPU-only estimate is not scored against full-system FPS; the local 1080p PCGameBenchmarks estimate of 201 and OGB measured full-system average of 193.64 have different targets and are shown only side by side.

On a read-only local catalog, 100 real `/api/fps/predict` calls returned HTTP 200 (86 external GPU-model estimates and 14 labeled legacy estimates). A separate API request returned the exact 4K measurement above. Builder API response, Upgrader GPU-only delta, and CPU Adequacy change were exercised with network price refresh disabled; the smoke script stubs the costly assembly-selection operation, so it is not an optimizer benchmark. See `FPS_BENCHMARK_DATA.md` for exact coverage and error reasons.

Final unified-engine verification (2026-11-15): backend 745 tests passed / 2 skipped on an isolated temporary SQLite database; frontend 122/122; Vite production build and Python compileall succeeded; `git diff --check` passed.

## Единый адаптивный результат FPS — 2026-11-15

`app.services.adaptive_fps.predict_adaptive_fps(cpu, gpu, game, settings)` — общий resolver-представление для `POST /api/fps/predict`, сборщика и апгрейдера. Он отдаёт один `fps_result` с типом `measured_system_fps`, `estimated_system_fps`, `gpu_reference_only` или `unavailable`. Старые поля `fps_v2_evidence`, `fps_v3_evidence` и `fps_v4_evidence` сохранены только для совместимости API; текущий интерфейс показывает один выбранный результат.

Приоритет источников: подходящий лицензированный тест полной связки; интерполяция разрешения только по той же CPU/GPU связке и сопоставимым условиям; явно помеченный legacy-профиль; FPSHQ/PCGameBenchmarks GPU-опора; ближайшая опорная видеокарта той же игры; широкий межигровой GPU-ориентир. Последние уровни дают число только для видеокарты и явно показывают исходные настройки. Интерполированный 1% Low не создаётся. GPU-only значение не заполняет FPS системы. Ограничивающий компонент возвращается только при явном признаке калибровки; текущая выборка не даёт оснований заявлять CPU/GPU bottleneck.

RAM может участвовать только как известный контекст теста и отфильтровать несовпадающее измерение. Тип, объём и канальность RAM не меняют FPS-формулу. PassMark CPU Mark и G3D Mark остаются отдельными аппаратными индексами, а не переводятся в FPS. Прирост апгрейда показывается только между сопоставимыми результатами одной модели/серии; изменение CPU не получает фиктивный прирост из неизменившейся GPU-only оценки.

Покрытие `adaptive_game_coverage()`: 16 447 выбираемых игр; 19 имеют хотя бы один legacy-прогноз полной системы; 1 игра имеет 4 строгих измерения одной CPU/GPU пары из одной серии; 16 441 игра имеет внешний GPU-профиль; у 1 нет отдельной игровой GPU-кривой, поэтому используется только широкий межигровой ориентир. Каталог включает 1 434 CPU и 785 GPU. Это покрытие названий игр, а не обещание FPS всей системы: для числа нужны валидный score GPU или точный источниковый crosswalk. PCGameBenchmarks curve использует native 1080p High; при отличающихся настройках API возвращает число с явной маркировкой условий источника.

Единственная общая leakage-safe точка сравнения — Cyberpunk 2077 1440p High: интерполяция 150.16 против измеренных 179.13 FPS, MAE 28.97 FPS и MdAPE/P90 APE 16.17%; legacy baseline 123 FPS, MAE 56.13 FPS и MdAPE/P90 APE 31.33%. Это один внутрисерийный диагностический пример, недостаточный для независимого подтверждения точности или production-promote новой универсальной модели. ML, CPU frametime decomposition, RT, upscaling и frame generation остаются неоткалиброванными.

### Числовой fallback для любой выбираемой игры — 2026-11-15

Начиная с этой правки v4 не оставляет пустым числовой результат только потому, что нет точной пары CPU/GPU. Порядок доступных вариантов: опубликованный тест всей пары; интерполяция этой пары; прежняя модель игры; FPSHQ GPU-опора для 50 игр и совпадающих 1080p/1440p/4K High условий; профильная GPU-оценка PCGameBenchmarks на 1080p High; ближайшая GPU-опора той же игры, если score вне безопасного диапазона; общий GPU-ориентир по медиане 16 441 профилей игр. Для игры вне каталога доступен только последний общий ориентир. `best_available_fps` и `best_available_fps_basis` дают единое поле для UI/API.

GPU-only значение не заполняет `average_fps`, 1% Low, bottleneck или прирост полной системы. В API рядом сохраняются `settings` запроса и `source_settings` источника. Общий fallback возвращает межигровые P10–P90 как разброс каталога, а не интервал точности выбранной игры. Для неизвестной/виртуальной/неотрисовывающей карты, отсутствующего PassMark score без точного разрешённого crosswalk, либо отсутствия физической GPU-опоры результат остаётся недоступным: числовое значение в таких случаях было бы выдуманным.

Дополнительный `requirements_anchored_v1_experimental` строит отдельный сценарий CPU+GPU, когда точные CPU и GPU из рекомендованных требований (или минимальных при отсутствии точного рекомендованного набора) сопоставились с локальными PassMark записями. Сценарий помечен как очень низкой достоверности; чувствительность параметров не является доверительным интервалом, системные требования не являются FPS-замером, RAM не участвует. Он не заменяет основной результат и не калибрует bottleneck.

Пример: Ryzen 5 5600 + RTX 5090, Cyberpunk 2077, 1440p High сейчас показывает legacy-оценку системы около 166 FPS и отдельную FPSHQ GPU-опору около 171 FPS. Это два разных вида результата, а не подтверждение, что система должна выдать 171 FPS. В локальном FPSHQ наборе 2 400 GPU-строк для 50 игр и 16 моделей: 1 666 model, 728 aggregate и 6 строк с меткой measured; даже последние не содержат сопоставимых CPU/GPU системных замеров и не используются как такие замеры.

Покрытие по играм означает наличие источникового числа для GPU, а не доказанную точность прогноза всей системы. Сводка и проверка сценариев: `backend/scripts/evaluate_requirements_anchored.py`; SQLite открывается только в режиме `mode=ro`.
