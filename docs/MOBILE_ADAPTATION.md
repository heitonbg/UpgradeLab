# Mobile adaptation — final validation, 16.11.2026

Кнопка «Отправить свой бенчмарк» перенесена в header страницы бенчмарков, сразу после заголовка/описания. Нижний CTA удалён. Переход ведёт на существующую отдельную страницу ?tab=benchmark-submit; кнопка доступна в первом экране 320/390 px.

Основные причины: мобильные контроли наследовали desktop-ограничения, вложенные padding отнимали ширину мастера, большой редактор имел min-height:100dvh вопреки max-height, дополнительные фильтры/таблицы занимали первый экран. Ранее созданный мобильный слой сохранён и приведён к одному max-width:760px breakpoint плюс уточнение 16px отступов от 390px; глобальное overflow-x:hidden не добавлялось.

Изменены frontend/src/components/BenchmarkExplorer.jsx, frontend/src/mobile.css, frontend/index.html (viewport-fit=cover); tools/mobile_layout_audit.py расширен, добавлен tools/mobile_form_scenarios.py. Поднята кнопка, убраны её дубль и лишние рамки/padding мастеров, добавлены safe-area отступы, исправлены высота редактора и единственный scroll owner в modal-content. Мобильные menu, card table, 16px inputs, компактные формы из предыдущей итерации сохранены. Backend, Steam, API-контракты, авторизация, алгоритмы подбора/FPS не менялись.

Проверены реальные существующие маршруты: home; calculator scenario=build/upgrade/custom; search; benchmarks; marketplace; account; benchmark-submit. FPS Calculator — часть upgrade, каталог/поиск — search, сравнение — существующие блоки/модальные окна, новые маршруты не создавались. На аккаунте fixture сохранённой сборки раскрыты детали, открыт редактор объявления. Вход и регистрация проверены в guest-режиме. Настройки профиля входят в account. Все четыре шага обоих мастеров пройдены без отправки реального расчёта.

Viewport matrix: 320×640, 360×800, 375×812, 390×844, 414×896, 430×932, 768×1024, 1024×768, 1280×900, 1440×900, 1920×1080. Девять маршрутов × 11 размеров = 99 снимков с авторизованными fixtures, плюс отдельные сценарии на 320/390. Проверены page overflow, текст >=12px, открытие меню/переходы, desktop layout, 16px inputs, dropdown CPU в пределах viewport, создание/редактирование объявления, modal bounds и восстановление body scroll, сохранённая сборка, login/register и верхняя кнопка бенчмарка. Browser API полностью mock; тесты не пишут рабочую SQLite. Тест матрицы исправлен на актуальный endpoint /api/hardware/selectors; ложный UI-error из прежней fixture устранён.

Результат: в 99 случаях нет горизонтального overflow, мелкого текста и pageerror. Формовые и навигационные сценарии прошли. Desktop меню и таблица сохранены. Frontend suite: 133 passed; production build passed; git diff --check passed.

Артефакты: ../.artifacts/mobile-audit/complete.json, complete-{width}-{route}.png; form-{width}-*.png. Предыдущие before-home.png/before-benchmarks.png — локальные снимки до мобильной итерации; after/current содержат другие тестовые данные, это визуальное сравнение компоновки, а не pixel-identical accuracy test. Вручную просмотрены снимки главной, заполненных бенчмарков, подборщика 320px и модального окна. Не заявляется ручной просмотр каждого из 99 файлов.

Скриншоты:
- [До: главная](../.artifacts/mobile-audit/before-home.png)
- [После: главная](../.artifacts/mobile-audit/complete-390-home.png)
- [До: бенчмарки](../.artifacts/mobile-audit/before-benchmarks.png)
- [После: бенчмарки](../.artifacts/mobile-audit/complete-390-benchmarks.png)
- [Мастер 320px](../.artifacts/mobile-audit/complete-320-calculator-build.png)
- [Объявление 320px](../.artifacts/mobile-audit/form-320-new-listing.png)

Воспроизведение: локальный Vite 127.0.0.1:5174, затем Python с Playwright: tools/mobile_layout_audit.py (AUDIT_AUTH=1), tools/mobile_layout_interactions.py, tools/mobile_form_scenarios.py. Артефакты не включаются в production ZIP. Общий git diff --stat сохранён в .artifacts/mobile-audit/worktree-diffstat.txt; он содержит изменения предыдущих итераций и не включает untracked файлы.

Ограничения: Chromium/Edge emulation, не физический iPhone/Safari. VisualViewport при настоящей клавиатуре, safe area на физическом устройстве и все возможные пользовательские данные не проверены. Стандартный CSS safe-area реализован, но не выдаётся за аппаратный тест. Подбор/FPS API не пересчитывались ради responsive-теста; layout результатов апгрейда проверялся существующей fixture-проверкой в предыдущей итерации. В этой итерации backend не менялся. Commit/push/deployment не выполнялись.
