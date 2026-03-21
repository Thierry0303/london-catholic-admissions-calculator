import streamlit as st
import pandas as pd
import os
import numpy as np
import math
import urllib.parse
import requests
import json
import urllib.request

st.set_page_config(page_title="London Catholic Schools 2025", page_icon="✝️", layout="centered")
st.markdown('<a name="top"></a>', unsafe_allow_html=True)

# ========================================
# CONSTANTS & HELPERS
# ========================================
FULL_PATH = "catholic_schools_with_pan_coords.csv"
FULL_GITHUB = "https://raw.githubusercontent.com/Thierry0303/london-catholic-admissions-calculator/main/catholic_schools_with_pan_coords.csv"

CATHOLIC_PATTERNS = ["catholic", "roman catholic", "rc", "r.c.", "r c", "rom cath", "roman-catholic", "cath "]

RELIGION_COLS = [
    "ReligiousCharacter_DfE",
    "ReligiousCharacter",
    "ReligiousCharacter (name)"
]

def is_catholic(row):
    # First try religion columns
    for col in RELIGION_COLS:
        if col in row and isinstance(row[col], str):
            val = row[col].lower().strip()
            if any(p in val for p in CATHOLIC_PATTERNS):
                return True
    
    # Strong name-based fallback (important for academies with missing religion fields)
    if "School Name" in row and isinstance(row["School Name"], str):
        name_lower = row["School Name"].lower()
        if any(p in name_lower for p in CATHOLIC_PATTERNS):
            return True
        # Extra help for common RC school names
        if "st joseph" in name_lower or "st. joseph" in name_lower or "st john" in name_lower:
            if "catholic" in name_lower or "rc" in name_lower or "roman" in name_lower:
                return True
    
    return False

# ========================================
# DATA LOADING
# ========================================
@st.cache_data
def load_data():
    df = pd.read_csv(FULL_PATH) if os.path.exists(FULL_PATH) else pd.read_csv(FULL_GITHUB)
    
    # Clean URN
    df["URN"] = pd.to_numeric(df.get("URN"), errors="coerce").astype("Int64")
    
    # Remove duplicates
    df = df.drop_duplicates(subset=["URN"], keep="first")
    
    # Apply catholic filter with improved logic
    df = df[df.apply(is_catholic, axis=1)]
    
    # Numeric conversions
    df["PAN 2025"] = pd.to_numeric(df.get("PAN 2025"), errors="coerce").fillna(0).astype(int)
    df["1st Pref Apps 2025"] = pd.to_numeric(df.get("1st Pref Apps 2025"), errors="coerce").fillna(0).astype(int)
    df["PAN 2025"] = df["PAN 2025"].replace(0, 1)  # avoid division by zero
    
    df["Oversub Ratio"] = (df["1st Pref Apps 2025"] / df["PAN 2025"]) * 100
    df["Oversub Ratio"] = df["Oversub Ratio"].round(0).astype(int)
    
    # Fill missing columns
    for col in ["Phone", "School Website", "Ofsted Rating", "Last Inspection",
                "Snobe Overall Grade", "Phase", "Postcode"]:
        if col not in df.columns:
            df[col] = ""
    
    df["School Website"] = df["School Website"].astype(str).str.strip().replace({"": np.nan, "nan": np.nan})
    df["School Website"] = df["School Website"].apply(
        lambda x: f"http://{x}" if pd.notnull(x) and not str(x).startswith(("http://", "https://")) else x
    )
    
    def ofsted_badge(r):
        r = str(r)
        if "Outstanding" in r: return "Outstanding"
        if "Good" in r: return "Good"
        if "Requires" in r: return "Requires Improvement"
        if "Inadequate" in r: return "Inadequate"
        return "Awaiting"
    
    df["Ofsted Badge"] = df["Ofsted Rating"].apply(ofsted_badge)
    
    if "Local Authority" in df.columns:
        df["Local Authority"] = df["Local Authority"].astype(str).str.strip().str.title()
    
    return df

# ========================================
# IMD / CRIME / POSTCODE HELPERS
# ========================================
@st.cache_data
def load_imd_lookup():
    if not os.path.exists("imd_lookup.csv"):
        return pd.DataFrame(columns=["postcode", "imd_decile", "imd_score"])
    imd = pd.read_csv("imd_lookup.csv")
    imd["postcode"] = imd["postcode"].astype(str).str.upper().str.replace(" ", "")
    return imd

def fetch_imd_for_postcode(pc, imd_df):
    if not isinstance(pc, str) or pc.strip() == "":
        return None, None
    clean = pc.upper().replace(" ", "")
    match = imd_df[imd_df["postcode"] == clean]
    if match.empty:
        return None, None
    row = match.iloc[0]
    return row.get("imd_decile"), row.get("imd_score")

def imd_label(decile):
    try:
        d = int(decile)
    except:
        return "No IMD data"
    if d <= 2: return "Very deprived (bottom 20%)"
    if d <= 4: return "More deprived than average"
    if d <= 7: return "Around average"
    if d <= 9: return "Less deprived than average"
    return "Very affluent (top 10%)"

@st.cache_data(show_spinner=False)
def fetch_crime_count(lat, lon, date="2024-01"):
    try:
        url = f"https://data.police.uk/api/crimes-street/all-crime?lat={lat}&lng={lon}&date={date}"
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            return None
        return len(resp.json())
    except:
        return None

def crime_label(count):
    if count is None: return "No crime data"
    if count < 50: return "Low recorded crime"
    if count < 150: return "Moderate recorded crime"
    if count < 300: return "High recorded crime"
    return "Very high recorded crime"

@st.cache_data(show_spinner=False)
def postcode_to_latlon(postcode: str):
    clean = postcode.strip().upper().replace(" ", "")
    try:
        url = f"https://api.postcodes.io/postcodes/{clean}"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
        if data.get("status") == 200:
            r = data["result"]
            return r["latitude"], r["longitude"]
    except Exception:
        pass
    return None, None

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# ========================================
# COMPOSITE SCORE
# ========================================
def compute_composite_score(row):
    score = 0
    # Distance
    if "Distance (km)" in row and not pd.isna(row["Distance (km)"]):
        score += row["Distance (km)"] * 2
    # Snobe
    snobe_order = {"A+":1, "A":2, "B":3, "C":4, "D":5, "E":6}
    score += snobe_order.get(row.get("Snobe Overall Grade"), 10) * 10
    # Ofsted
    ofsted_order = {
        "Outstanding": 1, "Good": 2, "Requires Improvement": 3,
        "Inadequate": 4, "Awaiting": 5
    }
    score += ofsted_order.get(row.get("Ofsted Badge"), 5) * 8
    # Oversubscription
    score += row.get("Oversub Ratio", 200) / 5
    # IMD
    try:
        imd = int(row.get("imd_decile", 5))
    except:
        imd = 5
    score += (11 - imd) * 3
    # Crime
    crime = row.get("crime_count", None)
    if crime is not None:
        score += crime / 20
    return score

# ========================================
# LOAD DATA + DEBUG
# ========================================
merged = load_data()

# Debug: Raw data check for specific school
raw_df = pd.read_csv(FULL_PATH) if os.path.exists(FULL_PATH) else pd.read_csv(FULL_GITHUB)

st.subheader("Debug: Raw data check for URN 148438 (St Joseph's Cadogan Street)")
target = raw_df[raw_df["URN"].astype(str).str.contains("148438", na=False)]
if not target.empty:
    st.dataframe(
        target[["URN", "School Name", "Local Authority", "Phase",
                "ReligiousCharacter_DfE", "ReligiousCharacter", "ReligiousCharacter (name)"]]
    )
    if "ReligiousCharacter (name)" in target.columns:
        st.write("ReligiousCharacter (name) value:", target["ReligiousCharacter (name)"].iloc[0])
else:
    st.warning("URN 148438 not found in raw CSV at all")

# Debug: After catholic filter
st.subheader("Debug: Master data after load & catholic filter")
st.write("Total rows after catholic filter:", len(merged))

st.write("Any St Joseph variants?")
joseph_mask = merged["School Name"].str.contains("joseph|st.? ?jo", case=False, na=False, regex=True)
st.dataframe(merged[joseph_mask][["URN", "School Name", "Local Authority", "Phase", "PAN 2025", "ReligiousCharacter_DfE"]].head(10))

st.write("Missing lat/long count:", merged[["Latitude", "Longitude"]].isna().sum())

st.write("Religion field top values:")
for col in RELIGION_COLS:
    if col in merged.columns:
        st.write(f"**{col}** top values:")
        st.write(merged[col].value_counts().head(8))

# ────────────────────────────────────────
# Continue with the rest of your original app from here
# (sidebar, filters, map, results, etc.)
# ────────────────────────────────────────

# Example continuation (add your full original code below this point)
imd_df = load_imd_lookup()

params = st.query_params
_qp_postcode = params.get("postcode", "")
# ... rest of your code: sidebar, filters, map, best school, results list ...
