#!/usr/bin/env python3
"""
Beregn TSS for alle aktiviteter fra 2008 og fremover.
Dette sikrer at alle aktiviteter har TSS, enten fra EPOC eller estimert.
"""

import sys
import os
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from app.database.session import SessionLocal
from app.database.models.activity import Activity
from app.services.training_stress_service import TrainingStressService
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def calculate_tss_from_2008():
    """
    Beregn TSS for alle aktiviteter fra 2008 og fremover.
    """
    db = SessionLocal()
    
    try:
        # Initialiser TSS-service
        logger.info("Initialiserer TSS-service...")
        tss_service = TrainingStressService(db)
        
        # Hent alle aktiviteter fra 2008 og fremover, sortert etter dato (eldste først)
        logger.info("Henter alle aktiviteter fra 2008 og fremover...")
        start_date = datetime(2008, 1, 1, tzinfo=timezone.utc)
        
        activities = db.query(Activity).filter(
            Activity.start_time >= start_date
        ).order_by(Activity.start_time.asc()).all()
        
        logger.info(f"Fant {len(activities)} aktiviteter fra 2008 og fremover")
        
        if not activities:
            logger.warning("Ingen aktiviteter funnet")
            return
        
        # Prosesser aktivitetene
        updated_count = 0
        skipped_count = 0
        failed_count = 0
        already_has_tss = 0
        
        for i, activity in enumerate(activities, 1):
            activity_id = activity.activity_id
            activity_date = activity.start_time.date()
            
            # Sjekk om aktiviteten allerede har TSS
            if activity.training_stress_score is not None and activity.training_stress_score > 0:
                already_has_tss += 1
                if i % 100 == 0:
                    logger.debug(f"Prosesserer aktivitet {i}/{len(activities)}: {activity_id} ({activity_date}) - har allerede TSS={activity.training_stress_score}")
                continue
            
            logger.info(f"Prosesserer aktivitet {i}/{len(activities)}: {activity_id} ({activity_date}) - {activity.activity_name}")
            
            try:
                # Beregn TSS
                tss = tss_service.calculate_tss_for_activity(activity)
                
                if tss and tss > 0:
                    old_tss = activity.training_stress_score
                    activity.training_stress_score = tss
                    
                    # Commit hver 50. aktivitet for å unngå for store transaksjoner
                    if i % 50 == 0:
                        db.commit()
                        logger.info(f"  ✅ Committet {i} aktiviteter så langt...")
                    
                    updated_count += 1
                    logger.info(f"  ✅ Oppdatert: TSS={tss} (var {old_tss})")
                else:
                    skipped_count += 1
                    logger.warning(f"  ⚠️  Ingen TSS beregnet (resultat: {tss})")
                    
            except Exception as e:
                failed_count += 1
                logger.error(f"  ❌ Feil ved beregning av TSS for aktivitet {activity_id}: {e}")
                # Fortsett med neste aktivitet
                continue
        
        # Commit resterende endringer
        db.commit()
        
        logger.info("=" * 80)
        logger.info(f"✅ Ferdig! Oppdatert {updated_count} aktiviteter med TSS")
        logger.info(f"   Allerede hadde TSS: {already_has_tss} aktiviteter")
        logger.info(f"   Hoppet over {skipped_count} aktiviteter (ingen TSS beregnet)")
        logger.info(f"   Feilet {failed_count} aktiviteter")
        logger.info(f"   Totalt prosessert: {len(activities)} aktiviteter")
        
        # Verifiser endringene
        activities_with_tss = db.query(Activity).filter(
            Activity.start_time >= start_date,
            Activity.training_stress_score.isnot(None),
            Activity.training_stress_score > 0
        ).count()
        
        logger.info(f"   Totalt {activities_with_tss} aktiviteter har nå TSS-data")
        
        # Vis statistikk over TSS-kilder
        activities_with_epoc = db.query(Activity).filter(
            Activity.start_time >= start_date,
            Activity.epoc.isnot(None),
            Activity.epoc > 0
        ).count()
        
        logger.info(f"   Aktiviteter med EPOC-data: {activities_with_epoc}")
        logger.info(f"   Aktiviteter med estimert TSS: {activities_with_tss - activities_with_epoc}")
        
    except Exception as e:
        logger.error(f"Feil ved beregning av TSS: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logger.info("🚀 Starter beregning av TSS for alle aktiviteter fra 2008...")
    logger.info("📝 Dette kan ta lang tid avhengig av antall aktiviteter...")
    
    calculate_tss_from_2008()
    
    logger.info("✅ Beregning fullført!")

