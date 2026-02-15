"""Debug: Hent én dag med metrics og skriv ut responsestrukturen."""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv()

import garth
from garth.exc import GarthHTTPError
from app.services.garmin_client import GarminClient
from app.config import settings


async def main():
    client = GarminClient(
        email=settings.GARMIN_EMAIL,
        password=settings.GARMIN_PASSWORD,
        token_dir=settings.TOKEN_DIR
    )
    await client.initialize()
    
    date_str = "2025-02-01"
    print(f"Henter usersummary for {date_str}...")
    
    try:
        raw = await asyncio.to_thread(
            garth.connectapi,
            f"/usersummary-service/usersummary/daily/{garth.client.username}",
            params={"calendarDate": date_str}
        )
        print("Rå respons type:", type(raw))
        if isinstance(raw, dict):
            keys = list(raw.keys())
            print("Antall nøkler:", len(keys))
            hill_keys = [k for k in keys if 'hill' in k.lower() or 'endurance' in k.lower() or 'morning' in k.lower() or 'readiness' in k.lower()]
            print("Hill/Endurance/Morning/Readiness nøkler:", hill_keys)
            if 'allMetrics' in raw:
                am = raw['allMetrics']
                print("allMetrics type:", type(am))
                if isinstance(am, dict):
                    print("allMetrics nøkler:", list(am.keys())[:10])
                    mm = am.get('metricsMap', {})
                    print("metricsMap antall:", len(mm) if mm else 0)
                    for i, (k, v) in enumerate(list(mm.items())[:5]):
                        print(f"  {k}: type={type(v).__name__}, value={type(v.get('value') if isinstance(v, dict) else 'N/A').__name__}")
        print(json.dumps(raw, indent=2, default=str)[:3000])
    except Exception as e:
        print(f"Feil: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
