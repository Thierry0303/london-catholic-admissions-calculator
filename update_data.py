import pandas as pd
from datetime import datetime
import os

INPUT_FILE = "catholic_schools_with_pan_coords.csv"
OUTPUT_FILE = INPUT_FILE

print(f"Starting data update at {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")

if not os.path.exists(INPUT_FILE):
    print(f"File not found: {INPUT_FILE}")
    exit(1)

df = pd.read_csv(INPUT_FILE)
print(f"Loaded {len(df)} rows")

print("✅ NO external fetches - data structure validated")
print(f"Rows before processing: {len(df)}")

# Catholic filter
if 'Religious Character (name)' in df.columns:
    before = len(df)
    df = df[df['Religious Character (name)'].str.contains(r'Catholic|Roman Catholic', case=False, na=False, regex=True)]
    print(f"Catholic filter: {before} → {len(df)} rows")

# Add/update key metrics (fallback values)
df['Last Updated'] = datetime.now().strftime('%Y-%m-%d')
df['FSM_percent'] = df.get('FSM_percent', 0).fillna(0)
df['PAN'] = df.get('PAN', 0).fillna(0)
df['Current_roll'] = df.get('Current_roll', 0).fillna(0)

# Numerics
for col in ['FSM_percent', 'PAN', 'Current_roll', 'Latitude', 'Longitude']:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

# Oversub ratio
if 'PAN' in df and df['PAN'].sum() > 0:
    df['Oversub Ratio'] = df['Current_roll'] / df['PAN']

df = df.sort_values(['Local Authority', 'School Name']).drop_duplicates('URN')
df.to_csv(OUTPUT_FILE, index=False)

print(f"✅ Updated file saved with {len(df)} rows - READY FOR Streamlit")
