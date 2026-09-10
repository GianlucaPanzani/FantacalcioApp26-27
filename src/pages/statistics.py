import math
import streamlit as st
import pandas as pd
from lib.utils import (
    get_default_value,
    highlight_player_role,
    get_background_img_path
)
from lib.streamlit_api import (
    thick_divider,
    bottom_caption,
    set_dark_background,
    set_page_background,
    sync_filter,
    apply_filters,
    get_user_view_of_column,
    load_dataset,
    load_env,
    load_models,
    store_env,
    get_roles_dict,
    plot_comparison_between_players,
    plot_player_history
)
from lib.xgboost_predictor import (
    features_to_predict_list,
    features_to_predict_per_role_dict
)


st.set_page_config(
    page_title="Statistics",
    page_icon="📊",
    layout="wide",
)

page_name = "statistics"

img_path = get_background_img_path(page_name)
set_page_background(img_path)
set_dark_background()

columns_to_filter_list = [
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


def build_statistics_table(players: pd.DataFrame) -> pd.DataFrame:
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


def get_column_width(players: pd.DataFrame, column: str) -> int:
    """Return a readable width based on the column label and its contents."""
    max_content_length = int(players[column].fillna("").astype(str).str.len().max())
    label_length = len(get_user_view_of_column(column))
    return (max(max_content_length, label_length) + 1) * 8


def players_filters(players: pd.DataFrame) -> pd.DataFrame:
    """Display the player filters vertically in the sidebar."""

    st.number_input(
        label="Choose the number of player to inspect",
        value=2,
        max_value=4,
        min_value=1,
        key=number_of_players_key,
    )

    st.number_input(
        label="Choose the number of seasons to plot",
        value=5,
        max_value=10,
        min_value=1,
        key=seasons_to_plot_key,
    )

    multiselect_columns = ["team", "competition"]

    # Initialize multiselect values using the inferred column defaults.
    for column in multiselect_columns:
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
    for column in multiselect_columns:
        col_name_df_dict[column] = apply_filters(
            players,
            exclude=column,
            columns_to_filter_list=columns_to_filter_list,
            compare_op_for_columns_to_filter_dict=compare_op_for_columns_to_filter_dict,
            page=page_name
        )
    
    # Create the multiselect widgets
    for column in multiselect_columns:
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

    slider_columns = ["goals_per90", "nineties"]

    for column in slider_columns:
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

    # Multiple values from the same field are combined through isin (OR).
    filtered_df = apply_filters(
        players,
        columns_to_filter_list=columns_to_filter_list,
        compare_op_for_columns_to_filter_dict=compare_op_for_columns_to_filter_dict,
        page=page_name
    )
    st.session_state[f"{page_name}_filtered_players_key"] = filtered_df
    return filtered_df


def create_dataframe(statistics_table, displayed_table):
    fantacalcio_visible_columns = [col for col in fantacalcio_dataset_columns if col in statistics_table.columns]

    integer_statistics_columns = {"age", "birth_year", "appearances", "starts", "minutes"}
    float_statistics_columns = {col for col in statistics_table.select_dtypes(include="float").columns if col not in integer_statistics_columns}
    statistics_number_formats = {
        **dict.fromkeys(integer_statistics_columns, "%d"),
        **dict.fromkeys(float_statistics_columns, "%.2f"),
    }

    st.dataframe(
        displayed_table.style.apply(
            highlight_player_role,
            axis=1,
            subset=fantacalcio_visible_columns,
        ),
        width="stretch",
        height=650 if displayed_table.shape[0] > 30 else "auto",
        hide_index=False,
        column_config={
            column: (
                st.column_config.NumberColumn(
                    get_user_view_of_column(column),
                    format=statistics_number_formats[column],
                    width=get_column_width(displayed_table, column),
                    alignment="center",
                )
                if column in statistics_number_formats
                else st.column_config.Column(
                    get_user_view_of_column(column),
                    width=get_column_width(displayed_table, column),
                    alignment="center",
                )
            )
            for column in statistics_table.columns
        },
    )
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
filtered_players = history_players.copy()
model_packages_dict = load_models(target_features=features_to_predict_list)

role_widget_key = f"{page_name}_role_key"
number_of_players_key = f"{page_name}_number_of_players_key"
seasons_to_plot_key = f"{page_name}_seasons_to_plot_key"
statistics_keys_set.update({number_of_players_key, seasons_to_plot_key})
st.session_state.setdefault(number_of_players_key, 2)
st.session_state.setdefault(seasons_to_plot_key, 3)

# Filters on the sidebar
with st.sidebar:
    st.markdown("### Filters")
    filtered_players = players_filters(history_players)

st.title("📊 Statistics")
st.caption(
    "Use the sidebar filters to explore the data. Select one player to view their \
    history or two to compare them, including the average values for their roles, \
    that you can see in the graphics as an horizontal row."
)

st.divider()

# Filters per role
selected_role = st.pills(
    "Select fanta role",
    options=get_roles_dict().keys(),
    selection_mode="single",
    key=role_widget_key,
)
if selected_role:
    filtered_players = filtered_players[filtered_players["fanta_role"].eq(selected_role)]

# Select the players before building the union of their graphical columns
n_cols = st.session_state[number_of_players_key]
cols = st.columns(n_cols)
selected_players = []
for i, col in enumerate(cols):
    with col:
        selected_player = st.selectbox(
            f"Search player {i+1}",
            options=sorted(filtered_players["player"].dropna().unique(), key=str),
            index=None,
            placeholder="Select a player...",
            key=f"{page_name}_player_selected_{i+1}_key",
        )
        selected_players.append(selected_player)

# Use the union of the graphical columns configured for the selected roles
columns_to_plot = []
selected_roles = set()
for selected_player in selected_players:
    if selected_player is None:
        continue

    player_history = history_players[history_players["player"].eq(selected_player)].sort_values("season")
    player_roles = player_history["fanta_role"].dropna()
    if player_roles.empty:
        continue

    fanta_role = player_roles.iloc[-1]
    selected_roles.add(fanta_role)
    role_name = get_roles_dict()[fanta_role]
    graphical_columns = st.session_state.get(f"settings_{fanta_role}_graphical_cols_key", [])
    for column in graphical_columns:
        if column in history_players.columns and column not in columns_to_plot:
            columns_to_plot.append(column)

# Show first the columns having an AI prediction for the selected roles
ai_prediction_columns = {
    feature
    for fanta_role in selected_roles
    for feature in features_to_predict_per_role_dict.get(fanta_role, [])
    if feature.endswith("_per90") and feature in model_packages_dict
}
columns_to_plot.sort(key=lambda column: column not in ai_prediction_columns)

# Plot each player below their selectbox
for selected_player, col in zip(selected_players, cols):
    if selected_player is not None:
        with col:
            plot_player_history(
                history_players=history_players,
                player=selected_player,
                columns_to_plot=columns_to_plot,
                seasons_to_plot=st.session_state[seasons_to_plot_key],
                enable_ai_predictions=st.session_state.get("settings_ai_enabled_key", False),
                models_packages_dict=model_packages_dict,
            )


# Create the dataframe
#create_dataframe(statistics_table, displayed_table)

statistics_keys_list = list(statistics_keys_set)
store_env(
    data_dict={key: st.session_state[key] for key in statistics_keys_list if key in st.session_state},
    path=".env",
)

bottom_caption()