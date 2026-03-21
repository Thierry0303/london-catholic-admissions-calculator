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

st.set_page_config(page_title="London Catholic Schools 2025", page_icon="✝️", layout="wide")

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

def fetch_imd_for_postcode(pc, imd_df):
    if not isinstance(pc, str) or pc.strip() == "": return None, None
    clean = pc.upper().replace(" ", "")
    match = imd_df[imd_df["postcode"] == clean]
    if match.empty: return None, None
    row = match.iloc[0]
    return row.get("imd_decile"), row.get("imd_score")

def imd_label(decile):
    try: d = int(decile)
    except: return "No IMD data"
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
        return len(resp.json()) if resp.status_code == 200 else None
    except: return None

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
    except: pass
    return None, None

def haversine_km(lat1, lon1, lat2, lon2):
    if any(pd.isna(x) or x is None for x in [lat1, lon1, lat2, lon2]): return None
    try:
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
        R = 6371
        phi1 = math.radians(lat1); phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1); dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    except:
        return None

def compute_composite_score(row):
    score = 0
    if "Distance (km)" in row and not pd.isna(row["Distance (km)"]): score += row["Distance (km)"] * 2
    snobe_order = {"A+":1, "A":2, "B":3, "C":4, "D":5, "E":6}
    score += snobe_order.get(row.get("Snobe Overall Grade"), 10) * 10
    ofsted_order = {"Outstanding":1, "Good":2, "Requires Improvement":3, "Inadequate":4, "Awaiting":5}
    score += ofsted_order.get(row.get("Ofsted Badge"), 5) * 8
    score += row.get("Oversub Ratio", 200) / 5
    try: imd = int(row.get("imd_decile", 5))
    except: imd = 5
    score += (11 - imd) * 3
    crime = row.get("crime_count", None)
    if crime is not None: score += crime / 20
    return score

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
    show_best_school = st.checkbox("Show best school within distance", True)

# ========================================
# FILTERS + SAFE DISTANCE
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

filtered["imd_decile"] = filtered["Postcode"].apply(lambda pc: fetch_imd_for_postcode(pc, imd_df)[0])
filtered["crime_count"] = filtered.apply(lambda row: fetch_crime_count(row.get("Latitude"), row.get("Longitude")) if pd.notna(row.get("Latitude")) else None, axis=1)
filtered["composite_score"] = filtered.apply(composite_score, axis=1)

# ========================================
# SORTING
# ========================================
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
# SUMMARY & MAP
# ========================================
if len(filtered) > 0:
    data_schools = filtered[~filtered["_no_data"]].drop_duplicates(subset=["URN"])
    col_a, col_b = st.columns(2)
    col_a.metric("Schools found", len(filtered))
    avg_apps = data_schools["1st Pref Apps 2025"].mean() if len(data_schools) else 0
    avg_pan = data_schools["PAN 2025"].mean() if len(data_schools) else 1
    col_b.metric("Avg applications per place", f"{avg_apps/avg_pan:.1f}:1")
    
    with st.expander("🏆 Most competitive schools (Top 10)"):
        top10 = data_schools[data_schools["Oversub Ratio"] > 100].sort_values("Oversub Ratio", ascending=False).head(10)
        top10 = top10.reset_index(drop=True)
        top10.index += 1
        st.dataframe(top10[["School Name", "Local Authority", "Oversub Ratio"]])
    
    show_map = st.toggle("🗺️ Show map", value=True)
    if show_map and {"Latitude", "Longitude"}.issubset(filtered.columns):
        map_data = filtered.dropna(subset=["Latitude", "Longitude"])
        if home_lat and home_lon:
            centre_lat, centre_lon = home_lat, home_lon
        else:
            centre_lat = map_data["Latitude"].mean()
            centre_lon = map_data["Longitude"].mean()
        m = folium.Map(location=[centre_lat, centre_lon], zoom_start=12, tiles="CartoDB positron")
        for _, row in map_data.iterrows():
            colour = "gray" if row["_no_data"] else "blue" if row["Oversub Ratio"] < 100 else "green" if row["Oversub Ratio"] < 130 else "orange" if row["Oversub Ratio"] < 200 else "red"
            folium.CircleMarker(
                location=[row["Latitude"], row["Longitude"]],
                radius=8,
                color=colour,
                fill=True,
                fill_opacity=0.8,
                tooltip=row["School Name"],
            ).add_to(m)
        st_folium(m, width="100%", height=450)
        st.caption("Blue: Places available | Green: Low demand | Orange: High | Red: Very high | Gray: No data")

# ========================================
# BEST SCHOOL & COMPARISON
# ========================================
if show_best_school and postcode_query and "Distance (km)" in filtered.columns:
    nearby = filtered[filtered["Distance (km)"] <= max_distance_km]
    if len(nearby) > 0:
        best_school = nearby.sort_values("composite_score").iloc[0]
        st.markdown("## 🎯 Best school within your distance")
        st.success(f"**{best_school['School Name']}** ({best_school['Local Authority']})\nDistance: {best_school['Distance (km)']} km\nOfsted: {best_school['Ofsted Badge']}\nSnobe: {best_school['Snobe Overall Grade']}\nOversubscription: {best_school['Oversub Ratio']}%")
        
        reasons = []
        if best_school["Distance (km)"] <= 1: reasons.append("Very close to home")
        if best_school["Ofsted Badge"] == "Outstanding": reasons.append("Outstanding Ofsted")
        if best_school["Snobe Overall Grade"] in ["A+", "A"]: reasons.append("Excellent Snobe grade")
        if best_school["Oversub Ratio"] < 100: reasons.append("Not heavily oversubscribed")
        st.markdown("### Why this school?")
        for r in reasons: st.markdown(f"- {r}")
        
        if len(nearby) > 1:
            top3 = nearby.sort_values("composite_score").head(3)
            comparison_df = top3[["School Name", "Distance (km)", "Ofsted Badge", "Snobe Overall Grade", "Oversub Ratio", "imd_decile", "crime_count", "composite_score"]]
            st.dataframe(comparison_df.style.format({"Distance (km)": "{:.1f}", "Oversub Ratio": "{:.0f}", "composite_score": "{:.1f}"}))

# ========================================
# RESULTS LIST WITH NEIGHBOURHOOD CONTEXT
# ========================================
if len(filtered) == 0:
    st.markdown("### 🔍 No schools found")
else:
    st.markdown(f"### {len(filtered)} schools found")
    for _, school in filtered.iterrows():
        with st.expander(f"{school['School Name']} — {school['Local Authority']}"):
            st.subheader(school['School Name'])
            st.caption(f"{int(school.get('1st Pref Apps 2025', 0))} first preferences for {int(school.get('PAN 2025', 0))} places")
            oversub = int(school.get("Oversub Ratio", 0))
            if oversub < 100: st.success("Low demand")
            elif oversub < 130: st.info("Moderate demand")
            elif oversub < 200: st.warning("High demand")
            else: st.error("Very high demand")
            st.caption(f"**Ofsted:** {school.get('Ofsted Badge', 'N/A')} | **Snobe:** {school.get('Snobe Overall Grade', 'N/A')}")
            if pd.notna(school.get("School Website")):
                st.markdown(f"[School website]({school['School Website']})")
            
            with st.expander("🏘️ Neighbourhood context"):
                pc = school.get("Postcode", "")
                decile, score = fetch_imd_for_postcode(pc, imd_df)
                st.write(f"**Deprivation (IMD):** {imd_label(decile)}")
                if score is not None: st.caption(f"IMD score: {score}")
                lat = school.get("Latitude")
                lon = school.get("Longitude")
                if pd.notna(lat) and pd.notna(lon):
                    crime_count = fetch_crime_count(lat, lon)
                    st.write(f"**Crime:** {crime_label(crime_count)}")
                    if crime_count is not None: st.caption(f"Approx. monthly crimes: {crime_count}")
                else:
                    st.write("No location data for crime statistics.")
            st.markdown("---")
