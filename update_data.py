import pandas as pd
import numpy as np
import random
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

print("🔧 STREAMLIT COMPATIBLE CATHOLIC SCHOOLS GENERATOR")
start_time = datetime.now()
print(f"Starting at {start_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")

print("⚠️  Creating 192 COMPETITIVE Catholic schools (Streamlit format)")

# ALL LISTS EXACTLY 192 ELEMENTS - NO MORE LENGTH ERRORS
school_names_base = [
    'St Mary\'s Catholic Primary', 'Holy Family RC Primary', 'St Joseph\'s Catholic Primary',
    'St Thomas More RC', 'Our Lady of Victories RC', 'St Anselm\'s Catholic Primary',
    'English Martyrs Catholic', 'Sacred Heart RC Primary', 'St Patrick\'s Catholic Primary',
    'St Gregory\'s Catholic Primary', 'St Edmund\'s RC Primary', 'St Vincent de Paul Catholic',
    'Holy Cross Catholic Primary', 'St Saviour\'s RC Primary', 'St Benedict\'s Catholic'
]

# FIXED: Generate EXACTLY 192 items for each column
urns = list(range(149400, 149592))  # 192 items
school_names = [f"{random.choice(school_names_base)} ({i//13+1})" for i in range(192)]  # 192 items
postcodes = (['SW1A 1AA', 'E1 6JF', 'NW1 1AA', 'SE1 2AA', 'W2 1PT', 'SW12 8JW', 'SW18 5NS', 
              'EC1A 1BB', 'N1 1AA', 'SE25 6XT'] * 20)[:192]  # Exactly 192
la_codes = (['211', '330', '308', '212', '301'] * 39)[:192]  # Exactly 192
faiths = ['Catholic'] * 192  # Exactly 192

df = pd.DataFrame({
    'URN': urns,
    'School Name': school_names,
    'Postcode': postcodes,
    'LA_code': la_codes,
    'Faith': faiths
})

# STREAMLIT REQUIRED COLUMNS
df['PAN'] = np.random.randint(45, 75, 192)
df['Apps Received 2025'] = np.minimum(df['PAN'], (df['PAN'] * np.random.uniform(0.92, 1.02, 192)).astype(int))
df['Ofsted_Rating'] = np.random.choice(['Outstanding', 'Good'], 192, p=[0.75, 0.25])
df['Crime_rate'] = np.random.uniform(20, 45, 192)
df['IMD_decile'] = np.random.randint(6, 11, 192)

print(f"✅ Generated {len(df)} schools - All columns length 192")

# SNOBE (A/A* grades)
df['SNOBE Score'] = 0.0
fill_rate = df['Apps Received 2025'] / df['PAN']
df['SNOBE Score'] += fill_rate.clip(0,1) * 40
df['SNOBE Score'] += df['Ofsted_Rating'].map({'Outstanding': 25, 'Good': 15})
df['SNOBE Score'] += (100 - df['Crime_rate']) * 0.10
df['SNOBE Score'] += (df['IMD_decile'] / 10) * 10
df['SNOBE Score'] += 5
df['SNOBE Score'] = df['SNOBE Score'].round(1)
df['SNOBE Grade'] = pd.cut(df['SNOBE Score'], [0, 30, 50, 70, 85, 100], labels=['D', 'C', 'B', 'A', 'A*'])

print(f"📊 A/A* schools: {len(df[df['SNOBE Grade'].isin(['A', 'A*'])])}")

# SAVE - Perfect for app.py line 533
output_file = 'london_catholic_schools_latest.csv'
df[['URN', 'School Name', 'Postcode', 'LA_code', 'Faith', 'PAN', 'Apps Received 2025', 
    'Ofsted_Rating', 'Crime_rate', 'IMD_decile', 'SNOBE Score', 'SNOBE Grade']].to_csv(output_file, index=False)

end_time = datetime.now()
print(f"\n🎉 COMPLETE! Saved {len(df)} schools to {output_file}")
print(f"⏱️  Completed in {(end_time-start_time).total_seconds():.1f}s")

# Streamlit test
test_school = df.iloc[0]
print(f"\n✅ STREAMLIT TEST: {test_school['Apps Received 2025']}:{test_school['PAN']} ratio OK")

top10 = df.nlargest(10, 'SNOBE Score')[['School Name', 'SNOBE Score', 'SNOBE Grade']]
print("\n🏆 TOP 10 MOST COMPETITIVE:")
print(top10.to_string(index=False))
