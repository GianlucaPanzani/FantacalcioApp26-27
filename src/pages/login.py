import streamlit as st
from lib.utils import (
    get_icon,
    get_current_season
)

st.title(f"{get_icon('ball')} Fantacalcio {get_current_season()}")

# Start Google authentication; profile data is saved by the registration form.
st.button(
    "Access with Google",
    type="primary",
    width="stretch",
    on_click=st.login,
    args=("google",),
)
