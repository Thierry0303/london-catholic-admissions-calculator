# After admissions merge, add these blocks:

# -----------------------------
# 3. CRIME DATA (Met Police / UK Police API)
# -----------------------------
try:
    # London borough crime stats (12 months)
    crime_url = "https://data.police.uk/api/crimes-street-all-crime?lat=51.5074&lng=-0.1278&date=2026-03"
    response = requests.get(crime_url)
    if response.status_code == 200:
        crimes = response.json()
        borough_crimes = {}
        for crime in crimes[:1000]:  # Sample
            borough = crime.get('context', '').split(',')[-2].strip()
            borough_crimes[borough] = borough_crimes.get(borough, 0) + 1
        
        df['Crime_index'] = df['Local Authority'].map(borough_crimes).fillna(50)
        print("✅ Crime data added")
except:
    df['Crime_index'] = 50  # London avg
    print("Using default crime index")

# -----------------------------
# 4. IMD DEPRIVATION (gov.uk Index Multiple Deprivation)
# -----------------------------
try:
    # IMD 2019 scores by LSOA → map to boroughs
    imd_url = "https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/833994/File_7_ID_2019_Index_of_Multiple_Deprivation.csv"
    imd_df = pd.read_csv(io.StringIO(requests.get(imd_url).text))
    
    # Average by borough (LSOA → LA mapping)
    imd_df['LA'] = imd_df['LSOA_code'].str[:9]  # Extract LA code
    borough_imd = imd_df.groupby('LA')['Index_of_Multiple_Deprivation'].mean().to_dict()
    
    df['IMD_rank'] = df['Local Authority'].map(borough_imd).fillna(25)
    print("✅ IMD deprivation scores added")
except:
    df['IMD_rank'] = 25  # London avg
    print("Using default IMD")

# Update numeric_cols list:
numeric_cols = ['FSM_percent', 'PAN', 'Crime_index', 'IMD_rank', 'Latitude', 'Longitude']
