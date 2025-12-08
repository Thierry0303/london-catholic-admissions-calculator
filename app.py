import streamlit as st
import pandas as pd

# --- Load your existing CSV (this is the only file you need) ---
@st.cache_data
def load_data():
    df = pd.read_csv(r"C:\Users\Thier Ry\OneDrive\catholic-admission-app\Admission\catholic_schools_with_pan_coords.csv")
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

# --- Realistic Likelihood Calculator ---
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

    if priority_score >= 70:  # Sibling + practising
        chance = max(15, 98 - (oversub - 100) * 0.25)
    elif priority_score >= 50:  # Practising Catholic
        chance = max(8, 90 - (oversub - 100) * 0.6)
    elif priority_score >= 20:  # Baptised only
        chance
