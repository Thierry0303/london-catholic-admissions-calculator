import pandas as pd
import requests
import time
from bs4 import BeautifulSoup

MASTER_FILE = "catholic_schools_with_pan_coords.csv"
OUTPUT_FILE = "catholic_schools_with_pan_coords.csv"

LONDON_BOROUGHS = ["Barnet","Bexley","Brent","Bromley","Camden","Croydon","Ealing","Enfield",
                   "Greenwich","Hackney","Hammersmith and Fulham","Haringey","Harrow","Havering",
                   "Hillingdon","Hounslow","Islington","Kensington and Chelsea","Kingston upon Thames",
                   "Lambeth","Lewisham","Merton","Newham","Redbridge","Richmond upon Thames",
                   "Southwark","Sutton","Tower Hamlets","Waltham Forest","Wandsworth","Westminster"]


def fetch_latest_dfe_admissions() -> pd.DataFrame:
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
        "total_number_places_offered": "Places Offered 2025",
        "times_put_as_1st_preference": "1st Pref Apps 2025",      # ← THIS IS THE KEY CHANGE
        "times_put_as_any_preferred_school": "Any Pref Apps 2025", # extra for reference
    }

    df = df.rename(columns=rename_map)

    df["Local Authority"] = df["Local Authority"].astype(str).str.strip()
    df = df[df["Local Authority"].isin(LONDON_BOROUGHS)]

    df["URN"] = pd.to_numeric(df["URN"], errors="coerce").astype("Int64")
    df["Places Offered 2025"] = pd.to_numeric(df["Places Offered 2025"], errors="coerce").fillna(0).astype(int)
    df["1st Pref Apps 2025"] = pd.to_numeric(df["1st Pref Apps 2025"], errors="coerce").fillna(0).astype(int)
    df["Any Pref Apps 2025"] = pd.to_numeric(df["Any Pref Apps 2025"], errors="coerce").fillna(0).astype(int)

    print(f"✅ DfE data ready: {len(df):,} London schools")
    return df[["URN", "Local Authority", "Places Offered 2025", "1st Pref Apps 2025", "Any Pref Apps 2025"]]


def fetch_snobe_grade(urn: int) -> str | None:
    # (unchanged — your existing fast Snobe fetch)
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
    # (unchanged)
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
        time.sleep(1)
    return df


def main():
    print("🔧 Starting regular data refresh...")

    master = pd.read_csv(MASTER_FILE)
    master["URN"] = pd.to_numeric(master["URN"], errors="coerce").astype("Int64")
    print(f"📂 Loaded {len(master)} London Catholic schools")

    dfe = fetch_latest_dfe_admissions()

    print("🔗 Merging fresh DfE data...")
    merged = master.merge(dfe, on="URN", how="left", suffixes=("", "_DfE"))

    # Prefer fresh DfE numbers
    for col in ["1st Pref Apps 2025", "Places Offered 2025", "Any Pref Apps 2025"]:
        dfe_col = f"{col}_DfE"
        if dfe_col in merged.columns:
            merged[col] = merged[dfe_col].combine_first(merged.get(col, 0))
            merged.drop(columns=[dfe_col], inplace=True)

    # === OVERSUBSCRIPTION RATIO (FIXED) ===
    merged["Apps Received 2025"] = merged["1st Pref Apps 2025"]   # this is what parents care about
    merged["Oversub Ratio"] = (
        merged["1st Pref Apps 2025"] / merged["PAN 2025"].replace(0, 1) * 100
    ).round(0).astype(int)

    print(f"📊 Oversubscription ratios updated using 1st-preference applications + PAN 2025")

    # Show results for your example schools
    examples = merged[merged["URN"].isin([137157, 149297])]
    if not examples.empty:
        print("\n🔍 Check for popular schools:")
        print(examples[["School Name", "1st Pref Apps 2025", "PAN 2025", "Oversub Ratio"]].to_string(index=False))

    # Match rate
    matched = (merged["1st Pref Apps 2025"] > 0).sum()
    print(f"✅ {matched} of {len(merged)} schools received fresh 2025 DfE data")

    # Snobe (unchanged)
    merged = update_snobe_grades(merged)

    # Crime, IMD, Ofsted can be added here in future (see notes below)

    merged.to_csv(OUTPUT_FILE, index=False)
    print(f"💾 Saved updated file → {OUTPUT_FILE}")
    print("🎉 Refresh complete! Popular schools should now show realistic high demand.")


if __name__ == "__main__":
    main()
