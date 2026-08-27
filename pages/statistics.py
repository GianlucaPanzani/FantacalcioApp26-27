import streamlit as st
import pandas as pd
from lib.streamlit_api import (
    persistent_session_keys,
    role_limits_dict,
    role_budget_limits_dict,
    thick_divider,
    get_fanta_manager_players_dict,
    sync_filter,
    load_dataset,
    load_env,
    store_env
)


st.set_page_config(
    page_title="Statistics",
    page_icon="📊",
    layout="wide",
)

# =============================================================================
# ============================== FUNCTIONS ====================================
# =============================================================================

def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Apply filters currently stored in Streamlit session state."""
    result = df.copy()

    selected_players = st.session_state.get("player_key", [])
    selected_season = st.session_state.get("season_key")
    selected_team = st.session_state.get("team_key")
    selected_competition = st.session_state.get("competition_key")
    selected_min_goals = st.session_state.get("goals_per90_key", 0.0)
    selected_min_nineties = st.session_state.get("nineties_key", 0.0)

    if selected_players:
        result = result[result["player"].isin(selected_players)]
    if selected_season is not None:
        result = result[result["season"] == selected_season]
    if selected_team:
        result = result[result["team"] == selected_team]
    if selected_competition:
        result = result[result["competition"] == selected_competition]
    if selected_min_goals > 0:
        result = result[result["goals_per90"] >= selected_min_goals]
    if selected_min_nineties > 0:
        result = result[result["nineties"] >= selected_min_nineties]
    return result

def get_safe_slider_max(df, column_name, state_key, minimum_max=0.01):
    # Ignore missing or non-numeric values.
    values = pd.to_numeric(df[column_name], errors="coerce").dropna()
    data_max = float(values.max()) if not values.empty else 0.0
    current_value = pd.to_numeric(st.session_state.get(state_key, 0.0), errors="coerce")
    if pd.isna(current_value):
        current_value = 0.0
    current_value = float(current_value)
    st.session_state[state_key] = current_value
    return max(data_max, current_value, minimum_max)

def player_filter(players: pd.DataFrame) -> pd.DataFrame:
    """
    Display a Streamlit UI for filtering historical player records.

    Existing filters are applied before creating the widgets, so every widget
    shows values compatible with the current selection.

    Parameters
    ----------
    players:
        DataFrame containing historical player data.

    Returns
    -------
    pd.DataFrame
        Filtered player DataFrame.
    """

    # Initialize default filter values
    st.session_state.setdefault("player_key", [])
    st.session_state.setdefault("season_key", None)
    st.session_state.setdefault("team_key", None)
    st.session_state.setdefault("competition_key", None)
    st.session_state.setdefault("goals_per90_key", 0.0)
    st.session_state.setdefault("nineties_key", 0.0)

    # Apply previous selections before generating widget options.
    options_df = apply_filters(players)

    names = sorted(options_df["player"].dropna().astype(str).unique())
    seasons = sorted(options_df["season"].dropna().unique(), key=str, reverse=True)
    teams = sorted(options_df["team"].dropna().astype(str).unique())
    competitions = sorted(options_df["competition"].dropna().astype(str).unique())

    # Restore widget values after their options change.
    st.session_state["player_widget_key"] = [
        player
        for player in st.session_state["player_key"]
        if player in names
    ]
    st.session_state["season_widget_key"] = (
        st.session_state["season_key"]
        if st.session_state["season_key"] in seasons
        else None
    )
    st.session_state["team_widget_key"] = (
        st.session_state["team_key"]
        if st.session_state["team_key"] in teams
        else None
    )
    st.session_state["competition_widget_key"] = (
        st.session_state["competition_key"]
        if st.session_state["competition_key"] in competitions
        else None
    )

    # Create widgets
    cols = st.columns([9,1,9,1,9,1,9,1])
    with cols[0]:
        selected_players = st.multiselect(
            "Search players",
            options=names,
            placeholder="Select one or more players...",
            key="player_widget_key",
            on_change=sync_filter,
            args=("player_key", "player_widget_key"),
        )
    with cols[2]:
        selected_team = st.selectbox(
            "Select team",
            options=teams,
            index=None,
            placeholder="Select a team...",
            key="team_widget_key",
            on_change=sync_filter,
            args=("team_key", "team_widget_key"),
        )
    with cols[4]:
        selected_season = st.selectbox(
            "Select season",
            options=seasons,
            index=None,
            placeholder="Select a season...",
            key="season_widget_key",
            on_change=sync_filter,
            args=("season_key", "season_widget_key"),
        )
    with cols[6]:
        selected_competition = st.selectbox(
            "Select competition",
            options=competitions,
            index=None,
            placeholder="Select a competition...",
            key="competition_widget_key",
            on_change=sync_filter,
            args=("competition_key", "competition_widget_key"),
        )

    st.divider()

    # Ensure that the current slider value remains valid.
    max_goals = get_safe_slider_max(options_df, "goals_per90", "goals_per90_key")
    max_nineties = get_safe_slider_max(options_df, "nineties", "nineties_key")

    st.session_state["goals_per90_widget_key"] = st.session_state["goals_per90_key"]
    st.session_state["nineties_widget_key"] = st.session_state["nineties_key"]

    cols = st.columns([9,1,9,1,9,1,9,1])
    with cols[0]:
        selected_min_goals = st.slider(
            "Minimum goals per 90",
            min_value=0.0,
            max_value=max_goals,
            step=0.01,
            key="goals_per90_widget_key",
            on_change=sync_filter,
            args=("goals_per90_key", "goals_per90_widget_key"),
        )
    with cols[6]:
        selected_min_90s = st.slider(
            "Minimum number of 90s played",
            min_value=0.0,
            max_value=max_nineties,
            step=0.01,
            key="nineties_widget_key",
            on_change=sync_filter,
            args=("nineties_key", "nineties_widget_key"),
        )

    # Apply the values returned by the widgets during the current rerun.
    filtered_df = players.copy()
    if selected_players:
        filtered_df = filtered_df[filtered_df["player"].isin(selected_players)]
    if selected_season is not None:
        filtered_df = filtered_df[filtered_df["season"] == selected_season]
    if selected_team:
        filtered_df = filtered_df[filtered_df["team"] == selected_team]
    if selected_competition:
        filtered_df = filtered_df[filtered_df["competition"] == selected_competition]
    if selected_min_goals > 0:
        filtered_df = filtered_df[filtered_df["goals_per90"] >= selected_min_goals]
    if selected_min_90s > 0:
        filtered_df = filtered_df[filtered_df["nineties"] >= selected_min_90s]

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

st.title("📊 Statistics")
st.subheader("Players Filter")

load_env(keys=persistent_session_keys, path=".env")

history_players = load_dataset("data/filtered_history_players.csv")
filtered_players = player_filter(history_players)

st.session_state["filtered_players"] = filtered_players

st.divider()

col1, col2, col3, col4, col5 = st.columns([1,1,3,1,1])
col1.metric("Rows", len(filtered_players))
col2.metric("Columns", len(filtered_players.columns))
col5.metric("Players", filtered_players["player"].nunique())

st.dataframe(
    filtered_players,
    use_container_width=True,
    hide_index=True
)

# Case of exit: multiple players selected
if filtered_players["player"].nunique() != 1:
    st.stop()
# Case of statistics absent
if filtered_players.shape[0] == 1 and filtered_players["season"].iloc[0] == "2026-27":
    st.stop()

st.divider()
st.subheader("Graphics")

if filtered_players["season"].nunique() == 1 and (st.session_state["season_widget_key"] or st.session_state["team_widget_key"]):
    st.warning("You have selected 1 specific season or a specific team: deselect it to see the statistics accross years.")

plot_player_history(filtered_players)