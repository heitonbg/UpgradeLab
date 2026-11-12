# Редизайн UpgradeLab — итерация 12

Дата: 10.11.2026. Визуальное направление проверено по предоставленному `.design/upgradeLab_concept.png`; цифры/товары референса не использованы как данные.

## Изменения продукта

Вместо постоянной боковой панели и бежевого акцента — компактная горизонтальная навигация и графитово-синяя система. Добавлена настоящая главная с оригинальным изображением ПК, рабочими переходами в сборку/апгрейд/поиск/биржу. Восемь категорий ведут в соответствующий поиск.

Главная `?tab=home`; конфигуратор `?tab=calculator&scenario=build`; апгрейд — тот же calculator с scenario=upgrade; поиск `?tab=search`; биржа `?tab=marketplace`; вход/регистрация/профиль `?tab=account`. Это существующее SPA с состояниями, не новый серверный router. Восстановление по существующему hash token сохранено. Настоящая главная до итерации отсутствовала.

Изменена композиция конфигуратора: строки восьми деталей, собственные category thumbnails, правая sticky сводка. Существующий выбор варианта, ручные детали и сравнение цен сохранены. Апгрейд использует прежние шаги и расчёт; график показывает только полученные backend FPS. Поиск выделен в отдельный раздел, имеет работающую сортировку, фильтры, город, источники и readable empty/error/outcome.

Биржа визуально соединена с сервисом, фото не обрезают товар. Декоративные картинки имеют явную маркировку, источник доверия и даты продавца сохранены. Форма разделена на секции с прогрессивным раскрытием и preview; старые объявления, contacts/photos, категории, delivery, статусы, dirty guard не удалены. Длинные списки рендерятся порциями по 24.

Профиль/авторизация/восстановление/настройки оформлены в общей системе. Сохранения показывают три разные стоимости. Кнопка «Создать новый расчёт» вызывает существующий POST /api/builds с config и сохраняет исходную историю; ошибки не удаляют старую сборку. Удаление сохранения запрашивает подтверждение. Из скрытого конфигуратора убран дублирующий SavedBuilds widget; на него ведёт рабочая кнопка профиля.

## Ассеты и воспроизведение

Десять оригинальных raster-визуалов: desktop/mobile PC и восемь категорий. Подготовлены 30 WebP и собственный SVG placeholder. Файлы реально подключены к React, srcset/sizes и fixed dimensions заданы, hero high priority, категории lazy. Происхождение/размеры: ASSET_LICENSES.md и frontend/public/images/hardware/manifest.json. Оптимизатор: tools/optimize_assets.py; Pillow — отдельный dev-инструмент (tools/requirements-assets.txt), не зависимость backend production.

Скриншоты до/после лежат в игнорируемых `.artifacts/ui-before` / `.artifacts/ui-after`. UI проверен локальным Edge с мок API; внешние URL блокируются. Реальный XLSX проверяется отдельно, не подменяет frontend fixtures. В production seed не добавлялись демонстрационные цены, предложения или FPS.

## Файлы этой итерации

- Backend: app/services/regard_feed.py, catalog_files.py, catalog_import.py, catalog_access.py; app/schemas/catalog.py; scripts/regard_feed.py, import_catalog.py; tests/test_regard_feed.py (пути относительно backend).
- Frontend shell/pages: src/App.jsx, src/main.jsx, src/index.css, src/redesign.css, src/components/HomePage.jsx, CategoryImage.jsx, PriceOriginBadge.jsx, StoreOffers.jsx; tailwind.config.js, package.json.
- Конфигуратор: src/components/calculator/BuildSection.jsx, BuildSummary.jsx, CalculatorResult.jsx, FpsComparison.jsx; src/lib/fpsChart.js, fpsChart.test.js, catalogView.js, catalogView.test.js.
- Биржа/профиль/UI: src/components/marketplace/ListingForm.jsx, ListingCard.jsx, ListingGrid.jsx, ListingPhoto.jsx; src/components/saved/AccountBuilds.jsx; src/components/ui/Icon.jsx, HardwareSearch.jsx.
- Локальные изображения: frontend/public/images/hardware/*.webp, placeholder.svg, manifest.json.
- Инструменты: tools/optimize_assets.py, requirements-assets.txt, regard_daily_preview.ps1, regard_daily.example.json.
- Документы: REGARD_REAL_FEED.md, REDESIGN_2026.md, DESIGN_SYSTEM.md, ASSET_LICENSES.md, UI_VISUAL_AUDIT.md, ARCHITECTURE.md, TECHNICAL_AUDIT.md, PRICE_FEED_IMPORT.md, TODO.md, CHANGELOG_DEV.md.

До задачи рабочее дерево уже содержало изменения итераций 9–11. Они не сбрасывались; git diff от HEAD включает и прежнюю работу.

## Сохранённые ограничения

Формулы FPS/bottleneck, CPU compatibility, TTL/UTC, auth hashing/rate limits, cookie-сессии и права владельца не переписаны. Реальные товарные фото/остатки/доставка не выдуманы. Ни оплаты, ни резервирования, ни новой площадки не добавлено. Storefront real-feed публикация остаётся выключенной.

Проверки, performance measurements и оставшиеся ограничения описаны в UI_VISUAL_AUDIT.md. Коммит/push/deployment не выполнялись. Два предлагаемых коммита: `feat(catalog): add private native Regard feed analysis and daily diff` и `feat(ui): redesign UpgradeLab with responsive hardware assets`.

Из общего поиска motherboard/RAM/SSD/PSU/case/cooler переносятся в существующую ручную форму с offer_id и scope; остальные детали заполняются пользователем. CPU/GPU предлагают перейти к парным вариантам, без обещания закрепить один SKU. Сервер определяет актуальную цену и совместимость.
