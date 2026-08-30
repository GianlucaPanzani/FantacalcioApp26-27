from numbers import Real
import streamlit as st
import pandas as pd
from lib.utils import (
    get_default_value,
    get_condition_by,
    get_color_per_role,
    stats_interest_level_colors_dict,
)
from lib.streamlit_api import (
    persistent_session_keys,
    columns_to_user_view_dict,
    sync_filter,
    get_user_view_of_column,
    get_stats_persistent_keys,
    load_dataset,
    load_env,
    store_env,
    plot_comparison_between_players,
    plot_player_history
)


st.set_page_config(
    page_title="Select Players",
    page_icon="📊",
    layout="wide",
)


columns_to_filter_list = [
    "player",
    "R",
    "team",
    "competition",
    "goals_per90",
    "nineties",
]

hidden_statistics_columns = [
    "Id",
    "Diff.",
    "Diff.M",
]


# =============================================================================
# ============================== FUNCTIONS ====================================
# =============================================================================

def apply_filters(df: pd.DataFrame, exclude=None) -> pd.DataFrame:
    """Apply session-state filters, excluding one filter when requested."""
    result = df.copy()

    for column in columns_to_filter_list:
        selected_values = st.session_state.get(f"{column}_key", get_default_value(result[column]))
        if exclude == column or not selected_values:
            continue
        result = result[
            get_condition_by(result, column, selected_values, compare_op_for_columns_to_filter_dict[column])
        ]

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


def create_multiselect_filters(players: pd.DataFrame, columns=["player", "fanta_role", "season", "team", "competition"]) -> pd.DataFrame:
    """Display the player filters vertically in the sidebar."""

    # Initialize multiselect values using the inferred column defaults.
    for column in columns:
        default_value = get_default_value(players[column])
        default_value = default_value if isinstance(default_value, list) else []
        st.session_state.setdefault(f"{column}_key", default_value)

        # Convert values previously stored by selectboxes to lists.
        selected_values = st.session_state[f"{column}_key"]
        if not isinstance(selected_values, list):
            selected_values = [] if selected_values in (None, "") else [selected_values]
            st.session_state[f"{column}_key"] = selected_values

    # Each column receives the DataFrame filtered by all the other fields.
    col_name_df_dict = {}
    for column in columns:
        col_name_df_dict[column] = apply_filters(players, exclude=column)

    # Create the multiselect widgets
    for column in columns:
        options = sorted(col_name_df_dict[column][column].dropna().unique(), key=str)
        selected_values = [value for value in st.session_state[f"{column}_key"] if value in options]
        st.session_state[f"{column}_key"] = selected_values
        st.session_state[f"{column}_widget_key"] = selected_values

        st.multiselect(
            f"Select {column.replace('_', ' ')}",
            options=options,
            placeholder=f"Select one or more elements...",
            key=f"{column}_widget_key",
            on_change=sync_filter,
            args=(f"{column}_key", f"{column}_widget_key"),
        )

    # Multiple values from the same field are combined through isin (OR).
    filtered_df = apply_filters(players)
    st.session_state["filtered_players"] = filtered_df
    return filtered_df


def create_sliders_filters(players: pd.DataFrame, columns=["goals_per90", "nineties"]):
    """Create the statistics sliders dynamically."""

    for column in columns:
        options_df = apply_filters(players, exclude=column)
        st.session_state.setdefault(f"{column}_key", get_default_value(players[column]))
        st.session_state[f"{column}_widget_key"] = st.session_state[f"{column}_key"]

        st.slider(
            columns_to_user_view_dict[column],
            min_value=0.0,
            max_value=get_safe_slider_max(options_df, column, f"{column}_key"),
            step=0.01,
            key=f"{column}_widget_key",
            on_change=sync_filter,
            args=(f"{column}_key", f"{column}_widget_key"),
        )

    filtered_df = apply_filters(players)
    st.session_state["filtered_players"] = filtered_df
    return filtered_df


def get_stats_player_key(field: str, player_id) -> str:
    """Return the persistent Session State key for one player field."""
    return f"stats_{field}_{player_id}_key"


def get_latest_player_rows(players: pd.DataFrame) -> pd.DataFrame:
    """Return the most recent available row for every player ID."""
    latest_players = players.copy()

    if latest_players.empty:
        return latest_players

    latest_players["season"] = latest_players["season"].fillna("").astype(str)
    latest_players = latest_players.sort_values(["season", "player"])
    latest_players = latest_players.drop_duplicates(subset="id", keep="last")
    return latest_players.sort_values("player").reset_index(drop=True)


def get_visible_statistics_columns(players: pd.DataFrame) -> list[str]:
    """Return the statistics columns that should be visible to the user."""
    return [column for column in players.columns if column not in hidden_statistics_columns]


def highlight_stats_role(row: pd.Series) -> list[str]:
    """Apply the Fantacalcio role color to every visible statistic cell."""
    role_color = get_color_per_role(row.get("fanta_role", ""))
    if not role_color:
        return [""] * len(row)
    return [f"background-color: {role_color}; color: #212121"] * len(row)


def get_statistics_column_config(columns: list[str]) -> dict:
    """Create readable Streamlit column configurations for statistics tables."""
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
            options=list(stats_interest_level_colors_dict),
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
    """Display the filtered players with one persistent checkbox per player."""
    players_editor_df = players.set_index("id")[visible_columns].copy()

    selected_values = []
    for player_id in players_editor_df.index:
        selected_key = get_stats_player_key("selected", player_id)
        st.session_state.setdefault(selected_key, False)
        selected_values.append(bool(st.session_state[selected_key]))

    players_editor_df.insert(0, "selected", selected_values)
    column_order = ["selected"] + visible_columns
    column_config = get_statistics_column_config(column_order)
    editor_data = players_editor_df.style.apply(
        highlight_stats_role,
        axis=1,
        subset=visible_columns,
    )

    edited_players = st.data_editor(
        editor_data,
        hide_index=True,
        width="stretch",
        height=450,
        column_order=column_order,
        disabled=visible_columns,
        column_config=column_config,
        key="stats_players_selection_editor_key",
    )

    for player_id, selected_value in edited_players["selected"].items():
        selected_key = get_stats_player_key("selected", player_id)
        st.session_state[selected_key] = bool(selected_value)


def create_selected_players_table(players: pd.DataFrame, visible_columns: list[str]) -> None:
    """Display and edit the persistent shortlist of selected players."""
    selected_player_ids = []
    for player_id in players["id"].dropna().drop_duplicates():
        selected_key = get_stats_player_key("selected", player_id)
        if st.session_state.get(selected_key, False):
            selected_player_ids.append(player_id)

    if not selected_player_ids:
        return

    selected_players = players[players["id"].isin(selected_player_ids)]
    selected_players = get_latest_player_rows(selected_players)
    selected_players_editor_df = selected_players.set_index("id")[visible_columns].copy()

    selected_values = []
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
        if interest_level not in stats_interest_level_colors_dict:
            interest_level = "Da valutare"
        description = st.session_state[description_key]
        description = "" if pd.isna(description) else str(description)

        st.session_state[mln_key] = mln_value
        st.session_state[interest_level_key] = interest_level
        st.session_state[description_key] = description

        selected_values.append(bool(st.session_state[selected_key]))
        mln_values.append(mln_value)
        interest_level_values.append(interest_level)
        description_values.append(description)

    selected_players_editor_df.insert(0, "description", description_values)
    selected_players_editor_df.insert(0, "interest_level", interest_level_values)
    selected_players_editor_df.insert(0, "mln", mln_values)
    selected_players_editor_df.insert(0, "selected", selected_values)

    editable_columns = ["selected", "mln", "interest_level", "description"]
    column_order = editable_columns + visible_columns
    column_config = get_statistics_column_config(column_order)
    editor_data = selected_players_editor_df.style.apply(
        highlight_stats_role,
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
        key="stats_selected_players_editor_key",
    )

    for player_id, player_row in edited_selected_players.iterrows():
        selected_key = get_stats_player_key("selected", player_id)
        mln_key = get_stats_player_key("mln", player_id)
        interest_level_key = get_stats_player_key("interest_level", player_id)
        description_key = get_stats_player_key("description", player_id)

        interest_level = player_row["interest_level"]
        if interest_level not in stats_interest_level_colors_dict:
            interest_level = "Da valutare"

        description = player_row["description"]
        description = "" if pd.isna(description) else str(description)

        st.session_state[selected_key] = bool(player_row["selected"])
        mln_value = pd.to_numeric(player_row["mln"], errors="coerce")
        st.session_state[mln_key] = 0 if pd.isna(mln_value) else int(mln_value)
        st.session_state[interest_level_key] = interest_level
        st.session_state[description_key] = description

def checks_to_stop(players: pd.DataFrame):

    # Case of NO statistics: more than 2 players selected
    if players["player"].nunique() > 2:
        st.stop()

    # Case of NO statistics: the current season hasn't stats
    if players.shape[0] == 1 and players["season"].iloc[0] == "2026-27":
        st.stop()

    # Case of NO statistics: one specific season or team selected (no plots possible with this)
    if players["season"].nunique() == 1 and (st.session_state["season_widget_key"] or st.session_state["team_widget_key"]):
        st.warning("You have selected 1 specific season or a specific team: deselect it to see the statistics accross years.")
        st.stop()
    
    return


# =============================================================================
# =============================== SCRIPT ======================================
# =============================================================================

fanta_players = load_dataset("data/Listone_Fantacalcio_Stagione_2026_27.csv")

stats_persistent_keys = get_stats_persistent_keys(fanta_players["id"])
all_persistent_session_keys = persistent_session_keys + stats_persistent_keys
load_env(keys=all_persistent_session_keys, path=".env")

with st.sidebar:
    st.markdown("### Filters")
    filtered_players = create_multiselect_filters(fanta_players)
    filtered_players = create_sliders_filters(filtered_players)


st.title("📊 Statistics")
st.subheader("Players")

st.divider()

col1, col2, col3, col4, col5 = st.columns([1,1,3,1,1])
latest_filtered_players = get_latest_player_rows(filtered_players)
visible_statistics_columns = get_visible_statistics_columns(latest_filtered_players)

col1.metric("Rows", len(latest_filtered_players))
col2.metric("Columns", len(visible_statistics_columns) + 1)
col5.metric("Players", latest_filtered_players["player"].nunique())

create_player_selection_table(latest_filtered_players, visible_statistics_columns)
create_selected_players_table(fanta_players, visible_statistics_columns)

store_env(
    data_dict={
        key: st.session_state[key]
        for key in all_persistent_session_keys
        if key in st.session_state
    },
    path=".env",
)

checks_to_stop(filtered_players)

st.divider()

# Case of 2 players
if filtered_players["player"].nunique() == 2:
    plot_comparison_between_players(filtered_players)
    st.stop()

plot_player_history(filtered_players)
