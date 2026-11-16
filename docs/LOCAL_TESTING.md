# Локальный запуск тестового архива

Архив содержит исходники, документацию и тестовые данные проекта. В нём нет `.env`, локальных баз, прайсов XLSX, кэшей и установленных зависимостей.

## Backend

Из корня распакованного проекта:

```powershell
cd backend
Copy-Item .env.testing.example .env
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Тестовый SQLite создаётся отдельно в `backend/upgradeLab-testing.db`. Сетевой поиск, браузерные адаптеры, загрузка Регарда и платный OpenRouter выключены.

## Frontend

В другом терминале:

```powershell
cd frontend
npm ci
npm run dev
```

Откройте <http://localhost:5173>. Vite проксирует `/api` на `http://127.0.0.1:8000`; если backend запущен по другому адресу, задайте `API_PROXY_TARGET` при запуске Vite.

Для запуска проверок: `npm test`. Для production-сборки: `npm run build`.
