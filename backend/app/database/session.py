from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from ..config import settings

# Oppsett av database-URL fra innstillinger
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

# Opprett database-motoren
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False} # Nødvendig for SQLite
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
