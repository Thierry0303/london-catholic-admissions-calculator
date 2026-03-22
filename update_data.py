# update_data.py - Safe version: never overwrites existing school-level data
# Only recalculates Oversub Ratio from existing PAN + Apps data
# Do NOT run this on Streamlit Cloud - run locally only if needed

import pandas as pd
import numpy as np
import os

MASTER_FILE = "catholic_schools_with_pan_coords.csv"
OUTPUT_FILE = "catholic_schools_with_pan_coords.csv"


def main():
    print("=== update_data.py (safe mode) ===\n")

    if not os.path.exists(MASTER_FILE):
        print("ERROR: Master file missing!")
        return

    df = pd.read_csv(MASTER_FILE, low_memory=False)
    df["URN"] = df["URN"].astype(str).str.strip()
    print(f"Loaded {len(df)} schools")

    # Ensure numeric columns are clean
    for col in ["PAN", "Apps Received 2025", "Offers Made 2025"]:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Recalculate Oversub Ratio safely
    pan_safe = df["PAN"].replace(0, np.nan)
    df["Oversub Ratio"] = (
        (df["Apps Received 2025"] / pan_safe * 100)
        .replace([np.inf, -np.inf], 0)
        .fillna(0)
        .round(6)
    )

    has_data = df[(df["PAN"] > 0) & (df["Apps Received 2025"] > 0)]
    no_data  = df[(df["PAN"] == 0) & (df["Apps Received 2025"] == 0)]
    print(f"Schools with data:    {len(has_data)}")
    print(f"Schools without data: {len(no_data)}")

    print("\nTop 10 most oversubscribed:")
    top = has_data.nlargest(10, "Oversub Ratio")
    for _, r in top.iterrows():
        print(f"  {r['School Name']} ({r['Local Authority']}): {int(r['Apps Received 2025'])}:{int(r['PAN'])}")

    df.to_csv(OUTPUT_FILE, index=False)
    print(f"\nSaved {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
