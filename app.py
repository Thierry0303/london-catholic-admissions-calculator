@st.cache_data
def load_data():
    df = pd.read_csv("catholic_schools_with_pan_coords.csv")

    # Rename for consistency
    if "1st Pref Apps 2025" in df.columns:
        df["Apps Received 2025"] = df["1st Pref Apps 2025"]
    if "PAN 2025" in df.columns:
        df["PAN"] = df["PAN 2025"]

    # Safe numerics
    for col in ["PAN", "Apps Received 2025"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0 if col == "Apps Received 2025" else 1)
        else:
            df[col] = 0 if col == "Apps Received 2025" else 1

    # Kill any inf from div-by-zero
    df["PAN"] = df["PAN"].replace(0, 1)

    # Compute ratio safely
    ratio = df["Apps Received 2025"] / df["PAN"]
    ratio = ratio.replace([np.inf, -np.inf], 0) * 100
    df["Oversub Ratio"] = ratio.round(0).fillna(0).astype(int)

    df["_no_data"] = (df["Apps Received 2025"] == 0)

    # Fill other columns
    for col in ["Snobe Overall Grade", "Ofsted Rating", "Local Authority", "Postcode", "Phase", "School Name"]:
        if col not in df.columns:
            df[col] = ""

    return df
