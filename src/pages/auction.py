import streamlit as st
import pandas as pd
from lib.xgboost_predictor import (
    features_to_predict_list
)
from lib.utils import (
    interest_colors_dict,
    get_current_year,
)
from lib.streamlit_api.data_handler import (
    load_dataset,
    load_models,
    sync_filter,
    get_roles_dict,
    load_env,
    store_env,
    restore_bought_players,
    has_full_team,
    save_bought_players,
)
from lib.streamlit_api.design_handler import (
    bottom_caption,
    get_background_img_path,
    get_emoji,
    get_icon,
    highlight_interest,
    set_page_background,
    set_dark_background,
)
from lib.streamlit_api.visualization_handler import (
    highlight_bought_rows,
    print_models_predictions,
    create_horizontal_teams,
    create_vertical_teams,
)

page_name = "auction"

st.set_page_config(
    page_title="Auction 26-27",
    page_icon=get_emoji(page_name),
    layout="wide",
)

img_path = get_background_img_path(page_name)
set_page_background(img_path)
set_dark_background()

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

fanta_manager_split_value_key = f"{page_name}_fanta_managers_split_value"
fanta_manager_split_value_widget_key = f"{page_name}_fanta_managers_split_value_widget"
enable_bought_players_stats_key = f"{page_name}_bought_players_stats_key"
enable_player_preferences_key = f"{page_name}_enable_player_preferences_key"
reset_managers_widget_key = f"{page_name}_reset_managers_widget_key"
reset_boughts_button_key = f"{page_name}_reset_boughts_button_key"
reset_bought_message_key = f"{page_name}_reset_boughts_message_key"
show_ai_predictions_key = f"{page_name}_show_ai_predictions_key"
show_ai_explainations_key = f"{page_name}_show_ai_explainations_key"
show_ai_plots_key = f"{page_name}_show_ai_plots_key"
hide_other_fantamanagers_key = f"{page_name}_hide_other_fantamanagers_key"

bought_player_columns = ["id", "player", "team", "role", "mantra_role", "manager", "mln"]


# =============================================================================
# ============================== FUNCTIONS ====================================
# =============================================================================

def request_auction_start() -> None:
    """Record the host request to start the auction."""
    st.session_state["auction_start_requested_key"] = True


def player_filters(fanta_players: pd.DataFrame) -> pd.DataFrame:
    """Render auction filters and return the matching players.

    Params
    ----------
    fanta_players : pandas.DataFrame
        Current-season players available to the auction page.

    Returns
    -------
    pandas.DataFrame
        Players matching the selected role, manager, player and team filters.
    """
    filtered_df = fanta_players.copy()

    # Role filter
    role_filter_key = f"{page_name}_fanta_role_key"
    role_widget_key = f"{page_name}_fanta_role_widget_key"
    auction_keys_set.add(role_filter_key)
    st.session_state.setdefault(role_filter_key, None)
    role_options = get_roles_dict().keys()
    st.session_state[role_widget_key] = (
        st.session_state[role_filter_key]
        if st.session_state[role_filter_key] in role_options
        else None
    )
    selected_role = st.pills(
        "Select fanta role",
        options=role_options,
        selection_mode="single",
        key=role_widget_key,
        on_change=sync_filter,
        args=(role_filter_key, role_widget_key),
    )
    if selected_role:
        filtered_df = filtered_df[filtered_df["fanta_role"].eq(selected_role)]

    # Fanta Manager filter
    manager_filter_key = f"{page_name}_selected_manager_key"
    manager_widget_key = f"{page_name}_selected_manager_widget_key"
    auction_keys_set.add(manager_filter_key)
    st.session_state.setdefault(manager_filter_key, None)
    manager_options = ["Free"] + st.session_state.get("settings_managers_key", [])
    st.session_state[manager_widget_key] = (
        st.session_state[manager_filter_key]
        if st.session_state[manager_filter_key] in manager_options
        else None
    )
    selected_fanta_manager = st.pills(
        "Select a Fanta Manager",
        options=manager_options,
        selection_mode="single",
        key=manager_widget_key,
        on_change=sync_filter,
        args=(manager_filter_key, manager_widget_key),
    )

    # Player filter
    player_filter_key = f"{page_name}_player_key"
    player_widget_key = f"{page_name}_player_widget_key"
    auction_keys_set.add(player_filter_key)
    st.session_state.setdefault(player_filter_key, None)
    selected_player = st.session_state[player_filter_key]
    player_options = sorted(fanta_players["player"].dropna().astype(str).unique())
    st.session_state[player_widget_key] = selected_player if selected_player in player_options else None
    selected_player = st.selectbox(
        "Search a player",
        options=player_options,
        index=None,
        placeholder="Select a player...",
        key=player_widget_key,
        on_change=sync_filter,
        args=(player_filter_key, player_widget_key),
    )
    if selected_player:
        filtered_df = filtered_df[filtered_df["player"].eq(selected_player)]

    # Team filter
    team_filter_key = f"{page_name}_team_key"
    team_widget_key = f"{page_name}_team_widget_key"
    auction_keys_set.add(team_filter_key)
    st.session_state.setdefault(team_filter_key, None)
    team_options = sorted(fanta_players["team"].dropna().astype(str).unique())
    st.session_state[team_widget_key] = (
        st.session_state[team_filter_key]
        if st.session_state[team_filter_key] in team_options
        else None
    )
    selected_team = st.selectbox(
        "Select a team",
        options=team_options,
        index=None,
        placeholder="Select a team...",
        key=team_widget_key,
        on_change=sync_filter,
        args=(team_filter_key, team_widget_key),
    )
    if selected_team:
        filtered_df = filtered_df[filtered_df["team"].eq(selected_team)]

    # Handle cases of free players and not
    fanta_manager_players_dict = st.session_state[f"{page_name}_manager_players_dict_key"]
    if selected_fanta_manager == "Free":
        bought_player_ids = set()
        for bought_players in fanta_manager_players_dict.values():
            if isinstance(bought_players, pd.DataFrame) and "id" in bought_players.columns:
                bought_player_ids.update(bought_players["id"].dropna().astype(str))
        filtered_df = filtered_df[~filtered_df["id"].astype(str).isin(bought_player_ids)]
    elif selected_fanta_manager:
        bought_players = fanta_manager_players_dict.get(selected_fanta_manager, pd.DataFrame())
        bought_player_ids = (
            set(bought_players["id"].dropna().astype(str))
            if "id" in bought_players.columns
            else set()
        )
        filtered_df = filtered_df[filtered_df["id"].astype(str).isin(bought_player_ids)]

    # Order the player field per role
    filtered_df = (
        filtered_df.assign(
            _role_order=pd.Categorical(
                filtered_df["fanta_role"],
                categories=get_roles_dict().keys(),
                ordered=True,
            ),
            _player_order=filtered_df["player"].astype("string").str.casefold(),
        )
        .sort_values(["_role_order", "_player_order"], na_position="last")
        .drop(columns=["_role_order", "_player_order"])
    )

    st.session_state[f"{page_name}_filtered_players"] = filtered_df
    return filtered_df


def general_filters():
    """Render general controls for team layout and optional table columns."""

    # Set the number of columns of the view of the teams made by the fanta managers
    auction_keys_set.add(fanta_manager_split_value_key)
    st.session_state.setdefault(fanta_manager_split_value_key, 5)
    st.session_state[fanta_manager_split_value_widget_key] = st.session_state[fanta_manager_split_value_key]
    n_cols_selected = st.number_input(
        label="Set the number of columns used for the teams:",
        min_value=1,
        max_value=5,
        key=fanta_manager_split_value_widget_key,
        on_change=sync_filter,
        args=(fanta_manager_split_value_key, fanta_manager_split_value_widget_key),
        persist_state="session",
    )

    # Checkbox to show the Manager's prefered players
    auction_keys_set.add(enable_player_preferences_key)
    st.session_state.setdefault(enable_player_preferences_key, False)
    st.checkbox(
        "Show the columns of your selected players",
        key=enable_player_preferences_key,
        persist_state="session",
        wrap=True,
    )

    # Checkbox to show the Manager's prefered players
    auction_keys_set.add(enable_bought_players_stats_key)
    st.session_state.setdefault(enable_bought_players_stats_key, False)
    st.checkbox(
        "Enable compact view of the purchases",
        key=enable_bought_players_stats_key,
        persist_state="session",
        wrap=True,
        disabled=True if n_cols_selected == 1 else False
    )

    return


def checkbox_filters(fanta_players: pd.DataFrame) -> pd.DataFrame:
    """Render AI display controls and return role-sorted players."""
    filtered_df = fanta_players.copy()

    # Checkbox to show AI predictions
    auction_keys_set.add(show_ai_predictions_key)
    st.session_state.setdefault(show_ai_predictions_key, False)
    st.checkbox(
        "Show AI predictions",
        help="Select a single player to see the predictions",
        key=show_ai_predictions_key,
        persist_state="session",
        wrap=True,
    )

    # Checkbox to show the AI explaination
    auction_keys_set.add(show_ai_explainations_key)
    st.session_state.setdefault(show_ai_explainations_key, False)
    st.checkbox(
        "Enable AI explainations",
        help="Select a single player to see the predictions and their explainations",
        key=show_ai_explainations_key,
        persist_state="session",
        wrap=True,
        disabled=False if st.session_state[show_ai_predictions_key] else True
    )

    # Checkbox to show the AI plots
    auction_keys_set.add(show_ai_plots_key)
    st.session_state.setdefault(show_ai_plots_key, False)
    st.checkbox(
        "Enable AI plots",
        help="Select a single player to see the predictions and their plots",
        key=show_ai_plots_key,
        persist_state="session",
        wrap=True,
        disabled=False if st.session_state[show_ai_predictions_key] else True
    )

    # Order the player field per role
    filtered_df = (
        filtered_df.assign(
            _role_order=pd.Categorical(
                filtered_df["fanta_role"],
                categories=get_roles_dict().keys(),
                ordered=True,
            ),
            _player_order=filtered_df["player"].astype("string").str.casefold(),
        )
        .sort_values(["_role_order", "_player_order"], na_position="last")
        .drop(columns=["_role_order", "_player_order"])
    )

    st.session_state[f"{page_name}_filtered_players"] = filtered_df
    return filtered_df


def reset_teams_filters(fanta_managers):
    """Render controls that reset purchases for selected Fanta Managers."""

    selected_fanta_managers = st.multiselect(
        "Select Fanta Managers to reset",
        options=fanta_managers,
        placeholder="Select one or more managers...",
        key=reset_managers_widget_key,
        persist_state="session",
    )

    if selected_fanta_managers:
        st.html(
            f"""
            <style>
            .st-key-{reset_boughts_button_key} button:not(:disabled) {{
                background-color: #D32F2F;
                border-color: #D32F2F;
                color: #FFFFFF;
            }}
            .st-key-{reset_boughts_button_key} button:not(:disabled):hover {{
                background-color: #B71C1C;
                border-color: #B71C1C;
            }}
            </style>
            """
        )
        st.button(
            "Reset boughts",
            icon=":material/delete_sweep:",
            width="stretch",
            disabled=not selected_fanta_managers,
            key=reset_boughts_button_key,
            on_click=reset_fanta_manager_boughts,
            args=(reset_managers_widget_key,),
            help="Remove every bought player from the selected Fanta Managers.",
        )

    reset_message = st.session_state.pop(reset_bought_message_key, None)
    if reset_message:
        st.toast(reset_message, icon=":material/check_circle:")
    return


def load_player_preferences(path: str) -> dict:
    """Load selected-player metadata from CSV, indexed by player ID.

    Params
    ----------
    path : str
        Path to the selected players CSV file.

    Returns
    -------
    dict
        Maximum bid, interest and description indexed by player ID.
    """
    try:
        preferences_df = pd.read_csv(path, low_memory=False)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return {}

    required_columns = {"Id", "mln", "interest", "description"}
    if not required_columns.issubset(preferences_df.columns):
        return {}

    preferences = {}
    for _, preference_row in preferences_df.drop_duplicates("Id", keep="last").iterrows():
        player_id = preference_row["Id"]
        if pd.isna(player_id):
            continue

        if isinstance(player_id, float) and player_id.is_integer():
            player_id = int(player_id)

        mln_prevision = pd.to_numeric(preference_row["mln"], errors="coerce")
        interest = preference_row["interest"]
        description = preference_row["description"]
        preferences[str(player_id)] = {
            "mln_prevision": None if pd.isna(mln_prevision) else int(mln_prevision),
            "interest": None if pd.isna(interest) else str(interest),
            "description": None if pd.isna(description) else str(description),
        }

    return preferences


def update_player_boughts(players: pd.DataFrame, fanta_manager_players_dict: dict, fanta_managers: list) -> None:
    """Apply manager and price values to the in-memory purchase mapping.

    Params
    ----------
    players : pandas.DataFrame
        Edited player rows containing manager and price values.
    fanta_manager_players_dict : dict
        Purchased-player DataFrames indexed by Fanta Manager.
    fanta_managers : list
        Manager names allowed as purchase owners.
    """
    for _, player_row in players.iterrows():
        selected_manager = player_row["bought"]
        selected_manager = "" if pd.isna(selected_manager) else str(selected_manager).strip()

        mln_value = pd.to_numeric(player_row["mln"], errors="coerce")
        mln_value = 0 if pd.isna(mln_value) else int(mln_value)

        player_data = {
            "id": player_row["id"],
            "player": player_row["player"],
            "team": player_row["team"],
            "role": player_row["fanta_role"],
            "mantra_role": player_row.get("mantra_role"),
            "manager": selected_manager,
            "mln": mln_value,
        }

        # Remove the player from the previous fanta manager
        for fanta_manager, bought_players in fanta_manager_players_dict.items():
            if not bought_players.empty and "id" in bought_players.columns:
                different_player = bought_players["id"].astype(str) != str(player_row["id"])
                fanta_manager_players_dict[fanta_manager] = bought_players.loc[different_player].copy()

        # Add the player to the selected fanta manager
        if selected_manager in fanta_managers:
            bought_players = fanta_manager_players_dict.get(selected_manager, pd.DataFrame()).to_dict("records")
            bought_players.append(player_data)
            fanta_manager_players_dict[selected_manager] = pd.DataFrame(bought_players)

    st.session_state[f"{page_name}_manager_players_dict_key"] = fanta_manager_players_dict

    bought_players_dataframes = [
        bought_players
        for bought_players in fanta_manager_players_dict.values()
        if not bought_players.empty
    ]
    if bought_players_dataframes:
        bought_players_df = pd.concat(bought_players_dataframes, ignore_index=True)
    else:
        bought_players_df = pd.DataFrame(
            columns=bought_player_columns
        )
    st.session_state[f"{page_name}_bought_players_df_key"] = bought_players_df
    return


def reset_fanta_manager_boughts(selection_key: str) -> None:
    """Reset purchases belonging to the Fanta Managers selected in a widget.

    Params
    ----------
    selection_key : str
        Session State key containing the selected manager names.
    """
    fanta_managers = st.session_state.get("settings_managers_key", [])
    selected_managers = [
        manager
        for manager in st.session_state.get(selection_key, [])
        if manager in fanta_managers
    ]
    if not selected_managers:
        return

    empty_bought_players = pd.DataFrame(columns=bought_player_columns)
    fanta_manager_players_dict = st.session_state.get(
        f"{page_name}_manager_players_dict_key",
        {},
    )

    for fanta_manager in fanta_managers:
        fanta_manager_players_dict.setdefault(fanta_manager, empty_bought_players.copy())
    for fanta_manager in selected_managers:
        fanta_manager_players_dict[fanta_manager] = empty_bought_players.copy()

        for role in ("P", "D", "C", "A"):
            st.session_state[f"{page_name}_{fanta_manager}_num_of_bought_{role}_key"] = 0
            st.session_state[f"{page_name}_{fanta_manager}_{role}_budget_limit_exceed_key"] = False
            st.session_state[f"{page_name}_{fanta_manager}_{role}_limit_exceed_key"] = False

        st.session_state[f"{page_name}_{fanta_manager}_last_spent_amount_key"] = 0
        st.session_state[f"{page_name}_{fanta_manager}_last_spent_player_id_key"] = ""
        st.session_state[f"{page_name}_{fanta_manager}_purchase_delta_highlight_key"] = False

    remaining_boughts = [
        bought_players
        for bought_players in fanta_manager_players_dict.values()
        if isinstance(bought_players, pd.DataFrame) and not bought_players.empty
    ]
    bought_players_df = (
        pd.concat(remaining_boughts, ignore_index=True)
        if remaining_boughts
        else empty_bought_players
    )

    st.session_state[f"{page_name}_manager_players_dict_key"] = fanta_manager_players_dict
    st.session_state[f"{page_name}_bought_players_df_key"] = bought_players_df

    for key in list(st.session_state):
        if str(key).startswith(f"{page_name}_purchase_editor_"):
            del st.session_state[key]

    store_env(
        data_dict={f"{page_name}_bought_players_df_key": bought_players_df},
        path=".env",
    )
    st.session_state[selection_key] = []
    st.session_state[reset_bought_message_key] = "Purchases reset for: {', '.join(selected_managers)}"
    return


def sync_purchase_editor(
    players_editor_df: pd.DataFrame,
    fanta_manager_players_dict: dict,
    fanta_managers: list,
    editor_key: str,
) -> None:
    """Apply table edits and update each manager's latest budget transaction.

    Params
    ----------
    players_editor_df : pandas.DataFrame
        DataFrame displayed by the purchase editor.
    fanta_manager_players_dict : dict
        Purchased-player DataFrames indexed by Fanta Manager.
    fanta_managers : list
        Manager names allowed as purchase owners.
    editor_key : str
        Session State key containing edits emitted by the data editor.
    """

    editor_changes = st.session_state.get(editor_key, {}).get("edited_rows", {})

    changed_row_positions = set()
    purchase_events = []
    price_updates = []

    # Build the boughts before the modifications
    bought_players_by_id = {}
    for fanta_manager, bought_players in fanta_manager_players_dict.items():
        if not isinstance(bought_players, pd.DataFrame) or bought_players.empty or "id" not in bought_players.columns:
            continue
        for _, bought_player in bought_players.iterrows():
            bought_players_by_id[str(bought_player["id"])] = {
                "manager": fanta_manager,
                "mln": int(
                    pd.to_numeric(
                        bought_player.get("mln"),
                        errors="coerce",
                    )
                ),
            }

    for row_position, changes in editor_changes.items():
        row_position = int(row_position)
        if row_position < 0 or row_position >= len(players_editor_df):
            continue

        player_id = str(players_editor_df.iloc[row_position]["id"])
        previous_purchase = bought_players_by_id.get(player_id, {})
        previous_manager = previous_purchase.get("manager", "")

        # Apply to the dataframe the modifies in the editor
        for column in ("bought", "mln"):
            if column not in changes:
                continue
            players_editor_df.iloc[row_position, players_editor_df.columns.get_loc(column)] = changes[column]
            changed_row_positions.add(row_position)

        selected_manager = players_editor_df.iloc[row_position]["bought"]
        selected_manager = "" if pd.isna(selected_manager) else str(selected_manager).strip()

        mln_value = pd.to_numeric(players_editor_df.iloc[row_position]["mln"], errors="coerce")
        mln_value = 0 if pd.isna(mln_value) else int(mln_value)

        # New purchase
        if "bought" in changes and selected_manager in fanta_managers and selected_manager != previous_manager:
            purchase_events.append((selected_manager, player_id, mln_value))
        elif "mln" in changes and selected_manager in fanta_managers:
            price_updates.append((selected_manager, player_id, mln_value))

    if not changed_row_positions:
        return

    update_player_boughts(
        players_editor_df.iloc[sorted(changed_row_positions)],
        fanta_manager_players_dict,
        fanta_managers,
    )

    # Update the price if the player is equal to the last transaction player
    for fanta_manager, player_id, mln_value in price_updates:
        last_transaction_amount_key = f"{page_name}_{fanta_manager}_last_transaction_amount_key"
        last_transaction_player_id_key = f"{page_name}_{fanta_manager}_last_transaction_player_id_key"

        last_transaction_amount = st.session_state.get(last_transaction_amount_key, 0)

        # Purchase done
        if str(st.session_state.get(last_transaction_player_id_key, "")) == player_id and last_transaction_amount < 0:
            st.session_state[last_transaction_amount_key] = -abs(mln_value)

    # Update new purchases
    for fanta_manager, player_id, mln_value in purchase_events:
        last_transaction_amount_key = f"{page_name}_{fanta_manager}_last_transaction_amount_key"
        last_transaction_player_id_key = f"{page_name}_{fanta_manager}_last_transaction_player_id_key"

        st.session_state[last_transaction_amount_key] = -abs(mln_value)
        st.session_state[last_transaction_player_id_key] = player_id
    return


def create_editor_dataframe(filtered_players: pd.DataFrame, fanta_manager_players_dict: dict, player_preferences: dict | None = None,):
    """Display the editable purchase table for the filtered players.

    Params
    ----------
    filtered_players : pandas.DataFrame
        Player rows currently visible after filtering.
    fanta_manager_players_dict : dict
        Purchased-player DataFrames indexed by Fanta Manager.
    player_preferences : dict or None
        Optional selected-player metadata indexed by player ID.
    """
    players_editor_df = filtered_players.copy()

    # Create the players dataframe to be shown
    bought_players_by_id = {}
    for fanta_manager, bought_players in fanta_manager_players_dict.items():
        if not isinstance(bought_players, pd.DataFrame):
            continue
        for _, bought_player in bought_players.iterrows():
            bought_player_data = bought_player.to_dict()
            bought_player_data["manager"] = fanta_manager
            bought_players_by_id[str(bought_player["id"])] = bought_player_data

    # Create the bought column
    bought_values = players_editor_df["id"].map(
        lambda player_id: bought_players_by_id.get(str(player_id), {}).get("manager")
    ).fillna("").astype(str)
    players_editor_df.insert(loc=0, column="bought", value=bought_values)

    # Create the mln column
    mln_values = pd.to_numeric(
        players_editor_df["id"].map(
            lambda player_id: bought_players_by_id.get(str(player_id), {}).get("mln", 1)
        ).fillna(1).astype(int),
        errors="coerce"
    )
    players_editor_df.insert(loc=1, column="mln", value=mln_values)

    # Case of checkbox selected to show the selected players
    if player_preferences is not None:
        for column in ["mln_prevision", "interest", "description"]:
            players_editor_df[column] = pd.Series(
                data=[
                    player_preferences.get(str(player_id), {}).get(column)
                    for player_id in players_editor_df["id"]
                ],
                index=players_editor_df.index,
                dtype=object,
            )

    # Use a different widget key when the visible players change.
    fanta_managers = st.session_state["settings_managers_key"]
    visible_player_ids = tuple(players_editor_df["id"].astype(str).tolist())
    editor_state = (visible_player_ids, tuple(fanta_managers), player_preferences is not None)
    editor_key = f"{page_name}_purchase_editor_{abs(hash(editor_state))}_key"

    # Applied when a manager selection occurs
    editor_changes = st.session_state.get(editor_key, {}).get("edited_rows", {})
    for row_position, changes in editor_changes.items():
        if "bought" in changes:
            selected_manager = changes["bought"]
            selected_manager = "" if pd.isna(selected_manager) else str(selected_manager)
            players_editor_df.iloc[int(row_position), players_editor_df.columns.get_loc("bought")] = selected_manager

    # Create the personalization of some columns for the table
    column_config = {
        column: st.column_config.Column(alignment="center")
        for column in players_editor_df.columns
    }
    column_config.update(
        {
            "bought": st.column_config.SelectboxColumn(
                "Bought",
                help="Select the fanta manager who purchased the player.",
                options=[""] + fanta_managers,
                default=""
            ),
            "mln": st.column_config.NumberColumn(
                "Mln",
                help="Fantamilioni spent for this player.",
                min_value=1,
                step=1,
                format="%d",
                alignment="center",
            ),
            "id": st.column_config.NumberColumn("ID", alignment="center"),
            "fanta_role": st.column_config.TextColumn("R", alignment="center"),
            "player": st.column_config.TextColumn("Player", alignment="center"),
            "team": st.column_config.TextColumn("Team", alignment="center"),
        }
    )

    if player_preferences is not None:
        column_config.update(
            {
                "mln_prevision": st.column_config.NumberColumn(
                    "Mln prevision",
                    help="Maximum number of credits planned for this player.",
                    format="%d",
                    alignment="center",
                ),
                "interest": st.column_config.TextColumn(
                    "Interest",
                    alignment="center",
                ),
                "description": st.column_config.TextColumn(
                    "Description",
                    help="Temporary note: changes made here are not saved.",
                    width="medium",
                ),
            }
        )

    # Set the order of the columns
    column_order = ["bought", "mln", "fanta_role", "player", "team", "Qt.I", "Qt.A", "FVM"]
    if player_preferences is not None:
        column_order += ["mln_prevision", "interest", "description"]

    # Set the editable columns
    editable_columns = {"bought", "mln"}
    if player_preferences is not None:
        editable_columns.add("mln_prevision")
        editable_columns.add("description")

    # Create the table
    editor_data = players_editor_df.style.apply(
        highlight_bought_rows, axis=1, fanta_managers=fanta_managers
    )
    if player_preferences is not None:
        editor_data = editor_data.map(
            lambda interest: (
                "background-color: #0e1117; color: #fafafa"
                if pd.isna(interest)
                else highlight_interest(interest)
            ),
            subset=["interest"],
        )
    st.data_editor(
        editor_data,
        hide_index=True,
        width="stretch",
        height="stretch",
        column_order=column_order,
        disabled=[column for column in players_editor_df.columns if column not in editable_columns],
        column_config=column_config,
        key=editor_key,
        on_change=sync_purchase_editor,
        args=(players_editor_df, fanta_manager_players_dict, fanta_managers, editor_key),
    )

    return


def remove_bought_player(player: dict) -> None:
        """Remove one purchased player and record the refunded amount."""
        free_player = pd.DataFrame(
            [
                {
                    "bought": "",
                    "mln": 1,
                    "id": player["id"],
                    "player": player["player"],
                    "team": player["team"],
                    "fanta_role": player["role"],
                    "mantra_role": player.get("mantra_role"),
                }
            ]
        )
        all_fanta_manager_players_dict = st.session_state[f"{page_name}_manager_players_dict_key"]
        all_fanta_managers = st.session_state["settings_managers_key"]

        update_player_boughts(
            players=free_player,
            fanta_manager_players_dict=all_fanta_manager_players_dict,
            fanta_managers=all_fanta_managers,
        )

        fanta_manager = str(player.get("manager", ""))

        last_transaction_amount_key = f"{page_name}_{fanta_manager}_last_transaction_amount_key"
        last_transaction_player_id_key = f"{page_name}_{fanta_manager}_last_transaction_player_id_key"

        st.session_state[last_transaction_amount_key] = abs(int(player["mln"]))
        st.session_state[last_transaction_player_id_key] = int(player["id"])

        for key in list(st.session_state):
            if str(key).startswith(f"{page_name}_purchase_editor_"):
                del st.session_state[key]

        return



# =============================================================================
# =============================== SCRIPT ======================================
# =============================================================================

# Block 1: Load Fanta Manager settings and require at least two managers.
loaded_env_values = load_env(path=".env")

# Track the persistent keys already stored for this page.
auction_keys_set = {
    key
    for key in loaded_env_values
    if key.startswith(f"{page_name}_")
}

# Initialize missing manager and auction settings.
settings_my_manager_key = "settings_my_manager_key"
auction_keys_set.add(settings_my_manager_key)
st.session_state.setdefault(settings_my_manager_key, "Me")
settings_managers_key = "settings_managers_key"
auction_keys_set.add(settings_managers_key)
st.session_state.setdefault(settings_managers_key, [st.session_state[settings_my_manager_key]])
settings_budget_key = "settings_budget_key"
auction_keys_set.add(settings_budget_key)
st.session_state.setdefault(settings_budget_key, 500)
settings_ai_enabled_key = "settings_ai_enabled_key"
auction_keys_set.add(settings_ai_enabled_key)
st.session_state.setdefault(settings_ai_enabled_key, False)

# Show the current Fanta Manager first and check for at least one other manager.
my_fanta_manager = st.session_state[settings_my_manager_key]
fanta_managers = st.session_state[settings_managers_key]
fanta_managers = [my_fanta_manager] + [manager for manager in fanta_managers if manager != my_fanta_manager]
st.session_state[settings_managers_key] = fanta_managers

'''
try:
    fanta_manager = register_to_auction(
        auth_issuer=st.user.iss,
        auth_subject=st.user.sub,
        username=st.session_state[f"{page_name}_username_key"],
        invite_code=st.session_state[f"{page_name}_invite_code_key"],
        team_name=st.session_state[f"{page_name}_team_name_key"],
    )
except ValueError as error:
    st.error(error)
    st.stop()
except sqlite3.IntegrityError:
    st.warning("This username or team name is already in use.")
    st.stop()
'''

# Case of no other managers different by my_fantamanager in the list
if not any(manager != my_fanta_manager for manager in fanta_managers):
    st.info("Add at least one other Fanta Manager in Settings before accessing the auction.")
    st.stop()

# Load data
models_packages_dict = load_models(target_features=features_to_predict_list)
feature_explanations = load_dataset("data/csv/models_generated/features_explainability.csv")
history_players = load_dataset("data/csv/notebooks_generated/serie_a_players_history.csv")
fanta_players = load_dataset("data/csv/notebooks_generated/serie_a_players_history.csv", filter_by_current_year=True)

# Restore purchased players when their session data has not been initialized
if f"{page_name}_manager_players_dict_key" not in st.session_state:
    restore_bought_players(
        bought_players_df_key=f"{page_name}_bought_players_df_key",
        settings_managers_key=settings_managers_key,
        fanta_manager_players_dict_key=f"{page_name}_manager_players_dict_key"
    )
fanta_manager_players_dict = st.session_state[f"{page_name}_manager_players_dict_key"]

# Load the optional preferences stored by the Players Selection page
player_preferences = None
if st.session_state[enable_player_preferences_key]:
    selection_players_path = st.session_state.get(
        "selection_selected_players_csv_path_key",
        "data/csv/pages/selection/selection_selected_players.csv",
    )
    player_preferences = load_player_preferences(selection_players_path)

# Render the sidebar controls for layout, AI views, and team resets.
with st.sidebar:

    st.markdown("### General settings")
    general_filters()
    st.divider()

    st.markdown("### AI settings")
    filtered_players = checkbox_filters(fanta_players)
    st.divider()

    st.markdown("### Reset teams")
    reset_teams_filters(fanta_managers)

# Title
year = get_current_year()
cols = st.columns([1,15])
with cols[0]:
    st.markdown(f"{get_icon('auction')}", unsafe_allow_html=True)
with cols[1]:
    st.title(f"Auction {year}-{year+1}")
st.caption(
    "Run the auction by filtering players, reviewing saved preferences and AI predictions, assigning purchases "
    "and prices, monitoring budgets and role limits, and exporting the completed teams to PDF."
)

st.space(15)

# Offer a full-width start request before the player table; permissions will follow.
auction_start_requested_key = "auction_start_requested_key"
st.session_state.setdefault(auction_start_requested_key, False)
st.button(
    "Start auction",
    type="primary",
    icon=":material/play_arrow:",
    width="stretch",
    key="auction_request_start_button_key",
    disabled=st.session_state[auction_start_requested_key],
    on_click=request_auction_start,
)
if st.session_state[auction_start_requested_key]:
    st.success("Auction start requested.")

# Render player filters, the editable dataset, and the optional interest legend.
if not st.session_state[enable_player_preferences_key]:
    cols = st.columns([7,1,52])
    with cols[0]:
        with st.container(border=True, key=f"dark-card-{page_name}_plyer_filters_key"):
            st.markdown("#### Filters")
            filtered_players = player_filters(filtered_players)
    with cols[2]:
        create_editor_dataframe(filtered_players, fanta_manager_players_dict, player_preferences)
else:
    cols = st.columns([11,1,40,1,7])
    with cols[0]:
        with st.container(border=True, key=f"dark-card-{page_name}_plyer_filters_key"):
            st.markdown("#### Filters")
            filtered_players = player_filters(filtered_players)
    with cols[2]:
        create_editor_dataframe(filtered_players, fanta_manager_players_dict, player_preferences)
    with cols[4]:
        if st.session_state[enable_player_preferences_key]:
            with st.container(border=True, height="stretch", width="content", key="dark-card-interest_container_key"):
                st.markdown("**Interest meanings**:")
                for interest, color in interest_colors_dict.items():
                    st.markdown(f':color[●]{{foreground="{color}"}} :small[{interest}]')

# Show AI predictions only when enabled and exactly one player is selected.
if st.session_state[show_ai_predictions_key] and filtered_players.shape[0] == 1:
    st.divider()

    selected_player = filtered_players.iloc[0]
    history_of_the_player = history_players[
        history_players["player"].eq(selected_player["player"])
        & history_players["season"].lt(selected_player["season"])
    ]

    print_models_predictions(
        models_packages_dict=models_packages_dict,
        history_players=history_players,
        history_of_the_player=history_of_the_player,
        player_row=filtered_players.iloc[0],
        top_k=4,
        worst_k=2,
        explainability_enabled=st.session_state[show_ai_explainations_key],
        plots_enebled=st.session_state[show_ai_plots_key],
    )

# Offer team downloads when all managers have completed their squads.
auction_completed = True
for fanta_manager in fanta_manager_players_dict:
    if not has_full_team(fanta_manager, page_name):
        auction_completed = False
if auction_completed:
    st.divider()
    download_col, managers_col = st.columns([6,20])
    with download_col:
        st.subheader("Download teams")
        save_bought_players(page_name)
else:
    managers_col = st.columns(1)[0]

# Display manager squads in the selected horizontal or vertical layout.
with managers_col:
    split_value = st.session_state[fanta_manager_split_value_key]
    ordered_manager_items = [
        (my_fanta_manager, fanta_manager_players_dict.get(my_fanta_manager, pd.DataFrame())),
    ] + [
        (fanta_manager, players)
        for fanta_manager, players in fanta_manager_players_dict.items()
        if fanta_manager != my_fanta_manager
    ]
    fanta_manager_players_dict_splitted: list[dict] = [
        dict(ordered_manager_items[i:i + split_value])
        for i in range(0, len(ordered_manager_items), split_value)
    ]
    for fanta_manager_players_chunk in fanta_manager_players_dict_splitted:
        if split_value > 1:
            create_vertical_teams(
                fanta_manager_players_chunk,
                split_value,
                page_name,
                enable_bought_players_stats_key,
                remove_bought_player,
            )
        elif split_value == 1:
            create_horizontal_teams(
                fanta_manager_players_chunk,
                page_name,
                remove_bought_player,
            )

# Persist the existing page settings and purchases using the current storage format.
fantacalcio_bought_players_df_key = f"{page_name}_bought_players_df_key"
auction_keys_set.add(fantacalcio_bought_players_df_key)
fantacalcio_keys_list = list(auction_keys_set)
store_env(
    data_dict={key: st.session_state[key] for key in fantacalcio_keys_list if key in st.session_state},
    path=".env",
)

# Render the page footer.
bottom_caption()
