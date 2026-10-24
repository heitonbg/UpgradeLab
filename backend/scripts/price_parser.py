"""
Быстрый парсер цен через обычные HTTP-запросы.
Обрабатывает 3 модели. Пытается достать цены с DNS (API) и Авито (HTML).
Если не выходит — генерирует цену по PassMark.
Запуск: python -m scripts.price_parser
"""
import logging
import random
import time
from statistics import median
from typing import List
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select, update

from app.db.base import SessionLocal
from app.db.models import Hardware

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ОГРАНИЧЕНИЕ: обрабатываем только 3 комплектующих для быстрой проверки
MAX_ITEMS_TO_UPDATE = 3 

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

def get_dns_prices(query: str) -> List[int]:
    """Парсит DNS через внутренний API (JSON)"""
    prices = []
    # Внутренний API поиска DNS
    url = f"https://restapi.dns-shop.ru/v1/search?q={quote(query)}"
    try:
        with httpx.Client(headers=HEADERS, timeout=5.0) as client:
            res = client.get(url)
            if res.status_code == 200:
                data = res.json()
                items = data.get("data", {}).get("items", [])
                for item in items:
                    price_info = item.get("price", {})
                    price_val = price_info.get("current") or price_info.get("price")
                    if price_val:
                        try:
                            price = int(float(price_val))
                            if 1000 < price < 500000:
                                prices.append(price)
                        except (ValueError, TypeError):
                            continue
    except Exception:
        pass
    return prices

def get_avito_prices(query: str) -> List[int]:
    """Пытается спарсить Авито через HTML (сработает, только если нет бана)"""
    prices = []
    url = f"https://www.avito.ru/moskva?q={quote(query)}"
    try:
        with httpx.Client(headers=HEADERS, timeout=5.0, follow_redirects=True) as client:
            res = client.get(url)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                # Ищем мета-теги с ценами
                for el in soup.find_all('meta', itemprop='price'):
                    price_str = el.get('content')
                    if price_str and price_str.isdigit():
                        price = int(price_str)
                        if 1000 < price < 500000:
                            prices.append(price)
    except Exception:
        pass
    return prices

def generate_mock_price(raw_score: int, hw_type: str) -> int:
    """Генерирует цену на основе PassMark"""
    if hw_type == "CPU":
        base_price = int((raw_score / 1000) * 1500)
    else:
        base_price = int((raw_score / 1000) * 2000)
    variation = random.uniform(0.9, 1.1)
    final_price = int(base_price * variation)
    return (final_price // 100) * 100

def main():
    logger.info("Начинаем быстрый парсинг цен...")
    
    db = SessionLocal()
    try:
        query = select(Hardware).limit(MAX_ITEMS_TO_UPDATE)
        hw_list = db.scalars(query).all()
        logger.info(f"Загружено {len(hw_list)} комплектующих.")
    finally:
        db.close()

    results = {}
    
    for i, hw in enumerate(hw_list, 1):
        logger.info(f"[{i}/{len(hw_list)}] Обработка: {hw.name}")
        
        # 1. Пытаемся достать цены
        dns = get_dns_prices(hw.name)
        avito = get_avito_prices(hw.name)
        all_prices = dns + avito
        
        if all_prices:
            # 2. Считаем медиану
            price = int(median(all_prices))
            logger.info(f"  ✅ Найдено: Медиана {price} ₽ (DNS: {len(dns)}, Авито: {len(avito)})")
        else:
            # 3. Если не нашли — генерируем
            price = generate_mock_price(hw.raw_score, hw.type)
            logger.info(f"  🤖 Парсинг не удался. Генерация: {price} ₽")
            
        results[hw.id] = price
        time.sleep(1)

    # Сохраняем в БД
    if results:
        db = SessionLocal()
        try:
            for hw_id, price in results.items():
                stmt = update(Hardware).where(Hardware.id == hw_id).values(avg_price=price)
                db.execute(stmt)
            db.commit()
            logger.info(f"✅ База данных обновлена для {len(results)} моделей.")
        finally:
            db.close()

if __name__ == "__main__":
    main()