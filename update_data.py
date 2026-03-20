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
    Fetch DfE school-level applications/offers CSV (2025/26).
    Uses 'times_put_as_any_preferred_school' for total apps.
    Uses 'total_number_places_offered' as proxy for PAN/places.
    Filters to London + Roman Catholic.
    """
    CSV_URL = (
        "https://content.explore-education-statistics.service.gov.uk/api/releases/"
        "5ed40264-1835-4848-a29b-446ed6c075c2/files/7c9894e4-9038-4213-823c-bf50bc993cec"
    )

    print("⬇️ Downloading DfE admissions CSV (2025/26 entry)...")
    print(f"    {CSV_URL}")

    df = pd.read_csv(CSV_URL, low_memory=False)
    print(f"✅ Loaded {len(df):,} rows")

    # Debug: show columns immediately
    print("Columns in raw CSV:", df.columns.tolist())

    # Exact mappings based on known dataset
    rename_map = {
        "school_urn": "URN",
        "la_name": "Local Authority",
        "denomination": "ReligiousCharacter",
        "total_number_places_offered": "Places Offered 2025",
        "times_put_as_any_preferred_school": "Apps Received 2025",
    }

    # Check if all source columns exist
    missing_sources = [src for src in rename_map if src not in df.columns]
    if missing_sources:
        print("\nMissing source columns:", missing_sources)
        print("Available columns:", sorted(df.columns.tolist()))
        raise RuntimeError("Required columns missing from CSV. Update rename_map.")

    # Rename
    df = df.rename(columns=rename_map)

    # Debug: confirm after rename
    print("Columns after rename:", df.columns.tolist())
    if "Local Authority" not in df.columns or "URN" not in df.columns:
        raise RuntimeError("'Local Authority' or 'URN' missing after rename — check mapping.")

    # Filter London boroughs
    df["Local Authority"] = df["Local Authority"].astype(str).str.strip()
    print("Unique LAs before filter:", df["Local Authority"].unique()[:10])  # debug
    df = df[df["Local Authority"].isin(LONDON_BOROUGHS)]
    print(f"Rows after LA filter: {len(df):,}")

    df["ReligiousCharacter"] = df["ReligiousCharacter"].astype(str).str.strip()
    print("Sample ReligiousCharacter values:")
    print(df["ReligiousCharacter"].head(10))
    print(df["ReligiousCharacter"].value_counts().head(15))

    # Try broad then narrow
    catholic_mask = df["ReligiousCharacter"].str.lower().str.contains("catholic")
    print(f"Rows matching broad 'catholic': {catholic_mask.sum()}")
    
    df = df[catholic_mask]

    # Clean numerics
    df["URN"] = pd.to_numeric(df["URN"], errors="coerce").astype("Int64")
    df["Places Offered 2025"] = pd.to_numeric(df["Places Offered 2025"], errors="coerce").fillna(0).astype(int)
    df["Apps Received 2025"] = pd.to_numeric(df["Apps Received 2025"], errors="coerce").fillna(0).astype(int)
    df = df.dropna(subset=["URN"])

    print(f"✅ Final filtered London RC schools: {len(df):,}")
    return df[["URN", "Local Authority", "Places Offered 2025", "Apps Received 2025", "ReligiousCharacter"]]


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
        print("ℹ️ No missing Snobe grades — skipping.")
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
        time.sleep(1.0)
    return df


def main():
    print("🔧 Starting full data update...")
    print("📂 Loading master file...")
    master = pd.read_csv(MASTER_FILE)
    master["URN"] = pd.to_numeric(master["URN"], errors="coerce").astype("Int64")
    # Debug master columns
    print("Master columns:", master.columns.tolist())

    print("📡 Fetching latest DfE admissions data...")
    dfe = fetch_latest_dfe_admissions()

    print("🔗 Merging DfE data into master...")
    merged = master.merge(dfe, on=["URN", "Local Authority"], how="left", suffixes=("", "_DfE"))

    # Prefer DfE values
    for col in ["Places Offered 2025", "Apps Received 2025"]:
        dfe_col = f"{col}_DfE"
        if dfe_col in merged.columns:
            merged[col] = merged[dfe_col].fillna(merged.get(col, 0))
            merged.drop(columns=[dfe_col], inplace=True)

    merged["Places Offered 2025"] = pd.to_numeric(merged["Places Offered 2025"], errors="coerce").fillna(0).astype(int)
    merged["Apps Received 2025"] = pd.to_numeric(merged["Apps Received 2025"], errors="coerce").fillna(0).astype(int)

    print("📊 Computing oversubscription ratios...")
    merged["Oversub Ratio"] = (
        (merged["Apps Received 2025"] / merged["Places Offered 2025"].replace(0, 1)) * 100
    ).round(0).astype(int)

    print("🏅 Updating Snobe overall grades...")
    merged = update_snobe_grades(merged)

    print(f"💾 Saving updated file: {OUTPUT_FILE}")
    merged.to_csv(OUTPUT_FILE, index=False)
    print("🎉 Update complete!")


if __name__ == "__main__":
    main()
