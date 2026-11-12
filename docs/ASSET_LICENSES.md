# Происхождение изображений UpgradeLab

Проверено 10.11.2026. Все новые raster assets оригинально созданы встроенным image_gen по заданию владельца. Это сгенерированные декоративные предметные иллюстрации, не фотографии реальных SKU и не доказательство наличия/совместимости. Изображения магазинов, Google Images, чужих исполнений видеокарты и случайные CDN URL не использовались.

Авторство/происхождение: AI-generated for UpgradeLab, встроенный image_gen; собственный SVG нарисован в коде проекта. Внешней фотолицензии или приписанного фотографа нет; не заявляется CC-лицензия или исключительность прав на AI output. Требуемая внешним источником атрибуция отсутствует, поскольку внешний фотоисточник не использован. Публичный интерфейс маркирует иллюстрации, когда их можно спутать с фото товара.

| Исходник (локальный, игнорируется Git) | WebP-файлы | Размеры | Использование |
| --- | --- | --- | --- |
| `.artifacts/assets-source/case.png` | `case-480.webp`, `case-320.webp`, `case-160.webp` | 480×480, 320×320, 160×160 | Категория/сценарий; не фото предложения |
| `.artifacts/assets-source/cooler.png` | `cooler-480.webp`, `cooler-320.webp`, `cooler-160.webp` | 480×480, 320×320, 160×160 | Категория/сценарий; не фото предложения |
| `.artifacts/assets-source/cpu.png` | `cpu-480.webp`, `cpu-320.webp`, `cpu-160.webp` | 480×480, 320×320, 160×160 | Категория/сценарий; не фото предложения |
| `.artifacts/assets-source/gpu.png` | `gpu-480.webp`, `gpu-320.webp`, `gpu-160.webp` | 480×480, 320×320, 160×160 | Категория/сценарий; не фото предложения |
| `.artifacts/assets-source/hero.png` | `hero-1536.webp`, `hero-1200.webp`, `hero-800.webp` | 1536×1024, 1200×800, 800×533 | Hero первого экрана |
| `.artifacts/assets-source/hero_mobile.png` | `hero_mobile-800.webp`, `hero_mobile-480.webp`, `hero_mobile-320.webp` | 800×1200, 480×720, 320×480 | Hero первого экрана |
| `.artifacts/assets-source/memory.png` | `memory-480.webp`, `memory-320.webp`, `memory-160.webp` | 480×480, 320×320, 160×160 | Категория/сценарий; не фото предложения |
| `.artifacts/assets-source/motherboard.png` | `motherboard-480.webp`, `motherboard-320.webp`, `motherboard-160.webp` | 480×480, 320×320, 160×160 | Категория/сценарий; не фото предложения |
| `.artifacts/assets-source/psu.png` | `psu-480.webp`, `psu-320.webp`, `psu-160.webp` | 480×480, 320×320, 160×160 | Категория/сценарий; не фото предложения |
| `.artifacts/assets-source/storage.png` | `storage-480.webp`, `storage-320.webp`, `storage-160.webp` | 480×480, 320×320, 160×160 | Категория/сценарий; не фото предложения |

Десять PNG-исходников: 21,441,528 bytes. Тридцать WebP вместе: 548,526 bytes; уменьшение совокупного веса относительно десяти исходников — 97.44%. Максимальный файл 96,126 bytes. Это сравнение десяти PNG с полным набором тридцати производных, не среднее арифметическое процентов.

Все производные находятся в frontend/public/images/hardware. Manifest содержит реальное разрешение, вес, SHA-256 исходника, процент уменьшения и происхождение каждого файла. Не выполняется upscale: desktop hero максимум 1536 px по исходнику, не заявленные 1600. Пропорции сохраняются, mobile hero создан отдельной портретной композицией. EXIF/XMP/ICC не переносятся; Pillow WebP quality=83, method=6. Параметры сверены с [документацией Pillow](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#webp).

`placeholder.svg` — собственное нейтральное изображение отсутствующего фото; `Icon.jsx` и знак UpgradeLab — собственные inline SVG в существующей системе. Пользовательские фотографии не заменяются иллюстрацией другого исполнения; onError показывает нейтральный placeholder. Внешние изображения/лицензии не добавлялись. Существующие фотографии пользователей по-прежнему принадлежат их авторам.

Предоставленный `.design/upgradeLab_concept.png` использован только как направление дизайна, не скопирован в production ассеты; происхождение/разрешение на распространение самого референса не подтверждены. В mockup цифры/цены не считались фактическими.

## Процесс и промпты

Использован built-in image_gen, не CLI/API fallback. Общий промпт category: «Original UpgradeLab website decorative category image, not a specific purchasable SKU. Premium realistic studio photography on deep graphite-blue background #101722. Soft cool blue-violet edge light and neutral key light, grounded shadow, centered with safe margin, technically believable. No logos, writing, watermark, fantasy connectors, floating pieces or excessive RGB».

Субъекты: CPU — square desktop processor, plain metal heat spreader/green substrate; GPU — dual-fan full-size black desktop card/normal PCIe edge; motherboard — standard micro-ATX board with socket/DIMM/PCIe; memory — two matching desktop DIMM sticks; storage — M.2 2280 black module; PSU — standard ATX black cuboid/fan grille/cables; case — empty black mid-tower with glass side/mesh front; cooler — aluminum air tower, copper heat pipes, black 120mm fan. Запрошен квадратный кадр; фактическое разрешение проверено по файлам.

Desktop hero: photorealistic unbranded black tower PC, three-quarter view on right, tempered-glass side with normal GPU/air cooler, neat cables, graphite-blue studio, subtle blue-violet light, dark negative space at left, no logos/text/RGB excess. Mobile hero: отдельная портретная композиция того же направления, целый tower с комфортными полями. Текст и CTA всегда HTML.

Пересборка из сохранённых PNG:

```powershell
uv pip install --python backend/.venv/Scripts/python.exe -r tools/requirements-assets.txt
backend/.venv/Scripts/python.exe tools/optimize_assets.py --source .artifacts/assets-source --output frontend/public/images/hardware
```

PNG-исходники остаются локальными артефактами. Production использует проверенные WebP и не зависит от генератора/Pillow. Если исходники не переданы в другую среду, готовые WebP остаются рабочими; для новой оптимизации нужны исходные изображения.
