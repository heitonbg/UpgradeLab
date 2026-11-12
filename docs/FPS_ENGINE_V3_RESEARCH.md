# FPS Engine v3: исследование и проектные границы

Дата: 2026-11-11. Это исследовательская итерация, не выпуск FPS-модели v3. Production-прогноз остался legacy/v2; новый регрессионный или ML estimator не включён.

## Что фактически делает legacy

`performance.py` применяет `min(CPU_capacity, GPU_capacity) × game/mode overhead`. CPU capacity для большинства игр начинается с CPU Mark и игровых множителей в `GAME_PROFILES`; GPU capacity использует отдельные GPU опоры, опубликованные одиночные GPU chart points, либо G3D Mark. Для CS2 отдельно используются опубликованные CPU/GPU опоры в других условиях и смягчённая кривая для незамеченных CPU/GPU. Это оценка пользовательской пары через перенос результатов, а не замер этой пары.

Для пары без точной игровой опоры FPS получается главным образом из PassMark/G3D Mark и вручную заданных коэффициентов. CPU/GPU ceilings — полезная диагностическая декомпозиция формулы, не измерение bottleneck. Разрешение/пресет принимаются только для явно существующих профилей. Сейчас API поддерживает 1080p Low/High и 1440p High; 4K, Medium/Ultra без опор, RT, upscaling и Frame Generation дают отказ/неподдерживаемый результат. VRAM отображается как характеристика, но надёжной модели VRAM capacity effects нет. Архитектура, Single Thread и L3 в Hardware каталоге недостаточно представлены; фиксированный X3D бонус запрещён.

Все интервалы FPS — широкие эвристические границы, не статистические prediction intervals. 1% Low API возвращает `null`: отдельный estimator не существует.

## Проверенная база

Пересборка через `scripts.evaluate_fps --curated`: 81 нормализованное measured/publisher point, 73 Open GPU Benchmarks runs и 8 TechFuelHQ points; 4 названия игр; 3 CPU, 3 GPU, 2 publisher, 4 серии; 69/81 записей с полными выбранными настройками; 78 записей содержат опубликованный 1% Low. Это описательные totals, не размер калибровочной выборки.

Для строгой независимой оценки native, stock, desktop, Windows, версия игры и точные условия имеются лишь 3 Cyberpunk наблюдения одной CPU/GPU/test series; evaluation группирует повторы в 3 test configurations. Получить независимый publisher holdout нельзя без утечки. Другие записи — Linux (8 native stock points), RT/upscaling/FG, ручной OC или неполные условия; они остаются архивом исследований, а не примешиваются к строгой выборке.

| Источник | Лицензия/доступ | Использование |
| --- | --- | --- |
| [Open GPU Benchmarks](https://opengpubenchmarks.com/), [license](https://opengpubenchmarks.com/license/) | CC BY 4.0; API явно несёт attribution/source metadata | 73 нормализованных raw game runs; использовать только с attribution и условиями. В общей базе не каждый ряд отвечает native Windows cohort. |
| [TechFuelHQ RTX 5080 dataset](https://techfuelhq.com/data/gpu/rog-astral-rtx-5080-oc-2026-06-09/) | Dataset CC BY 4.0; first-party permission/attribution описаны в сохранённых source metadata | 8 точек после дедупликации. Manual OC, неполные OS/build/дата; не годится калибровать stock или X3D. |
| OpenBenchmarking | В сохранённой политике зафиксировано `ai-train=no`; данные и права на импорт не установлены | Не импортировать. Код лицензирован отдельно от пользовательских результатов. |
| FPSHQ | Документация декларирует CC BY 4.0, но `/api/` закрыт robots policy, страница дала 403; экспорт смешивает исходные измерения и rescaling | Не импортировать через запрещённый API или обход. |
| BenchPress Data | Данные CC BY 4.0, код MIT | Проверенный tree содержит только `.gitkeep`; измеренных отчётов нет, baseline помечены estimates. |
| TechPowerup32/fps-benchmark-dataset | CSV repo MIT | 188 строк осмотрены ранее: нет URL измерений, даты, test series, game build и настроек RT/FG/OS; происхождение единиц CPU_Score не раскрыто. Не считать независимыми game measurements. |
| SteamFPS / DeckSettings | CC BY compilation с сохранением upstream rights / права issue submissions не установлены | Deck target FPS не равен измеренному среднему; handheld results нельзя смешивать с Windows desktop. Не импортированы. |
| Kaggle FPS Benchmark | Лицензия датасета не подтверждена | Не скачивался; лицензия ноутбука не является лицензией набора. |
| PCGameBenchmarks (GitHub/Hugging Face/Kaggle) | CC BY 4.0 по карточке/репозиторию | Содержит estimated FPS, а не raw измерения CPU/GPU-пары; исключён из обучения. |
| TechSpot / Hardware Unboxed, Gamers Nexus, iXBT, ComputerBase | Публичные статьи-кандидаты; права на повторное использование таблиц не подтверждены | Ссылки допустимы как ориентиры. Значения не копировались в новый датасет без permission. Синдикация Hardware Unboxed/TechSpot — одна серия, не два независимых источника. |

Ранее зафиксированные URL, robots probes, решения по лицензиям, X3D-кандидаты и SHA находятся в `backend/app/data/benchmarks/{sources.json,source_policies.json}`. Отсутствие импорта — соблюдение границы разрешённого использования, не пробел, который можно закрыть scraping-ом.

## X3D, RAM и условия измерений

В 81 rows есть только 3 названия CPU в полном архиве, но нет независимых X3D/non-X3D пар одинаковой игры, GPU, версии, сцены и настроек. Следовательно, для Ryzen 5 5500X3D/5600X, 5700X3D/5700X и 5800X3D/5800X неизвестны отдельные калиброванные эффекты. CS2 опоры из ComputerBase — опубликованные условия 2023/RTX 4090/720p для CPU и 1080p Medium для GPU, тогда как пользовательский режим Low. Они дают переносимое относительное сравнение с пометкой, но не X3D contrast для идентичной системы.

Дополнительное исследование публикаций нашло прямые 5500X3D comparisons, не включённые в лицензированный machine-readable архив. В [TechSpot April 2026](https://www.techspot.com/review/3109-amd-ryzen-5500x3d/) 14-game average для Ryzen 5 5500X3D был на 13–15% выше Ryzen 5 5600X, но по отдельным CPU-sensitive играм результат менялся: около паритета в Rainbow Six Siege X, примерно +15% Battlefield 6, +30% Arc Raiders Medium / +18% Epic, +28% Baldur's Gate 3 и +18% CS2 Medium / +14% Very High. Этот же обзор сообщает около +8% в Cyberpunk Phantom Liberty Medium и +12% с RT. Система использовала RTX 5090 OC и разные тестовые платформы памяти/CPU поколений; числа нельзя прямо переносить на Regard-конфигурации с RTX 3060 Ti/DDR4-2400 или считать универсальным бонусом.

Отдельный [GamersNexus review](https://gamersnexus.net/cpus/am4-lives-amd-ryzen-5-5500x3d-cpu-review-benchmarks) тоже показывает зависящие от игры отношения: например, Dragon's Dogma 2 95 FPS average для 5500X3D против 108 для 5800X3D; Baldur's Gate 3 102 FPS average и 19% разницы до 5800X3D. Это отдельная издательская test series, а не совместимый train/test ряд с TechSpot.

Эти проценты используются здесь только для качественного вывода о взаимодействии game × CPU/cache × settings. Значения статей не были скопированы в `measurements.json` или использованы для обучения: права на повторное использование chart data не подтверждены; не все сцены/OS/game build/RAM условия доступны в структурированном разрешённом экспорте. См. лицензии и import decisions в таблице выше.

В imported dataset `ram_channels` отсутствует в 8 TechFuel rows. Не известны в достаточной мере CL/тайминги, rank, слотное расположение и стабильная связь между указанной общей ёмкостью и каналами. Текущий RAM multiplier в legacy (`.93` для одноканального CS2; +5% DDR4 dual; DDR5 base +8% и dual ещё +3%) — прежняя эвристика, не калиброванный эффект и не новый результат этого исследования. Она не может поддержать точную FPS цифру или доказать пользу конкретного RAM комплекта.

Для 1% Low одна лишь средняя FPS недостаточна. PresentMon выдаёт frame presentation/display timing events; CapFrameX анализирует исходные frame times. В CapFrameX варианты `P1` и `1% low average` имеют различную методику (включая суммарное время худших кадров), поэтому готовые 1% Low разных издателей нельзя автоматически считать одной метрикой. Raw frametimes в текущих импортированных записях отсутствуют; 1% Low остаётся `null` в пользовательском прогнозе.

Primary references: [Intel PresentMon source](https://github.com/GameTechDev/PresentMon), [CapFrameX frametime statistic implementation](https://github.com/CXWorld/CapFrameX/blob/master/source/CapFrameX.Statistics.NetStandard/FrametimeStatisticProvider.cs), [CapFrameX explanation of low-frame metric](https://www.capframex.com/news/detail/New%20version%201.5.3), [NVIDIA FrameView guide](https://www.nvidia.com/content/dam/en-zz/Solutions/GeForce/technologies/frameview/FrameView_Beta_User_Guide.pdf).

## Рассмотренные модели

| Кандидат | Статус |
| --- | --- |
| Legacy PassMark/game-profile baseline | Сохранён в production с legacy/heuristic labels; это baseline, точность не универсальна. |
| GPU-relative transfer | Есть существующие GPU опоры и CS2 относительные reference; valid matching и перенос ограничены, это не новая обученная модель. |
| CPU/GPU frametime: `t = a/CPU + b/GPU` | Алгоритм offline evaluation существует. Число допустимых cross-publisher cohorts недостаточно, ни одного fold не обучено. |
| Regularized regression | Не обучалась: нет независимого объёма/разнообразия и признаков CPU architecture/cache/RAM для безопасной оценки. |
| Gradient boosting | Не обучался; 3 строго оценимые конфигурации совершенно недостаточны. Не добавлялись библиотеки. |
| Hierarchical transfer | Offline anchor baseline abstains on mismatched series/settings and X3D; common independent support — 0. |

Продуктовый FPS API не переводился на v3. Импортировался **0 новых бенчмарков** в этой итерации. Новое значение в датасете без доступа, лицензии, source/test-series и условий дало бы ложное увеличение объёма.

## Следующие данные, которые разблокируют обучение

Нужен разрешённый машиночитаемый набор с несколькими CPU и GPU внутри одной серии, одинаковыми game build/scenes/settings/OS/driver/RAM, отдельными native/RT/upscaling/FG cohorts, raw frametimes/явным определением 1% Low и правом на повторное использование. Для X3D нужны попарные контролируемые CPU contrasts в CPU-limited играх (CS2, стратегия/симулятор) и GPU-limited AAA, включая RAM/BIOS настройки. До такого набора продвигать v3 нельзя.

