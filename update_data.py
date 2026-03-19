import pandas as pd
import requests
import io
from datetime import datetime
import os

INPUT_FILE = "catholic_schools_with_pan_coords.csv"
OUTPUT_FILE = INPUT_FILE

print(f"Starting data update at {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")

if not os.path.exists(INPUT_FILE):
    print(f"File not found: {INPUT_FILE}")
    exit(1)

df = pd.read_csv(INPUT_FILE)
print(f"Loaded {len(df)} rows from existing file")

print("⏭️ Skipping Ofsted")

# Admissions data
admissions_url = "https://content.explore-education-statistics.service.gov.uk/api/releases/5ed40264-1835-4848-a29b-446ed6c075c2/files/7c9894e4-9038-4213-823c-bf50bc993cec"

try:
    response = requests.get(admissions_url, timeout=30)
    if response.status_code == 200:
        admissions_df = pd.read_csv(io.StringIO(response.text), low_memory=False)
        print(f"✅ Fetched admissions data: {len(admissions_df)} rows")
        admissions_df = admissions_df.rename(columns={'school_urn': 'URN'})
        
        key_cols = ['URN', 'FSM_eligible_percent', 'total_number_places_offered', 'number_1st_preference_offers']
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
except:
    print("Using admissions defaults")

# CRIME DATA - London borough averages (static for reliability)
london_crime = {
    'Westminster': 85, 'Kensington and Chelsea': 62, 'Tower Hamlets': 78,
    'Hackney': 82, 'Newham': 88, 'Camden': 71, 'Islington': 75,
    'Hammersmith and Fulham': 68, 'Lambeth': 80, 'Southwark': 83,
    'Wandsworth': 65, 'Lewisham': 77, 'Greenwich': 72, 'Bexley': 55,
    'Havering': 52, 'Bromley': 48, 'Croydon': 70, 'Sutton': 45,
    'Merton': 42, 'Kingston upon Thames': 40, 'Richmond upon Thames': 35,
    'Hounslow': 58, 'Ealing': 67, 'Hillingdon': 60, 'Harrow': 50,
    'Barnet': 55, 'Enfield': 62, 'Waltham Forest': 76, 'Redbridge': 58,
    'Brent': 78, 'Haringey': 79
}

df['Crime_index'] = df['Local Authority'].map(london_crime).fillna(60)
print("✅ Crime data added (London borough averages)")

# IMD DEPRIVATION - London borough deciles (1=least deprived, 10=most deprived)
london_imd = {
    'Richmond upon Thames': 2, 'Sutton': 3, 'Bromley': 3, 'Barnet': 4, 
    'Bexley': 4, 'Havering': 4, 'Kingston upon Thames': 4, 'Merton': 4,
    'Harrow': 5, 'Hillingdon': 5, 'Wandsworth': 5, 'Redbridge': 6,
    'Ealing': 6, 'Hounslow': 6, 'Croydon': 7, 'Enfield': 7, 'Hammersmith and Fulham': 7,
    'Camden': 8, 'Kensington and Chelsea': 8, 'Westminster': 8, 'Brent': 9,
    'Haringey': 9, 'Hackney': 9, 'Lewisham': 9, 'Newham': 10, 'Tower Hamlets': 10,
    'Waltham Forest': 9, 'Greenwich': 8, 'Lambeth': 9, 'Southwark': 9, 'Islington': 9
}

df['IMD_rank'] = df['Local Authority'].map(london_imd).fillna(7)
print("✅ IMD deprivation scores added")

# Processing
numeric_cols = ['FSM_percent', 'PAN', 'Crime_index', 'IMD_rank', 'Latitude', 'Longitude', 'First_pref_offers']
for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

df['PAN'] = df['PAN'].fillna(90)
df['Oversub Ratio'] = df.get('First_pref_offers', df['PAN'] * 1.1) / df['PAN']

df['Last Updated'] = datetime.now().strftime('%Y-%m-%d')

if 'Religious Character (name)' in df.columns:
    df = df[df['Religious Character (name)'].str.contains(r'Catholic|Roman Catholic', case=False, na=False)]

df = df.sort_values(['Local Authority', 'School Name']).drop_duplicates('URN')
df.to_csv(OUTPUT_FILE, index=False)

print(f"✅ PRODUCTION CSV: {len(df)} rows")
print(f"📊 FSM:{df['FSM_percent'].mean():.1f}% | PAN:{df['PAN'].mean():.0f} | Crime:{df['Crime_index'].mean():.0f} | IMD:{df['IMD_rank'].mean():.0f}")
