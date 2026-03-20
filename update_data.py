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
    CSV_URL = (
        "https://content.explore-education-statistics.service.gov.uk/api/releases/"
        "5ed40264-1835-4848-a29b-446ed6c075c2/files/7c9894e4-9038-4213-823c-bf50bc993cec"
    )

    print("⬇️ Downloading DfE admissions CSV (2025/26)...")
    print(f"    {CSV_URL}")

    df = pd.read_csv(CSV_URL, low_memory=False)
    print(f"✅ Loaded {len(df):,} rows")

    rename_map = {
        "school_urn": "URN",
        "la_name": "Local Authority",
        "denomination": "ReligiousCharacter",
        "total_number_places_offered": "Places Offered 2025",
        "times_put_as_any_preferred_school": "Apps Received 2025",
    }

    missing = [src for src in rename_map if src not in df.columns]
    if missing:
        print("Missing columns:", missing)
        raise ValueError("CSV changed - update rename_map.")

    df = df.rename(columns=rename_map)

    df["Local Authority"] = df["Local Authority"].astype(str).str.strip()
    df = df[df["Local Authority"].isin(LONDON_BOROUGHS)]

    # NO Catholic filter here — dataset doesn't distinguish; rely on master CSV
    # (Uncomment below if you ever want broad faith schools)
    # df = df[df["ReligiousCharacter"].str.strip() == "Faith"]

    df["URN"] = pd.to_numeric(df["URN"], errors="coerce").astype("Int64")
    df["Places Offered 2025"] = pd.to_numeric(df["Places Offered 2025"], errors="coerce").fillna(0).astype(int)
    df["Apps Received 2025"] = pd.to_numeric(df["Apps Received 2025"], errors="coerce").fillna(0).astype(int)
    df = df.dropna(subset=["URN"])

    print(f"✅ DfE data prepared: {len(df):,} London schools (all faiths)")
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
    except:
        return None


def update_snobe_grades(df: pd.DataFrame) -> pd.DataFrame:
    if "Snobe Overall Grade" not in df.columns:
        df["Snobe Overall Grade"] = ""
    mask = df["Snobe Overall Grade"].astype(str).str.strip().isin(["", "nan", "NaN"])
    to_update = df[mask & df["URN"].notna()]
    if to_update.empty:
        print("ℹ️ No missing Snobe grades.")
        return df

    print(f"🔎 Fetching Snobe for {len(to_update)} schools...")
    for i, (_, row) in enumerate(to_update.iterrows(), 1):
        urn = int(row["URN"])
        grade = fetch_snobe_grade(urn)
        if grade:
            df.loc[row.name, "Snobe Overall Grade"] = grade
            print(f"  [{i}/{len(to_update)}] URN {urn}: {grade}")
        else:
            print(f"  [{i}/{len(to_update)}] URN {urn}: not found")
        time.sleep(1.0)
    return df


def main():
    print("🔧 Starting update...")
    print("📂 Loading master...")
    master = pd.read_csv(MASTER_FILE)
    master["URN"] = pd.to_numeric(master["URN"], errors="coerce").astype("Int64")
    print("Master columns:", master.columns.tolist())
    print(f"Master has {len(master)} schools (should be London Catholic only)")

    print("📡 Fetching DfE data...")
    dfe = fetch_latest_dfe_admissions()

    print("🔗 Merging on URN...")
    merged = master.merge(dfe, on="URN", how="left", suffixes=("", "_DfE"))

    # Prefer DfE fresh data where available
    for col in ["Places Offered 2025", "Apps Received 2025"]:
        dfe_col = f"{col}_DfE"
        if dfe_col in merged.columns:
            merged[col] = merged[dfe_col].combine_first(merged.get(col, pd.NA))
            merged.drop(columns=[dfe_col], inplace=True)

    # Fill missing numerics
    merged["Places Offered 2025"] = pd.to_numeric(merged.get("Places Offered 2025", 0), errors="coerce").fillna(0).astype(int)
    merged["Apps Received 2025"] = pd.to_numeric(merged.get("Apps Received 2025", 0), errors="coerce").fillna(0).astype(int)

    print("📊 Computing oversubscription...")
    merged["Oversub Ratio"] = (
        merged["Apps Received 2025"] / merged["Places Offered 2025"].replace(0, 1)
    ) * 100
    merged["Oversub Ratio"] = merged["Oversub Ratio"].round(0).astype(int)

    # Optional: flag if DfE data was added
    merged["DfE Data Updated"] = merged["Apps Received 2025"] > 0  # simplistic

    print("🏅 Snobe grades...")
    merged = update_snobe_grades(merged)

    print(f"💾 Saving {OUTPUT_FILE}")
    merged.to_csv(OUTPUT_FILE, index=False)
    print("🎉 Done! Check how many rows got new Apps/Places from DfE.")


if __name__ == "__main__":
    main()
