import streamlit as st
import pandas as pd
import os

# --- Load your CSV (works locally and on Streamlit Cloud) ---
@st.cache_data
def load_data():
    local_path = "catholic_schools_with_pan_coords.csv"
    github_url = "https://raw.githubusercontent.com/Thierry0303/london-catholic-admissions-calculator/main/catholic_schools_with_pan_coords.csv"

    if os.path.exists(local_path):
        df = pd.read_csv(local_path)
    else:
        df = pd.read_csv(github_url)

    df["PAN"] = pd.to_numeric(df["PAN"], errors='coerce').fillna(0).astype(int)
    df["Apps Received 2025"] = pd.to_numeric(df["Apps Received 2025"], errors='coerce').fillna(0)
    df["Oversub Ratio"] = (df["Apps Received 2025"] / df["PAN"].replace(0, 1)) * 100
    df["Oversub Ratio"] = df["Oversub Ratio"].round(0).astype(int)
    return df

merged = load_data()

# --- Streamlit UI ---
st.set_page_config(page_title="London Catholic Schools Admission 2025", layout="wide")
st.title("🏛️ London Catholic Schools Admission Calculator 2025")
st.markdown("""
**The most accurate parent-built tool for Catholic school admissions in London**  
Data: DfE GIAS PANs + Snobe applications + real coordinates
""")

# --- Sidebar ---
st.sidebar.header("🔍 Filters & Your Family")
selected_borough = st.sidebar.selectbox("Borough", sorted(merged["Local Authority"].dropna().unique()))

threshold = st.sidebar.slider("Show only schools oversubscribed above (%)", 100, 1000, 200, 50)

selected_phase = st.sidebar.multiselect("Phase", options=sorted(merged["Phase"].dropna().unique()),
                                        default=sorted(merged["Phase"].dropna().unique()))

postcode_query = st.sidebar.text_input("Postcode search (e.g. SW6, W3, SE19)")

st.sidebar.markdown("### 🙏 Your Admission Criteria")
baptised = st.sidebar.checkbox("Child is baptised Catholic", value=True)
church_attendance = st.sidebar.checkbox("Regular church attendance (weekly/fortnightly)", value=True)
sibling = st.sidebar.checkbox("Sibling already at the school", value=False)

# --- Likelihood Calculator ---
def calculate_likelihood(row):
    priority_score = 0
    if sibling:
        priority_score += 40
    if baptised and church_attendance:
        priority_score += 35
    elif baptised:
        priority_score += 18
    else:
        priority_score += 5

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

# --- Apply filters ---
filtered = merged[merged["Local Authority"] == selected_borough]
filtered = filtered[filtered["Phase"].isin(selected_phase)]

if postcode_query:
    filtered = filtered[filtered["Postcode"].str.contains(postcode_query.strip(), case=False, na=False)]

filtered = filtered.copy()
filtered["Admission Likelihood %"] = filtered.apply(calculate_likelihood, axis=1)

filtered_threshold = filtered[filtered["Oversub Ratio"] > threshold]

# --- Results Table ---
st.subheader(f"🏫 All Catholic Schools in {selected_borough}")
display = filtered[["School Name", "Phase", "Postcode", "PAN", "Apps Received 2025",
                    "Oversub Ratio", "Admission Likelihood %"]].copy()

display = display.sort_values("Admission Likelihood %", ascending=False)

st.dataframe(
    display.style
    .bar(subset=["Oversub Ratio"], color="#ff9999")
    .bar(subset=["Admission Likelihood %"], color="#90ee90")
    .format({"Oversub Ratio": "{:.0f}%", "Admission Likelihood %": "{:.0f}%"}),
    use_container_width=True
)

# --- Tough Schools ---
if not filtered_threshold.empty:
    st.subheader(f"🔥 Highly Competitive Schools (>{threshold}%)")
    tough = filtered_threshold[["School Name", "PAN", "Apps Received 2025", "Oversub Ratio", "Admission Likelihood %"]]
    st.dataframe(
        tough.sort_values("Oversub Ratio", ascending=False)
        .style.bar(subset=["Oversub Ratio"], color="#ff4d4d")
        .format({"Oversub Ratio": "{:.0f}%", "Admission Likelihood %": "{:.0f}%"}),
        use_container_width=True
    )

# --- Top 10 Chart ---
st.subheader("🏆 Top 10 Most Oversubscribed Catholic Schools in London (2025)")
top10 = merged.nlargest(10, "Oversub Ratio")[["School Name", "Local Authority", "Oversub Ratio"]]
st.bar_chart(top10.set_index("School Name")["Oversub Ratio"])

# --- Map ---
st.subheader(f"🗺️ Map of Catholic Schools in {selected_borough}")
if {"Latitude", "Longitude"}.issubset(filtered.columns):
    map_data = filtered[["School Name", "Admission Likelihood %", "Latitude", "Longitude"]].dropna()
    map_data = map_data.rename(columns={"Latitude": "lat", "Longitude": "lon"})
    st.map(map_data, size=80, color="#d40000")

    with st.expander("📍 See exact coordinates + your chances"):
        st.dataframe(
            map_data[["School Name", "Admission Likelihood %", "lat", "lon"]]
            .sort_values("Admission Likelihood %", ascending=False)
        )
else:
    st.info("No coordinates found in dataset.")

# --- Personal Advice ---
st.markdown("### 🎯 Your Personal Advice")
if sibling:
    st.success("✅ **Strong position** — siblings nearly always get in, even at very oversubscribed schools!")
elif baptised and church_attendance:
    st.success("🙏 **Good position** — practising Catholic families get priority at nearly all schools.")
elif baptised:
    st.warning("⚠️ Baptism helps, but many schools require proof of regular practice.")
else:
    st.error("❌ Most Catholic schools give very low priority to non-Catholics unless exceptional circumstances.")

# --- Download ---
st.subheader("💾 Download Your Results")
csv = filtered.to_csv(index=False).encode('utf-8')
st.download_button(
    "📥 Download this borough as CSV",
    csv,
    f"{selected_borough.replace(' ', '_')}_Catholic_Schools_2025.csv",
    "text/csv"
)

st.caption("Built with ❤️ by a London parent | Data updated for 2025 admissions cycle")
