import streamlit as st
import pandas as pd
from lib.xgboost_predictor import (
    features_to_predict_list
)
from lib.utils import (
    interest_markers,
    set_format_interest,
    get_current_year,
    get_circular_role_icon,
    get_color_per_role
)
from lib.streamlit_api import (
    thick_divider,
    highlight_bought_rows,
    sync_filter,
    load_dataset,
    load_models,
    print_models_predictions,
    get_roles_dict,
    get_role_limits,
    get_role_budget_limits,
    get_role_limits,
    set_text_size,
    load_env,
    load_models,
    store_env,
    restore_bought_players,
    has_full_team,
    generate_pdf_with_bought_players
)


st.set_page_config(
    page_title="Fantacalcio 26-27",
    page_icon="⚽",
    layout="wide",
)

page_name = "fantacalcio"

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

def player_filters(fanta_players: pd.DataFrame) -> pd.DataFrame:
    filtered_df = fanta_players.copy()

    cols = st.columns([8,12,6,1,8,1,8])

    # Role filter
    role_filter_key = f"{page_name}_fanta_role_key"
    role_widget_key = f"{page_name}_fanta_role_widget_key"
    fantacalcio_keys_set.add(role_filter_key)
    st.session_state.setdefault(role_filter_key, None)
    role_options = sorted(fanta_players["fanta_role"].dropna().astype(str).unique())
    st.session_state[role_widget_key] = (
        st.session_state[role_filter_key]
        if st.session_state[role_filter_key] in role_options
        else None
    )
    with cols[0]:
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
    fantacalcio_keys_set.add(manager_filter_key)
    st.session_state.setdefault(manager_filter_key, None)
    manager_options = ["Free"] + st.session_state.get("settings_managers_key", [])
    st.session_state[manager_widget_key] = (
        st.session_state[manager_filter_key]
        if st.session_state[manager_filter_key] in manager_options
        else None
    )
    with cols[1]:
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
    fantacalcio_keys_set.add(player_filter_key)
    st.session_state.setdefault(player_filter_key, None)
    selected_player = st.session_state[player_filter_key]
    player_options = sorted(fanta_players["player"].dropna().astype(str).unique())
    st.session_state[player_widget_key] = selected_player if selected_player in player_options else None
    with cols[4]:
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
    fantacalcio_keys_set.add(team_filter_key)
    st.session_state.setdefault(team_filter_key, None)
    team_options = sorted(fanta_players["team"].dropna().astype(str).unique())
    st.session_state[team_widget_key] = (
        st.session_state[team_filter_key]
        if st.session_state[team_filter_key] in team_options
        else None
    )
    with cols[6]:
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

    # Set the number of columns of the view of the teams made by the fanta managers
    fantacalcio_keys_set.add(fanta_manager_split_value_key)
    st.session_state.setdefault(fanta_manager_split_value_key, False)
    st.number_input(
        label=f"Set the number of columns used for the teams:",
        min_value=1,
        max_value=5,
        value=4,
        key=fanta_manager_split_value_key
    )

    # Checkbox to show the Manager's prefered players
    fantacalcio_keys_set.add(enable_player_preferences_key)
    st.session_state.setdefault(enable_player_preferences_key, False)
    st.checkbox(
        "Show the columns of your selected players",
        key=enable_player_preferences_key,
        persist_state="session",
        wrap=True,
    )

    # Checkbox to show the Manager's prefered players
    fantacalcio_keys_set.add(enable_bought_players_stats_key)
    st.session_state.setdefault(enable_bought_players_stats_key, False)
    st.checkbox(
        "Enable compact view of the purchases",
        key=enable_bought_players_stats_key,
        persist_state="session",
        wrap=True,
    )

    return


def checkbox_filters(fanta_players: pd.DataFrame) -> pd.DataFrame:
    filtered_df = fanta_players.copy()

    # Checkbox to show AI predictions
    fantacalcio_keys_set.add(show_ai_predictions_key)
    st.session_state.setdefault(show_ai_predictions_key, False)
    st.checkbox(
        "Show AI predictions",
        help="Select a single player to see the predictions",
        key=show_ai_predictions_key,
        persist_state="session",
        wrap=True,
    )

    # Checkbox to show the AI explaination
    fantacalcio_keys_set.add(show_ai_explainations_key)
    st.session_state.setdefault(show_ai_explainations_key, False)
    st.checkbox(
        "Enable AI explainations",
        help="Select a single player to see the predictions and their explainations",
        key=show_ai_explainations_key,
        persist_state="session",
        wrap=True,
    )

    # Checkbox to show the AI plots
    fantacalcio_keys_set.add(show_ai_plots_key)
    st.session_state.setdefault(show_ai_plots_key, False)
    st.checkbox(
        "Enable AI plots",
        help="Select a single player to see the predictions and their plots",
        key=show_ai_plots_key,
        persist_state="session",
        wrap=True,
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
    """Load the selected players' preferences from CSV, indexed by player ID."""
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
    """Update auction data using only the manager and price columns."""
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
    """Reset every purchase belonging to the selected Fanta Managers."""
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
    """Apply purchase edits and update the last budget transaction."""

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
        players_editor_df["interest"] = players_editor_df["interest"].map(set_format_interest)

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
        editable_columns.add("interest")
        editable_columns.add("description")

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


def remove_bought_player(player: dict) -> None:
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


def create_vertical_teams(fanta_manager_players_dict: dict, n_cols: int):
    """Display one compact team column for each Fanta Manager."""

    # Initializations
    my_fanta_manager = st.session_state["settings_my_manager_key"]
    fanta_managers = st.session_state.get("settings_managers_key", [])
    if not fanta_managers:
        return
    ordered_fanta_managers = fanta_manager_players_dict.keys()
    starting_budget = st.session_state.get("settings_budget_key", 500)

    colors = {
        "orange": ("rgba(255,255,255,1)", "rgba(255,165,0,0.80)"),
        "green": ("rgba(255,255,255,1)", "rgba(0,128,0,0.80)"),
        "blue": ("rgba(255,255,255,1)", "rgba(0,0,255,0.80)"),
        "red": ("rgba(255,255,255,1)", "rgba(255,0,0,0.80)"),
        "violet": ("rgba(255,255,255,1)", "rgba(128,0,128,0.80)"),
        "gray": ("rgba(255,255,255,1)", "rgba(128,128,128,0.80)"),
    }

    # Iterations on fanta managers
    manager_cols = st.columns(n_cols)
    for col, fanta_manager in zip(manager_cols, ordered_fanta_managers):

        # Preparation of the bought dataframe
        bought_players = fanta_manager_players_dict.get(fanta_manager, pd.DataFrame()).copy()
        if bought_players.empty:
            bought_players = pd.DataFrame(columns=["player", "role", "mln"])
        bought_players["mln"] = pd.to_numeric(bought_players["mln"], errors="coerce").fillna(1).astype(int)
        
        # Initializations
        tot_spent = bought_players["mln"].sum()
        available_budget = starting_budget - tot_spent
        role_budget_limits_dict = get_role_budget_limits()
        role_number_limits_dict = get_role_limits()
        last_transaction_amount_key = f"{page_name}_{fanta_manager}_last_transaction_amount_key"
        last_transaction_player_id_key = f"{page_name}_{fanta_manager}_last_transaction_player_id_key"
        
        # Initialize variables for the available budget metric
        if last_transaction_amount_key not in st.session_state:
            if not bought_players.empty and "id" in bought_players.columns:
                last_bought_player = bought_players.iloc[-1]
                st.session_state[last_transaction_player_id_key] = str(last_bought_player["id"])
                st.session_state[last_transaction_amount_key] = -int(last_bought_player["mln"])
            else:
                st.session_state[last_transaction_player_id_key] = ""
                st.session_state[last_transaction_amount_key] = 0
        else:
            st.session_state.setdefault(last_transaction_amount_key, 0)
        
        # Prepare variables for the available budget metric
        budget_value_color = "green" if available_budget >= 0 else "red"
        budget_value = f"+{available_budget}" if available_budget >= 0 else f"-{available_budget}"
        last_transaction_amount = st.session_state[last_transaction_amount_key]
        if last_transaction_amount > 0:
            budget_delta = f"+{last_transaction_amount} mln"
            budget_delta_color = "green"
            budget_delta_arrow = "up"
        elif last_transaction_amount < 0:
            budget_delta = f"{last_transaction_amount} mln"
            budget_delta_color = "red"
            budget_delta_arrow = "down"
        else:
            budget_delta = "0 mln"
            budget_delta_color = "gray"
            budget_delta_arrow = "off"

        # Compute the dictionary with the total mln spent per role
        tot_spent_per_role = {}
        for role, role_budget_limit in role_budget_limits_dict.items():
            bought_players_role = bought_players.loc[bought_players["role"] == role]
            tot_spent_per_role[role] = bought_players_role['mln'].sum()

        with col:

            st.markdown(f"### :blue[{fanta_manager}]", text_alignment="left")

            set_text_size(text_size=1.1, class_name="shrinked-team")
            with st.container(key=f"{fanta_manager}-shrinked-team", border=True, height="stretch", width="stretch"):
                    
                col1, col2 = st.columns([9,10])
                with col1:
                    try:
                        st.image(f"img/codex_gen/{fanta_manager.lower()}.png", output_format="PNG")
                    except:
                        st.image("img/codex_gen/unknown.png", output_format="PNG")
                with col2:
                    st.metric(
                        label="**Budget**",
                        value=f":{budget_value_color}[{budget_value} $]",
                        delta=budget_delta,
                        delta_color=budget_delta_color,
                        delta_arrow=budget_delta_arrow,
                        width="content",
                        height="content",
                        icon="💰"
                    )

                if bought_players.empty:
                    st.caption("No players purchased")
                    continue

                for i, role in enumerate(get_roles_dict()):
                    players_of_role = bought_players[bought_players["role"].eq(role)]
                    if players_of_role.empty:
                        continue

                    players_of_role = bought_players[bought_players["role"].eq(role)]

                    badge_color = get_color_per_role(role, color_version=False)
                    bought_number_foreground, bought_number_background = colors[badge_color]
                    budget_spent_foreground, budget_spent_background = colors["violet"]

                    # Cases of warinings
                    if players_of_role.shape[0] > role_number_limits_dict[role]:
                        warning_bought_number_background = "rgba(0,0,0,0.85)"
                        warning_bought_number_foreground = "rgba(255,75,75,1)"
                        warning_bought_number_icon = "⚠️"
                    else:
                        warning_bought_number_background = bought_number_background
                        warning_bought_number_foreground = bought_number_foreground
                        warning_bought_number_icon = ""

                    if tot_spent_per_role[role] > role_budget_limits_dict[role]:
                        warning_budget_spent_background = "rgba(0,0,0,0.85)"
                        warning_budget_spent_foreground = "rgba(255,75,75,1)"
                    else:
                        warning_budget_spent_background = budget_spent_background
                        warning_budget_spent_foreground = budget_spent_foreground

                    with st.container(border=True if not st.session_state[enable_bought_players_stats_key] else False):

                        # Case of view of the number of bought players per role enabled
                        if not st.session_state[enable_bought_players_stats_key]:

                            st.markdown(
                                f'{warning_bought_number_icon} :color[**{get_roles_dict()[role].capitalize()}s** '
                                f'{players_of_role.shape[0]}/{role_number_limits_dict[role]}]'
                                f'{{foreground="{warning_bought_number_foreground}" background="{warning_bought_number_background}"}}',
                                text_alignment="left",
                            )
  

                        for j, (_, player) in enumerate(players_of_role.iterrows()):
                            error_color = "red" if j+1 > role_number_limits_dict[role] else "white"

                            sub_col1, sub_col2, sub_col3, sub_col4 = st.columns([1,5,2,2], vertical_alignment="center")
                            with sub_col1:
                                st.markdown(f"{get_circular_role_icon(role, font_size=13, height=21, width=21)}", unsafe_allow_html=True)
                            with sub_col2:
                                st.markdown(f':color[**{player["player"]}**]{{foreground="{error_color}"}}')
                            with sub_col3:
                                st.caption(f"{player['mln']}", text_alignment="right")
                            with sub_col4:
                                st.button(
                                    ":material/delete:",
                                    key=f"{page_name}_{fanta_manager}_{player['id']}_remove_player_key",
                                    help=f"Remove {player['player']} from {fanta_manager}.",
                                    type="tertiary",
                                    width="stretch",
                                    on_click=remove_bought_player,
                                    args=(player.to_dict(),),
                                )
                        
                        if not st.session_state[enable_bought_players_stats_key]:
                            if fanta_manager == my_fanta_manager:
                                st.markdown(
                                    f'###### :color[Spent: {tot_spent_per_role[role]}/{role_budget_limits_dict[role]} mln]'
                                    f'{{foreground="{warning_budget_spent_foreground}" background="{warning_budget_spent_background}"}}',
                                    width="stretch",
                                    text_alignment="left",
                                    anchors=False,
                                )
                            else:
                                st.markdown(
                                    f'###### :color[Spent: {tot_spent_per_role[role]} mln]'
                                    f'{{foreground="{budget_spent_foreground}" background="{budget_spent_background}"}}',
                                    width="stretch",
                                    text_alignment="left",
                                    anchors=False,
                                )
                    
                if available_budget < 0:
                    st.error("Budget exceeded")
            
    return



def create_horizontal_teams(fanta_manager_players_dict: dict):
    """Display one compact team column for each Fanta Manager."""

    # Initializations
    my_fanta_manager = st.session_state["settings_my_manager_key"]
    fanta_managers = st.session_state.get("settings_managers_key", [])
    if not fanta_managers:
        return
    ordered_fanta_managers = fanta_manager_players_dict.keys()
    starting_budget = st.session_state.get("settings_budget_key", 500)

    colors = {
        "orange": ("rgba(255,255,255,1)", "rgba(255,165,0,0.80)"),
        "green": ("rgba(255,255,255,1)", "rgba(0,128,0,0.80)"),
        "blue": ("rgba(255,255,255,1)", "rgba(0,0,255,0.80)"),
        "red": ("rgba(255,255,255,1)", "rgba(255,0,0,0.80)"),
        "violet": ("rgba(255,255,255,1)", "rgba(128,0,128,0.80)"),
        "gray": ("rgba(255,255,255,1)", "rgba(128,128,128,0.80)"),
    }

    # Iterations on fanta managers
    for fanta_manager in ordered_fanta_managers:

        # Preparation of the bought dataframe
        bought_players = fanta_manager_players_dict.get(fanta_manager, pd.DataFrame()).copy()
        if bought_players.empty:
            bought_players = pd.DataFrame(columns=["player", "role", "mln"])
        bought_players["mln"] = pd.to_numeric(bought_players["mln"], errors="coerce").fillna(1).astype(int)
        
        # Initializations
        tot_spent = bought_players["mln"].sum()
        available_budget = starting_budget - tot_spent
        role_budget_limits_dict = get_role_budget_limits()
        role_number_limits_dict = get_role_limits()
        last_transaction_amount_key = f"{page_name}_{fanta_manager}_last_transaction_amount_key"
        last_transaction_player_id_key = f"{page_name}_{fanta_manager}_last_transaction_player_id_key"
        
        # Initialize variables for the available budget metric
        if last_transaction_amount_key not in st.session_state:
            if not bought_players.empty and "id" in bought_players.columns:
                last_bought_player = bought_players.iloc[-1]
                st.session_state[last_transaction_player_id_key] = str(last_bought_player["id"])
                st.session_state[last_transaction_amount_key] = -int(last_bought_player["mln"])
            else:
                st.session_state[last_transaction_player_id_key] = ""
                st.session_state[last_transaction_amount_key] = 0
        else:
            st.session_state.setdefault(last_transaction_amount_key, 0)
        
        # Prepare variables for the available budget metric
        budget_value_color = "green" if available_budget >= 0 else "red"
        budget_value = f"+{available_budget}" if available_budget >= 0 else f"-{available_budget}"
        last_transaction_amount = st.session_state[last_transaction_amount_key]
        if last_transaction_amount > 0:
            budget_delta = f"+{last_transaction_amount} mln"
            budget_delta_color = "green"
            budget_delta_arrow = "up"
        elif last_transaction_amount < 0:
            budget_delta = f"{last_transaction_amount} mln"
            budget_delta_color = "red"
            budget_delta_arrow = "down"
        else:
            budget_delta = "0 mln"
            budget_delta_color = "gray"
            budget_delta_arrow = "off"

        # Compute the dictionary with the total mln spent per role
        tot_spent_per_role = {}
        for role, role_budget_limit in role_budget_limits_dict.items():
            bought_players_role = bought_players.loc[bought_players["role"] == role]
            tot_spent_per_role[role] = bought_players_role['mln'].sum()
        

        st.markdown(f"## :blue[{fanta_manager}]", text_alignment="left")

        with st.container(height="stretch", width="stretch"):

            col_fanta_manager, col_players = st.columns([1,7])
            with col_fanta_manager:

                set_text_size(text_size=1.1, class_name="shrinked-team")
                with st.container(key=f"{fanta_manager}-shrinked-team", height="stretch", width="stretch"):
                    try:
                        st.image(f"img/codex_gen/{fanta_manager.lower()}.png", output_format="PNG")
                    except:
                        st.image("img/codex_gen/unknown.png", output_format="PNG")

                    with st.container(border=True):
                        st.metric(
                            label="**Budget**",
                            value=f":{budget_value_color}[{budget_value} $]",
                            delta=budget_delta,
                            delta_color=budget_delta_color,
                            delta_arrow=budget_delta_arrow,
                            width="stretch",
                            height="stretch",
                            icon="💰"
                        )
            
            with col_players:

                for i, (role, col) in enumerate(zip(get_roles_dict(), st.columns(len(get_roles_dict().keys()), border=True))):
                    players_of_role = bought_players[bought_players["role"].eq(role)]

                    badge_color = get_color_per_role(role, color_version=False)
                    bought_number_foreground, bought_number_background = colors[badge_color]
                    budget_spent_foreground, budget_spent_background = colors["violet"]

                    # Cases of warinings
                    if players_of_role.shape[0] > role_number_limits_dict[role]:
                        warning_bought_number_background = "rgba(0,0,0,0.85)"
                        warning_bought_number_foreground = "rgba(255,75,75,1)"
                        warning_bought_number_icon = "⚠️"
                    else:
                        warning_bought_number_background = bought_number_background
                        warning_bought_number_foreground = bought_number_foreground
                        warning_bought_number_icon = ""

                    if tot_spent_per_role[role] > role_budget_limits_dict[role]:
                        warning_budget_spent_background = "rgba(0,0,0,0.85)"
                        warning_budget_spent_foreground = "rgba(255,75,75,1)"
                    else:
                        warning_budget_spent_background = budget_spent_background
                        warning_budget_spent_foreground = budget_spent_foreground

                    with col:
                            
                        st.markdown(
                            f'###### {warning_bought_number_icon} :color[**{get_roles_dict()[role].capitalize()}s** '
                            f'{players_of_role.shape[0]}/{role_number_limits_dict[role]}]'
                            f'{{foreground="{warning_bought_number_foreground}" background="{warning_bought_number_background}"}}',
                            text_alignment="center",
                        )

                        if players_of_role.empty:
                            st.caption(f"No {get_roles_dict()[role].capitalize()}s purchased")
                            continue

                        for j, (_, player) in enumerate(players_of_role.iterrows()):

                            sub_col1, sub_col2, sub_col3, sub_col4 = st.columns([1,5,2,2], vertical_alignment="center")
                            with sub_col1:
                                st.markdown(f"{get_circular_role_icon(role, font_size=13, height=21, width=21)}", unsafe_allow_html=True)
                            with sub_col2:
                                error_color = "red" if j+1 > role_number_limits_dict[role] else "white"
                                st.markdown(
                                    f':color[**{player["player"]}**]'
                                    f'{{foreground="{error_color}"}}'
                                )
                            with sub_col3:
                                st.caption(f"{player['mln']}", text_alignment="right")
                            with sub_col4:
                                st.button(
                                    ":material/delete:",
                                    key=f"{page_name}_{fanta_manager}_{player['id']}_remove_player_key",
                                    help=f"Remove {player['player']} from {fanta_manager}.",
                                    type="tertiary",
                                    width="stretch",
                                    on_click=remove_bought_player,
                                    args=(player.to_dict(),),
                                )

                        with st.container(height="stretch", width="stretch", vertical_alignment="bottom"):
                            if fanta_manager == my_fanta_manager:
                                st.markdown(
                                    f'###### :color[Spent: {tot_spent_per_role[role]}/{role_budget_limits_dict[role]} mln]'
                                    f'{{foreground="{warning_budget_spent_foreground}" background="{warning_budget_spent_background}"}}',
                                    width="stretch",
                                    text_alignment="center",
                                    anchors=False,
                                )
                            else:
                                st.markdown(
                                    f'###### :color[Spent: {tot_spent_per_role[role]} mln]'
                                    f'{{foreground="{budget_spent_foreground}" background="{budget_spent_background}"}}',
                                    width="stretch",
                                    text_alignment="center",
                                    anchors=False,
                                )
                        
                    if available_budget < 0:
                        st.error("Budget exceeded")
                
    return


# =============================================================================
# =============================== SCRIPT ======================================
# =============================================================================

# Load stored persistent values before initializing Session State defaults
loaded_env_values = load_env(path=".env")
models_packages_dict = load_models(target_features=features_to_predict_list)
feature_explanations = load_dataset("data/features_explainability.csv")

# Set of keys whom value has to be stored (for next loaded)
fantacalcio_keys_set = {
    key
    for key in loaded_env_values
    if key.startswith(f"{page_name}_")
}

# Initialize by default values not available in the environment file
settings_my_manager_key = "settings_my_manager_key"
fantacalcio_keys_set.add(settings_my_manager_key)
st.session_state.setdefault(settings_my_manager_key, "Me")
settings_managers_key = "settings_managers_key"
fantacalcio_keys_set.add(settings_managers_key)
st.session_state.setdefault(settings_managers_key, [st.session_state[settings_my_manager_key]])
settings_budget_key = "settings_budget_key"
fantacalcio_keys_set.add(settings_budget_key)
st.session_state.setdefault(settings_budget_key, 500)
settings_ai_enabled_key = "settings_ai_enabled_key"
fantacalcio_keys_set.add(settings_ai_enabled_key)
st.session_state.setdefault(settings_ai_enabled_key, False)

# Reorder the Fanta Managers with my Fanta Manager as first item
my_fanta_manager = st.session_state[settings_my_manager_key]
fanta_managers = st.session_state[settings_managers_key]
fanta_managers = [my_fanta_manager] + [manager for manager in fanta_managers if manager != my_fanta_manager]
st.session_state[settings_managers_key] = fanta_managers

# Case of restore of bought players needed
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
        "data/selection_players.csv",
    )
    player_preferences = load_player_preferences(selection_players_path)

# History players
history_players = load_dataset("data/filtered_history_players.csv")

# Filters + players table
fanta_players = load_dataset("data/filtered_history_players.csv", filter_by_current_year=True)

# Filters
with st.sidebar:
    st.markdown("### General settings")
    general_filters()
    st.markdown("### AI settings")
    filtered_players = checkbox_filters(fanta_players)
    st.divider()
    st.markdown("### Reset teams")
    reset_teams_filters(fanta_managers)

# Title
year = get_current_year()
st.title(f"⚽ Fantacalcio {year}-{year+1}")
st.caption(
    "Filter players, display your saved preferences and assign purchases and prices. "
    "The page automatically tracks the remaining budget, purchased players and role limits."
    "At the end of the auction it will allows you to download the pdf with all the created teams."
)

st.divider()

# Filters
filtered_players = player_filters(filtered_players)

# Create editable df
if not st.session_state[enable_player_preferences_key]:
    create_editor_dataframe(filtered_players, fanta_manager_players_dict, player_preferences)
else:
    col1, _, col2 = st.columns([52,1,7])
    with col1:
        create_editor_dataframe(filtered_players, fanta_manager_players_dict, player_preferences)
    with col2:
        if st.session_state[enable_player_preferences_key]:
            with st.container(border=True, width="content"):
                st.markdown("**Symbols meanings**:")
                for key, value in interest_markers.items():
                    st.markdown(f"{value} :small[{key}]")


# Case of AI enabled
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

st.divider()

# Teams of the Fanta Managers
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
        create_vertical_teams(fanta_manager_players_chunk, split_value)
    elif split_value == 1:
        create_horizontal_teams(fanta_manager_players_chunk)


# Store persistent Session State values
fantacalcio_bought_players_df_key = f"{page_name}_bought_players_df_key"
fantacalcio_keys_set.add(fantacalcio_bought_players_df_key)
fantacalcio_keys_list = list(fantacalcio_keys_set)
store_env(
    data_dict={key: st.session_state[key] for key in fantacalcio_keys_list if key in st.session_state},
    path=".env",
)

# Case of pdf generation
auction_completed = True
for fanta_manager in fanta_manager_players_dict:
    if not has_full_team(fanta_manager):
        auction_completed = False
if auction_completed:
    with st.spinner("Building the teams file..."):
        generate_pdf_with_bought_players()


with st.bottom:
    st.caption("© 2026 GP · All rights reserved")
