import pandas as pd
import requests
from datetime import datetime
import os
import io  # for reading CSV from memory

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
# 1. Try to fetch latest Ofsted inspections CSV (monthly)
# -----------------------------
ofsted_url = "https://assets.publishing.service.gov.uk/media/69affb1cc78869bf8eb8a5c5/Management_information_-_state-funded_schools_-_latest_inspections_as_at_28_Feb_2026.csv"
# Note: Update this URL manually when new month releases (or add page scraping later)
# Pattern: replace date in filename, media ID changes per release

try:
    response = requests.get(ofsted_url, timeout=30)
    if response.status_code == 200:
        ofsted_df = pd.read_csv(io.StringIO(response.text))
        print(f"Successfully fetched Ofsted data: {len(ofsted_df)} rows")
        
        # Key columns: URN, Overall effectiveness (numeric), map to text
        if 'URN' in ofsted_df.columns and 'Overall effectiveness' in ofsted_df.columns:
            ofsted_df = ofsted_df[['URN', 'Overall effectiveness']].drop_duplicates(subset='URN')
            ofsted_df['Ofsted Rating'] = ofsted_df['Overall effectiveness'].map(
                {1: 'Outstanding', 2: 'Good', 3: 'Requires Improvement', 4: 'Inadequate'}
            ).fillna('Not available')
            # Merge into main df
            df = df.drop(columns=['Ofsted Rating'], errors='ignore')  # remove old if exists
            df = df.merge(ofsted_df[['URN', 'Ofsted Rating']], on='URN', how='left')
            print("Ofsted ratings merged/updated")
        else:
            print("Ofsted CSV missing expected columns")
    else:
        print(f"Ofsted fetch failed (status {response.status_code}) - using existing data")
except Exception as e:
    print(f"Ofsted fetch error: {e} - skipping and using existing data")

# -----------------------------
# 2. Try to fetch latest admissions/applications CSV (annual ~June)
# -----------------------------
admissions_url = "https://content.explore-education-statistics.service.gov.uk/api/releases/5ed40264-1835-4848-a29b-446ed6c075c2/files/7c9894e4-9038-4213-823c-bf50bc993cec"
# This is 2025 data; for 2026, URL will change (new release ID). Check page in June 2026 and update URL here.
# Or add scraping of https://explore-education-statistics.service.gov.uk/find-statistics/primary-and-secondary-school-applications-and-offers to find newest link.

try:
    response = requests.get(admissions_url, timeout=30)
    if response.status_code == 200:
        admissions_df = pd.read_csv(io.StringIO(response.text))
        print(f"Successfully fetched admissions data: {len(admissions_df)} rows")
        
        # Assume columns like URN, PAN, Applications, Offers (adapt based on actual CSV)
        key_admissions_cols = ['URN', 'PAN 2025', 'Apps Received 2025', 'Offers Made 2025']  # adjust names
        available_cols = [col for col in key_admissions_cols if col in admissions_df.columns]
        if 'URN' in admissions_df.columns and len(available_cols) > 1:
            admissions_df = admissions_df[available_cols].drop_duplicates(subset='URN')
            # Merge (overwrite old admissions columns)
            for col in available_cols[1:]:  # skip URN
                if col in df.columns:
                    df = df.drop(columns=[col], errors='ignore')
                df = df.merge(admissions_df[['URN', col]], on='URN', how='left')
            print("Admissions data merged/updated")
        else:
            print("Admissions CSV missing URN or key columns")
    else:
        print(f"Admissions fetch failed (status {response.status_code}) - skipping")
except Exception as e:
    print(f"Admissions fetch error: {e} - skipping")

# -----------------------------
# Your original processing (cleaning, filter, recalcs, freshness)
# -----------------------------
print(f"Rows before processing: {len(df)}")

if 'Religious Character (name)' in df.columns:
    df = df[df['Religious Character (name)'].str.contains(r'Catholic|Roman Catholic', case=False, na=False, regex=True)]
    print(f"After Catholic filter: {len(df)} rows")

numeric_cols = ['PAN 2025', 'Apps Received 2025', 'Offers Made 2025', '1st Pref Rate %', 'Oversub Ratio', 'Latitude', 'Longitude']
for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

if all(col in df.columns for col in ['Apps Received 2025', 'PAN 2025']):
    df['Oversub Ratio'] = df['Apps Received 2025'] / df['PAN 2025'].replace(0, pd.NA)

df['Last Updated'] = datetime.now().strftime('%Y-%m-%d')

df = df.sort_values(by=['Local Authority', 'School Name']).drop_duplicates(subset=['URN'])

df.to_csv(OUTPUT_FILE, index=False)
print(f"✅ Updated file saved with {len(df)} rows")
