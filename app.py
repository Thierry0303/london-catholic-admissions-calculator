import streamlit as st
import pandas as pd
import os
import numpy as np

# --- Load Data (works locally + on Streamlit Cloud) ---
@st.cache_data
def load_data():
    local_path = "catholic_schools_with_pan_coords.csv"
    github_url = "https://raw.githubusercontent.com/Thierry0303/london-catholic-admissions-calculator/main/catholic_schools_with_pan_coords.csv"
    
    if os.path.exists(local_path):
        df = pd.read_csv(local_path)
    else:
        df = pd.read_csv(github_url)
    
    # Clean and calculate
    df["PAN"] = pd.to_numeric(df.get("PAN"), errors="coerce").fillna(0).astype(int)
    df["Apps Received 2025"] = pd.to_numeric(df.get("Apps Received 2025"), errors="coerce").fillna(0).astype(int)
    df["Oversub Ratio"] = (df["Apps Received 2025"] / df["PAN"].replace(0, 1)) * 100
    df["Oversub Ratio"] = df["Oversub Ratio"].round(0).astype(int)
    
    # Ensure contact/Ofsted columns exist
    for col in ["Phone", "Website", "Ofsted Rating", "Last Inspection"]:
        if col not in df.columns:
            df[col] = ""
    
    # Normalize Website column
    df["Website"] = df["Website"].astype(str).str.strip().replace({"": np.nan, "nan": np.nan})
    df["Website"] = df["Website"].apply(
        lambda x: f"http://{x}" if pd.notnull(x) and not str(x).startswith(("http://","https://")) else x
    )
    
    # Ofsted badge
    def ofsted_badge(r):
        if "Outstanding" in str(r): return "Outstanding"
        if "Good" in str(r): return "Good"
        if "Requires" in str(r): return "Requires Improvement"
        if "Inadequate" in str(r): return "Inadequate"
        return "Awaiting"
    df["Ofsted Badge"] = df["Ofsted Rating"].apply(ofsted_badge)
    
    return df

merged = load_data()

# --- Page Config ---
st.set_page_config(page_title="London Catholic Schools 2025", page_icon="📘", layout="centered")

# --- Header ---
st.markdown("""
<h1 style="text-align:center; color:#0055a5; font-size:2.5rem;">Cross London Catholic Schools 2025</h1>
<p style="text-align:center; font-size:1.2rem; color:#444;">Real chances • Phone • Website • Ofsted • For parents</p>
""", unsafe_allow_html=True)

# --- Sidebar ---
with st.sidebar:
    st.header("Filters")
    selected_borough = st.selectbox("Borough", sorted(merged["Local Authority"].dropna().unique()))
    selected_phase = st.multiselect("Phase", merged["Phase"].unique(), default=merged["Phase"].unique())
    postcode_query = st.text_input("Postcode (e.g. SW6)")
    
    with st.expander("Admission Criteria", expanded=True):
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
    if priority_score >= 70: chance = max(15, 98 - (oversub - 100) * 0.25)
    elif priority_score >= 50: chance = max(8, 90 - (oversub - 100) * 0.6)
    elif priority_score >= 20: chance = max(3, 65 - oversub * 0.8)
    else: chance = max(1, 40 - oversub)
    return min(100, round(chance, 1))

# --- Filter ---
filtered = merged[merged["Local Authority"] == selected_borough]
filtered = filtered[filtered["Phase"].isin(selected_phase)]
if postcode_query:
    filtered = filtered[filtered["Postcode"].str.contains(postcode_query.strip(), case=False, na=False)]
filtered = filtered.copy()
filtered["Your Chance"] = filtered.apply(calculate_likelihood, axis=1)

# --- Personal Advice ---
if sibling:
    st.success("Siblings nearly always get in — **you are in a very strong position!**")
elif baptised and church_attendance:
    st.success("Practising Catholic family — **excellent chances**")
elif baptised:
    st.info("Baptism helps, but many schools require proof of practice")
else:
    st.warning("Non-Catholic places are very limited")

# --- Results: Mobile Cards ---
st.subheader(f"{len(filtered)} school{'s' if len(filtered) != 1 else ''} in {selected_borough}")

for _, school in filtered.sort_values("Your Chance", ascending=False).iterrows():
    with st.container():
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"**{school['School Name']}** • {school['Phase']}")
            st.caption(f"{school['Postcode']} • Oversub: {school['Oversub Ratio']}%")
        with col2:
            chance = int(school['Your Chance'])
            color = "#4CAF50" if chance >= 80 else "#FF9800" if chance >= 50 else "#F44336"
            st.markdown(f"<div style='background:{color};color:white;padding:8px;border-radius:8px;text-align:center;font-weight:bold;'>{chance}%</div>", unsafe_allow_html=True)
        
        # Ofsted
        if school["Ofsted Rating"]:
            st.caption(f"Ofsted {school['Ofsted Badge']} • Last: {school['Last Inspection']}")
        
        # Contact info
        if school.get("Phone"):
            st.markdown(f"📞 {school['Phone']}")
        if school.get("Website"):
            st.markdown(f"🌐 [Visit Website]({school['Website']})")
        
        st.markdown("---")

# --- Map ---
if {"Latitude", "Longitude"}.issubset(filtered.columns):
    map_data = filtered[["School Name", "Your Chance", "Latitude", "Longitude"]].dropna().rename(columns={"Latitude": "lat", "Longitude": "lon"})
    st.map(map_data)

# --- Download ---
csv = filtered.to_csv(index=False).encode()
st.download_button("Download Results + Contacts", csv, f"{selected_borough}_Catholic_2025.csv", "text/csv")

# --- Top 10 ---
with st.expander("Top 10 Most Oversubscribed Catholic Schools"):
    top10 = merged.nlargest(10, "Oversub Ratio")[["School Name", "Oversub Ratio"]]
    st.bar_chart(top10.set_index("School Name")["Oversub Ratio"])

st.caption("Built with ❤️ by a London parent • 2025 admissions • Phone • Website • Ofsted • Mobile-ready")
