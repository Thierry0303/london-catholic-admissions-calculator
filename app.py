# update_data.py - Improved version with strong preference for first-preference apps
# Run this to refresh admissions data from DfE + apply overrides
# Current date: March 22, 2026

import pandas as pd
import os
import time
import requests

MASTER_FILE = "catholic_schools_with_pan_coords.csv"
OUTPUT_FILE = "catholic_schools_with_pan_coords.csv"

# Schools you want to force high demand for
KEY_SCHOOLS = {
    "Oratory Roman Catholic Primary": "100491",
    "St Joseph RC Primary Kensington": "148438",
    "St Richard Reynolds Catholic High": "149297",
}

def debug_print(msg):
    print(f"[DEBUG] {msg}")

def load_master():
    debug_print(f"Loading master CSV: {MASTER_FILE}")
    if not os.path.exists(MASTER_FILE):
        debug_print("Master file missing! Cannot continue.")
        return pd.DataFrame()
    master = pd.read_csv(MASTER_FILE, low_memory=False)
    master["URN"] = master["URN"].astype(str).str.strip()
    debug_print(f"Master loaded: {len(master)} rows | URN type: {master['URN'].dtype}")
    return master


def fetch_dfe_admissions():
    # 2025/26 primary admissions – first-preference data
    # This URL may change with new DfE releases – check explore-education-statistics.service.gov.uk
    CSV_URL = (
        "https://content.explore-education-statistics.service.gov.uk/api/releases/"
        "5ed40264-1835-4848-a29b-446ed6c075c2/files/7c9894e4-9038-4213-823c-bf50bc993cec"
    )

    debug_print("Downloading latest DfE admissions data (2025/26)...")
    try:
        dfe = pd.read_csv(CSV_URL, low_memory=False)
        debug_print(f"Downloaded DfE data: {len(dfe):,} rows")
    except Exception as e:
        debug_print(f"Download failed: {e}")
        return pd.DataFrame()

    rename_map = {
        "school_urn": "URN",
        "la_name": "Local Authority",
        "times_put_as_1st_preference": "1st Pref Apps 2025",           # ← Primary preference!
        "times_put_as_any_preferred_school": "Any Pref Apps 2025",
        "total_number_places_offered": "Places Offered 2025 (DfE)",
    }

    dfe = dfe.rename(columns=rename_map)

    # Filter to London boroughs
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

    debug_print(f"London Catholic-relevant DfE data: {len(dfe)} schools")
    debug_print(f"Available columns: {list(dfe.columns)}")

    return dfe


def merge_and_prefer_first_pref(master, dfe):
    debug_print("Merging master + DfE on URN (string comparison)...")
    merged = master.merge(dfe, on="URN", how="left", suffixes=("", "_DfE"))

    debug_print(f"Merge result: {len(merged)} rows")

    # Prefer first-preference from DfE when present
    first_pref_col = "1st Pref Apps 2025"
    first_pref_dfe = f"{first_pref_col}_DfE"
    if first_pref_dfe in merged.columns:
        debug_print(f"Preferring {first_pref_col} from DfE")
        merged[first_pref_col] = merged[first_pref_dfe].combine_first(merged.get(first_pref_col, 0))
        merged.drop(columns=[first_pref_dfe], inplace=True, errors="ignore")
    else:
        debug_print(f"Warning: First-preference column '{first_pref_dfe}' missing in DfE data")

    # Final demand column
    merged["Apps Received 2025"] = merged.get(first_pref_col, 0).fillna(0).astype(int)

    # PAN: master preferred, fallback to DfE
    if "PAN" not in merged.columns:
        merged["PAN"] = 1
    merged["PAN"] = merged["PAN"].fillna(merged.get("PAN_DfE", 1)).replace(0, 1).astype(int)

    # Calculate ratio
    ratio = merged["Apps Received 2025"] / merged["PAN"].astype(float)
    ratio = ratio.replace([np.inf, -np.inf], 0)
    merged["Oversub Ratio"] = (ratio * 100).round(0).fillna(0).astype(int)

    debug_print("Oversubscription calculated (1st-pref preferred)")

    return merged


def apply_overrides(merged):
    overrides = {
        "100491": {"Apps Received 2025": 169, "Oversub Ratio": 563},   # Oratory
        "148438": {"Apps Received 2025": 145, "Oversub Ratio": 483},   # St Joseph Kensington
        "149297": {"Apps Received 2025": 355, "Oversub Ratio": 197},   # St Richard Reynolds
    }

    debug_print("\nApplying manual overrides for known oversubscribed schools...")
    for urn_str, updates in overrides.items():
        mask = merged["URN"].astype(str) == urn_str
        if mask.any():
            for col, val in updates.items():
                merged.loc[mask, col] = val
            debug_print(f"  Applied override for URN {urn_str}")
        else:
            debug_print(f"  Warning: URN {urn_str} not found – override skipped")

    return merged


def show_key_schools(merged):
    debug_print("\n=== Final values for your key schools ===")
    for name, urn in KEY_SCHOOLS.items():
        match = merged[merged["URN"].astype(str) == urn]
        if not match.empty:
            row = match.iloc[0]
            debug_print(f"{name} (URN {urn}):")
            debug_print(f"  Apps Received 2025   = {row.get('Apps Received 2025', 'missing')}")
            debug_print(f"  1st Pref Apps 2025   = {row.get('1st Pref Apps 2025', 'missing')}")
            debug_print(f"  PAN                  = {row.get('PAN', 'missing')}")
            debug_print(f"  Oversub Ratio        = {row.get('Oversub Ratio', 'missing')}")
            debug_print("  ---")
        else:
            debug_print(f"{name} (URN {urn}) NOT FOUND in final data")


def main():
    debug_print("=== update_data.py started (debug mode) ===")

    master = load_master()
    if master.empty:
        return

    dfe = fetch_dfe_admissions()
    merged = merge_and_prefer_first_pref(master, dfe)
    merged = apply_overrides(merged)
    show_key_schools(merged)

    # Save
    merged.to_csv(OUTPUT_FILE, index=False)
    debug_print(f"\nSaved refreshed file: {OUTPUT_FILE}")
    debug_print("=== Finished ===")


if __name__ == "__main__":
    main()   
