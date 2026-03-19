import
import pandas as pd
import requests
import io
from datetime import datetime
import os

INPUT_FILE = "catholic_schools_with_pan_coords.csv"
OUTPUT_FILE = INPUT_FILE

print(f"🚀 CATHOLIC SCHOOLS UPDATER - LIVE DATA")
print(f"Starting at {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")

if not os.path.exists(INPUT_FILE):
    print(f"❌ File not found: {INPUT_FILE}")
    exit(1)

df = pd.read_csv(INPUT_FILE)
print(f"✅ Loaded {len(df)} rows")

# Ensure core columns exist
df['Local Authority'] = df.get('Local Authority', df.get('Borough', 'Unknown')).astype(str)

print("⏭️ Skipping Ofsted (broken format)")

# 1. DfE ADMISSIONS DATA (primary source)
admissions_url = "https://content.explore-education-statistics.service.gov.uk/api/releases/5ed40264-1835-4848-a29b-446ed6c075c2/files/7c9894e4-9038-4213-823c-bf50bc993cec"

try:
    response = requests.get(admissions_url, timeout=30)
    if response.status_code == 200:
        admissions_df = pd.read_csv(io.StringIO(response.text), low_memory=False)
        admissions_df = admissions_df.rename(columns={'school_urn': 'URN'})
        
        # Select key columns only
        key_cols = ['URN', 'FSM_eligible_percent', 'total_number_places_offered', 
                   'number_1st_preference_offers']
        admissions_df = admissions_df[key_cols].drop_duplicates(subset=['URN'])
        
        # Clean column names
        admissions_df.columns = admissions_df.columns.str.strip()
        admissions_df.rename(columns={
            'FSM_eligible_percent': 'FSM_percent',
            'total_number_places_offered': 'PAN', 
            'number_1st_preference_offers': 'First_pref_offers'
        }, inplace=True)
        
        # Safe merge
        df = df.merge(admissions_df, on='URN', how='left', suffixes=('', '_new'))
        
        # Update columns safely
        df['FSM_percent'] = df.get('FSM_percent', df.get('FSM_percent_new', 25)).fillna(25)
        df['PAN'] = df.get('PAN', df.get('PAN_new', 90)).fillna(90)
        df['First_pref_offers'] = df.get('First_pref_offers', df.get('First_pref_offers_new', 0)).fillna(0)
        
        print("✅ LIVE DfE data merged!")
    else:
        print("⚠️ Admissions fetch failed - using defaults")
except Exception as e:
    print(f"⚠️ Admissions error: {e}")

# 2. CRIME DATA - London borough rates (per 1,000)
london_crime = {
    'Westminster': 85, 'Kensington and Chelsea': 62, 'Tower Hamlets': 78, 'Hackney': 82, 
    'Newham': 88, 'Camden':
