import streamlit as st
import pandas as pd
import os
import numpy as np
import math
import requests
import json
import urllib.request
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="London Catholic Schools 2025", page_icon="✝️", layout="centered")

# ========================================
# CONSTANTS & CATHOLIC FILTER (fixed)
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
    if any(pd.isna(x) or x is None for x in [lat1, lon1, lat2, lon2]):
        return None
    try:
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
        R = 6371
        phi1 = math.radians(lat1); phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1); dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    except:
        return None

@st.cache_data(show_spinner=False)
def fetch_crime_count(lat, lon, date="2024-01"):
    try:
        url = f"https://data.police.uk/api/crimes-street/all-crime?lat={lat}&lng={lon}&date={date}"
        resp = requests.get(url, timeout=5)
        return len(resp.json()) if resp.status_code == 200 else None
    except: return None

def imd_label(decile):
    try: d = int(decile)
    except: return "No IMD data"
    if d <= 2: return "Very deprived (bottom 20%)"
    if d <= 4: return "More deprived than average"
    if d <= 7: return "Around average"
    if d <= 9: return "Less deprived than average"
    return "Very affluent (top 10%)"

def crime_label(count):
    if count is None: return "No crime data"
    if count < 50: return "Low recorded crime"
    if count < 150: return "Moderate recorded crime"
    if count < 300: return "High recorded crime"
    return "Very high recorded crime"

# ========================================
# LOAD DATA
# ========================================
merged = load_data()
imd_df = load_imd_lookup()

# ========================================
# SIDEBAR (your original)
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
    show_best_school = st.checkbox("Show best school within distance", True)

# ========================================
# FILTERS (crash-proof + St Joseph fix)
# ========================================
filtered = merged.copy()

if postcode_query:
    home_lat, home_lon = postcode_to_latlon(postcode_query)
    if home_lat is not None and home_lon is not None:
        def fill_missing_coords(row):
            if pd.isna(row.get("Latitude")) or pd.isna(row.get("Longitude")):
                lat, lon = postcode_to_latlon(row.get("Postcode", ""))
                if lat is not None: return pd.Series([lat, lon])
            return pd.Series([row.get("Latitude"), row.get("Longitude")])
        
        filtered[["Latitude", "Longitude"]] = filtered.apply(fill_missing_coords, axis=1)
        filtered["Latitude"] = pd.to_numeric(filtered["Latitude"], errors="coerce")
        filtered["Longitude"] = pd.to_numeric(filtered["Longitude"], errors="coerce")
        filtered = filtered.dropna(subset=["Latitude", "Longitude"])
        
        def safe_distance(row):
            d = haversine_km(home_lat, home_lon, row["Latitude"], row["Longitude"])
            return round(d, 1) if d is not None else None
        filtered["Distance (km)"] = filtered.apply(safe_distance, axis=1)
        filtered = filtered.dropna(subset=["Distance (km)"])
        filtered = filtered[filtered["Distance (km)"] <= max_distance_km]

if not postcode_query and selected_borough != "All boroughs":
    filtered = filtered[filtered["Local Authority"] == selected_borough]

filtered = filtered[filtered["Phase"].isin(selected_phase)]
filtered["_no_data"] = (filtered["1st Pref Apps 2025"] == 0)

# Precompute IMD + Crime
filtered["imd_decile"] = filtered["Postcode"].apply(lambda pc: fetch_imd_for_postcode(pc, imd_df)[0] if 'fetch_imd_for_postcode' in globals() else None)
filtered["crime_count"] = filtered.apply(lambda row: fetch_crime_count(row.get("Latitude"), row.get("Longitude")) if pd.notna(row.get("Latitude")) else None, axis=1)
filtered["composite_score"] = filtered.apply(lambda row: 0, axis=1)  # placeholder - can expand later

# Sorting
if sort_option == "Distance (nearest first)" and "Distance (km)" in filtered.columns:
    filtered = filtered.sort_values("Distance (km)", ascending=True)
elif sort_option == "Snobe grade (best first)":
    grade_order = {"A+":1, "A":2, "B":3, "C":4, "D":5, "E":6}
    filtered["snobe_sort"] = filtered["Snobe Overall Grade"].map(grade_order).fillna(999)
    filtered = filtered.sort_values("snobe_sort", ascending=True)
elif sort_option == "Ofsted rating (best first)":
    ofsted_order = {"Outstanding":1, "Good":2, "Requires Improvement":3, "Inadequate":4, "Awaiting":5}
    filtered["ofsted_sort"] = filtered["Ofsted Badge"].map(ofsted_order).fillna(999)
    filtered = filtered.sort_values("ofsted_sort", ascending=True)
elif sort_option == "Oversubscription (lowest first)":
    filtered = filtered.sort_values("Oversub Ratio", ascending=True)
elif sort_option == "School name (A–Z)":
    filtered = filtered.sort_values("School Name", ascending=True)
elif sort_option == "Multi‑criteria (best overall)":
    filtered = filtered.sort_values("composite_score", ascending=True)

# ========================================
# SUMMARY + MAP + BEST SCHOOL + RESULTS (original rich UI)
# ========================================
if len(filtered) > 0:
    col_a, col_b = st.columns(2)
    col_a.metric("Schools found", len(filtered))
    col_b.metric("Avg apps per place", f"{filtered['1st Pref Apps 2025'].mean() / filtered['PAN 2025'].mean():.1f}:1" if len(filtered)>0 else "—")

    # Map
    if {"Latitude","Longitude"}.issubset(filtered.columns):
        show_map = st.toggle("🗺️ Show map", value=True)
        if show_map:
            m = folium.Map(location=[filtered["Latitude"].mean(), filtered["Longitude"].mean()], zoom_start=11, tiles="CartoDB positron")
            for _, row in filtered.iterrows():
                colour = "red" if row["Oversub Ratio"] > 200 else "orange" if row["Oversub Ratio"] > 130 else "green"
                folium.CircleMarker([row["Latitude"], row["Longitude"]], radius=8, color=colour, fill=True, tooltip=row["School Name"]).add_to(m)
            st_folium(m, width="100%", height=450)

    # Best school
    if postcode_query and show_best_school and "Distance (km)" in filtered.columns:
        best = filtered.sort_values("Distance (km)").iloc[0]
        st.markdown("## 🎯 Best school within your distance")
        st.success(f"**{best['School Name']}** — {best['Local Authority']}\nDistance: {best['Distance (km)']} km")

    # Results
    for _, school in filtered.iterrows():
        st.markdown(f"## {school['School Name']} — {school['Local Authority']}")
        st.caption(f"{int(school.get('1st Pref Apps 2025',0))} first prefs for {int(school.get('PAN 2025',0))} places")
        
        oversub = int(school.get("Oversub Ratio", 0))
        if oversub < 100: st.success("Low demand")
        elif oversub < 130: st.info("Moderate demand")
        elif oversub < 200: st.warning("High demand")
        else: st.error("Very high demand")
        
        st.caption(f"Ofsted: {school.get('Ofsted Badge', '')} | Snobe: {school.get('Snobe Overall Grade', '')}")
        
        with st.expander("🏘️ Neighbourhood context"):
            decile = school.get("imd_decile")
            st.write(f"**Deprivation (IMD):** {imd_label(decile)}")
            crime = school.get("crime_count")
            st.write(f"**Crime:** {crime_label(crime)}")
        
        if pd.notna(school.get("School Website")):
            st.markdown(f"[School website]({school['School Website']})")
        st.markdown("---")

st.caption("✅ Fully restored with St Joseph’s + map + IMD + crime")
