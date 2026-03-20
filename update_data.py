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
    Fetch DfE school-level applications/offers CSV (2025/26 entry) from EES.
    Use 'times_put_as_any_preferred_school' for total apps received.
    Use 'total_number_places_offered' as proxy for PAN (places offered ≈ capacity).
    Filter to London + Roman Catholic schools.
    """
    CSV_URL = (
        "https://content.explore-education-statistics.service.gov.uk/api/releases/"
        "5ed40264-1835-4848-a29b-446ed6c075c2/files/7c9894e4-9038-4213-823c-bf50bc993cec"
    )

    print("⬇️ Downloading DfE admissions CSV (2025/26 entry)...")
    print(f"    {CSV_URL}")

    df = pd.read_csv(CSV_URL, low_memory=False)
    print(f"✅ Loaded {len(df)} rows")

    # Exact column names from this dataset
    expected = {
        "URN": "school_urn",
        "Local Authority": "la_name",
        "ReligiousCharacter": "denomination",
        "Places Offered 2025": "total_number_places_offered",  # proxy for PAN
        "Apps Received 2025": "times_put_as_any_preferred_school",  # total preferences
    }

    missing = [name for name, col in expected.items() if col not in df.columns]
    if missing:
        print("\nAvailable columns:")
        print(sorted(df.columns.tolist()))
        raise RuntimeError(f"Missing columns: {', '.join(missing)}. Dataset may have changed.")

    df = df.rename(columns=expected)

    # Filter London + Catholic
    df["Local Authority"] = df["Local Authority"].astype(str).str.strip()
    df = df[df["Local Authority"].isin(LONDON_BOROUGHS)]

    df["ReligiousCharacter"] = df["ReligiousCharacter"].astype(str).str.strip()
    df = df[df["ReligiousCharacter"].str.contains("Roman Catholic|Catholic", case=False, na=False)]

    # Numerics
    df["URN"] = pd.to_numeric(df["URN"], errors="coerce").astype("Int64")
    df["Places Offered 2025"] = pd.to_numeric(df["Places Offered 2025"], errors="coerce").fillna(0).astype(int)
    df["Apps Received 2025"] = pd.to_numeric(df["Apps Received 2025"], errors="coerce").fillna(0).astype(int)
    df = df.dropna(subset=["URN"])

    print(f"✅ Filtered to {len(df)} London Roman Catholic schools")
    return df[["URN", "Local Authority", "Places Offered 2025", "Apps Received 2025"]]


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

    print("📡 Fetching latest DfE admissions data...")
    dfe = fetch_latest_dfe_admissions()

    print("🔗 Merging DfE data into master...")
    merged = master.merge(dfe, on=["URN", "Local Authority"], how="left", suffixes=("", "_DfE"))

    # Prefer DfE values (Places Offered as PAN proxy, Apps)
    for col in ["Places Offered 2025", "Apps Received 2025"]:
        dfe_col = f"{col}_DfE"
        if dfe_col in merged.columns:
            merged[col] = merged[dfe_col].fillna(merged[col] if col in merged else 0)
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
