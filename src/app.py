import pandas as pd
import streamlit as st

from backend import api
from backend.user_services import get_user
from backend.auction_services import get_partecipation

from lib.streamlit_api import (
    sidebar_navigation_size
)
from lib.utils import (
    get_icon
)


# Case of user not logged with google
if not st.user.is_logged_in:
    navigation = st.navigation(
        [st.Page("pages/login.py", title="Login")],
        position="hidden",
    )
    navigation.run()
    st.stop()

# Recover the registered account using the identity supplied by Google.
user = get_user(
    auth_issuer=st.user.iss,
    auth_subject=st.user.sub,
)

# New users and users without a membership must complete registration first.
if user is None:
    navigation = st.navigation(
        pages=[st.Page("pages/registration.py", title="Registration")],
        position="hidden",
    )
    navigation.run()
    st.stop()


sidebar_navigation_size(font_size=1.25)

pages = {
    "Pages": [
        st.Page("pages/auction.py", title=f"{get_icon('auction')} Auction"),
        st.Page("pages/fantacalcio.py", title=f"{get_icon('ball')} Fantacalcio"),
        st.Page("pages/statistics.py", title=f"{get_icon('graphic')} Statistics"),
        st.Page("pages/selection.py", title=f"{get_icon('ai')} Players Selection"),
        st.Page("pages/settings.py", title=f"{get_icon('settings')} Settings"),
    ]
}
navigation = st.navigation(pages, position="sidebar", expanded=True)
navigation.run()
