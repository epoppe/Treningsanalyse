from sqlalchemy import create_engine, event, pool
from sqlalchemy.orm import sessionmaker
from ..config import settings
import logging

logger = logging.getLogger(__name__)

# Oppsett av database-URL fra innstillinger
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

# Optimaliser SQLite med connection pooling og PRAGMA-settings
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    # Bruk StaticPool for SQLite for å holde én connection åpen
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={
            "check_same_thread": False,
            "timeout": 30  # Timeout for locked database
        },
        poolclass=pool.StaticPool,  # Viktig for SQLite i single-process app
        echo=False  # Sett til True for SQL query debugging
    )
    
    # Konfigurer SQLite med PRAGMA for optimal ytelse
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        # Aktiver WAL (Write-Ahead Logging) mode for bedre concurrency
        cursor.execute("PRAGMA journal_mode=WAL")
        # Raskere synkronisering (trygt for de fleste bruksområder)
        cursor.execute("PRAGMA synchronous=NORMAL")
        # Øk cache-størrelse til 64MB (fra standard 2MB)
        cursor.execute("PRAGMA cache_size=-64000")
        # Bruk minne for midlertidige tabeller
        cursor.execute("PRAGMA temp_store=MEMORY")
        # Optimaliser for ytelse
        cursor.execute("PRAGMA optimize")
        cursor.close()
        logger.debug("SQLite PRAGMA settings applied for optimal performance")
else:
    # For andre databaser (PostgreSQL, etc.)
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_pre_ping=True,  # Verifiser connections før bruk
        pool_size=10,
        max_overflow=20
    )

# Opprett en SessionLocal-klasse som vi vil bruke for å lage database-sesjoner
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency for å få database-sesjon
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
