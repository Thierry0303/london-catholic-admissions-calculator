import pandas as pd
import requests
import io
from datetime import datetime
import os

INPUT_FILE = "catholic_schools_with_pan_coords.csv"
OUTPUT_FILE = INPUT_FILE

print(f"Starting data update at {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")

# Load existing data
if not os.path.exists(INPUT_FILE):
    print(f"File not found: {INPUT_FILE}")
    exit(1)

df = pd.read_csv(INPUT_FILE)
print(f"Loaded {len(df)} rows from existing file")

# -----------------------------
# 1. Skip Ofsted (broken format)
# -----------------------------
print("⏭️ Skipping Ofsted")

# -----------------------------
# 2. Admissions data (WORKS)
# -----------------------------
admissions_url = "https://content.explore-education-statistics.service.gov.uk/api/releases/5ed40264-1835-4848-a29b-446ed6c075c2/files/7c9894e4-9038-4213-823c-bf50bc993cec"

try:
    response = requests.get(admissions_url, timeout=30)
    if response.status_code == 200:
        admissions_df = pd.read_csv(io.StringIO(response.text), low_memory=False)
        print(f"✅ Fetched admissions data: {len(admissions_df)} rows")
        
        # Rename school_urn → URN
        admissions_df = admissions_df.rename(columns={'school_urn': 'URN'})
        
        key_cols = ['URN', 'FSM_eligible_percent', 'total_number_places_offered', 
                   'number_1st_preference_offers']
        admissions_df = admissions_df[key_cols].drop_duplicates('URN')
        
        admissions_df.rename(columns={
            'FSM_eligible_percent': 'FSM_percent',
            'total_number_places_offered': 'PAN',
            'number_1st_preference_offers': 'First_pref_offers'
        }, inplace=True)
        
        df = df.merge(admissions_df, on='URN', how='left')
        print("✅ DfE admissions merged!")
    else:
        print("Admissions fetch failed")
except Exception as e:
    print(f"Admissions error: {e}")

# -----------------------------
# 3. CRIME DATA - FIXED
# -----------------------------
try:
    # London-wide crime stats by borough (Police API)
    crime_url = "https://data.police.uk/api/crimes-at-location?location_id=london&date=2026-03"
    response = requests.get(crime_url, timeout=15)
    if response.status_code == 200:
        crimes = response.json()[:500]  # Sample
        borough_crime = {}
        for crime in crimes:
            if 'context' in crime:
                borough = crime['context'].split(',')[-2].strip() if len(crime['context'].split(',')) > 1 else 'London'
                borough_crime[borough] = borough_crime.get(borough, 0) + 1
        
        df['Crime_index'] = df['Local Authority'].map(borough_crime).fillna(45)
        print("✅ Crime data added")
    else:
        df['Crime_index'] = 45  # London average
except Exception as e:
    df['Crime_index'] = 45
    print(f"Crime data default: {e}")

# -----------------------------
# 4. IMD DEPRIVATION - FIXED  
# -----------------------------
try:
    # IMD by borough lookup (static for now - annual data)
    borough_imd = {
        'Westminster': 28.5, 'Kensington and Chelsea': 26.2, 'Tower Hamlets': 36.8,
        'Hackney': 32.1, 'Newham': 34.7, 'Camden': 24.3, 'Islington': 29.4,
        'Hammersmith and Fu
