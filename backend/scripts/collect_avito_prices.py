"""Incrementally collect real Avito observations for CPU/GPU catalog models."""
import argparse
import time
from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import Hardware
from app.schemas.offers import SearchOffers
from app.services.offers import search_offers
from app.services.upgrade_prices import upgrade_price_map


def main():
    parser = argparse.ArgumentParser(description='Collect Avito CPU/GPU observations without bypassing access checks.')
    parser.add_argument('--offset', type=int, default=0, help='First catalog index to process')
    parser.add_argument('--limit', type=int, default=25, help='Maximum number of models per run')
    parser.add_argument('--category', choices=['CPU', 'GPU', 'all'], default='all')
    parser.add_argument('--method', choices=['http', 'browser'], default='http')
    parser.add_argument('--delay', type=float, default=1.0, help='Seconds between requests (minimum 1)')
    args = parser.parse_args()
    if args.offset < 0 or not 1 <= args.limit <= 200 or args.delay < 1:
        parser.error('offset >= 0, 1 <= limit <= 200, delay >= 1')
    from app.main import app  # noqa: F401 -- initialize database and seed catalog
    with SessionLocal() as db:
        query = select(Hardware).where(Hardware.type.in_(['CPU', 'GPU'])).order_by(Hardware.id)
        if args.category != 'all':
            query = query.where(Hardware.type == args.category)
        items = list(db.scalars(query))
        next_offset = args.offset
        for index, item in enumerate(items[args.offset:args.offset + args.limit], start=args.offset):
            request = SearchOffers(query=item.name[:160], category=item.type, sources=['avito'],
                                   hardware_id=item.id, method=args.method)
            request._deadline = time.monotonic() + 15
            response = search_offers(db, request)
            status = response['sources'][0]
            print(f"{index}: {item.name} — {status['status']}: {status['message']}", flush=True)
            if status['status'] in ('unavailable', 'timeout', 'disabled'):
                print('Source unavailable; stopped without bypassing its access checks.', flush=True)
                break
            next_offset = index + 1
            if next_offset < min(args.offset + args.limit, len(items)):
                time.sleep(args.delay)
        prices = upgrade_price_map(db, ['avito'])
        print(f"Catalog models: {len(items)}; Avito observations/snapshots with prices: "
              f"{sum(item.id in prices for item in items)}; resume with --offset {next_offset}")


if __name__ == '__main__':
    main()
