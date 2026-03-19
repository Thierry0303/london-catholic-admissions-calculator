import pandas as pd
import requests
from datetime import datetime
import os
import io

INPUT_FILE = "catholic_schools_with_pan_coords.csv"
OUTPUT_FILE = INPUT_FILE

print(f"Starting data update at {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")

# Load existing data (fallback if fetches fail)
if not os.path.exists(INPUT_FILE):
    print(f"File not found: {INPUT_FILE}. Exiting.")
    exit(1)

df = pd.read_csv(INPUT_FILE)
print(f"Loaded {len(df)} rows from existing file")

# -----------------------------
# 1. Fetch DfE Schools CSV (daily updated, has URN + FSM/Capacity)
# -----------------------------
schools_url = "https://ea-edubase-api-prod.azurewebsites.net/edubase/all"
try:
    response = requests.get(schools_url, timeout=30)
    if response.status_code == 200:
        schools_df = pd.read_csv(io.StringIO(response.text), low_memory=False)
        print(f"Successfully fetched schools data: {len(schools_df)} rows")
        
        # Filter to open schools only, select key columns
        schools_df = schools_df[schools_df['EstablishmentStatus (name)'] == 'Open']
        key_cols = ['URN', 'EstablishmentName', 'LA (name)', 'PhaseOfEducation (name)', 
                   'PercentageFSM', 'SchoolCapacity', 'NumberOfPupils', 'Postcode']
        schools_df = schools_df[key_cols].drop_duplicates(subset='URN')
        
        # Rename for consistency
        schools_df.rename(columns={
            'PercentageFSM': 'FSM_percent',
            'SchoolCapacity': 'PAN',
            'NumberOfPupils': 'Current_roll',
            'LA (name)': 'Local Authority',
            'EstablishmentName': 'School Name'
        }, inplace=True)
        
        # Merge into main df
        merge_cols = ['URN', 'FSM_percent', 'PAN', 'Current_roll']
        df = df.merge(schools_df[merge_cols], on='URN', how='left', suffixes=('', '_new'))
        
        # Keep new values, drop old if they exist
        for col in merge_cols[1:]:
            if f'{col}_new' in df.columns:
                df[col] = df[f'{col}_new']
                df.drop(columns=[f'{col}_new'], inplace=True)
        
        print("Schools data (FSM, capacity, pupils) merged/updated")
    else:
        print(f"Schools fetch failed (status {response.status_code})")
except Exception as e:
    print(f"Schools fetch error: {e} - using existing data")

# -----------------------------
# 2. Skip Ofsted (problematic) - use schools CSV Ofsted data instead if needed
# -----------------------------

# -----------------------------
# 3. Skip LA-level admissions (no URN) - find school-level CSV later
# -----------------------------

# -----------------------------
# Processing (cleaning, filter, recalcs, freshness)
# -----------------------------
print(f"Rows before processing: {len(df)}")

# Filter to Catholic only
if 'Religious Character (name)' in df.columns:
    df = df[df['Religious Character (name)'].str.contains(r'Catholic|Roman Catholic', case=False, na=False, regex=True)]
    print(f"After Catholic filter: {len(df)} rows")

# Convert numerics
numeric_cols = ['PAN', 'Current_roll', 'FSM_percent', 'Latitude', 'Longitude']
for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

# Calculate oversubscription if PAN data exists
if 'PAN' in df.columns and 'Current_roll' in df.columns:
    df['Oversub Ratio'] = df['Current_roll'] / df['PAN'].replace(0, pd.NA)

# Freshness timestamp
df['Last Updated'] = datetime.now().strftime('%Y-%m-%d')

# Sort and dedupe
df = df.sort_values(by=['Local Authority', 'School Name']).drop_duplicates(subset=['URN'])

# Save
df.to_csv(OUTPUT_FILE, index=False)
print(f"✅ Updated file saved with {len(df)} rows")
