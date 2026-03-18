import pandas as pd
from datetime import datetime
import os

INPUT_FILE = "catholic_schools_with_pan_coords.csv"   # ← your exact file name
OUTPUT_FILE = INPUT_FILE

print(f"Starting data update at {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")

if not os.path.exists(INPUT_FILE):
    print(f"File not found: {INPUT_FILE}. Exiting.")
    exit(1)

df = pd.read_csv(INPUT_FILE)

# Basic cleaning & processing (expand this later if you add new sources)
print(f"Loaded {len(df)} rows initially")

# Ensure Catholic filter (in case source data ever includes others)
if 'Religious Character (name)' in df.columns:
    df = df[df['Religious Character (name)'].str.contains(r'Catholic|Roman Catholic', case=False, na=False, regex=True)]
    print(f"After Catholic filter: {len(df)} rows")

# Convert numeric columns safely
numeric_cols = ['PAN 2025', 'Apps Received 2025', 'Offers Made 2025', '1st Pref Rate %', 'Oversub Ratio', 'Latitude', 'Longitude']
for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

# Recalculate oversub ratio if possible
if all(col in df.columns for col in ['Apps Received 2025', 'PAN 2025']):
    df['Oversub Ratio'] = df['Apps Received 2025'] / df['PAN 2025'].replace(0, pd.NA)

# Add a freshness column (your app can display this)
df['Last Updated'] = datetime.now().strftime('%Y-%m-%d')

# Sort and deduplicate for cleanliness
df = df.sort_values(by=['Local Authority', 'School Name']).drop_duplicates(subset=['URN'])

# Save back to same file
df.to_csv(OUTPUT_FILE, index=False)
print(f"✅ Updated file saved with {len(df)} rows")
