from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.db.models import HardwarePrice
import json
from pathlib import Path

SOURCE_LABELS = {"passmark": "PassMark / USD → RUB", "avito_snapshot": "Avito: сохранённые предложения", "retailer_feed": "Прайс поставщика"}


def price_map(db):
    """Only sourced observations may participate in a budget calculation."""
    quotes = {}
    for quote in db.scalars(select(HardwarePrice)):
        age = datetime.utcnow() - quote.observed_at
        lifetime = timedelta(days=30 if quote.market == "used_ru" else 7)
        if age > lifetime or quote.price_rub <= 0:
            continue
        previous = quotes.get(quote.hardware_id)
        priority = {"retail_ru": 3, "used_ru": 2, "retail_us_converted": 1}
        if previous is None or (priority.get(quote.market, 0), quote.observed_at) > (priority.get(previous.market, 0), previous.observed_at):
            quotes[quote.hardware_id] = quote
    return quotes


def public_price(quote):
    if quote is None:
        return {"avg_price": None, "price_source": None, "price_date": None, "price_market": None, "price_url": None}
    return {"avg_price": quote.price_rub, "price_source": SOURCE_LABELS.get(quote.source, quote.source),
            "price_date": quote.observed_at.replace(tzinfo=timezone.utc), "price_market": quote.market, "price_url": quote.source_url}


def load_price_cache(db):
    from app.db.models import Hardware
    from app.services.hardware_matching import model_key
    path = Path(__file__).resolve().parents[2] / "price_data.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    lookup = {(hw.type, model_key(hw.name)): hw.id for hw in db.scalars(select(Hardware))}
    for row in data.get("metadata", []):
        hw_id = lookup.get((row["type"], model_key(row["name"])))
        if hw_id is not None:
            db.get(Hardware, hw_id).socket = row["socket"]
    for row in data.get("quotes", []):
        hw_id = lookup.get((row["type"], model_key(row["name"])))
        if hw_id is None:
            continue
        observed = datetime.fromisoformat(row["observed_at"])
        quote = db.get(HardwarePrice, (hw_id, row["source"]))
        if quote and quote.observed_at >= observed:
            continue
        if quote is None:
            quote = HardwarePrice(hardware_id=hw_id, source=row["source"])
            db.add(quote)
        for key in ("price_rub", "market", "source_url", "sample_count"):
            setattr(quote, key, row[key])
        quote.observed_at = observed
    db.commit()
