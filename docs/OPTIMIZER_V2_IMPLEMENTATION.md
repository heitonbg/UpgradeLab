# Gaming Optimizer V2: implementation and evidence

Дата: 2026-11-12. Проверки выполнялись на отдельной копии `.artifacts/product-readiness-20261111/pc_upgrade_v2.db`; рабочая SQLite не открывалась для записи. Сетевые предложения, импорт, Regard sync, OpenRouter и платный поиск в прогонах выключены.

## Что изменено

### RAM candidates

Старый `shortlist(..., 6)` удалял 2×8 GB комплекты до расчёта полной сборки. Теперь `memory_shortlist` оставляет до 32 недоминируемых вариантов с разной ёмкостью, числом модулей, известной скоростью и стоимостью. Категория RAM пропускается через полный бюджет, а окончательное ограничение выполняется по цене всей сборки; доля RAM не отсекает хорошие варианты заранее.

Скорость извлекается только из явного атрибута или названия. Неизвестное значение остаётся `null` и не трактуется как медленное/быстрое. Кандидат 2×N из одного одиночного SKU добавляется только если импорт явно сообщает `availability=in_stock` и `quantity >= 2`; цена умножается на два, в ответе сохраняется ID исходной позиции и предупреждение, что это два отдельных модуля, не заводской комплект. Свободные модули из двух независимых строк не объединяются: текущая модель каталога не гарантирует общую поставку, согласование таймингов и вторую ссылку на покупку.

Для RAM в сборке отдельно возвращаются ёмкость, число модулей, известная скорость и `dual_channel_potential`. Это только возможность при поддержке платы/контроллера, не обещание включённого режима и не FPS-бонус. Legacy FPS estimate больше не корректируется на single/dual-channel.

В рамках одной пары CPU/GPU solver сравнивает RAM-кандидаты на той же плате, SSD и корпусе. Performance и Balanced выбирают максимальную RAM quality (скорость разрешает ничью), Economy — минимальную стоимость. Balanced по всей сборке максимизирует минимум нормированных CPU, GPU и RAM признаков, затем общий proxy score и меньшую цену. Это не оставляет автоматический выбор на CPU Mark multi-core разрыве, когда GPU является более слабой частью. Board/SSD/case candidates по-прежнему обязаны проходить совместимость; неизвестные VRM, число слотов и параметры платы не выдумываются.

### CPU/GPU quality and objectives

Для автоматического игрового подбора введён **hardware quality proxy**, независимый от FPS:

```text
CPU_norm = empirical percentile of PassMark CPU Mark among positive-score CPUs for this socket
GPU_norm = empirical percentile of PassMark G3D among positive-score desktop GPUs
RAM_quality = sqrt(capacity_norm × module_count/2)
hardware_quality = cube_root(CPU_norm × GPU_norm × RAM_quality)
```

Percentile (доля каталожных записей с баллом не выше текущего) смягчает использование многопоточного CPU Mark как игрового признака: абсолютный разрыв CPU Mark не трактуется как пропорциональный разрыв FPS. `capacity_norm` ограничен 32 GB и пользовательским минимумом; скорость остаётся отдельным полем и разрешает ничью при выборе RAM, не получает выдуманного процента игровой прибавки. Ранги строятся по локальному Hardware-каталогу, а не по доступным ценам, поэтому offer/reference/hybrid используют одну шкалу.

- **Performance**: максимальный hardware quality среди полных сборок в бюджете; target FPS не является стоп-условием.
- **Balanced**: максимальный weakest-link score `min(CPU_norm, GPU_norm, RAM_quality)`, затем общий геометрический hardware proxy и меньшая цена при равенстве.
- **Economy**: минимальная цена полной сборки; неподтверждённый FPS не доказывает достижение target.

Это новая объявленная функция выбора на синтетических аппаратных показателях, а не калиброванная модель игровой производительности. Названия/числа PassMark не эквивалентны FPS. CPU Mark multi-core не даёт single-thread/X3D игровой зависимости.

В авто-сборке legacy FPS остаётся только отдельно помеченным ориентиром; диапазон и `target_reached` не управляют выбором, `target_reached=null` означает, что полная конфигурация не подтверждена игровыми замерами. Для ручных и legacy-путей сохранено прежнее поведение.

## Математическая проверка

`backend/tests/test_optimizer_v2_oracle.py` задаёт маленький исчерпывающий набор допустимых полных конфигураций. Production `build_options` сравнивается с oracle для Performance, Balanced и Economy и для economy с недостижимой целью FPS. Тесты также проверяют RAM-kit parsing, Pareto-разнообразие, отсутствие выдуманных модулей, подтверждённое количество товара, разные RAM choices для разных objectives и nullable target status.

Результаты: 600 backend tests, 598 passed / 2 skipped; frontend 101/101; production build successful; real Edge E2E 10/10 in 165.207 s; `git diff --check` clean apart from Git LF→CRLF informational warnings.

## Regard staging matrix: before / after

Использованы те же 25 запросов из `.artifacts/product-readiness-20261111/gaming-matrix-current.json`: 5 бюджетов × 5 профилей. Новый ответ и время каждого расчёта сохранены в `.artifacts/product-readiness-20261111/gaming-matrix-v2.json`. Все расчёты локальные, только на staging-копии.

| Бюджет | Профиль | Было CPU / GPU / RAM | Стало CPU / GPU / RAM | Цена до → после |
|---:|---|---|---|---|
| Бюджет | Профиль | CPU до → после | GPU до → после | RAM до → после | Цена до → после | Остаток после |
|---:|---|---|---|---|---:|---:|
| 50 000 ₽ | competitive_1080p | AMD Ryzen 3 3200G → AMD Ryzen 5 4500 | GeForce GT 1030 → GeForce GTX 750 | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) → Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) | 47 620 → 50 000 ₽ | 0 ₽ |
| 50 000 ₽ | aaa_1080p | AMD Ryzen 3 3200G → AMD Ryzen 5 4500 | GeForce GT 1030 → GeForce GTX 750 | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) → Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) | 47 620 → 50 000 ₽ | 0 ₽ |
| 50 000 ₽ | aaa_1440p | AMD Ryzen 3 3200G → AMD Ryzen 5 4500 | GeForce GT 1030 → GeForce GTX 750 | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) → Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) | 47 620 → 50 000 ₽ | 0 ₽ |
| 50 000 ₽ | balanced_gaming_work | AMD Ryzen 5 4500 → AMD Ryzen 5 5600 | GeForce GT 730 → GeForce GT 610 | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) → Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) | 49 770 → 49 670 ₽ | 330 ₽ |
| 50 000 ₽ | cpu_intensive_gaming | AMD Ryzen 3 3200G → AMD Ryzen 5 4500 | GeForce GT 1030 → GeForce GTX 750 | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) → Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) | 47 620 → 50 000 ₽ | 0 ₽ |
| 80 000 ₽ | competitive_1080p | AMD Ryzen 5 5600 → AMD Ryzen 7 5700X | GeForce RTX 2060 SUPER → GeForce GTX 1660 SUPER | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) → Оперативная память 16GB DDR4 3200MHz Patriot Signature (PSD416G3200K) (2x8GB KIT) | 79 760 → 78 960 ₽ | 1 040 ₽ |
| 80 000 ₽ | aaa_1080p | AMD Ryzen 3 3200G → AMD Ryzen 7 5700X | GeForce RTX 2060 SUPER → GeForce GTX 1660 SUPER | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) → Оперативная память 16GB DDR4 3200MHz Patriot Signature (PSD416G3200K) (2x8GB KIT) | 73 130 → 78 960 ₽ | 1 040 ₽ |
| 80 000 ₽ | aaa_1440p | AMD Ryzen 5 4500 → AMD Ryzen 7 5700X | GeForce RTX 2060 SUPER → GeForce GTX 1660 SUPER | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) → Оперативная память 16GB DDR4 3200MHz Patriot Signature (PSD416G3200K) (2x8GB KIT) | 76 700 → 78 960 ₽ | 1 040 ₽ |
| 80 000 ₽ | balanced_gaming_work | Intel Core i7-13700KF → Intel Core i7-13700KF | GeForce GT 610 → GeForce GT 610 | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) → Оперативная память 16GB DDR4 3200MHz Digma (DGMAD43200016D) | 76 960 → 78 520 ₽ | 1 480 ₽ |
| 80 000 ₽ | cpu_intensive_gaming | AMD Ryzen 5 5600 → AMD Ryzen 7 5700X | GeForce RTX 2060 SUPER → GeForce GTX 1660 SUPER | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) → Оперативная память 16GB DDR4 3200MHz Patriot Signature (PSD416G3200K) (2x8GB KIT) | 79 760 → 78 960 ₽ | 1 040 ₽ |
| 120 000 ₽ | competitive_1080p | Intel Core i5-12600KF → AMD Ryzen 7 5700X | GeForce RTX 3060 Ti → GeForce RTX 3070 Ti | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) → Оперативная память 16GB DDR4 3600MHz Netac Shadow S White (NTSSD4P36DP-16W) (2x8GB KIT) | 98 180 → 110 910 ₽ | 9 090 ₽ |
| 120 000 ₽ | aaa_1080p | AMD Ryzen 5 3400G → AMD Ryzen 7 5700X | GeForce RTX 3070 Ti → GeForce RTX 3070 Ti | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) → Оперативная память 16GB DDR4 3600MHz Netac Shadow S White (NTSSD4P36DP-16W) (2x8GB KIT) | 97 040 → 110 910 ₽ | 9 090 ₽ |
| 120 000 ₽ | aaa_1440p | AMD Ryzen 5 4500 → AMD Ryzen 7 5700X | GeForce RTX 3070 Ti → GeForce RTX 3070 Ti | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) → Оперативная память 16GB DDR4 3600MHz Netac Shadow S White (NTSSD4P36DP-16W) (2x8GB KIT) | 98 270 → 110 910 ₽ | 9 090 ₽ |
| 120 000 ₽ | balanced_gaming_work | Intel Core i9-13900KF → AMD Ryzen 9 9950X | GeForce GT 610 → GeForce GT 1030 | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) → Оперативная память 16GB DDR5 5600MHz Patriot Signature (PSD516G5600K) (2x8GB KIT) | 86 790 → 115 680 ₽ | 4 320 ₽ |
| 120 000 ₽ | cpu_intensive_gaming | Intel Core i5-12600KF → AMD Ryzen 7 5700X | GeForce RTX 3060 Ti → GeForce RTX 3070 Ti | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) → Оперативная память 16GB DDR4 3600MHz Netac Shadow S White (NTSSD4P36DP-16W) (2x8GB KIT) | 98 180 → 110 910 ₽ | 9 090 ₽ |
| 150 000 ₽ | competitive_1080p | Intel Core i5-14600KF → AMD Ryzen 9 5950X | GeForce RTX 3070 → GeForce RTX 3070 Ti | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) → Оперативная память 16GB DDR4 4600 MHz Kingston Fury Renegade RGB (KF446C19RB2AK2/16) (2x8GB KIT) | 109 990 → 149 500 ₽ | 500 ₽ |
| 150 000 ₽ | aaa_1080p | AMD Ryzen 5 3400G → AMD Ryzen 9 5950X | GeForce RTX 3080 → GeForce RTX 3070 Ti | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) → Оперативная память 16GB DDR4 4600 MHz Kingston Fury Renegade RGB (KF446C19RB2AK2/16) (2x8GB KIT) | 123 010 → 149 500 ₽ | 500 ₽ |
| 150 000 ₽ | aaa_1440p | AMD Ryzen 5 5500 → AMD Ryzen 9 5950X | GeForce RTX 3080 → GeForce RTX 3070 Ti | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) → Оперативная память 16GB DDR4 4600 MHz Kingston Fury Renegade RGB (KF446C19RB2AK2/16) (2x8GB KIT) | 126 350 → 149 500 ₽ | 500 ₽ |
| 150 000 ₽ | balanced_gaming_work | AMD Ryzen 9 9950X3D → AMD Ryzen 9 9950X3D | GeForce GT 610 → GeForce GT 610 | Оперативная память 16GB DDR5 4800MHz KingSpec (KS4800D5P11016G) → Оперативная память 16GB DDR5 6000MHz Patriot Viper Venom RGB (PVVR516G600C36K) (2x8GB KIT) | 128 400 → 137 560 ₽ | 12 440 ₽ |
| 150 000 ₽ | cpu_intensive_gaming | Intel Core i5-14600KF → AMD Ryzen 9 5950X | GeForce RTX 3070 → GeForce RTX 3070 Ti | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) → Оперативная память 16GB DDR4 4600 MHz Kingston Fury Renegade RGB (KF446C19RB2AK2/16) (2x8GB KIT) | 109 990 → 149 500 ₽ | 500 ₽ |
| 200 000 ₽ | competitive_1080p | Intel Core i5-14600KF → AMD Ryzen 9 5950X | GeForce RTX 3080 → GeForce RTX 5070 | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) → Оперативная память 16GB DDR4 3600MHz Netac Shadow S White (NTSSD4P36DP-16W) (2x8GB KIT) | 140 260 → 195 360 ₽ | 4 640 ₽ |
| 200 000 ₽ | aaa_1080p | AMD Ryzen 5 4500 → AMD Ryzen 9 5950X | GeForce RTX 5070 → GeForce RTX 5070 | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) → Оперативная память 16GB DDR4 3600MHz Netac Shadow S White (NTSSD4P36DP-16W) (2x8GB KIT) | 153 700 → 195 360 ₽ | 4 640 ₽ |
| 200 000 ₽ | aaa_1440p | AMD Ryzen 5 5500 → AMD Ryzen 9 5950X | GeForce RTX 3080 → GeForce RTX 5070 | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) → Оперативная память 16GB DDR4 3600MHz Netac Shadow S White (NTSSD4P36DP-16W) (2x8GB KIT) | 126 350 → 195 360 ₽ | 4 640 ₽ |
| 200 000 ₽ | balanced_gaming_work | AMD Ryzen 9 9950X3D → AMD Ryzen 9 9950X3D | GeForce GT 610 → GeForce GT 610 | Оперативная память 16GB DDR5 4800MHz KingSpec (KS4800D5P11016G) → Оперативная память 32GB DDR5 8000MHz KingBank KFXB (K5.01.FPA5KD9501) (2x16GB KIT) | 128 400 → 165 000 ₽ | 35 000 ₽ |
| 200 000 ₽ | cpu_intensive_gaming | Intel Core i5-14600KF → AMD Ryzen 9 5950X | GeForce RTX 3080 → GeForce RTX 5070 | Оперативная память 16GB DDR4 2400MHz ExeGate HiPower (EX288045RUS) → Оперативная память 16GB DDR4 3600MHz Netac Shadow S White (NTSSD4P36DP-16W) (2x8GB KIT) | 140 260 → 195 360 ₽ | 4 640 ₽ |

Ключевой сценарий 120 000 ₽ / RDR2: Ryzen 5 4500 → Ryzen 7 5700X; RTX 3070 Ti сохранена; 1×16 GB DDR4-2400 → комплект 2×8 GB DDR4-3600. Полная цена 98 270 → 110 910 ₽, остаток 21 730 → 9 090 ₽. Legacy estimate обоих вариантов около 88 FPS и не является измерением; `target_reached=null`. Выбор balanced объясняется более ровными catalog-percentile CPU/GPU/RAM. Перед покупкой всё ещё нужно проверить BIOS, реальные DIMM slots/XMP и размеры. Другие варианты CPU/GPU остаются отдельными карточками.

На этом же запросе objective даёт разные результаты: Balanced — Ryzen 7 5700X + RTX 3070 Ti за 110 910 ₽; Performance по геометрическому proxy — Ryzen 9 5950X + RTX 2060 SUPER за 118 360 ₽; Economy — Ryzen 3 3200G + GT 610 за 46 730 ₽. Вариант Performance может выглядеть странно для игры: multi-core CPU Mark даёт больший percentile вклад, хотя G3D слабее. Мы открыто выводим метрики отдельно; улучшение измеренного игрового FPS не доказано.

## Solver coverage, runtime and memory

Solver remains bounded by configured CPU/GPU caps and profile time limit. `global_optimum_proven` remains false. Supporting parts are assembled and checked against the complete budget, but current solver does not enumerate every motherboard/case/PSU/cooler permutation as an independent final result; it chooses compatible support candidates and optimizes RAM within the chosen board/SSD/case composition. Unknown board VRM, DIMM slots and memory-channel topology remain unknown.

Runtime for final 25-case run: 171.99 s total, p50 6.645 s, p95 10.269 s, maximum 10.958 s; all 25 API calls returned HTTP 200. Matrix TestClient peak RSS was not sampled. During the real Edge E2E workload, the isolated backend process peaked at 164.1 MiB working set / 144.9 MiB private bytes (100 ms sampling); this is a browser-run smoke figure, not a load-limit guarantee.

## FPS Engine evidence limits

FPS V3 is not enabled. The curated dataset and evaluation remain in [FPS benchmark data](FPS_BENCHMARK_DATA.md), [V3 research](FPS_ENGINE_V3_RESEARCH.md) and [V3 evaluation](FPS_ENGINE_V3_EVALUATION.md). The current catalog has insufficient independent, comparable CPU/GPU/game/configuration test series for validated CPU-bound and X3D predictions. Keep `fps_outlook` as a disclosed estimate; do not label proxy scores as measured FPS or claim target attainment.

## Confirmed changes versus remaining hypotheses

Confirmed by code/tests: RAM kits no longer disappear behind the six-cheapest cutoff; complete-build budget gates RAM; the three objectives execute separate ranking rules; automatic gaming selection no longer depends on legacy FPS/target; CPU/GPU/RAM proxy dimensions are returned separately; unknown data remains unknown; explicit stock quantity is required before creating a two-stick composition.

Not yet proven: that this hardware proxy improves real game FPS; that catalog PassMark entries accurately reflect a particular board BIOS/VRM configuration; that two sticks train at advertised XMP speed; and that the bounded solver reaches a global optimum on full Regard inventory. Do not promote those claims without independent tests.
