# --- Neighbourhood context (cleaned up)
with st.expander("🏘️ Neighbourhood context"):
    st.caption(
        "ℹ️ These figures reflect the **surrounding area**, not the school itself. "
        "Crime stats cover a ~500 m radius from the school (latest available month)."
    )

    c_left, c_right = st.columns(2)

    # ============================================================
    # IMD CLEANED-UP BADGE
    # ============================================================
    with c_left:
        st.markdown("**Deprivation (IMD)**")

        if has_postcode:
            imd_data = fetch_imd(str(school["Postcode"]))

            if imd_data and imd_data.get("decile"):
                dec = imd_data["decile"]
                desc, colour = imd_label(dec)

                st.markdown(
                    f"""
                    <div style="
                        background:{colour};
                        color:white;
                        padding:6px 10px;
                        border-radius:6px;
                        font-weight:600;
                        font-size:0.85rem;
                        display:inline-block;
                        margin-bottom:4px;">
                        {desc}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                st.caption("1 = most deprived · 10 = least deprived in England")

                if imd_data.get("score") is not None:
                    st.caption(f"IMD score: {imd_data['score']}")

            else:
                st.markdown(
                    """
                    <div style="
                        background:#9E9E9E;
                        color:white;
                        padding:6px 10px;
                        border-radius:6px;
                        font-weight:600;
                        font-size:0.85rem;
                        display:inline-block;">
                        IMD unavailable
                    </div>
                    """,
                    unsafe_allow_html=True
                )
        else:
            st.caption("No postcode available.")

    # ============================================================
    # CRIME CLEANED-UP BADGE
    # ============================================================
    with c_right:
        st.markdown("**Crime (500 m radius)**")

        if has_coords:
            crime_data, crime_month = fetch_crime(float(school["Latitude"]), float(school["Longitude"]))

            if crime_data:
                total = crime_data.get("total", 0)

                # Colour scale
                c_colour = (
                    "#1B5E20" if total < 20 else
                    "#E65100" if total < 60 else
                    "#B71C1C"
                )

                st.markdown(
                    f"""
                    <div style="
                        background:{c_colour};
                        color:white;
                        padding:6px 10px;
                        border-radius:6px;
                        font-weight:600;
                        font-size:0.85rem;
                        display:inline-block;
                        margin-bottom:4px;">
                        {total} incidents
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                st.caption(f"Month: {crime_month}")

                # Top 3 categories
                breakdown = {k: v for k, v in crime_data.items() if k != "total"}
                top_cats = sorted(breakdown.items(), key=lambda x: x[1], reverse=True)[:3]

                for cat, n in top_cats:
                    st.caption(f"• {cat}: {n}")

            else:
                st.caption("Crime data unavailable — the police API may be slow or this area isn't covered.")
        else:
            st.caption("No coordinates available.")
