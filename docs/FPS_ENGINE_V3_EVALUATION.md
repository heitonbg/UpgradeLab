# FPS Engine v3: воспроизводимая оценка

Дата: 2026-11-11. Production candidate не продвигался. Результат ниже воспроизводится локально и не трактует отсутствие prediction как нулевую ошибку.

## Запуск

```powershell
cd C:\vscode\upgradeLab\backend
.\.venv\Scripts\python.exe -m scripts.evaluate_fps --curated
```

Измерения и источники: `app/data/benchmarks/measurements.json`, `sources.json`, `source_policies.json`. Importer валидирует provenance, дедуплицирует повтор источника и группирует test series целиком. Fold исключает publisher, а практически одинаковые series не разделяются между train и test.

Полный JSON результат этого запуска: [fps-evaluation-final.json](../.artifacts/product-readiness-20261111/fps-evaluation-final.json) (локальный артефакт).

## Размер и независимость данных

| Метрика | Результат |
| --- | ---: |
| Нормализованные observations | 81 |
| Raw runs / publisher points | 73 / 8 |
| Игры / CPU / GPU | 4 / 3 / 3 |
| Издатели / серии | 2 / 4 |
| Полные условия (строгий словарь полей) | 69/81 = 85.2% |
| Строки с издательским 1% Low | 78 |
| Native, stock, Windows, desktop observations до группировки | 4 |
| Строгие test configurations после дедупликации | 3 |
| X3D/non-X3D controlled pairs | 0 |

Состав архивных игр: Cyberpunk 2077 — 75, Helldivers 2 — 4, Alan Wake 2 — 1, Black Myth: Wukong — 1. Большинство — одна RTX 5080/9950X3D линия, а не разнообразная панель. Четыре native Windows rows сворачиваются evaluation policy в три настройки одной publisher/test series. В независимый holdout не попадает ни одна сопоставимая test series.

## Сравнение моделей

Одинаковые leakage-safe publisher folds. Test denominator для всей строгой выборки — 3 конфигурации.

| Модель | Предсказаний | MAE | MdAPE | MAPE | P90 abs err | Интервал | Coverage выборки |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| Legacy v2 (на двух поддержанных точках внешней диагностики) | 2 | 86.385 FPS | 46.56% | 46.56% | н/д (n=2) | 0/2 покрыто; границы эвристические | 2/3 (66.7% строго доступных points; 2.8% всех конфигураций) |
| Relative transfer | 0 | н/д | н/д | н/д | н/д | не калибровался | 0 |
| CPU/GPU frametime | 0 | н/д | н/д | н/д | н/д | не калибровался | 0 |
| Regularized regression | 0 | н/д | н/д | н/д | н/д | не обучалась | 0 |
| Gradient boosting | 0 | н/д | н/д | н/д | н/д | не обучался | 0 |

Legacy points: RTX 5080 / Ryzen 9 9950X3D Cyberpunk 2077 1080p High: measured 193.64, estimate 114, abs error 79.64; 1440p High: 179.13 vs 86, abs error 93.13. 4K отсутствовал в API/legacy profile. Обе точки — одна серия, так что это диагностический пример крупного расхождения, не независимая оценка общей accuracy. Вынесенный отдельно summary ранее даёт те же MAE/MAPE на двух наблюдениях.

`common_support_all_models=0`. Нельзя честно сравнить MAE новых моделей на тех же held-out рядах: новый кандидат не имеет ни одного валидного prediction. Для групп по играм/CPU/GPU/разрешению X3D-метрики не публикуются, когда `n=0`; x3d group observations не создают paired comparison.

## Проверки 1% Low и uncertainty

Из 81 записей 78 содержат издательский 1% Low, но это не обеспечивает одинаковую семантику или raw per-frame data; часть точек имеет OC/RT/FG/неполные условия. Evaluation усредняет повторные captures одинаковой конфигурации с равным весом, но не усредняет их percentiles. Для объединённой записи `one_percent_low=null`. Production 1% Low остаётся `null` для всех прогнозов. Улучшения 1% Low нет и не заявляется.

Coverage существующего интервала — 0/2 диагностических точек. Legacy interval — фиксированное эвристическое расширение, не prediction interval. Никакая новая модель не прошла calibration/coverage check. P90 absolute error на n=2 не считается доказательной и оставлен `н/д`.

## Пригодность к production

**Нет. FPS Engine v3 небезопасно включать как новую модель.** Legacy сохраняется только с текущими метками/ограничениями; новая модель не заменяет его и не получает дополнительную точность на основании synthetic/PassMark/FPS-calc данных. Для неподдержанных условий правильный ответ — `null/insufficient_data`, а не extrapolated 4K, RT, DLSS/FSR, FG или 1% Low.

Оптимизатор по-прежнему располагает legacy heuristic FPS, поэтому его target gating имеет эти же ограничения. В CPU-work режиме исправлено отдельно: API больше не выдает игровое число, рассчитанное для случайной пары CPU/GPU; поле FPS равно `null`.

