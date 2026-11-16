"""Build two clean Code archives with independent roots and validated manifests."""
import argparse,hashlib,json,re
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
ROOT=Path(__file__).resolve().parents[1]
SKIP={'.git','.venv','venv','node_modules','dist','build','coverage','__pycache__','.artifacts','.pytest_cache','storage','uploads','tests','price_data','fixtures'}
EXT={'.db','.sqlite','.sqlite3','.xlsx','.xls','.ods','.log','.pyc','.zip','.pem','.key'}
BACKEND_FILES={'amvera.yml','Dockerfile','.dockerignore','requirements.txt','requirements-browser.txt','seed_data.json','price_data.json'}
FRONTEND_FILES={'amvera.yml','package.json','package-lock.json','index.html','vite.config.js','postcss.config.js','tailwind.config.js'}
BACKEND_GUIDE="""# Backend Amvera — текущий релиз

Распакуйте содержимое этого ZIP прямо в корень Code backend-проекта. Среда Docker. Не заменяйте Data: /data/pc_upgrade.db, файлы прайса, аккаунты, объявления и сборки сохраняются. Перед обновлением сделайте резервную копию SQLite. При старте добавляются таблицы общих снимков, захватов и лимитов бенчмарков; готовая БД в ZIP не включена.

Переменные backend:
AMVERA=1
STEAM_REQUIREMENTS_ENABLED=true
STEAM_WORKER_ENABLED=true
STEAM_WORKER_IDLE_SECONDS=10
STEAM_REQUEST_INTERVAL_SECONDS=4
DATABASE_URL=sqlite:////data/pc_upgrade.db
FRONTEND_URL=https://frontendupgradelab-iwrawww.waw0.amvera.tech
BACKEND_URL=https://backendupgradelab-iwrawww.waw0.amvera.tech
CORS_ORIGINS=https://frontendupgradelab-iwrawww.waw0.amvera.tech
COOKIE_SECURE=true
COOKIE_SAMESITE=none
REGARD_BOOTSTRAP_ON_START=true
REGARD_DOWNLOAD_ENABLED=true
REGARD_PRICE_URL=https://www.regard.ru/api/site/pricelist
REGARD_DAILY_SYNC_ENABLED=true
REGARD_DAILY_SYNC_INTERVAL_SECONDS=86400
OPENROUTER_SEARCH_ENABLED=false
OPENROUTER_ALLOW_PAID_WEB=false

SOURCE_PERMISSIONS: сохраните существующий разрешённый JSON для regard (automatic_network, public_display и сведения о подтверждении). SMTP и ключи остаются только в переменных Amvera. Если Data пустая, отдельно загрузите price.xlsx, regard-schema.json и regard-rights.json; последний должен разрешать automatic_download и нужный публичный показ. Для существующей Data сохраняйте эти файлы и SQLite. Повторный SHA-256 пропускает импорт; скачивание для сравнения содержимого может всё равно требоваться.

BENCHMARK_REVIEWER_EMAILS: укажите email своих аккаунтов модераторов через запятую. Новые замеры pending до проверки. Очередь GET /api/benchmarks/submissions/review-queue; закрытый frametime GET /api/benchmarks/submissions/{id}/capture; решение PATCH /api/benchmarks/submissions/{id}. Распознавание файла не доказывает подлинность.

Steam: worker запускается backend автоматически, отдельный проект не требуется. Очередь и кеш используют ту же SQLite в /data; supervisor восстанавливает worker после падения. Новые SQLite используют DELETE/FULL; существующий WAL не конвертируется автоматически. Linux/container smoke на реальном хранилище ещё не выполнен: при необходимости запустите python -m scripts.steam_linux_smoke на отдельной временной БД.

После запуска проверьте /api/health, /api/catalog/readiness и /docs; затем авторизацию, общую ссылку, загрузку замера и подбор ПК с настоящего frontend origin. Целевой FPS основан на некалиброванной модели; вариант с доплатой показан отдельно. Docker и работа на Amvera из текущей среды не проверялись; deployment не выполнялся.
"""
FRONTEND_GUIDE="""# Frontend Amvera — текущий релиз

Распакуйте содержимое этого ZIP прямо в корень Code frontend-проекта. Среда Node.JS Browser; используйте amvera.yml из архива. Он задаёт адрес backend для Vite на этапе сборки.

Backend: https://backendupgradelab-iwrawww.waw0.amvera.tech
Frontend: https://frontendupgradelab-iwrawww.waw0.amvera.tech

Сначала обновите backend из парного ZIP. Общие снимки сборок и импорт CSV/JSON используют его новые API. Создание снимка требует входа, чтение публичной ссылки — нет. Для объявления копируется прямая ссылка. Для обоих проектов содержимое ZIP размещается непосредственно в Code, без дополнительной внешней папки. Deployment не выполнялся.
"""

def files(kind):
    base=ROOT/kind
    roots={'app','scripts'} if kind=='backend' else {'src','public','scripts'}
    singles=BACKEND_FILES if kind=='backend' else FRONTEND_FILES
    for p in sorted(base.rglob('*')):
        rel=p.relative_to(base)
        if not p.is_file() or p.is_symlink():continue
        if rel.parts[0] not in roots and not (len(rel.parts)==1 and p.name in singles):continue
        if any(part in SKIP for part in rel.parts[:-1]):continue
        if p.name.startswith('.env') or p.suffix.lower() in EXT or p.name.endswith(('-wal','-shm','.test.js')):continue
        if kind=='backend' and rel.parts[0]=='scripts' and p.suffix!='.py':continue
        yield p,rel.as_posix()

def package(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    manifest=[]
    for kind in ('backend','frontend'):
        target=output/f'UpgradeLab-{kind.capitalize()}-Amvera-ready.zip'
        entries=list(files(kind))
        with ZipFile(target,'w',ZIP_DEFLATED,compresslevel=7) as z:
            for p,rel in entries:z.write(p,rel)
            z.writestr('AMVERA_SETUP.md',BACKEND_GUIDE if kind=='backend' else FRONTEND_GUIDE)
        with ZipFile(target) as z:
            names=z.namelist()
            assert len(names)==len(set(names))
            assert z.testzip() is None
            required=BACKEND_FILES if kind=='backend' else FRONTEND_FILES
            assert required.issubset(names),(kind,'missing root files')
            if kind=='backend':
                for n in ('app/api/shared_builds.py','app/services/benchmark_capture.py','app/services/target_selection.py','scripts/startup.py','app/services/steam_lifecycle.py','app/services/steam_http.py','app/services/steam_storage.py','app/services/steam_parser.py','app/api/steam_requirements.py','app/workers/steam_requirements_worker.py','app/data/steam_game_index.json','scripts/steam_linux_smoke.py'):assert n in names
            for n in names:
                p=Path(n)
                assert not p.is_absolute() and '..' not in p.parts
                assert p.suffix.lower() not in EXT and not p.name.startswith('.env')
                assert not any(part in SKIP for part in p.parts[:-1])
                if kind=='backend':assert 'frontend' not in p.parts
                if p.suffix.lower() in ('.py','.js','.jsx','.json','.md','.yml','.txt'):
                    data=z.read(n)
                    if re.search(rb'sk-or-v1-[a-zA-Z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC )?PRIVATE KEY-----',data):
                        raise RuntimeError('Possible secret in '+n)
        manifest.append({'archive':target.name,'files':len(names),'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'nested_archives':0})
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest,indent=2))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default=str(ROOT/'.artifacts/amvera-release'));args=parser.parse_args();package(args.output)
