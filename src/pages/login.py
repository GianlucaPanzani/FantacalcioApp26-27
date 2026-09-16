import streamlit as st
from lib.utils import (
    get_emoji,
    get_icon,
    get_current_season
)

page_name = "login"

st.set_page_config(
    page_title="Login | Fantacalcio",
    page_icon=get_emoji(page_name),
)

st.title(f"{get_icon('ball')} Fantacalcio {get_current_season()}")
st.header("Login")

# Start Google authentication (profile data is saved by the registration form)
st.button(
    "Access with Google",
    type="primary",
    width="stretch",
    on_click=st.login,
    args=("google",),
)
