import pandas as pd
import streamlit as st
from lib.streamlit_api import (
    sidebar_navigation_size
)
from lib.utils import (
    get_ai_icon,
    get_ai_player_selection_icon
)

sidebar_navigation_size(font_size=1.25)

pages = {
    "Pages": [
        st.Page("pages/fantacalcio.py", title="Fantacalcio", icon="⚽"),
        st.Page("pages/statistics.py", title="Statistics", icon="📊"),
        st.Page("pages/selection.py", title=f"{get_ai_icon()} Players Selection"),
        st.Page("pages/settings.py", title="Settings", icon="⚙️"),
    ]
}
navigation = st.navigation(pages, position="sidebar", expanded=True)
navigation.run()

