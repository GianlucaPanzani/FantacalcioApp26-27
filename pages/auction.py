import streamlit as st
import pandas as pd
import lib.streamlit_api as myst


st.set_page_config(
    page_title="Fantacalcio 26-27",
    page_icon="⚽",
    layout="wide",
)

# =============================================================================
# ============================== FUNCTIONS ====================================
# =============================================================================

def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Apply filters currently stored in Streamlit session state."""
    result = df.copy()

    selected_players = st.session_state.get("fanta_player_key", [])
    selected_team = st.session_state.get("fanta_team_key")

    if selected_players:
        result = result[result["player"].isin(selected_players)]
    if selected_team:
        result = result[result["team"] == selected_team]
    return result

def player_filter(fanta_players: pd.DataFrame):

    # Initialize default filter values
    st.session_state.setdefault("fanta_player_key", [])
    st.session_state.setdefault("fanta_team_key", "")

    # Apply previous selections before generating widget options.
    options_df = apply_filters(fanta_players)

    names = sorted(options_df["player"].dropna().astype(str).unique())
    teams = sorted(options_df["team"].dropna().astype(str).unique())

    # Restore widget values after their options change.
    st.session_state["fanta_player_widget_key"] = [
        player
        for player in st.session_state["fanta_player_key"]
        if player in names
    ]
    st.session_state["fanta_team_widget_key"] = (
        st.session_state["fanta_team_key"]
        if st.session_state["fanta_team_key"] in teams
        else None
    )
    
    # Create widgets
    cols = st.columns([9,1,9,1,9,1,9,1])
    with cols[0]:
        selected_players = st.multiselect(
            "Search players",
            options=names,
            placeholder="Select one or more players...",
            key="fanta_player_widget_key",
            on_change=myst.sync_filter,
            args=("fanta_player_key", "fanta_player_widget_key"),
        )
    with cols[2]:
        selected_team = st.selectbox(
            "Select team",
            options=teams,
            index=None,
            placeholder="Select a team...",
            key="fanta_team_widget_key",
            on_change=myst.sync_filter,
            args=("fanta_team_key", "fanta_team_widget_key"),
        )

    st.divider()

    # Apply the values returned by the widgets during the current rerun.
    filtered_df = fanta_players.copy()
    if selected_players:
        filtered_df = filtered_df[filtered_df["player"].isin(selected_players)]
    if selected_team:
        filtered_df = filtered_df[filtered_df["team"] == selected_team]

    return filtered_df

def create_sidebar_settings():

    with st.sidebar:
        st.divider()

        with st.container(border=True):
            st.markdown("### ⚙️ Fantacalcio settings")
            st.caption("Customize Fantacalcio values")

            budget = st.number_input(
                "Available budget",
                min_value=0,
                value=500,
                step=10,
                key="fantacalcio_budget",
            )

            scoring_mode = st.selectbox(
                "Scoring mode",
                options=["Classic", "Mantra"],
                key="fantacalcio_scoring_mode",
            )

            include_unmatched = st.toggle(
                "Include players without statistics",
                value=True,
                key="fantacalcio_include_unmatched",
            )
    
    return


# =============================================================================
# =============================== SCRIPT ======================================
# =============================================================================

create_sidebar_settings()

st.title("⚽ Fantacalcio 26-27 - Create your own team")

fanta_players = myst.load_dataset("data/filtered_history_players.csv", filter_by_current_year=True)

st.divider()

st.subheader("Add a player to your team")

filtered_players = player_filter(fanta_players)
st.session_state["filtered_players"] = filtered_players


