import streamlit as st
import pandas as pd
from lib.utils import (
    get_default_value,
)
from lib.streamlit_api import (
    columns_to_user_view_dict,
    thick_divider,
    sync_filter,
    apply_filters,
    get_roles_list,
    load_dataset,
    load_env,
    store_env,
    plot_comparison_between_players,
    plot_player_history
)


st.set_page_config(
    page_title="Statistics",
    page_icon="📊",
    layout="wide",
)

page_name = "statistics"

columns_to_filter_list = [
    "player",
    "fanta_role",
    "season",
    "team",
    "competition",
    "goals_per90",
    "nineties",
]

compare_op_for_columns_to_filter_dict = {
    "player": None,
    "fanta_role": "eq",
    "season": "eq",
    "team": "eq",
    "competition": "eq",
    "goals_per90": "geq",
    "nineties": "geq",
}


# =============================================================================
# ============================== FUNCTIONS ====================================
# =============================================================================

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


def create_multiselect_filters(players: pd.DataFrame, columns=["player", "fanta_role", "season", "team", "competition"]) -> pd.DataFrame:
    """Display the player filters vertically in the sidebar."""

    # Initialize multiselect values using the inferred column defaults.
    for column in columns:
        default_value = get_default_value(players[column])
        default_value = default_value if isinstance(default_value, list) else []
        filter_key = f"{page_name}_{column}_key"
        statistics_keys_set.add(filter_key)
        st.session_state.setdefault(filter_key, default_value)

        # Convert values previously stored by selectboxes to lists.
        selected_values = st.session_state[f"{page_name}_{column}_key"]
        if not isinstance(selected_values, list):
            selected_values = [] if selected_values in (None, "") else [selected_values]
            st.session_state[f"{page_name}_{column}_key"] = selected_values

    # Each column receives the DataFrame filtered by all the other fields.
    col_name_df_dict = {}
    for column in columns:
        col_name_df_dict[column] = apply_filters(
            players,
            exclude=column,
            columns_to_filter_list=columns_to_filter_list,
            compare_op_for_columns_to_filter_dict=compare_op_for_columns_to_filter_dict,
            page=page_name
        )

    # Create the multiselect widgets
    for column in columns:
        options = sorted(col_name_df_dict[column][column].dropna().unique(), key=str)
        selected_values = [value for value in st.session_state[f"{page_name}_{column}_key"] if value in options]
        st.session_state[f"{page_name}_{column}_key"] = selected_values
        st.session_state[f"{page_name}_{column}_widget_key"] = selected_values

        st.multiselect(
            f"Select {column.replace('_', ' ')}",
            options=options,
            placeholder=f"Select one or more elements...",
            key=f"{page_name}_{column}_widget_key",
            on_change=sync_filter,
            args=(f"{page_name}_{column}_key", f"{page_name}_{column}_widget_key"),
        )

    # Multiple values from the same field are combined through isin (OR).
    filtered_df = apply_filters(
        players,
        columns_to_filter_list=columns_to_filter_list,
        compare_op_for_columns_to_filter_dict=compare_op_for_columns_to_filter_dict,
        page=page_name
    )
    st.session_state[f"{page_name}_filtered_players_key"] = filtered_df
    return filtered_df


def create_sliders_filters(players: pd.DataFrame, columns=["goals_per90", "nineties"]):
    """Create the statistics sliders dynamically."""

    for column in columns:
        options_df = apply_filters(
            players,
            exclude=column,
            columns_to_filter_list=columns_to_filter_list,
            compare_op_for_columns_to_filter_dict=compare_op_for_columns_to_filter_dict,
            page=page_name
        )
        filter_key = f"{page_name}_{column}_key"
        statistics_keys_set.add(filter_key)
        st.session_state.setdefault(filter_key, get_default_value(players[column]))
        st.session_state[f"{page_name}_{column}_widget_key"] = st.session_state[f"{page_name}_{column}_key"]

        st.slider(
            columns_to_user_view_dict[column],
            min_value=0.0,
            max_value=get_safe_slider_max(options_df, column, f"{page_name}_{column}_key"),
            step=0.01,
            key=f"{page_name}_{column}_widget_key",
            on_change=sync_filter,
            args=(f"{page_name}_{column}_key", f"{page_name}_{column}_widget_key"),
        )

    filtered_df = apply_filters(
        players,
        columns_to_filter_list=columns_to_filter_list,
        compare_op_for_columns_to_filter_dict=compare_op_for_columns_to_filter_dict,
        page=page_name
    )
    st.session_state[f"{page_name}_filtered_players_key"] = filtered_df
    return filtered_df

def checks_to_stop(players: pd.DataFrame):

    # Case of NO statistics: more than 2 players selected
    if players["player"].nunique() > 2:
        st.stop()

    # Case of NO statistics: the current season hasn't stats
    if players.shape[0] == 1 and players["season"].iloc[0] == "2026-27":
        st.stop()

    # Case of NO statistics: one specific season or team selected (no plots possible with this)
    if players["season"].nunique() == 1 and (st.session_state[f"{page_name}_season_widget_key"] or st.session_state[f"{page_name}_team_widget_key"]):
        st.warning("You have selected 1 specific season or a specific team: deselect it to see the statistics accross years.")
        st.stop()
    
    return


# =============================================================================
# =============================== SCRIPT ======================================
# =============================================================================

loaded_env_values = load_env(path=".env")
statistics_keys_set = set(loaded_env_values)
history_players = load_dataset("data/filtered_history_players.csv")
with st.sidebar:
    st.markdown("### Filters")
    filtered_players = create_multiselect_filters(history_players)
    filtered_players = create_sliders_filters(filtered_players)


st.title("📊 Statistics")
st.subheader("Players")

st.divider()

col1, col2, col3, col4, col5 = st.columns([1,1,3,1,1])
col1.metric("Rows", len(filtered_players))
col2.metric("Columns", len(filtered_players.columns))
col5.metric("Players", filtered_players["player"].nunique())

st.dataframe(
    filtered_players,
    width="stretch",
    hide_index=True
)

statistics_keys_list = list(statistics_keys_set)
store_env(
    data_dict={key: st.session_state[key] for key in statistics_keys_list if key in st.session_state},
    path=".env",
)

checks_to_stop(filtered_players)

st.divider()

# Case of 2 players
if filtered_players["player"].nunique() == 2:
    plot_comparison_between_players(filtered_players)
    st.stop()

plot_player_history(filtered_players)
