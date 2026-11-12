# Аудит согласованности интерфейса UpgradeLab

Дата: 2026-11-10. Работа выполнена поверх незакоммиченных предыдущих итераций. Commit, push, deployment не выполнялись. Backend, рабочая БД, товарные адаптеры и правила достоверности цен этой итерацией не изменялись.

## Причины и исправления

`index.css` и `redesign.css` содержали конкурирующие слои: соответственно 439 и 93 различных HEX. Поздний слой редизайна перекрывал лишь часть прежних поверхностей, выделений, focus и сообщений. Все цветовые литералы этих файлов переведены на общие токены; старые декоративные коричневые градиенты убраны. Единственный источник палитры — `frontend/src/tokens.css` (21 цвет); прозрачности используют RGB-производные тех же значений. Tailwind ссылается на эти переменные. Предупреждения о неподтверждённых ценах остаются янтарными, ошибки красными, успех зелёным. Изображения товаров не перекрашивались.

Общий Button поддерживает primary, secondary, outline, ghost, destructive/danger и iconOnly, loading/disabled/focus. Основная высота кнопок и полей 44 px, радиус 6 px. Общие input/select/textarea имеют единые фон, границы, placeholder, validation и focus. Нативные select/datalist сохранены с настоящими обработчиками.

Биржа: sidebar 300 px (280 px на промежуточной ширине); «Все объявления» занимает строку, «Продажа» и «Обмен» следующую; счётчики читаемы. Поля цены одинаковой ширины, неверный диапазон отмечается явно. На ширинах до 800 px фильтры раскрываются кнопкой. Общий ErrorState использует нейтральную поверхность, небольшой красный значок, короткое описание и рабочий retry.

Причина ложного «Найдено 0»: пустой начальный массив использовался как успешный результат даже при ошибке. Теперь loading / refreshing / empty / error / partial / success различаются; неизвестные счётчики показывают тире. При неудачном обновлении уже полученные объявления остаются видимыми с предупреждением; фильтры сохраняются. useListings защищён от результата устаревшего запроса.

CityPicker ранее не предлагал retry, ошибка могла сохраняться после успешного ответа. Добавлены повторная загрузка, проверка структуры ответа, сброс ошибки после успеха, защита от старых ответов, разделение пустого справочника и сбоя. Ошибка не очищает выбранный город; вымышленных вариантов нет. Первичная загрузка объединяется между компонентами, неуспешный promise не кешируется навсегда.

## Диагностика справочника городов

Production build использует публичный `VITE_API_BASE_URL` из `.env.production`: `backendupgradelab-iwrawww.waw0.amvera.tech`. Это прямой запрос к Amvera, а не локальный Vite proxy. Проверка отсутствующего локального :8000 сама по себе не объясняет production-ошибку.

Из текущей среды публичные `/api/health` и `/api/cities` не дали HTTP-ответа: оба ограниченных пятисекундных запроса завершились SSL handshake timeout. Артефакт: `.artifacts/ui-consistency/remote-api-probe.json`. Поэтому причина удалённой недоступности, HTTP-статус и CORS **не установлены**; неисправность не объявлена устранённой CSS-изменениями. Обход TLS не применялся.

Изолированный FastAPI на 127.0.0.1:8871 с настоящим маршрутом городов вернул 200 и 21 запись. Через frontend proxy :8870 получены те же 200/21. Health и listings также 200, объявлений 8. Использована отдельная fixture SQLite, внешние соединения запрещены. Для локальной браузерной приёмки сборка временно получила `VITE_API_BASE_URL=/`; production env-файл не изменялся. Остальные API-состояния воспроизводились контролируемыми browser fixtures без магазинов.

## Проверки и артефакты

- Frontend unit tests: 76/76 (69 существующих и 7 новых). Новые: ошибка против пустой выдачи, partial/refreshing, диапазон цены, конкурентная загрузка городов, retry, некорректный ответ. Старые дефекты зафиксированы скриншотами до изменения; новые unit-тесты не заявляются как запуск на старом коде.
- Production build успешен. Backend source этой итерацией не изменён, backend-регрессия повторно не запускалась; выполнен реальный локальный read-only API smoke.
- Основная браузерная матрица: 70 снимков до и 77 после (10 обязательных состояний плюс partial). Дополнительно 7 loading-снимков. Ширины 320, 375, 390, 768, 1024, 1440, 1920 px; проверки overflow страницы и диалогов, JavaScript errors.
- Ещё две браузерные регрессии: 98 проверок страниц и 98 форм. Главная, поиск/выдача/пустая выдача/ошибка API, вход/429, регистрация, восстановление, профиль/настройки, сохранённая сборка, апгрейд/FPS, все восемь категорий, создание/редактирование, доставка, длинный список 24→48, fallback фото и ручное добавление детали. Подтверждены отправленные fixture payloads; это не проверка реальных магазинов или SMTP.
- Проверены Tab, focus ring поиска, Escape диалога, reduced-motion, кнопки фильтров 44 px, прокручиваемый диалог при высоте viewport 420 px. Экранная клавиатура настоящего телефона и screen reader вручную не тестировались.
- Визуально просмотрены реальные PNG до/после ошибки биржи, мобильная ошибка городов, результат конфигуратора и форма входа с ошибкой. Программная проверка размеров дополнена этим просмотром.

Артефакты: `.artifacts/ui-consistency/before`, `after`, `regression-pages`, `regression-forms`; отчёты `report.json`, `interaction-report.json`, `pages-report.json`, логи тестов/сборки. `after/search-empty` показывает начальный поиск; настоящая отправленная пустая выдача находится в `regression-pages/search-empty-*.png`.

Сравнение: `before/market-error-1440.png` → `after/market-error-1440.png`; мобильная версия `after/cities-error-375.png`. История цены и неподтверждённые предложения по-прежнему явно обозначены; повышение статуса цен не производилось.

## Файлы этой итерации

- frontend/src/tokens.css, index.css, redesign.css; frontend/tailwind.config.js.
- frontend/src/main.jsx (подключение tokens), App.jsx (цвет SVG бренда).
- frontend/src/components/ui/Button.jsx, ErrorState.jsx; components/CityPicker.jsx.
- frontend/src/components/marketplace/MarketplaceSection.jsx; hooks/useListings.js.
- frontend/src/lib/marketState.js, cityLoader.js, uiConsistency.test.js; frontend/package.json (test script).
- docs/UI_CONSISTENCY_AUDIT.md, UI_COLOR_MIGRATION.csv, DESIGN_SYSTEM.md, CHANGELOG_DEV.md.

В рабочем дереве есть другие изменения предыдущих итераций; они сохранены. Нативные выпадающие меню остаются зависимыми от ОС. Метаданные в плотных карточках компактны; необходима отдельная проверка на физических устройствах. Production-доступность Amvera требует проверки из среды развёртывания. Архитектура, авторизация, совместимость, география и price TTL сохранены.

Предлагаемый коммит: `fix(ui): unify design tokens and marketplace recovery states`.

## Реестр прежних тёплых цветов

Полная таблица ниже дублируется в `UI_COLOR_MIGRATION.csv`. Включены все найденные тёплые литералы (hue 15–68°, saturation >12%); семантические предупреждения отмечены отдельно. Полный исходный реестр всех цветов сохранён в `.artifacts/ui-consistency/colors-before.json`, подробные замены свойств — `color-migration.json`. Inline JSX-цвет бренда переведён на --accent-text; inline размеры/прогресс сохранены. Tailwind yellow/amber используются только для warning, red/green — для error/success.

| Файл / селектор | Старый цвет | Роль | Новый токен | Компонент |
| --- | --- | --- | --- | --- |
| frontend\src\index.css / .primary-btn | #241b0e | Прежний акцент / текст / поверхность | --on-accent | Нет; общий CSS |
| frontend\src\index.css / .primary-btn:hover | #f2c98e | Прежний акцент / текст / поверхность | --surface-raised | Нет; общий CSS |
| frontend\src\index.css / .text-btn | #d4b282 | Прежний акцент / текст / поверхность | --accent-text | Нет; общий CSS |
| frontend\src\index.css / .text-btn:hover | #f1d7b1 | Прежний акцент / текст / поверхность | --accent-text | Нет; общий CSS |
| frontend\src\index.css / input:focus, select:focus, textarea:focus | #c5a37525 | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / input:focus, select:focus, textarea:focus | #c5a375 | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .hardware-options li.highlighted | #38352f | Прежний акцент / текст / поверхность | --surface-raised | Нет; общий CSS |
| frontend\src\index.css / .hardware-options li.highlighted | #f3dfc2 | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .browser-detect button | #b2a18a | Прежний акцент / текст / поверхность | --accent-text | Нет; общий CSS |
| frontend\src\index.css / .auth-tabs button.selected | #efd4ad | Прежний акцент / текст / поверхность | --accent-text | Нет; общий CSS |
| frontend\src\index.css / .account-item button | #b39783 | Прежний акцент / текст / поверхность | --accent-text | Нет; общий CSS |
| frontend\src\index.css / .fps-stat.highlight | #6c5435 | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .result-price a | #d0ad7f | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .hero-mark | #201f1c | Прежний акцент / текст / поверхность | --surface-raised (градиент удалён) | Нет; общий CSS |
| frontend\src\index.css / .hero-mark | #655135 | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .hero-mark | #dfbb88 | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .scenario-tabs>button:hover | #877050 | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .scenario-tabs>button.selected | #a5824e | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .scenario-tabs>button.selected | #24231f | Прежний акцент / текст / поверхность | --surface-raised (градиент удалён) | Нет; общий CSS |
| frontend\src\index.css / .scenario-tabs>button.selected>svg:first-child,.scenario-tabs>button.selected strong | #efcf9d | Прежний акцент / текст / поверхность | --accent-text | Нет; общий CSS |
| frontend\src\index.css / .section-icon | #514737 | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .section-icon | #d8b582 | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .builder-step>legend>span | #c6a87c | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .builder-step>legend>span | #444236 | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .auto-parts-toggle | #514838 | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .auto-parts-toggle strong | #e7d0ad | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .source-picker-action | #d2b183 | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .budget-card .eyebrow | #c5ab83 | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .budget-card>strong | #efdbb9 | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .quality-heading | #c6b18e | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .build-result-heading .eyebrow | #aa9475 | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .part-price-actions>strong | #e6dbc8 | Прежний акцент / текст / поверхность | --text-primary | Нет; общий CSS |
| frontend\src\index.css / .part-price-actions>a | #bba17c | Прежний акцент / текст / поверхность | --accent-text | Нет; общий CSS |
| frontend\src\index.css / .part-quality a | #d5b27d | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .build-total | #594a35 | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .build-total strong | #eedabd | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .compatibility-details summary | #b6a085 | Прежний акцент / текст / поверхность | --accent-text | Нет; общий CSS |
| frontend\src\index.css / .deal-tabs>button.selected | #5b4930 | Прежний акцент / текст / поверхность | --accent | ErrorState / MarketplaceSection |
| frontend\src\index.css / .deal-tabs>button.selected | #342d22 | Прежний акцент / текст / поверхность | --surface-selected | ErrorState / MarketplaceSection |
| frontend\src\index.css / .deal-tabs>button.selected | #efce9e | Прежний акцент / текст / поверхность | --accent-text | ErrorState / MarketplaceSection |
| frontend\src\index.css / .deal-tabs>button.selected>span | #d1b181 | Прежний акцент / текст / поверхность | --accent-text | ErrorState / MarketplaceSection |
| frontend\src\index.css / .deal-tabs>button:hover | #e4d4bb | Прежний акцент / текст / поверхность | --accent-text | ErrorState / MarketplaceSection |
| frontend\src\index.css / .market-search:focus-within | #ae8e5b | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .market-filter-foot>button | #cead79 | Прежний акцент / текст / поверхность | --accent-text | Нет; общий CSS |
| frontend\src\index.css / .filter-validation | #e0b4a2 | Прежний акцент / текст / поверхность | --error | Нет; общий CSS |
| frontend\src\index.css / .listing-open:hover .listing-tile | #9c7c50 | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .listing-media | #d4a56c0d | Прежний акцент / текст / поверхность | --surface-raised (градиент удалён) | Нет; общий CSS |
| frontend\src\index.css / .listing-deal | #29251dd9 | Прежний акцент / текст / поверхность | --surface-raised | Нет; общий CSS |
| frontend\src\index.css / .listing-deal | #a4865245 | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .listing-deal | #d3b886 | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .listing-value | #e9c38c | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .listing-tile-foot>span:last-child | #bba17e | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .market-empty | #d0a16c09 | Прежний акцент / текст / поверхность | --surface-raised (градиент удалён) | Нет; общий CSS |
| frontend\src\index.css / .empty-icon | #cfad7b | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .empty-icon | #5c4f3e | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .market-empty .eyebrow | #978466 | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .market-error | #715343 | Прежний акцент / текст / поверхность | --error | ErrorState / MarketplaceSection |
| frontend\src\index.css / .market-error | #d8b391 | Прежний акцент / текст / поверхность | --error | ErrorState / MarketplaceSection |
| frontend\src\index.css / .market-error h3 | #e0c8b6 | Прежний акцент / текст / поверхность | --error | ErrorState / MarketplaceSection |
| frontend\src\index.css / .market-error p | #af9b8f | Прежний акцент / текст / поверхность | --error | ErrorState / MarketplaceSection |
| frontend\src\index.css / .login-prompt h4 | #e4d6c0 | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .fps-evidence summary | #d2b487 | Прежний акцент / текст / поверхность | --accent-text | Нет; общий CSS |
| frontend\src\index.css / .loading-panel | #24221f55 | Прежний акцент / текст / поверхность | --surface-raised (градиент удалён) | Нет; общий CSS |
| frontend\src\index.css / .loading-panel>.loading-inline | #efdbbf | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .loading-track | #36342f | Прежний акцент / текст / поверхность | --surface-raised | Нет; общий CSS |
| frontend\src\index.css / .network-activity | #4b4941 | Прежний акцент / текст / поверхность | --border | Нет; общий CSS |
| frontend\src\index.css / .choice-limited | #dfcba9 | Семантическое предупреждение | --warning | Нет; общий CSS |
| frontend\src\index.css / .choice-limited | #49371b25 | Семантическое предупреждение | --surface-raised | Нет; общий CSS |
| frontend\src\index.css / .choice-limited | #5a4a35 | Семантическое предупреждение | --warning | Нет; общий CSS |
| frontend\src\index.css / .build-choice-card:hover | #a88b65 | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .build-choice-card.recommended | #2d2923 | Прежний акцент / текст / поверхность | --surface-raised (градиент удалён) | Нет; общий CSS |
| frontend\src\index.css / .build-choice-card.recommended | #b58a4e | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .recommended .choice-tag | #a37f47 | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .recommended .choice-tag | #f3ce96 | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .choice-details summary | #d8bc94 | Прежний акцент / текст / поверхность | --accent-text | Нет; общий CSS |
| frontend\src\index.css / .build-ready | #544836 | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .build-ready strong | #ecd5b2 | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .bottleneck-lesson | #51483a | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .lesson-heading .eyebrow | #c6aa80 | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .lesson-heading button,.lesson-actions>.text-btn,.lesson-complete .text-btn | #bca887 | Прежний акцент / текст / поверхность | --accent-text | Нет; общий CSS |
| frontend\src\index.css / .lesson-answers label:hover | #79705f | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .lesson-answers label.selected | #f2dfc1 | Прежний акцент / текст / поверхность | --accent-text | Нет; общий CSS |
| frontend\src\index.css / .lesson-answers label.selected | #d1aa6f | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .lesson-feedback | #d2af78 | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .lesson-feedback strong | #ead3ae | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .flow-navigation button:not(:disabled):hover | #ebd7b9 | Прежний акцент / текст / поверхность | --accent-text | Нет; общий CSS |
| frontend\src\index.css / .flow-navigation .current button | #f3d8af | Прежний акцент / текст / поверхность | --accent-text | Нет; общий CSS |
| frontend\src\index.css / .flow-navigation .current .flow-step-number | #b38a52 | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .flow-progress>span | #edc58d | Прежний акцент / текст / поверхность | --surface-raised | Нет; общий CSS |
| frontend\src\index.css / .flow-progress>span | #a6814b | Прежний акцент / текст / поверхность | --surface-raised | Нет; общий CSS |
| frontend\src\index.css / .flow-heading .eyebrow | #c3a173 | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .flow-panel .store-checkboxes>label:has(input:checked) | #e6d6bc | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .flow-panel .store-checkboxes>label:has(input:checked) | #746044 | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .flow-callout | #c7a777 | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .flow-callout | #4d4639 | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .assembly-search-summary | #c4af8f | Прежний акцент / текст / поверхность | --accent-text | Нет; общий CSS |
| frontend\src\index.css / .assembly-search-summary | #4f493d | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .assembly-price-notice | #aa8250 | Семантическое предупреждение | --warning | Нет; общий CSS |
| frontend\src\index.css / .assembly-price-notice | #efd0a0 | Семантическое предупреждение | --warning | Нет; общий CSS |
| frontend\src\index.css / .assembly-price-notice p | #c8bba7 | Семантическое предупреждение | --warning | Нет; общий CSS |
| frontend\src\index.css / .part-price-unconfirmed | #d6b581 | Семантическое предупреждение | --warning | Нет; общий CSS |
| frontend\src\index.css / .assembly-partial .eyebrow | #c7a879 | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .partial-missing summary small | #c6a87c | Прежний акцент / текст / поверхность | --accent-text | Нет; общий CSS |
| frontend\src\index.css / .partial-missing a | #dfbf91 | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .partial-missing a | #4d4437 | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .assembly-progress>span | #c89e5c | Прежний акцент / текст / поверхность | --surface-raised | Нет; общий CSS |
| frontend\src\index.css / .assembly-budget-overview>div:last-child | #5c4c33 | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .slot-icon | #c9a56a | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .slot-icon | #48453d | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .slot-web-links a,.slot-store-links a | #494337 | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .slot-web-links a,.slot-store-links a | #dfc296 | Прежний акцент / текст / поверхность | --accent-text | Нет; общий CSS |
| frontend\src\index.css / .review-icon | #4b473e | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .review-icon | #d3b180 | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .review-row>button | #d7b683 | Прежний акцент / текст / поверхность | --accent-text | Нет; общий CSS |
| frontend\src\index.css / .flow-import>summary | #c8b18e | Прежний акцент / текст / поверхность | --accent-text | Нет; общий CSS |
| frontend\src\index.css / .search-orbit>span | #a082543f | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .search-orbit>div | #393124 | Прежний акцент / текст / поверхность | --surface-raised (градиент удалён) | Нет; общий CSS |
| frontend\src\index.css / .search-orbit>div | #9d7d4a | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .loading-time>span:first-child | #c7b38f | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .loading-tip>span | #b99e75 | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / 50% | #d2ac70 | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .upgrade-source-row.source-cached>span:last-child | #e4c08b | Семантическое предупреждение | --warning | Нет; общий CSS |
| frontend\src\index.css / .upgrade-choice-card:first-child | #27241f | Прежний акцент / текст / поверхность | --surface-raised (градиент удалён) | Нет; общий CSS |
| frontend\src\index.css / .upgrade-choice-card:first-child | #c49d66 | Прежний акцент / текст / поверхность | --accent | Нет; общий CSS |
| frontend\src\index.css / .upgrade-choice-fps | #f4c27b | Прежний акцент / текст / поверхность | --text-secondary | Нет; общий CSS |
| frontend\src\index.css / .fps-preview-warning | #e2bf8b | Семантическое предупреждение | --warning | Нет; общий CSS |
| frontend\src\index.css / .part-purchase-warning | #e0bd87 | Семантическое предупреждение | --warning | Нет; общий CSS |
| frontend\src\redesign.css / /* UpgradeLab 2026: shared tokens and composition. */ :root | #e1b974 | Прежний акцент / текст / поверхность | --surface-raised (градиент удалён) | Нет; общий CSS |
| frontend\src\redesign.css / .price-origin[data-origin=seller_declared] | #665535 | Семантическое предупреждение | --warning | Нет; общий CSS |
| frontend\src\redesign.css / .price-origin[data-origin=seller_declared] | #e5c791 | Семантическое предупреждение | --warning | Нет; общий CSS |
| frontend\src\redesign.css / .price-origin[data-origin=seller_declared] | #2b261d | Семантическое предупреждение | --surface-raised | Нет; общий CSS |
