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
# 1. Ofsted data (skip - broken CSV format)
# -----------------------------
print("⏭️ Skipping Ofsted (broken CSV format)")

# -----------------------------
# 2. Admissions data (WORKS! Uses school_urn)
# -----------------------------
admissions_url = "https://content.explore-education-statistics.service.gov.uk/api/releases/5ed40264-1835-4848-a29b-446ed6c075c2/files/7c9894e4-9038-4213-823c-bf50bc993cec"

try:
    response = requests.get(admissions_url, timeout=30)
    if response.status_code == 200:
        admissions_df = pd.read_csv(io.StringIO(response.text), low_memory=False)
        print(f"Successfully fetched admissions data: {len(admissions_df)} rows")
        
        # RENAME school_urn → URN for merge
        admissions_df = admissions_df.rename(columns={'school_urn': 'URN'})
        
        # Key columns with friendly names
        key_cols = ['URN', 'FSM_eligible_percent', 'total_number_places_offered', 
                   'number_1st_preference_offers', 'number_preferred_offers']
        admissions_df = admissions_df[key_cols].drop_duplicates(subset='URN')
        
        admissions_df.rename(columns={
            'FSM_eligible_percent': 'FSM_percent',
            'total_number_places_offered': 'PAN',
            'number_1st_preference_offers': 'First_pref_offers',
            'number_preferred_offers': 'Preferred_offers'
        }, inplace=True)
        
        # Merge into main dataframe
        df = df.merge(admissions_df, on='URN', how='left', suffixes=('', '_new'))
        
        # Keep new values, drop duplicates
        for col in ['FSM_percent', 'PAN', 'First_pref_offers', 'Preferred_offers']:
            if f'{col}_new' in df.columns:
                df[col] = df[f'{col}_new']
                df = df.drop(columns=[f'{col}_new'])
        
        print("✅ REAL DfE admissions data merged!")
    else:
        print(f"Admissions fetch failed (status {response.status_code})")
except Exception as e:
    print(f"Admissions error: {e} - using defaults")

# -----------------------------
# Processing & calculations
# -----------------------------
print(f"Rows before processing: {len(df)}")

# Convert to numeric safely
numeric_cols = ['FSM_percent', 'PAN', 'First_pref_offers', 'Preferred_offers', 
                'Latitude', 'Longitude']
for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

# Calculate oversubscription ratio
if 'PAN' in df.columns:
    df['PAN'] = df['PAN'].fillna(210)  # Default PAN
    df['Oversub Ratio'] = df['First_pref_offers'].fillna(df['PAN'] * 1.1) / df['PAN']

# Add freshness timestamp
df['Last Updated'] = datetime.now().strftime('%Y-%m-%d')

# Clean and sort
if 'Religious Character (name)' in df.columns:
    df = df[df['Religious Character (name)'].str.contains(r'Catholic|Roman Catholic', case=False, na=False)]
    
df = df.sort_values(['Local Authority', 'School Name']).drop_duplicates(subset=['URN'])

# Save
df.to_csv(OUTPUT_FILE, index=False)
print(f"✅ Updated file saved with {len(df)} rows")
print(f"📊 FSM avg: {df['FSM_percent'].mean():.1f}%, PAN avg: {df['PAN'].mean():.0f}")
