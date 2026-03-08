with c_left:
    st.markdown("**Deprivation (IMD)**")

    if has_postcode:
        imd_data = fetch_imd(str(school["Postcode"]))

        if imd_data and imd_data.get("decile"):
            dec = imd_data["decile"]
            desc, colour = imd_label(dec)

            # IMD badge
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
