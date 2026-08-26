import pandas as pd
import streamlit as st
import lib.streamlit_api as myst


pages = {
    "Pages": [
        st.Page("pages/statistics.py", title="Statistics", icon="📊"),
        st.Page("pages/fantacalcio.py", title="Fantacalcio", icon="⚽"),
        st.Page("pages/auction.py", title="Auction", icon="🔨"),
    ]
}
navigation = st.navigation(pages, position="sidebar", expanded=True)
navigation.run()

