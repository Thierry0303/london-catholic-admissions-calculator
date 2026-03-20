import streamlit as st
import pandas as pd
import numpy as np
import math

st.set_page_config(page_title="London Catholic Schools 2025", page_icon="✝️", layout="centered")

# ========================================
# DATA LOADING – FIXED & SAFE
# ========================================
@st.cache_data
def load_data():
    df = pd.read_csv("catholic_schools_with_pan_coords.csv")

    # Rename for consistency
    if "1st Pref Apps 2025" in df.columns:
        df["Apps Received 2025"] = df["1st Pref Apps 2025"]
    if "PAN 2025" in df.columns:
        df["PAN"] = df["PAN 2025"]

    # Safe numerics
    for col in ["PAN", "Apps Received 2025"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0 if col == "Apps Received 2025" else 1)
        else:
            df[col] = 0 if col == "Apps Received 2025" else 1

    # Kill any inf from div-by-zero
    df["PAN"] = df["PAN"].replace(0, 1)

    # Compute ratio safely
    ratio = df["Apps Received 2025"] / df["PAN"]
    ratio = ratio.replace([np.inf, -np.inf], 0) * 100
    df["Oversub Ratio"] = ratio.round(0).fillna(0).astype(int)

    df["_no_data"] = (df["Apps Received 2025"] == 0)

    # Fill other columns
    for col in ["Snobe Overall Grade", "Ofsted Rating", "Local Authority", "Postcode", "Phase", "School Name"]:
        if col not in df.columns:
            df[col] = ""

    return df
    
    # Fill missing columns
    for col in ["Snobe Overall Grade", "Ofsted Rating", "Local Authority", "Postcode", "Phase", "School Name",
                "Latitude", "Longitude", "Phone", "School Website"]:
        if col not in df.columns:
            df[col] = ""

    # Clean website
    df["School Website"] = df["School Website"].astype(str).str.strip().replace({"": np.nan, "nan": np.nan})
    df["School Website"] = df["School Website"].apply(
        lambda x: f"https://{x}" if pd.notnull(x) and not str(x).startswith(("http", "https")) else x
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


merged = load_data()

# ========================================
# SIDEBAR
# ========================================
with st.sidebar:
    st.header("🔍 Search")
    postcode_query = st.text_input("Your postcode (e.g. SW6 1AA)", "")
    max_distance_km = st.slider("Max distance (km)", 1, 20, 5, disabled=not postcode_query)

    st.divider()
    st.subheader("Or filter by borough")
    boroughs = ["All boroughs"] + sorted(merged["Local Authority"].dropna().unique())
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

# Phase filter (robust)
if child_stage == "Primary":
    filtered = filtered[filtered["Phase"].str.contains("Primary|All-through", na=False)]
elif child_stage == "Secondary":
    filtered = filtered[filtered["Phase"].str.contains("Secondary|All-through", na=False)]

# Distance filter
if postcode_query:
    # (your postcode_to_latlon + haversine functions can be added back if you want distance)
    pass  # placeholder – you can re-add later

# Borough filter
if selected_borough != "All boroughs":
    filtered = filtered[filtered["Local Authority"] == selected_borough]

# ========================================
# HEADER
# ========================================
st.markdown("""
<h1 style="text-align:center; color:#0055a5; font-size:2.5rem;">✝️ London Catholic Schools 2025</h1>
<p style="text-align:center; font-size:1.2rem; color:#444;">Real chances • Ofsted • Snobe • For parents</p>
""", unsafe_allow_html=True)

st.caption(f"📅 Data last auto-updated: {merged.get('Last Updated', pd.Series(['2026-03-19'])).max()}")

if len(filtered) == 0:
    st.warning("No schools match your filters.")
    st.stop()

# Summary
col1, col2 = st.columns(2)
col1.metric("Schools found", len(filtered))
avg_ratio = (filtered["Apps Received 2025"] / filtered["PAN"]).mean()
col2.metric("Avg apps per place", f"{avg_ratio:.1f}:1" if not pd.isna(avg_ratio) else "—")

# ========================================
# TOP 10 MOST OVERSUBSCRIBED
# ========================================
with st.expander("🏆 Top 10 Most Oversubscribed Schools", expanded=True):
    top10 = filtered.nlargest(10, "Oversub Ratio")[["School Name", "Oversub Ratio", "Apps Received 2025", "PAN"]]
    st.dataframe(top10, use_container_width=True, hide_index=True)

# ========================================
# SCHOOL CARDS (the main glorious part)
# ========================================
for _, school in filtered.iterrows():
    with st.container(border=True):
        col1, col2 = st.columns([4, 1])

        with col1:
            website = school.get("School Website", "")
            name_link = f"[{school['School Name']}]({website})" if website else school["School Name"]
            st.markdown(f"**{name_link}** • {school['Phase']}")

            loc = f"{school.get('Postcode','')} • {school.get('Local Authority','')}"
            st.caption(loc)

            apps = int(school["Apps Received 2025"])
            pan = int(school["PAN"])
            ratio = int(school["Oversub Ratio"])
            st.caption(f"**{apps} : {pan}** ({apps} apps for {pan} places)")

            badges = []
            if school.get("Snobe Overall Grade"):
                badges.append(f"Snobe {school['Snobe Overall Grade']}")
            if school.get("Ofsted Badge") and school["Ofsted Badge"] != "Awaiting":
                badges.append(f"Ofsted {school['Ofsted Badge']}")
            if badges:
                st.caption(" • ".join(badges))

        with col2:
            # FIXED DEMAND BADGE
            if school["_no_data"] or apps == 0:
                color = "#9E9E9E"
                label = "No data"
            elif ratio >= 400:
                color = "#B71C1C"
                label = "Very high demand"
            elif ratio >= 200:
                color = "#E65100"
                label = "High demand"
            elif ratio >= 130:
                color = "#F9A825"
                label = "Moderate demand"
            elif ratio < 100:
                color = "#1565C0"
                label = "Low demand"
            else:
                color = "#2E7D32"
                label = "Lower demand"

            st.markdown(
                f'<div style="background:{color}; color:white; padding:12px; border-radius:8px; '
                f'text-align:center; font-weight:bold; font-size:1rem;">{label}</div>',
                unsafe_allow_html=True
            )
            st.caption(f"{ratio}% oversubscribed")

        # Neighbourhood context (crime + IMD) can be re-added here if you want

st.divider()
st.caption("Built with love for London Catholic parents • March 2026")
