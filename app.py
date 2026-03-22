import pandas as pd
import requests
import time
from bs4 import BeautifulSoup

MASTER_FILE = "catholic_schools_with_pan_coords.csv"
OUTPUT_FILE = "catholic_schools_with_pan_coords.csv"

LONDON_BOROUGHS = [
    "Barnet","Bexley","Brent","Bromley","Camden","Croydon","Ealing","Enfield",
    "Greenwich","Hackney","Hammersmith and Fulham","Haringey","Harrow","Havering",
    "Hillingdon","Hounslow","Islington","Kensington and Chelsea","Kingston upon Thames",
    "Lambeth","Lewisham","Merton","Newham","Redbridge","Richmond upon Thames",
    "Southwark","Sutton","Tower Hamlets","Waltham Forest","Wandsworth","Westminster"
]


def fetch_latest_dfe_admissions() -> pd.DataFrame:
    # Latest known URL for 2025/26 admissions (first-pref data)
    CSV_URL = (
        "https://content.explore-education-statistics.service.gov.uk/api/releases/"
        "5ed40264-1835-4848-a29b-446ed6c075c2/files/7c9894e4-9038-4213-823c-bf50bc993cec"
    )

    print("⬇️ Downloading latest DfE admissions data (2025/26)...")
    df = pd.read_csv(CSV_URL, low_memory=False)
    print(f"✅ Loaded {len(df):,} rows")

    rename_map = {
        "school_urn": "URN",
        "la_name": "Local Authority",
        "times_put_as_1st_preference": "1st Pref Apps 2025",               # ← PRIMARY column we want
        "times_put_as_any_preferred_school": "Any Pref Apps 2025",
        "total_number_places_offered": "Places Offered 2025 (DfE)",
    }

    df = df.rename(columns=rename_map)

    df["Local Authority"] = df["Local Authority"].astype(str).str.strip()
    df = df[df["Local Authority"].isin(LONDON_BOROUGHS)]

    df["URN"] = pd.to_numeric(df["URN"], errors="coerce").astype("Int64")
    for col in ["1st Pref Apps 2025", "Any Pref Apps 2025", "Places Offered 2025 (DfE)"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    print(f"✅ DfE data ready: {len(df):,} London schools")
    return df[["URN", "Local Authority", "1st Pref Apps 2025", "Any Pref Apps 2025", "Places Offered 2025 (DfE)"]]


def fetch_snobe_grade(urn: int) -> str | None:
    url = f"https://snobe.co.uk/schools/{urn}"
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return None
        text = BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True)
        for g in ["A+", "A", "B", "C", "D", "E"]:
            if f"Overall Grade {g}" in text:
                return g
        return None
    except:
        return None


def update_snobe_grades(df: pd.DataFrame) -> pd.DataFrame:
    if "Snobe Overall Grade" not in df.columns:
        df["Snobe Overall Grade"] = ""
    to_update = df[df["Snobe Overall Grade"].astype(str).str.strip().isin(["", "nan", "NaN"]) & df["URN"].notna()]
    if to_update.empty:
        print("ℹ️ Snobe grades already up to date")
        return df

    print(f"🔎 Updating Snobe for {len(to_update)} schools...")
    for i, (_, row) in enumerate(to_update.iterrows(), 1):
        grade = fetch_snobe_grade(int(row["URN"]))
        if grade:
            df.loc[row.name, "Snobe Overall Grade"] = grade
            print(f"  [{i}/{len(to_update)}] URN {row['URN']}: {grade}")
        time.sleep(1.2)  # polite delay
    return df


def main():
    print("🔧 Starting regular data refresh...")

    master = pd.read_csv(MASTER_FILE)
    master["URN"] = pd.to_numeric(master["URN"], errors="coerce").astype("Int64")
    print(f"📂 Loaded {len(master)} London Catholic schools")

    dfe = fetch_latest_dfe_admissions()

    print("🔗 Merging fresh DfE data...")
    merged = master.merge(dfe, on="URN", how="left", suffixes=("", "_DfE"))

    # Prefer fresh DfE values, especially first-preference
    for col in ["1st Pref Apps 2025", "Any Pref Apps 2025", "Places Offered 2025 (DfE)"]:
        dfe_col = f"{col}_DfE"
        if dfe_col in merged.columns:
            merged[col] = merged[dfe_col].combine_first(merged.get(col, 0))
            merged.drop(columns=[dfe_col], inplace=True)

    # Final demand column = first-preference apps (our main metric)
    merged["Apps Received 2025"] = merged["1st Pref Apps 2025"].fillna(0).astype(int)

    # Safe PAN from master (preferred) or fallback
    merged["PAN"] = merged["PAN 2025"].fillna(merged.get("PAN", 1)).replace(0, 1).astype(int)

    # Final oversubscription ratio
    ratio = merged["Apps Received 2025"] / merged["PAN"].astype(float)
    ratio = ratio.replace([np.inf, -np.inf], 0)
    merged["Oversub Ratio"] = (ratio * 100).round(0).fillna(0).astype(int)

    print("📊 Oversubscription ratios updated using 1st-preference applications (preferred) + master PAN")

    # Debug: show the three schools you care about
    important_urns = [100491, 148438, 149297]  # Oratory, St Joseph Kensington, St Richard Reynolds
    important = merged[merged["URN"].isin(important_urns)][
        ["School Name", "URN", "Apps Received 2025", "PAN", "Oversub Ratio"]
    ]
    if not important.empty:
        print("\n🔍 Popular schools check:")
        print(important.to_string(index=False))
    else:
        print("\nWarning: None of the popular schools (Oratory, St Joseph, St Richard Reynolds) found in data.")

    # Snobe update (unchanged)
    merged = update_snobe_grades(merged)

    merged.to_csv(OUTPUT_FILE, index=False)
    print(f"💾 Saved updated file → {OUTPUT_FILE}")
    print("🎉 Refresh complete! Run the app again to see updated demand levels.")


if __name__ == "__main__":
    main()
