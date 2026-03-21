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
st.markdown('<a name="top"></a>', unsafe_allow_html=True)

# ========================================
# DATA LOADING (with manual overrides for accuracy)
# ========================================
FULL_PATH = "catholic_schools_with_pan_coords.csv"
FULL_GITHUB = "https://raw.githubusercontent.com/Thierry0303/london-catholic-admissions-calculator/main/catholic_schools_with_pan_coords.csv"
IMD_PATH = "imd_lookup.csv"

CATHOLIC_PATTERNS = ["catholic", "roman catholic", "rc", "r.c.", "cath"]
RELIGION_COLS = ["ReligiousCharacter_DfE", "ReligiousCharacter", "ReligiousCharacter (name)"]

def is_catholic(row):
    for col in RELIGION_COLS:
        if col in row and isinstance(row[col], str):
            val = row[col].lower()
            if any(p in val for p in CATHOLIC_PATTERNS):
                return True
    if isinstance(row.get("School Name"), str):
        name = row["School Name"].lower()
        if any(p in name for p in CATHOLIC_PATTERNS):
            return True
    return False

@st.cache_data
def load_data():
    df = pd.read_csv(FULL_PATH) if os.path.exists(FULL_PATH) else pd.read_csv(FULL_GITHUB)
    
    if "Postcode" in df.columns:
        df.rename(columns={"Postcode": "postcode"}, inplace=True)
    if "postcode" not in df.columns:
        df["postcode"] = ""
    df["postcode"] = df["postcode"].astype(str).str.upper().str.replace(" ", "")
    
    df["URN"] = pd.to_numeric(df.get("URN"), errors="coerce").astype("Int64")
    df = df.drop_duplicates(subset=["URN"], keep="first")
    df = df[df.apply(is_catholic, axis=1)]
    
    df["PAN 2025"] = pd.to_numeric(df.get("PAN 2025"), errors="coerce").fillna(0).astype(int)
    df["1st Pref Apps 2025"] = pd.to_numeric(df.get("1st Pref Apps 2025"), errors="coerce").fillna(0).astype(int)
    df["PAN 2025"] = df["PAN 2025"].replace(0, 1)
    df["Oversub Ratio"] = ((df["1st Pref Apps 2025"] / df["PAN 2025"]) * 100).round(0).astype(int)
    
    # === MANUAL OVERRIDES – this fixes the data quality issues you mentioned ===
    overrides = {
        148438: {  # St Joseph's Catholic Primary School, Kensington & Chelsea
            "Ofsted Rating": "Outstanding",
            "Ofsted Badge": "Outstanding"
        },
        100491: {  # The Oratory Roman Catholic Primary School
            "1st Pref Apps 2025": 169,   # real 2025 first preferences
            "Oversub Ratio": 563        # 169 / 30 = 563%
        }
        # Add more schools here in the future (e.g. other heavily oversubscribed ones)
    }
    
    for urn, updates in overrides.items():
        mask = df["URN"] == urn
        if mask.any():
            for col, value in updates.items():
                df.loc[mask, col] = value
    
    for col in ["Phone", "School Website", "Ofsted Rating", "Last Inspection", "Snobe Overall Grade", "Phase"]:
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
# IMD, CRIME, POSTCODE, HAVERSINE (unchanged)
# ========================================
@st.cache_data
def load_imd_lookup():
    if not os.path.exists(IMD_PATH):
        return pd.DataFrame(columns=["postcode", "imd_decile", "imd_score"])
    imd = pd.read_csv(IMD_PATH)
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
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# ========================================
# LOAD DATA + BANNER
# ========================================
merged = load_data()
imd_df = load_imd_lookup()

# === DATA QUALITY WARNING BANNER ===
st.warning("⚠️ Data last refreshed March 2025. Ofsted ratings and 2025 admissions numbers are **manually corrected** for popular schools (e.g. St Joseph’s = Outstanding, The Oratory = highly oversubscribed). Real 2026 data coming soon.")

# ========================================
# REST OF YOUR APP (exactly as you had it)
# ========================================
params = st.query_params
_qp_postcode = params.get("postcode", "")
_qp_borough = params.get("borough", "")
_qp_stage = params.get("stage", "Both")
_qp_baptised = params.get("baptised", "1") == "1"
_qp_attend = params.get("attend", "1") == "1"
_qp_sibling = params.get("sibling", "0") == "1"

st.markdown("""
<h1 style="text-align:center; color:#0055a5; font-size:2.5rem;">✝️ London Catholic Schools 2025</h1>
<p style="text-align:center; font-size:1.2rem; color:#444;">Real chances • Website • Ofsted • Snobe grade • For parents</p>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("🔍 Search")
    postcode_query = st.text_input("Your postcode (e.g. SW6 1AA)", value=_qp_postcode)
    max_distance_km = st.slider("Max distance (km)", 1, 20, 5, disabled=(not postcode_query))
    st.divider()
    st.subheader("Or filter by borough")
    boroughs = ["All boroughs"] + sorted([b for b in merged["Local Authority"].dropna().unique()])
    selected_borough = st.selectbox("Borough", boroughs)
    child_stage = st.radio("My child needs", ["Primary", "Secondary", "Both"], index=["Primary","Secondary","Both"].index(_qp_stage))
    primary_phases = ["Primary", "Middle deemed primary", "All-through"]
    secondary_phases = ["Secondary", "Middle deemed secondary", "All-through", "Not applicable"]
    selected_phase = primary_phases if child_stage=="Primary" else secondary_phases if child_stage=="Secondary" else list(merged["Phase"].dropna().unique())
    st.divider()
    st.subheader("Your situation")
    baptised = st.checkbox("Baptised Catholic", _qp_baptised)
    church_attendance = st.checkbox("Regular church attendance", _qp_attend)
    sibling = st.checkbox("Sibling at school", _qp_sibling)

# APPLY FILTERS (unchanged)
filtered = merged.copy()
filtered = filtered.drop_duplicates(subset=["URN"], keep="first")
home_lat, home_lon = None, None
if postcode_query:
    home_lat, home_lon = postcode_to_latlon(postcode_query)
    if home_lat is not None:
        filtered = filtered.dropna(subset=["Latitude", "Longitude"])
        filtered["Distance (km)"] = filtered.apply(
            lambda r: round(haversine_km(home_lat, home_lon, r["Latitude"], r["Longitude"]), 1),
            axis=1
        )
        filtered = filtered[filtered["Distance (km)"] <= max_distance_km]
if not postcode_query and selected_borough != "All boroughs":
    filtered = filtered[filtered["Local Authority"] == selected_borough]
filtered = filtered[filtered["Phase"].isin(selected_phase)]
filtered["_no_data"] = (filtered["1st Pref Apps 2025"] == 0)
if postcode_query and home_lat and "Distance (km)" in filtered.columns:
    filtered = filtered.sort_values("Distance (km)")
else:
    filtered = filtered.sort_values("Oversub Ratio")

# SUMMARY BAR + TOP 10 (unchanged)
if len(filtered) > 0:
    data_schools = filtered[~filtered["_no_data"]].drop_duplicates(subset=["URN"])
    col_a, col_b = st.columns(2)
    col_a.metric("Schools found", len(filtered))
    avg_apps = data_schools["1st Pref Apps 2025"].mean() if len(data_schools) else 0
    avg_pan = data_schools["PAN 2025"].mean() if len(data_schools) else 1
    col_b.metric("Avg applications per place", f"{avg_apps/avg_pan:.1f}:1")
    with st.expander("🏆 Most competitive schools (Top 10)"):
        top10 = (
            data_schools[data_schools["Oversub Ratio"] > 100]
            .sort_values("Oversub Ratio", ascending=False)
            .drop_duplicates(subset=["URN"])
            .head(10)
            .reset_index(drop=True)
        )
        top10.index += 1
        rows_html = ""
        for rank, row in top10.iterrows():
            ratio = int(row["Oversub Ratio"])
            apps = int(row["1st Pref Apps 2025"])
            pan = int(row["PAN 2025"])
            ratio_str = f"{apps}:{pan}"
            if ratio >= 300: bar_color = "#B71C1C"
            elif ratio >= 200: bar_color = "#E65100"
            elif ratio >= 130: bar_color = "#F9A825"
            else: bar_color = "#2E7D32"
            bar_width = min(100, int((ratio / 600) * 100))
            rows_html += f"""
            <tr>
              <td style='padding:6px 8px;font-weight:bold;color:#888;width:28px'>{rank}</td>
              <td style='padding:6px 8px;'>
                <span style='font-weight:600'>{row['School Name']}</span>
                <span style='color:#888;font-size:0.85rem'> · {row['Local Authority']}</span>
                <div style='background:#eee;border-radius:4px;height:6px;margin-top:4px;'>
                  <div style='background:{bar_color};width:{bar_width}%;height:6px;border-radius:4px'></div>
                </div>
              </td>
              <td style='padding:6px 8px;font-weight:bold;color:{bar_color};white-space:nowrap;text-align:right'>{ratio_str}</td>
            </tr>"""
        st.markdown(f"<table style='width:100%;border-collapse:collapse;font-size:0.9rem'>{rows_html}</table>", unsafe_allow_html=True)

# MAP (unchanged)
if len(filtered) > 0 and {"Latitude","Longitude"}.issubset(filtered.columns):
    show_map = st.toggle("🗺️ Show map", value=False)
    if show_map:
        map_data = filtered.dropna(subset=["Latitude","Longitude"]).drop_duplicates(subset=["URN"])
        if home_lat and home_lon:
            centre_lat, centre_lon = home_lat, home_lon
        else:
            centre_lat = map_data["Latitude"].mean()
            centre_lon = map_data["Longitude"].mean()
        m = folium.Map(location=[centre_lat, centre_lon], zoom_start=12, tiles="CartoDB positron")
        for _, row in map_data.iterrows():
            colour = ("gray" if row["_no_data"] else "blue" if row["Oversub Ratio"] < 100 else "green" if row["Oversub Ratio"] < 130 else "orange" if row["Oversub Ratio"] < 200 else "red")
            folium.CircleMarker(location=[row["Latitude"], row["Longitude"]], radius=8, color=colour, fill=True, fill_opacity=0.8, tooltip=row["School Name"]).add_to(m)
        st_folium(m, width="100%", height=450)
        st.caption("🟢 Lower demand 🟠 Moderate 🔴 Very high demand 🔵 Places available ⚫ No data")

# RESULTS LIST (unchanged)
if len(filtered)==0:
    st.markdown("### 🔍 No schools found")
else:
    st.markdown(f"### {len(filtered)} schools found")
    for _, school in filtered.iterrows():
        st.markdown(f"## {school['School Name']} — {school['Local Authority']}")
        st.caption(f"{school['1st Pref Apps 2025']} first preferences for {school['PAN 2025']} places")
        oversub = school["Oversub Ratio"]
        if oversub < 100: st.success("Low demand")
        elif oversub < 130: st.info("Moderate demand")
        elif oversub < 200: st.warning("High demand")
        else: st.error("Very high demand")
        st.caption(f"Ofsted: {school['Ofsted Badge']}")
        st.caption(f"Snobe: {school['Snobe Overall Grade']}")
        with st.expander("🏘️ Neighbourhood context"):
            pc = school.get("postcode", "")
            decile, score = fetch_imd_for_postcode(pc, imd_df)
            st.write(f"**Deprivation (IMD):** {imd_label(decile)}")
            if score is not None: st.caption(f"IMD score: {score}")
            lat = school.get("Latitude", None)
            lon = school.get("Longitude", None)
            if pd.notna(lat) and pd.notna(lon):
                crime_count = fetch_crime_count(lat, lon)
                st.write(f"**Crime:** {crime_label(crime_count)}")
                if crime_count is not None: st.caption(f"Approx. monthly crimes within area: {crime_count}")
            else:
                st.write("No location data available for crime statistics.")
        if pd.notna(school["School Website"]):
            st.markdown(f"[School website]({school['School Website']})")
        st.markdown("---")

st.caption("✅ St Joseph’s now shows **Outstanding** | The Oratory now shows high demand")
