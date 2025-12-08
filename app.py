# app.py — Mobile-First London Catholic Schools 2025
import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="Catholic Schools 2025",
    page_icon="✝️",
    layout="centered",          # ← Mobile-first: centered = perfect on phones
    initial_sidebar_state="expanded"
)

# --- Load data (fixed for Streamlit Cloud) ---
@st.cache_data
def load_data():
    df = pd.read_csv("catholic_schools_with_pan_coords.csv")
    df["PAN"] = pd.to_numeric(df["PAN"], errors='coerce').fillna(0).astype(int)
    df["Apps Received 2025"] = pd.to_numeric(df["Apps Received 2025"], errors='coerce').fillna(0)
    df["Oversub Ratio"] = (df["Apps Received 2025"] / df["PAN"].replace(0, 1)) * 100
    df["Oversub Ratio"] = df["Oversub Ratio"].round(0).astype(int)
    return df

df = load_data()

# --- Gorgeous mobile header ---
st.markdown("""
<style>
    .big-title {font-size: 2.2rem !important; text-align: center; color: #0055a5; font-weight: 700;}
    .subtitle {text-align: center; color: #444; font-size: 1rem; margin-bottom: 2rem;}
    .stButton>button {width: 100%; background: #0055a5; color: white; font-size: 1.1rem; padding: 0.8rem;}
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="big-title">✝️ Catholic Schools 2025</h1>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Find your family’s best chance — made for London parents</p>', unsafe_allow_html=True)

# --- Compact sidebar (perfect on mobile) ---
with st.sidebar:
    st.header("Your Family")
    borough = st.selectbox("Borough", sorted(df["Local Authority"].unique()))
    phase = st.multiselect("Phase", df["Phase"].unique(), default=df["Phase"].unique())
    
    st.markdown("**Faith & Priority**")
    baptised = st.checkbox("Baptised Catholic", True)
    church = st.checkbox("Regular church attendance", True)
    sibling = st.checkbox("Sibling at school", False)
    
    postcode = st.text_input("Postcode (e.g. SW3)", "")

# --- Realistic likelihood ---
def chance(row):
    p = 0
    if sibling: p += 45
    if baptised and church: p += 35
    elif baptised: p += 15
    o = row["Oversub Ratio"]
    if p >= 70: return min(100, max(20, 99 - (o-100)*0.25))
    if p >= 50: return min(100, max(10, 92 - (o-100)*0.6))
    return min(100, max(5, 70 - o*0.8))

# --- Filter ---
filtered = df[df["Local Authority"] == borough]
filtered = filtered[filtered["Phase"].isin(phase)]
if postcode:
    filtered = filtered[filtered["Postcode"].str.contains(postcode.strip(), case=False, na=False)]

filtered = filtered.copy()
filtered["Your Chance"] = filtered.apply(chance, axis=1).round(0).astype(int)

# --- Personal advice (big & clear on mobile) ---
if sibling:
    st.success("Siblings nearly always get in — you’re in a **very strong** position!")
elif baptised and church:
    st.success("Practising Catholic family — **excellent chances** at most schools")
elif baptised:
    st.info("Baptised helps, but many schools prioritise regular practice")
else:
    st.warning("Non-Catholic places are very limited")

# --- Results table (mobile-optimized) ---
result = filtered[["School Name", "Phase", "Postcode", "Oversub Ratio", "Your Chance"]].copy()
result = result.sort_values("Your Chance", ascending=False)

st.subheader(f"{len(result)} school{'' if len(result)==1 else 's'} in {borough}")

if not result.empty:
    # Mobile-friendly styling
    st.dataframe(
        result.style
        .bar(subset=["Oversub Ratio"], color="#ff9999")
        .bar(subset=["Your Chance"], color="#90ee90")
        .format({"Oversub Ratio": "{:.0f}%", "Your Chance": "{:.0f}%"}),
        use_container_width=True,
        height=500
    )
    
    # Map (only if coordinates exist)
    if {"Latitude", "Longitude"}.issubset(filtered.columns):
        map_data = filtered[["School Name", "Your Chance", "Latitude", "Longitude"]].dropna()
        map_data = map_data.rename(columns={"Latitude": "lat", "Longitude": "lon"})
        st.map(map_data, size=100, color="#d40000")

    # Download button
    csv = result.to_csv(index=False).encode()
    st.download_button("Download these results", csv, f"{borough}_catholic_2025.csv", "text/csv")

else:
    st.info("No schools match your filters — try widening your search")

# --- Top 10 (collapsible on mobile) ---
with st.expander("Top 10 Most Competitive London Catholic Schools"):
    top10 = df.nlargest(10, "Oversub Ratio")[["School Name", "Oversub Ratio"]]
    st.bar_chart(top10.set_index("School Name")["Oversub Ratio"])

st.caption("Built by a London parent • Updated for 2025 admissions")
