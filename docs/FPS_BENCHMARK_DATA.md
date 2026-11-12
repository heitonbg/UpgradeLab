# FPS Benchmark Data & Calibration

Дата исследования: 2026-11-10. Существующие незакоммиченные изменения сохранены. Рабочая SQLite, дизайн, price TTL и правила авторизации не изменены. Commit, push и deployment не выполнялись.

## Вывод

Получен воспроизводимый нормализованный набор **81 наблюдение: 73 исходных прогона Open GPU Benchmarks и 8 уникальных опубликованных точек TechFuelHQ**. Это 4 игры, 3 точные модели CPU, 3 модели GPU/устройства, 4 тестовые серии и 2 издателя. После объединения повторных прогонов для оценки остаются 72 конфигурации.

Новый независимый источник добавил 8 точек и 2 игры к прежнему покрытию. Переход от dashboard к per-GPU records восстановил отдельные прогоны; повторы не объявляются новыми независимыми сериями. **Сопоставимых данных для доказанного улучшения Windows FPS Engine пока недостаточно. Новая модель не включена в production.**

Главное ограничение — разнообразие и условия, а не число строк: строгая stock/native Windows-когорта содержит 4 прогона, но всего 3 конфигурации одной пары Ryzen 9 9950X3D / RTX 5080 FE в Cyberpunk 2077. Из них legacy поддерживает 2 конфигурации. Нет контролируемых пар X3D/non-X3D и нет разрешённых CS2-измерений в новом наборе.

## Источники и решения по разрешениям

Robots.txt проверялся отдельно от лицензии: доступность страницы или разрешение обхода само по себе не даёт права перепубликовать/обучаться на данных. Снимки ответов и хэши — `app/data/benchmarks/source_policies.json`, реестр решений — `sources.json`. Защита, CAPTCHA, TLS и запреты не обходились.

| Источник | Лицензия / robots / доступ | Решение |
| --- | --- | --- |
| [Open GPU Benchmarks](https://opengpubenchmarks.com/license/) | CC BY 4.0, ai-training explicitly permitted; robots Allow /, ai-train=yes. Документированный API доступен | Импортированы 73 игровых прогона из двух per-GPU JSON. Dashboard не смешивается с raw records |
| [TechFuelHQ](https://techfuelhq.com/data/gpu/rog-astral-rtx-5080-oc-2026-06-09/), [условия](https://techfuelhq.com/terms/) | Dataset CC BY 4.0, robots разрешает доступ, условия подтверждают повторное использование датасетов с атрибуцией | 9 игровых точек, 1 повтор объединён → 8. Автор заявляет собственные тесты; это не независимая проверка его оборудования нами |
| [OpenBenchmarking](https://openbenchmarking.org/) | Checked robots: ai-train=no, use=reference. Страница legal вернула 403; лицензия пользовательских результатов не установлена. GPL кода Phoronix не является лицензией данных | Не импортирован и не использован для обучения |
| [FPSHQ](https://fpshq.com/data/), [API docs](https://fpshq.com/api-docs/) | Документация заявляет CC BY 4.0; robots закрывает /api/ с узкими исключениями для других путей. Data page web-open 403 | API не запрашивался, обходов не было. Median export включает пересчёт обзорных значений; не считать его сырыми замерами |
| [BenchPress Data](https://github.com/sturimcode/benchpress-data) | CC BY 4.0 data, MIT code; публичное дерево GitHub получено | В reports только .gitkeep. Оценочные baselines не импортированы как измерения |
| [TechPowerup32 FPS dataset](https://github.com/TechPowerup32/fps-benchmark-dataset) | MIT, публичный CSV доступен | 188 строк изучены, но нет первичных URL, дат, серии, версии игры, RT/FG/OS; статус measured не подтверждён. В curated data не импортированы. Без доказательств также не объявлены синтетическими |
| [SteamFPS](https://github.com/xpressmike/steamos-playability-dataset) | CC BY 4.0 compilation; NOTICE сохраняет условия upstream-источников | Заявлены 241 community Deck measurement, но отдельные права/семантика upstream и различие target/average FPS не установлены. Не импортирован. Derived verdicts не превращались в FPS |
| [DeckSettings](https://github.com/DeckSettings/game-reports-steamos) | GPL-3.0 repository; отдельный grant для issue submissions не установлен | Шаблон спрашивает target framerate. Это не гарантированный measured average; не импортирован |
| [Kaggle FPS Benchmark](https://www.kaggle.com/datasets/ulrikthygepedersen/fps-benchmark) | Страница без читаемого содержимого, условия датасета не подтверждены | Кандидат. Apache-2.0 лицензия notebook не выдаётся за лицензию датасета. Без авторизации/обходов выгрузка не выполнялась |
| [Hugging Face PCGameBenchmarks](https://huggingface.co/datasets/pcgamebenchmarks/pc-game-system-requirements-fps) | CC BY 4.0, но FPS расчётные | Повторно не импортирован как измерения. Фиксированные 30 FPS в видео-датасетах gameplay также не являются результатом теста GPU |
| [TechSpot / Hardware Unboxed](https://www.techspot.com/review/3109-amd-ryzen-5500x3d/) | Права на импорт не подтверждены; прямой robots-запрос завершился ошибкой проверки TLS | X3D-кандидат без импорта. Один и тот же обзор TechSpot/HU не будет считаться двумя независимыми источниками. TLS не отключался |
| [Gamers Nexus](https://gamersnexus.net/cpus/am4-lives-amd-ryzen-5-5500x3d-cpu-review-benchmarks) | Robots получен, открытая лицензия набора/разрешение копирования графиков не установлены | Кандидат; не применялся OCR/импорт графиков. Simulation time в Stellaris не переводится в FPS |
| [iXBT](https://www.ixbt.com/platform/amd-ryzen-5-5500x3d-review.html) | Robots получен, есть ограничения media paths; разрешение на dataset reuse не установлено | Кандидат X3D, значения не импортированы |
| [ComputerBase](https://www.computerbase.de/) | Robots получен, /api/ закрыт; разрешение нового импорта не подтверждено | Кандидат. Старые legacy-опоры сохранены, но не переобозначены как новый лицензированный training set |

Источники новых данных: **Open GPU Benchmarks — https://opengpubenchmarks.com (CC BY 4.0)** и **TechFuelHQ — ASUS ROG Astral RTX 5080 OC First-Party Bench Dataset — https://techfuelhq.com/data/gpu/rog-astral-rtx-5080-oc-2026-06-09/ (CC BY 4.0)**. Нормализация и объединение повторов выполнены UpgradeLab; источники не заявляются одобряющими проект.

## Состав и происхождение записей

Версионируемый набор: `backend/app/data/benchmarks/measurements.json`.

- `ogb_rtx5080_raw.json`: ответ `https://opengpubenchmarks.com/api/v1/official/rtx_5080_16gb_fe/summary.json`. Используется records (отдельные прогоны), не game_summaries.
- `ogb_steam_machine_raw.json`: аналогичный документированный endpoint для steam_machine_8gb_valve.
- `techfuel_raw.json`: исходный dataset.json v1.4.0. Лицензия сохранена как TECHFUEL_LICENSE.txt. Несовпадение версии на каталожной странице не скрывается: обработана именно скачанная версия JSON.
- Для каждого снимка в normalized manifest записан SHA-256. Raw файлы сохраняют _license/_source или publisher/license/version исходного формата.

Каждая строка содержит игру/версию, точные исходные названия CPU/GPU, RAM/VRAM при наличии, output resolution, preset, RT, upscaling, FG и его режим, render scale при наличии, average FPS, 1% Low, measured/estimated, record_kind, publisher, source URL, source_ids, дату/время либо исходное окно дат, сцену, ОС/драйвер, профиль разгона, серию и уровень подтверждения источником. Неизвестные поля — null, не вымышленные значения.

`raw_run` означает опубликованную сводку одного прогона, а не захваченный нами frametime CSV. `publisher_point` — опубликованная точка с неизвестным количеством повторов. Дата публикации не подставляется как дата теста. RT у Open GPU нормализуется по именованным preset labels: обычные пресеты трактуются как raster, Ray Tracing:* — как RT; правило и ограничение явно записаны в notes. Пустой upscaling у этого источника означает native в его контракте. Для других источников такое правило не применяется.

У TechFuelHQ сохранены manual OC, 64 GB DDR5-6000 и 16 GB VRAM из исходного описания. Версия игры, ОС, драйвер, RAM channels и точная дата не придуманы. Black Myth: Wukong имеет неизвестный render scale. Для части «native» точек неизвестен FG: слово native само по себе не принято за доказательство FG=off.

Повтор Cyberpunk native PT 19 FPS в двух графиках TechFuel объединён; 1% Low 15 FPS сохранён из графика, где он опубликован. Равные значения разных издателей не объединяются автоматически. Разные время/дата, драйвер, RAM и профиль OC не считаются дублями. Конфликтующие 1% Low у повтора вызывают отказ вместо молчаливой подмены.

## Качество и покрытие

| Показатель | Значение |
| --- | --- |
| Наблюдений measured / estimated | 81 / 0 |
| Исходных per-run записей / publisher points | 73 / 8 |
| Конфигураций после объединения повторных прогонов | 72 |
| Уникальных игр | 4 |
| Точных моделей CPU / GPU | 3 / 3 |
| Издателей / серий | 2 / 4 |
| Основные настройки заполнены | 69/81 = 85,19% |
| Есть опубликованный 1% Low | 78/81 |
| Native stock Windows | 4 прогона → 3 конфигурации |
| Native stock Linux с известной сценой | 8 прогонов, отдельная когорта |
| Новых разрешённых измерений CS2 | 0 |
| Контролируемых X3D/non-X3D пар | 0 |
| Исключено синтетических прогонов из полученных per-GPU файлов | 20 |
| Повторных chart points объединено | 1 |

Основная полнота включает version, CPU/GPU, RAM/VRAM, resolution/preset, RT/upscaling/FG, scene и OS. Это не полнота всех аппаратных признаков: Single Thread/L3/архитектура не появились автоматически. Три GPU-модели — RTX 5080 FE, ASUS Astral RTX 5080 OC и Steam Machine; две первые используют один GPU-чип, что дополнительно ограничивает разнообразие.

Отсутствуют: game_version у 8 точек, RAM channels у 8, RT у 1, FG у 4, OS у 8, driver у 42, scene у 6, точная observed_date у 8 (сохраняется предоставленное окно дат). Полнота и большие FPS числа не доказывают независимость или точность.

Игры: Cyberpunk 2077 — 75 наблюдений, Helldivers 2 — 4, Alan Wake 2 — 1, Black Myth: Wukong — 1. Набор сильно перекошен к одной игре и двум аппаратным платформам Open GPU. Четыре series_id — группы публикации/bench/игры/версии, а не четыре независимые лаборатории: два игровых набора используют одну Steam Machine. Разделение по издателям строже этого счётчика.

## X3D: найденные сравнительные публикации

Найдены конкретные кандидаты, но разрешённого импорта их измерений нет:

- 5500X3D / 5600X: [TechSpot](https://www.techspot.com/review/3109-amd-ryzen-5500x3d/), [Gamers Nexus](https://gamersnexus.net/cpus/am4-lives-amd-ryzen-5-5500x3d-cpu-review-benchmarks), [iXBT](https://www.ixbt.com/platform/amd-ryzen-5-5500x3d-review.html).
- 5700X3D / 5700X: [TechSpot 2024](https://www.techspot.com/review/2801-amd-ryzen-5700x3d/); независимый кандидат — [Gamers Nexus 5700X3D](https://gamersnexus.net/cpus/new-amd-ryzen-7-5700x3d-cpu-review-benchmarks-vs-5800x3d-more), состав контрольных CPU нужно проверить по разрешённому экспорту.
- 5800X3D / 5800X: [ComputerBase gaming benchmark](https://www.computerbase.de/artikel/prozessoren/ryzen-7-5800x3d-gaming-benchmark.80191/).

Числа из поисковых сниппетов не заносились в dataset. Для проверки эффекта кеша нужны одинаковые GPU/сцена/build/preset/RAM и подтверждение CPU-bound режима. GPU-bound результаты 4K не позволяют выделить CPU-cache эффект. Стратегии/симуляторы могут измерять simulation time; его нельзя записывать в average FPS.

Пример CS2/X3D сейчас — честный отказ калибровки: нет ни одной допустимой пары, ratio error = n/a. Старые CS2 alias-приближения остаются legacy, а не новым доказанным бонусом. 5500X3D/5600X, 5700X3D/5700X и 5800X3D/5800X не получают постоянного коэффициента из этого исследования.

## Модели и независимая оценка

Разбиение выполняется по издателям; совпадающий series_id также исключается из train. Оба источника заявляют собственные разные bench-системы. Повторы одной серии не попадают по разные стороны split. Будущие перепубликации одного обзора должны иметь общую lineage/series: другое доменное имя само по себе не создаёт независимое измерение.

Для метрик повторные прогоны одной конфигурации сначала усредняются с равным весом. Так два 1440p High прогона 179,71 и 178,55 FPS дают одну точку 179,13 FPS. По средним FPS нельзя восстановить pooled 1% Low: он в оценочном агрегате остаётся неизвестным; исходные значения сохранены в датасете.

| Модель | Реализованное сравнение | Результат |
| --- | --- | --- |
| Legacy | Текущий неизменённый расчёт; exact model match по существующему PassMark, поддерживаемый mode, отдельная stock/native Windows-когорта | 2 конфигурации, эквивалент 3 raw-прогонов |
| Relative transfer | Экспериментальная anchor baseline: FPS_anchor × min(CPU Mark ratio, G3D ratio), только совпадающие условия и другой издатель; диапазон отношений ограничен; перенос X3D между разными CPU запрещён | 0 допустимых anchors. Коэффициент 1 — лишь baseline, не доказанная эквивалентность Mark игровому FPS |
| CPU/GPU frametime | Экспериментальная неотрицательная модель t_ms=a/CPU_Mark+b/G3D_Mark, FPS=1000/t. Проверяется ранг; для каждой группы нужны ≥6 наблюдений, ≥3 значений CPU/GPU, ≥3 серий, ≥2 обучающих издателей и ещё отдельный held-out издатель | На реальном наборе не обучена: требований разнообразия нет. Математический solver проверен на явно синтетических unit fixtures, не включённых в benchmark data |
| Регрессия с игровыми/аппаратными признаками | Кандидат для достаточного набора, обучение не реализовывалось ради формального результата. ST/L3/архитектура не импутируются | Не обучена. Нет достаточных независимых рядов и признаков |

Сравнение на общем support всех четырёх методов: 0 конфигураций. Следовательно, нельзя утверждать, что новая модель лучше legacy; promotion.allowed=false. Производственный движок не заменён, L3/X3D-бонус, новые универсальные коэффициенты, 1% Low-модель не добавлялись.

### Фактические метрики legacy

| Метрика | Значение |
| --- | --- |
| n независимых по настройкам конфигураций | 2; одна аппаратная пара/серия |
| MAE | 86,385 FPS |
| MAPE / MdAPE | 46,559% / 46,559% |
| Покрытие эвристического интервала | 0/2 |
| Покрытие строгой Windows-когорты | 2/3 конфигураций = 66,67% |
| Покрытие всех конфигураций набора | 2/72 = 2,78% |
| Покрытые исходные наблюдения | 3/81 = 3,70% |
| Ошибка X3D-сравнений | n/a, 0 контрольных пар |

Это ограниченная внешняя диагностика одной связки, не глобальная MAE. Per-game/CPU/GPU/resolution/X3D breakdown содержится в evaluation_report.json; отсутствующая группа имеет n=0/null, а не 0 ошибок. Linux, OC, RT и FG не смешивались с Windows/raster. Для новых кандидатов без прогноза MAE/MAPE/MdAPE=null; coverage=0 в существующей когорте, interval coverage не определяется.

### Примеры AAA из измерений

- OGB, RTX 5080 FE / Ryzen 9 9950X3D, Cyberpunk 2.31, native 1080p High: измерено 193,64 FPS; legacy 114, интервал 75–150.
- Та же серия, native 1440p High: среднее двух исходных прогонов 179,13; legacy 86, интервал 60–115.
- TechFuel, Astral 5080 manual OC / 7800X3D, Cyberpunk 4K native PT: 19 average / 15 1% Low. Это RT, другая система и неизвестный build; перенос к raster/stock не выполняется.
- TechFuel, Alan Wake 2 RT + DLSS Quality: 49 average / 38 1% Low. Полный preset и FG неизвестны; это не готовая калибровочная точка.
- TechFuel, Wukong Cinematic 4K output: 34 average / 27 1% Low; внутренний render scale неизвестен, не выдаётся за native.

## Оптимизатор и три режима цен

Offers/reference/hybrid сохранены, дизайн и приоритет hybrid не менялись. Отдельный тест подтвердил:

| Синтетический ассортимент, бюджет 80 000 ₽, цель 400 FPS | Выбор GPU | Плановая сумма | Прогноз legacy |
| --- | --- | --- | --- |
| offers | RX 6600, свежее предложение | 48 500 ₽ | 342 FPS |
| hybrid | RX 6600, приоритет имеющейся реальной категории | 48 500 ₽ | 342 FPS |
| reference | RTX 4060, наблюдение двухдневной давности | 49 500 ₽ | 402 FPS |

Reference-вариант даёт больше модельного FPS и FPS/рубль в бюджете, но не подтверждённую возможность покупки. Hybrid не гарантирует максимум FPS или глобально лучший FPS/рубль: если пригодная реальная GPU-категория существует, старые справочные GPU не допускаются. Политику сознательно не меняли в data-итерации; контрпример закреплён тестом. Возможное будущее решение — показывать Pareto-альтернативы с явным числом справочных позиций и выбором пользователя, а не молча заменять найденное предложение старой ценой.

Числа таблицы — **синтетические тестовые цены и legacy-прогнозы**, не реальные измерения и не магазинные предложения. Артефакт: `.artifacts/benchmark-data/hybrid-counterexample.json`.

Подтверждённый дефект исправлен: при CPU Mark=0 сборщик раньше мог вернуть 1 FPS или опереться на имя CPU. Теперь обе ветви сборки исключают CPU/GPU с неположительным score, текущий апгрейд возвращает понятный отказ, кандидаты также фильтруются. Hardware не удаляется из БД; известная цена не превращает неизвестную производительность в допустимый прогноз. Неподдерживаемые игры/настройки остаются insufficient_data в FPS API. Смысл complete/draft/partial и маркировка исторических цен сохранены.

## Воспроизведение без сети и рабочей БД

```powershell
cd C:\vscode\upgradeLab\backend
$env:DATABASE_URL='sqlite://'
.\.venv\Scripts\python.exe -m scripts.prepare_fps_benchmarks --output ../.artifacts/benchmark-data/reproduced
.\.venv\Scripts\python.exe -m scripts.evaluate_fps --curated
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_benchmark_data.py
```

Default output prepare — versioned app/data/benchmarks. Для read-only воспроизведения используйте приведённый --output. Скрипты не скачивают данные и не открывают SQLite; тест блокирует socket.connect и подключение к основному SQLAlchemy engine. Один и тот же набор файлов воспроизводит measurements.json, quality_report.json и evaluation_report.json побайтово. Исходный evaluate_fps без --curated сохраняет старый отчёт.

Сетевое обновление намеренно не автоматизировано: сначала повторно проверить robots/лицензию, затем получить документированные фиксированные JSON и сохранить их вместе с новыми хэшами/условиями. Произвольные URL в runtime не добавлялись.

## Проверки и файлы

- Новые целевые тесты: 21/21.
- Полная backend-регрессия: 531 total, 529 passed, 2 skipped.
- Frontend: 77/77; production build успешен, CSS/JS assets имеют прежние размеры/хэши этой frontend-версии.
- git diff --check — успешно. Старые DeprecationWarning для datetime.utcnow сохранены, это не новые ошибки тестов.

Файлы этой итерации:

- `backend/app/services/benchmark_data.py`, `benchmark_calibration.py`.
- `backend/scripts/prepare_fps_benchmarks.py`, `evaluate_fps.py`.
- `backend/app/data/benchmarks/`: два raw OGB JSON, raw TechFuel JSON/лицензия, normalized measurements, quality/evaluation reports, sources и source_policies.
- `backend/tests/test_benchmark_data.py`.
- `backend/app/services/builds.py`, `automatic_builds.py`, `backend/app/api/calculate.py`: только подтверждённые проверки допустимости scores.
- Документация: FPS_BENCHMARK_DATA.md, FPS_ENGINE_V2.md, ARCHITECTURE.md, TECHNICAL_AUDIT.md, CHANGELOG_DEV.md, TODO.md.

Список остальных dirty-файлов относится к предыдущим итерациям и не сбрасывался. Frontend source и рабочая БД этой итерацией не менялись.

## Что нужно для следующей калибровки

1. Получить прямое разрешение/экспорт CPU-зависимых X3D-тестов перечисленных изданий; никаких писем или сообщений от имени пользователя не отправлялось.
2. Согласовать небольшой benchmark schema с авторами: game build, сцена, GPU/CPU, RAM, resolution/preset/render scale, RT/upscaling/FG, OC/power, ОС/driver, average/1% Low, run IDs и права.
3. Набрать разные GPU и CPU с контролируемыми X3D/non-X3D парами на CS2, стратегиях/симуляторах и AAA, несколько независимых издателей на одинаковых условиях. Измерить CPU-bound признаки/масштабирование разрешения, а не предполагать их по названию игры.
4. Подтвердить права и происхождение аппаратных Single Thread/architecture/L3/V-Cache признаков. Отсутствующие значения не заменять игровым рейтингом другого сервиса.
5. Только затем обучать кандидаты и сравнивать MAE/MAPE/MdAPE, покрытие и group errors на общих независимых holdouts; отдельно моделировать 1% Low. Не выбирать гиперпараметры на финальном test.

Текущий вывод: больше проверяемых исходных данных получено, но **доказательств для улучшения и включения новой FPS-модели пока нет**.

Предлагаемый коммит: `feat(benchmarks): curate licensed FPS runs and add source-held-out evaluation`.
