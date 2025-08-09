#!/usr/bin/env python3
"""
Script for å opprette sync_state-tabellen i databasen
"""

from pathlib import Path
import sqlite3
import sys


project_root = Path(__file__).resolve().parent
db_path = project_root / "data" / "treningsanalyse.db"


def create_sync_state_table():
    if not db_path.exists():
        print(f"Database ikke funnet: {db_path}")
        return False

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Sjekk eksisterende tabell
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sync_state';")
        if cursor.fetchone():
            print("sync_state-tabellen eksisterer allerede!")
            return True

        cursor.execute(
            """
            CREATE TABLE sync_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key VARCHAR(100) NOT NULL UNIQUE,
                last_synced_date DATE,
                last_synced_at DATETIME,
                meta TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        cursor.execute("CREATE UNIQUE INDEX idx_sync_state_key ON sync_state(key);")
        cursor.execute("CREATE INDEX idx_sync_state_last_synced_date ON sync_state(last_synced_date);")

        conn.commit()
        print("✅ Opprettet sync_state-tabellen med indekser")
        return True
    except Exception as e:
        print(f"❌ Feil ved opprettelse av tabell: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()


if __name__ == "__main__":
    print("🚀 Oppretter sync_state-tabell...")
    ok = create_sync_state_table()
    if ok:
        print("✅ sync_state-tabell opprettet vellykket!")
    else:
        print("❌ Feil ved opprettelse av sync_state-tabell")
        sys.exit(1)


