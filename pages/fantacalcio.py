import streamlit as st
import pandas as pd
import lib.ollama_api as llm
from lib.utils import (
    save_bought_players,
    restore_df_from
)
from lib.streamlit_api import (
    role_limits_dict,
    sync_filter,
    load_dataset,
)


st.set_page_config(
    page_title="Fantacalcio 26-27",
    page_icon="⚽",
    layout="wide",
)



# Fanta Manager name of the user
st.session_state.setdefault("my_fanta_manager_key", "Me")

# Restore bought players when a new Streamlit session starts
if "fanta_manager_players_dict_key" not in st.session_state:
    restored_players = restore_df_from("data/bought_players.csv")

    # Recreate the dictionary
    fanta_manager_players_dict = {}
    if not restored_players.empty:
        for fanta_manager, bought_players in restored_players.groupby("manager"):
            fanta_manager_players_dict[fanta_manager] = bought_players.reset_index(drop=True)

    # Restore my Fanta Manager name
    my_fanta_manager = st.session_state["my_fanta_manager_key"]
    fanta_manager_players_dict.setdefault(my_fanta_manager, pd.DataFrame())
    st.session_state["fanta_manager_players_dict_key"] = fanta_manager_players_dict

# Fanta Managers with the bought players
fanta_manager_players_dict = st.session_state["fanta_manager_players_dict_key"]

# Fanta Manager names
st.session_state.setdefault("fanta_managers_key", list(fanta_manager_players_dict.keys()))

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
                    current_fanta_manager = st.session_state["my_fanta_manager_key"]
                    bought_players = fanta_manager_players_dict.pop(current_fanta_manager, pd.DataFrame())
                    if not bought_players.empty and "manager" in bought_players.columns:
                        bought_players["manager"] = my_new_fanta_manager
                    fanta_manager_players_dict[my_new_fanta_manager] = bought_players
                    fanta_managers.remove(current_fanta_manager)
                    fanta_managers.append(my_new_fanta_manager)
                    st.session_state["fanta_managers_key"] = fanta_managers
                    st.session_state["my_fanta_manager_key"] = my_new_fanta_manager
                    st.session_state["fanta_manager_players_dict_key"] = fanta_manager_players_dict

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
                    fanta_manager_players_dict[new_fanta_manager] = pd.DataFrame()
                    st.session_state["fanta_managers_key"] = fanta_managers
                    st.session_state["fanta_manager_players_dict_key"] = fanta_manager_players_dict

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
    st.session_state.setdefault("selected_fanta_manager_key", "")

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
            on_change=sync_filter,
            args=("fanta_player_key", "fanta_player_widget_key"),
        )
    with cols[2]:
        selected_team = st.selectbox(
            "Select team",
            options=teams,
            index=None,
            placeholder="Select a team...",
            key="fanta_team_widget_key",
            on_change=sync_filter,
            args=("fanta_team_key", "fanta_team_widget_key"),
        )
    with cols[4]:
        selected_role = st.selectbox(
            "Select role",
            options=roles,
            index=None,
            placeholder="Select a role...",
            key="fanta_role_widget_key",
            on_change=sync_filter,
            args=("fanta_role_key", "fanta_role_widget_key"),
        )
    with cols[6]:
        selected_fanta_manager = st.selectbox(
            "Select a Fanta Manager",
            options=st.session_state["fanta_managers_key"],
            index=None,
            placeholder="Select a manager...",
            key="fanta_managers_widget_key",
            on_change=sync_filter,
            args=("selected_fanta_manager_key", "fanta_managers_widget_key"),
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
        bought_players = fanta_manager_players_dict.get(selected_fanta_manager, pd.DataFrame())
        bought_player_ids = bought_players["id"] if "id" in bought_players.columns else []
        filtered_df = filtered_df[filtered_df["id"].isin(bought_player_ids)]
    
    # Store in session_state
    st.session_state["filtered_players"] = filtered_df
    return filtered_df


def generate_ai_response(fanta_manager_players_dict: dict):
    # Data preparation
    my_players = fanta_manager_players_dict.get(st.session_state["my_fanta_manager_key"], pd.DataFrame()).copy()
    if my_players.empty:
        my_players = pd.DataFrame(columns=["role", "mln"])
    my_players["mln"] = pd.to_numeric(my_players["mln"], errors="coerce").fillna(0).astype(int)
    total_spent = my_players["mln"].sum()
    available_budget = st.session_state["fantacalcio_budget_key"] - total_spent

    role_counts = {
        role: len(my_players.loc[my_players["role"] == role])
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


def create_editor_dataframe(filtered_players: pd.DataFrame, fanta_manager_players_dict: dict):

    # Create the players dataframe to be shown
    bought_players_by_id = {}
    for fanta_manager, bought_players in fanta_manager_players_dict.items():
        for _, bought_player in bought_players.iterrows():
            bought_player_data = bought_player.to_dict()
            bought_player_data["manager"] = fanta_manager
            bought_players_by_id[str(bought_player["id"])] = bought_player_data

    players_editor_df = filtered_players.copy()
    bought_values = players_editor_df["id"].map(lambda player_id: bought_players_by_id.get(str(player_id), {}).get("manager"))
    bought_values = bought_values.fillna("").astype(str)
    mln_values = players_editor_df["id"].map(lambda player_id: bought_players_by_id.get(str(player_id), {}).get("mln", 0))
    mln_values = pd.to_numeric(mln_values, errors="coerce").fillna(0).astype(int)
    players_editor_df.insert(loc=0, column="bought", value=bought_values)
    players_editor_df.insert(loc=1, column="mln", value=mln_values)

    # Use a different widget key when the visible players change.
    fanta_managers = st.session_state["fanta_managers_key"]
    visible_player_ids = tuple(players_editor_df["id"].astype(str).tolist())
    editor_state = (visible_player_ids, tuple(fanta_managers))
    editor_key = f"purchase_editor_{abs(hash(editor_state))}_key"

    # Apply pending manager selections before styling the rows
    editor_changes = st.session_state.get(editor_key, {}).get("edited_rows", {})
    for row_position, changes in editor_changes.items():
        if "bought" in changes:
            selected_manager = changes["bought"]
            selected_manager = "" if pd.isna(selected_manager) else str(selected_manager)
            players_editor_df.iloc[int(row_position), players_editor_df.columns.get_loc("bought")] = selected_manager

    # Highlight players bought by the user or by another fanta manager
    def highlight_bought_rows(row):
        if row["bought"] == st.session_state["my_fanta_manager_key"]:
            row_style = "background-color: rgba(40, 167, 69, 0.25)"
        elif row["bought"] in fanta_managers:
            row_style = "background-color: rgba(220, 53, 69, 0.25)"
        else:
            row_style = ""
        return [row_style] * len(row)

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
                min_value=0,
                step=1,
                format="%d",
                alignment="center",
            ),
            "id": st.column_config.NumberColumn("ID", alignment="center"),
            "player": st.column_config.TextColumn("Player", alignment="center"),
            "team": st.column_config.TextColumn("Team", alignment="center"),
            "fanta_role": st.column_config.TextColumn("R", alignment="center"),
        }
    )

    # Create the table
    edited_players = st.data_editor(
        players_editor_df.style.apply(highlight_bought_rows, axis=1),
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

        # Remove the player from the previous fanta manager
        for fanta_manager, bought_players in fanta_manager_players_dict.items():
            if not bought_players.empty and "id" in bought_players.columns:
                fanta_manager_players_dict[fanta_manager] = bought_players.loc[bought_players["id"] != player_row["id"]].copy()

        # Add the player to the selected fanta manager
        if selected_manager in fanta_managers:
            bought_players = fanta_manager_players_dict.get(selected_manager, pd.DataFrame()).to_dict("records")
            bought_players.append(player_data)
            fanta_manager_players_dict[selected_manager] = pd.DataFrame(bought_players)

    # Store the updated auction state
    st.session_state["fanta_manager_players_dict_key"] = fanta_manager_players_dict
    return


def create_fanta_managers_stats():

    fanta_managers = st.session_state["fanta_managers_key"]
    starting_budget = st.session_state.get("fantacalcio_budget_key", 500)
    total_players_limit = sum(role_limits_dict.values())

    # Show up to four fanta managers on each row
    for row_start in range(0, len(fanta_managers), 4):
        current_managers = fanta_managers[row_start:row_start + 4]
        cols = st.columns(len(current_managers))

        for i, fanta_manager in enumerate(current_managers):
            bought_players_df = fanta_manager_players_dict.get(fanta_manager, pd.DataFrame()).copy()
            if bought_players_df.empty:
                bought_players_df = pd.DataFrame(columns=["role", "mln"])
            bought_players_df["mln"] = pd.to_numeric(bought_players_df["mln"], errors="coerce").fillna(0).astype(int)
            total_spent = bought_players_df["mln"].sum()
            available_budget = starting_budget - total_spent

            role_counts = {
                role: len(bought_players_df.loc[bought_players_df["role"] == role])
                for role in role_limits_dict
            }
            role_spending = {
                role: bought_players_df.loc[bought_players_df["role"] == role, "mln"].sum()
                for role in role_limits_dict
            }

            bought_p = role_counts["P"]
            bought_d = role_counts["D"]
            bought_c = role_counts["C"]
            bought_a = role_counts["A"]
            tot_p = role_limits_dict["P"]
            tot_d = role_limits_dict["D"]
            tot_c = role_limits_dict["C"]
            tot_a = role_limits_dict["A"]

            with cols[i]:
                st.metric(
                    label=f"{fanta_manager} · Available",
                    value=f"{available_budget} mln",
                    delta=f"-{total_spent} mln · {bought_players_df.shape[0]}/{total_players_limit} players",
                    delta_color="inverse",
                    icon="💰",
                    border=True
                )

                st.caption(
                    f"P: {bought_p}/{tot_p} · {role_spending['P']} mln  \n"
                    f"D: {bought_d}/{tot_d} · {role_spending['D']} mln  \n"
                    f"C: {bought_c}/{tot_c} · {role_spending['C']} mln  \n"
                    f"A: {bought_a}/{tot_a} · {role_spending['A']} mln"
                )

                if available_budget < 0:
                    st.error("Budget exceeded")


def create_current_purchases(fanta_manager_players_dict: dict, fanta_manager=None):
    # Create the df
    if fanta_manager is None:
        fanta_manager = st.session_state["my_fanta_manager_key"]
    bought_players_df = fanta_manager_players_dict.get(fanta_manager, pd.DataFrame()).copy()
    if bought_players_df.empty:
        bought_players_df = pd.DataFrame(columns=["player", "team", "role", "mantra_role", "manager", "mln"])
    bought_players_df["mln"] = pd.to_numeric(bought_players_df["mln"], errors="coerce").fillna(0).astype(int)

    # Compute some budget metric
    starting_budget = st.session_state.get("fantacalcio_budget_key", 500)
    total_spent = bought_players_df["mln"].sum()
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
            label=f"Available for :blue[**{fanta_manager}**]",
            value=f":green[{available_budget}] mln",
            delta=f"-{total_spent} mln spent",
            icon="💰",
            border=True
        )

        if available_budget < 0:
            st.error("Budget exceeded")

    # Create the columns for the bought players
    for role, (col, role_label, role_limit) in role_columns_dict.items():

        # Players bought with the role "role"
        bought_players_role = bought_players_df.loc[bought_players_df["role"] == role]
        st.session_state[f"{fanta_manager}_num_of_bought_{role}_key"] = len(bought_players_role)

        with col:
            with st.container(border=True):
                st.metric(
                    label=f"{role_label} ({role})",
                    value=f"{len(bought_players_role)}/{role_limit}",
                    delta=f"-{bought_players_role['mln'].sum()} mln"
                )

                if len(bought_players_role) > role_limit:
                    st.error("Role limit exceeded")

                # Case of no player bought for this role
                if bought_players_role.empty:
                    st.caption("No players purchased")
                    continue

                st.divider()
                
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

fanta_players = load_dataset("data/filtered_history_players.csv", filter_by_current_year=True)

st.divider()
st.subheader("Add a player to your team")

# Handling data players
filtered_players = player_filter(fanta_players)

# Create the editable table
st.markdown("#### Fanta list")
create_editor_dataframe(filtered_players, fanta_manager_players_dict)

# Case of AI enabled to responde
if st.session_state["ai_enabled_key"] and filtered_players.shape[0] == 1:
    generate_ai_response(fanta_manager_players_dict)

st.divider()
st.subheader("Current teams")
for fanta_manager in fanta_manager_players_dict.keys():
    create_current_purchases(fanta_manager_players_dict, fanta_manager)

# Save bought players
bought_players_dataframes = [bought_players for bought_players in fanta_manager_players_dict.values() if not bought_players.empty]
if bought_players_dataframes:
    to_save_df = pd.concat(bought_players_dataframes, ignore_index=True)
else:
    to_save_df = pd.DataFrame(columns=["id", "player", "team", "role", "mantra_role", "manager", "mln"])
save_bought_players(path="data/bought_players.csv", df=to_save_df)
