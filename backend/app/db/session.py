from sqlalchemy import event
from sqlmodel import create_engine, Session
from app.core.config import settings

# Get database URL from config
DATABASE_URL = settings.database.get_database_url()

# Create the database engine (SQLite needs this parameter to allow multi-threaded access)
engine = create_engine(
    DATABASE_URL,
    echo=settings.database.echo,
    connect_args={"check_same_thread": False}
)

if DATABASE_URL.startswith("sqlite"):
    # WAL + busy_timeout: concurrent writers (API + background workflow threads)
    # otherwise easily hit "database is locked" on the default rollback journal.
    @event.listens_for(engine, "connect")
    def _sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


def get_session():
    """
    FastAPI dependency that provides a transactional database session.
    It ensures that the session is committed on success and rolled back on error.
    """
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close() 