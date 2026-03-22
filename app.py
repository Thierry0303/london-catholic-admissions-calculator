import os
import numpy as np
import math
import requests
import json
import urllib.request
import folium
from streamlit_folium import st_folium
import urllib.parse

st.set_page_config(page_title="London Catholic Schools 2025", page_icon="✝️", layout="centered")
st.markdown('<a name="top"></a>', unsafe_allow_html=True)

# ========================================
# DATA LOADING + OVERRIDES
#  DATA LOADING
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
    
    # MANUAL OVERRIDES (fixes data quality)
    overrides = {
        148438: {"Ofsted Rating": "Outstanding", "Ofsted Badge": "Outstanding"},   # St Joseph's Kensington
        100491: {"1st Pref Apps 2025": 169, "Oversub Ratio": 563}                 # The Oratory
    }
    for urn, updates in overrides.items():
        mask = df["URN"] == urn
        if mask.any():
            for col, value in updates.items():
                df.loc[mask, col] = value
    
    for col in ["Phone", "School Website", "Ofsted Rating", "Last Inspection", "Snobe Overall Grade", "Phase"]:
    if os.path.exists(FULL_PATH):
        df = pd.read_csv(FULL_PATH)
    else:
        df = pd.read_csv(FULL_GITHUB)

    df["PAN"] = pd.to_numeric(df.get("PAN"), errors="coerce").fillna(0).astype(int)
    df["Apps Received 2025"] = pd.to_numeric(df.get("Apps Received 2025"), errors="coerce").fillna(0).astype(int)
    df["Oversub Ratio"] = (df["Apps Received 2025"] / df["PAN"].replace(0, 1)) * 100
    df["Oversub Ratio"] = df["Oversub Ratio"].round(0).astype(int)

    for col in ["Phone", "School Website", "Ofsted Rating", "Last Inspection", "Snobe Overall Grade"]:
        if col not in df.columns:
            df[col] = ""
    

    df["School Website"] = df["School Website"].astype(str).str.strip().replace({"": np.nan, "nan": np.nan})
    df["School Website"] = df["School Website"].apply(
        lambda x: f"http://{x}" if pd.notnull(x) and not str(x).startswith(("http://", "https://")) else x
    )
    

    def ofsted_badge(r):
        r = str(r)
        if "Outstanding" in r: return "Outstanding"
@@ -81,63 +43,19 @@ def ofsted_badge(r):
        if "Inadequate" in r: return "Inadequate"
        return "Awaiting"
    df["Ofsted Badge"] = df["Ofsted Rating"].apply(ofsted_badge)
    

    if "Local Authority" in df.columns:
        df["Local Authority"] = df["Local Authority"].astype(str).str.strip().str.title()

    return df


# ========================================
# HELPERS
#  POSTCODE → LAT/LNG  (free, no API key)
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
    """Calls postcodes.io — free, no key needed."""
    import urllib.request, json
    clean = postcode.strip().upper().replace(" ", "")
    try:
@@ -147,249 +65,627 @@ def postcode_to_latlon(postcode: str):
        if data.get("status") == 200:
            r = data["result"]
            return r["latitude"], r["longitude"]
    except:
    except Exception:
        pass
    return None, None


def haversine_km(lat1, lon1, lat2, lon2):
    if any(pd.isna(x) or x is None for x in [lat1, lon1, lat2, lon2]):
        return None
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ========================================
#  CRIME DATA  (data.police.uk — no key)
# ========================================
CRIME_CATEGORY_LABELS = {
    "anti-social-behaviour":   "Antisocial behaviour",
    "bicycle-theft":           "Bicycle theft",
    "burglary":                "Burglary",
    "criminal-damage-arson":   "Criminal damage & arson",
    "drugs":                   "Drugs",
    "other-theft":             "Other theft",
    "possession-of-weapons":   "Weapons possession",
    "public-order":            "Public order",
    "robbery":                 "Robbery",
    "shoplifting":             "Shoplifting",
    "theft-from-the-person":   "Theft from person",
    "vehicle-crime":           "Vehicle crime",
    "violent-crime":           "Violence & sexual offences",
    "other-crime":             "Other crime",
}

@st.cache_data(show_spinner=False, ttl=86400)
def get_latest_crime_month() -> str:
    """Asks the police API what the latest available month is."""
    import urllib.request, json
    try:
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
        R = 6371
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    except:
        req = urllib.request.Request(
            "https://data.police.uk/api/crimes-street-dates",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            dates = json.loads(r.read())
        if dates and isinstance(dates, list):
            return dates[0]["date"]
    except Exception:
        pass
    return "2025-10"  # safe fallback


def _make_polygon(lat: float, lon: float, radius_km: float = 0.5, points: int = 6) -> str:
    """
    Generates a lat:lng polygon string around a centre point.
    Used by the police API to search a proper area instead of snapping to
    the nearest road (which often returns 0 results).
    """
    R = 6371.0
    coords = []
    for i in range(points):
        angle = math.radians(360 / points * i)
        dlat = (radius_km / R) * math.cos(angle) * (180 / math.pi)
        dlon = (radius_km / R) * math.sin(angle) * (180 / math.pi) / math.cos(math.radians(lat))
        coords.append(f"{lat + dlat:.6f},{lon + dlon:.6f}")
    return ":".join(coords)


@st.cache_data(show_spinner=False, ttl=86400)
def fetch_crime(lat: float, lon: float):
    """
    Fetches street-level crimes in a 500m polygon from data.police.uk.
    Returns (dict {label: count, 'total': n}, month_str) or (None, error_str).
    """
    import urllib.request, json
    month = get_latest_crime_month()
    poly = _make_polygon(lat, lon, radius_km=0.5)
    url = f"https://data.police.uk/api/crimes-street/all-crime?poly={poly}&date={month}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            crimes = json.loads(resp.read())
        if not isinstance(crimes, list):
            return None, "bad response"
        counts = {}
        for c in crimes:
            cat = c.get("category", "other-crime")
            label = CRIME_CATEGORY_LABELS.get(cat, cat.replace("-", " ").title())
            counts[label] = counts.get(label, 0) + 1
        counts["total"] = sum(counts.values())
        return counts, month
    except Exception as e:
        return None, str(e)


# ========================================
#  IMD DATA — static CSV committed to repo
# ========================================
@st.cache_data(show_spinner=False)
def load_imd_lookup():
    for path in [
        "imd_lookup.csv",
        "https://raw.githubusercontent.com/Thierry0303/london-catholic-admissions-calculator/main/imd_lookup.csv",
    ]:
        try:
            df = pd.read_csv(path)
            df["postcode"] = df["postcode"].astype(str).str.strip().str.upper().str.replace(" ", "", regex=False)
            return df.set_index("postcode")
        except Exception:
            continue
    return None


def fetch_imd(postcode: str):
    clean = postcode.strip().upper().replace(" ", "")
    lookup = load_imd_lookup()
    if lookup is None or clean not in lookup.index:
        return None
    row = lookup.loc[clean]
    decile = row["imd_decile"]
    if pd.isna(decile):
        return None
    return {"decile": max(1, int(float(decile)))}


def imd_label(decile: int):
    """Returns (text description, colour hex) for an IMD decile."""
    if decile <= 2:   return "Most deprived area (decile {})".format(decile), "#B71C1C"
    if decile <= 4:   return "Below average (decile {})".format(decile),      "#E65100"
    if decile <= 6:   return "Average area (decile {})".format(decile),        "#F9A825"
    if decile <= 8:   return "Above average (decile {})".format(decile),       "#558B2F"
    return             "Least deprived area (decile {})".format(decile),        "#1B5E20"


# ========================================
# LOAD DATA + WARNING BANNER
#  LIKELIHOOD CALCULATOR
# ========================================
def calculate_likelihood(row, baptised, church_attendance, sibling):
    priority_score = 0
    if sibling: priority_score += 40
    if baptised and church_attendance: priority_score += 35
    elif baptised: priority_score += 18
    else: priority_score += 5

    oversub = row["Oversub Ratio"]
    if priority_score >= 70:
        chance = max(15, 98 - (oversub - 100) * 0.25)
    elif priority_score >= 50:
        chance = max(8, 90 - (oversub - 100) * 0.6)
    elif priority_score >= 20:
        chance = max(3, 65 - oversub * 0.8)
    else:
        chance = max(1, 40 - oversub)
    return min(100, round(chance, 1))


def chance_explanation(row, baptised, church_attendance, sibling):
    parts = []
    if sibling:
        parts.append("sibling priority (+40 pts)")
    if baptised and church_attendance:
        parts.append("practising Catholic (+35 pts)")
    elif baptised:
        parts.append("baptised but attendance not confirmed (+18 pts)")
    else:
        parts.append("non-Catholic (+5 pts)")
    oversub = row["Oversub Ratio"]
    parts.append(f"school is {oversub}% subscribed ({oversub - 100:+d}% vs places available)" if oversub > 100 else f"school has spare capacity ({oversub}% subscribed)")
    return " • ".join(parts)


merged = load_data()
imd_df = load_imd_lookup()

# ========================================
# QUERY PARAMS + HEADER + SIDEBAR (your original)
#  QUERY PARAMS — shareable URLs
# ========================================
params = st.query_params
_qp_postcode = params.get("postcode", "")
_qp_borough = params.get("borough", "")
_qp_stage = params.get("stage", "Both")
_qp_baptised = params.get("baptised", "1") == "1"
_qp_attend = params.get("attend", "1") == "1"
_qp_sibling = params.get("sibling", "0") == "1"
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

    # --- Postcode first ---
    postcode_query = st.text_input("Your postcode (e.g. SW6 1AA)", placeholder="SW6 1AA", value=_qp_postcode)
    max_distance_km = st.slider("Max distance (km)", 1, 20, 5, disabled=(not postcode_query))

    st.divider()
    st.subheader("Or filter by borough")
    boroughs = ["All boroughs"] + sorted([b for b in merged["Local Authority"].dropna().unique()])
    selected_borough = st.selectbox("Borough", boroughs)
    child_stage = st.radio("My child needs", ["Primary", "Secondary", "Both"], index=["Primary","Secondary","Both"].index(_qp_stage))
    primary_phases = ["Primary", "Middle deemed primary", "All-through"]
    default_borough_idx = boroughs.index(_qp_borough) if _qp_borough in boroughs else 0
    selected_borough = st.selectbox("Borough", boroughs, index=default_borough_idx)

    _stage_idx = ["Primary", "Secondary", "Both"].index(_qp_stage) if _qp_stage in ["Primary", "Secondary", "Both"] else 2
    child_stage = st.radio("My child needs", ["Primary", "Secondary", "Both"], index=_stage_idx)
    primary_phases   = ["Primary", "Middle deemed primary", "All-through"]
    secondary_phases = ["Secondary", "Middle deemed secondary", "All-through", "Not applicable"]
    selected_phase = primary_phases if child_stage=="Primary" else secondary_phases if child_stage=="Secondary" else list(merged["Phase"].dropna().unique())
    if child_stage == "Primary":
        selected_phase = primary_phases
    elif child_stage == "Secondary":
        selected_phase = secondary_phases
    else:
        selected_phase = list(merged["Phase"].dropna().unique())

    st.divider()
    st.subheader("Your situation")
    baptised = st.checkbox("Baptised Catholic", _qp_baptised)
    church_attendance = st.checkbox("Regular church attendance", _qp_attend)
    sibling = st.checkbox("Sibling at school", _qp_sibling)
    with st.expander("Admission criteria", expanded=True):
        baptised = st.checkbox("Baptised Catholic", _qp_baptised)
        church_attendance = st.checkbox("Regular church attendance", _qp_attend)
        sibling = st.checkbox("Sibling at school", _qp_sibling)

# ========================================
# FILTERS + CRASH-PROOF DISTANCE
#  APPLY FILTERS
# ========================================
filtered = merged.copy()
filtered = filtered.drop_duplicates(subset=["URN"], keep="first")

# Postcode-based distance filter
home_lat, home_lon = None, None
distance_warning = None
if postcode_query:
    home_lat, home_lon = postcode_to_latlon(postcode_query)
    if home_lat is not None:
        # Fill missing coordinates
        def fill_missing_coords(row):
            if pd.isna(row.get("Latitude")) or pd.isna(row.get("Longitude")):
                lat, lon = postcode_to_latlon(row.get("postcode", ""))
                if lat is not None:
                    return pd.Series([lat, lon])
            return pd.Series([row.get("Latitude"), row.get("Longitude")])
        
        filtered[["Latitude", "Longitude"]] = filtered.apply(fill_missing_coords, axis=1)
        filtered["Latitude"] = pd.to_numeric(filtered["Latitude"], errors="coerce")
        filtered["Longitude"] = pd.to_numeric(filtered["Longitude"], errors="coerce")
        filtered = filtered.dropna(subset=["Latitude", "Longitude"])
        
        # CRASH-PROOF distance
        def safe_distance(row):
            d = haversine_km(home_lat, home_lon, row["Latitude"], row["Longitude"])
            return round(d, 1) if d is not None else None
        
        filtered["Distance (km)"] = filtered.apply(safe_distance, axis=1)
        filtered = filtered.dropna(subset=["Distance (km)"])
        filtered = filtered[filtered["Distance (km)"] <= max_distance_km]
# ---------------------------------------------------------
# BEST MATCH WEIGHTED SCORING SYSTEM
# ---------------------------------------------------------

st.subheader("Best Match Weighting")

# User-adjustable weights
W_IMD = st.slider("Weight: IMD (lower deprivation is better)", 0.0, 1.0, 0.25)
W_CRIME = st.slider("Weight: Crime (lower crime is better)", 0.0, 1.0, 0.25)
W_ACADEMIC = st.slider("Weight: Academic strength (oversubscription)", 0.0, 1.0, 0.25)
W_DISTANCE = st.slider("Weight: Distance (closer is better)", 0.0, 1.0, 0.25)

# Normalisation helper
def normalise(series):
    if series.max() == series.min():
        return series * 0
    return (series - series.min()) / (series.max() - series.min())

# Normalise metrics
filtered["norm_imd"] = normalise(filtered["IMD_rank"])
filtered["norm_crime"] = normalise(filtered["Crime_index"])
filtered["norm_oversub"] = normalise(filtered["Oversub Ratio"])

# Distance only if available
if "Distance (km)" in filtered.columns:
    filtered["norm_distance"] = normalise(filtered["Distance (km)"])
    filtered["norm_distance"] = 1 - filtered["norm_distance"]
else:
    filtered["norm_distance"] = 0  # neutral value


# Invert metrics where lower = better
filtered["norm_imd"] = 1 - filtered["norm_imd"]
filtered["norm_crime"] = 1 - filtered["norm_crime"]
filtered["norm_distance"] = 1 - filtered["norm_distance"]

filtered["Best Match Score"] = (
    W_IMD * filtered["norm_imd"] +
    W_CRIME * filtered["norm_crime"] +
    W_ACADEMIC * filtered["norm_oversub"] +
    W_DISTANCE * filtered["norm_distance"]
)

# Sort by best match
filtered = filtered.sort_values("Best Match Score", ascending=False)

# Display best match
top_school = filtered.iloc[0]
st.success(
    f"🏆 Best overall match: **{top_school['School Name']}** "
    f"(Score: {top_school['Best Match Score']:.2f})"
)


    if home_lat is None:
        distance_warning = f"⚠️ Couldn't find postcode **{postcode_query}** — check spelling and try again."
    else:
        if {"Latitude", "Longitude"}.issubset(filtered.columns):
            filtered = filtered.dropna(subset=["Latitude", "Longitude"])
            filtered["Distance (km)"] = filtered.apply(
                lambda r: round(haversine_km(home_lat, home_lon, r["Latitude"], r["Longitude"]), 1), axis=1
            )
            filtered = filtered[filtered["Distance (km)"] <= max_distance_km]
        else:
            distance_warning = "⚠️ Distance filtering unavailable — coordinate data missing."

# Borough filter (skip if postcode active)
if not postcode_query and selected_borough != "All boroughs":
    filtered = filtered[filtered["Local Authority"] == selected_borough]

# Phase filter
filtered = filtered[filtered["Phase"].isin(selected_phase)]
filtered["_no_data"] = (filtered["1st Pref Apps 2025"] == 0)

# Fix 2: Flag schools with no admissions data
filtered = filtered.copy()
filtered["_no_data"] = (filtered["Apps Received 2025"] == 0) & (filtered["PAN"] == 0)

# Default sort: by distance if postcode active, otherwise by oversubscription
if postcode_query and home_lat and "Distance (km)" in filtered.columns:
    filtered = filtered.sort_values("Distance (km)")
    filtered = filtered.sort_values("Distance (km)", ascending=True)
else:
    filtered = filtered.sort_values("Oversub Ratio")
    filtered = filtered[~filtered["_no_data"]].sort_values("Oversub Ratio", ascending=True)

# Update URL query params for shareability
st.query_params.update({
    "postcode":  postcode_query or "",
    "borough":   selected_borough if selected_borough != "All boroughs" else "",
    "stage":     child_stage,
    "baptised":  "1" if baptised else "0",
    "attend":    "1" if church_attendance else "0",
    "sibling":   "1" if sibling else "0",
})

# ========================================
# SUMMARY + TOP 10 + MAP + RESULTS (your original code)
#  PERSONAL ADVICE BANNER
# ========================================
if sibling:
    st.success("Siblings nearly always get in — **extremely strong position!**")
elif baptised and church_attendance:
    st.success("Practising Catholic family — **excellent chances**")
elif baptised:
    st.info("Baptism helps, but many schools require proof of practice")
else:
    st.warning("Non-Catholic places are very limited")

# Distance warning
if distance_warning:
    st.warning(distance_warning)

# ========================================
#  SUMMARY STATS BAR
# ========================================
if len(filtered) > 0:
    data_schools = filtered[~filtered["_no_data"]].drop_duplicates(subset=["URN"])
    data_schools = filtered[~filtered["_no_data"]]
    avg_oversub = int(data_schools["Oversub Ratio"].mean()) if len(data_schools) else 0
    best_chance = 0  # unused, kept for compatibility
    n = len(filtered)
    location_label = f"within {max_distance_km}km of {postcode_query.upper()}" if postcode_query and home_lat else selected_borough

    col_a, col_b = st.columns(2)
    col_a.metric("Schools found", len(filtered))
    avg_apps = data_schools["1st Pref Apps 2025"].mean() if len(data_schools) else 0
    avg_pan = data_schools["PAN 2025"].mean() if len(data_schools) else 1
    col_b.metric("Avg applications per place", f"{avg_apps/avg_pan:.1f}:1")
    
    with st.expander("🏆 Most competitive schools (Top 10)"):
        # (your original top 10 table code - unchanged)
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

# MAP
if len(filtered) > 0 and {"Latitude","Longitude"}.issubset(filtered.columns):
    col_a.metric("Schools found", n)
    avg_apps = data_schools["Apps Received 2025"].mean() if len(data_schools) else 0
    avg_pan  = data_schools["PAN"].replace(0,1).mean() if len(data_schools) else 1
    avg_ratio_str = f"{avg_apps/avg_pan:.1f}:1" if avg_pan else "—"
    col_b.metric("Avg applications per place", avg_ratio_str)
    st.caption(f"Results for: **{location_label}**  •  Last updated: March 2025")

    # Top 10 most competitive
    if len(data_schools) >= 3:
        with st.expander("🏆 Most competitive schools (by oversubscription)"):
            top10 = (
                data_schools[data_schools["Oversub Ratio"] > 100]
                .sort_values("Oversub Ratio", ascending=False)
                .head(10)
                .reset_index(drop=True)
            )
            top10.index += 1
            if len(top10):
                rows_html = ""
                for rank, row in top10.iterrows():
                    ratio = int(row["Oversub Ratio"])
                    apps  = int(row["Apps Received 2025"])
                    pan   = int(row["PAN"]) if row["PAN"] > 0 else 1
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
                    phase_icon = "🏫" if row["Phase"] == "Secondary" else "🎒"
                    dist_str = f" · {row['Distance (km)']:.1f} km" if "Distance (km)" in row and pd.notna(row.get("Distance (km)")) else ""
                    rows_html += f"""
                    <tr>
                      <td style='padding:6px 8px;font-weight:bold;color:#888;width:28px'>{rank}</td>
                      <td style='padding:6px 8px;'>
                        <span style='font-weight:600'>{phase_icon} {row['School Name']}</span>
                        <span style='color:#888;font-size:0.85rem'> · {row['Local Authority']}{dist_str}</span>
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
            else:
                st.caption("No oversubscribed schools in current filter.")

st.divider()

# ========================================
#  MAP TOGGLE
# ========================================
if {"Latitude", "Longitude"}.issubset(filtered.columns) and len(filtered) > 0:
    show_map = st.toggle("🗺️ Show map", value=False)
    if show_map:
        map_data = filtered.dropna(subset=["Latitude","Longitude"]).drop_duplicates(subset=["URN"])
        centre_lat = home_lat if home_lat else map_data["Latitude"].mean()
        centre_lon = home_lon if home_lon else map_data["Longitude"].mean()
        m = folium.Map(location=[centre_lat, centre_lon], zoom_start=12, tiles="CartoDB positron")
        import folium
        from streamlit_folium import st_folium
        map_data = filtered.dropna(subset=["Latitude", "Longitude"]).copy()
        if home_lat and home_lon:
            centre_lat, centre_lon = home_lat, home_lon
            zoom = 13 if max_distance_km <= 3 else 12 if max_distance_km <= 7 else 11
        else:
            centre_lat = map_data["Latitude"].mean()
            centre_lon = map_data["Longitude"].mean()
            zoom = 11
        m = folium.Map(location=[centre_lat, centre_lon], zoom_start=zoom, tiles="CartoDB positron")
        for _, row in map_data.iterrows():
            colour = "gray" if row["_no_data"] else "blue" if row["Oversub Ratio"] < 100 else "green" if row["Oversub Ratio"] < 130 else "orange" if row["Oversub Ratio"] < 200 else "red"
            folium.CircleMarker(location=[row["Latitude"], row["Longitude"]], radius=8, color=colour, fill=True, fill_opacity=0.8, tooltip=row["School Name"]).add_to(m)
        st_folium(m, width="100%", height=450)
        st.caption("🟢 Lower demand 🟠 Moderate 🔴 Very high demand 🔵 Places available ⚫ No data")
            if row["_no_data"]:
                colour = "gray"
            elif row["Oversub Ratio"] < 100:
                colour = "blue"
            elif row["Oversub Ratio"] >= 300:
                colour = "red"
            elif row["Oversub Ratio"] >= 200:
                colour = "orange"
            else:
                colour = "green"
            chance_str = "No data" if row["_no_data"] else (
                "Places available" if row["Oversub Ratio"] < 100 else f"{int(row['Apps Received 2025'])}:{int(row['PAN'])} apps:places"
            )
            folium.CircleMarker(
                location=[row["Latitude"], row["Longitude"]],
                radius=8,
                color=colour,
                fill=True,
                fill_color=colour,
                fill_opacity=0.8,
                popup=folium.Popup(f"<b>{row['School Name']}</b><br>{chance_str}", max_width=200),
                tooltip=row["School Name"],
            ).add_to(m)
        # key forces re-render when filters change
        map_key = f"map_{postcode_query}_{selected_borough}_{child_stage}_{len(map_data)}"
        st_folium(m, width="100%", height=450, returned_objects=[], key=map_key)
        st.caption("🟢 Lower demand  🟠 Moderate  🔴 Very high demand  🔵 Places available  ⚫ No data")
        st.divider()

# RESULTS LIST
if len(filtered)==0:
# ========================================
#  RESULTS CARDS
# ========================================
if len(filtered) == 0:
    st.markdown("### 🔍 No schools found")
    if postcode_query and home_lat:
        st.info(f"No Catholic schools within **{max_distance_km} km** of **{postcode_query.upper()}**. Try increasing the distance slider.")
    elif postcode_query and home_lat is None:
        st.info("Check your postcode and try again.")
    else:
        st.info("No schools match your current filters. Try selecting a different borough or phase.")
else:
    st.markdown(f"### {len(filtered)} schools found")
    # ── Sort control — left: count, right: sort dropdown ──
    count_col, sort_col = st.columns([3, 2])
    with sort_col:
        sort_options = ["Oversubscription (lowest first)", "Snobe grade", "Ofsted rating", "Alphabetical"]
        if postcode_query and home_lat and "Distance (km)" in filtered.columns:
            sort_options = ["Distance (nearest first)"] + sort_options
        sort_by = st.selectbox("↕️ Sort by", sort_options, label_visibility="visible")

    # Apply sort
    OFSTED_ORDER = {"Outstanding": 0, "Good": 1, "Requires Improvement": 2, "Inadequate": 3, "Awaiting": 4}
    SNOBE_ORDER  = {"A+": 0, "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "": 99}

    if sort_by == "Distance (nearest first)" and "Distance (km)" in filtered.columns:
        filtered = filtered.sort_values("Distance (km)", ascending=True)
    elif sort_by == "Oversubscription (lowest first)":
        filtered = filtered[~filtered["_no_data"]].sort_values("Oversub Ratio", ascending=True)
    elif sort_by == "Ofsted rating":
        filtered = filtered.copy()
        filtered["_ofsted_order"] = filtered["Ofsted Badge"].map(OFSTED_ORDER).fillna(4)
        filtered = filtered.sort_values("_ofsted_order")
    elif sort_by == "Snobe grade":
        filtered = filtered.copy()
        filtered["_snobe_order"] = filtered["Snobe Overall Grade"].astype(str).str.strip().map(SNOBE_ORDER).fillna(99)
        filtered = filtered.sort_values("_snobe_order")
    elif sort_by == "Alphabetical":
        filtered = filtered.sort_values("School Name")

    with count_col:
        st.subheader(f"{len(filtered)} school{'s' if len(filtered) != 1 else ''}")

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
            if score is not None:
                st.caption(f"IMD score: {score}")
            lat = school.get("Latitude", None)
            lon = school.get("Longitude", None)
            if pd.notna(lat) and pd.notna(lon):
                crime_count = fetch_crime_count(lat, lon)
                st.write(f"**Crime:** {crime_label(crime_count)}")
                if crime_count is not None:
                    st.caption(f"Approx. monthly crimes within area: {crime_count}")
            else:
                st.write("No location data available for crime statistics.")
        if pd.notna(school["School Website"]):
            st.markdown(f"[School website]({school['School Website']})")
        st.markdown("---")
        with st.container():
            col1, col2 = st.columns([3, 1])
            with col1:
                website = school.get("School Website")
                has_website = pd.notna(website) and str(website).strip() not in ("", "nan")
                name_str = f"[{school['School Name']}]({website})" if has_website else f"**{school['School Name']}**"
                st.markdown(f"{name_str} • {school['Phase']}")
                dist_str = f" • 📍 {school['Distance (km)']} km away" if "Distance (km)" in school and pd.notna(school.get("Distance (km)")) else ""
                st.caption(f"{school['Postcode']} • {school['Local Authority']}{dist_str}")
                if school.get("_no_data"):
                    st.caption("⚠️ No 2025 admissions data available for this school")
                else:
                    st.caption(f"Applications vs places: **{int(school['Apps Received 2025'])}:{int(school['PAN'])}** ({school['Apps Received 2025']} apps for {school['PAN']} places)")

                badges = []
                if school.get("Phase") == "Not applicable":
                    badges.append("🏫 Independent (fee-paying)")
                if school.get("Snobe Overall Grade") and str(school["Snobe Overall Grade"]).strip():
                    badges.append(f"Snobe {school['Snobe Overall Grade']} ℹ️")
                if school.get("Ofsted Badge") and school["Ofsted Badge"] != "Awaiting":
                    badges.append(f"Ofsted: {school['Ofsted Badge']}")
                if badges:
                    st.caption(" • ".join(badges))

            with col2:
                if school.get("_no_data"):
                    st.markdown(
                        "<div style='background:#9E9E9E;color:white;padding:10px;border-radius:10px;text-align:center;font-weight:bold;font-size:0.9rem'>No data</div>",
                        unsafe_allow_html=True
                    )
                    st.caption("no admissions data")
                else:
                    if school['Oversub Ratio'] < 100:
                        st.markdown(
                            "<div style='background:#1565C0;color:white;padding:10px;border-radius:10px;"
                            "text-align:center;font-weight:bold;font-size:0.95rem'>Low<br>demand</div>",
                            unsafe_allow_html=True
                        )
                        st.caption(f"{int(school['Apps Received 2025'])}:{int(school['PAN'])} apps:places")
                    else:
                        oversub = school['Oversub Ratio']
                        apps = int(school['Apps Received 2025'])
                        pan  = int(school['PAN'])
                        ratio_str = f"{apps}:{pan}"
                        if oversub >= 300:
                            badge_color, badge_label = "#B71C1C", "Very high<br>demand"
                        elif oversub >= 200:
                            badge_color, badge_label = "#E65100", "High<br>demand"
                        elif oversub >= 130:
                            badge_color, badge_label = "#F9A825", "Moderate<br>demand"
                        else:
                            badge_color, badge_label = "#2E7D32", "Lower<br>demand"
                        st.markdown(
                            f"<div style='background:{badge_color};color:white;padding:10px;border-radius:10px;text-align:center;font-weight:bold;font-size:0.95rem'>{badge_label}</div>",
                            unsafe_allow_html=True
                        )
                        st.caption(f"{ratio_str} apps:places · Catholics prioritised")

            # How calculated
            with st.expander("ℹ️ About these figures"):
                st.caption(
                    f"**{school['Apps Received 2025']:.0f} applications** were made for **{school['PAN']} places** in 2025. "
                    f"As a Catholic school, places are prioritised for baptised Catholics. "
                    f"Non-Catholics rarely receive an offer at oversubscribed Catholic schools. "
                    f"The oversubscription ratio reflects all applicants, not just Catholics."
                )

            # Neighbourhood context (crime + IMD)
            has_coords = pd.notna(school.get("Latitude")) and pd.notna(school.get("Longitude"))
            has_postcode = pd.notna(school.get("Postcode")) and str(school.get("Postcode", "")).strip()
            if has_coords or has_postcode:
                with st.expander("🏘️ Neighbourhood context"):
                    st.caption(
                        "ℹ️ These figures reflect the **surrounding area**, not the school itself. "
                        "Crime stats cover a ~500 m radius from the school (latest available month)."
                    )
                    c_left, c_right = st.columns(2)

                    # --- IMD ---
                    with c_left:
                        st.markdown("**Deprivation (IMD)**")
                        if has_postcode:
                            imd_data = fetch_imd(str(school["Postcode"]))
                            if imd_data and imd_data.get("decile") is not None:
                                desc, colour = imd_label(imd_data["decile"])
                                st.markdown(
                                    f"<span style='background:{colour};color:white;padding:3px 8px;"
                                    f"border-radius:6px;font-size:0.85rem'>{desc}</span>",
                                    unsafe_allow_html=True
                                )
                                st.caption("1 = most deprived · 10 = least deprived in England")
                                if imd_data.get("score"):
                                    st.caption(f"IMD score: {imd_data['score']}")
                            else:
                                st.caption("IMD data loading…")
                        else:
                            st.caption("No postcode available.")

                    # --- Crime ---
                    with c_right:
                        st.markdown("**Crime (500 m radius)**")
                        if has_coords:
                            crime_data, crime_month = fetch_crime(float(school["Latitude"]), float(school["Longitude"]))
                            if crime_data:
                                total = crime_data.pop("total", 0)
                                c_colour = "#1B5E20" if total < 20 else "#E65100" if total < 60 else "#B71C1C"
                                st.markdown(
                                    f"<span style='background:{c_colour};color:white;padding:3px 8px;"
                                    f"border-radius:6px;font-size:0.85rem'>{total} incidents</span>",
                                    unsafe_allow_html=True
                                )
                                london_context = "low" if total < 20 else "typical for inner London" if total < 60 else "high"
                                st.caption(f"Month: {crime_month}  •  Context: {london_context}")
                                top_cats = sorted(crime_data.items(), key=lambda x: x[1], reverse=True)[:3]
                                for cat, n in top_cats:
                                    st.caption(f"• {cat}: {n}")
                            else:
                                st.caption("Crime data unavailable — the police API may be slow or this area isn't covered.")
                        else:
                            st.caption("No coordinates available.")

            if pd.notna(school.get("Phone")) and school["Phone"]:
                st.caption(f"📞 {school['Phone']}")

            st.markdown("---")

# ========================================
#  DOWNLOAD
# ========================================
if len(filtered) > 0:
    csv = filtered.to_csv(index=False).encode()
    label = postcode_query.upper() if postcode_query else selected_borough.replace(" ", "_")
    st.download_button(
        "⬇️ Download Results (CSV)",
        csv,
        f"{label}_Catholic_Schools_2025.csv",
        "text/csv"
    )

# ========================================
#  TOP 10 CHART
# ========================================
with st.expander("📊 Top 10 Most Oversubscribed London Catholic Schools"):
    top10 = merged.nlargest(10, "Oversub Ratio")[["School Name", "Oversub Ratio"]]
    st.bar_chart(top10.set_index("School Name")["Oversub Ratio"])

# ========================================
#  SNOBE EXPLANATION FOOTNOTE
# ========================================
st.divider()
st.markdown(
    '<div style="text-align:center;margin-bottom:8px">'
    '<a href="#top" style="background:#0055a5;color:white;padding:8px 20px;'
    'border-radius:20px;text-decoration:none;font-size:0.9rem;">⬆️ Back to top</a>'
    '</div>',
    unsafe_allow_html=True
)
st.caption("Built with love by a London parent • 2025 admissions data • Mobile-ready")
with st.expander("ℹ️ About this data"):
    st.markdown(
        "**Snobe grade** — Independent rating of school quality (separate from Ofsted). "
        "See [snobe.co.uk](https://snobe.co.uk) for methodology.\n\n"
        "**IMD (Deprivation)** — England's official Index of Multiple Deprivation by area. "
        "Decile 1 = most deprived 10% of areas in England; Decile 10 = least deprived. "
        "Source: MHCLG 2019.\n\n"
        "**Crime data** — Street-level incidents within ~500 m of the school postcode, "
        "sourced from [data.police.uk](https://data.police.uk). "
        "Reflects the surrounding area, not the school itself.\n\n"
        "**Oversubscription** — Based on first-preference applications received in the 2025 admissions round. "
        "Schools may fill remaining places through second/third preference applicants.\n\n"
        "**Faith priority** — Catholic schools prioritise baptised Catholics. The oversubscription ratio "
        "includes all applicants; non-Catholics rarely receive offers at oversubscribed Catholic schools. "
        "Check each school's admissions policy for the exact criteria order."
    )

# ========================================
