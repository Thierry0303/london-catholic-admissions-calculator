import streamlit as st
import pandas as pd
import os
import numpy as np
import math

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

    # --- Postcode first ---
    postcode_query = st.text_input("Your postcode (e.g. SW6 1AA)", placeholder="SW6 1AA")
    max_distance_km = st.slider("Max distance (km)", 1, 20, 5, disabled=(not postcode_query))

    st.divider()
    st.subheader("Or filter by borough")
    boroughs = ["All boroughs"] + sorted([b for b in merged["Local Authority"].dropna().unique()])
    selected_borough = st.selectbox("Borough", boroughs)

    phases = list(merged["Phase"].dropna().unique())
    selected_phase = st.multiselect("Phase", phases, default=phases)

    st.divider()
    st.subheader("Your situation")
    with st.expander("Admission criteria", expanded=True):
        baptised = st.checkbox("Baptised Catholic", True)
        church_attendance = st.checkbox("Regular church attendance", True)
        sibling = st.checkbox("Sibling at school", False)

# ========================================
#  APPLY FILTERS
# ========================================
filtered = merged.copy()

# Postcode-based distance filter
home_lat, home_lon = None, None
distance_warning = None
if postcode_query:
    home_lat, home_lon = postcode_to_latlon(postcode_query)
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

# Likelihood
filtered = filtered.copy()
filtered["Your Chance"] = filtered.apply(
    lambda r: calculate_likelihood(r, baptised, church_attendance, sibling), axis=1
)
filtered = filtered.sort_values("Your Chance", ascending=False)

# ========================================
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
    avg_oversub = int(filtered["Oversub Ratio"].mean())
    best_chance = int(filtered["Your Chance"].max())
    n = len(filtered)
    location_label = f"within {max_distance_km}km of {postcode_query.upper()}" if postcode_query and home_lat else selected_borough

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Schools found", n)
    col_b.metric("Avg oversubscription", f"{avg_oversub}%")
    col_c.metric("Best chance for you", f"{best_chance}%")
    st.caption(f"Results for: **{location_label}**  •  Last updated: March 2025")

st.divider()

# ========================================
#  MAP TOGGLE
# ========================================
if {"Latitude", "Longitude"}.issubset(filtered.columns) and len(filtered) > 0:
    show_map = st.toggle("🗺️ Show map", value=False)
    if show_map:
        map_data = filtered[["School Name", "Your Chance", "Latitude", "Longitude"]].dropna()
        map_data = map_data.rename(columns={"Latitude": "lat", "Longitude": "lon"})
        st.map(map_data)
        st.divider()

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
    st.subheader(f"{len(filtered)} school{'s' if len(filtered) != 1 else ''}")

    for _, school in filtered.iterrows():
        with st.container():
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{school['School Name']}** • {school['Phase']}")
                dist_str = f" • 📍 {school['Distance (km)']} km away" if "Distance (km)" in school and pd.notna(school.get("Distance (km)")) else ""
                st.caption(f"{school['Postcode']} • {school['Local Authority']}{dist_str}")
                st.caption(f"Oversubscription: **{school['Oversub Ratio']}%** ({school['Apps Received 2025']} apps for {school['PAN']} places)")

                badges = []
                if school.get("Snobe Overall Grade") and str(school["Snobe Overall Grade"]).strip():
                    badges.append(f"Snobe {school['Snobe Overall Grade']} ℹ️")
                if school.get("Ofsted Badge") and school["Ofsted Badge"] != "Awaiting":
                    badges.append(f"Ofsted: {school['Ofsted Badge']}")
                if badges:
                    st.caption(" • ".join(badges))

            with col2:
                chance = int(school['Your Chance'])
                color = "#1B5E20" if chance >= 80 else "#33691E" if chance >= 50 else "#B71C1C"
                st.markdown(
                    f"<div style='background:{color};color:white;padding:10px;border-radius:10px;text-align:center;font-weight:bold;font-size:1.3rem'>{chance}%</div>",
                    unsafe_allow_html=True
                )
                st.caption("your chance")

            # How calculated
            with st.expander("How is this calculated?"):
                st.caption(chance_explanation(school, baptised, church_attendance, sibling))
                st.caption("Chance combines your Catholic priority score with how oversubscribed the school is. It's a guide, not a guarantee.")

            if pd.notna(school.get("Phone")) and school["Phone"]:
                st.markdown(f"📞 {school['Phone']} | [Call](tel:{school['Phone']})")
            if pd.notna(school.get("School Website")) and str(school["School Website"]).strip():
                st.markdown(f"🌐 [Visit School Website]({school['School Website']})")

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
st.caption(
    "**Snobe grade**: Independent rating of school quality (separate from Ofsted). "
    "Higher grades indicate better performance on academic and pastoral measures. "
    "See [snobe.co.uk](https://snobe.co.uk) for methodology.\n\n"
    "Built with love by a London parent • 2025 admissions data • Mobile-ready"
)
