import pandas as pd
import requests
import time
from bs4 import BeautifulSoup

MASTER_FILE = "catholic_schools_with_pan_coords.csv"
OUTPUT_FILE = "catholic_schools_with_pan_coords.csv"  # overwrite in place

LONDON_BOROUGHS = [
    "Barnet","Bexley","Brent","Bromley","Camden","Croydon","Ealing","Enfield",
    "Greenwich","Hackney","Hammersmith and Fulham","Haringey","Harrow","Havering",
    "Hillingdon","Hounslow","Islington","Kensington and Chelsea","Kingston upon Thames",
    "Lambeth","Lewisham","Merton","Newham","Redbridge","Richmond upon Thames",
    "Southwark","Sutton","Tower Hamlets","Waltham Forest","Wandsworth","Westminster"
]


def fetch_latest_dfe_admissions() -> pd.DataFrame:
    """
    Fetch latest DfE 'School applications and offers' CSV via data.gov.uk API,
    filter to London + Catholic, and return a tidy DataFrame with URN, PAN, Apps.
    """

    # 🔥 FIXED ENDPOINT — this one works
    PACKAGE_URL = "https://www.data.gov.uk/api/3/action/package_show?id=school-applications-and-offers-england"

    print("🔎 Fetching DfE admissions package metadata…")
    r = requests.get(PACKAGE_URL, timeout=20)
    r.raise_for_status()
    pkg = r.json()["result"]

    # Pick latest CSV resource by last_modified
    csv_resources = [res for res in pkg["resources"] if res["format"].lower() == "csv"]
    if not csv_resources:
        raise RuntimeError("No CSV resources found in DfE package.")
    latest = max(csv_resources, key=lambda res: res.get("last_modified") or "")
    url = latest["url"]
    print(f"⬇️  Downloading latest admissions CSV:\n    {url}")

    df = pd.read_csv(url)
    print(f"✅ Loaded DfE admissions: {len(df)} rows")

    # Try to normalise column names a bit
    cols = {c.lower().strip(): c for c in df.columns}
    def find_col(*candidates):
        for cand in candidates:
            if cand.lower() in cols:
                return cols[cand.lower()]
        return None

    urn_col   = find_col("urn")
    la_col    = find_col("local authority name", "la_name", "local authority")
    rel_col   = find_col("religious character", "religiouscharacter")
    pan_col   = find_col("published admission number", "pan", "publishedadmissionnumber")
    apps_col  = find_col("total applications", "totalapplications", "number of applications")

    missing = [name for name, col in [
        ("URN", urn_col),
        ("Local Authority", la_col),
        ("Religious character", rel_col),
        ("PAN", pan_col),
        ("Applications", apps_col),
    ] if col is None]
    if missing:
        raise RuntimeError(f"Missing expected columns in DfE CSV: {', '.join(missing)}")

    df = df.rename(columns={
        urn_col:  "URN",
        la_col:   "Local Authority",
        rel_col:  "ReligiousCharacter",
        pan_col:  "PAN",
        apps_col: "Apps Received 2025",
    })

    # Filter to London boroughs
    df["Local Authority"] = df["Local Authority"].astype(str).str.strip()
    df = df[df["Local Authority"].isin(LONDON_BOROUGHS)]

    # Filter to Catholic schools
    df["ReligiousCharacter"] = df["ReligiousCharacter"].astype(str)
    df = df[df["ReligiousCharacter"].str.contains("Roman Catholic", case=False, na=False)]

    # Clean numeric
    df["URN"] = pd.to_numeric(df["URN"], errors="coerce").astype("Int64")
    df["PAN"] = pd.to_numeric(df["PAN"], errors="coerce").fillna(0).astype(int)
    df["Apps Received 2025"] = pd.to_numeric(df["Apps Received 2025"], errors="coerce").fillna(0).astype(int)

    df = df.dropna(subset=["URN"])
    print(f"✅ Filtered to London Catholic schools: {len(df)} rows")
    return df[["URN", "Local Authority", "PAN", "Apps Received 2025"]]


def fetch_snobe_grade(urn: int) -> str | None:
    """
    Fetch Snobe Overall Grade for a given URN.
    Returns grade string like 'A+' or None if not found.
    """
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
    """
    Fast mode: only fetch Snobe grade where 'Snobe Overall Grade' is missing/blank.
    """
    if "Snobe Overall Grade" not in df.columns:
        df["Snobe Overall Grade"] = ""

    mask_missing = df["Snobe Overall Grade"].astype(str).str.strip().isin(["", "nan", "NaN"])
    to_update = df[mask_missing & df["URN"].notna()].copy()

    if to_update.empty:
        print("ℹ️ No Snobe grades missing — skipping Snobe fetch.")
        return df

    print(f"🔎 Updating Snobe grades for {len(to_update)} schools (fast mode)…")
    for i, (idx, row) in enumerate(to_update.iterrows(), start=1):
        urn = int(row["URN"])
        grade = fetch_snobe_grade(urn)
        if grade:
            df.loc[idx, "Snobe Overall Grade"] = grade
            print(f"  [{i}/{len(to_update)}] URN {urn}: Snobe {grade}")
        else:
            print(f"  [{i}/{len(to_update)}] URN {urn}: no grade found")
        time.sleep(1.0)  # be polite to Snobe
    return df


def main():
    print("🔧 FULL UPDATE STARTED")
    print("📂 Loading master file…")

    master = pd.read_csv(MASTER_FILE)
    if "URN" not in master.columns:
        raise RuntimeError("Master file must contain a 'URN' column.")
    master["URN"] = pd.to_numeric(master["URN"], errors="coerce").astype("Int64")

    print("📡 Fetching latest DfE admissions…")
    dfe = fetch_latest_dfe_admissions()

    print("🔗 Merging DfE data into master…")
    merged = master.merge(dfe, on=["URN", "Local Authority"], how="left", suffixes=("", "_DfE"))

    # Prefer DfE PAN / Apps where available
    for col in ["PAN", "Apps Received 2025"]:
        dfe_col = f"{col}_DfE"
        if dfe_col in merged.columns:
            merged[col] = merged[dfe_col].fillna(merged.get(col))
            merged.drop(columns
