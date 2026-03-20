import pandas as pd
import requests
import time
from bs4 import BeautifulSoup

MASTER_FILE = "catholic_schools_with_pan_coords.csv"
OUTPUT_FILE = "catholic_schools_with_pan_coords.csv"  # overwrites in place

LONDON_BOROUGHS = [
    "Barnet", "Bexley", "Brent", "Bromley", "Camden", "Croydon", "Ealing", "Enfield",
    "Greenwich", "Hackney", "Hammersmith and Fulham", "Haringey", "Harrow", "Havering",
    "Hillingdon", "Hounslow", "Islington", "Kensington and Chelsea", "Kingston upon Thames",
    "Lambeth", "Lewisham", "Merton", "Newham", "Redbridge", "Richmond upon Thames",
    "Southwark", "Sutton", "Tower Hamlets", "Waltham Forest", "Wandsworth", "Westminster"
]


def fetch_latest_dfe_admissions() -> pd.DataFrame:
    """
    Fetch the latest DfE school-level applications and offers CSV from Explore Education Statistics (2025/26 entry).
    Compute total applications from preference columns.
    Filter to London + Roman Catholic schools.
    Return tidy DataFrame with URN, PAN, Apps Received 2025.
    """
    # Direct URL to school-level CSV for 2025/26 (stable; update UUID if 2026/27 releases)
    CSV_URL = (
        "https://content.explore-education-statistics.service.gov.uk/api/releases/"
        "5ed40264-1835-4848-a29b-446ed6c075c2/files/7c9894e4-9038-4213-823c-bf50bc993cec"
    )

    print("⬇️ Downloading latest DfE admissions school-level CSV (2025/26 entry)...")
    print(f"    {CSV_URL}")

    try:
        df = pd.read_csv(CSV_URL, low_memory=False)
        print(f"✅ Loaded {len(df)} rows from DfE CSV")
    except Exception as e:
        raise RuntimeError(f"Failed to download or parse CSV: {e}\nCheck URL or network.")

    # Normalize column names for matching: lower, strip, remove spaces/underscores
    cols = {c.lower().strip().replace(" ", "").replace("_", ""): c for c in df.columns}

    def find_col(*candidates):
        for cand in candidates:
            norm = cand.lower().strip().replace(" ", "").replace("_", "")
            if norm in cols:
                return cols[norm]
        return None

    # Find key columns (adjust candidates based on actual data; common patterns shown)
    urn_col     = find_col("urn", "laestab", "schoolurn")
    la_col      = find_col("localauthority", "laname", "localauthorityname", "la")
    rel_col     = find_col("religiouscharacter", "denomination", "faith", "typeofestablishment")
    pan_col     = find_col("publishedadmissionnumber", "pan", "admissionnumber", "capacity")

    # Preference columns for total apps (sum them if no direct total)
    pref1_col   = find_col("1stpreference", "firstpreference", "preferences1", "pref1")
    pref2_col   = find_col("2ndpreference", "secondpreference", "preferences2", "pref2")
    pref3_col   = find_col("3rdpreference", "thirdpreference", "preferences3", "pref3")
    total_pref_col = find_col("totalpreferences", "totalapplications", "totalprefs", "appsreceived")

    missing = [name for name, col in [
        ("URN", urn_col),
        ("Local Authority", la_col),
        ("Religious character", rel_col),
        ("PAN", pan_col),
    ] if col is None]

    if missing:
        print("\nAvailable columns in CSV:")
        print(sorted(df.columns.tolist()))
        raise RuntimeError(f"Missing key columns: {', '.join(missing)}. "
                           "Update 'find_col' candidates above based on printed list.")

    # Rename found columns
    rename_dict = {
        urn_col: "URN",
        la_col: "Local Authority",
        rel_col: "ReligiousCharacter",
        pan_col: "PAN",
    }
    df = df.rename(columns=rename_dict)

    # Compute total applications received
    if total_pref_col:
        df["Apps Received 2025"] = pd.to_numeric(df[total_pref_col], errors="coerce").fillna(0).astype(int)
    else:
        pref_cols = [c for c in [pref1_col, pref2_col, pref3_col] if c]
        if not pref_cols:
            raise RuntimeError("No preference columns found to compute total applications.")
        df["Apps Received 2025"] = df[pref_cols].sum(axis=1, skipna=True).astype(int)
        print(f"ℹ️ Computed total apps from {len(pref_cols)} preference columns.")

    # Filter to London boroughs + Roman Catholic
    df["Local Authority"] = df["Local Authority"].astype(str).str.strip()
    df = df[df["Local Authority"].isin(LONDON_BOROUGHS)]

    df["ReligiousCharacter"] = df["ReligiousCharacter"].astype(str).str.strip()
    df = df[df["ReligiousCharacter"].str.contains("Roman Catholic|Catholic", case=False, na=False)]

    # Clean numerics
    df["URN"] = pd.to_numeric(df["URN"], errors="coerce").astype("Int64")
    df["PAN"] = pd.to_numeric(df["PAN"], errors="coerce").fillna(0).astype(int)
    df = df.dropna(subset=["URN"])

    print(f"✅ Filtered to {len(df)} London Roman Catholic schools")
    return df[["URN", "Local Authority", "PAN", "Apps Received 2025"]]


def fetch_snobe_grade(urn: int) -> str | None:
    url = f"https://snobe.co.uk/schools/{urn}"
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        for token in ["A+", "A", "B", "C", "D", "E"]:
            if f"Overall Grade {token}" in text or f"Overall grade {token}" in text:
                return token
        return None
    except Exception:
        return None


def update_snobe_grades(df: pd.DataFrame) -> pd.DataFrame:
    if "Snobe Overall Grade" not in df.columns:
        df["Snobe Overall Grade"] = ""
    mask_missing = df["Snobe Overall Grade"].astype(str).str.strip().isin(["", "nan", "NaN"])
    to_update = df[mask_missing & df["URN"].notna()].copy()
    if to_update.empty:
        print("ℹ️ No missing Snobe grades — skipping fetch.")
        return df

    print(f"🔎 Fetching Snobe grades for {len(to_update)} schools...")
    for i, (idx, row) in enumerate(to_update.iterrows(), 1):
        urn = int(row["URN"])
        grade = fetch_snobe_grade(urn)
        if grade:
            df.loc[idx, "Snobe Overall Grade"] = grade
            print(f"  [{i}/{len(to_update)}] URN {urn}: {grade}")
        else:
            print(f"  [{i}/{len(to_update)}] URN {urn}: not found")
        time.sleep(1.0)  # polite delay
    return df


def main():
    print("🔧 Starting full data update...")
    print("📂 Loading master file...")
    master = pd.read_csv(MASTER_FILE)
    master["URN"] = pd.to_numeric(master["URN"], errors="coerce").astype("Int64")

    print("📡 Fetching latest DfE admissions data...")
    dfe = fetch_latest_dfe_admissions()

    print("🔗 Merging DfE data into master...")
    merged = master.merge(dfe, on=["URN", "Local Authority"], how="left", suffixes=("", "_DfE"))

    # Prefer fresh DfE values for PAN / Apps
    for col in ["PAN", "Apps Received 2025"]:
        dfe_col = f"{col}_DfE"
        if dfe_col in merged.columns:
            merged[col] = merged[dfe_col].fillna(merged[col] if col in merged.columns else 0)
            merged.drop(columns=[dfe_col], inplace=True)

    # Ensure numeric types
    merged["PAN"] = pd.to_numeric(merged["PAN"], errors="coerce").fillna(0).astype(int)
    merged["Apps Received 2025"] = pd.to_numeric(merged["Apps Received 2025"], errors="coerce").fillna(0).astype(int)

    print("📊 Computing oversubscription ratios...")
    merged["Oversub Ratio"] = (
        (merged["Apps Received 2025"] / merged["PAN"].replace(0, 1)) * 100
    ).round(0).astype(int)

    print("🏅 Updating Snobe overall grades...")
    merged = update_snobe_grades(merged)

    print(f"💾 Saving updated file: {OUTPUT_FILE}")
    merged.to_csv(OUTPUT_FILE, index=False)
    print("🎉 Update complete!")


if __name__ == "__main__":
    main()
