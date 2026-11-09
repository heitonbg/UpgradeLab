"""Idempotent additive SQLite migration; no user rows are rewritten or removed."""
from sqlalchemy import inspect, text

LISTING_COLUMNS = {
    'listing_type': "VARCHAR(20) NOT NULL DEFAULT 'sale'",
    'exchange_for': 'VARCHAR(500)', 'photo_url': 'TEXT',
    'city_id': 'VARCHAR(100)', 'category': 'VARCHAR(20)', 'hardware_id': 'INTEGER',
    'contact_type': 'VARCHAR(20)', 'publication_status': "VARCHAR(20) NOT NULL DEFAULT 'active'",
    'updated_at': 'DATETIME', 'availability_confirmed_at': 'DATETIME',
}

def migrate_listings(engine):
    columns={column['name'] for column in inspect(engine).get_columns('listings')}
    with engine.begin() as connection:
        for name,definition in LISTING_COLUMNS.items():
            if name not in columns:
                connection.execute(text(f'ALTER TABLE listings ADD COLUMN {name} {definition}'))
