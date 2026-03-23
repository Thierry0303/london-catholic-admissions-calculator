"""
refresh_data.py
───────────────
Automatically updates catholic_schools_with_pan_coords.csv with:
  1. DfE school-level applications & offers (published each June)
  2. Ofsted ratings (from monthly management information CSV)

Run manually or via GitHub Actions (.github/workflows/refresh.yml).

Requirements: pip install pandas requests openpyxl
"""

import io
import re
import zipfile
import requests
import pandas as pd
import numpy as np

MASTER_FILE  = "catholic_schools_with_pan_coords.csv"
OUTPUT_FILE  = "catholic_schools_with_pan_coords.csv"

LONDON_LAS = {
    "Barnet","Bexley","Brent","Bromley","Camden","Croydon","Ealing","Enfield",
    "Greenwich","Hackney","Hammersmith and Fulham","Haringey","Harrow","Havering",
    "Hillingdon","Hounslow","Islington","Kensington and Chelsea",
    "Kingston upon Thames","Lambeth","Lewisham","Merton","Newham","Redbridge",
    "Richmond upon Thames","Southwark","Sutton","Tower Hamlets",
    "Waltham Forest","Wandsworth","Westminster",
}

# ── EES API: discover the latest release of applications & offers ─────────────
EES_PUB_ID   = "66c8e9db-8bf2-4b0b-b094-cfab25c20b05"   # applications & offers
EES_API_BASE = "https://api.education.gov.uk/statistics"

def get_latest_release_file_id():
    """Use EES API to find the latest release and its school-level ZIP file ID."""
    url = f"{EES_API_BASE}/releases?publicationId={EES_PUB_ID}&pageSize=1"
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        releases = r.json().get("results", [])
        if not releases:
            return None, None
        latest = releases[0]
        release_id = latest["id"]
        print(f"  Latest release: {latest.get('title', release_id)}")
    except Exception as e:
        print(f"  Could not fetch release list: {e}")
        return None, None

    # List files in this release
    url2 = f"{EES_API_BASE}/releases/{release_id}/files"
    try:
        r2 = requests.get(url2, timeout=30)
        r2.raise_for_status()
        files = r2.json().get("results", [])
        for f in files:
            name = f.get("name", "").lower()
            if "school level" in name or "school-level" in name:
                return release_id, f["id"]
        # fallback: pick the largest file
        files_sorted = sorted(files, key=lambda x: x.get("size", 0), reverse=True)
        if files_sorted:
            return release_id, files_sorted[0]["id"]
    except Exception as e:
        print(f"  Could not list release files: {e}")
    return release_id, None


def download_dfe(release_id, file_id):
    """Download and return a filtered London-only DataFrame from the DfE school-level file."""

    # Direct download URL pattern
    url = f"{EES_API_BASE}/releases/{release_id}/files/{file_id}/download"
    print(f"  Downloading DfE file (may be large)…")
    try:
        r = requests.get(url, timeout=120, stream=True)
        r.raise_for_status()
        content = r.content
    except Exception as e:
        print(f"  Download failed: {e}")
        return pd.DataFrame()

    # Handle ZIP or plain CSV
    try:
        if content[:2] == b"PK":   # ZIP magic bytes
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                csv_names = [n for n in z.namelist() if n.endswith(".csv")]
                csv_names.sort(key=lambda n: z.getinfo(n).file_size, reverse=True)
                with z.open(csv_names[0]) as f:
                    df = pd.read_csv(f, low_memory=False)
        else:
            df = pd.read_csv(io.BytesIO(content), low_memory=False)
    except Exception as e:
        print(f"  Could not parse DfE file: {e}")
        return pd.DataFrame()

    print(f"  Raw DfE rows: {len(df):,}")

    # Normalise LA column name
    la_col = next((c for c in df.columns if "la_name" in c.lower()), None)
    if la_col and la_col != "la_name":
        df = df.rename(columns={la_col: "la_name"})

    df["la_name"] = df["la_name"].astype(str).str.strip()
    df = df[df["la_name"].isin(LONDON_LAS)]
    print(f"  London rows: {len(df):,}")
    return df


def apply_dfe_to_master(master, dfe):
    """
    Update Apps, PAN and Oversub Ratio in master using DfE 1st-preference data.
    Only overwrites rows where we can find a match; never zeroes out existing data.
    """
    if dfe.empty:
        print("  DfE data empty — skipping admissions update.")
        return master

    urn_col  = next((c for c in dfe.columns if "urn" in c.lower()), None)
    app_col  = next((c for c in dfe.columns if "1st_preference" in c.lower() and "put" in c.lower()), None)
    pan_col  = next((c for c in dfe.columns if "places_offered" in c.lower()), None)
    off_col  = next((c for c in dfe.columns if "1st_preference_offers" in c.lower() and "number" in c.lower()), None)

    if not all([urn_col, app_col, pan_col]):
        print(f"  Warning: could not find required DfE columns. Found: {list(dfe.columns[:10])}")
        return master

    print(f"  Matching on: URN={urn_col}, apps={app_col}, pan={pan_col}")

    dfe["_urn"] = pd.to_numeric(dfe[urn_col], errors="coerce")
    dfe = dfe.dropna(subset=["_urn"])
    dfe["_urn"] = dfe["_urn"].astype(int)
    dfe_idx = dfe.set_index("_urn")

    updated = 0
    for i, row in master.iterrows():
        urn = int(row["URN"]) if pd.notna(row["URN"]) else None
        if urn is None or urn not in dfe_idx.index:
            continue
        d = dfe_idx.loc[urn]
        if isinstance(d, pd.DataFrame):
            d = d.iloc[0]

        apps   = pd.to_numeric(d.get(app_col), errors="coerce")
        pan    = pd.to_numeric(d.get(pan_col),  errors="coerce")
        offers = pd.to_numeric(d.get(off_col),  errors="coerce") if off_col else np.nan

        if pd.isna(apps) or pd.isna(pan) or pan == 0:
            continue

        master.at[i, "Apps Received 2025"] = int(apps)
        master.at[i, "PAN"]               = int(pan)
        master.at[i, "PAN 2025"]          = int(pan)
        if pd.notna(offers):
            master.at[i, "Offers Made 2025"] = int(offers)
        master.at[i, "Oversub Ratio"] = round(apps / pan * 100, 6)
        updated += 1

    print(f"  Updated {updated} schools from DfE data.")
    return master


# ── Ofsted monthly management information ────────────────────────────────────
OFSTED_MI_URL = (
    "https://www.gov.uk/government/statistical-data-sets/"
    "monthly-management-information-ofsteds-school-inspections-outcomes"
)

def fetch_ofsted_ratings():
    """
    Fetch Ofsted monthly MI CSV and return URN → EffectivenessGrade mapping.
    Falls back gracefully if unavailable.
    """
    print("  Fetching Ofsted monthly management information page…")
    try:
        r = requests.get(OFSTED_MI_URL, timeout=30)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        print(f"  Could not fetch Ofsted MI page: {e}")
        return {}

    # Find CSV download link
    csv_links = re.findall(r'href="(https://[^"]+\.csv)"', html)
    if not csv_links:
        print("  No CSV link found on Ofsted MI page.")
        return {}

    csv_url = csv_links[0]
    print(f"  Downloading Ofsted CSV: {csv_url}")
    try:
        r2 = requests.get(csv_url, timeout=60)
        r2.raise_for_status()
        df = pd.read_csv(io.BytesIO(r2.content), encoding="latin-1", low_memory=False)
    except Exception as e:
        print(f"  Could not download/parse Ofsted CSV: {e}")
        return {}

    print(f"  Ofsted rows: {len(df):,}")

    # Find URN and rating columns (column names vary across releases)
    urn_col = next((c for c in df.columns if c.strip().lower() in ("urn", "school urn")), None)
    grade_col = next((
        c for c in df.columns
        if "overall" in c.lower() and "effectiveness" in c.lower()
    ), None)

    if not urn_col or not grade_col:
        print(f"  Could not find URN/grade columns. Columns: {list(df.columns[:15])}")
        return {}

    df["_urn"] = pd.to_numeric(df[urn_col], errors="coerce")
    df = df.dropna(subset=["_urn"])
    df["_urn"] = df["_urn"].astype(int)

    mapping = {}
    for _, row in df.iterrows():
        grade = str(row[grade_col]).strip()
        if grade and grade.lower() not in ("nan", ""):
            mapping[row["_urn"]] = grade

    print(f"  Ofsted ratings loaded: {len(mapping):,}")
    return mapping


def apply_ofsted(master, ofsted_map):
    """Update Ofsted Rating column from fresh mapping."""
    if not ofsted_map:
        print("  Ofsted map empty — skipping Ofsted update.")
        return master

    updated = 0
    for i, row in master.iterrows():
        urn = int(row["URN"]) if pd.notna(row["URN"]) else None
        if urn and urn in ofsted_map:
            raw = ofsted_map[urn]
            # Normalise to our existing format "Ofsted Outstanding" etc.
            for label in ("Outstanding", "Good", "Requires Improvement", "Inadequate"):
                if label.lower() in raw.lower():
                    master.at[i, "Ofsted Rating"] = f"Ofsted {label}"
                    updated += 1
                    break

    print(f"  Updated {updated} Ofsted ratings.")
    return master


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("=== refresh_data.py ===\n")

    print("Loading master CSV…")
    master = pd.read_csv(MASTER_FILE, low_memory=False)
    master["URN"] = pd.to_numeric(master["URN"], errors="coerce")
    master = master.dropna(subset=["URN"])
    master["URN"] = master["URN"].astype(int)
    print(f"  {len(master)} schools loaded.\n")

    # ── DfE admissions ──────────────────────────────────────────────────────
    print("Step 1: DfE admissions data")
    release_id, file_id = get_latest_release_file_id()
    if release_id and file_id:
        dfe = download_dfe(release_id, file_id)
        master = apply_dfe_to_master(master, dfe)
    else:
        print("  Could not resolve DfE release/file ID — skipping.")
    print()

    # ── Ofsted ratings ──────────────────────────────────────────────────────
    print("Step 2: Ofsted ratings")
    ofsted_map = fetch_ofsted_ratings()
    master = apply_ofsted(master, ofsted_map)
    print()

    # ── Enforce column order & save ─────────────────────────────────────────
    COLS = [
        "url","URN","School Name","Local Authority","Street","Town","Postcode","Phase",
        "ReligiousCharacter (name)","PAN 2025","Apps Received 2025","Offers Made 2025",
        "1st Pref Rate %","Oversub Ratio","Latitude","Longitude","EstablishmentName",
        "PAN","Snobe Overall Grade","Ofsted Rating","School Website",
        "Ofsted","Snobe","Website","Independent",
    ]
    for c in COLS:
        if c not in master.columns:
            master[c] = ""
    master = master[COLS]

    master.to_csv(OUTPUT_FILE, index=False)
    print(f"Saved {OUTPUT_FILE}  ({len(master)} rows × {len(master.columns)} cols)")
    print("\n=== Done ===")


if __name__ == "__main__":
    main()
