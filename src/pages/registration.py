import sqlite3
import streamlit as st

from backend.services import register_user
from lib.streamlit_api.design_handler import get_emoji

page_name = "registration"

st.set_page_config(
    page_title="Registration | Fantacalcio",
    page_icon=get_emoji(page_name),
)



def save_data():
    """Save the user with the values submitted by the form."""
    # Read widget values here: callbacks run after Streamlit submits the form.
    st.session_state[error_key] = None
    st.session_state[saved_key] = False
    try:
        username = st.session_state[username_key].strip()
        team_name = st.session_state[team_name_key].strip()
        archive = st.session_state[zip_key]
        if not username:
            raise ValueError("Enter a username.")
        if not team_name:
            raise ValueError("Enter a team name.")
        
        user = register_user(
            user_data={
                "auth_issuer": st.user.iss,
                "auth_subject": st.user.sub,
                "username": username,
                "team_name": team_name,
            },
            zip_archive=archive.getvalue() if archive is not None else None
        )
    except ValueError as error:
        st.session_state[error_key] = str(error)
        return
    except sqlite3.IntegrityError:
        st.session_state[error_key] = "This username or team name is already in use."
        return

    # Save the identifiers of the registered user and auction.
    st.session_state["user_id_key"] = user["id"]
    st.session_state["auction_id_key"] = user["current_auction_id"]
    st.session_state["settings_my_manager_key"] = user["username"]
    st.session_state["settings_managers_key"] = [user["username"]]
    st.session_state[saved_key] = True
    return



# Session state keys
auction_code_key = f"{page_name}_auction_code_widget_key"
username_key = f"{page_name}_username_key"
team_name_key = f"{page_name}_team_name_key"
zip_key = f"{page_name}_zip_key"
confirmation_button_key = f"{page_name}_confirmation_button_key"
error_key = f"{page_name}_error_key"
saved_key = f"{page_name}_saved_key"


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
        on_click=save_data,
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
