# -----------------------------
# 2. Admissions data (NOW WORKS!)
# -----------------------------
try:
    response = requests.get(admissions_url, timeout=30)
    if response.status_code == 200:
        admissions_df = pd.read_csv(io.StringIO(response.text), low_memory=False)
        print(f"Successfully fetched admissions data: {len(admissions_df)} rows")
        
        # KEY: Use 'school_urn' not 'URN'
        admissions_df = admissions_df.rename(columns={'school_urn': 'URN'})
        
        # Key admissions metrics
        key_cols = ['URN', 'number_preferred_offers', 'number_1st_preference_offers', 
                   'FSM_eligible_percent', 'total_number_places_offered']
        
        admissions_df = admissions_df[key_cols].drop_duplicates('URN')
        admissions_df.rename(columns={
            'number_preferred_offers': 'Preferred offers',
            'number_1st_preference_offers': '1st pref offers', 
            'FSM_eligible_percent': 'FSM_percent',
            'total_number_places_offered': 'PAN'
        }, inplace=True)
        
        # Merge!
        df = df.merge(admissions_df, on='URN', how='left', suffixes=('', '_new'))
        print("✅ Admissions data merged - REAL FSM% + offers!")
        
except Exception as e:
    print(f"Admissions error: {e}")
