import streamlit as st
import pandas as pd
import lib.ollama_api as llm
import lib.streamlit_api as myst



st.set_page_config(
    page_title="Fantacalcio 26-27",
    page_icon="⚽",
    layout="wide",
)

# Fanta Manager name of the user
st.session_state.setdefault("my_fanta_manager_key", "Me")


role_limits_dict = {
    "P": st.session_state.get("fantacalcio_goalkeepers_limit_key", 3),
    "D": st.session_state.get("fantacalcio_defenders_limit_key", 8),
    "C": st.session_state.get("fantacalcio_midfielders_limit_key", 8),
    "A": st.session_state.get("fantacalcio_attackers_limit_key", 6),
}

# =============================================================================
# ============================== FUNCTIONS ====================================
# =============================================================================

def create_sidebar_settings():

    st.session_state.setdefault("fanta_managers_key", [st.session_state["my_fanta_manager_key"]])

    with st.sidebar:

        with st.container(border=True):

            st.markdown("## ⚙️ Settings")
            st.caption("Customize the Fantacalcio values.")

            st.markdown("### Fanta managers")

            fanta_managers = st.session_state["fanta_managers_key"]

            my_new_fanta_manager = st.text_input(
                label="Modify your Fanta Manager name",
                placeholder=st.session_state["my_fanta_manager_key"],
                key="my_fanta_manager_widget_key",
            ).strip()
            update_fanta_manager_button = st.button("Update", width="stretch")
            if update_fanta_manager_button:
                existing_names = [manager.lower() for manager in fanta_managers]
                if not my_new_fanta_manager:
                    is_warning = True
                    st.warning("Enter a fanta manager name.")
                elif my_new_fanta_manager.lower() in existing_names:
                    is_warning = True
                    st.warning("Fanta manager already present.")
                else:
                    is_warning = False
                    fanta_managers.remove(st.session_state["my_fanta_manager_key"])
                    fanta_managers.append(my_new_fanta_manager)
                    st.session_state["fanta_managers_key"] = fanta_managers
                    st.session_state["my_fanta_manager_key"] = my_new_fanta_manager

            new_fanta_manager = st.text_input(
                label="Add a new Fanta Manager",
                placeholder="Enter a name...",
                key="new_fanta_manager_widget_key",
            ).strip()
            add_fanta_manager_button = st.button("Add", width="stretch")
            if add_fanta_manager_button:
                existing_names = [manager.lower() for manager in fanta_managers]
                if not new_fanta_manager:
                    is_warning = True
                    st.warning("Enter a fanta manager name.")
                elif new_fanta_manager.lower() in existing_names:
                    is_warning = True
                    st.warning("Fanta manager already present.")
                else:
                    is_warning = False
                    fanta_managers.append(new_fanta_manager)
                    st.session_state["fanta_managers_key"] = fanta_managers


            st.caption(f"Fanta managers: {', '.join(fanta_managers)}")
            if add_fanta_manager_button and not is_warning:
                st.success("Fanta Manager added successfully")
            if update_fanta_manager_button and not is_warning:
                st.success("Fanta Manager updated successfully")
            
            st.markdown("### Auction settings")

            budget = st.number_input(
                "Available budget",
                min_value=0,
                value=500,
                step=50,
                key="fantacalcio_budget_key",
            )

            goalkeepers_limit = st.number_input(
                "Goalkeepers",
                min_value=0,
                value=3,
                step=1,
                key="fantacalcio_goalkeepers_limit_key",
            )

            defenders_limit = st.number_input(
                "Defenders",
                min_value=0,
                value=8,
                step=1,
                key="fantacalcio_defenders_limit_key",
            )

            midfielders_limit = st.number_input(
                "Midfielders",
                min_value=0,
                value=8,
                step=1,
                key="fantacalcio_midfielders_limit_key",
            )

            attackers_limit = st.number_input(
                "Attackers",
                min_value=0,
                value=6,
                step=1,
                key="fantacalcio_attackers_limit_key",
            )

            st.markdown("### AI settings")

            ai_enabled = st.toggle(
                "Activate AI to help you",
                value=False,
                key="ai_enabled_key",
            )
    
    return


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Apply filters currently stored in Streamlit session state."""
    result = df.copy()

    selected_players = st.session_state.get("fanta_player_key", [])
    selected_team = st.session_state.get("fanta_team_key")
    selected_role = st.session_state.get("fanta_role_key")

    if selected_players:
        result = result[result["player"].isin(selected_players)]
    if selected_team:
        result = result[result["team"] == selected_team]
    if selected_role:
        result = result[result["fanta_role"] == selected_role]
    return result


def player_filter(fanta_players: pd.DataFrame) -> pd.DataFrame:

    # Initialize default filter values
    st.session_state.setdefault("fanta_player_key", [])
    st.session_state.setdefault("fanta_team_key", "")
    st.session_state.setdefault("fanta_role_key", "")

    # Apply previous selections before generating widget options.
    options_df = apply_filters(fanta_players)

    names = sorted(options_df["player"].dropna().astype(str).unique())
    teams = sorted(options_df["team"].dropna().astype(str).unique())
    roles = sorted(options_df["fanta_role"].dropna().astype(str).unique())

    # Restore widget values after their options change.
    st.session_state["fanta_player_widget_key"] = [
        player
        for player in st.session_state["fanta_player_key"]
        if player in names
    ]
    st.session_state["fanta_team_widget_key"] = (
        st.session_state["fanta_team_key"]
        if st.session_state["fanta_team_key"] in teams
        else None
    )
    st.session_state["fanta_role_widget_key"] = (
        st.session_state["fanta_role_key"]
        if st.session_state["fanta_role_key"] in roles
        else None
    )
    
    # Create widgets
    cols = st.columns([9,1,9,1,9,1,9,1])
    with cols[0]:
        selected_players = st.multiselect(
            "Search players",
            options=names,
            placeholder="Select one or more players...",
            key="fanta_player_widget_key",
            on_change=myst.sync_filter,
            args=("fanta_player_key", "fanta_player_widget_key"),
        )
    with cols[2]:
        selected_team = st.selectbox(
            "Select team",
            options=teams,
            index=None,
            placeholder="Select a team...",
            key="fanta_team_widget_key",
            on_change=myst.sync_filter,
            args=("fanta_team_key", "fanta_team_widget_key"),
        )
    with cols[4]:
        selected_role = st.selectbox(
            "Select role",
            options=roles,
            index=None,
            placeholder="Select a role...",
            key="fanta_role_widget_key",
            on_change=myst.sync_filter,
            args=("fanta_role_key", "fanta_role_widget_key"),
        )
    with cols[6]:
        selected_fanta_manager = st.selectbox(
            "Select a Fanta Manager",
            options=st.session_state["fanta_managers_key"],
            index=None,
            placeholder="Select a manager...",
            key="fanta_managers_widget_key",
            on_change=myst.sync_filter,
            args=("fanta_managers_key", "fanta_managers_widget_key"),
        )

    st.divider()

    # Apply the values returned by the widgets during the current rerun.
    filtered_df = fanta_players.copy()
    if selected_players:
        filtered_df = filtered_df[filtered_df["player"].isin(selected_players)]
    if selected_team:
        filtered_df = filtered_df[filtered_df["team"] == selected_team]
    if selected_role:
        filtered_df = filtered_df[filtered_df["fanta_role"] == selected_role]
    if selected_fanta_manager:
        filtered_df = filtered_df[filtered_df["Bought by"] == selected_fanta_manager]
    
    # Store in session_state
    st.session_state["filtered_players"] = filtered_df
    return filtered_df


def get_bought_players_dict():
    '''Pick all the players bought during the auction.'''
    st.session_state.setdefault("bought_players_dict_key", {})
    return st.session_state["bought_players_dict_key"]


def generate_ai_response(bought_players_dict: dict):
    # Data preparation
    my_players = [player for player in bought_players_dict.values() if player.get("manager") == st.session_state["my_fanta_manager_key"]]
    total_spent = sum(int(player.get("mln", 0)) for player in my_players)
    available_budget = st.session_state["fantacalcio_budget_key"] - total_spent

    role_counts = {
        role: sum(player.get("role") == role for player in my_players)
        for role in ["P", "D", "C", "A"]
    }

    # Create the prompt for the LLM
    prompt = f"""
    You are an expert in Serie A Fantacalcio.

    Analyze this player:
    {filtered_players.iloc[0].to_dict()}

    My current auction situation:
    - Available budget: {available_budget} mln
    - Goalkeepers: {role_counts["P"]}/{role_limits_dict["P"]}
    - Defenders: {role_counts["D"]}/{role_limits_dict["D"]}
    - Midfielders: {role_counts["C"]}/{role_limits_dict["C"]}
    - Attackers: {role_counts["A"]}/{role_limits_dict["A"]}

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
    considering my available budget and remaining role slots.

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


def create_editor_dataframe(filtered_players: pd.DataFrame, bought_players_dict: dict):

    # Show one row for each player and add the auction columns
    players_editor_df = filtered_players.copy()
    players_editor_df.insert(
        loc=0,
        column="bought",
        value=players_editor_df["id"].map(
            lambda player_id: bought_players_dict.get(str(player_id), {}).get("manager", "")
        )
    )
    players_editor_df.insert(
        loc=1,
        column="mln",
        value=pd.to_numeric(
            players_editor_df["id"].map(
                lambda player_id: bought_players_dict.get(str(player_id), {}).get("mln", 0)
            ),
            errors="coerce",
        ).fillna(0).astype(int)
    )

    # Use a different widget key when the visible players change.
    fanta_managers = st.session_state["fanta_managers_key"]
    visible_player_ids = tuple(players_editor_df["id"].astype(str).tolist())
    editor_state = (visible_player_ids, tuple(fanta_managers))
    editor_key = f"purchase_editor_{abs(hash(editor_state))}_key"

    # Create the editable table
    column_config = {column: st.column_config.Column(alignment="center") for column in players_editor_df.columns}
    column_config.update({
        "bought": st.column_config.SelectboxColumn(
            "Bought by",
            help="Select the fanta manager who purchased the player.",
            options=["Free"] + fanta_managers,
            default="Free",
        ),
        "mln": st.column_config.NumberColumn(
            "mln",
            help="Fantamilioni spent for this player.",
            min_value=0,
            step=1,
            format="%d",
            alignment="center",
        ),
        "id": st.column_config.NumberColumn("ID", alignment="center"),
        "player": st.column_config.TextColumn("Player", alignment="center"),
        "team": st.column_config.TextColumn("Team", alignment="center"),
        "fanta_role": st.column_config.TextColumn("Role", alignment="center"),
        "mantra_role": st.column_config.TextColumn("Mantra", alignment="center"),
    })

    edited_players = st.data_editor(
        players_editor_df,
        hide_index=True,
        width="stretch",
        height=450,
        column_order=["bought", "mln", "player", "team", "fanta_role", "Qt.I", "Qt.A", "FVM"],
        disabled=[column for column in players_editor_df.columns if column not in {"bought", "mln"}],
        column_config=column_config,
        key=editor_key,
    )

    # Update purchases for the players currently visible in the editor.
    for _, player_row in edited_players.iterrows():
        player_id = str(player_row["id"])
        selected_manager = player_row["bought"]

        if pd.isna(selected_manager):
            selected_manager = ""
        else:
            selected_manager = str(selected_manager).strip()

        # Case of price to be initialized
        if pd.isna(player_row["mln"]):
            player_row["mln"] = 0

        player_data = {
            "id": player_row["id"],
            "player": player_row["player"],
            "team": player_row["team"],
            "role": player_row["fanta_role"],
            "mantra_role": player_row.get("mantra_role"),
            "manager": selected_manager,
            "mln": int(player_row["mln"])
        }

        # Case of player bought by a fantasy manager
        if selected_manager in fanta_managers:
            bought_players_dict[player_id] = player_data
            continue
        
        bought_players_dict.pop(player_id, None)

    # Store the updated auction state
    st.session_state["bought_players_dict_key"] = bought_players_dict
    return


def create_budget_columns(bought_players_dict: dict, fanta_manager=st.session_state["my_fanta_manager_key"]):
    # Create the df
    bought_df = pd.DataFrame(bought_players_dict.values())
    if bought_df.empty:
        bought_df = pd.DataFrame(
            columns=[
                "player",
                "team",
                "role",
                "mantra_role",
                "manager",
                "mln",
            ]
        )
    purchased_df = bought_df.loc[bought_df["manager"] == fanta_manager].copy()
    purchased_df["mln"] = pd.to_numeric(purchased_df["mln"], errors="coerce").fillna(0).astype(int)

    # Compute some budget metrics
    starting_budget = st.session_state.get("fantacalcio_budget_key", 500)
    total_spent = purchased_df["mln"].sum()
    available_budget = starting_budget - total_spent

    # Create columns
    budget_col, _, p_col, _, d_col, _, c_col, _, a_col = st.columns([10,1,9,1,9,1,9,1,9])

    role_columns_dict = {
        "P": (p_col, "Goalkeepers", role_limits_dict["P"]),
        "D": (d_col, "Defenders", role_limits_dict["D"]),
        "C": (c_col, "Midfielders", role_limits_dict["C"]),
        "A": (a_col, "Attackers", role_limits_dict["A"]),
    }

    # Create the bought of the budget
    with budget_col:
        st.metric(
            label="Available",
            value=f"{available_budget} mln",
            delta=f"-{total_spent} mln spent",
            delta_color="inverse",
            icon="💰",
            border=True
        )

        if available_budget < 0:
            st.error("Budget exceeded")

    # Create the columns for the bought players
    for role, (col, role_label, role_limit) in role_columns_dict.items():

        # Players bought with the role "role"
        bought_players_role = purchased_df.loc[purchased_df["role"] == role]
        st.session_state[f"{fanta_manager}_num_of_bought_{role}_key"] = len(bought_players_role)

        with col:
            st.metric(
                f"{role_label} ({role})",
                f"{len(bought_players_role)}/{role_limit}",
                delta=f"-{bought_players_role['mln'].sum()} mln",
                border=True
            )

            if len(bought_players_role) > role_limit:
                st.error("Role limit exceeded")

            # Case of no player bought for this role
            if bought_players_role.empty:
                st.caption("No players purchased")
                continue
            
            # List the bought players
            for _, player_row in bought_players_role.iterrows():
                st.markdown(
                    f"- #### **{player_row['player']}**\n"
                    f"  {player_row['team']} · {player_row['mln']} mln"
                )

    return


# =============================================================================
# =============================== SCRIPT ======================================
# =============================================================================

fanta_managers = create_sidebar_settings()

st.title("⚽ Fantacalcio 26-27 - Create your own team")

fanta_players = myst.load_dataset("data/filtered_history_players.csv", filter_by_current_year=True)

st.divider()
st.subheader("Add a player to your team")

# Handling data players
filtered_players = player_filter(fanta_players)
bought_players_dict = get_bought_players_dict()

# Create the editable table
st.markdown("#### Available players")
create_editor_dataframe(filtered_players, bought_players_dict)

# Case of AI enabled to responde
if st.session_state["ai_enabled_key"] and filtered_players.shape[0] == 1:
    generate_ai_response(bought_players_dict)

st.divider()
st.subheader("Your team")

create_budget_columns(bought_players_dict)

