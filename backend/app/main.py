from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import logging
from dotenv import load_dotenv
from contextlib import asynccontextmanager

from .services.garmin_client import GarminClient
from .storage import DataStorage
from .config import settings
from .routers import activities, analysis, garmin_data, health, sync, training_readiness, training_stress, power
from .database.models.activity import Base
from .database.session import engine as db_engine, SessionLocal
from .database.models import activity as activity_model
from .dependencies import get_db, get_garmin_client, get_data_storage
from .services.sync_service import SyncService

# Konfigurer logging 
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Last miljøvariabler
load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialiserer applikasjonen ved oppstart."""
    logger.info("Starte applikasjonen...")
    
    # Logg konfigurasjonsdetaljer
    logger.info(f"Bruker Garmin e-post: {settings.GARMIN_EMAIL[:4]}...")
    logger.info(f"Bruker token-mappe: {settings.TOKEN_DIR}")
    logger.info(f"Bruker datalagringsmappe: {settings.DATA_DIR}")
    
    # Initialiser Garmin-klienten
    logger.info("Initialiserer Garmin-klienten...")
    garmin_client = GarminClient(
        email=settings.GARMIN_EMAIL,
        password=settings.GARMIN_PASSWORD,
        token_dir=settings.TOKEN_DIR
    )
    
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
    
    # Opprett databasetabeller
    Base.metadata.create_all(bind=db_engine)
    logger.info("Databasetabeller opprettet/verifisert.")
    
    yield
    logger.info("Stopper applikasjonen...")

# Opprett FastAPI app
app = FastAPI(lifespan=lifespan)

# Konfigurer CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Frontend-adressen
        "http://localhost:3001",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inkluder alle routere med korrekt prefix
app.include_router(activities.router, prefix="/api", tags=["Aktiviteter"])
app.include_router(garmin_data.router, prefix="/api", tags=["Garmin Data"])
app.include_router(sync.router, prefix="/api/sync", tags=["sync"])

app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(health.router, prefix="/api/health", tags=["health"])
app.include_router(training_readiness.router, prefix="/api", tags=["Training Readiness"])
app.include_router(training_stress.router, prefix="/api", tags=["Training Stress"])
app.include_router(power.router, prefix="/api", tags=["Power"])

@app.get("/")
def read_root():
    return {"message": "Welcome to the Treningsanalyse API"}
