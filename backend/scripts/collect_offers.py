"""Collect verified store offers, e.g. python -m scripts.collect_offers 'RTX 5060'
--sources regard oldi kns --method http. Prices are persisted in the server DB."""
import argparse
import json
from pathlib import Path
from app.core.stores import STORES
from app.schemas.offers import SearchOffers
from app.services.offers import search_offers
from app.db.base import SessionLocal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?")
    parser.add_argument("--category", default="GPU", choices=["CPU", "GPU", "motherboard", "memory", "storage", "psu", "case", "cooler"])
    parser.add_argument("--sources", nargs="+", choices=list(STORES), default=list(STORES))
    parser.add_argument("--method", choices=["http", "browser", "discovery"], default="http")
    parser.add_argument("--report", help="Optional JSON report path")
    parser.add_argument("--list-sources", action="store_true")
    args = parser.parse_args()
    if args.list_sources:
        print(json.dumps({key: value["name"] for key, value in STORES.items()}, ensure_ascii=False, indent=2))
        return
    if not args.query:
        parser.error("Укажите модель или --list-sources")
    payload = SearchOffers(query=args.query, category=args.category, sources=args.sources, method=args.method)
    from app.main import app  # Ensure tables and benchmark catalog exist.
    with SessionLocal() as db:
        result = search_offers(db, payload)
    content = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.report:
        Path(args.report).write_text(content, encoding="utf-8")
    print(content)


if __name__ == "__main__":
    main()
