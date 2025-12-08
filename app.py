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

# --- Likelihood Calculator ---
def calculate_likelihood(row):
    priority_score = 0
    if sibling: priority_score += 40
    if baptised and church_attendance: priority_score += 35
    elif baptised: priority_score += 18
    else: priority_score += 5

    oversub = row["Oversub Ratio"]
    if priority_score
