from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.core.config import settings

connect_args = ({"check_same_thread": False, "timeout": 30} if settings.database_url.startswith("sqlite") else {})

engine = create_engine(settings.database_url, connect_args=connect_args)

if engine.url.get_backend_name() == 'sqlite':
    from sqlalchemy import event

    @event.listens_for(engine, 'connect')
    def configure_sqlite_connection(connection, _record):
        cursor = connection.cursor()
        cursor.execute('PRAGMA busy_timeout=30000')
        # Do not change an existing database's persistent journal mode here.
        # New SQLite files default to DELETE; WAL requires storage validation.
        cursor.execute('PRAGMA synchronous=FULL')
        cursor.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
