import pandas as pd
import requests
import io
from datetime import datetime
import os

INPUT_FILE = "catholic_schools_with_pan_coords.csv"
OUTPUT_FILE = INPUT_FILE

print(f"Starting data update at {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")

# Load existing data
if not os.path.exists(INPUT_FILE):
    print(f"File not found: {INPUT_FILE}")
    exit(1)

df = pd.read_csv(INPUT_FILE)
print(f"Loaded {len(df)} rows from existing file")

# -----------------------------
# 1. Ofsted data (skip - broken CSV format)
# -----------------------------
print("⏭️ Skipping Ofsted (broken CSV format)")

# -----------------------------
# 2. Admissions data (WORKS! Uses school_urn)
# -----------------------------
admissions_url = "https://content.explore-education-statistics.service.gov.uk/api/releases/5ed40264-1835-4848-a29b-446ed6c075c2/files/7c9894e4-9038-4213-823c-bf50bc993cec"

try:
    response = requests.get(admissions_url, timeout=30)
    if response.status_code == 200:
        admissions_df = pd.read_csv(io.StringIO(response.text), low_memory=False)
        print(f"Successfully fetched admissions data: {len(admissions_df)} rows")
        
        #
