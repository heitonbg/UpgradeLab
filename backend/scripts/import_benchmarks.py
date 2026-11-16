"""Explicitly import the licensed curated dataset into an SQLite database.

Example (isolated local database):
    python -m scripts.import_benchmarks --database-url sqlite:///./storage/benchmarks.sqlite
"""
import argparse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.migrations import migrate_benchmarks
from app.services.benchmark_storage import import_curated_benchmarks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url', required=True,
                        help='Explicit target database URL; no default app database is used.')
    parser.add_argument('--dataset', default=None, help='Path to curated measurements.json')
    args = parser.parse_args()
    connect_args = {'check_same_thread': False, 'timeout': 30} if args.database_url.startswith('sqlite') else {}
    engine = create_engine(args.database_url, connect_args=connect_args)
    migrate_benchmarks(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as db:
        result = import_curated_benchmarks(db, args.dataset)
    print(result)


if __name__ == '__main__':
    main()
