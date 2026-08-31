import math
import streamlit as st
import pandas as pd
from lib.utils import (
    get_default_value,
    highlight_player_role,
)
from lib.streamlit_api import (
    thick_divider,
    sync_filter,
    apply_filters,
    get_user_view_of_column,
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

hidden_statistics_columns = [
    "id",
    "normalized_name",
    "RM",
    "mantra_role",
    "Qt.A M",
    "Qt.I M",
    "Diff.M",
    "FVM M",
]

fantacalcio_dataset_columns = [
    "id",
    "fanta_role",
    "mantra_role",
    "player",
    "Squadra",
    "Qt.A",
    "Qt.I",
    "Diff.",
    "Qt.A M",
    "Qt.I M",
    "Diff.M",
    "FVM",
    "FVM M",
]


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


def get_statistics_table(players: pd.DataFrame) -> pd.DataFrame:
    """Put Fantacalcio fields first and remove columns hidden from the table."""
    ordered_columns = [
        column
        for column in fantacalcio_dataset_columns
        if column in players.columns
    ]
    ordered_columns.extend(
        column
        for column in players.columns
        if column not in ordered_columns
    )
    visible_columns = [
        column
        for column in ordered_columns
        if column not in hidden_statistics_columns
    ]
    return players[visible_columns]





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
            f"Select {get_user_view_of_column(column).lower()}",
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
            get_user_view_of_column(column),
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
statistics_keys_set = {
    key
    for key in loaded_env_values
    if key.startswith(f"{page_name}_")
}
history_players = load_dataset("data/filtered_history_players.csv")
with st.sidebar:
    st.markdown("### Filters")
    filtered_players = create_multiselect_filters(history_players)
    filtered_players = create_sliders_filters(filtered_players)


st.title("📊 Statistics")
st.subheader("Players")

# Case of 2 players
if filtered_players["player"].nunique() == 2:
    st.divider()
    plot_comparison_between_players(filtered_players)
elif filtered_players["player"].nunique() == 1:
    st.divider()
    plot_player_history(filtered_players)

st.divider()

statistics_table = get_statistics_table(filtered_players)

cols = st.columns([1,1,1,4,1,1])
with cols[0]:
    st.metric("Rows", len(filtered_players))
with cols[1]:
    st.metric("Columns", len(statistics_table.columns))
with cols[2]:
    st.metric("Total Players", filtered_players["player"].nunique())
with cols[5]:
    rows_per_page = 1000
    total_table_pages = max(0, int(float(statistics_table.shape[0] / rows_per_page))) + 1
    table_page_key = f"{page_name}_table_page_key"
    st.session_state[table_page_key] = min(st.session_state.get(table_page_key, 1), total_table_pages)
    table_page = st.number_input(
        f"Page {st.session_state.get(table_page_key, 1)}/{total_table_pages}",
        min_value=1,
        max_value=total_table_pages,
        key=table_page_key,
    )
    start = (table_page - 1) * rows_per_page
    end = start + rows_per_page
    displayed_table = statistics_table.iloc[start:end]
with cols[4]:
    st.metric("Players in the page", displayed_table.shape[0])

fantacalcio_visible_columns = [
    column
    for column in fantacalcio_dataset_columns
    if column in statistics_table.columns
]

st.dataframe(
    displayed_table.style.apply(
        highlight_player_role,
        axis=1,
        subset=fantacalcio_visible_columns
    ),
    width="stretch",
    hide_index=False,
    column_config={
        column: st.column_config.Column(get_user_view_of_column(column), alignment="center")
        for column in statistics_table.columns
    }
)

statistics_keys_list = list(statistics_keys_set)
store_env(
    data_dict={key: st.session_state[key] for key in statistics_keys_list if key in st.session_state},
    path=".env",
)

#checks_to_stop(filtered_players)


