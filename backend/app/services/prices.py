from datetime import timedelta
from app.core.price_time import as_utc, as_naive_utc, is_fresh, current_verification, OBSERVATION_SKEW, OFFER_TTL
from sqlalchemy import select
from app.db.models import HardwarePrice
import json
from pathlib import Path
from types import SimpleNamespace
from app.schemas.offers import LABELS

SOURCE_LABELS = {"passmark": "PassMark / USD → RUB", "avito_snapshot": "Avito: сохранённые предложения", "retailer_feed": "Прайс поставщика"}
SOURCE_LABELS.update(LABELS)


def price_map(db, sources=None, allowed_offer_ids=None, preferred_source=None, observed=False):
    """Only sourced observations may participate in a budget calculation."""
    quotes = {}
    for quote in db.scalars(select(HardwarePrice)) if sources is None else []:
        lifetime = timedelta(days=30 if quote.market == "used_ru" else 7)
        if not is_fresh(quote.observed_at, lifetime, inclusive=True, future_tolerance=OBSERVATION_SKEW) or quote.price_rub <= 0:
            continue
        previous = quotes.get(quote.hardware_id)
        priority = {"retail_ru": 3, "used_ru": 2, "retail_us_converted": 1}
        if previous is None or (priority.get(quote.market, 0), quote.observed_at) > (priority.get(previous.market, 0), previous.observed_at):
            quotes[quote.hardware_id] = quote
    from app.services.offers import available_offers
    for offer in available_offers(db, sources, include_unavailable=observed):
        if allowed_offer_ids is not None and offer.id not in allowed_offer_ids:
            continue
        if not offer.hardware_id:
            continue
        previous = quotes.get(offer.hardware_id)
        preferred = offer.source == preferred_source
        previous_preferred = previous is not None and previous.source == preferred_source
        if (previous is None or previous.market == "retail_us_converted" or preferred and not previous_preferred
                or preferred == previous_preferred and offer.price_rub < previous.price_rub):
            verification = json.loads(offer.attributes).get('price_verification', {})
            quotes[offer.hardware_id] = SimpleNamespace(
                price_rub=offer.price_rub, source=offer.source,
                market="used_ru" if offer.condition == "used" else "retail_ru",
                source_url=offer.url, observed_at=offer.observed_at, sample_count=1,
                offer_id=offer.id, origin=offer.origin, offer_name=offer.name,
                verified_at=current_verification(verification))
    return quotes


def public_price(quote):
    if quote is None:
        return {"avg_price": None, "price_source": None, "price_date": None, "price_market": None, "price_url": None}
    return {"avg_price": quote.price_rub, "price_source": SOURCE_LABELS.get(quote.source, quote.source),
            "sample_count": getattr(quote, 'sample_count', 1), "average_method": getattr(quote, 'average_method', None),
            "price_window_days": getattr(quote, 'observation_days', None),
            "offer_id": getattr(quote, "offer_id", None), "price_offer_name": getattr(quote, "offer_name", None), "price_origin": getattr(quote, "origin", "snapshot"),
            "price_verified_at": (current_verification({'status': 'verified', 'checked_at': getattr(quote, 'verified_at', None)})
                                  if is_fresh(quote.observed_at, OFFER_TTL, inclusive=True, future_tolerance=OBSERVATION_SKEW) else None),
            "price_date": as_utc(quote.observed_at), "price_market": quote.market, "price_url": quote.source_url}


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
        observed = as_naive_utc(row.get("observed_at"))
        if observed is None or not is_fresh(observed, timedelta.max, inclusive=True, future_tolerance=OBSERVATION_SKEW):
            continue
        quote = db.get(HardwarePrice, (hw_id, row["source"]))
        if (quote and is_fresh(quote.observed_at, timedelta.max, inclusive=True, future_tolerance=OBSERVATION_SKEW)
                and as_utc(quote.observed_at) >= as_utc(observed)):
            continue
        if quote is None:
            quote = HardwarePrice(hardware_id=hw_id, source=row["source"])
            db.add(quote)
        for key in ("price_rub", "market", "source_url", "sample_count"):
            setattr(quote, key, row[key])
        quote.observed_at = observed
    db.commit()
