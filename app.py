import streamlit as st
import pandas as pd
import os
import numpy as np
import math
import urllib.parse

st.set_page_config(page_title="London Catholic Schools 2025", page_icon="✝️", layout="centered")
st.markdown('<a name="top"></a>', unsafe_allow_html=True)

# ========================================
#  DATA LOADING
# ========================================
FULL_PATH = "catholic_schools_with_pan_coords.csv"
FULL_GITHUB = "https://raw.githubusercontent.com/Thierry0303/london-catholic-admissions-calculator/main/catholic_schools_with_pan_coords.csv"

CATHOLIC_PATTERNS = ["catholic", "roman catholic", "rc", "r.c.", "cath"]
RELIGION_COLS = [
    "ReligiousCharacter_DfE",
    "ReligiousCharacter",
    "ReligiousCharacter (name)"
]

def is_catholic(row):
    # Religious character columns
    for col in RELIGION_COLS:
        if col in row and isinstance(row[col], str):
            val = row[col].lower()
            if any(p in val for p in CATHOLIC_PATTERNS):
                return True
    # School name
    if isinstance(row.get("School Name"), str):
        name = row["School Name"].lower()
        if any(p in name for p in CATHOLIC_PATTERNS):
            return True
    return False

@st.cache_data
def load_data():
    df = pd.read_csv(FULL_PATH) if os.path.exists(FULL_PATH) else pd.read_csv(FULL_GITHUB)

    # Ensure URN numeric
    df["URN"] = pd.to_numeric(df.get("URN"), errors="coerce").astype("Int64")

    # --- GLOBAL DEDUPE ---
    df = df.drop_duplicates(subset=["URN"], keep="first")

    # Catholic-only filter
    df = df[df.apply(is_catholic, axis=1)]

    # Clean numerics
    df["PAN 2025"] = pd.to_numeric(df.get("PAN 2025"), errors="coerce").fillna(0).astype(int)
    df["1st Pref Apps 2025"] = pd.to_numeric(df.get("1st Pref Apps 2025"), errors="coerce").fillna(0).astype(int)

    df["PAN 2025"] = df["PAN 2025"].replace(0, 1)
    df["Oversub Ratio"] = (df["1st Pref Apps 2025"] / df["PAN 2025"]) * 100
    df["Oversub Ratio"] = df["Oversub Ratio"].round(0).astype(int)

    # Ensure optional columns exist
    for col in ["Phone", "School Website", "Ofsted Rating", "Last Inspection", "Snobe Overall Grade", "Phase", "Postcode"]:
        if col not in df.columns:
            df[col] = ""

    # Clean website URLs
    df["School Website"] = df["School Website"].astype(str).str.strip().replace({"": np.nan, "nan": np.nan})
    df["School Website"] = df["School Website"].apply(
        lambda x: f"http://{x}" if pd.notnull(x) and not str(x).startswith(("http://", "https://")) else x
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

    return df


# ========================================
#  POSTCODE → LAT/LNG
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
#  LOAD DATA
# ========================================
merged = load_data()

# ========================================
#  QUERY PARAMS
# ========================================
params = st.query_params
_qp_postcode  = params.get("postcode", "")
_qp_borough   = params.get("borough", "")
_qp_stage     = params.get("stage", "Both")
_qp_baptised  = params.get("baptised", "1") == "1"
_qp_attend    = params.get("attend", "1") == "1"
_qp_sibling   = params.get("sibling", "0") == "1"

# ========================================
#  HEADER
# ========================================
st.markdown("""
<h1 style="text-align:center; color:#0055a5; font-size:2.5rem;">✝️ London Catholic Schools 2025</h1>
<p style="text-align:center; font-size:1.2rem; color:#444;">Real chances • Website • Ofsted • Snobe grade • For parents</p>
""", unsafe_allow_html=True)

# ========================================
#  SIDEBAR
# ========================================
with st.sidebar:
    st.header("🔍 Search")

    postcode_query = st.text_input("Your postcode (e.g. SW6 1AA)", value=_qp_postcode)
    max_distance_km = st.slider("Max distance (km)", 1, 20, 5, disabled=(not postcode_query))

    st.divider()
    st.subheader("Or filter by borough")
    boroughs = ["All boroughs"] + sorted([b for b in merged["Local Authority"].dropna().unique()])
    selected_borough = st.selectbox("Borough", boroughs)

    child_stage = st.radio("My child needs", ["Primary", "Secondary", "Both"], index=["Primary","Secondary","Both"].index(_qp_stage))
    primary_phases   = ["Primary", "Middle deemed primary", "All-through"]
    secondary_phases = ["Secondary", "Middle deemed secondary", "All-through", "Not applicable"]
    selected_phase = primary_phases if child_stage=="Primary" else secondary_phases if child_stage=="Secondary" else list(merged["Phase"].dropna().unique())

    st.divider()
    st.subheader("Your situation")
    baptised = st.checkbox("Baptised Catholic", _qp_baptised)
    church_attendance = st.checkbox("Regular church attendance", _qp_attend)
    sibling = st.checkbox("Sibling at school", _qp_sibling)

# ========================================
#  APPLY FILTERS
# ========================================
filtered = merged.copy()

# --- UI-level dedupe ---
filtered = filtered.drop_duplicates(subset=["URN"], keep="first")

# --- Postcode filter ---
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

# --- Borough filter ---
if not postcode_query and selected_borough != "All boroughs":
    filtered = filtered[filtered["Local Authority"] == selected_borough]

# --- Phase filter ---
filtered = filtered[filtered["Phase"].isin(selected_phase)]

# --- Admissions data flag ---
filtered["_no_data"] = (filtered["1st Pref Apps 2025"] == 0)

# --- Sort ---
if postcode_query and home_lat and "Distance (km)" in filtered.columns:
    filtered = filtered.sort_values("Distance (km)")
else:
    filtered = filtered.sort_values("Oversub Ratio")

# ========================================
#  SUMMARY BAR + TOP 10
# ========================================
if len(filtered) > 0:
    data_schools = filtered[~filtered["_no_data"]].drop_duplicates(subset=["URN"])

    col_a, col_b = st.columns(2)
    col_a.metric("Schools found", len(filtered))

    avg_apps = data_schools["1st Pref Apps 2025"].mean() if len(data_schools) else 0
    avg_pan  = data_schools["PAN 2025"].mean() if len(data_schools) else 1
    col_b.metric("Avg applications per place", f"{avg_apps/avg_pan:.1f}:1")

    # --- TOP 10 ---
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
            apps  = int(row["1st Pref Apps 2025"])
            pan   = int(row["PAN 2025"])
            ratio_str = f"{apps}:{pan}"

            if ratio >= 300:
                bar_color = "#B71C1C"
            elif ratio >= 200:
                bar_color = "#E65100"
            elif ratio >= 130:
                bar_color = "#F9A825"
            else:
                bar_color = "#2E7D32"

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
#  MAP
# ========================================
if len(filtered) > 0 and {"Latitude","Longitude"}.issubset(filtered.columns):
    show_map = st.toggle("🗺️ Show map", value=False)
    if show_map:
        import folium
        from streamlit_folium import st_folium

        map_data = filtered.dropna(subset=["Latitude","Longitude"]).drop_duplicates(subset=["URN"])

        if home_lat and home_lon:
            centre_lat, centre_lon = home_lat, home_lon
        else:
            centre_lat = map_data["Latitude"].mean()
            centre_lon = map_data["Longitude"].mean()

        m = folium.Map(location=[centre_lat, centre_lon], zoom_start=12, tiles="CartoDB positron")

        for _, row in map_data.iterrows():
            colour = (
                "gray" if row["_no_data"]
                else "blue" if row["Oversub Ratio"] < 100
                else "green" if row["Oversub Ratio"] < 130
                else "orange" if row["Oversub Ratio"] < 200
                else "red"
            )
            folium.CircleMarker(
                location=[row["Latitude"], row["Longitude"]],
                radius=8,
                color=colour,
                fill=True,
                fill_opacity=0.8,
                tooltip=row["School Name"],
            ).add_to(m)

        st_folium(m, width="100%", height=450)
        st.caption("🟢 Lower demand  🟠 Moderate  🔴 Very high demand  🔵 Places available  ⚫ No data")

# ========================================
#  RESULTS LIST
# ========================================
if len(filtered)==0:
    st.markdown("### 🔍 No schools found")
else:
    st.markdown(f"### {len(filtered)} schools found")

    for _, school in filtered.iterrows():
        st.markdown(f"## {school['School Name']} — {school['Local Authority']}")
        st.caption(f"{school['1st Pref Apps 2025']} first preferences for {school['PAN 2025']} places")

        oversub = school["Oversub Ratio"]
        if oversub < 100:
            st.success("Low demand")
        elif oversub < 130:
            st.info("Moderate demand")
        elif oversub < 200:
            st.warning("High demand")
        else:
            st.error("Very high demand")

        st.caption(f"Ofsted: {school['Ofsted Badge']}")
        st.caption(f"Snobe: {school['Snobe Overall Grade']}")

        if pd.notna(school["School Website"]):
            st.markdown(f"[School website]({school['School Website']})")

        st.markdown("---")
