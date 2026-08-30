from pathlib import Path
import pandas as pd
import streamlit as st
from lib.utils import (
    highlight_player_role,
    set_format_interest_level,
    interest_level_markers
)
from lib.streamlit_api import (
    sync_filter,
    apply_filters,
    get_user_view_of_column,
    load_dataset,
    load_env,
    store_env,
)


st.set_page_config(
    page_title="Players Selection",
    page_icon="🎯",
    layout="wide",
)

page_name = "selection"

columns_to_filter_list = [
    "Nome",
    "R",
    "Squadra",
]

compare_op_for_columns_to_filter_dict = {
    "Nome": None,
    "R": "eq",
    "Squadra": "eq",
}

hidden_selection_columns = [
    "Id",
    "RM",
    "Qt.A M",
    "Qt.I M",
    "Diff.M",
    "FVM",
    "FVM M",
]

interest_level_colors_dict = {
    "Da valutare": "#E0E0E0",
    "Bassissimo": "#FFFFFF",
    "Basso": "#FFF59D",
    "Medio": "#FFCC80",
    "Alto": "#EF9A9A",
    "Scommessa": "#81D4FA",
    "Buoni low cost": "#81FAC8",
}


# =============================================================================
# ============================== FUNCTIONS ====================================
# =============================================================================

def players_filters(players: pd.DataFrame) -> pd.DataFrame:
    """Display the Fantacalcio player filters vertically in the sidebar."""
    # Initilizations of the session_state
    for column in columns_to_filter_list:
        # Add the key to the page's keys
        filter_key = f"{page_name}_{column}_key"
        selection_keys_set.add(filter_key)
        st.session_state.setdefault(filter_key, [])

        # Check if it is None or empty string to initialize it to empty list
        selected_values_of_column = st.session_state[f"{page_name}_{column}_key"]
        if selected_values_of_column in [None, ""]:
            st.session_state[f"{page_name}_{column}_key"] = []

    # Apply the filters
    column_df_dict = {}
    for column in columns_to_filter_list:
        column_df_dict[column] = apply_filters(
            players,
            exclude=column,
            columns_to_filter_list=columns_to_filter_list,
            compare_op_for_columns_to_filter_dict=compare_op_for_columns_to_filter_dict,
            page=page_name
        )

    # Create the multiselection filters
    for column in columns_to_filter_list:
        options = sorted(column_df_dict[column][column].dropna().unique(), key=str)
        selected_values = [value for value in st.session_state[f"{page_name}_{column}_key"] if value in options]
        st.session_state[f"{page_name}_{column}_key"] = selected_values
        st.session_state[f"{page_name}_{column}_widget_key"] = selected_values

        st.multiselect(
            f"Select {get_user_view_of_column(column).lower()}",
            options=options,
            placeholder="Select one or more elements...",
            key=f"{page_name}_{column}_widget_key",
            on_change=sync_filter,
            args=(f"{page_name}_{column}_key", f"{page_name}_{column}_widget_key"),
        )
    
    st.divider()

    # Filter the df based on the selections
    filtered_players = apply_filters(
        players,
        columns_to_filter_list=columns_to_filter_list,
        compare_op_for_columns_to_filter_dict=compare_op_for_columns_to_filter_dict,
        page=page_name
    )
    st.session_state[f"{page_name}_filtered_selection_players_key"] = filtered_players
    return filtered_players


def get_stats_player_key(field: str, player_id) -> str:
    """Return the persistent Session State key for one player field."""
    return f"{page_name}_{field}_{player_id}_key"


def update_player_selections(player_ids: tuple, editor_key: str) -> None:
    """Synchronize checkbox edits with the persistent player state."""
    edited_rows = st.session_state[editor_key]["edited_rows"]
    for row_position, changes in edited_rows.items():
        if "selected" in changes:
            player_id = player_ids[int(row_position)]
            st.session_state[get_stats_player_key("selected", player_id)] = bool(changes["selected"])


def remove_selected_player(player_ids: tuple, button_key: str) -> None:
    """Remove the player associated with the clicked table button."""
    click = st.session_state.get(button_key)
    if click is None:
        return

    player_id = player_ids[click["row"]]
    st.session_state[get_stats_player_key("selected", player_id)] = False


def load_selected_players(path: str) -> None:
    """Restore selected players and their editable fields from a CSV file."""
    try:
        selection_players = pd.read_csv(path, low_memory=False)
    except pd.errors.EmptyDataError:
        return

    for _, player_row in selection_players.iterrows():
        player_id = player_row["Id"]
        if pd.isna(player_id):
            continue
        if isinstance(player_id, float) and player_id.is_integer():
            player_id = int(player_id)

        mln_value = pd.to_numeric(player_row["mln"], errors="coerce")
        interest_level = player_row["interest_level"]
        description = player_row["description"]

        if interest_level not in interest_level_colors_dict:
            interest_level = "Da valutare"

        st.session_state[get_stats_player_key("selected", player_id)] = True
        st.session_state[get_stats_player_key("mln", player_id)] = 0 if pd.isna(mln_value) else int(mln_value)
        st.session_state[get_stats_player_key("interest_level", player_id)] = interest_level
        st.session_state[get_stats_player_key("description", player_id)] = "" if pd.isna(description) else str(description)

    return


def store_selected_players(players: pd.DataFrame, path: str) -> None:
    """Overwrite the CSV file with the currently selected players."""
    selection_players = []

    for player_id in players["Id"]:
        selected_key = get_stats_player_key("selected", player_id)

        # Case of non-selected player
        if not st.session_state.get(selected_key, False):
            continue
        
        # Creation of the keys
        mln_key = get_stats_player_key("mln", player_id)
        interest_level_key = get_stats_player_key("interest_level", player_id)
        description_key = get_stats_player_key("description", player_id)

        # Append of the new row to store
        selection_players.append(
            {
                "Id": player_id,
                "mln": st.session_state.get(mln_key, 0),
                "interest_level": st.session_state.get(interest_level_key, "Da valutare"),
                "description": st.session_state.get(description_key, ""),
            }
        )

    # Write into the file
    selection_players_df = pd.DataFrame(
        selection_players,
        columns=["Id", "mln", "interest_level", "description"],
    )
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    selection_players_df.to_csv(csv_path, index=False)
    return


def get_selection_column_config(columns: list[str]) -> dict:
    """Create readable Streamlit column configurations for selection tables."""
    column_config = {
        column: st.column_config.Column(
            get_user_view_of_column(column),
            alignment="center",
        )
        for column in columns
    }

    if "selected" in columns:
        column_config["selected"] = st.column_config.CheckboxColumn(
            get_user_view_of_column("selected"),
            help="Add or remove this player from your selection.",
            default=False,
            pinned=True,
        )
    if "mln" in columns:
        column_config["mln"] = st.column_config.NumberColumn(
            get_user_view_of_column("mln"),
            help="Maximum number of credits you would spend for this player.",
            min_value=0,
            step=1,
            format="%d",
            required=True,
        )
    if "interest_level" in columns:
        column_config["interest_level"] = st.column_config.SelectboxColumn(
            get_user_view_of_column("interest_level"),
            help="Choose your current interest level for this player.",
            options=list(interest_level_colors_dict),
            format_func=set_format_interest_level,
            default="Da valutare",
            required=True,
        )
    if "description" in columns:
        column_config["description"] = st.column_config.TextColumn(
            get_user_view_of_column("description"),
            help="Write a short note about this player.",
            default="",
            width="large",
        )

    return column_config


def create_player_selection_table(players: pd.DataFrame, visible_columns: list[str]) -> None:
    """Display the filtered Fantacalcio players with persistent checkboxes."""
    players_editor_df = players.set_index("Id")[visible_columns].copy()

    selected_values = []
    for player_id in players_editor_df.index:
        selected_key = get_stats_player_key("selected", player_id)
        st.session_state.setdefault(selected_key, False)
        selected_values.append(bool(st.session_state[selected_key]))

    players_editor_df.insert(0, "selected", selected_values)
    column_order = ["selected"] + visible_columns
    column_config = get_selection_column_config(column_order)
    editor_data = players_editor_df.style.apply(
        highlight_player_role,
        axis=1,
        subset=visible_columns,
    )

    editor_key = f"{page_name}_players_selection_editor_key"
    st.data_editor(
        editor_data,
        hide_index=True,
        width="stretch",
        height=450,
        column_order=column_order,
        disabled=visible_columns,
        column_config=column_config,
        key=editor_key,
        on_change=update_player_selections,
        args=(tuple(players_editor_df.index), editor_key),
    )


def create_selected_players_table(players: pd.DataFrame, visible_columns: list[str]) -> None:
    """Display and edit the persistent shortlist of selected players."""
    selected_player_ids = []
    for player_id in players["Id"]:
        selected_key = get_stats_player_key("selected", player_id)
        if st.session_state.get(selected_key, False):
            selected_player_ids.append(player_id)

    if not selected_player_ids:
        return

    selected_players_editor_df = players[players["Id"].isin(selected_player_ids)]
    selected_players_editor_df = selected_players_editor_df.set_index("Id")[visible_columns].copy()

    mln_values = []
    interest_level_values = []
    description_values = []

    for player_id in selected_players_editor_df.index:
        selected_key = get_stats_player_key("selected", player_id)
        mln_key = get_stats_player_key("mln", player_id)
        interest_level_key = get_stats_player_key("interest_level", player_id)
        description_key = get_stats_player_key("description", player_id)

        st.session_state.setdefault(selected_key, True)
        st.session_state.setdefault(mln_key, 0)
        st.session_state.setdefault(interest_level_key, "Da valutare")
        st.session_state.setdefault(description_key, "")

        mln_value = pd.to_numeric(st.session_state[mln_key], errors="coerce")
        mln_value = 0 if pd.isna(mln_value) else int(mln_value)
        interest_level = st.session_state[interest_level_key]
        if interest_level not in interest_level_colors_dict:
            interest_level = "Da valutare"
        description = st.session_state[description_key]
        description = "" if pd.isna(description) else str(description)

        st.session_state[mln_key] = mln_value
        st.session_state[interest_level_key] = interest_level
        st.session_state[description_key] = description

        mln_values.append(mln_value)
        interest_level_values.append(interest_level)
        description_values.append(description)

    selected_players_editor_df.insert(0, "description", description_values)
    selected_players_editor_df.insert(0, "interest_level", interest_level_values)
    selected_players_editor_df.insert(0, "mln", mln_values)
    selected_players_editor_df.insert(0, "remove", ":material/delete:")

    editable_columns = ["remove", "mln", "interest_level", "description"]
    column_order = editable_columns + visible_columns
    column_config = get_selection_column_config(column_order)
    remove_button_key = f"{page_name}_remove_player_button_key"
    column_config["remove"] = st.column_config.ButtonColumn(
        "",
        help="Remove this player from your selection.",
        pinned=True,
        type="tertiary",
        on_click=remove_selected_player,
        args=(tuple(selected_players_editor_df.index), remove_button_key),
        key=remove_button_key,
    )
    editor_data = selected_players_editor_df.style.apply(
        highlight_player_role,
        axis=1,
        subset=visible_columns,
    )

    st.divider()
    st.subheader("Selected players")
    edited_selected_players = st.data_editor(
        editor_data,
        hide_index=True,
        width="stretch",
        height=450,
        column_order=column_order,
        disabled=visible_columns,
        column_config=column_config,
        key=f"{page_name}_selected_players_editor_key",
    )

    for player_id, player_row in edited_selected_players.iterrows():
        mln_key = get_stats_player_key("mln", player_id)
        interest_level_key = get_stats_player_key("interest_level", player_id)
        description_key = get_stats_player_key("description", player_id)

        interest_level = player_row["interest_level"]
        if interest_level not in interest_level_colors_dict:
            interest_level = "Da valutare"

        description = player_row["description"]
        description = "" if pd.isna(description) else str(description)
        mln_value = pd.to_numeric(player_row["mln"], errors="coerce")

        st.session_state[mln_key] = 0 if pd.isna(mln_value) else int(mln_value)
        st.session_state[interest_level_key] = interest_level
        st.session_state[description_key] = description


# =============================================================================
# =============================== SCRIPT ======================================
# =============================================================================

fanta_players = load_dataset("data/Listone_Fantacalcio_Stagione_2026_27.csv")
loaded_env_values = load_env(path=".env")
selection_keys_set = {key for key in loaded_env_values if key.startswith(f"{page_name}_")}

# Save the path to the csv file with selected players
selection_players_key = f"{page_name}_selected_players_csv_path_key"
st.session_state.setdefault(selection_players_key, "data/selection_players.csv")
selection_keys_set.add(selection_players_key)

# Load the selected players 
selection_restored_key = f"{page_name}_selection_players_restored_key"
if not st.session_state.get(selection_restored_key, False):
    load_selected_players(st.session_state[selection_players_key])
    st.session_state[selection_restored_key] = True

# Create filters on the sidebar
with st.sidebar:
    st.markdown("### Filters")
    filtered_players = players_filters(fanta_players)


st.title(":material/group_add: Players Selection")
st.subheader("Fantacalcio players")

st.divider()

# Filter the visible columns
visible_selection_columns = [column for column in filtered_players.columns if column not in hidden_selection_columns]

# Metrics
col1, col2, col3, col4 = st.columns([1,1,4,1])
with col1:
    st.metric("Rows", len(filtered_players))
with col2:
    st.metric("Columns", len(visible_selection_columns) + 1)
with col4:
    st.metric("Players", filtered_players["Nome"].nunique())

# Create the full table
create_player_selection_table(filtered_players, visible_selection_columns)

# Create the selection table
create_selected_players_table(fanta_players, visible_selection_columns)

# Store the selected players in a csv file
store_selected_players(fanta_players, st.session_state[selection_players_key])

selection_keys_list = list(selection_keys_set)
store_env(
    data_dict={
        key: st.session_state[key]
        for key in selection_keys_list
        if key in st.session_state
    },
    path=".env",
)
