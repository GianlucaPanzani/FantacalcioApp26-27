import pandas as pd
import streamlit as st
from lib.streamlit_api import (
    sidebar_navigation_size
)
from lib.utils import (
    get_ai_icon
)

sidebar_navigation_size()

pages = {
    "Pages": [
        st.Page("pages/statistics.py", title="Statistics", icon="📊"),
        st.Page("pages/fantacalcio.py", title="Fantacalcio", icon="⚽"),
        st.Page("pages/selection.py", title="Players Selection", icon=":material/group_add:"),
        st.Page("pages/predictions.py", title=f"{get_ai_icon()} Predictions"),
        st.Page("pages/settings.py", title="Settings", icon="⚙️"),
    ]
}
navigation = st.navigation(pages, position="sidebar", expanded=True)
navigation.run()

