import sqlite3
from pathlib import Path

# Finn database-filen
db_path = Path("data/treningsanalyse.db")

def reset_body_battery_cache():
    """
    Nullstiller body_battery_start cache slik at nye verdier blir beregnet.
    """
    if not db_path.exists():
        print(f"Database ikke funnet: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Oppdater alle body_battery_start verdier til NULL
        cursor.execute("UPDATE activities SET body_battery_start = NULL;")
        rows_affected = cursor.rowcount
        conn.commit()
        
        print(f"✅ Nullstilte Body Battery-cache for {rows_affected} aktiviteter")
        print("🔄 Neste gang Body Battery hentes vil nye, varierende verdier beregnes")
        
        return True
        
    except Exception as e:
        print(f"❌ Feil ved nullstilling av cache: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    print("Nullstiller Body Battery-cache...")
    success = reset_body_battery_cache()
    
    if success:
        print("\n🎉 Cache nullstilt! Refresh frontend-siden for å se nye verdier.")
    else:
        print("\n❌ Nullstilling av cache feilet!") 