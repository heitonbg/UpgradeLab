FROM mcr.microsoft.com/playwright/python:v1.64.1-noble

ENV PYTHONUNBUFFERED=1 \
    AMVERA=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    REGARD_BOOTSTRAP_ON_START=true \
    REGARD_DOWNLOAD_ENABLED=true \
    REGARD_PRICE_URL=https://www.regard.ru/api/site/pricelist \
    REGARD_DAILY_SYNC_ENABLED=true \
    REGARD_DAILY_SYNC_INTERVAL_SECONDS=86400 \
    SOURCE_PERMISSIONS='{"regard":{"automatic_network":true,"public_display":true,"basis":"Project owner confirmed permission for automatic downloads and public non-commercial display","confirmed_by":"Project owner","confirmed_at":"2026-11-15T16:43:07Z"}}'

WORKDIR /app

COPY requirements.txt requirements-browser.txt ./
RUN python -m pip install --no-cache-dir -r requirements-browser.txt

COPY . .

EXPOSE 80
CMD ["python", "-m", "scripts.startup"]
