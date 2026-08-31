import streamlit as st
import pandas as pd
import lib.ollama_api as llm
from lib.utils import (
    interest_markers,
    set_format_interest
)
from lib.streamlit_api import (
    thick_divider,
    highlight_bought_rows,
    sync_filter,
    apply_filters,
    load_dataset,
    get_role_limits,
    get_role_budget_limits,
    get_default_value,
    get_condition_by,
    load_env,
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

enable_player_preferences_key = f"{page_name}_enable_player_preferences_key"
reset_managers_widget_key = f"{page_name}_reset_managers_widget_key"
reset_boughts_button_key = f"{page_name}_reset_boughts_button_key"
bought_player_columns = ["id", "player", "team", "role", "mantra_role", "manager", "mln"]


# =============================================================================
# ============================== FUNCTIONS ====================================
# =============================================================================

def player_filters(fanta_players: pd.DataFrame, columns_list: list, widget_types: list, fanta_manager_players_dict: dict) -> pd.DataFrame:

    # Initialize default filter values
    for col, widget_type in zip(columns_list, widget_types):
        key = f"{page_name}_{col}_key"
        fantacalcio_keys_set.add(key)
        st.session_state.setdefault(key, get_default_value(fanta_players[col]))

    # Create widgets
    filtered_df = fanta_players.copy()
    for i, (column, widget_type) in enumerate(zip(columns_list, widget_types)):

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
        if widget_type == "multiselect":
            st.session_state[widget_key] = [
                value
                for value in st.session_state[filter_key]
                if value in options
            ]
        elif widget_type == "selectbox":
            st.session_state[widget_key] = (
                st.session_state[filter_key]
                if st.session_state[filter_key] in options
                else None
            )

        if widget_type == "multiselect":
            selected_values = st.multiselect(
                f"Search {column}",
                options=options,
                placeholder="Select one or more elements...",
                key=widget_key,
                on_change=sync_filter,
                args=(filter_key, widget_key),
            )
        else:
            selected_values = st.selectbox(
                f"Select {column}",
                options=options,
                index=None,
                placeholder="Select an element...",
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

    # Create the special filter based on the external boughts dictionary
    manager_filter_key = f"{page_name}_selected_manager_key"
    fantacalcio_keys_set.add(manager_filter_key)
    st.session_state.setdefault(manager_filter_key, "")

    manager_options = ["Free"] + st.session_state["settings_managers_key"]
    manager_widget_key = f"{page_name}_selected_manager_widget_key"
    st.session_state[manager_widget_key] = (
        st.session_state[manager_filter_key]
        if st.session_state[manager_filter_key] in manager_options
        else None
    )

    # Fanta Manager filter
    selected_fanta_manager = st.selectbox(
        "Select a Fanta Manager",
        options=manager_options,
        index=None,
        placeholder="Select a manager...",
        key=manager_widget_key,
        on_change=sync_filter,
        args=(manager_filter_key, manager_widget_key),
    )

    if selected_fanta_manager == "Free":
        bought_player_ids = set()
        for bought_players in fanta_manager_players_dict.values():
            if isinstance(bought_players, pd.DataFrame) and "id" in bought_players.columns:
                bought_player_ids.update(bought_players["id"].dropna().astype(str))
        filtered_df = filtered_df[~filtered_df["id"].astype(str).isin(bought_player_ids)]
    elif selected_fanta_manager:
        bought_players = fanta_manager_players_dict.get(selected_fanta_manager, pd.DataFrame())
        if "id" in bought_players.columns:
            bought_player_ids = set(bought_players["id"].dropna().astype(str))
        else:
            bought_player_ids = set()
        filtered_df = filtered_df[filtered_df["id"].astype(str).isin(bought_player_ids)]

    # Checkbox to show the Manager's prefered players
    fantacalcio_keys_set.add(enable_player_preferences_key)
    st.session_state.setdefault(enable_player_preferences_key, False)
    st.checkbox(
        "Show your selected players",
        key=enable_player_preferences_key,
        persist_state="session",
        wrap=True,
    )

    st.divider()
    
    # Store in session_state
    st.session_state[f"{page_name}_filtered_players"] = filtered_df
    return filtered_df


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


def generate_ai_response(fanta_manager_players_dict: dict):
    # Data preparation
    my_players = fanta_manager_players_dict.get(st.session_state["settings_my_manager_key"], pd.DataFrame()).copy()
    if my_players.empty:
        my_players = pd.DataFrame(columns=["role", "mln"])
    my_players["mln"] = pd.to_numeric(my_players["mln"], errors="coerce").fillna(0).astype(int)
    total_spent = my_players["mln"].sum()
    available_budget = st.session_state["settings_budget_key"] - total_spent

    role_counts = {
        role: len(my_players.loc[my_players["role"] == role])
        for role in ["P", "D", "C", "A"]
    }
    role_spending = {
        role: my_players.loc[my_players["role"] == role, "mln"].sum()
        for role in ["P", "D", "C", "A"]
    }
    role_limits_dict = get_role_limits()
    role_budget_limits_dict = get_role_budget_limits()

    # Create the prompt for the LLM
    prompt = f"""
    You are an expert in Serie A Fantacalcio.

    Analyze this player:
    {filtered_players.iloc[0].to_dict()}

    My current auction situation:
    - Available budget: {available_budget} mln
    - Goalkeepers: {role_counts["P"]}/{role_limits_dict["P"]} players, {role_spending["P"]}/{role_budget_limits_dict["P"]} mln spent
    - Defenders: {role_counts["D"]}/{role_limits_dict["D"]} players, {role_spending["D"]}/{role_budget_limits_dict["D"]} mln spent
    - Midfielders: {role_counts["C"]}/{role_limits_dict["C"]} players, {role_spending["C"]}/{role_budget_limits_dict["C"]} mln spent
    - Attackers: {role_counts["A"]}/{role_limits_dict["A"]} players, {role_spending["A"]}/{role_budget_limits_dict["A"]} mln spent

    Evaluate the player according to his Fantacalcio role:

    - For goalkeepers, consider starting status, saves, clean-sheet potential and penalty saves.
    - For defenders, consider starting status, defensive reliability, attacking contribution and cards.
    - For midfielders, consider goals, assists, set pieces and tactical role.
    - For attackers, consider starting status, goals, penalties, competition and injury risk.

    Consider his likely playing time, technical characteristics, team context,
    bonus potential, reliability and the needs of my current squad.

    Use only the supplied data and facts you are confident about.
    Do not invent injuries, transfers or starting status. Clearly mention uncertainty
    when current information is unavailable.

    Answer in Italian, using at most 160 words and this structure:

    **Profilo:** brief description of his real playing role and likely usage.

    **Punti a favore**
    - Two or three concise points.

    **Rischi**
    - One or two concise points.

    **Verdetto:** state whether you would buy him and suggest a reasonable maximum bid,
    considering my available budget, remaining role budget and remaining role slots.

    **Voto Fantacalcio:** X/10.
    """

    with st.spinner("Ollama AI is working..."):
        response = llm.query_ollama(
            prompt=prompt,
            content="Follow the user's instructions carefully. Use the supplied data, \
                avoid unsupported claims and respect the requested output format.",
        )

    st.markdown(response)
    return


def update_player_boughts(
    players: pd.DataFrame,
    fanta_manager_players_dict: dict,
    fanta_managers: list,
) -> None:
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
    st.session_state[f"{page_name}_reset_boughts_message_key"] = "Purchases reset for: {', '.join(selected_managers)}"
    return


def sync_purchase_editor(players_editor_df: pd.DataFrame, fanta_manager_players_dict: dict, fanta_managers: list, editor_key: str) -> None:
    """Apply purchase edits before Streamlit rebuilds the table."""
    editor_changes = st.session_state.get(editor_key, {}).get("edited_rows", {})
    changed_row_positions = set()

    for row_position, changes in editor_changes.items():
        row_position = int(row_position)
        for column in ("bought", "mln"):
            if column in changes:
                players_editor_df.iloc[
                    row_position,
                    players_editor_df.columns.get_loc(column),
                ] = changes[column]
                changed_row_positions.add(row_position)

    if changed_row_positions:
        update_player_boughts(
            players_editor_df.iloc[sorted(changed_row_positions)],
            fanta_manager_players_dict,
            fanta_managers,
        )


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
        height=450,
        column_order=column_order,
        disabled=[column for column in players_editor_df.columns if column not in editable_columns],
        column_config=column_config,
        key=editor_key,
        on_change=sync_purchase_editor,
        args=(players_editor_df, fanta_manager_players_dict, fanta_managers, editor_key),
    )

    return


def create_current_teams(fanta_manager_players_dict: dict, fanta_manager=None):
    # Create the df
    if fanta_manager is None:
        fanta_manager = st.session_state["settings_my_manager_key"]
    bought_players_df = fanta_manager_players_dict.get(fanta_manager, pd.DataFrame()).copy()
    if bought_players_df.empty:
        bought_players_df = pd.DataFrame(columns=["player", "team", "role", "mantra_role", "manager", "mln"])
    bought_players_df["mln"] = pd.to_numeric(bought_players_df["mln"], errors="coerce").fillna(0).astype(int)

    # Compute some budget metric
    starting_budget = st.session_state.get("settings_budget_key", 500)
    tot_spent = bought_players_df["mln"].sum()
    available_budget = starting_budget - tot_spent

    # Create columns
    budget_col, _, p_col, _, d_col, _, c_col, _, a_col = st.columns([10,1,9,1,9,1,9,1,9])

    role_limits_dict = get_role_limits()
    role_columns_dict = {
        "P": (p_col, "Goalkeepers", role_limits_dict["P"]),
        "D": (d_col, "Defenders", role_limits_dict["D"]),
        "C": (c_col, "Midfielders", role_limits_dict["C"]),
        "A": (a_col, "Attackers", role_limits_dict["A"]),
    }

    # Create the bought of the budget
    with budget_col:
        st.html(
            """
            <style>
            [class*="budget-metric"] [data-testid="stMetricLabel"] p {
                font-size: 1.25rem;
            }
            </style>
            """
        )
        with st.container(key=f"{fanta_manager}-budget-metric"):
            st.metric(
                label=f"Available cash for :blue[**{fanta_manager}**]",
                value=f":green[+{available_budget}] mln",
                delta=f"-{tot_spent} mln" if tot_spent > 0 else "",
                delta_color="blue" if tot_spent > 0 else "gray",
                icon="💰",
                border=True
            )

        if available_budget < 0:
            st.error("Budget exceeded")

    # Create the columns for the bought players
    role_budget_limits_dict = get_role_budget_limits()
    for role, (col, role_label, role_limit) in role_columns_dict.items():
        role_budget_limit = role_budget_limits_dict[role]

        # Players bought with the role "role"
        bought_players_role = bought_players_df.loc[bought_players_df["role"] == role]
        tot_spent_role = bought_players_role['mln'].sum()
        st.session_state[f"{page_name}_{fanta_manager}_num_of_bought_{role}_key"] = len(bought_players_role)
        st.session_state[f"{page_name}_{fanta_manager}_{role}_budget_limit_exceed_key"] = tot_spent_role > role_limit

        with col:
            with st.container(border=True, width="stretch", height="stretch"):
                
                if fanta_manager == my_fanta_manager:
                    delta_str = \
                        f"-{tot_spent_role} mln [budget {role_budget_limit}]" \
                        if (tot_spent_role > 0 and tot_spent_role < role_budget_limit) or (tot_spent_role > role_budget_limit) \
                        else f"0 mln [budget {role_budget_limit}]"
                else:
                    delta_str = \
                        f"-{tot_spent_role} mln" \
                        if (tot_spent_role > 0 and tot_spent_role < role_budget_limit) or (tot_spent_role > role_budget_limit) \
                        else "0 mln"
                delta_color_str = "grey" if tot_spent_role == 0 else "red" if tot_spent_role > role_budget_limit else "blue"

                st.metric(
                    label=f"{role_label} ({role})",
                    value=f"{len(bought_players_role)}/{role_limit}",
                    delta=delta_str,
                    delta_color=delta_color_str,
                )

                st.divider()

                if len(bought_players_role) > role_limit:
                    st.session_state[f"{page_name}_{fanta_manager}_{role}_limit_exceed_key"] = True
                    st.error("Role limit exceeded: remove the last purchase.")
                else:
                    st.session_state[f"{page_name}_{fanta_manager}_{role}_limit_exceed_key"] = False

                # Case of no player bought for this role
                if bought_players_role.empty:
                    st.caption("No players purchased")
                    continue
                
                # List the bought players
                for _, player_row in bought_players_role.iterrows():
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.session_state[f"{page_name}_{fanta_manager}_{role}_limit_exceed_key"]:
                            st.markdown(f"- :red[**{player_row['player']}**]")
                        else:
                            st.markdown(f"- **{player_row['player']}**")
                    with col2:
                        st.markdown(
                            f":small[:grey[{player_row['mln']} mln]]  \n"
                            f":small[:grey[{player_row['team']}]]",
                            text_alignment="right"
                        )

    return

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

    reset_message = st.session_state.pop(f"{page_name}_reset_boughts_message_key", None)
    if reset_message:
        st.toast(reset_message, icon=":material/check_circle:")
    return


# =============================================================================
# =============================== SCRIPT ======================================
# =============================================================================

# Load stored persistent values before initializing Session State defaults
loaded_env_values = load_env(path=".env")

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


st.title("⚽ Fantacalcio 26-27 - Create your own team")

thick_divider()

# Filters + players table
st.header("Fanta List")
st.caption(
    "Search or reduce the players in the table using the following filters.\n"
    "Select the Fanta Manager on the first column if someone has bought a player and set the millions spent to update the teams."
)

fanta_players = load_dataset("data/filtered_history_players.csv", filter_by_current_year=True)

with st.sidebar:

    st.markdown("### Filters")
    filtered_players = player_filters(
        fanta_players,
        columns_list=["player", "team", "fanta_role"],
        widget_types=["multiselect", "selectbox", "selectbox"],
        fanta_manager_players_dict=fanta_manager_players_dict
    )

    st.markdown("### Reset teams")
    reset_teams_filters(fanta_managers)

# Load the optional preferences stored by the Players Selection page
player_preferences = None
if st.session_state[enable_player_preferences_key]:
    selection_players_path = st.session_state.get(
        "selection_selected_players_csv_path_key",
        "data/selection_players.csv",
    )
    player_preferences = load_player_preferences(selection_players_path)

# Create editable df
if not st.session_state[enable_player_preferences_key]:
    create_editor_dataframe(filtered_players, fanta_manager_players_dict, player_preferences)
else:
    col1, _, col2 = st.columns([26,1,3])
    with col1:
        create_editor_dataframe(filtered_players, fanta_manager_players_dict, player_preferences)
    with col2:
        if st.session_state[enable_player_preferences_key]:
            for key, value in interest_markers.items():
                st.markdown(f"{value} :small[{key}]")

# Case of AI enabled
if st.session_state[settings_ai_enabled_key] and filtered_players.shape[0] == 1:
    generate_ai_response(fanta_manager_players_dict)

thick_divider()

# Teams of the Fanta Managers
st.header("Teams & Billing")
st.divider()
for fanta_manager in st.session_state[settings_managers_key]:
    create_current_teams(fanta_manager_players_dict, fanta_manager)
    st.divider()

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
    
