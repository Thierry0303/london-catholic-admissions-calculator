import pandas as pd
from datetime import datetime

df = pd.read_csv("catholic_schools_with_pan_coords.csv")
print(f"Loaded {len(df)} rows")

df['Last Updated'] = datetime.now().strftime('%Y-%m-%d')

# Ensure key columns exist
df['FSM_percent'] = pd.to_numeric(df.get('FSM_percent', 25), errors='coerce')
df['PAN'] = pd.to_numeric(df.get('PAN', 210), errors='coerce')  # Typical primary PAN
df['Oversub Ratio'] = df['Current_roll'].fillna(df['PAN'] * 0.95) / df['PAN']

df.to_csv("catholic_schools_with_pan_coords.csv", index=False)
print(f"✅ Production ready - {len(df)} rows")
