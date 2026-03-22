# update_data.py - Debug version (March 2026)
# Run this script to refresh admissions data and see exactly what's happening

import pandas as pd
import os
import time

MASTER_FILE = "catholic_schools_with_pan_coords.csv"
OUTPUT_FILE = "catholic_schools_with_pan_coords.csv"

# These are the URNs you mentioned
KEY_SCHOOLS = {
    "Oratory Roman Catholic Primary": "100491",
    "St Joseph RC Primary Kensington": "148438",
    "St Richard Reynolds Catholic High": "149297",
}

def debug_print(msg):
    print(f"[DEBUG] {msg}")

def load_master():
    debug_print(f"Loading master file: {MASTER_FILE}")
    if not os.path.exists(MASTER_FILE):
        debug_print("Master file not found!")
        return pd.DataFrame()
    master = pd.read_csv(MASTER_FILE, low_memory=False)
    master["URN"] = master["URN"].astype(str).str.strip()
    debug_print(f"Master loaded: {len(master)} rows, URN type = {master['URN'].dtype}")
    return master


def fetch_dfe_admissions():
    # Latest known DfE link for 2025/26 primary admissions (first prefs)
    # Update this URL if DfE publishes a newer release!
    CSV_URL = (
        "https://content.explore-education-statistics.service.gov.uk/api/releases/"
        "5ed40264-1835-4848-a29b-446ed6c075c2/files/7c9894e4-9038-4213-823c-bf50bc993cec"
    )

    debug_print("Downloading DfE admissions data...")
    try:
        dfe = pd.read_csv(CSV_URL, low_memory=False)
        debug_print(f"DfE data loaded: {len(dfe):,} rows")
    except Exception as e:
        debug_print(f"Failed to download DfE data: {e}")
        return pd.DataFrame()

    # Rename columns we care about
    rename_map = {
        "school_urn": "URN",
        "la_name": "Local Authority",
        "times_put_as_1st_preference": "1st Pref Apps 2025",           # ← this is the gold standard
        "times_put_as_any_preferred_school": "Any Pref Apps 2025",
        "total_number_places_offered": "Places Offered 2025 (DfE)",
    }

    dfe = dfe.rename(columns=rename_map)

    # Keep only London boroughs
    london_las = [
        "Barnet", "Bexley", "Brent", "Bromley", "Camden", "Croydon", "Ealing", "Enfield",
        "Greenwich", "Hackney", "Hammersmith and Fulham", "Haringey", "Harrow", "Havering",
        "Hillingdon", "Hounslow", "Islington", "Kensington and Chelsea", "Kingston upon Thames",
        "Lambeth", "Lewisham", "Merton", "Newham", "Redbridge", "Richmond upon Thames",
        "Southwark", "Sutton", "Tower Hamlets", "Waltham Forest", "Wandsworth", "Westminster"
    ]

    dfe["Local Authority"] = dfe["Local Authority"].astype(str).str.strip()
    dfe = dfe[dfe["Local Authority"].isin(london_las)]

    # Force URN to string for safe merging
    dfe["URN"] = dfe["URN"].astype(str).str.strip()

    debug_print(f"DfE London data ready: {len(dfe)} schools")
    debug_print(f"Columns in DfE: {list(dfe.columns)}")

    return dfe[["URN", "Local Authority", "1st Pref Apps 2025", "Any Pref Apps 2025", "Places Offered 2025 (DfE)"]]


def main():
    debug_print("=== Starting data refresh (debug mode) ===")

    master = load_master()
    if master.empty:
        debug_print("Aborting: no master data")
        return

    dfe = fetch_dfe_admissions()
    if dfe.empty:
        debug_print("Warning: no DfE data loaded - using master only")

    debug_print("Merging master + DfE on URN (string match)...")
    merged = master.merge(dfe, on="URN", how="left", suffixes=("", "_DfE"))

    debug_print(f"After merge: {len(merged)} rows")

    # Prefer first-preference from DfE when available
    if "1st Pref Apps 2025_DfE" in merged.columns:
        merged["1st Pref Apps 2025"] = merged["1st Pref Apps 2025_DfE"].combine_first(merged.get("1st Pref Apps 2025", 0))
        merged.drop(columns=["1st Pref Apps 2025_DfE"], inplace=True, errors="ignore")

    # Final demand column = first-preference (or fallback)
    merged["Apps Received 2025"] = merged.get("1st Pref Apps 2025", 0).fillna(0).astype(int)

    # PAN: prefer master, fallback to DfE if missing
    if "PAN" not in merged.columns:
        merged["PAN"] = 1
    merged["PAN"] = merged["PAN"].fillna(merged.get("PAN_DfE", 1)).replace(0, 1).astype(int)

    # Calculate oversubscription ratio
    ratio = merged["Apps Received 2025"] / merged["PAN"].astype(float)
    ratio = ratio.replace([np.inf, -np.inf], 0)
    merged["Oversub Ratio"] = (ratio * 100).round(0).fillna(0).astype(int)

    debug_print("Oversubscription calculated using 1st-pref preference when available")

    # Show debug for your three schools
    debug_print("\n=== Checking key schools ===")
    for name, urn in KEY_SCHOOLS.items():
        match = merged[merged["URN"].astype(str) == urn]
        if not match.empty:
            row = match.iloc[0]
            debug_print(f"{name} (URN {urn}):")
            debug_print(f"  Apps Received 2025   = {row.get('Apps Received 2025')}")
            debug_print(f"  1st Pref Apps 2025   = {row.get('1st Pref Apps 2025', 'missing')}")
            debug_print(f"  PAN                  = {row.get('PAN')}")
            debug_print(f"  Oversub Ratio        = {row.get('Oversub Ratio')}")
            debug_print("  ---")
        else:
            debug_print(f"Warning: {name} (URN {urn}) NOT FOUND in final data!")

    # Save final file
    merged.to_csv(OUTPUT_FILE, index=False)
    debug_print(f"\nSaved updated file: {OUTPUT_FILE}")
    debug_print("=== Refresh complete ===")


if __name__ == "__main__":
    main()
