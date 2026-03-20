import streamlit as st
import pandas as pd
import numpy as np
import math
import urllib.parse

st.set_page_config(page_title="London Catholic Schools 2025", page_icon="✝️", layout="centered")
st.markdown('<a name="top"></a>', unsafe_allow_html=True)

# ========================================
# DATA LOADING & CLEANING
# ========================================
@st.cache_data
def load_data():
    try:
        df = pd.read_csv("catholic_schools_with_pan_coords.csv")
    except FileNotFoundError:
        st.error("CSV file not found. Make sure catholic_schools_with_pan_coords.csv is in the repo root.")
        st.stop()

    # Standardize column names (align with update_data.py)
    if '1st Pref Apps 2025' in df.columns:
        df['Apps Received 2025'] = df['1st Pref Apps 2025']
    if 'PAN 2025' in df.columns:
        df['PAN'] = df['PAN 2025']

    # Safe numeric conversion
    for col in ['PAN', 'Apps Received 2025']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
        else:
            df[col] = 0  # create column with 0 if missing

    # Ensure PAN never zero for division
    df['PAN'] = df['PAN'].replace(0, 1)

    # Calculate oversub safely
    df["Oversub Ratio"] = (df["Apps Received 2025"] / df["PAN"]) * 100
    df["Oversub Ratio"] = df["Oversub Ratio"].round(0).fillna(0).astype(int)

    # Flag no-data schools
    df["_no_data"] = (df["Apps Received 2025"] == 0)

    # Fill missing optional columns
    for col in ["Phone", "School Website", "Ofsted Rating", "Last Inspection", "Snobe Overall Grade",
                "Local Authority", "Postcode", "Phase", "School Name", "Latitude", "Longitude"]:
        if col not in df.columns:
            df[col] = ""

    # Clean website
    df["School Website"] = df["School Website"].astype(str).str.strip().replace({"": np.nan, "nan": np.nan})
    df["School Website"] = df["School Website"].apply(
        lambda x: f"https://{x}" if pd.notnull(x) and not str(x).startswith(("http://", "https://")) else x
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

    # Capitalize borough
    df["Local Authority"] = df["Local Authority"].astype(str).str.strip().str.title()

    # Last update hint
    if 'Last Updated' in df.columns:
        st.caption(f"📅 Data last auto-updated: {df['Last Updated'].max()}")
    else:
        st.caption("Data processed recently")

    return df


merged = load_data()

# ========================================
# HELPERS (postcode → lat/lon, distance)
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
    R = 6371
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# ========================================
# SIDEBAR
# ========================================
with st.sidebar:
    st.header("🔍 Search")
    postcode_query = st.text_input("Your postcode (e.g. SW6 1AA)", "")
    max_distance_km = st.slider("Max distance (km)", 1, 20, 5, disabled=not postcode_query)

    st.divider()
    st.subheader("Or filter by borough")
    boroughs = ["All boroughs"] + sorted(merged["Local Authority"].dropna().unique().tolist())
    selected_borough = st.selectbox("Borough", boroughs)

    child_stage = st.radio("My child needs", ["Primary", "Secondary", "Both"], horizontal=True)

    st.divider()
    st.subheader("Your situation")
    with st.expander("Admission criteria", expanded=True):
        baptised = st.checkbox("Baptised Catholic")
        church_attendance = st.checkbox("Regular church attendance")
        sibling = st.checkbox("Sibling at school")

# ========================================
# FILTERING
# ========================================
filtered = merged.copy()

# Phase
primary_phases = ["Primary", "Middle deemed primary", "All-through"]
secondary_phases = ["Secondary", "Middle deemed secondary", "All-through", "Not applicable"]
if child_stage == "Primary":
    filtered = filtered[filtered["Phase"].isin(primary_phases)]
elif child_stage == "Secondary":
    filtered = filtered[filtered["Phase"].isin(secondary_phases)]

# Distance
home_lat, home_lon = None, None
if postcode_query:
    home_lat, home_lon = postcode_to_latlon(postcode_query)
    if home_lat is not None and {"Latitude", "Longitude"}.issubset(filtered.columns):
        filtered = filtered.dropna(subset=["Latitude", "Longitude"])
        filtered["Distance (km)"] = filtered.apply(
            lambda r: round(haversine_km(home_lat, home_lon, r["Latitude"], r["Longitude"]), 1), axis=1
        )
        filtered = filtered[filtered["Distance (km)"] <= max_distance_km]

# Borough (if no postcode filter active)
if not postcode_query and selected_borough != "All boroughs":
    filtered = filtered[filtered["Local Authority"] == selected_borough]

# ========================================
# HEADER & SUMMARY
# ========================================
st.title("✝️ London Catholic Schools 2025")
st.caption("Real chances • Ofsted • Snobe • For parents")

if len(filtered) == 0:
    st.warning("No schools match your filters. Try widening distance or changing borough/phase.")
    st.stop()

col1, col2 = st.columns(2)
col1.metric("Schools found", len(filtered))
avg_ratio = (filtered["Apps Received 2025"] / filtered["PAN"]).mean()
col2.metric("Avg apps per place", f"{avg_ratio:.1f}:1" if not pd.isna(avg_ratio) else "—")

# ========================================
# RESULTS CARDS
# ========================================
for _, school in filtered.iterrows():
    with st.container(border=True):
        col1, col2 = st.columns([4, 1])

        with col1:
            website = school.get("School Website", "")
            name_link = f"[{school['School Name']}]({website})" if website.strip() else school['School Name']
            st.markdown(f"**{name_link}** • {school['Phase']}")

            loc = f"{school.get('Postcode', '')} • {school.get('Local Authority', '')}"
            if "Distance (km)" in school and pd.notna(school.get("Distance (km)")):
                loc += f" • {school['Distance (km)']} km"
            st.caption(loc)

            apps = int(school["Apps Received 2025"])
            pan = int(school["PAN"])
            ratio_pct = int(school["Oversub Ratio"])

            st.caption(f"**{apps} : {pan}**  ({apps} apps for {pan} places)")

            badges = []
            if school.get("Snobe Overall Grade"):
                badges.append(f"Snobe {school['Snobe Overall Grade']}")
            if school.get("Ofsted Badge") and school["Ofsted Badge"] != "Awaiting":
                badges.append(f"Ofsted {school['Ofsted Badge']}")
            if badges:
                st.caption(" • ".join(badges))

        with col2:
            # Demand badge – FIXED logic
            if school["_no_data"] or apps == 0:
                color = "#9E9E9E"
                label = "No data"
            elif ratio_pct < 100:
                color = "#1565C0"
                label = "Low demand"
            elif ratio_pct >= 400:
                color = "#B71C1C"
                label = "Very high demand"
            elif ratio_pct >= 200:
                color = "#E65100"
                label = "High demand"
            elif ratio_pct >= 130:
                color = "#F9A825"
                label = "Moderate demand"
            else:
                color = "#2E7D32"
                label = "Lower demand"

            st.markdown(
                f"""<div style="
                    background:{color};
                    color:white;
                    padding:12px;
                    border-radius:8px;
                    text-align:center;
                    font-weight:bold;
                    font-size:1rem;
                    line-height:1.3;
                ">{label}</div>""",
                unsafe_allow_html=True
            )
            st.caption(f"{ratio_pct}% oversubscribed")

        with st.expander("About these figures"):
            st.caption(
                f"In 2025, **{apps}** families listed this school for **{pan}** places. "
                "Ratio includes all applicants; Catholic schools prioritise baptised Catholics."
            )

st.divider()
st.caption("Data: DfE 2025 • Snobe • Ofsted • Built for London parents • March 2026")
