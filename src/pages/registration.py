import sqlite3
import streamlit as st

from backend.user_services import (
    set_user
)
from lib.streamlit_api.design_handler import get_emoji

page_name = "registration"

st.set_page_config(
    page_title="Registration | Fantacalcio",
    page_icon=get_emoji(page_name),
)


# Session state keys
username_key = f"{page_name}_username_key"
team_name_key = f"{page_name}_team_name_key"
zip_key = f"{page_name}_zip_key"
confirmation_button_key = f"{page_name}_confirmation_button_key"
error_key = f"{page_name}_error_key"
saved_key = f"{page_name}_saved_key"


def save_user():
    """Save the user with the values submitted by the form."""
    # Read widget values here: callbacks run after Streamlit submits the form.
    st.session_state[error_key] = None
    st.session_state[saved_key] = False
    try:
        user = set_user(
            st.user.iss,
            st.user.sub,
            st.session_state[username_key],
        )
    except ValueError as error:
        st.session_state[error_key] = str(error)
    except sqlite3.IntegrityError:
        st.session_state[error_key] = "This username is already in use."
    else:
        st.session_state["user_id"] = user["id"]
        st.session_state[saved_key] = True

# Callbacks read fresh widget values from session state after form submission.
if not st.user.is_logged_in:
    st.error("Sign in with Google before registering.")
    st.stop()


# Collect registration data together; only the submit button writes to the DB.
st.title("Complete your registration")

with st.form(f"{page_name}_form"):
    st.text_input("Username", key=username_key)
    st.text_input("Team name", key=team_name_key)
    st.file_uploader(
        "Import zip file to restore the state of your own application",
        type=["zip"],
        key=zip_key,
        help="Optional. ZIP import will be available later; uploaded files are not imported yet.",
    )
    st.form_submit_button(
        "Confirm",
        type="primary",
        width="stretch",
        key=confirmation_button_key,
        on_click=save_user,
    )

# Show the result produced by the submit callback.
if st.session_state.get(error_key):
    st.error(st.session_state[error_key])
elif st.session_state.get(saved_key):
    st.success("Registration successfully completed")
    st.button(
        "Enter the app",
        type="primary",
        width="content",
        on_click=st.rerun,
    )
