#!/usr/bin/env python3
"""
Script for å sjekke parquet-filen direkte uten kompliserte imports
"""

import os
import pandas as pd

def simple_parquet_check():
    """Sjekk activity_details.parquet direkte"""
    
    parquet_file = os.path.join("data", "activity_details.parquet")
    
    if not os.path.exists(parquet_file):
        print(f"❌ Parquet-fil ikke funnet: {parquet_file}")
        return
    
    try:
        # Last parquet-filen direkte
        df = pd.read_parquet(parquet_file)
        
        print(f"📋 Activity Details Parquet Oversikt:")
        print(f"Total rader: {len(df):,}")
        print(f"Kolonner: {list(df.columns)}")
        
        if 'activity_id' in df.columns:
            unique_activities = df['activity_id'].nunique()
            print(f"Unike aktiviteter: {unique_activities:,}")
            
            # Vis noen aktivitets-IDer
            sample_ids = df['activity_id'].unique()[:10]
            print(f"Eksempler på aktivitets-IDer: {sample_ids}")
            
            # Sjekk dato-kolonner hvis de finnes
            date_columns = [col for col in df.columns if 'time' in col.lower() or 'date' in col.lower()]
            if date_columns:
                print(f"Dato-kolonner: {date_columns}")
                for col in date_columns[:2]:  # Bare de første 2
                    if col in df.columns:
                        try:
                            min_val = df[col].min()
                            max_val = df[col].max()
                            print(f"  {col}: {min_val} til {max_val}")
                        except:
                            print(f"  {col}: Kunne ikke beregne min/max")
        
        print(f"\n📊 De første 3 radene:")
        print(df.head(3))
    
    except Exception as e:
        print(f"❌ Feil ved lasting av parquet-fil: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    simple_parquet_check() 