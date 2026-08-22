from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
import logging
from dotenv import load_dotenv
from contextlib import asynccontextmanager

from .services.garmin_client import GarminClient
from .storage import DataStorage
from .config import settings
from .routers import activities, analysis, analytics, garmin_data, health, readiness_v1, sync, training_readiness, training_stress, power, cache, bulk, factor_relationships, route_analysis, analysis_workspace
from .database.session import engine as db_engine, SessionLocal
from .database.migrations import get_schema_version, run_migrations
from .dependencies import get_db, get_garmin_client, get_data_storage
from .services.sync_service import SyncService
from .middleware.cache_headers import CacheHeadersMiddleware
from .middleware.security_headers import SecurityHeadersMiddleware

# Konfigurer logging 
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Last miljøvariabler
load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialiserer applikasjonen ved oppstart."""
    logger.info("Starte applikasjonen... (v2 - med nye normaliseringer)")
    
    # Logg konfigurasjonsdetaljer (aldri full e-post/passord)
    logger.info("Bruker Garmin e-post: %s", settings.masked_garmin_email())
    logger.info(f"Bruker token-mappe: {settings.TOKEN_DIR}")
    logger.info(f"Bruker datalagringsmappe: {settings.DATA_DIR}")
    
    # Initialiser Garmin-klienten
    logger.info("Initialiserer Garmin-klienten...")
    garmin_client = GarminClient(
        email=settings.GARMIN_EMAIL,
        password=settings.GARMIN_PASSWORD,
        token_dir=settings.TOKEN_DIR
    )

    # Hopp over innlogging ved oppstart hvis SKIP_GARMIN_INIT er satt (dev/test).
    # Innlogging skjer da lazy ved første synk. Uten dette vil garminconnect kjøre
    # sine (trege, anti-WAF-forsinkede) innloggingsstrategier ved hver oppstart.
    if settings.SKIP_GARMIN_INIT:
        logger.info("SKIP_GARMIN_INIT satt – hopper over Garmin-innlogging ved oppstart.")
        app.state.garmin_client = garmin_client
    else:
        success = await garmin_client.initialize()

        if success:
            logger.info("Garmin-klient initialisert vellykket.")
            app.state.garmin_client = garmin_client
        else:
            logger.warning("Kunne ikke initialisere Garmin-klienten.")
            app.state.garmin_client = garmin_client
    
    # Initialiser DataStorage
    app.state.data_storage = DataStorage(settings.DATA_DIR)
    logger.info("DataStorage initialisert.")

    # Kjør Alembic-migrasjoner (erstatter create_all + manuelle migrate_*)
    try:
        revision = run_migrations(db_engine, settings.DATABASE_URL)
        app.state.schema_version = revision
        logger.info("Database-schema migrert til revisjon %s", revision)
    except Exception as exc:
        logger.error("Database-migrasjon feilet: %s", exc)
        raise

    yield
    logger.info("Stopper applikasjonen...")

# Opprett FastAPI app
app = FastAPI(lifespan=lifespan)

# Konfigurer CORS (origins fra Settings / CORS_ORIGINS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
)

# Sikkerhetsheaders + HTTP Cache Headers
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CacheHeadersMiddleware)

# Inkluder alle routere med korrekt prefix
app.include_router(activities.router, prefix="/api", tags=["Aktiviteter"])
app.include_router(garmin_data.router, prefix="/api", tags=["Garmin Data"])
app.include_router(sync.router, prefix="/api/sync", tags=["sync"])

app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(analysis_workspace.router, prefix="/api/analysis", tags=["analysis-workspace"])
app.include_router(route_analysis.router, prefix="/api/analysis", tags=["route-analysis"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(factor_relationships.router, prefix="/api/analysis", tags=["factor-relationships"])
app.include_router(health.router, prefix="/api/health", tags=["health"])
app.include_router(training_readiness.router, prefix="/api", tags=["Training Readiness"])
app.include_router(readiness_v1.router)
app.include_router(training_stress.router, prefix="/api", tags=["Training Stress"])
app.include_router(power.router, prefix="/api", tags=["Power"])
app.include_router(cache.router, prefix="/api", tags=["Cache"])
app.include_router(bulk.router, prefix="/api", tags=["Bulk Operations"])

@app.get("/")
def read_root():
    return {"message": "Welcome to the Treningsanalyse API"}


@app.get("/health")
def health_check():
    """Enkel health check med schema-versjon (Alembic-revisjon)."""
    schema = get_schema_version(db_engine)
    return {
        "status": "ok" if schema.get("schema_at_head") else "degraded",
        **schema,
    }


@app.get("/health/live")
def health_live():
    """Liveness: prosessen svarer."""
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready():
    """Readiness: DB + schema på head."""
    from sqlalchemy import text

    checks: dict = {}
    try:
        with db_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    schema = get_schema_version(db_engine)
    checks["schema"] = "ok" if schema.get("schema_at_head") else "degraded"
    checks["schema_version"] = schema.get("schema_version")

    data_dir_ok = False
    try:
        from pathlib import Path
        data_dir_ok = Path(settings.DATA_DIR).exists()
    except Exception:
        data_dir_ok = False
    checks["data_dir"] = "ok" if data_dir_ok else "missing"

    ready = checks["database"] == "ok" and checks["schema"] == "ok" and checks["data_dir"] == "ok"
    return {"status": "ok" if ready else "not_ready", "checks": checks}


@app.get("/health/data")
def health_data(db: Session = Depends(get_db)):
    """Dataintegritet: manglende datoer, pace, distanse, HR, VO2, duplikater."""
    from .services.data_integrity_service import build_data_integrity_report

    return build_data_integrity_report(db)


@app.get("/api/debug/db-info")
def debug_db_info(db: Session = Depends(get_db)):
    """Debug: vis hvilken database som brukes og antall aktiviteter."""
    from .database.models.activity import Activity
    from .config import settings
    count = db.query(Activity).count()
    return {
        "database_url": settings.DATABASE_URL[:80] + "..." if len(settings.DATABASE_URL) > 80 else settings.DATABASE_URL,
        "activity_count": count,
        "data_dir": settings.DATA_DIR,
        **get_schema_version(db_engine),
    }
