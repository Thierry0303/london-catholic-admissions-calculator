import pandas as pd
import requests
import io
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

print("🚀 CATHOLIC SCHOOLS UPDATER - LIVE DATA")
start_time = datetime.now()
print(f"Starting at {start_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")

# 1. MAIN SCHOOL DATA (primary source)
schools_url = "https://raw.githubusercontent.com/mike-harrison-uk/london-catholic-admissions-calculator/main/data/schools.csv"
try:
    response = requests.get(schools_url, timeout=30)
    df = pd.read_csv(io.StringIO(response.text))
    print(f"✅ Loaded {len(df)} rows")
except:
    print("❌ Failed to load main schools data")
    exit(1)

# 2. DfE ADMISSIONS DATA (fixed duplicate columns)
admissions_url = "https://content.explore-education-statistics.service.gov.uk/api/releases/5ed40264-1835-4848-a29b-446ed6c075c2/files/7c9894e4-9038-4213-823c-bf50bc993cec"
try:
    response = requests.get(admissions_url, timeout=30)
    if response.status_code == 200:
        admissions_df = pd.read_csv(io.StringIO(response.text), low_memory=False)
        admissions_df = admissions_df.rename(columns={'school_urn': 'URN'})
        # FIXED: Drop duplicate suffix columns before merge
        dup_cols = ['PAN_new', 'First_pref_offers_new', 'FSM_percent_new']
        for col in dup_cols:
            if f'{col}_x' in admissions_df.columns and f'{col}_y' in admissions_df.columns:
                admissions_df[col] = admissions_df[f'{col}_x'].fillna(admissions_df[f'{col}_y'])
                admissions_df = admissions_df.drop([f'{col}_x', f'{col}_y'], axis=1)
        df = df.merge(admissions_df[['URN', 'PAN_new', 'First_pref_offers_new', 'FSM_percent_new']], 
                     on='URN', how='left')
        print("✅ Admissions data merged")
    else:
        print("⚠️ Admissions data unavailable")
except Exception as e:
    print(f"⚠️ Admissions error: {str(e)}")

# 3. CRIME DATA
crime_url = "https://raw.githubusercontent.com/mike-harrison-uk/london-catholic-admissions-calculator/main/data/crime_rates.csv"
try:
    crime_df = pd.read_csv(crime_url)
    df = df.merge(crime_df, on='LA_code', how='left')
    print("✅ Crime rates added")
except:
    print("⚠️ Crime data unavailable")

# 4. IMD DEPRIVATION
imd_url = "https://raw.githubusercontent.com/mike-harrison-uk/london-catholic-admissions-calculator/main/data/imd_london.csv"
try:
    imd_df = pd.read_csv(imd_url)
    df = df.merge(imd_df, left_on='Postcode', right_on='Postcode', how='left')
    print("✅ IMD deprivation added")
except:
    print("⚠️ IMD data unavailable")

# 5. OFSTED (with fallback)
ofsted_proxy = None  # FIXED: Define variable first
try:
    ofsted_url = "https://raw.githubusercontent.com/mike-harrison-uk/london-catholic-admissions-calculator/main/data/ofsted_ratings.csv"
    ofsted_df = pd.read_csv(ofsted_url)
    df = df.merge(ofsted_df[['URN', 'Ofsted_Rating']], on='URN', how='left')
    print("✅ Ofsted ratings added")
except:
    print("⏭️ Skipping Ofsted (broken format)")
    df['Ofsted_Rating'] = 'No data'

# 6. CALCULATE SNOBE RATINGS
print("🔍 Calculating SNOBE ratings...")
df['SNOBE_score'] = 0.0

# Academic (40%)
df.loc[df['First_pref_offers_new'].notna(), 'SNOBE_score'] += (
    df['First_pref_offers_new'] / df['PAN_new'] * 40
).fillna(0)

# Ofsted (25%)
ofsted_map = {'Outstanding': 25, 'Good': 15, 'Requires improvement': 5, 'Inadequate': 0}
df['SNOBE_score'] += df['Ofsted_Rating'].map(ofsted_map).fillna(0)

# Crime safety (15%)
df['SNOBE_score'] += (100 - df['Crime_rate'].fillna(50)) * 0.15

# Deprivation (10%)
df['SNOBE_score'] += (100 - df['IMD_decile'].fillna(5) * 20) * 0.10

# Faith (10%) - Catholic bonus
df.loc[df['Faith'] == 'Catholic', 'SNOBE_score'] += 10

df['SNOBE_grade'] = pd.cut(df['SNOBE_score'], 
                          bins=[0, 30, 50, 70, 85, 100], 
                          labels=['D', 'C', 'B', 'A', 'A*'])

print("✅ SNOBE ratings calculated")

# 7. SAVE RESULTS
output_file = 'london_catholic_schools_latest.csv'
df.to_csv(output_file, index=False)
end_time = datetime.now()
duration = (end_time - start_time).total_seconds()

print(f"\n🎉 COMPLETE! Saved {len(df)} schools to {output_file}")
print(f"⏱️  Completed in {duration:.1f} seconds")
print(f"📊 Top 5 SNOBE: {df.nlargest(5, 'SNOBE_score')[['School_name', 'SNOBE_score', 'SNOBE_grade']].to_dict('records')}")
