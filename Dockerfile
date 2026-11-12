FROM node:22-alpine AS frontend-build
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM mcr.microsoft.com/playwright/python:v1.64.1-noble
ENV PYTHONUNBUFFERED=1 AMVERA=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app
COPY backend/requirements.txt backend/requirements-browser.txt ./
RUN python -m pip install --no-cache-dir -r requirements-browser.txt
COPY backend/app ./app
COPY backend/scripts ./scripts
COPY backend/seed_data.json ./seed_data.json
COPY backend/price_data.json ./price_data.json
COPY --from=frontend-build /src/frontend/dist ./web-dist
EXPOSE 80
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]
