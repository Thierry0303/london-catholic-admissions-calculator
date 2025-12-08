import streamlit as st
import pandas as pd
import os
import numpy as np

st.set_page_config(page_title="London Catholic Schools 2025", page_icon="📘", layout="centered")

# --- Config ---
FULL_PATH = "catholic_schools_with_pan_coords.csv"
FULL_GITHUB = "https://raw.githubusercontent.com/Thierry0303/london-catholic-admissions-calculator/main/catholic_schools_with_pan_coords.csv"

# --- Load Data ---
@st.cache_data
def load_data():
    if os.path.exists(FULL_PATH):
        df = pd.read_csv(FULL_PATH)
    else:
        df = pd.read_csv(FULL_GITHUB)

    # Clean numeric fields
    df["PAN"] = pd.to_numeric(df.get("PAN"), errors="coerce").fillna(0).astype(int)
    df["Apps Received 2025"] = pd.to_numeric(df.get("Apps Received 2025"), errors="coerce").fillna(0).astype(int)

    # Oversubscription ratio (%)
    df["Oversub Ratio"] = (df["Apps Received 2025"] / df["PAN"].replace(0, 1)) * 100
    df["Oversub Ratio"] = df["Oversub Ratio"].round(0).astype(int)

    # Ensure columns exist
    for col in ["Phone", "School Website", "Ofsted Rating", "Last Inspection", "Snobe Overall Grade"]:
        if col not in df.columns:
            df[col] = ""

    # Normalize Website links
    df["School Website"] = df["School Website"].astype(str).str.strip().replace({"": np.nan, "nan": np.nan})
    df["School Website"] = df["School Website"].apply(
        lambda x: f"http://{x}" if pd.notnull(x) and not str(x).startswith(("http://","https://")) else x
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

    # Borough normalization
    if "Local Authority" in df.columns:
        df["Local Authority"] = df["Local Authority"].astype(str).str.strip().str.title()

    return df

merged = load_data()

# --- Header ---
st.markdown("""
<h1 style="text-align:center; color:#0055a5; font-size:2.5rem;">Cross London Catholic Schools 2025</h1>
<p style="text-align:center; font-size:1.2rem; color:#444;">Real chances • Website • Ofsted • Snobe grade • For parents</p>
""", unsafe_allow_html=True)

# --- Sidebar ---
with st.sidebar:
    st.header("Filters")
    boroughs = sorted([b for b in merged["Local Authority"].dropna().unique()])
    selected_borough = st.selectbox("Borough", boroughs)
    phases = list(merged["Phase"].dropna().unique())
    selected_phase = st.multiselect("Phase", phases, default=phases)
    postcode_query = st.text_input("Postcode (e.g. SW6)")

    with st.expander("Admission criteria", expanded=True):
        baptised = st.checkbox("Baptised Catholic", True)
        church_attendance = st.checkbox("Regular church attendance", True)
        sibling = st.checkbox("Sibling at school", False)

# --- Likelihood Calculator ---
def calculate_likelihood(row):
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

# --- Composite Quality Score ---
def quality_score(row):
    grade_map = {"A+": 5, "A": 4.5, "A-": 4, "B+": 3.5, "B": 3, "B-": 2.5}
    grade_val = grade_map.get(str(row.get("Snobe Overall Grade", "")).strip(), 0)

    ofsted_map = {"Outstanding": 5, "Good": 4, "Requires Improvement": 2, "Inadequate": 1}
    ofsted_val = ofsted_map.get(str(row.get("Ofsted Badge", "")).strip(), 0)

    oversub_penalty = 1 / (1 + row.get("Oversub Ratio", 0))
    return round((grade_val + ofsted_val) * oversub_penalty, 2)

merged["Quality Score"] = merged.apply(quality_score, axis=1)

# --- Filter ---
filtered = merged[merged["Local Authority"] == selected_borough]
filtered = filtered[filtered["Phase"].isin(selected_phase)]
if postcode_query:
    filtered = filtered[filtered["Postcode"].str.contains(postcode_query.strip(), case=False, na=False)]
filtered = filtered.copy()
filtered["Your Chance"] = filtered.apply(calculate_likelihood, axis=1)

# --- Personal Advice ---
if sibling:
    st.success("Siblings nearly always get in — you are in a very strong position!")
elif baptised and church_attendance:
    st.success("Practising Catholic family — excellent chances")
elif baptised:
    st.info("Baptism helps, but many schools require proof of practice")
else:
    st.warning("Non-Catholic places are very limited")

# --- Results Cards ---
st.subheader(f"{len(filtered)} school{'s' if len(filtered) != 1 else ''} in {selected_borough}")

for _, school in filtered.sort_values("Your Chance", ascending=False).iterrows():
    with st.container():
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"**{school['School Name']}** • {school['Phase']}")
            st.caption(f"{school['Postcode']} • Oversub: {school['Oversub Ratio']}%")

            # --- Rating Display with tooltips ---
            rating_parts = []
            snobe_grade = str(school.get("Snobe Overall Grade", "")).strip()
            ofsted = str(school.get("Ofsted Badge", "")).strip()

            if snobe_grade:
                grade_tooltip = {
                    "A+": "Top 5% nationally",
                    "A": "Excellent overall performance",
                    "A-": "Very strong school",
                    "B+": "Above average",
                    "B": "Solid performance",
                    "B-": "Room for improvement"
                }.get(snobe_grade, "Rated by Snobe")
                rating_parts.append(
                    f"<span title='{grade_tooltip}' style='color:#4CAF50;font-weight:bold;'>Snobe {snobe_grade}</span>"
                )

            if ofsted and ofsted != "Awaiting":
                ofsted_tooltip = {
                    "Outstanding": "Highest Ofsted rating",
                    "Good": "Consistently strong teaching and outcomes",
                    "Requires Improvement": "Some weaknesses identified",
                    "Inadequate": "Serious concerns raised"
                }.get(ofsted, "Ofsted rating")
                rating_parts.append(
                    f"<span title='{ofsted_tooltip}' style='color:#2196F3;font-weight:bold;'>Ofsted {ofsted}</span>"
                )

            if rating_parts:
                rating_html = " • ".join(rating_parts)
                st.markdown(f"<div style='margin-top:4px;font-size:0.95rem;'>{rating_html}</div>", unsafe_allow_html=True)

        with col2:
            chance = int(school['Your Chance'])
            color = "#4CAF50" if chance >= 80 else "#FF9800" if chance >= 50 else "#F44336"
            st.markdown(
                f"<div style='background:{color};color:white;padding:8px;border-radius:8px;text-align:center;font-weight:bold;'>{chance}%</div>",
                unsafe_allow_html=True
            )

        if school.get("School Website") and pd.notnull(school["School Website"]) and str(school["School Website"]).strip():
            st.markdown(f"🌐 [Visit Website]({school['School Website']})")

        st.caption(f"Quality Score: {school['Quality Score']}")
        st.markdown("---")

# --- Map ---
if {"Latitude", "Longitude"}.issubset(filtered.columns):
    map_data = filtered[
