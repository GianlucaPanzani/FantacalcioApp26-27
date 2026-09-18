import streamlit as st

from backend.users_db import get_users
from backend.db_api import create_db
from lib.streamlit_api.design_handler import get_icon, sidebar_navigation_size

try:
    create_db()
except:
    pass

# Case of user not logged with google
if not st.user.is_logged_in:
    navigation = st.navigation(
        [st.Page("pages/login.py", title="Login")],
        position="hidden",
    )
    navigation.run()
    st.stop()

# Recover the registered account using the identity supplied by Google.
users = get_users(
    filters={
        "auth_issuer": st.user.iss,
        "auth_subject": st.user.sub,
    },
)
user = users[0] if users else None

# New users must complete registration before entering the application.
if user is None:
    navigation = st.navigation(
        pages=[st.Page("pages/registration.py", title="Registration")],
        position="hidden",
    )
    navigation.run()
    st.stop()

st.session_state["user_id_key"] = user["id"]
st.session_state["auction_id_key"] = user["current_auction_id"]
st.session_state["username_key"] = user["username"]


sidebar_navigation_size(font_size=1.28)

pages = {
    "FantAI": [
        st.Page("pages/auction.py", title=f"{get_icon('auction')} Auction"),
        st.Page("pages/fantacalcio.py", title=f"{get_icon('ball')} Fantacalcio"),
        st.Page("pages/statistics.py", title=f"{get_icon('graphic')} Statistics"),
        st.Page("pages/selection.py", title=f"{get_icon('ai')} Players Selection"),
        st.Page("pages/settings.py", title=f"{get_icon('settings')} Settings"),
    ]
}
navigation = st.navigation(pages, position="sidebar", expanded=True)
navigation.run()
