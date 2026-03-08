import streamlit as st
import pandas as pd
import os
import np as np
import math
import urllib.parse

st.set_page_config(page_title="London Catholic Schools 2025", page_icon="✝️", layout="centered")

# ========================================
#  DATA LOADING
# ========================================
FULL_PATH = "catholic_schools_with_pan_coords.csv"
FULL_GITHUB = "https://raw.githubusercontent.com/Thierry0303/london-catholic-admissions-calculator/main/catholic_schools_with_pan_coords.csv"

@st.cache_data
def load_data():
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
        if "Good" in r: return "Good"
        if "Requires" in r: return "Requires Improvement"
        if "Inadequate" in r: return "Inadequate"
        return "Awaiting"
    df["Ofsted Badge"] = df["Ofsted Rating"].apply(ofsted_badge)

    if "Local Authority" in df.columns:
        df["Local Authority"] = df["Local Authority"].astype(str).str.strip().str.title()

    return df


# ========================================
#  POSTCODE → LAT/LNG  (free, no API key)
# ========================================
@st.cache_data(show_spinner=False)
def postcode_to_latlon(postcode: str):
    """Calls postcodes.io — free, no key needed."""
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
    url = f"https://data.police.uk/api/crimes-street/all-crime?poly={poly}&
