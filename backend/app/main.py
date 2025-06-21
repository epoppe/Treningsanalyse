from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from dotenv import load_dotenv
from contextlib import asynccontextmanager

from .services.garmin_client import GarminClient
from .storage import DataStorage
from .config import settings
from .routers import garmin_data, sync, activities, sleep, analysis

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
    
    yield
    logger.info("Stopper applikasjonen...")

# Opprett FastAPI app
app = FastAPI(lifespan=lifespan)

# Legg til CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inkluder alle routere med korrekt prefix
app.include_router(activities.router, prefix="/api", tags=["Aktiviteter"])
app.include_router(garmin_data.router, prefix="/api", tags=["Garmin Data"])
app.include_router(sync.router, prefix="/api", tags=["Synkronisering"])
app.include_router(sleep.router, prefix="/api", tags=["Søvn"])
app.include_router(analysis.router, prefix="/api", tags=["Analyse"])
