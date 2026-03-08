import streamlit as st
import pandas as pd

# ---------------------------------------------------------
# IMD LOOKUP
# ---------------------------------------------------------

@st.cache_data
def load_imd_lookup():
    url = (
        "https://assets.publishing.service.gov.uk/media/"
        "5d8b3b5ced915d0373d35414/"
        "File_7_-_All_IoD2019_Scores__Ranks__Deciles_and_"
        "Population_Denominators_3.csv"
    )

    df = pd.read_csv(url)

    # Normalise postcode
    df["Postcode"] = df["Postcode"].str.replace(" ", "").str.upper()

    # Keep only IMD columns
    df = df[
        [
            "Postcode",
            "Index of Multiple Deprivation (IMD) Decile",
            "Index of Multiple Deprivation (IMD) Score",
        ]
    ]

    df = df.rename(
        columns={
            "Index of Multiple Deprivation (IMD) Decile": "IMD_Decile",
            "Index of Multiple Deprivation (IMD) Score": "IMD_Score",
        }
    )

    return df.set_index("Postcode")


def fetch_imd(postcode):
    """Return IMD decile + score for a postcode."""
    if not postcode:
        return None

    clean = postcode.replace(" ", "").upper()
    lookup = load_imd_lookup()

    if clean not in lookup.index:
        return None

    row = lookup.loc[clean]
    return {
        "decile": int(row["IMD_Decile"]),
        "score": float(row["IMD_Score"]),
    }


# ---------------------------------------------------------
# IMD DEBUG PANEL
# ---------------------------------------------------------

def imd_debug_panel():
    st.header("🔍 IMD Debug Panel")

    postcode = st.text_input("Enter a postcode to debug IMD lookup")

    if not postcode:
        st.info("Enter a postcode above to begin.")
        return

    clean = postcode.replace(" ", "").upper()
    st.write(f"**Cleaned postcode:** `{clean}`")

    lookup = load_imd_lookup()

    # Check if postcode exists in lookup
    if clean in lookup.index:
        st.success("Postcode found in IMD lookup table")

        row = lookup.loc[clean]
        st.json(
            {
                "IMD Decile": int(row["IMD_Decile"]),
                "IMD Score": float(row["IMD_Score"]),
            }
        )

        st.subheader("Raw IMD row")
        st.dataframe(lookup.loc[[clean]])

    else:
        st.error("Postcode NOT found in IMD lookup table")
        st.write("Possible reasons:")
        st.write("- The postcode is new or not in the ONS File 7 dataset")
        st.write("- The postcode is not a residential postcode")
        st.write("- The postcode belongs to Scotland, Wales, or NI (England IMD only)")


# ---------------------------------------------------------
# MAIN APP
# ---------------------------------------------------------

st.set_page_config(page_title="IMD Debug App", layout="wide")

st.title("🏫 IMD Lookup & Debug Tool")

page = st.sidebar.radio(
    "Navigation",
    ["Home", "IMD Debug Panel"],
)

if page == "Home":
    st.write("Welcome! Use the sidebar to open the IMD Debug Panel.")
    st.write("This minimal app helps you verify IMD lookups before integrating into your main project.")

elif page == "IMD Debug Panel":
    imd_debug_panel()
