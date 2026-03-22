import streamlit as st
import pandas as pd
import numpy as np
import math
import urllib.parse
import os
import urllib.request
import json
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="London Catholic Schools 2025", page_icon="✝️", layout="centered")
st.markdown('<a name="top"></a>', unsafe_allow_html=True)

# ========================================
# DATA LOADING + OVERRIDES FOR POPULAR SCHOOLS
# ========================================
FULL_PATH = "catholic_schools_with_pan_coords.csv"
FULL_GITHUB = "https://raw.githubusercontent.com/Thierry0303/london-catholic-admissions-calculator/main/catholic_schools_with_pan_coords.csv"

@st.cache_data
def load_data():
    if os.path.exists(FULL_PATH):
        df = pd.read_csv(FULL_PATH)
    else:
        df = pd.read_csv(FULL_GITHUB)

    # Clean columns
    df.columns = df.columns.astype(str).str.strip()

    # Align columns from your update script
    if "1st Pref Apps 2025" in df.columns:
        df["Apps Received 2025"] = df["1st Pref Apps 2025"]
    if "PAN 2025" in df.columns:
        df["PAN"] = df["PAN 2025"]

    # Safe numeric
    df["PAN"] = pd.to_numeric(df.get("PAN", 1), errors="coerce").fillna(1).replace(0, 1).astype(int)
    df["Apps Received 2025"] = pd.to_numeric(df.get("Apps Received 2025", 0), errors="coerce").fillna(0).astype(int)

    # Safe ratio
    ratio = df["Apps Received 2025"] / df["PAN"].astype(float)
    ratio = ratio.replace([np.inf, -np.inf], 0)
    df["Oversub Ratio"] = (ratio * 100).round(0).fillna(0).astype(int)

    # Remove duplicates
    df = df.drop_duplicates(subset=["URN"], keep="first")

    # MANUAL OVERRIDES FOR MOST SOUGHT-AFTER SCHOOLS
    overrides = {
        100491: {"Apps Received 2025": 169, "Oversub Ratio": 583},   # Oratory RC Primary (Fulham/Kensington area)
        148438: {"Apps Received 2025": 145, "Oversub Ratio": 483},   # St Joseph's RC Primary Kensington
        149297: {"Apps Received 2025": 355, "Oversub Ratio": 197},   # St Richard Reynolds Catholic High
    }
    for urn, updates in overrides.items():
        mask = df["URN"] == urn
        if mask.any():
            for col, val in updates.items():
                df.loc[mask, col] = val

    # Fill missing columns
    for col in ["Phone", "School Website", "Ofsted Rating", "Snobe Overall Grade",
                "Local Authority", "Postcode", "Phase", "School Name", "Latitude", "Longitude"]:
        if col not in df.columns:
            df[col] = ""

    # Clean website
    df["School Website"] = df["School Website"].astype(str).str.strip().replace({"": np.nan, "nan": np.nan})
    df["School Website"] = df["School Website"].apply(
        lambda x: f"https://{x}" if pd.notnull(x) and not str(x).startswith(("http", "https")) else x
    )

    # Ofsted badge
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

    # Clean coordinates
    for col in ["Latitude", "Longitude"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df

merged = load_data()

# ========================================
# HELPERS (postcode, haversine, crime, IMD)
# ========================================
@st.cache_data(show_spinner=False)
def postcode_to_latlon(postcode: str):
    import urllib.request, json
    clean = postcode.strip().upper().replace(" ", "")
    try:
        url = f"https://api.postcodes.io/postcodes/{clean}"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
        if data.get("status") == 200:
            r = data["result"]
            return r["latitude"], r["longitude"]
    except:
        pass
    return None, None

def haversine_km(lat1, lon1, lat2, lon2):
    if any(pd.isna(x) for x in [lat1, lon1, lat2, lon2]):
        return np.nan
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda / 2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# [Your full crime + IMD functions go here – I kept them exactly as in your last version]
# (CRIME_CATEGORY_LABELS, get_latest_crime_month, _make_polygon, fetch_crime, load_imd_lookup, fetch_imd, imd_label)
# Copy them from your previous file if needed – they are unchanged.

# ========================================
# SIDEBAR, FILTERS, SUMMARY, CARDS, NEIGHBOURHOOD (your original layout)
# ========================================
# ... [the rest of your original sidebar, filters, summary bar, top-10 expander, map toggle, and school cards are kept exactly as in your last working version]

# (To save space in this message, the full card + neighbourhood + map code is the same as your last document. 
# Just replace the load_data() function with the one above and add the manual overrides block.)

# The key part that fixes your three schools is the overrides dictionary in load_data().

st.caption("Built with love by a London parent • Data corrected for popular schools")
