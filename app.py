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
# DATA LOADING + OVERRIDES
# ========================================
FULL_PATH = "catholic_schools_with_pan_coords.csv"
FULL_GITHUB = "https://raw.githubusercontent.com/Thierry0303/london-catholic-admissions-calculator/main/catholic_schools_with_pan_coords.csv"
IMD_PATH = "imd_lookup.csv"

CATHOLIC_PATTERNS = ["catholic", "roman catholic", "rc", "r.c.", "cath"]
RELIGION_COLS = ["ReligiousCharacter_DfE", "ReligiousCharacter", "ReligiousCharacter (name)"]

def is_catholic(row):
    for col in RELIGION_COLS:
        if col in row and isinstance(row[col], str):
            if any(p in row[col].lower() for p in CATHOLIC_PATTERNS):
                return True
    if isinstance(row.get("School Name"), str):
        if any(p in row["School Name"].lower() for p in CATHOLIC_PATTERNS):
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

    overrides = {
        148438: {"Ofsted Rating": "Outstanding", "Ofsted Badge": "Outstanding"},
        100491: {"1st Pref Apps 2025": 169, "Oversub Ratio": 563}
    }
    for urn, updates in overrides.items():
        mask = df["URN"] == urn
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
# HELPERS
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
    if any(pd.isna(x) or x is None for x in [lat1, lon1, lat2, lon2]):
        return None
    try:
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
        R = 6371
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    except:
        return None

# ========================================
# LOAD DATA + WARNING
# ========================================
merged = load_data()
imd_df = load_imd_lookup()

st.warning("⚠️ Data last refreshed March 2025. Ofsted ratings and 2025 admissions numbers include manual corrections.")

# ========================================
# SIDEBAR
# ========================================
params = st.query_params
_qp_postcode = params.get("postcode", "")
_qp_stage = params.get("stage", "Both")

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

# ========================================
# FILTERS + DISTANCE
# ========================================
filtered = merged.copy()
filtered = filtered.drop_duplicates(subset=["URN"], keep="first")

home_lat, home_lon = None, None
if postcode_query:
    home_lat, home_lon = postcode_to_latlon(postcode_query)

    if home_lat is not None:
        def fill_missing_coords(row):
            if pd.isna(row.get("Latitude")) or pd.isna(row.get("Longitude")):
                lat, lon = postcode_to_latlon(row.get("postcode", ""))
                if lat is not None:
                    return pd.Series([lat, lon])
            return pd.Series([row.get("Latitude"), row.get("Longitude")])

        filtered[["Latitude","Longitude"]] = filtered.apply(fill_missing_coords, axis=1)
        filtered["Latitude"] = pd.to_numeric(filtered["Latitude"], errors="coerce")
        filtered["Longitude"] = pd.to_numeric(filtered["Longitude"], errors="coerce")
        filtered = filtered.dropna(subset=["Latitude","Longitude"])

        def safe_distance(row):
            d = haversine_km(home_lat, home_lon, row["Latitude"], row["Longitude"])
            return round(d,1) if d is not None else None

        filtered["Distance (km)"] = filtered.apply(safe_distance, axis=1)
        filtered = filtered.dropna(subset=["Distance (km)"])
        filtered = filtered[filtered["Distance (km)"] <= max_distance_km]
    else:
        filtered["Distance (km)"] = np.nan
else:
    filtered["Distance (km)"] = np.nan

# ========================================
# WEIGHTED SCORING (BEFORE BOROUGH FILTER)
# ========================================
st.subheader("Best Match Weighting")

W_IMD = st.slider("Weight: IMD (lower deprivation is better)", 0.0, 1.0, 0.25)
W_CRIME = st.slider("Weight: Crime (lower crime is better)", 0.0, 1.0, 0.25)
W_ACADEMIC = st.slider("Weight: Academic strength (oversubscription)", 0.0, 1.0, 0.25)
W_DISTANCE = st.slider("Weight: Distance (closer is better)", 0.0, 1.0, 0.25)

def normalise(series):
    series = pd.to_numeric(series, errors="coerce")
    if series.dropna().empty or series.max() == series.min():
        return pd.Series(0, index=series.index)
    return (series - series.min()) / (series.max() - series.min())

if "IMD_rank" not in filtered.columns:
    filtered["IMD_rank"] = 0
if "Crime_index" not in filtered.columns:
    filtered["Crime_index"] = 0

filtered["norm_imd"] = normalise(filtered["IMD_rank"])
filtered["norm_crime"] = normalise(filtered["Crime_index"])
filtered["norm_distance"] = normalise(filtered["Distance (km)"])
filtered["norm_oversub"] = normalise(filtered["Oversub Ratio"])

filtered["norm_imd"] = 1 - filtered["norm_imd"]
filtered["norm_crime"] = 1 - filtered["norm_crime"]
filtered["norm_distance"] = 1 - filtered["norm_distance"]

filtered["Best Match Score"] = (
    W_IMD * filtered["norm_imd"] +
    W_CRIME * filtered["norm_crime"] +
    W_ACADEMIC * filtered["norm_oversub"] +
    W_DISTANCE * filtered["norm_distance"]
)

# ========================================
# BOROUGH + PHASE FILTERS (AFTER SCORING)
# ========================================
if selected_borough != "All boroughs":
    filtered = filtered[filtered["Local Authority"] == selected_borough]

filtered = filtered[filtered["Phase"].isin(selected_phase)]
filtered["_no_data"] = (filtered["1st Pref Apps 2025"] == 0)

# ========================================
# SORTING TOGGLE
# ========================================
sort_mode = st.radio(
    "Sort results by:",
    ["Best match score", "Distance", "Oversubscription"],
    index=0
)

if sort_mode == "Best match score":
    filtered = filtered.sort_values("Best Match Score", ascending=False)
elif sort_mode == "Distance":
    filtered = filtered.sort_values("Distance (km)")
else:
    filtered = filtered.sort_values("Oversub Ratio", ascending=False)

# ========================================
# BEST MATCH DISPLAY
# ========================================
if len(filtered) > 0:
    top_school = filtered.iloc[0]
    st.success(
        f"🏆 Best overall match: **{top_school['School Name']}** "
        f"(Score: {top_school['Best Match Score']:.2f})"
    )

# ========================================
# SUMMARY + TOP 10
# ========================================
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

        st.markdown(
            f"<table style='width:100%;border-collapse:collapse;font-size:0.9rem'>{rows_html}</table>",
            unsafe_allow_html=True
        )

# ========================================
# MAP
# ========================================
if len(filtered) > 0 and {"Latitude
