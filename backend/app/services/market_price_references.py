"""Dated, source-linked planning references for common CPUs and GPUs.

These are marketplace asking prices and shop listings, not completed sales or
offers available to purchase. Never use them as verified quotes or in totals.
"""
from __future__ import annotations

from datetime import date
from urllib.parse import quote_plus
import re


OBSERVED_ON = date(2026, 11, 13)
MARKET_SOURCE = "https://thing-price.ru/c/processory"
GPU_MARKET_SOURCE = "https://thing-price.ru/c/gpu"

# Price references are captured from current DNS/other verified shop listings
# and Avito asking-price summaries. They are shown for planning only.
REFERENCES = (
    {"category": "CPU", "key": "ryzen55600", "model": "AMD Ryzen 5 5600",
     "retail_price_rub": 10799, "used_price_rub": 8500, "used_sample_count": 3,
     "retail_url": "https://thing-price.ru/m/amd-ryzen-5-5600",
     "market_url": "https://thing-price.ru/m/amd-ryzen-5-5600",
     "market_basis": "нижняя четверть магазинных цен; 3 Avito-объявления, не завершённые сделки"},
    {"category": "CPU", "key": "ryzen75700x", "model": "AMD Ryzen 7 5700X",
     "retail_price_rub": 12724, "used_price_rub": 12500, "used_sample_count": 5,
     "retail_url": "https://thing-price.ru/m/amd-ryzen-7-5700x", "market_url": "https://thing-price.ru/m/amd-ryzen-7-5700x",
     "market_basis": "нижняя четверть магазинных цен; 5 Avito-объявлений, не завершённые сделки"},
    {"category": "CPU", "key": "i512400f", "model": "Intel Core i5-12400F",
     "retail_price_rub": 12308, "used_price_rub": 7500, "used_sample_count": 4,
     "retail_url": "https://thing-price.ru/m/intel-core-i5-12400f", "market_url": "https://thing-price.ru/m/intel-core-i5-12400f",
     "market_basis": "нижняя четверть магазинных цен; Avito-цена давно не обновлялась, только ориентир"},
    {"category": "GPU", "key": "rtx3060", "model": "GeForce RTX 3060 12 ГБ",
     "retail_price_rub": 49560, "used_price_rub": 30990, "used_sample_count": 33,
     "retail_url": "https://thing-price.ru/m/nvidia-geforce-rtx-3060-12-gb", "market_url": "https://thing-price.ru/m/nvidia-geforce-rtx-3060-12-gb",
     "market_basis": "нижняя четверть магазинных цен; 33 Avito-объявления, не завершённые сделки"},
    {"category": "GPU", "key": "rtx4060", "model": "GeForce RTX 4060",
     "retail_price_rub": 29999, "used_price_rub": 36000, "used_sample_count": 17,
     "retail_url": "https://thing-price.ru/m/nvidia-geforce-rtx-4060",
     "market_url": "https://thing-price.ru/m/nvidia-geforce-rtx-4060",
     "market_basis": "нижняя четверть магазинных цен; 17 Avito-объявлений, б/у может стоить дороже новой"},
    {"category": "GPU", "key": "rtx5060", "model": "GeForce RTX 5060",
     "retail_price_rub": 53999, "used_price_rub": 46000, "used_sample_count": 23,
     "retail_url": "https://thing-price.ru/m/nvidia-geforce-rtx-5060", "market_url": "https://thing-price.ru/m/nvidia-geforce-rtx-5060",
     "market_basis": "нижняя четверть магазинных цен; 23 Avito-объявления, не завершённые сделки"},
    {"category": "GPU", "key": "rx6600", "model": "Radeon RX 6600",
     "retail_price_rub": 29916, "used_price_rub": 21088, "used_sample_count": 13,
     "retail_url": "https://thing-price.ru/m/amd-radeon-rx-6600", "market_url": "https://thing-price.ru/m/amd-radeon-rx-6600",
     "market_basis": "нижняя четверть магазинных цен; 13 Avito-объявлений, не завершённые сделки"},
    {"category": "GPU", "key": "rx7600", "model": "Radeon RX 7600",
     "retail_price_rub": 43446, "used_price_rub": 32000, "used_sample_count": 5,
     "retail_url": "https://thing-price.ru/m/amd-radeon-rx-7600", "market_url": "https://thing-price.ru/m/amd-radeon-rx-7600",
     "market_basis": "нижняя четверть магазинных цен; выборка всего 5 Avito-объявлений, низкая уверенность"},
)


def _canonical(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").casefold())


def planning_price_reference(name: str, category: str) -> dict | None:
    normalized = _canonical(name)
    for row in REFERENCES:
        if row["category"] != category:
            continue
        key = row["key"]
        # Avoid assigning a base model's price to Ti/XT/X variants even when
        # the model name has a vendor prefix (e.g. "GeForce RTX 5060 Ti").
        match_at = normalized.find(key)
        if match_at >= 0 and len(normalized) > match_at + len(key):
            suffix = normalized[match_at + len(key):]
            if suffix.startswith(("ti", "xt", "super", "mobile", "laptop", "3d")):
                continue
            if key == "ryzen55600" and suffix.startswith("x"):
                continue
        if key in normalized:
            query = quote_plus(row["model"])
            result = {**row, "observed_at": OBSERVED_ON.isoformat(),
                      "retail_url": f"https://www.dns-shop.ru/search/?q={query}",
                      "market_url": f"https://www.avito.ru/rossiya?q={query}",
                      "used_price_basis": "asking_price_reference",
                      "is_purchase_quote": False}
            if row.get("used_price_rub") and row.get("retail_price_rub"):
                result["used_discount_percent"] = round(
                    (1 - row["used_price_rub"] / row["retail_price_rub"]) * 100)
            return result
    return None


def planning_price_options(names, category: str, limit: int = 3) -> list[dict]:
    """Return distinct exact-model references represented by candidate queries."""
    found = []
    seen = set()
    for name in names:
        reference = planning_price_reference(name, category)
        if reference and reference["key"] not in seen:
            seen.add(reference["key"])
            found.append(reference)
            if len(found) >= limit:
                break
    return found
