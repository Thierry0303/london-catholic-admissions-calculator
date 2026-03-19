import pandas as pd
import numpy as np
import random
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

print("🔧 STREAMLIT COMPATIBLE CATHOLIC SCHOOLS GENERATOR")
start_time = datetime.now()
print(f"Starting at {start_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")

N = 192
print(f"⚠️  Creating {N} COMPETITIVE Catholic schools (Streamlit format)")

# -----------------------------
# 1. Base lists (auto-repeat)
# -----------------------------
school_names_base = [
    "St Mary's Catholic Primary", "Holy Family RC Primary", "St Joseph's Catholic Primary",
    "St Thomas More RC", "Our Lady of Victories RC", "St Anselm's Catholic Primary",
    "English Martyrs Catholic", "Sacred Heart RC Primary", "St Patrick's Catholic Primary",
    "St Gregory's Catholic Primary", "St Edmund's RC Primary", "St Vincent de Paul Catholic",
    "Holy Cross Catholic Primary", "St Saviour's RC Primary", "St Benedict's Catholic"
]

postcodes_base = [
    'SW1A 1AA', 'E1 6JF', 'NW1 1AA', 'SE1 2AA', 'W2 1PT',
    'SW12 8JW', 'SW18 5NS', 'EC1A 1BB', 'N1 1AA', 'SE25 6XT'
]

la_codes_base = ['211', '330', '308', '212', '301']

# Auto-expand lists to exactly N items
def expand_list(base, n):
    return (base * (n // len(base) + 1))[:n]

# -----------------------------
# 2. Build DataFrame
# -----------------------------
df = pd.DataFrame({
    'URN': range(149400, 149400 + N),
    'School Name': [f"{random.choice(school_names_base)} ({i//13+1})" for i in range(N)],
    'Postcode': expand_list(postcodes_base, N),
    'LA_code': expand_list(la_codes_base, N),
    'Faith': ['Catholic'] * N
})

# -----------------------------
# 3. Core numeric fields
# -----------------------------
df['PAN'] = np.random.randint(45, 75, N)

# Apps Received ~ 92–102% of PAN
df['Apps Received 2025'] = (
    df['PAN'] * np.random.uniform(0.92, 1.02, N)
).astype(int).clip(lower=0)

df['Ofsted_Rating'] = np.random.choice(['Outstanding', 'Good'], N, p=[0.75, 0.25])
df['Crime_rate'] = np.random.uniform(20, 45, N)
df['IMD_decile'] = np.random.randint(6, 11, N)

# -----------------------------
# 4. Oversubscription (NEW)
# -----------------------------
df['Oversubscription'] = (df['Apps Received 2025'] / df['PAN']).round(2)
df['Oversubscription Rank'] = df['Oversubscription'].rank(ascending=False).astype(int)

# -----------------------------
# 5. SNOBE Score (vectorized)
# -----------------------------
df['SNOBE Score'] = (
    df['Oversubscription'].clip(0, 1) * 40 +
    df['Ofsted_Rating'].map({'Outstanding': 25, 'Good': 15}) +
    (100 - df['Crime_rate']) * 0.10 +
    (df['IMD_decile'] / 10) * 10 +
    5
).round(1)

df['SNOBE Grade'] = pd.cut(
    df['SNOBE Score'],
    [0, 30, 50, 70, 85, 100],
    labels=['D', 'C', 'B', 'A', 'A*']
)

print(f"📊 A/A* schools: {len(df[df['SNOBE Grade'].isin(['A', 'A*'])])}")

# -----------------------------
# 6. Save CSV
# -----------------------------
output_file = 'london_catholic_schools_latest.csv'
df.to_csv(output_file, index=False)

end_time = datetime.now()
print(f"\n🎉 COMPLETE! Saved {len(df)} schools to {output_file}")
print(f"⏱️  Completed in {(end_time-start_time).total_seconds():.1f}s")

# -----------------------------
# 7. Streamlit test
# -----------------------------
test_school = df.iloc[0]
print(f"\n✅ STREAMLIT TEST: Oversubscription = {test_school['Oversubscription']}")

top10 = df.nlargest(10, 'Oversubscription')[['School Name', 'Oversubscription']]
print("\n🏆 TOP 10 MOST COMPETITIVE (by oversubscription):")
print(top10.to_string(index=False))
