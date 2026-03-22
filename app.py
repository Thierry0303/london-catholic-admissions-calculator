import streamlit as st
import pandas as pd
import numpy as np
import math
import urllib.parse
import os

st.set_page_config(page_title="London Catholic Schools 2025", page_icon="✝️", layout="centered")
st.markdown('<a name="top"></a>', unsafe_allow_html=True)

# ========================================
# DATA LOADING – ROBUST & ERROR-PROOF
# ========================================
@st.cache_data
def load_data():
    FULL_PATH = "catholic_schools_with_pan_coords.csv"
    FULL_GITHUB = "https://raw.githubusercontent.com/Thierry0303/london-catholic-admissions-calculator/main/catholic_schools_with_pan_coords.csv"

    # Try local first, then GitHub
    try:
        if os.path.exists(FULL_PATH):
            df = pd.read_csv(FULL_PATH)
        else:
            df = pd.read_csv(FULL_GITHUB)
    except Exception as e:
        st.error(f"Failed to load CSV: {str(e)}\n\nCheck file exists and is valid.")
        st.stop()

    # Clean column names
    df.columns = df.columns.astype(str).str.strip().str.replace(r'\u00A0|\uFEFF', ' ', regex=True)

    # Auto-detect PAN and Apps columns
    pan_col = next((c for c in df.columns if "pan" in c.lower() or "admission" in c.lower()), None)
    apps_col = next((c for c in df.columns if ("app" in c.lower() or "pref" in c.lower()) and "2025" in c.lower()), None)

    # Safe numeric conversion
    if pan_col:
        df["PAN"] = pd.to_numeric(df[pan_col], errors="coerce").fillna(1).replace(0, 1).astype(int)
    else:
        df["PAN"] = 1  # fallback

    if apps_col:
        df["Apps Received 2025"] = pd.to_numeric(df[apps_col], errors="coerce").fillna(0).astype(int)
    else:
        df["Apps Received 2025"] = 0

    # Oversub ratio – safe (no inf/NaN)
    ratio = df["Apps Received 2025"] / df["PAN"].astype(float)
    ratio = ratio.replace([np.inf, -np.inf], 0)
    df["Oversub Ratio"] = (ratio * 100).round(0).fillna(0).astype(int)

    df["_no_data"] = (df["Apps Received 2025"] == 0)

    # Fill optional columns
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

    # Normalise borough
    if "Local Authority" in df.columns:
        df["Local Authority"] = df["Local Authority"].astype(str).str.strip().str.title()

    # Clean coordinates
    for col in ["Latitude", "Longitude"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df

merged = load_data()

# ========================================
# HELPERS
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
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# ========================================
# QUERY PARAMS
# ========================================
params = st.query_params
_qp_postcode = params.get("postcode", "")
_qp_borough = params.get("borough", "")
_qp_stage = params.get("stage", "Both")
_qp_baptised = params.get("baptised", "1") == "1"
_qp_attend = params.get("attend", "1") == "1"
_qp_sibling = params.get("sibling", "0") == "1"

# ========================================
# HEADER
# ========================================
st.markdown("""
<h1 style="text-align:center; color:#0055a5; font-size:2.5rem;">✝️ London Catholic Schools 2025</h1>
<p style="text-align:center; font-size:1.2rem; color:#444;">Real chances • Ofsted • Snobe • For parents</p>
""", unsafe_allow_html=True)

# ========================================
# SIDEBAR
# ========================================
with st.sidebar:
    st.header("🔍 Search")
    postcode_query = st.text_input("Your postcode (e.g. SW6 1AA)", value=_qp_postcode)
    max_distance_km = st.slider("Max distance (km)", 1, 20, 5, disabled=not postcode_query)

    st.divider()
    st.subheader("Or filter by borough")
    boroughs = ["All boroughs"] + sorted(merged["Local Authority"].dropna().unique().tolist())
    selected_borough = st.selectbox("Borough", boroughs, index=boroughs.index(_qp_borough) if _qp_borough in boroughs else 0)

    child_stage = st.radio("My child needs", ["Primary", "Secondary", "Both"], index=["Primary", "Secondary", "Both"].index(_qp_stage))

    st.divider()
    st.subheader("Your situation")
    with st.expander("Admission criteria", expanded=True):
        baptised = st.checkbox("Baptised Catholic", value=_qp_baptised)
        church_attendance = st.checkbox("Regular church attendance", value=_qp_attend)
        sibling = st.checkbox("Sibling at school", value=_qp_sibling)

# ========================================
# APPLY FILTERS
# ========================================
filtered = merged.copy()

# Postcode distance
home_lat, home_lon = None, None
if postcode_query:
    home_lat, home_lon = postcode_to_latlon(postcode_query)
    if home_lat is not None and {"Latitude", "Longitude"}.issubset(filtered.columns):
        valid = filtered["Latitude"].notna() & filtered["Longitude"].notna()
        filtered["Distance (km)"] = np.nan
        if valid.any():
            filtered.loc[valid, "Distance (km)"] = filtered.loc[valid].apply(
                lambda r: round(haversine_km(home_lat, home_lon, r["Latitude"], r["Longitude"]), 1), axis=1
            )
        filtered = filtered[(filtered["Distance (km)"].isna()) | (filtered["Distance (km)"] <= max_distance_km)]

# Borough filter
if selected_borough != "All boroughs":
    filtered = filtered[filtered["Local Authority"] == selected_borough]

# Phase filter
primary_phases = ["Primary", "Middle deemed primary", "All-through"]
secondary_phases = ["Secondary", "Middle deemed secondary", "All-through", "Not applicable"]
if child_stage == "Primary":
    filtered = filtered[filtered["Phase"].isin(primary_phases)]
elif child_stage == "Secondary":
    filtered = filtered[filtered["Phase"].isin(secondary_phases)]

# Flag no data
filtered["_no_data"] = (filtered["Apps Received 2025"] == 0) & (filtered["PAN"] == 0)

# Sort
if postcode_query and home_lat and "Distance (km)" in filtered.columns:
    filtered = filtered.sort_values("Distance (km)")
else:
    filtered = filtered[~filtered["_no_data"]].sort_values("Oversub Ratio")

# ========================================
# PERSONAL ADVICE
# ========================================
if sibling:
    st.success("Siblings nearly always get in — **extremely strong position!**")
elif baptised and church_attendance:
    st.success("Practising Catholic family — **excellent chances**")
elif baptised:
    st.info("Baptism helps, but many schools require proof of practice")
else:
    st.warning("Non-Catholic places are very limited")

# ========================================
# SUMMARY & TOP 10
# ========================================
col_a, col_b = st.columns(2)
col_a.metric("Schools found", len(filtered))
data_schools = filtered[~filtered["_no_data"]]
avg_ratio = (data_schools["Apps Received 2025"] / data_schools["PAN"]).mean()
col_b.metric("Avg apps per place", f"{avg_ratio:.1f}:1" if not pd.isna(avg_ratio) else "—")

with st.expander("🏆 Top 10 Most Oversubscribed", expanded=True):
    top10 = data_schools.nlargest(10, "Oversub Ratio")
    st.dataframe(top10[["School Name", "Oversub Ratio", "Apps Received 2025", "PAN"]])

# ========================================
# CARDS (your original layout restored)
# ========================================
for _, school in filtered.iterrows():
    with st.container():
        col1, col2 = st.columns([3, 1])
        with col1:
            website = school.get("School Website")
            name_str = f"[{school['School Name']}]({website})" if website else f"**{school['School Name']}**"
            st.markdown(f"{name_str} • {school['Phase']}")
            dist_str = f" • {school['Distance (km)']} km" if "Distance (km)" in school else ""
            st.caption(f"{school['Postcode']} • {school['Local Authority']}{dist_str}")
            if school["_no_data"]:
                st.caption("⚠️ No 2025 admissions data")
            else:
                st.caption(f"**{int(school['Apps Received 2025'])}:{int(school['PAN'])}** apps:places")
            badges = []
            if school.get("Snobe Overall Grade"):
                badges.append(f"Snobe {school['Snobe Overall Grade']}")
            if school.get("Ofsted Badge") != "Awaiting":
                badges.append(f"Ofsted {school['Ofsted Badge']}")
            if badges:
                st.caption(" • ".join(badges))

        with col2:
            oversub = int(school["Oversub Ratio"])
            if school["_no_data"]:
                st.markdown('<div style="background:#9E9E9E;color:white;padding:10px;border-radius:10px;text-align:center">No data</div>', unsafe_allow_html=True)
            else:
                if oversub >= 300:
                    color, label = "#B71C1C", "Very high demand"
                elif oversub >= 200:
                    color, label = "#E65100", "High demand"
                elif oversub >= 130:
                    color, label = "#F9A825", "Moderate demand"
                else:
                    color, label = "#1565C0", "Low demand"
                st.markdown(f'<div style="background:{color};color:white;padding:10px;border-radius:10px;text-align:center">{label}</div>', unsafe_allow_html=True)
                st.caption(f"{oversub}% oversubscribed")

        with st.expander("About these figures"):
            st.caption(f"{int(school['Apps Received 2025'])} apps for {int(school['PAN'])} places in 2025.")

# ========================================
# DOWNLOAD
# ========================================
if len(filtered) > 0:
    csv = filtered.to_csv(index=False).encode()
    st.download_button("⬇️ Download CSV", csv, "london-catholic-schools-2025.csv", "text/csv")

st.divider()
st.caption("Built with love by a London parent • 2025 data")
