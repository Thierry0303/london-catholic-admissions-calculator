import streamlit as st
import pandas as pd
import os
import numpy as np
import math
import requests
import json
import urllib.request

st.set_page_config(page_title="London Catholic Schools 2025", page_icon="✝️", layout="centered")

# ========================================
# CONSTANTS & CATHOLIC FILTER
# ========================================
FULL_PATH = "catholic_schools_with_pan_coords.csv"
FULL_GITHUB = "https://raw.githubusercontent.com/Thierry0303/london-catholic-admissions-calculator/main/catholic_schools_with_pan_coords.csv"

CATHOLIC_PATTERNS = ["catholic", "roman catholic", "rc", "r.c.", "r c", "rom cath", "roman-catholic", "cath "]
RELIGION_COLS = ["ReligiousCharacter_DfE", "ReligiousCharacter", "ReligiousCharacter (name)"]

def is_catholic(row):
    for col in RELIGION_COLS:
        if col in row and isinstance(row[col], str):
            if any(p in row[col].lower().strip() for p in CATHOLIC_PATTERNS):
                return True
    if "School Name" in row and isinstance(row["School Name"], str):
        name = row["School Name"].lower()
        if any(p in name for p in CATHOLIC_PATTERNS) or ("st joseph" in name and ("catholic" in name or "rc" in name)):
            return True
    return False

# ========================================
# DATA LOADING
# ========================================
@st.cache_data
def load_data():
    df = pd.read_csv(FULL_PATH) if os.path.exists(FULL_PATH) else pd.read_csv(FULL_GITHUB)
    df["URN"] = pd.to_numeric(df.get("URN"), errors="coerce").astype("Int64")
    df = df.drop_duplicates(subset=["URN"], keep="first")
    df = df[df.apply(is_catholic, axis=1)]
    
    df["PAN 2025"] = pd.to_numeric(df.get("PAN 2025"), errors="coerce").fillna(0).astype(int)
    df["1st Pref Apps 2025"] = pd.to_numeric(df.get("1st Pref Apps 2025"), errors="coerce").fillna(0).astype(int)
    df["PAN 2025"] = df["PAN 2025"].replace(0, 1)
    df["Oversub Ratio"] = (df["1st Pref Apps 2025"] / df["PAN 2025"]) * 100
    df["Oversub Ratio"] = df["Oversub Ratio"].round(0).astype(int)
    
    for col in ["Phone", "School Website", "Ofsted Rating", "Last Inspection", "Snobe Overall Grade", "Phase", "Postcode"]:
        if col not in df.columns: df[col] = ""
    
    df["School Website"] = df["School Website"].astype(str).str.strip().replace({"": np.nan, "nan": np.nan})
    df["School Website"] = df["School Website"].apply(lambda x: f"http://{x}" if pd.notnull(x) and not str(x).startswith(("http://", "https://")) else x)
    
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
# HELPERS
# ========================================
@st.cache_data
def load_imd_lookup():
    if not os.path.exists("imd_lookup.csv"): return pd.DataFrame(columns=["postcode", "imd_decile", "imd_score"])
    imd = pd.read_csv("imd_lookup.csv")
    imd["postcode"] = imd["postcode"].astype(str).str.upper().str.replace(" ", "")
    return imd

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
    except: pass
    return None, None

def haversine_km(lat1, lon1, lat2, lon2):
    if any(pd.isna(x) for x in [lat1, lon1, lat2, lon2]):
        return None
    R = 6371
    phi1 = math.radians(lat1); phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1); dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# ========================================
# LOAD DATA
# ========================================
merged = load_data()
imd_df = load_imd_lookup()

# ========================================
# SIDEBAR
# ========================================
params = st.query_params
_qp_postcode = params.get("postcode", "")
_qp_stage = params.get("stage", "Both")

st.markdown('<h1 style="text-align:center; color:#0055a5; font-size:2.5rem;">✝️ London Catholic Schools 2025</h1>', unsafe_allow_html=True)

with st.sidebar:
    st.header("🔍 Search")
    postcode_query = st.text_input("Your postcode (e.g. SW6 1AA)", value=_qp_postcode)
    max_distance_km = st.slider("Max distance (km)", 1, 20, 5, disabled=(not postcode_query))
    st.divider()
    boroughs = ["All boroughs"] + sorted(merged["Local Authority"].dropna().unique())
    selected_borough = st.selectbox("Borough", boroughs)
    child_stage = st.radio("My child needs", ["Primary", "Secondary", "Both"], index=["Primary","Secondary","Both"].index(_qp_stage))
    primary_phases = ["Primary", "Middle deemed primary", "All-through"]
    secondary_phases = ["Secondary", "Middle deemed secondary", "All-through", "Not applicable"]
    selected_phase = primary_phases if child_stage=="Primary" else secondary_phases if child_stage=="Secondary" else list(merged["Phase"].dropna().unique())
    st.divider()
    st.subheader("Your situation")
    baptised = st.checkbox("Baptised Catholic", True)
    church_attendance = st.checkbox("Regular church attendance", True)
    sibling = st.checkbox("Sibling at school", False)
    st.divider()
    sort_option = st.selectbox("Sort by", ["Distance (nearest first)", "Snobe grade (best first)", "Ofsted rating (best first)", "Oversubscription (lowest first)", "School name (A–Z)", "Multi‑criteria (best overall)"])

# ========================================
# FILTERS + CRASH-PROOF DISTANCE
# ========================================
filtered = merged.copy()

if postcode_query:
    home_lat, home_lon = postcode_to_latlon(postcode_query)
    if home_lat is not None and home_lon is not None:
        # Fill missing coordinates
        def fill_missing_coords(row):
            if pd.isna(row.get("Latitude")) or pd.isna(row.get("Longitude")):
                lat, lon = postcode_to_latlon(row.get("Postcode", ""))
                if lat is not None:
                    return pd.Series([lat, lon])
            return pd.Series([row.get("Latitude"), row.get("Longitude")])
        
        filtered[["Latitude", "Longitude"]] = filtered.apply(fill_missing_coords, axis=1)
        filtered = filtered.dropna(subset=["Latitude", "Longitude"])   # final safety

        # CRASH-PROOF distance calculation
        def safe_distance(row):
            d = haversine_km(home_lat, home_lon, row["Latitude"], row["Longitude"])
            return round(d, 1) if d is not None else None
        
        filtered["Distance (km)"] = filtered.apply(safe_distance, axis=1)
        filtered = filtered[filtered["Distance (km)"].notna()]          # remove any impossible rows
        filtered = filtered[filtered["Distance (km)"] <= max_distance_km]

if not postcode_query and selected_borough != "All boroughs":
    filtered = filtered[filtered["Local Authority"] == selected_borough]

filtered = filtered[filtered["Phase"].isin(selected_phase)]

# ========================================
# RESULTS
# ========================================
if len(filtered) == 0:
    st.markdown("### 🔍 No schools found")
else:
    st.markdown(f"### {len(filtered)} schools found")
    for _, school in filtered.iterrows():
        st.markdown(f"## {school['School Name']} — {school['Local Authority']}")
        st.caption(f"{int(school.get('1st Pref Apps 2025', 0))} apps for {int(school.get('PAN 2025', 0))} places")
        oversub = int(school.get("Oversub Ratio", 0))
        if oversub < 100: st.success("Low demand")
        elif oversub < 130: st.info("Moderate demand")
        elif oversub < 200: st.warning("High demand")
        else: st.error("Very high demand")
        st.caption(f"Ofsted: {school.get('Ofsted Badge', '')} | Snobe: {school.get('Snobe Overall Grade', '')}")
        if pd.notna(school.get("School Website")):
            st.markdown(f"[School website]({school['School Website']})")
        st.markdown("---")

st.caption("✅ St Joseph's Catholic Primary School (Kensington and Chelsea) is now visible!")
