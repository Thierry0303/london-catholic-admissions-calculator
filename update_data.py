import pandas as pd
import requests
from datetime import datetime
import os
import io

INPUT_FILE = "catholic_schools_with_pan_coords.csv"
OUTPUT_FILE = INPUT_FILE

print(f"Starting data update at {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")

if not os.path.exists(INPUT_FILE):
    print(f"File not found: {INPUT_FILE}. Exiting.")
    exit(1)

df = pd.read_csv(INPUT_FILE, low_memory=False)
print(f"Loaded {len(df)} rows from existing file")

# 1. Ofsted fetch
ofsted_url = "https://assets.publishing.service.gov.uk/media/69affb1cc78869bf8eb8a5c5/Management_information_-_state-funded_schools_-_latest_inspections_as_at_28_Feb_2026.csv"

try:
    response = requests.get(ofsted_url, timeout=30)
    if response.status_code == 200:
        ofsted_df = pd.read_csv(io.StringIO(response.text), low_memory=False)
        print(f"Successfully fetched Ofsted data: {len(ofsted_df)} rows")
        print("Ofsted columns:", ofsted_df.columns.tolist())

        # Dynamic detection - expanded keywords
        effectiveness_col = None
        for col in ofsted_df.columns:
            col_lower = col.lower()
            if any(k in col_lower for k in ['overall effectiveness', 'effectiveness', 'judgement', 'quality', 'grade', 'rating']):
                effectiveness_col = col
                break

        if 'URN' in ofsted_df.columns and effectiveness_col:
            print(f"Using effectiveness column: {effectiveness_col}")
            ofsted_df = ofsted_df[['URN', effectiveness_col]].drop_duplicates(subset='URN')
            ofsted_df = ofsted_df.rename(columns={effectiveness_col: 'Overall effectiveness'})
            ofsted_df['Overall effectiveness'] = pd.to_numeric(ofsted_df['Overall effectiveness'], errors='coerce')
            ofsted_df['Ofsted Rating'] = ofsted_df['Overall effectiveness'].map(
                {1: 'Outstanding', 2: 'Good', 3: 'Requires Improvement', 4: 'Inadequate'}
            ).fillna('Not available')

            df = df.drop(columns=['Ofsted Rating'], errors='ignore')
            df = df.merge(ofsted_df[['URN', 'Ofsted Rating']], on='URN', how='left')
            updated = df['Ofsted Rating'].notna().sum()
            print(f"Ofsted ratings merged for {updated} schools")
        else:
            print("Ofsted: No URN or effectiveness column found")
    else:
        print(f"Ofsted fetch failed (status {response.status_code})")
except Exception as e:
    print(f"Ofsted fetch error: {e} - skipping")

# 2. Admissions fetch
admissions_url = "https://content.explore-education-statistics.service.gov.uk/api/releases/5ed40264-1835-4848-a29b-446ed6c075c2/files/7c9894e4-9038-4213-823c-bf50bc993cec"

try:
    response = requests.get(admissions_url, timeout=30)
    if response.status_code == 200:
        admissions_df = pd.read_csv(io.StringIO(response.text), low_memory=False)
        print(f"Successfully fetched admissions data: {len(admissions_df)} rows")
        print("Admissions columns:", admissions_df.columns.tolist())

        if 'URN' in admissions_df.columns:
            # Dynamic detection - expanded keywords
            pan_col = next((c for c in admissions_df.columns if any(k in c.lower() for k in ['pan', 'admission number', 'published admission', 'places', 'capacity', 'intake'])), None)
            apps_col = next((c for c in admissions_df.columns if any(k in c.lower() for k in ['application', 'apps', 'preferences', 'total applications', 'received', 'number of preferences'])), None)
            offers_col = next((c for c in admissions_df.columns if any(k in c.lower() for k in ['offer', 'placed', 'allocation', 'offers made', 'first preference', 'total offers'])), None)

            cols_to_merge = ['URN']
            rename_map = {}
            if pan_col:
                cols_to_merge.append(pan_col)
                rename_map[pan_col] = 'PAN Current'
            if apps_col:
                cols_to_merge.append(apps_col)
                rename_map[apps_col] = 'Apps Received Current'
            if offers_col:
                cols_to_merge.append(offers_col)
                rename_map[offers_col] = 'Offers Made Current'

            if len(cols_to_merge) > 1:
                admissions_df = admissions_df[cols_to_merge].drop_duplicates(subset='URN')
                admissions_df = admissions_df.rename(columns=rename_map)
                for new_col in rename_map.values():
                    if new_col in df.columns:
                        df = df.drop(columns=[new_col], errors='ignore')
                    df = df.merge(admissions_df[['URN', new_col]], on='URN', how='left')
                print(f"Admissions merged {len(rename_map)} columns: {', '.join(rename_map.values())}")
            else:
                print("Admissions CSV has URN but no detectable key columns")
        else:
            print("Admissions CSV missing URN")
    else:
        print(f"Admissions fetch failed (status {response.status_code})")
except Exception as e:
    print(f"Admissions fetch error: {e} - skipping")

# Original processing
print(f"Rows before processing: {len(df)}")

if 'Religious Character (name)' in df.columns:
    df = df[df['Religious Character (name)'].str.contains(r'Catholic|Roman Catholic', case=False, na=False, regex=True)]
    print(f"After Catholic filter: {len(df)} rows")

numeric_cols = [
    'PAN 2025', 'Apps Received 2025', 'Offers Made 2025',
    'PAN Current', 'Apps Received Current', 'Offers Made Current',
    '1st Pref Rate %', 'Oversub Ratio', 'Latitude', 'Longitude'
]

for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

if 'Apps Received Current' in df.columns and 'PAN Current' in df.columns:
    df['Oversub Ratio Current'] = df['Apps Received Current'] / df['PAN Current'].replace(0, pd.NA)
elif all(col in df.columns for col in ['Apps Received 2025', 'PAN 2025']):
    df['Oversub Ratio'] = df['Apps Received 2025'] / df['PAN 2025'].replace(0, pd.NA)

df['Last Updated'] = datetime.now().strftime('%Y-%m-%d')

df = df.sort_values(by=['Local Authority', 'School Name']).drop_duplicates(subset=['URN'])

df.to_csv(OUTPUT_FILE, index=False)
print(f"✅ Updated file saved with {len(df)} rows")
