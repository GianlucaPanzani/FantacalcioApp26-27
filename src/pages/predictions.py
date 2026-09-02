import time
import streamlit as st
import pandas as pd
import lib.ollama_api as llm
from lib.utils import (
    interest_markers,
    set_format_interest,
    get_ai_icon
)
from lib.streamlit_api import (
    thick_divider,
    highlight_bought_rows,
    sync_filter,
    apply_filters,
    load_dataset,
    load_models,
    print_models_predictions,
    get_role_limits,
    get_role_budget_limits,
    get_default_value,
    get_condition_by,
    set_text_size,
    load_env,
    load_models,
    store_env,
    restore_bought_players,
)


st.set_page_config(
    page_title="AI predictions",
    page_icon=get_ai_icon(),
    layout="wide",
)

page_name = "predictions"

columns_to_filter_list = [
    "player",
    "team",
    "fanta_role",
]

compare_op_for_columns_to_filter_dict = {
    "player": None,
    "team": "eq",
    "fanta_role": "eq",
}

enable_player_preferences_key = f"{page_name}_enable_player_preferences_key"


# =============================================================================
# ============================== FUNCTIONS ====================================
# =============================================================================

def player_filters(fanta_players: pd.DataFrame, columns_list: list) -> pd.DataFrame:

    # Initialize default filter values
    for col in columns_list:
        key = f"{page_name}_{col}_key"
        fantacalcio_keys_set.add(key)
        st.session_state.setdefault(key, get_default_value(fanta_players[col]))

    # Create widgets
    filtered_df = fanta_players.copy()
    for i, column  in enumerate(columns_list):

        # Apply previous selections before generating widget options.
        options_df = apply_filters(
            fanta_players,
            columns_to_filter_list=columns_list,
            compare_op_for_columns_to_filter_dict=compare_op_for_columns_to_filter_dict,
            page=page_name
        )
        options = sorted(options_df[column].dropna().astype(str).unique())

        widget_key = f"{page_name}_{column}_widget_key"
        filter_key = f"{page_name}_{column}_key"

        # Build the filtered data and restore widget values after their options change.
        st.session_state[widget_key] = [
            value
            for value in st.session_state[filter_key]
            if value in options
        ]

        selected_values = st.multiselect(
            f"Search {column}",
            options=options,
            placeholder="Select one or more elements...",
            key=widget_key,
            on_change=sync_filter,
            args=(filter_key, widget_key),
        )

        # Apply the value setted in the widget
        if selected_values:
            filtered_df = filtered_df[
                get_condition_by(
                    df=filtered_df,
                    column=column,
                    selected_values=selected_values,
                    compare_op=compare_op_for_columns_to_filter_dict[column],
                )
            ]

    st.divider()
    
    # Store in session_state
    st.session_state[f"{page_name}_filtered_players"] = filtered_df
    return filtered_df


def load_fantamanager_players_of_interest(path: str) -> dict:
    """Load the selected players' preferences from CSV, indexed by player ID."""
    try:
        df = pd.read_csv(path, low_memory=False)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return {}

    required_columns = {"Id", "mln", "interest", "description"}
    if not required_columns.issubset(df.columns):
        return {}

    players_dict = {}
    for _, preference_row in df.drop_duplicates("Id", keep="last").iterrows():
        player_id = preference_row["Id"]
        if pd.isna(player_id):
            continue

        if isinstance(player_id, float) and player_id.is_integer():
            player_id = int(player_id)

        mln_prevision = pd.to_numeric(preference_row["mln"], errors="coerce")
        interest = preference_row["interest"]
        description = preference_row["description"]
        players_dict[str(player_id)] = {
            "mln_prevision": None if pd.isna(mln_prevision) else int(mln_prevision),
            "interest": None if pd.isna(interest) else str(interest),
            "description": None if pd.isna(description) else str(description),
        }

    return players_dict


def create_editor_dataframe(
        filtered_players: pd.DataFrame,
        player_of_interest: dict
    ):
    players_editor_df = filtered_players.copy()
    

    # Create the table
    st.data_editor(
        players_editor_df.style.apply(highlight_bought_rows, axis=1, fanta_managers=fanta_managers),
        hide_index=True,
        width="stretch",
        height=380,
        column_order=column_order,
        disabled=[column for column in players_editor_df.columns if column not in editable_columns],
        column_config=column_config,
        key=editor_key,
        on_change=sync_purchase_editor,
        args=(players_editor_df, fanta_manager_players_dict, fanta_managers, editor_key),
    )

    return

# =============================================================================
# =============================== SCRIPT ======================================
# =============================================================================

# Load stored persistent values before initializing Session State defaults
loaded_env_values = load_env(path=".env")
models_packages_dict = load_models(target_features=["goals_per90", "assists_per90", "minutes"])
feature_explanations = load_dataset("data/features_explainability.csv")

# Set of keys whom value has to be stored (for next loaded)
fantacalcio_keys_set = {
    key
    for key in loaded_env_values
    if key.startswith(f"{page_name}_")
}

# Initialize by default values not available in the environment file
settings_budget_key = "settings_budget_key"
fantacalcio_keys_set.add(settings_budget_key)
st.session_state.setdefault(settings_budget_key, 500)

# Load the optional preferences stored by the Players Selection page
player_of_interest = None
if st.session_state[enable_player_preferences_key]:
    players_of_interest_path = st.session_state.get("selection_selected_players_csv_path_key")
    player_of_interest = pd.DataFrame(load_fantamanager_players_of_interest(players_of_interest_path))


st.title(f"{get_ai_icon()} AI predictions")
st.caption(
    
)

thick_divider()

# Filters
with st.sidebar:
    st.markdown("### Filters")
    filtered_players = player_filters(
        fanta_players=player_of_interest,
        columns_list=["player", "team", "fanta_role"],
    )
    st.markdown("### Reset teams")
    reset_teams_filters(fanta_managers)

# Create editable df
col1, _, col2 = st.columns([52,1,7])
with col1:
    if not st.session_state[enable_player_preferences_key]:
        create_editor_dataframe(filtered_players, player_of_interest)
    else:
        create_editor_dataframe(filtered_players, player_of_interest)
with col2:
    if st.session_state[enable_player_preferences_key]:
        st.markdown("**Interest column symbols meanings**:")
        for key, value in interest_markers.items():
            st.markdown(f"{value} :small[{key}]")

# Case of AI enabled
selected_player = filtered_players.iloc[0]
history_of_the_player = history_players[
    history_players["player"].eq(selected_player["player"])
    & history_players["season"].lt(selected_player["season"])
]
print_models_predictions(
    models_packages_dict=models_packages_dict,
    history_of_the_player=history_of_the_player,
    player_row=filtered_players.iloc[0],
    top_k=4,
    worst_k=2,
    explainability_enabled=st.session_state[show_ai_explainations_key]
)

thick_divider()

# Store persistent Session State values
store_env(
    data_dict={key: st.session_state[key] for key in fantacalcio_keys_list if key in st.session_state},
    path=".env",
)
