import pandas as pd
import streamlit as st


def config_page(page_title="Football Dataset Explorer", page_icon="⚽", layout="wide", initial_sidebar_state="expanded"):
    st.set_page_config(
        page_title=page_title,
        page_icon=page_icon,
        layout=layout,
        initial_sidebar_state=initial_sidebar_state,
    )

def get_from_session_state(key: str):
    if key in st.session_state:
        return st.session_state[key]
    return None

@st.cache_data(show_spinner=False)
def load_dataset(path: str, filter_by_current_year: bool = False, current_season: str = "2026-27") -> pd.DataFrame:
    """Load and cache a players dataset."""
    df = pd.read_csv(path, low_memory=False)
    return df.loc[df["season"].eq(current_season)].copy() if filter_by_current_year else df

def sync_filter(filter_key: str, widget_key: str) -> None:
    """Copy a widget value into its persistent filter state."""
    st.session_state[filter_key] = st.session_state.get(widget_key)

def plot_player_history(filtered_players: pd.DataFrame) -> None:
    """
    Display selectable historical statistics for a single player.

    Each chart represents the evolution of one statistic across seasons.
    Charts are arranged alternately in two columns.

    Parameters
    ----------
    filtered_players:
        DataFrame containing the historical records of one player.
    """

    chart_fields = {
        # General statistics
        "age": "Age",
        "appearances": "Appearances",
        "starts": "Starts",
        "minutes": "Minutes",
        "nineties": "90-minute periods",

        # Attacking statistics
        "goals_per90": "Goals per 90",
        "assists_per90": "Assists per 90",
        "goals_assists_per90": "Goals + assists per 90",
        "non_penalty_goals_per90": "Non-penalty goals per 90",
        "non_penalty_goals_assists_per90": "Non-penalty goals + assists per 90",
        "penalty_attempts_per90": "Penalty attempts per 90",
        "shots_on_target_pct": "Shots on target %",
        "shots_per90": "Shots per 90",
        "shots_on_target_per90": "Shots on target per 90",
        "goals_per_shot": "Goals per shot",
        "goals_per_shot_on_target": "Goals per shot on target",

        # Defensive statistics
        "interceptions_per90": "Interceptions per 90",
        "tackles_won_per90": "Tackles won per 90",
        "yellow_cards_per90": "Yellow cards per 90",
        "red_cards_per90": "Red cards per 90",

        # Goalkeeper statistics
        "goals_against_per90": "Goals against per 90",
        "shots_on_target_against_per90": "Shots on target against per 90",
        "saves_per90": "Saves per 90",
        "save_pct": "Save percentage",
        "wins_per90": "Wins per 90",
        "draws_per90": "Draws per 90",
        "losses_per90": "Losses per 90",
        "clean_sheets_per90": "Clean sheets per 90",
        "clean_sheet_pct": "Clean sheet percentage",
        "keeper_penalty_attempts_per90": "Penalties faced per 90",
        "penalties_allowed_per90": "Penalties allowed per 90",
        "penalties_saved_per90": "Penalties saved per 90",
        "penalties_missed_per90": "Penalties missed per 90",
    }

    # Remove fields not present in the current dataset.
    available_fields = {
        field: label
        for field, label in chart_fields.items()
        if field in filtered_players.columns
    }

    # Fields selection
    selected_fields = st.multiselect(
        "Select statistics",
        options=list(available_fields),
        default=[
            field for field in [
                "appearances",
                "minutes",
                "goals_per90",
                "assists_per90",
            ] if field in available_fields
        ],
        format_func=lambda field: available_fields[field],
    )

    # Case of no fields selected
    if not selected_fields:
        st.info("Select at least one statistic.")
        return

    # Convert selected statistics to numeric values.
    chart_df = filtered_players.copy()
    chart_df = chart_df.sort_values("season")
    for field in selected_fields:
        chart_df[field] = pd.to_numeric(chart_df[field], errors="coerce")

    # Create the graphics in selected_fields in 2 columns
    col1, col2 = st.columns(2)
    for index, field in enumerate(selected_fields):
        container = col1 if index % 2 == 0 else col2
        data = chart_df[["season", field]].dropna()

        with container:
            st.markdown(
                f"<h4 style='text-align: center;'>{available_fields[field]}</h4>",
                unsafe_allow_html=True
            )

            st.line_chart(
                data,
                x="season",
                y=field,
                x_label="Season",
                y_label=available_fields[field],
                use_container_width=True,
            )